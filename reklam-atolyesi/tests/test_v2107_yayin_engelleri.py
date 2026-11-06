"""2.10.7: yayın engelleri (dış bağımsız denetim B1–B3). Sentetik veri; ağ ve ücretli çağrı yok."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading

import pytest

import draft_docs as DD
from conftest import ROOT, make_active_profile, run_hook
from test_generation import LIC, P, setup
from test_hooks import EL, SID, deny_of, enter_mode
from test_v2103_sahiplik_onay import _personal_upload_setup
from admem import approval as AP
from admem.store import Store
from admem.util import AdMemoryError, now_iso


# ----------------------------------------------------------------------------- saat dilimi verisi (B3)
def test_timezones_work_without_system_database(tmp_path):
    """İşletim sisteminin IANA verisi yokken (Windows'taki durum) saat dilimleri kurulumdaki tzdata paketinden okunur."""
    code = ("import datetime as d, zoneinfo\n"
            "ist = zoneinfo.ZoneInfo('Europe/Istanbul'); ny = zoneinfo.ZoneInfo('America/New_York')\n"
            "w = d.datetime(2026, 1, 15, 12, tzinfo=ny).utcoffset(); s = d.datetime(2026, 7, 15, 12, tzinfo=ny).utcoffset()\n"
            "print(d.datetime(2026, 7, 1, tzinfo=ist).utcoffset().total_seconds(), w.total_seconds(), s.total_seconds())")
    env = {**os.environ, "PYTHONTZPATH": str(tmp_path / "sistem-verisi-yok")}
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["10800.0", "-18000.0", "-14400.0"]  # yaz saati geçişi de doğru


def test_brand_timezone_accepted_without_system_database(tmp_path):
    code = ("import sys; sys.path.insert(0, %r); sys.path.insert(0, %r)\n"
            "from admem.store import Store\n"
            "from pathlib import Path\n"
            "d = Path(%r); s = Store(d / 'db' / 'ad-memory.sqlite', d)\n"
            "p = s.profile_create('Marka'); s.brand_upsert(p['id'], name='Marka', timezone='Europe/Istanbul'); print('ok')"
            ) % (str(ROOT / "servers" / "ad_memory"), str(ROOT / "scripts" / "lib"), str(tmp_path))
    env = {**os.environ, "PYTHONTZPATH": str(tmp_path / "sistem-verisi-yok")}
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert out.stdout.strip().endswith("ok"), out.stderr


def test_dependency_and_install_check_carry_tzdata():
    txt = (ROOT / "servers" / "ad_memory" / "pyproject.toml").read_text(encoding="utf-8")
    assert '"tzdata"' in txt
    assert 'name = "tzdata"' in (ROOT / "servers" / "ad_memory" / "uv.lock").read_text(encoding="utf-8")
    sys.path.insert(0, str(ROOT / "scripts" / "setup"))
    import kurulum_dogrula as KD
    ok, detail = KD.tz_check()
    assert ok and detail["tzdata_paketi"]


# ----------------------------------------------------------------------------- onay biçimi (B1)
@pytest.mark.parametrize("text", ["Hayır, onaylamıyorum.", "Hayır, 120 kredi harcama", "onaylamıyorum", "evet ama önce sesi değiştir",
                                  "tamam, yarın bakarız", "onay yok", "", "   "])
def test_not_an_approval(text):
    assert not AP.check(text)[0]


@pytest.mark.parametrize("text", ["evet", "Onaylıyorum.", "evet onaylıyorum", "tamam, devam", "120 kredi için onaylıyorum",
                                  "/reklam-atolyesi:onayla", "/onayla 120 kredi", "kabul ediyorum"])
def test_explicit_approval(text):
    assert AP.check(text, 120)[0]


def test_number_in_message_must_match_approved_amount():
    assert not AP.check("evet, 100 kredi", 120)[0]
    assert AP.check("evet, 120 kredi", 120)[0]


def _awaiting_brand_gate(store):
    p = store.profile_create("Marka Z")
    store.brand_upsert(p["id"], name="Marka Z", meta_ad_account_id="act_Z", timezone="Europe/Istanbul", tone="nötr")
    store.stage_start(p["id"], "S00a")
    f = DD.write_stage_doc(store, p["id"], "S00a")["path"]
    r = store.stage_complete(p["id"], "S00a", [{"path": str(f)}], "marka tanışması")
    return p["id"], r["stage_run"]


def test_gate_refuses_a_no(store):
    pid, run = _awaiting_brand_gate(store)
    with pytest.raises(AdMemoryError, match="onay sayılmaz"):
        store.gate_approve(pid, run["id"], run["output_version"], "Hayır, onaylamıyorum.")
    assert store.q1("SELECT status FROM stage_runs WHERE id=?", (run["id"],))["status"] == "awaiting_gate"


def _say(store, sid, text, pid):
    def add(s):
        s.setdefault("user_prompts", []).append({"id": pid, "text": text, "at": now_iso()})
    store._session_update(sid, add)


def test_gate_takes_approval_from_users_own_last_message(store, clock):
    pid, run = _awaiting_brand_gate(store)
    sid = "oturum-onay-01"
    clock.advance(minutes=1)
    _say(store, sid, "Hayır, onaylamıyorum.", "m1")
    with pytest.raises(AdMemoryError, match="onay sayılmaz"):  # model "evet" yazsa da kullanıcının son mesajı esas alınır
        store.gate_approve(pid, run["id"], run["output_version"], "evet", session_id=sid)
    _say(store, sid, "evet onaylıyorum", "m2")
    out = store.gate_approve(pid, run["id"], run["output_version"], "", session_id=sid)
    assert out["approved"]
    dec = store.q1("SELECT * FROM decisions WHERE stage_run_id=?", (run["id"],))
    assert "evet onaylıyorum" in json.dumps(dec, ensure_ascii=False)


def test_message_written_before_document_or_reused_is_refused(store, clock):
    sid = "oturum-onay-02"
    _say(store, sid, "evet", "m0")  # belge gösterilmeden önce yazılmış
    clock.advance(minutes=1)
    pid, run = _awaiting_brand_gate(store)
    with pytest.raises(AdMemoryError, match="gösterilmeden önce"):
        store.gate_approve(pid, run["id"], run["output_version"], "", session_id=sid)
    clock.advance(minutes=1)
    _say(store, sid, "evet", "m1")
    clock.advance(minutes=1)
    g = setup(store)
    gen = store.generation_log(g[0], g[1], g[2], "creative_generate_speech", P, 120)
    clock.advance(minutes=1)
    _say(store, sid, "onaylıyorum", "m2")
    store.generation_approve(g[0], gen["id"], 120, 4, "", LIC, session_id=sid)
    with pytest.raises(AdMemoryError, match="başka bir onay"):  # aynı mesaj ikinci bir onaya kullanılamaz
        store.gate_approve(pid, run["id"], run["output_version"], "", session_id=sid)


def test_old_message_expires(store, clock):
    pid, run = _awaiting_brand_gate(store)
    sid = "oturum-onay-03"
    clock.advance(minutes=1)
    _say(store, sid, "evet", "m1")
    clock.advance(minutes=AP.APPROVAL_TTL_MIN + 1)
    with pytest.raises(AdMemoryError, match="dakikadan eski"):
        store.gate_approve(pid, run["id"], run["output_version"], "", session_id=sid)


def test_navigator_records_users_own_messages(store, data_dir):
    enter_mode(data_dir)
    run_hook("navigator.py", {"session_id": SID, "hook_event_name": "UserPromptSubmit", "prompt": "evet onaylıyorum", "prompt_id": "p2"},
             data_dir)
    s = json.loads((data_dir / ".sessions" / f"{SID}.json").read_text(encoding="utf-8"))
    assert [u["text"] for u in s["user_prompts"]][-2:] == ["Reklam Atölyesi", "evet onaylıyorum"]


def test_approval_tools_require_session():
    import inspect
    sys.path.insert(0, str(ROOT / "servers" / "ad_memory"))
    import server
    for name in ("gate_approve", "generation_approve", "action_item_set_status", "playbook_activate", "feedback_export"):
        prm = inspect.signature(getattr(server, name)).parameters["session_id"]
        assert prm.default is inspect.Parameter.empty, name


# ----------------------------------------------------------------------------- ücretli onay ve fiyat (B1)
def test_price_change_during_approval_is_refused(data_dir, clock):
    """İki bağlantı: onay tahmini okuduktan sonra öteki bağlantı fiyatı yükseltir. Onay yazılmaz, rezervasyon alınmaz."""
    read, resume = threading.Event(), threading.Event()
    err: list = []

    class Paused(Store):
        armed = False

        def q1(self, sql, args=()):
            r = super().q1(sql, args)
            if self.armed and sql.startswith("SELECT * FROM generations WHERE id="):
                self.armed = False
                read.set()
                assert resume.wait(10)
            return r

    db = data_dir / "db" / "ad-memory.sqlite"
    first = Paused(db, data_dir)
    pid, cid, cy = setup(first)
    g = first.generation_log(pid, cid, cy, "creative_generate_speech", P, 120)
    clock.advance(seconds=5)
    first.armed = True

    def approve():
        try:
            first.generation_approve(pid, g["id"], 120, 4, "120 kredi için onaylıyorum", LIC)
        except AdMemoryError as e:
            err.append(str(e))
    w = threading.Thread(target=approve)
    w.start()
    assert read.wait(5)
    second = Store(db, data_dir)
    second.generation_log(pid, cid, cy, "creative_generate_speech", P, 900)
    resume.set()
    w.join()
    assert err and "tahmin bu arada değişti" in err[0]
    row = second.q1("SELECT * FROM generations WHERE id=?", (g["id"],))
    assert not second.generation_reserve(cid, row["call_hash"], "t")["ok"]
    first.close()
    second.close()


def test_reserve_rechecks_price_cap(store):
    pid, cid, cy = setup(store)
    g = store.generation_log(pid, cid, cy, "creative_generate_speech", P, 120)
    store.generation_approve(pid, g["id"], 120, 4, "onaylıyorum", LIC)
    store.ex("UPDATE generations SET estimate_credits=900 WHERE id=?", (g["id"],))  # onay dışı bir yoldan değişen fiyat
    res = store.generation_reserve(cid, g["call_hash"], "t")
    assert not res["ok"] and "üst sınır" in res["reason"]


def test_approval_expires(store, clock):
    pid, cid, cy = setup(store)
    g = store.generation_log(pid, cid, cy, "creative_generate_speech", P, 120)
    store.generation_approve(pid, g["id"], 120, 4, "onaylıyorum", LIC)
    clock.advance(minutes=AP.APPROVAL_TTL_MIN + 1)
    res = store.generation_reserve(cid, g["call_hash"], "t")
    assert not res["ok"] and "süresi doldu" in res["reason"]


def test_two_open_prices_for_one_call_are_refused(store):
    pid, cid, cy = setup(store)
    store.generation_log(pid, cid, cy, "creative_generate_speech", P, 900, input_file_hashes={"a": "x2"})
    a = store.generation_log(pid, cid, cy, "creative_generate_speech", P, 120, input_file_hashes={"a": "x1"})
    store.generation_approve(pid, a["id"], 120, 4, "onaylıyorum", LIC)
    res = store.generation_reserve(cid, a["call_hash"], "t")
    assert not res["ok"] and "birden çok açık fiyat" in res["reason"]


def test_paid_approval_number_must_match_cap(store):
    pid, cid, cy = setup(store)
    g = store.generation_log(pid, cid, cy, "creative_generate_speech", P, 120)
    with pytest.raises(AdMemoryError, match="aynı değil"):
        store.generation_approve(pid, g["id"], 900, 4, "evet 120 kredi", LIC)


# ----------------------------------------------------------------------------- dosya izni (B2)
UP, FIN = EL + "creative_create_asset_upload", EL + "creative_finalize_asset_upload"


def _create(data_dir, f, size):
    return run_hook("cost_guard.py", {"session_id": SID, "tool_name": UP,
                                      "tool_input": {"file_name": f.name, "mime_type": "audio/wav", "size_bytes": size}}, data_dir)


def _finish(data_dir, asset="a1"):
    return run_hook("cost_guard.py", {"session_id": SID, "tool_name": FIN, "tool_input": {"asset_id": asset, "flow_id": "f"}}, data_dir)


def _started(data_dir, asset):
    """PostToolUse: sağlayıcının yanıtındaki kimlik ve adres başlatma kaydına yazılır (2.10.12)."""
    run_hook("upload_guard.py", {"session_id": SID, "hook_event_name": "PostToolUse", "tool_name": UP, "tool_input": {},
                                 "tool_response": {"asset_id": asset, "upload_url": f"https://yukleme.example/{asset}?imza=1"}}, data_dir)


def _sent(data_dir, asset):
    sys.path.insert(0, str(ROOT / "scripts" / "ingest"))
    import izinli_yukleme as IY
    out = IY.run(data_dir, SID, asset, None, put=lambda url, body, mime: 200)
    assert out["ok"], out


def test_changed_content_with_same_name_and_size_is_refused(store, data_dir):
    pid, ok, _, cid = _personal_upload_setup(store, data_dir)
    store.processing_permission_check(pid, "elevenlabs", "seslendirme", True, ["voice"], SID, [cid], files=[str(ok)])
    ok.write_bytes(b"Z" * 64)  # aynı yol, aynı boyut, başka içerik
    out = _create(data_dir, ok, 64)
    assert deny_of(out) and "değişmiş" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_finish_step_needs_a_started_upload_and_valid_permission(store, data_dir):
    pid, ok, _, cid = _personal_upload_setup(store, data_dir)
    store.processing_permission_check(pid, "elevenlabs", "seslendirme", True, ["voice"], SID, [cid], files=[str(ok)])
    assert deny_of(_finish(data_dir))  # başlatılmış yükleme yok
    assert _create(data_dir, ok, 64) is None
    _started(data_dir, "a1")
    _sent(data_dir, "a1")
    assert _finish(data_dir) is None  # olağan akış (2.10.12: kimlik yakalandı, baytlar betikle gitti)
    assert deny_of(_finish(data_dir, "baska"))  # bir başlatma bir tamamlama
    assert _create(data_dir, ok, 64) is None
    _started(data_dir, "a2")
    _sent(data_dir, "a2")
    store.consent_withdraw(pid, cid, "kişi vazgeçti")
    out = _finish(data_dir, "a2")
    assert deny_of(out) and "geri çekildi" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_name_without_size_is_not_enough(store, data_dir):
    pid, ok, _, cid = _personal_upload_setup(store, data_dir)
    store.processing_permission_check(pid, "elevenlabs", "seslendirme", True, ["voice"], SID, [cid], files=[str(ok)])
    assert deny_of(run_hook("cost_guard.py", {"session_id": SID, "tool_name": UP,
                                              "tool_input": {"file_name": ok.name, "mime_type": "audio/wav"}}, data_dir))
