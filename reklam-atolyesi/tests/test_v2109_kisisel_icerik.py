"""2.10.9: kişisel içerik, silme, profil ayrımı ve oturum kilidi (dış bağımsız denetim B4, B7, B8, B11, B12). Sentetik veri; ağ yok."""
from __future__ import annotations

import json
import sqlite3
import sys
import time

import pytest

from conftest import ROOT, make_active_profile, out_file, run_hook
from test_hooks import OWN, SID, deny_of, enter_mode
from admem.util import AdMemoryError, LockBusy, file_lock, backup_inventory

sys.path.insert(0, str(ROOT / "hooks"))
sys.path.insert(0, str(ROOT / "scripts" / "setup"))


# ----------------------------------------------------------------------------- yorum kartı ve kişi izni (B4)
def _review_setup(store, rating=2.0, mode="hidden", name="Gizli Ad"):
    a = make_active_profile(store)
    pid, prod = a["profile"]["id"], a["product"]["id"]
    c = store.campaign_create(pid, prod, "K")
    cid = c["campaign"]["id"]
    ev = out_file(store, pid, cid, "izin.pdf")
    rv = store.review_add(pid, "Paket geldi.", mode, "yazili", "2026-03-01", ev, display_name=name, rating=rating)
    return pid, cid, c["cycle"]["id"], rv


def _card_plan(review_id, props, layers_extra=None):
    layers = [{"type": "component", "component": "ReviewCard", "review_id": review_id, "props": props}]
    return {"campaign": "k", "cycle_id": 1, "concept": "A", "hook": "h1", "format": "9x16", "purpose": "test", "status": "draft",
            "version": 1, "duration_s": 2, "fps": 30,
            "scenes": [{"id": "s1", "role": "proof", "start_s": 0, "dur_s": 2, "audio": {"mode": "none", "decision_id": "d1"},
                        "layers": layers + (layers_extra or [])}]}


def test_review_card_must_match_record(store):
    pid, cid, _, rv = _review_setup(store)
    plan = _card_plan(rv["id"], {"reviewId": rv["id"], "quote": "Bu ürün hayatımı değiştirdi.", "rating": 5, "displayName": "Görünen Ad"})
    errs = store.edit_plan_validate(pid, cid, plan=plan)["errors"]
    joined = " ".join(errs)
    assert "ReviewCard metin" in joined and "ReviewCard puan" in joined and "ReviewCard gösterilen ad" in joined


def test_review_card_matching_record_passes(store):
    pid, cid, _, rv = _review_setup(store, mode="initials", name="Ayşe Kaya")
    plan = _card_plan(rv["id"], {"reviewId": rv["id"], "quote": "Paket geldi.", "rating": 2, "displayName": "A. K."})
    assert not [e for e in store.edit_plan_validate(pid, cid, plan=plan)["errors"] if "ReviewCard" in e]


def test_review_card_props_filled_from_record(store):
    pid, cid, _, rv = _review_setup(store, mode="full", name="Ayşe Kaya", rating=4)
    filled = store._fill_review_props(pid, _card_plan(rv["id"], {}))
    props = filled["scenes"][0]["layers"][0]["props"]
    assert props == {"reviewId": rv["id"], "quote": "Paket geldi.", "rating": 4, "displayName": "Ayşe Kaya"}


def test_plan_with_person_without_consent_rejected(store):
    pid, cid, _, rv = _review_setup(store)
    clip = out_file(store, pid, cid, "klip.mp4", "video")
    a = store.asset_register(pid, "footage", clip, campaign_id=cid, people=[{"label": "kişi 1", "consent_id": None}])
    plan = _card_plan(rv["id"], {}, [{"type": "video", "source": {"kind": "footage", "asset": f"a{a['id']}"}}])
    errs = store.edit_plan_validate(pid, cid, plan=plan)["errors"]
    assert any("geçerli izin yok" in e for e in errs)


def test_withdrawn_review_blocks_creative_register(store):
    pid, cid, cyid, rv = _review_setup(store)
    plan = store._fill_review_props(pid, _card_plan(rv["id"], {}))
    with store.tx():
        plan_id = store.ex("""INSERT INTO edit_plans(campaign_id,cycle_id,format,purpose,status,version,plan_json,sha256,path,created_at)
                              VALUES(?,?,?,?,?,?,?,?,?,?)""", (cid, cyid, "9x16", "production", "ready", 1, json.dumps(plan), "x", "p", "t")).lastrowid
    assert store._plan_consent_errors(pid, plan_id) == []
    store.review_withdraw(pid, rv["id"], "kullanıcı geri çekti")
    assert any("geri çekilmiş" in e for e in store._plan_consent_errors(pid, plan_id))
    with pytest.raises(AdMemoryError, match="kreatif kaydedilmedi"):
        store.creative_register(pid, cid, cyid, out_file(store, pid, cid, "x.mp4"), "test", edit_plan_id=plan_id)


# ----------------------------------------------------------------------------- unut ve yedekler (B7)
def _copy_db(store, dest):
    src = sqlite3.connect(store.data_dir / "db" / "ad-memory.sqlite")
    dst = sqlite3.connect(dest)
    src.backup(dst)
    dst.close()
    src.close()


def test_forget_covers_update_backup_and_previous_db(store, data_dir):
    pid = make_active_profile(store)["profile"]["id"]
    it = store.memory_add("preference", "note", "Gizli tercih metni", "user", profile_id=pid, force_new=True)["created"]
    bdir = data_dir / "backups"
    bdir.mkdir(exist_ok=True)
    upd = bdir / "guncelleme-20261106-000000-000000.sqlite"
    _copy_db(store, upd)
    prev = data_dir / "db" / "onceki-20261106-000000"
    prev.mkdir()
    _copy_db(store, prev / "ad-memory.sqlite")
    out = store.memory_forget(it["id"], "unut", profile_id=pid)
    assert not upd.exists() and not prev.exists()
    assert upd.name in out["backups_removed"] and prev.name in out["backups_removed"]
    assert out["local_copies_complete"] is True


def test_forget_reports_unreadable_backup(store, data_dir):
    pid = make_active_profile(store)["profile"]["id"]
    it = store.memory_add("preference", "note", "Başka gizli metin", "user", profile_id=pid, force_new=True)["created"]
    bdir = data_dir / "backups"
    bdir.mkdir(exist_ok=True)
    (bdir / "guncelleme-20261106-000001-000000.sqlite").write_bytes(b"bu bir veritabani degil" * 50)
    out = store.memory_forget(it["id"], "unut", profile_id=pid)
    assert out["local_copies_complete"] is False and out["backups_unreadable"] and "tamamlandı deme" in out["warning"]


def test_restore_check_lists_all_copies(store, data_dir):
    import db_restore as DR
    bdir = data_dir / "backups"
    bdir.mkdir(exist_ok=True)
    _copy_db(store, bdir / "guncelleme-20261106-000002-000000.sqlite")
    (data_dir / "db" / "onceki-20261106-000002").mkdir()
    r = DR.check(data_dir)
    assert any(b["kind"] == "update" and b["check"] == "ok" for b in r["backups"])
    assert r["previous_databases"] and r["previous_databases"][0]["restorable"] is False


def test_backup_limit_counts_update_backups(store, data_dir):
    bdir = data_dir / "backups"
    bdir.mkdir(exist_ok=True)
    for i in range(3):
        _copy_db(store, bdir / f"guncelleme-2026110{i}-000000-000000.sqlite")
        time.sleep(0.01)
    store.backup(reason="test", keep=2)
    inv = [r for r in backup_inventory(data_dir) if r["kind"] in ("backup", "update")]
    assert len(inv) == 2 and inv[0]["kind"] == "backup"


# ----------------------------------------------------------------------------- profil ayrımı (B8)
def test_asset_from_other_profile_rejected(store):
    a = make_active_profile(store, "Marka A", "act_A")
    b = make_active_profile(store, "Marka B", "act_B", "Ürün B")
    ca = store.campaign_create(a["profile"]["id"], a["product"]["id"], "KA")["campaign"]["id"]
    f = out_file(store, a["profile"]["id"], ca, "ses.wav", "ses")
    with pytest.raises(AdMemoryError, match="başka bir profilin klasöründe"):
        store.asset_register(b["profile"]["id"], "audio", f)


def test_external_file_copied_into_profile_inbox(store, tmp_path):
    a = make_active_profile(store)
    pid = a["profile"]["id"]
    src = tmp_path / "masaustu" / "ham.mp4"
    src.parent.mkdir()
    src.write_bytes(b"ham video")
    row = store.asset_register(pid, "footage", str(src))
    dest = store.profile_dir(pid) / "inbox"
    assert row["path"].startswith(str(dest)) and open(row["path"], "rb").read() == b"ham video"


def _bind_profile(ddir, pid):
    p = ddir / ".sessions" / f"{SID}.json"
    s = json.loads(p.read_text(encoding="utf-8"))
    s["profile_id"] = pid
    p.write_text(json.dumps(s), encoding="utf-8")


def test_meta_guard_compares_account_with_session_profile(store, data_dir):
    a = make_active_profile(store, "Marka A", "act_111")
    enter_mode(data_dir)
    _bind_profile(data_dir, a["profile"]["id"])
    call = lambda tin: run_hook("meta_guard.py", {"session_id": SID, "tool_name": OWN + "ads_get_ad_entities", "tool_input": tin}, data_dir)
    assert call({"ad_account_id": "111"}) is None
    assert call({"ad_account_id": "act_111"}) is None
    out = call({"ad_account_id": "222"})
    assert deny_of(out) and "bu oturumdaki markanın hesabı değil" in json.dumps(out, ensure_ascii=False)
    # hesap belirtmeyen ortak çağrı (hesap listesi) denetime girmez
    assert run_hook("meta_guard.py", {"session_id": SID, "tool_name": OWN + "ads_get_ad_accounts", "tool_input": {}}, data_dir) is None


# ----------------------------------------------------------------------------- oturum kilidi (B12)
def test_lock_timeout_does_not_write(tmp_path):
    target = tmp_path / "oturum.json"
    with file_lock(target):
        with pytest.raises(LockBusy):
            with file_lock(target, timeout=0.1):
                target.write_text("yazılmamalı", encoding="utf-8")
    assert not target.exists()


def test_store_session_update_fails_when_locked(store):
    path = store._session_path(SID)
    with file_lock(path):
        with pytest.raises(AdMemoryError, match="değişiklik yazılmadı"):
            import admem.util as U
            orig = U.file_lock
            try:
                U.file_lock = lambda p, timeout=3.0, stale=10.0: orig(p, timeout=0.1, stale=stale)
                import admem.s_base as SB
                SB.file_lock = U.file_lock
                store._session_update(SID, lambda s: s.update(x=1))
            finally:
                U.file_lock = orig
                SB.file_lock = orig


def test_hooks_share_one_lock_implementation():
    import plugin_mode as pm
    src = (ROOT / "hooks" / "plugin_mode.py").read_text(encoding="utf-8")
    assert "O_EXCL" not in src  # kilit kodu yalnızca admem/util.py'de
    with pytest.raises(LockBusy):
        with pm.file_lock(ROOT / "tests" / ".kilit-denemesi"):
            with pm.file_lock(ROOT / "tests" / ".kilit-denemesi", timeout=0.1):
                pass


def test_navigator_keeps_fields_written_meanwhile(store, data_dir):
    import plugin_mode as pm
    enter_mode(data_dir)
    before = pm.load_session(data_dir, SID)
    after = json.loads(json.dumps(before))
    after["screen"] = "work"
    store._session_update(SID, lambda s: s.update(consumed_prompts=["p-onay"]))  # başka yazar araya girdi
    pm.save_changes(data_dir, SID, before, after)
    s = pm.load_session(data_dir, SID)
    assert s["consumed_prompts"] == ["p-onay"] and s["screen"] == "work"


# ----------------------------------------------------------------------------- dil seçeneği (B11)
def test_unused_language_option_removed(store):
    cfg = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert "language" not in cfg["userConfig"]
    with pytest.raises(AdMemoryError, match="yalnızca Türkçe"):
        store.settings_set("language", "en")
