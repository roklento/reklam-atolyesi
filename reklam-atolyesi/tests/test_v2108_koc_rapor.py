"""2.10.8: koç ve rapor doğruluğu (dış bağımsız denetim B5–B6). Sentetik veri; ağ yok."""
from __future__ import annotations

import pytest

import coach as CO
from conftest import make_active_profile
from test_analytics import CTX, build_campaign
from admem.util import AdMemoryError


def _decision(store, pid, cid, cy, concept="A"):
    an = CO.analyze(store.decision_input_snapshot(pid, cid, cy)["path"])
    return next(d for d in an["decisions"] if d["concept"] == concept), an


def _partly_measured(store):
    pid, cid, cy = build_campaign(store)
    aid = store.q1("SELECT id FROM ads WHERE meta_ad_id='901'")["id"]
    store.ex("UPDATE metrics_daily SET results=NULL, purchases=NULL, spend=1000 WHERE ad_id=?", (aid,))
    store.ex("UPDATE metrics_daily SET results=12, purchases=12, spend=60 WHERE ad_id=? AND date='2026-03-02'", (aid,))
    return pid, cid, cy, aid


# ----------------------------------------------------------------------------- eksik ölçüm (B6)
def test_unmeasured_sales_give_no_close_or_scale(store):
    pid, cid, cy, _ = _partly_measured(store)
    d, an = _decision(store, pid, cid, cy)
    assert d["decision"] == "tut" and d["label"] == "yetersiz ölçüm" and d["gated"] == "measurement_coverage"
    assert "kanıt" not in d["label"]


def test_cost_uses_only_days_with_measured_results():
    rows = [{"spend": 1000.0, "results": None} for _ in range(6)] + [{"spend": 60.0, "results": 12}]
    c = CO.cost_measured(rows, 28, True)
    assert c["spend"] == 60 and c["results"] == 12 and c["coverage"] < 0.1 and not c["threshold_met"]
    full = CO.cost_measured([{"spend": 100.0, "results": 10} for _ in range(7)], 28, True)
    assert full["threshold_met"] and full["coverage"] == 1.0


def test_no_result_column_stays_below_threshold():
    c = CO.cost_measured([{"spend": 100.0, "results": None} for _ in range(7)], 28, True)
    assert not c["threshold_met"] and c["measured"] is False


# ----------------------------------------------------------------------------- sınır ve öneri (B6)
def test_exceeded_total_limit_blocks_scale_advice(store):
    pid, cid, cy, aid = _partly_measured(store)
    store.ex("UPDATE metrics_daily SET results=200, purchases=200 WHERE ad_id=? AND results IS NULL", (aid,))
    d, an = _decision(store, pid, cid, cy)
    assert any(a["kind"] == "total_exceeded" for a in an["limit_alerts"])
    assert d["decision"] == "tut" and d["gated"] == "budget_limit" and d.get("ads_manager") is None
    assert not any(x["decision"] == "büyüt" for x in an["decisions"])


def test_budget_gate_keeps_scale_when_limits_hold():
    dec = [{"concept": "A", "decision": "büyüt", "why": "iyi", "ads_manager": "artır"}]
    CO.budget_gate(dec, [], {})
    assert dec[0]["decision"] == "büyüt"
    CO.budget_gate(dec, [{"kind": "risk_limit", "creative_key": "k1"}], {"k1": "A"})
    assert dec[0]["decision"] == "tut" and dec[0]["gated"] == "budget_limit"


# ----------------------------------------------------------------------------- rapor toplamları (B5)
def test_unmeasured_revenue_gives_unknown_roas(store):
    pid, cid, cy = build_campaign(store)
    for g in store.metrics_query(pid, campaign_id=cid)["groups"]:
        assert g["revenue"] is None and g["roas"] is None


def test_roas_needs_revenue_on_most_spend(store):
    pid, cid, cy = build_campaign(store)
    store.ex("UPDATE metrics_daily SET revenue=500 WHERE date='2026-03-01'")
    g = store.metrics_query(pid, campaign_id=cid, level="campaign")["groups"][0]
    assert g["roas"] is None and g["roas_coverage"] < 0.8
    store.ex("UPDATE metrics_daily SET revenue=50")
    g = store.metrics_query(pid, campaign_id=cid, level="campaign")["groups"][0]
    assert g["roas"] is not None and g["roas_coverage"] == 1.0


# ----------------------------------------------------------------------------- CSV (B5)
def _csv(tmp_path, text, name="m.csv"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_csv_period_row_is_refused(store, tmp_path):
    pid = make_active_profile(store)["profile"]["id"]
    p = _csv(tmp_path, "Reporting starts,Reporting ends,Ad ID,Impressions,Amount spent\n2026-03-01,2026-03-31,77,90000,3100\n")
    with pytest.raises(AdMemoryError, match="Gün"):
        store.metrics_import_csv(pid, str(p), CTX)
    assert not store.q1("SELECT 1 FROM metrics_daily")


def test_csv_daily_with_end_column_still_works(store, tmp_path):
    pid = make_active_profile(store)["profile"]["id"]
    p = _csv(tmp_path, "Reporting starts,Reporting ends,Ad ID,Impressions,Amount spent\n2026-03-01,2026-03-01,77,900,31\n"
                       "2026-03-02,2026-03-02,77,800,29\n")
    assert store.metrics_import_csv(pid, str(p), CTX)["inserted"] == 2


def test_csv_currency_must_match_context(store, tmp_path):
    pid = make_active_profile(store)["profile"]["id"]
    p = _csv(tmp_path, "Day,Ad ID,Impressions,Amount spent (USD)\n2026-03-01,77,1000,100\n")
    with pytest.raises(AdMemoryError, match="USD"):
        store.metrics_import_csv(pid, str(p), {**CTX, "currency": "TRY"})
    p2 = _csv(tmp_path, "Day,Ad ID,Impressions,Amount spent (TRY)\n2026-03-01,77,1000,100\n", "t.csv")
    assert store.metrics_import_csv(pid, str(p2), CTX)["inserted"] == 1


def test_csv_breakdown_rows_are_refused_not_overwritten(store, tmp_path):
    pid = make_active_profile(store)["profile"]["id"]
    p = _csv(tmp_path, "Day,Ad ID,Impressions,Amount spent,Placement\n2026-03-01,77,1000,100,Feed\n2026-03-01,77,500,40,Stories\n")
    with pytest.raises(AdMemoryError, match="Placement"):
        store.metrics_import_csv(pid, str(p), CTX)
    assert not store.q1("SELECT 1 FROM metrics_daily")


def test_reimport_of_same_file_still_updates(store, tmp_path):
    pid = make_active_profile(store)["profile"]["id"]
    p = _csv(tmp_path, "Day,Ad ID,Impressions,Amount spent\n2026-03-01,77,1000,100\n")
    store.metrics_import_csv(pid, str(p), CTX)
    assert store.metrics_import_csv(pid, str(p), CTX)["updated"] == 1


def test_ingest_refuses_duplicate_day_in_one_call(store):
    pid = make_active_profile(store)["profile"]["id"]
    rows = [{"meta_ad_id": "77", "date": "2026-03-01", "impressions": 1000, "spend": 100},
            {"meta_ad_id": "77", "date": "2026-03-01", "impressions": 500, "spend": 40}]
    with pytest.raises(AdMemoryError, match="birden çok satır"):
        store.metrics_ingest(pid, rows, "meta_mcp", CTX)
