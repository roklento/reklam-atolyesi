"""2.10.4: karar verisi (dış kod denetimi, Dalga B). Sentetik veri; ağ yok."""
from __future__ import annotations

import math

import pytest

import budget as BU
import coach as CO
from conftest import make_active_profile
from test_analytics import build_campaign
from test_dm_orders import _csv, _prof
from admem.store import Store
from admem.util import AdMemoryError


# ----------------------------------------------------------------------------- ölçüm tanımı ve ayarlar
def test_mixed_measurement_definitions_give_no_verdict(store):
    pid, cid, cyid = build_campaign(store)
    clean = CO.analyze(store.decision_input_snapshot(pid, cid, cyid)["path"])
    assert clean["predictions"]
    store.ex("UPDATE metrics_daily SET measurement_fingerprint='baska-tanim' WHERE date >= '2026-03-05'")
    an = CO.analyze(store.decision_input_snapshot(pid, cid, cyid)["path"])
    assert any(q["kind"] == "mixed_definitions" for q in an["data_quality"])
    assert an["predictions"] == []
    assert all(v["p_best"] is None and v["p_above_history"] is None for v in an["superiority_hook"].values())
    assert all(d["decision"] not in ("büyüt", "kapat") for d in an["decisions"])


def test_unapplied_params_are_refused(store):
    pid, cid, cyid = build_campaign(store)
    with pytest.raises(AdMemoryError, match="interval"):
        store.decision_input_snapshot(pid, cid, cyid, extra={"params": {"interval": 0.5}})
    snap = store.decision_input_snapshot(pid, cid, cyid, extra={"params": {"interval": 0.9}})  # aynı değer sorun değil
    assert CO.analyze(snap["path"])


def test_analyze_refuses_snapshot_with_other_interval(tmp_path):
    with pytest.raises(SystemExit, match="interval"):
        CO.check_params({"params": {"interval": 0.5, "seed": 1729}})
    CO.check_params({"params": {"interval": 0.9, "seed": 1729, "draws": 10_000, "n_cap": 30}})


# ----------------------------------------------------------------------------- para birimi
def test_channel_summary_keeps_currencies_apart():
    days = ["2026-03-02", "2026-03-03"]
    snap = {"currency": "TRY", "sales_orders": [
        {"date": "2026-03-02", "channel": "site", "status": "paid", "orders": 1, "units": 1, "amount": 100, "currency": "TRY"},
        {"date": "2026-03-02", "channel": "site", "status": "paid", "orders": 1, "units": 1, "amount": 100, "currency": "USD"}]}
    ch = CO.channel_summary(snap, days)
    assert ch["sales"]["site"]["revenue"] == 100 and ch["sales"]["site"]["units"] == 1
    assert ch["other_currency"] == {"site": {"USD": {"units": 1, "revenue": 100}}}
    assert "Farklı para birimindeki" in ch["note"]


def test_channel_summary_without_product_currency_uses_most_common():
    days = ["2026-03-02"]
    rows = [{"date": "2026-03-02", "channel": "site", "status": "paid", "orders": 1, "units": 1, "amount": 50, "currency": c}
            for c in ("TRY", "TRY", "EUR")]
    ch = CO.channel_summary({"sales_orders": rows}, days)
    assert ch["currency"] == "TRY" and ch["sales"]["site"]["revenue"] == 100 and "EUR" in ch["other_currency"]["site"]


def test_single_currency_unchanged():
    days = ["2026-03-02"]
    rows = [{"date": "2026-03-02", "channel": "site", "status": "paid", "orders": 1, "units": 2, "amount": 50}]
    ch = CO.channel_summary({"sales_orders": rows}, days)
    assert ch["sales"]["site"]["revenue"] == 50 and ch["other_currency"] == {}


# ----------------------------------------------------------------------------- sipariş düzeltmesi
def test_order_quantity_correction_is_imported(store, tmp_path):
    pid, _ = _prof(store)
    m = {"date": "Date", "order_id": "Id", "amount": "Total", "units": "Qty", "status": "Status"}
    f1 = _csv(tmp_path, "a.csv", "Id,Date,Total,Qty,Status\nX1,2026-03-02,100.00,1,paid\n")
    store.sales_import_csv(pid, f1, "Magaza", m, status_default="paid", currency="TRY")
    f2 = _csv(tmp_path, "b.csv", "Id,Date,Total,Qty,Status\nX1,2026-03-02,100.00,2,paid\n")
    r = store.sales_import_csv(pid, f2, "Magaza", m, status_default="paid", currency="TRY")
    assert r["updated"] == 1 and store.q1("SELECT units FROM sales_orders")["units"] == 2


# ----------------------------------------------------------------------------- sonlu sayılar
@pytest.mark.parametrize("bad", ["NaN", "inf", "-Infinity", "yüz"])
def test_economics_rejects_non_finite_contribution(bad):
    e = Store.economics({"economics_json": {"contribution": bad, "confirmed": True}, "price": 100})
    assert e["status"] == "unknown" and "target_cpa" not in e and e["invalid_values"] == ["contribution"]


def test_economics_non_finite_safety_factor_falls_back():
    e = Store.economics({"economics_json": {"contribution": 40, "confirmed": True}, "price": 100, "safety_factor": "nan"})
    assert e["status"] == "exact" and math.isfinite(e["target_cpa"]) and e["safety_factor"] == 0.7


BASE = {"cycle_no": 1, "adset_daily": 100, "cpm": 50, "budget_total": 1400, "spend_to_date": 0}


@pytest.mark.parametrize("field,value", [("other_daily_budgets", [-100]), ("other_daily_budgets", ["nan"]), ("budget_total", -1),
                                         ("spend_to_date", float("inf")), ("scale_layer_daily", -5)])
def test_budget_plan_rejects_negative_or_non_finite(field, value):
    with pytest.raises(SystemExit):
        BU.plan({**BASE, field: value})


def test_budget_plan_valid_other_budgets_still_count():
    out = BU.plan({**BASE, "other_daily_budgets": [100]})
    assert out["spend_projection"]["projected_additional"] > 0
