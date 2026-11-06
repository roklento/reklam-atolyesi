"""2.10.11: onay ve silme (dış bağımsız denetim 2.10.10 B1, B2, B4, B5, B6). Sentetik veri; ağ ve ücretli çağrı yok."""
from __future__ import annotations

import inspect
import json
import sys

import pytest

from conftest import ROOT
from test_generation import setup, P, LIC
from test_v2108_koc_rapor import CTX
from admem import approval as AP
from admem.util import AdMemoryError, now_iso

sys.path.insert(0, str(ROOT / "hooks"))
sys.path.insert(0, str(ROOT / "servers" / "ad_memory"))
import navigator  # noqa: E402


def _say(store, sid, text, mid, full=None):
    store._session_update(sid, lambda s: navigator.record_prompt(s, "UserPromptSubmit", full if full is not None else text, "", mid))


# ----------------------------------------------------------------------------- B1: oturum ve marka
def test_mcp_approval_tools_refuse_empty_session():
    import server
    from mcp.server.fastmcp.exceptions import ToolError
    with pytest.raises(ToolError, match="session_id gerekli"):
        server.approval_call("", lambda s: s)
    with pytest.raises(ToolError, match="session_id gerekli"):
        server.approval_call("   ", lambda s: s)
    for name in ("gate_approve", "generation_approve", "action_item_set_status", "playbook_activate", "feedback_export", "memory_forget"):
        src = inspect.getsource(getattr(server, name))
        assert "approval_call(session_id" in src, name


def test_yes_written_in_other_brand_session_does_not_approve(store, clock):
    p, c, cy = setup(store)
    other = store.profile_create("Başka Marka")["id"]
    store.session_bind("oturum-b-01", other)
    g = store.generation_log(p, c, cy, "creative_generate_speech", P, 120)
    clock.advance(minutes=1)
    _say(store, "oturum-b-01", "evet", "m1")
    with pytest.raises(AdMemoryError, match="başka bir markada"):
        store.generation_approve(p, g["id"], 120, 4, "", LIC, session_id="oturum-b-01")
    assert not store.generation_reserve(c, g["call_hash"], "x")["ok"]
    # aynı kullanıcı doğru markaya geçip onaylarsa geçer
    store.session_bind("oturum-b-01", p, c)
    clock.advance(minutes=1)
    _say(store, "oturum-b-01", "evet", "m2")
    store.generation_approve(p, g["id"], 120, 4, "", LIC, session_id="oturum-b-01")
    assert store.generation_reserve(c, g["call_hash"], "x")["ok"]


def test_prompt_records_brand_at_time_of_writing():
    s = {"profile_id": 7}
    navigator.record_prompt(s, "UserPromptSubmit", "evet", "", "a1")
    assert s["user_prompts"][-1]["profile_id"] == 7 and s["user_prompts"][-1]["truncated"] is False


# ----------------------------------------------------------------------------- B2: biçim
@pytest.mark.parametrize("text", ["/onaylama", "/onayla 10 krediyi aşma", "/reklam-atolyesi:onayla ama müziği değiştir",
                                  "/onayla 100 kredi", "evet 👎", "evet 👍", "evet нет", "evet?", "olur mu?", "evet" + " ve" * 120])
def test_not_an_approval(text):
    assert not AP.check(text, 120)[0]


@pytest.mark.parametrize("text", ["/onayla", "/reklam-atolyesi:onayla", "/onayla 120 kredi", "Evet!", "tamam, devam", "evet (120 kredi)"])
def test_still_an_approval(text):
    assert AP.check(text, 120)[0]


def test_foreign_yes_gets_plain_guidance():
    ok, why = AP.check("yes")
    assert not ok and "evet yazman yeterli" in why


def test_truncated_message_is_not_an_approval(store, clock):
    p, c, cy = setup(store)
    store.session_bind("oturum-uzun-1", p, c)
    g = store.generation_log(p, c, cy, "creative_generate_speech", P, 120)
    clock.advance(minutes=1)
    _say(store, "oturum-uzun-1", "", "u1", full="evet" + " " * 500 + "ama harcama")
    with pytest.raises(AdMemoryError, match="kısaltılarak"):
        store.generation_approve(p, g["id"], 120, 4, "", LIC, session_id="oturum-uzun-1")


# ----------------------------------------------------------------------------- B4: ret silmez
@pytest.mark.parametrize("text", ["hayır, silme", "silme", "unutma", "evet ama yarın"])
def test_refusal_does_not_forget(store, text):
    p, c, cy = setup(store)
    it = store.memory_add("preference", "note", "Sentetik tercih 4417", "user", profile_id=p, force_new=True)["created"]
    with pytest.raises(AdMemoryError, match="onay sayılmaz"):
        store.memory_forget(it["id"], text, p)
    assert store.q1("SELECT id FROM memory_items WHERE id=?", (it["id"],))


def test_forget_takes_users_own_message(store, clock):
    p, c, cy = setup(store)
    store.session_bind("oturum-sil-01", p)
    it = store.memory_add("preference", "note", "Sentetik tercih 5528", "user", profile_id=p, force_new=True)["created"]
    clock.advance(minutes=1)
    _say(store, "oturum-sil-01", "hayır, silme", "s1")
    with pytest.raises(AdMemoryError, match="onay sayılmaz"):
        store.memory_forget(it["id"], "evet", p, session_id="oturum-sil-01")  # model "evet" yazsa da kullanıcının cevabı esas
    _say(store, "oturum-sil-01", "evet, sil", "s2")
    store.memory_forget(it["id"], "", p, session_id="oturum-sil-01")
    assert store.q1("SELECT id FROM memory_items WHERE id=?", (it["id"],)) is None


# ----------------------------------------------------------------------------- B5: kalıntı ve kaldığı yerden sürme
def test_forget_scrubs_journal_detail_and_session_copies(store, clock):
    p, c, cy = setup(store)
    secret = "Sentetik özel tercih 6639"
    it = store.memory_add("preference", "note", secret, "user", profile_id=p, force_new=True)["created"]
    j = store.journal_log("Görüşme kaydedildi", p, detail={"metin": secret})
    _say(store, "oturum-yerel-1", secret, "k1")
    out = store.memory_forget(it["id"], "unut", p)
    assert secret not in json.dumps(store.q1("SELECT detail_json FROM journal WHERE id=?", (j["id"],)), ensure_ascii=False)
    assert secret not in store._session_path("oturum-yerel-1").read_text(encoding="utf-8")
    assert out["session_messages_scrubbed"] == 1 and out["local_copies_complete"]


def test_partial_forget_resumes_where_it_left(store, data_dir):
    p, c, cy = setup(store)
    it = store.memory_add("preference", "note", "Sentetik iki numara", "user", profile_id=p, force_new=True)["created"]
    bad = data_dir / "backups" / "guncelleme-denetim.sqlite"
    bad.parent.mkdir(exist_ok=True)
    bad.write_bytes(b"broken" * 50)
    out = store.memory_forget(it["id"], "unut", p)
    assert out["local_copies_complete"] is False and str(bad) in out["backups_unreadable"]
    pend = store.q1("SELECT value FROM settings WHERE key='forget_pending_json'")["value"]
    assert "Sentetik iki numara" not in pend  # kalan yerler kaydedilir, içerik saklanmaz
    again = store.memory_forget(it["id"], "unut", p)  # hâlâ bozuk: yine tamamlanmadı, hata değil
    assert again["resumed"] and again["local_copies_complete"] is False
    bad.unlink()
    done = store.memory_forget(it["id"], "unut", p)
    assert done["resumed"] and done["local_copies_complete"]
    with pytest.raises(AdMemoryError, match="kapsamda değil"):
        store.memory_forget(it["id"], "unut", p)


def test_resume_is_profile_isolated(store, data_dir):
    p, c, cy = setup(store)
    other = store.profile_create("Başka Marka")["id"]
    it = store.memory_add("preference", "note", "Sentetik üç numara", "user", profile_id=p, force_new=True)["created"]
    bad = data_dir / "backups" / "guncelleme-denetim.sqlite"
    bad.parent.mkdir(exist_ok=True)
    bad.write_bytes(b"broken" * 50)
    store.memory_forget(it["id"], "unut", p)
    with pytest.raises(AdMemoryError, match="kapsamda değil"):
        store.memory_forget(it["id"], "unut", other)


def test_forget_backup_scan_works_with_hash_in_path(tmp_path, clock):
    from admem.store import Store
    d = tmp_path / "Ajans #2 ğüş"
    d.mkdir()
    s = Store(d / "db" / "ad-memory.sqlite", d)
    try:
        p, c, cy = setup(s)
        it = s.memory_add("preference", "note", "Sentetik dört numara", "user", profile_id=p, force_new=True)["created"]
        s.backup(reason="test")
        out = s.memory_forget(it["id"], "unut", p)
        assert out["local_copies_complete"] and out["backups_removed"]
    finally:
        s.close()


# ----------------------------------------------------------------------------- B6: başka markanın dosyası
def test_csv_from_other_brand_folder_is_refused(store, data_dir):
    p, c, cy = setup(store)
    other = store.profile_create("Başka Marka")["id"]
    f = store.profile_dir(other) / "reports" / "meta.csv"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("Day,Ad ID,Impressions,Amount spent\n2026-03-01,77,900,31\n", encoding="utf-8")
    with pytest.raises(AdMemoryError, match="başka bir markanın klasöründe"):
        store.metrics_import_csv(p, str(f), CTX)
    assert not store.metrics_daily_rows(p)["rows"]


def test_csv_from_own_or_neutral_folder_is_accepted(store, data_dir, tmp_path):
    p, c, cy = setup(store)
    own = store.profile_dir(p) / "reports" / "meta.csv"
    own.parent.mkdir(parents=True, exist_ok=True)
    own.write_text("Day,Ad ID,Impressions,Amount spent\n2026-03-01,77,900,31\n", encoding="utf-8")
    assert store.metrics_import_csv(p, str(own), CTX)["inserted"] >= 1
    neutral = tmp_path / "İndirilenler" / "meta2.csv"
    neutral.parent.mkdir()
    neutral.write_text("Day,Ad ID,Impressions,Amount spent\n2026-03-02,78,800,30\n", encoding="utf-8")
    assert store.metrics_import_csv(p, str(neutral), CTX)["inserted"] >= 1
