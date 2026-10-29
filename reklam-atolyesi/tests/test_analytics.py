"""Koçluk sentetik gerçeklik testleri (spec 6.15) ve S02 bütçe hesabı (6.3, 4.4)."""
from __future__ import annotations

import json

import numpy as np
import pytest
from scipy import stats

import bayes as B
import budget as BU
import calibration as CAL
import coach as CO
import report as RP
from conftest import make_active_profile

CTX = {"account_id": "act_A", "timezone": "Europe/Istanbul", "currency": "TRY", "result_definition": "purchase",
       "metric_definitions": {}, "attribution_window": "7d_click", "action_report_time": "impression"}


# --- S02 bütçe ---------------------------------------------------------------
def test_budget_7_to_14_and_stop():
    base = {"cycle_no": 1, "adset_daily": 100, "cpm": 50, "decision_metric": "hook", "budget_total": None, "launch_at": "2026-03-10"}
    r7 = BU.plan(base)  # kreatif başına 50; 7 gün 700 → 14 reklam sığar ama ilk turda da araç sınırı (7) uygulanır (1.4.7, 1.5.3)
    assert r7["test_days"] == 7 and r7["allowed_test_ads"] == 7 and r7["cycle_days"] == 14
    assert any("eşit dağıtmaz" in w for w in r7["warnings"])
    r14 = BU.plan({**base, "adset_daily": 12, "cpm": 50})  # 7 gün 84 → 1 reklam; 14 gün 168 → 3 reklam
    assert r14["test_days"] == 14 and r14["allowed_test_ads"] == 3 and r14["cycle_days"] == 21
    stop = BU.plan({**base, "adset_daily": 5, "cpm": 50})  # 14 gün 70 → 1 reklam
    assert stop["production_blocked"] and stop["required_daily_adset_budget"] == pytest.approx(2 * 50 / 14, rel=1e-3)
    later = BU.plan({**base, "cycle_no": 2, "exploration_share": 0.2, "adset_daily": 300})
    assert later["structure"] == "creative_test" and later["allowed_test_ads"] <= 7


def test_total_budget_example_stops():
    r = BU.plan({"cycle_no": 1, "adset_daily": 100, "cpm": 10, "decision_metric": "hook", "budget_total": 700, "spend_to_date": 0,
                 "data_cutoff": "2026-03-10", "launch_at": "2026-03-10"})
    assert r["allowed_test_ads"] >= 2  # test matrisi sığıyor
    assert r["spend_projection"]["projected_additional"] == pytest.approx(1400)
    assert r["fits_total_budget"] is False


def test_unverified_spend_blocks_fit():
    r = BU.plan({"cycle_no": 1, "adset_daily": 100, "cpm": 10, "budget_total": 5000, "spend_to_date": None, "launch_at": "2026-03-10"})
    assert r["fits_total_budget"] is False


def test_risk_limit_below_per_creative():
    r = BU.plan({"cycle_no": 1, "adset_daily": 100, "cpm": 50, "risk_per_ad": 10, "launch_at": "2026-03-10"})
    assert r["production_blocked"]


def test_calendar_rule():
    r = BU.plan({"cycle_no": 1, "adset_daily": 100, "cpm": 10, "launch_at": "2026-03-10"})
    cal = r["calendar"]
    assert cal["test_end"] == "2026-03-17" and cal["plan_day"] == "2026-03-20" and cal["next_launch"] == "2026-03-24"


# --- Bayes ----------------------------------------------------------------------
def test_beta_matches_scipy_reference():
    p = B.rate_posterior("hook_rate", 300, 1200, (3.0, 9.0))
    a, b = 3 + 300, 9 + 900
    assert p.a == a and p.b == b
    lo, hi = stats.beta.ppf([0.05, 0.95], a, b)
    assert p.lo == pytest.approx(lo) and p.hi == pytest.approx(hi) and p.threshold_met


def test_threshold_labels_and_invalid_rate():
    assert B.rate_posterior("ctr_link", 20, 2000).label == "yön/yetersiz veri"
    assert B.rate_posterior("hook_rate", 50, 40) is None  # pay > payda model dışı


def test_gamma_cost_reference():
    c = B.cost_posterior(spend=600, results=12, target=40, verified_target=True)
    shape, rate = 0.5 + 12, 0.5 + 15
    assert c["gamma_shape"] == shape and c["gamma_rate"] == rate
    assert c["p_below_target"] == pytest.approx(stats.gamma.sf(1.0, shape, scale=1 / rate), abs=0.01)
    none = B.cost_posterior(600, 12, None, False)
    assert "p_below_target" not in none


def test_deterministic_seed():
    a = {"A": B.rate_posterior("hook_rate", 300, 1000), "B": B.rate_posterior("hook_rate", 280, 1000)}
    assert B.superiority(a) == B.superiority(a)


def test_coverage_simulation_reported_not_asserted_nominal():
    r = B.coverage_simulation(0.2, 500, reps=300)
    assert 0 < r["realized_coverage"] <= 1 and r["nominal"] == 0.9


def test_calibration_counts_only_below_30():
    pairs = [{"p": 0.8, "won": True, "chain": f"c{i}"} for i in range(12)]
    r = CAL.calibrate(pairs)
    assert r["resolved"] == 12 and "bins" not in r
    pairs += [{"p": 0.9, "won": True, "chain": "c0"}]  # aynı zincirin yeni sürümü yeni tahmin sayılmaz
    assert CAL.calibrate(pairs)["resolved"] == 12


# --- koçluk boru hattı (bilinen gerçeklik) --------------------------------------------
def build_campaign(store, impressions=4000, starved=True, test_start="2026-03-02T00:00:00+03:00", test_end="2026-03-09T00:00:00+03:00"):
    a = make_active_profile(store)
    pid = a["profile"]["id"]
    c = store.campaign_create(pid, a["product"]["id"], "K", result_type="purchase", budget_total=1000)
    cid, cyid = c["campaign"]["id"], c["cycle"]["id"]
    store.cycle_set(pid, cyid, test_start=test_start, test_end=test_end, structure_detected="bootstrap", adset_budget_daily=100,
                    structure_evidence_json={"source": "test"},
                    risk_limits_json={"per_ad": {"amount": 50, "currency": "TRY", "scope": "ad_launch_to_stop", "approved_at": "x", "note": "n"},
                                      "mapping": {"MRK_K_C_video_15_h1_novo_real_c1_r1": {"meta_ad_ids": ["903"]}}})
    truth = {"A": (0.30, 0.020), "B": (0.20, 0.010), "C": (0.25, 0.015)}
    rng = np.random.default_rng(1729)
    rows = []
    for i, (k, (hook, ctr)) in enumerate(truth.items()):
        key = f"MRK_K_{k}_video_15_h1_novo_real_c1_r1"
        f = store.campaign_dir(pid, cid) / "out" / f"{key}_916.mp4"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(bytes([i]) * 32)
        store.ex("""INSERT INTO creatives(campaign_id,cycle_id,creative_key,file_path,file_name,sha256,media_type,source_variant,card_index,delivery_role,
                    duration_s,format,created_at) VALUES(?,?,?,?,?,?, 'video','real',0,'test',15,'9x16','x')""", (cid, cyid, key, str(f), f.name, f"h{i}"))
        store.ex("INSERT INTO concepts(campaign_id,cycle_id,code,name,source,created_at,updated_at) VALUES(?,?,?,?, 'general','x','x')", (cid, cyid, k, k))
        store.ex("UPDATE creatives SET concept_id=(SELECT id FROM concepts WHERE cycle_id=? AND code=?) WHERE creative_key=?", (cyid, k, key))
        for d in range(1, 11):
            imp = impressions if not (starved and k == "C") else 40
            rows.append({"meta_ad_id": f"90{i + 1}", "ad_name": key, "date": f"2026-03-{d:02d}", "impressions": imp,
                         "video_3s": int(rng.binomial(imp, hook)), "thruplay": 0, "link_clicks": int(rng.binomial(imp, ctr)),
                         "spend": imp * 0.05 if k != "C" else imp * 0.05 + (40 if d == 1 else 0), "results": 0, "purchases": 0,
                         "p25": int(imp * hook * (0.8 if k != "B" else 0.4)), "p50": int(imp * hook * 0.6), "p75": int(imp * hook * 0.45),
                         "p95": int(imp * hook * 0.35), "p100": int(imp * hook * 0.3)})
    store.metrics_ingest(pid, rows, "synthetic", CTX)
    return pid, cid, cyid


def test_coach_known_truth(store, tmp_path):
    pid, cid, cyid = build_campaign(store)
    snap = store.decision_input_snapshot(pid, cid, cyid, "coach_report")
    an = CO.analyze(snap["path"])
    assert an["window"]["full_days"] == [f"2026-03-0{d}" for d in range(2, 9)]
    assert an["superiority_hook"]["A"]["p_best"] > 0.9
    dec = {d["concept"]: d for d in an["decisions"]}
    assert dec["C"]["label"] == "yetersiz veri" and dec["C"]["decision"] == "tut"  # aç kalan kaybeden sayılmaz
    assert not any(d["decision"] == "kapat" for d in an["decisions"])  # sonuç yok → kapat yok
    assert all("Meta'nın dağıtımı altında" in d["label"] or d["label"] == "yetersiz veri" for d in an["decisions"])
    assert "hook_x_ctr" not in json.dumps(an)  # huni çarpımı yok
    assert any(a["kind"] == "risk_limit" and a["results"] == 0 for a in an["limit_alerts"])  # sıfır sonuçta da sınır uyarısı
    # aynı kopya → aynı sonuç (deterministik)
    assert CO.analyze(snap["path"])["superiority_hook"] == an["superiority_hook"]
    snap2 = store.decision_input_snapshot(pid, cid, cyid, "coach_report")
    assert snap2["reused"] and snap2["sha256"] == snap["sha256"]


def test_boundary_days_excluded_in_coach(store):
    pid, cid, cyid = build_campaign(store, test_start="2026-03-02T18:00:00+03:00", test_end="2026-03-09T18:00:00+03:00")
    an = CO.analyze(store.decision_input_snapshot(pid, cid, cyid)["path"])
    assert len(an["window"]["full_days"]) == 6 and an["window"]["excluded_boundary_days"] == ["2026-03-02", "2026-03-09"]


def test_snapshot_immutable_after_provider_revision(store):
    pid, cid, cyid = build_campaign(store)
    s1 = store.decision_input_snapshot(pid, cid, cyid)
    store.ex("UPDATE metrics_daily SET spend=spend+1 WHERE date='2026-03-03'")
    s2 = store.decision_input_snapshot(pid, cid, cyid)
    assert s2["version"] == s1["version"] + 1 and s2["sha256"] != s1["sha256"]
    from admem.util import sha256_file
    assert sha256_file(s1["path"]) == s1["sha256"]  # eski kopya değişmez


def test_report_rejects_causal_language(store, tmp_path):
    pid, cid, cyid = build_campaign(store)
    snap = store.decision_input_snapshot(pid, cid, cyid, extra={"competitor_changes": ["Rakip A test başladıktan 3 gün sonra indirimli reklam yayına aldı"]})
    an = CO.analyze(snap["path"])
    md = RP.build(an, json.load(open(snap["path"], encoding="utf-8")), {}, None, None, None)
    for sec in RP.SECTIONS:
        assert f"## {sec}" in md
    an["competitive_context"]["statements"] = ["CPM rakip indirimi nedeniyle arttı"]
    with pytest.raises(SystemExit):
        RP.build(an, json.load(open(snap["path"], encoding="utf-8")), {}, None, None, None)


def test_action_items_guardrails(store):
    pid, cid, cyid = build_campaign(store)
    snap = store.decision_input_snapshot(pid, cid, cyid)
    ref = {"path": snap["path"], "sha256": snap["sha256"]}
    from admem.util import AdMemoryError
    with pytest.raises(AdMemoryError):
        store.action_items_set(pid, cid, [{"action": "bütçeyi artır", "before": {"daily_budget": 100}, "after": {"daily_budget": 150},
                                           "evidence": {"input_snapshot": ref}}])
    with pytest.raises(AdMemoryError):
        store.action_items_set(pid, cid, [{"action": "kapat", "kind": "pause", "reason_kind": "performance", "evidence": {"input_snapshot": ref}}])
    r = store.action_items_set(pid, cid, [{"action": "903 reklamını durdur", "reason_kind": "limit", "dedupe_key": "limit:903",
                                           "evidence": {"input_snapshot": ref}}], cycle_id=cyid)
    r2 = store.action_items_set(pid, cid, [{"action": "903 reklamını durdur", "reason_kind": "limit", "dedupe_key": "limit:903",
                                            "evidence": {"input_snapshot": ref}}], cycle_id=cyid)
    assert r["created"] and r2["refreshed"] == r["created"]  # açık madde kopyalanmaz
    with pytest.raises(AdMemoryError):
        store.action_item_set_status(pid, r["created"][0], "applied")
    store.action_item_set_status(pid, r["created"][0], "approved", approval_text="durduracağım")
    v = store.action_items_verify(pid, cid, [{"item_id": r["created"][0]}])
    assert v["results"][0]["status"] == "approved"  # kanıt yok: doğrulanmış sayılmaz


def test_predictions_versions_not_independent(store):
    pid, cid, cyid = build_campaign(store)
    s1 = store.decision_input_snapshot(pid, cid, cyid)
    p1 = store.prediction_log(pid, cid, cyid, "concept:A", "hook_rate", {"path": s1["path"], "sha256": s1["sha256"]}, 0.9)
    store.ex("UPDATE metrics_daily SET spend=spend+2")
    s2 = store.decision_input_snapshot(pid, cid, cyid)
    p2 = store.prediction_log(pid, cid, cyid, "concept:A", "hook_rate", {"path": s2["path"], "sha256": s2["sha256"]}, 0.92)
    assert p2["supersedes_id"] == p1["id"]
    store.prediction_resolve(pid, p2["id"], {"won": True}, {"path": s2["path"], "sha256": s2["sha256"]})
    assert store.calibration_get(pid)["resolved"] == 1


def test_playbook_requires_independent_validation(store):
    pid, cid, cyid = build_campaign(store)
    from admem.util import AdMemoryError
    store.ex("UPDATE cycles SET test_start='2026-04-01T00:00:00Z' WHERE id=?", (cyid,))  # ön kayıt test başlamadan
    h = store.hypothesis_add(pid, "Örnek hipotez", "hook_rate", cid, cyid, is_primary=True,
                             pre_registration={"arm_a": "A", "arm_b": "B", "metric": "hook_rate", "direction": "A>B", "comparison_ids": [1, 2]})
    ev = {"hypothesis_id": h["id"], "discovery_cycle_id": cyid, "validation_cycle_id": cyid, "discovery_same_direction": True,
          "p_superiority_validation_only": 0.97, "sufficient_data": True}
    with pytest.raises(AdMemoryError):
        store.playbook_propose(pid, "kural", ev)  # aynı tur: bağımsız değil
    ev["discovery_cycle_id"] = cyid - 1 if cyid > 1 else 999
    with pytest.raises(AdMemoryError):
        store.playbook_propose(pid, "kural", ev)  # üst huni: alt huni teyidi yok
    ev["lower_funnel"] = {"metric": "ctr_link", "same_direction": True, "sufficient": True, "preselected": True}
    r = store.playbook_propose(pid, "kural", ev)
    assert r["status"] == "proposed"
    store.playbook_activate(pid, r["id"], "onaylıyorum")
    store.playbook_revalidate(pid, r["id"], "contradicted")
    assert store.playbook_revalidate(pid, r["id"], "contradicted")["status"] == "retired"
