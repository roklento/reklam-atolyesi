"""2.5.0: admin ekibine anonim geri bildirim paketi (KURALLAR K15) — önizleme, açık onay, yerel dosya, kimlik ve serbest metin yok."""
from __future__ import annotations

import json

import pytest

from admem import feedback as FB
from admem.util import AdMemoryError
from conftest import make_active_profile

import draft_docs as DD

SECRET_WORDS = ["GizliMarka", "Zeta", "SırÜrün", "Omega", "ornek@posta.com", "0532 123 45 67", "act_ZZ"]


def seeded(store, data_dir):
    a = make_active_profile(store, name="GizliMarka Zeta", account="act_ZZ", product="SırÜrün")
    pid, prod = a["profile"]["id"], a["product"]["id"]
    r = store.campaign_create(pid, prod, "Kampanya Omega", result_type="purchase", budget_total=1234, budget_total_confirmed=True)
    cid, cyid = r["campaign"]["id"], r["cycle"]["id"]
    store.cycle_set(pid, cyid, adset_budget_daily=150)
    store.stage_start(pid, "S01", cid, cyid)
    d = DD.write_stage_doc(store, pid, "S01", cid, cyid, check=False)
    (store.campaign_dir(pid, cid) / "c1-brief.md").write_text(d["text"] + "\n{{eksik}}\n", encoding="utf-8")
    store.draft_check(pid, "S01", d["path"], cid, cyid)  # placeholder → kritik
    logs = data_dir / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "kullanim-hatasi-1.json").write_text(json.dumps({
        "time": "2026-03-02T08:00:00+00:00", "tool": "mcp__plugin_reklam-atolyesi_ad-memory__stage_complete",
        "error": f"GizliMarka Zeta için {data_dir}/profiles/x/c1-brief.md bulunamadı; ornek@posta.com 0532 123 45 67"}), encoding="utf-8")
    (logs / "kullanim-hatasi-2.json").write_text(json.dumps({
        "time": "2026-03-02T08:30:00+00:00", "tool": "mcp__claude_ai_Gmail__send", "error": "timeout"}), encoding="utf-8")
    return pid, cid, cyid


def test_export_requires_approval_and_contains_no_identity(store, data_dir, clock):
    pid, cid, cyid = seeded(store, data_dir)
    prev = store.feedback_preview(30)
    rep = prev["report"]
    FB.assert_anonymous(rep)
    with pytest.raises(AdMemoryError, match="açık onay"):
        store.feedback_export("  ")
    out = store.feedback_export("evet, paketi hazırla", 30)
    text = open(out["path"], encoding="utf-8").read()
    assert "logs" in out["path"] and "geri-bildirim" in out["path"]
    for w in SECRET_WORDS + [str(data_dir), "profiles/"]:
        assert w not in text, w
    data = json.loads(text)
    assert data["schema"] == FB.SCHEMA and data["profiles"]["active"] == 1
    assert data["errors"]["count"] == 2
    assert data["errors"]["by_tool"] == {"stage_complete": 1, "other_mcp": 1}  # kullanıcının başka hizmeti adıyla girmez
    assert data["errors"]["by_kind"]["not_found"] == 1 and data["errors"]["by_kind"]["timeout"] == 1
    assert data["draft_checks"]["issue_codes"].get("S01:placeholder:critical") == 1
    assert data["campaigns"]["result_type"] == {"purchase": 1}
    # yazma günlüğe kullanıcı onayıyla kaydedildi
    assert store.q1("SELECT COUNT(*) AS n FROM journal WHERE type='feedback_export'")["n"] == 1


def test_stuck_stage_and_synthetic_profiles_excluded(store, data_dir, clock):
    pid, cid, cyid = seeded(store, data_dir)
    syn = store.profile_create("Sentetik", synthetic=True)
    store.stage_start(syn["id"], "S00a")
    clock.advance(days=10)
    rep = store.feedback_preview(30)["report"]
    stuck = {(s["stage"], s["status"]): s for s in rep["stuck"]}
    assert stuck[("S01", "running")]["open_runs"] == 1 and stuck[("S01", "running")]["oldest"] == "7-30"
    assert ("S00a", "running") not in stuck  # sentetik profil sayılmaz
    assert rep["profiles"] == {"active": 1, "onboarding": 0, "archived": 0}


def test_anonymity_guard_and_buckets():
    with pytest.raises(ValueError):
        FB.assert_anonymous({"stages": {"S01": "Marka Zeta hata verdi"}})
    with pytest.raises(ValueError):
        FB.assert_anonymous({"Zeta Marka": 1})
    FB.assert_anonymous({"a": [1, 2.5, None, True, "S01:placeholder:critical"]})
    assert FB.tool_bucket("mcp__plugin_reklam-atolyesi_meta-ads__ads_get_ad_entities") == "ads_get_ad_entities"
    assert FB.tool_bucket("Bash") == "Bash" and FB.tool_bucket("mcp__x__y") == "other_mcp"
    assert FB.days_bucket(2) == "0-3" and FB.days_bucket(40) == "30+"


def test_period_bounds(store):
    with pytest.raises(AdMemoryError):
        store.feedback_preview(0)
    with pytest.raises(AdMemoryError):
        store.feedback_preview(400)
