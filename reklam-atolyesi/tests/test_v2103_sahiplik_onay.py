"""2.10.3: sahiplik, onay ve silme kapıları (dış kod denetimi, Dalga A). Sentetik veri; ağ yok."""
from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ROOT, make_active_profile, run_hook
from test_analytics import build_campaign
from test_hooks import EL, SID, deny_of, enter_mode
from admem.util import AdMemoryError


# ----------------------------------------------------------------------------- profil yalıtımı
def test_checkpoint_close_refuses_foreign_cycle(store):
    pid, cid, cyid = build_campaign(store)
    store.checkpoint_save(pid, "S04", {"next_step": "x"}, cid, cyid)
    other = make_active_profile(store, "Marka B", "act_B", "Ürün B")["profile"]["id"]
    with pytest.raises(AdMemoryError, match="bu profile ait değil"):
        store.checkpoint_close(other, "S04", "", None, cyid)
    assert store.checkpoint_get(pid, cid, cyid, "S04")  # A'nın notu açık kaldı
    assert store.checkpoint_close(pid, "S04", "", cid, cyid)["closed"] is True


def test_scene_cache_key_is_per_profile(store):
    a = make_active_profile(store)["profile"]["id"]
    b = make_active_profile(store, "Marka B", "act_B", "Ürün B")["profile"]["id"]
    fa = store.profile_dir(a) / "sahne.mp4"
    fb = store.profile_dir(b) / "sahne.mp4"
    for f, body in ((fa, b"A" * 10), (fb, b"B" * 10)):
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(body)
    store.scene_cache_put(a, "k1", str(fa))
    store.scene_cache_put(b, "k1", str(fb))
    assert store.scene_cache_get(a, "k1")["path"] == str(fa)
    assert store.scene_cache_get(b, "k1")["path"] == str(fb)
    with pytest.raises(AdMemoryError, match="bu profilin klasöründe değil"):
        store.scene_cache_put(a, "k2", str(fb))
    fa.unlink()  # A'nın bozuk kaydı silinirken B'ninki kalır
    assert store.scene_cache_get(a, "k1")["hit"] is False
    assert store.scene_cache_get(b, "k1")["hit"] is True


def test_scene_cache_migration_keeps_rows(data_dir, clock):
    from admem import db as DB
    from admem.store import Store
    path = data_dir / "db" / "eski.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    for f in sorted(DB.MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql")):
        if int(f.name[:3]) >= 10:
            break
        for stmt in DB._split_sql(f.read_text(encoding="utf-8")):
            conn.execute(stmt)
        conn.execute("INSERT INTO schema_meta(version, applied_at) VALUES (?, 'x')", (int(f.name[:3]),))
    conn.execute("INSERT INTO profiles(id,slug,name,created_at) VALUES(1,'p','P','x')")
    conn.execute("INSERT INTO scene_cache(key,profile_id,path,sha256,created_at) VALUES('k',1,'/x','h','x')")
    conn.commit()
    conn.close()
    s = Store(path, data_dir)
    try:
        assert DB.current_version(s.conn) == DB.SCHEMA_VERSION >= 10
        assert s.q1("SELECT * FROM scene_cache WHERE key='k' AND profile_id=1")["path"] == "/x"
    finally:
        s.close()


# ----------------------------------------------------------------------------- onay
def _approved_item(store, after):
    pid, cid, cyid = build_campaign(store)
    it = {"action": "Günlük bütçeyi artır", "reason_kind": "structure", "dedupe_key": "butce", "before": {"daily_budget": 100},
          "after": after}
    aid = store.action_items_set(pid, cid, [it])["created"][0]
    store.action_item_set_status(pid, aid, "approved", "evet, onaylıyorum")
    return pid, cid, aid, it


def test_changed_target_needs_new_approval(store):
    pid, cid, aid, it = _approved_item(store, {"daily_budget": 110})
    r = store.action_items_set(pid, cid, [{**it, "after": {"daily_budget": 120}}])
    row = store.q1("SELECT * FROM action_items WHERE id=?", (aid,))
    assert r["needs_reapproval"] == [aid] and row["status"] == "proposed" and row["decision_id"] is None
    assert row["after_json"] == {"daily_budget": 120}
    store.action_item_set_status(pid, aid, "approved", "120 de olur")
    assert store.q1("SELECT status FROM action_items WHERE id=?", (aid,))["status"] == "approved"


def test_new_evidence_keeps_approval(store):
    pid, cid, aid, it = _approved_item(store, {"daily_budget": 110})
    r = store.action_items_set(pid, cid, [{**it, "evidence": {"not": "yeni okuma"}}])
    assert "needs_reapproval" not in r
    assert store.q1("SELECT status FROM action_items WHERE id=?", (aid,))["status"] == "approved"


def test_verify_requires_every_target_field(store):
    pid, cid, aid, _ = _approved_item(store, {"daily_budget": 110, "status": "PAUSED"})
    r = store.action_items_verify(pid, cid, [{"item_id": aid, "source": "meta_mcp", "observed": {"daily_budget": 110}}])
    assert r["results"][0]["status"] == "approved" and r["results"][0]["unseen"] == ["status"]
    r = store.action_items_verify(pid, cid, [{"item_id": aid, "source": "meta_mcp", "observed": {"daily_budget": 110, "status": "PAUSED"}}])
    assert r["results"][0]["status"] == "applied"


def test_verify_mismatch_is_not_applied(store):
    pid, cid, aid, _ = _approved_item(store, {"daily_budget": 110, "status": "PAUSED"})
    r = store.action_items_verify(pid, cid, [{"item_id": aid, "source": "meta_mcp", "observed": {"daily_budget": 100, "status": "PAUSED"}}])
    assert r["results"][0]["status"] == "not_applied"


def test_gate_refuses_document_changed_after_completion(store):
    import draft_docs
    p0 = store.profile_create("Marka K")
    pid = p0["id"]
    store.stage_start(pid, "S00a")
    f = Path(draft_docs.write_stage_doc(store, pid, "S00a")["path"])
    run = store.stage_complete(pid, "S00a", [{"path": str(f)}], "marka tanışması")["stage_run"]
    f.write_bytes(f.read_bytes() + b"\nsonradan eklenen satir\n")
    with pytest.raises(AdMemoryError, match="çıktı dosyası değişti"):
        store.gate_approve(pid, run["id"], run["output_version"], "onaylıyorum")
    f2 = Path(draft_docs.write_stage_doc(store, pid, "S00a")["path"])  # yeniden tamamlanan sürüm onaylanır
    run = store.stage_complete(pid, "S00a", [{"path": str(f2)}], "marka tanışması")["stage_run"]
    assert store.gate_approve(pid, run["id"], run["output_version"], "onaylıyorum")["approved"]


def test_frozen_priors_cannot_be_reopened_by_status(store):
    pid, cid, cyid = build_campaign(store)
    store.ex("UPDATE cycles SET status='measuring', priors_snapshot_json='{\"p\": 1}' WHERE id=?", (cyid,))
    with pytest.raises(AdMemoryError, match="geri alınamaz"):
        store.cycle_set(pid, cyid, status="production")
    with pytest.raises(AdMemoryError, match="dondurulmuş"):
        store.cycle_set(pid, cyid, priors_snapshot_json={"p": 2})
    store.cycle_set(pid, cyid, status="closed")  # ileri yön serbest


# ----------------------------------------------------------------------------- unutma
@pytest.mark.parametrize("content", ["%", "_", "a%b"])
def test_forget_does_not_treat_wildcards_as_patterns(store, content):
    pid = make_active_profile(store)["profile"]["id"]
    store.memory_add("preference", "tercih", content, "user", profile_id=pid, force_new=True)
    iid = store.q1("SELECT id FROM memory_items WHERE content=?", (content,))["id"]
    store.journal_log("İlgisiz bir günlük özeti", profile_id=pid)
    store.memory_forget(iid, "unut", profile_id=pid)
    sums = [r["summary"] for r in store.qa("SELECT summary FROM journal WHERE profile_id=?", (pid,))]
    assert "İlgisiz bir günlük özeti" in sums and "[unutma isteğiyle kaldırıldı]" not in sums


def test_forget_still_scrubs_journal_mentions(store):
    pid = make_active_profile(store)["profile"]["id"]
    text = "Müşteri sabah paylaşımlarını tercih ediyor"
    store.memory_add("preference", "tercih", text, "user", profile_id=pid, force_new=True)
    iid = store.q1("SELECT id FROM memory_items WHERE content=?", (text,))["id"]
    store.journal_log(f"Not: {text}.", profile_id=pid)
    r = store.memory_forget(iid, "unut", profile_id=pid)
    assert r["journal_scrubbed"] == 1


# ----------------------------------------------------------------------------- hook'lar
def test_guard_hooks_block_when_they_cannot_run():
    import gen_config
    for target in ("windows", "posix"):
        pre = gen_config.hooks_json(target)["hooks"]["PreToolUse"]
        # 2.10.12: upload_guard her Bash/Write çağrısında çalışır ve plugin dışı oturumlara da dokunur; başlayamazsa bütün komutları
        # durdurmasın diye engellemez. Bayt adımının asıl kapısı tamamlama denetimidir (cost_guard, engelleyen).
        guards = [h for g in pre for h in g["hooks"] if not h["args"][0].endswith("upload_guard.py")]
        assert guards and all(h.get("onFailure") == "block" for h in guards)
        assert all(not h.get("onFailure") for g in pre for h in g["hooks"] if h["args"][0].endswith("upload_guard.py"))
    on_disk = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert on_disk == gen_config.hooks_json("windows")


def _personal_upload_setup(store, ddir):
    enter_mode(ddir)
    pid = make_active_profile(store)["profile"]["id"]
    store.session_bind(SID, profile_id=pid)
    store.brand_upsert(pid, processing_permissions_json={"providers": {"elevenlabs": {"basis": "açık rıza", "evidence": "belge.pdf"}}})
    folder = store.profile_dir(pid) / "malzeme"
    folder.mkdir(parents=True, exist_ok=True)
    ok, other = folder / "kisi-ses.wav", folder / "baska-kisi.wav"
    ok.write_bytes(b"R" * 64)
    other.write_bytes(b"S" * 80)
    ev = store.profile_dir(pid) / "riza.pdf"
    ev.write_bytes(b"%PDF")
    c = store.consent_add(pid, "Kişi 1", "voice", "açık rıza", "2026-03-01", str(ev), {"providers": ["elevenlabs"]})
    return pid, ok, other, c["id"]


def test_personal_upload_permission_needs_files(store, data_dir):
    pid, ok, _, cid = _personal_upload_setup(store, data_dir)
    with pytest.raises(AdMemoryError, match="files"):
        store.processing_permission_check(pid, "elevenlabs", "seslendirme", True, ["voice"], SID, [cid])


def test_upload_permission_bound_to_file_and_consent(store, data_dir):
    pid, ok, other, cid = _personal_upload_setup(store, data_dir)
    store.processing_permission_check(pid, "elevenlabs", "seslendirme", True, ["voice"], SID, [cid], files=[str(ok)])
    up = EL + "creative_create_asset_upload"
    assert run_hook("cost_guard.py", {"session_id": SID, "tool_name": up,
                                      "tool_input": {"file_name": ok.name, "mime_type": "audio/wav", "size_bytes": 64}}, data_dir) is None
    assert deny_of(run_hook("cost_guard.py", {"session_id": SID, "tool_name": up,
                                              "tool_input": {"file_name": other.name, "mime_type": "audio/wav", "size_bytes": 80}}, data_dir))
    assert deny_of(run_hook("cost_guard.py", {"session_id": SID, "tool_name": up,  # aynı ad, başka içerik (boyut tutmuyor)
                                              "tool_input": {"file_name": ok.name, "mime_type": "audio/wav", "size_bytes": 99}}, data_dir))
    store.consent_withdraw(pid, cid, "kişi vazgeçti")
    out = run_hook("cost_guard.py", {"session_id": SID, "tool_name": up,
                                     "tool_input": {"file_name": ok.name, "mime_type": "audio/wav", "size_bytes": 64}}, data_dir)
    assert deny_of(out) and "geri çekilmiş" in out["hookSpecificOutput"]["permissionDecisionReason"]


# ----------------------------------------------------------------------------- yedekten dönüş
def test_restore_failed_copy_leaves_database_in_place(store, data_dir, monkeypatch):
    sys.path.insert(0, str(ROOT / "scripts" / "setup"))
    import db_restore
    make_active_profile(store, "Önce")
    b = store.backup(reason="deneme")
    store.close()
    db = data_dir / "db" / "ad-memory.sqlite"
    before = db.read_bytes()

    def broken_copy(src, dst, *a, **k):
        Path(dst).write_bytes(b"yarim")
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(db_restore.shutil, "copy2", broken_copy)
    with pytest.raises(SystemExit, match="değiştirilmedi"):
        db_restore.restore(data_dir, Path(b["path"]), True)
    assert db.read_bytes() == before
    assert not (data_dir / "db" / "ad-memory.sqlite.restore-tmp").exists()
    assert not list((data_dir / "db").glob("onceki-*"))
