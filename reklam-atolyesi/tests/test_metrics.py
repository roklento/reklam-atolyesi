"""Metrik içe alma, ölçüm bağlamı, CSV, test penceresi ve önseller (spec 6.4, 6.6, 6.15, 9.2)."""
from __future__ import annotations

import pytest

from admem.util import AdMemoryError
from conftest import make_active_profile

CTX = {"account_id": "act_A", "timezone": "Europe/Istanbul", "currency": "TRY", "result_definition": "purchase",
       "metric_definitions": {"video_3s": "derived"}, "attribution_window": "7d_click_1d_view", "action_report_time": "impression"}


def rows(ad="9001", n=5, start=1):
    return [{"meta_ad_id": ad, "ad_name": "Reklam A", "date": f"2026-03-{start + i:02d}", "impressions": 1000, "spend": 50,
             "cost_per_video_view": 0.25, "link_clicks": 12, "results": 1, "purchases": 1} for i in range(n)]


def test_ingest_requires_context_and_derives_3s(store):
    pid = make_active_profile(store)["profile"]["id"]
    with pytest.raises(AdMemoryError):
        store.metrics_ingest(pid, rows(), "meta_mcp", {"account_id": "act_A"})
    r = store.metrics_ingest(pid, rows(), "meta_mcp", CTX)
    assert r["inserted"] == 5
    m = store.metrics_daily_rows(pid)["rows"][0]
    assert m["video_3s"] == 200 and m["video_3s_derived"] == 1


def test_null_context_needs_reason(store):
    pid = make_active_profile(store)["profile"]["id"]
    ctx = {**CTX, "attribution_window": None}
    with pytest.raises(AdMemoryError):
        store.metrics_ingest(pid, rows(), "csv", ctx)
    store.metrics_ingest(pid, rows(), "csv", {**ctx, "null_reasons": {"attribution_window": "dışa aktarımda yok"}})


def test_mismatched_definition_rolls_back_whole_import(store):
    pid = make_active_profile(store)["profile"]["id"]
    store.metrics_ingest(pid, rows(n=3), "meta_mcp", CTX)
    bad = {**CTX, "attribution_window": "1d_click"}
    new_rows = rows(n=3, start=4) + rows(n=1, start=1)  # 3 yeni gün + 1 mevcut gün farklı tanımla
    with pytest.raises(AdMemoryError):
        store.metrics_ingest(pid, new_rows, "csv", bad)
    assert len(store.metrics_daily_rows(pid)["rows"]) == 3  # yeni satırların hiçbiri yazılmadı


def test_same_definition_correction_updates(store):
    pid = make_active_profile(store)["profile"]["id"]
    store.metrics_ingest(pid, rows(n=2), "meta_mcp", CTX)
    rr = rows(n=2)
    rr[0]["spend"] = 55
    r = store.metrics_ingest(pid, rr, "meta_mcp", CTX)
    assert r["updated"] == 2
    assert store.metrics_daily_rows(pid)["rows"][0]["spend"] == 55


def test_unknown_completed_only_with_evidence(store):
    pid = make_active_profile(store)["profile"]["id"]
    ctx0 = {**CTX, "action_report_time": None, "null_reasons": {"action_report_time": "okunamadı"}}
    store.metrics_ingest(pid, rows(n=1), "csv", ctx0)
    with pytest.raises(AdMemoryError):
        store.metrics_ingest(pid, rows(n=1), "csv", CTX)
    store.metrics_ingest(pid, rows(n=1), "csv", CTX, completion_evidence="rapor ayarı ekran görüntüsü")


def test_other_account_rejected(store):
    pid = make_active_profile(store)["profile"]["id"]
    with pytest.raises(AdMemoryError):
        store.metrics_ingest(pid, rows(), "meta_mcp", {**CTX, "account_id": "act_X"})


def test_csv_import_turkish_export(store, tmp_path):
    import meta_tools
    pid = make_active_profile(store)["profile"]["id"]
    csvp = tmp_path / "disa.csv"
    meta_tools.synth_csv(str(csvp), 2, 4, 1729, "2026-02-01", ",")
    chk = meta_tools.csv_check(str(csvp))
    assert not chk["missing_required"] and chk["decimal"] == ","
    r = store.metrics_import_csv(pid, str(csvp), CTX)
    assert r["inserted"] == 8 and r["decimal"] == ","
    exp = store.metrics_export_csv(pid, str(tmp_path / "geri.csv"))
    assert exp["rows"] == 8


def test_test_window_boundary_days(store):
    tz = "Europe/Istanbul"
    w = store.test_window_days("2026-03-02T18:00:00+03:00", "2026-03-09T18:00:00+03:00", tz)
    assert len(w["full_days"]) == 6 and w["excluded_boundary_days"] == ["2026-03-02", "2026-03-09"]
    w2 = store.test_window_days("2026-03-02T00:00:00+03:00", "2026-03-09T00:00:00+03:00", tz)
    assert len(w2["full_days"]) == 7 and not w2["excluded_boundary_days"]


def test_metrics_query_test_window_excludes_boundaries(store):
    a = make_active_profile(store)
    pid = a["profile"]["id"]
    c = store.campaign_create(pid, a["product"]["id"], "K")
    cid, cyid = c["campaign"]["id"], c["cycle"]["id"]
    store.ex("UPDATE cycles SET test_start='2026-03-02T18:00:00+03:00', test_end='2026-03-09T18:00:00+03:00' WHERE id=?", (cyid,))
    rr = [{**r, "date": f"2026-03-{d:02d}"} for d, r in zip(range(1, 11), rows(n=10))]
    store.metrics_ingest(pid, rr, "meta_mcp", CTX)
    store.ex("UPDATE ads SET campaign_id=?, cycle_id=?", (cid, cyid))
    q = store.metrics_query(pid, cid, cyid, level="ad", window="test")
    assert q["groups"][0]["n_days"] == 6 and q["excluded_boundary_days"] == ["2026-03-02", "2026-03-09"]
    assert q["groups"][0]["spend"] == 6 * 50


def test_priors_cutoff_excludes_test_data(store):
    pid = make_active_profile(store)["profile"]["id"]
    rr = rows(ad="7001", n=6) + rows(ad="7002", n=6)
    store.metrics_ingest(pid, rr, "meta_mcp", CTX)
    r = store.priors_from_history(pid, "*", "2026-03-04")
    assert r["priors"]["hook_rate"]["source"] in ("history", "uniform")
    r2 = store.priors_from_history(pid, "*", "2026-03-01")
    assert r2["priors"]["hook_rate"]["source"] == "uniform"  # kesimden önce veri yok → Beta(1,1)


def test_naming_rules():
    from admem import naming
    k = naming.build_key("MRK", "K1", "A", "video", 15, "h1", True, "ai", 1, 1)
    assert k == "MRK_K1_A_video_15_h1_vo_ai_c1_r1"
    assert naming.build_file_name(k, "9x16") == "MRK_K1_A_video_15_h1_vo_ai_c1_r1_916.mp4"
    ck = naming.build_key("MRK", "K1", "A", "carousel", None, "h1", False, "real", 1, 1)
    assert naming.build_file_name(ck, "4x5", 2, "jpg").endswith("_45_k2.jpg")
    assert naming.match_ad_name(k) == k and naming.match_ad_name(k + "_45") == k
    assert naming.match_ad_name("Eski reklam 3") is None
