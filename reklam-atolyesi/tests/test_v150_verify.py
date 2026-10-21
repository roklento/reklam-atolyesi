"""1.5.0 ikinci doğrulama turunun regresyon testleri."""
from __future__ import annotations

import datetime as dt
import math

import coach as CO
from admem.store import Store
from test_analytics import build_campaign


def test_lead_costs_use_only_covered_days_and_gate_on_coverage(store):
    pid, cid, cyid = build_campaign(store)
    store.ex("UPDATE campaigns SET result_type='lead', lead_method='instant_form' WHERE id=?", (cid,))
    store.ex("UPDATE metrics_daily SET results=3")
    store.lead_outcome_set(pid, cid, "2026-03-02", "2026-03-04", 30, won=3)  # pencerenin 3/7 günü
    an = CO.analyze(store.decision_input_snapshot(pid, cid, cyid, "coach_report")["path"])
    ld = an["lead"]
    assert ld["outcome_coverage"] == round(3 / 7, 3) and ld["covered_spend"] < ld["spend"] and ld["coverage_note"]
    assert ld["cost_per_won"] == round(ld["covered_spend"] / 3, 2)
    assert ld["meta_leads"] > ld.get("meta_vs_crm", 0) and abs(ld["meta_vs_crm"] - 30 / (3 * 3 * 3)) < 0.01  # yalnızca kapsanan günlerin adayı
    assert not any(d["decision"] == "büyüt" for d in an["decisions"])


def test_ab_non_cell_concepts_get_no_verdict(store):
    pid, cid, cyid = build_campaign(store)
    store.cycle_set(pid, cyid, structure_detected="ab_test", meta_test_id="61",
                    structure_evidence_json={"study_read": {"cells": ["A", "B"], "variable": "creative"}})
    an = CO.analyze(store.decision_input_snapshot(pid, cid, cyid, "coach_report")["path"])
    c = next(d for d in an["decisions"] if d["concept"] == "C")
    assert c["decision"] == "tut" and c["label"] == "çalışma dışı"


def test_ab_check_and_plan_bad_inputs():
    import budget as BU
    assert not BU.ab_check({"cells": 2, "daily_total": 900, "expected_cpr": 10, "days": "abc"})["eligible"]
    r = BU.ab_check({"cells": 2, "daily_total": 900, "expected_cpr": 10, "remaining_budget": "x"})
    assert any("kalan bütçe" in w for w in r["warnings"])
    assert not BU.ab_check({"cells": 2, "daily_total": 900, "expected_cpr": math.inf})["eligible"]
    assert not BU.ab_check({"cells": 2, "daily_total": math.nan, "expected_cpr": 10})["eligible"]
    out = BU.plan({"cycle_no": 2, "adset_daily": 1000, "cpm": 50, "ab_test": True})
    assert "ab_test" not in out and any("ab_test girdisi" in w for w in out["warnings"])


def test_profile_and_candidates_robust_numbers():
    import candidates as OC
    import profile_check as PC
    now = dt.datetime(2026, 10, 21, tzinfo=dt.timezone.utc)
    ms = int(dt.datetime(2026, 10, 20, tzinfo=dt.timezone.utc).timestamp() * 1000)
    r = PC.check([{"id": "1", "timestamp": ms, "media_type": "IMAGE", "like_count": "n/a"}], None, now=now)
    assert r["posts_read"] == 1 and r["last_post_days"] == 1 and r["median_engagement_recent"] == 0
    a = [{"id": 1, "kind": "footage", "path": "x.mp4", "score_json": {"overall": 0.9}, "best_ranges_json": [{"in_s": 0, "out_s": "x"}]}]
    assert OC.build(a)["skipped"]["short"] == 1


def test_non_positive_contribution_explains_lead():
    eco = Store.economics({"economics_json": {"contribution": -5, "lead_close_rate": 0.2}})
    assert eco["status"] == "non_positive" and eco["cpl_status"] == "unknown" and "Katkı ≤ 0" in eco["cpl_note"]
