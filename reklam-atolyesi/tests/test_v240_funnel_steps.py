"""2.4.0: tıklamadan sonra adım adım teşhis — ortak adımlar, okunamayan olay, iç içe olmayan sayım, geçmişe göre darboğaz, rapor ve
geçmişten adım önselleri."""
from __future__ import annotations

import coach as CO
import report as RP
from conftest import make_active_profile
from test_analytics import build_campaign
from test_metrics import CTX


def row(**kw):
    r = {"link_clicks": 1000, "landing_page_views": 800, "view_content": 600, "add_to_cart": 120, "initiate_checkout": 60, "purchases": 30}
    r.update(kw)
    return r


def test_steps_divide_by_previous_step():
    fs = CO.funnel_steps([row()])
    s = {x["step"]: x for x in fs["steps"]}
    assert [x["step"] for x in fs["steps"]] == ["step_landing", "step_view", "step_cart", "step_checkout", "step_purchase"]
    assert s["step_landing"]["rate"] == 0.8 and s["step_cart"]["rate"] == 0.2 and s["step_purchase"]["rate"] == 0.5
    assert all(x["status"] == "olculdu" and x["canonical"] for x in fs["steps"])
    assert fs["bottleneck"] is None


def test_unread_event_is_not_zero_and_next_step_falls_back():
    fs = CO.funnel_steps([row(view_content=None, initiate_checkout=None)])
    s = {x["step"]: x for x in fs["steps"]}
    assert s["step_view"]["status"] == "okunamadi" and "rate" not in s["step_view"]
    # sepete ekleme, okunamayan ürün görme yerine sayfaya ulaşmaya bölünür ve geçmişle kıyaslanmaz
    assert s["step_cart"]["denominator"] == "landing_page_views" and not s["step_cart"]["canonical"]
    assert s["step_purchase"]["denominator"] == "add_to_cart" and s["step_purchase"]["rate"] == 0.25


def test_all_unread_says_meta_cannot_see_after_click():
    r = {"link_clicks": 500}
    fs = CO.funnel_steps([r])
    assert fs["all_unread"] and "pazaryeri" in fs["msg"]
    assert CO.funnel_steps([{"link_clicks": 0}]) is None


def test_non_nested_counts_are_not_rated():
    fs = CO.funnel_steps([row(initiate_checkout=10, purchases=30)])
    p = {x["step"]: x for x in fs["steps"]}["step_purchase"]
    assert p["status"] == "ic_ice_degil" and "rate" not in p


def test_small_denominator_is_insufficient():
    fs = CO.funnel_steps([row(link_clicks=40, landing_page_views=30, view_content=20, add_to_cart=5, initiate_checkout=2, purchases=1)])
    s = {x["step"]: x for x in fs["steps"]}
    assert s["step_landing"]["status"] == "olculdu" and s["step_cart"]["status"] == "veri_yetersiz"


def test_bottleneck_needs_history_and_picks_worst():
    fs = CO.funnel_steps([row()])
    CO.mark_bottleneck(fs, {})
    assert fs["bottleneck"] is None and "geçmişi olmadığından" in fs["msg"]
    fs = CO.funnel_steps([row()])
    # geçmişte sepete ekleme %40, ödemeyi tamamlama %55: bu tur sepet %20 (belirgin düşük), tamamlama %50 (aralık geçmişi kapsıyor)
    CO.mark_bottleneck(fs, {"step_cart": (12, 18), "step_purchase": (16.5, 13.5), "step_landing": (24, 6)})
    s = {x["step"]: x for x in fs["steps"]}
    assert fs["bottleneck"] == "step_cart" and s["step_cart"]["weak"] and not s["step_purchase"].get("weak")
    assert "Sepete ekleme" in fs["msg"] and "fiyat" in fs["msg"]


def test_uniform_prior_is_not_history():
    snap = {"priors": {"priors": [{"metric": "step_cart", "a": 1, "b": 1, "source": "uniform"},
                                  {"metric": "step_view", "a": 6, "b": 4, "source": "history"}]}}
    assert CO.history_priors(snap) == {"step_view": (6.0, 4.0)}


def test_analyze_and_report_show_steps(store):
    pid, cid, cyid = build_campaign(store)
    snap = store.decision_input_snapshot(pid, cid, cyid)
    an = CO.analyze(snap["path"])
    assert "steps" in an["funnel_diagnosis"]
    import json
    md = RP.build(an, json.load(open(snap["path"], encoding="utf-8")), {}, None, None, None)
    if an["funnel_diagnosis"]["steps"]:
        assert "Tıklamadan sonra adım adım" in md


def test_priors_from_history_has_step_metrics(store):
    pid = make_active_profile(store)["profile"]["id"]
    rr = [{"meta_ad_id": ad, "ad_name": "Reklam A", "date": f"2026-02-{d:02d}", "impressions": 2000, "spend": 50,
           "cost_per_video_view": 0.25, "link_clicks": 40, "landing_page_views": 30, "view_content": 25, "add_to_cart": 5,
           "initiate_checkout": 3, "results": 1, "purchases": 1} for ad in ("8001", "8002") for d in range(1, 6)]
    store.metrics_ingest(pid, rr, "meta_mcp", CTX)
    p = store.priors_from_history(pid, "*", "2026-03-01")["priors"]
    assert p["step_landing"]["source"] == "history" and abs(p["step_landing"]["mean"] - 0.75) < 1e-6
    assert p["step_cart"]["source"] == "history" and abs(p["step_cart"]["mean"] - 0.2) < 1e-6
    assert p["step_purchase"]["source"] == "uniform"  # reklam başına 15 ödeme başlatma < 30: geçmiş sayılmaz
