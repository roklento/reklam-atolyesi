"""1.5.0: müşteri adayı (lead) sonucu ve hizmet işletmesi, Meta A/B testi, vurgulu altyazı, ses efekti yoğunluğu, profil kontrolü ve
organik adaylar. Migration 006 (campaigns/cycles yeniden kurma) 005 şemalı dolu bir veritabanında sınanır."""
from __future__ import annotations

import json

import pytest

import coach as CO
import report as RP
from admem import db as DB
from admem.s_lead import lead_funnel, special_category_required, target_for, validate_service
from admem.store import Store
from admem.util import AdMemoryError
from conftest import make_active_profile
from test_analytics import build_campaign


def _prof(store):
    a = make_active_profile(store)
    return a["profile"]["id"], a["product"]["id"]


# --- migration 006 ------------------------------------------------------------------------------------------------------------
def test_migration_006_rebuilds_with_children(tmp_path, monkeypatch):
    path = tmp_path / "db" / "ad-memory.sqlite"
    conn = DB.connect(path)
    first = sorted(DB.MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))[:5]
    monkeypatch.setattr(DB, "pending_migrations", lambda c: [f for f in first if int(f.name[:3]) > DB.current_version(c)])
    DB.migrate(conn)
    monkeypatch.undo()
    assert DB.current_version(conn) == 5
    now = "2026-01-01T00:00:00Z"
    x = conn.execute
    x("INSERT INTO brands(id, name, timezone, created_at) VALUES(1, 'Marka A', 'Europe/Istanbul', ?)", (now,))
    x("INSERT INTO profiles(id, slug, name, brand_id, status, created_at) VALUES(1, 'marka-a', 'Marka A', 1, 'active', ?)", (now,))
    x("INSERT INTO products(id, brand_id, name, onboarding_status, created_at) VALUES(7, 1, 'Ürün', 'done', ?)", (now,))
    x("""INSERT INTO campaigns(id, brand_id, product_id, name, slug, result_type, test_structure, stage, cycle, created_at)
         VALUES(5, 1, 7, 'K', 'k', 'purchase', 'creative_test', 'S16', 2, ?)""", (now,))
    x("INSERT INTO cycles(id, campaign_id, cycle, structure_detected, meta_test_id, created_at) VALUES(11, 5, 1, 'bootstrap', 'm1', ?)", (now,))
    x("INSERT INTO cycles(id, campaign_id, cycle, structure_detected, created_at) VALUES(12, 5, 2, 'creative_test', ?)", (now,))
    x("INSERT INTO sales_manual(campaign_id, period_start, period_end, units, created_at) VALUES(5, '2026-01-01', '2026-01-07', 3, ?)", (now,))
    x("INSERT INTO dm_threads(brand_id, campaign_id, ref, channel, source, status, opened_at, opened_date, created_at, updated_at) "
      "VALUES(1, 5, 'M-0001', 'whatsapp', 'unknown', 'open', ?, '2026-01-01', ?, ?)", (now, now, now))
    conn.close()
    s = Store(path, tmp_path)
    try:
        assert DB.current_version(s.conn) == DB.SCHEMA_VERSION >= 6
        c = s.q1("SELECT * FROM campaigns WHERE id=5")
        assert (c["name"], c["result_type"], c["test_structure"], c["stage"], c["cycle"], c["lead_method"]) == \
            ("K", "purchase", "creative_test", "S16", 2, None)
        assert [r["id"] for r in s.qa("SELECT id FROM cycles WHERE campaign_id=5 ORDER BY id")] == [11, 12]
        assert s.q1("SELECT meta_test_id FROM cycles WHERE id=11")["meta_test_id"] == "m1"
        assert s.q1("SELECT kind FROM products WHERE id=7")["kind"] == "product"
        assert s.conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert s.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1  # denetim yeniden açık
        s.ex("UPDATE campaigns SET result_type='lead', lead_method='instant_form' WHERE id=5")  # yeni kısıt kabul ediyor
        with pytest.raises(Exception):
            s.ex("UPDATE campaigns SET lead_method='fax' WHERE id=5")
        with pytest.raises(Exception):  # yabancı anahtar hâlâ çalışıyor
            s.ex("INSERT INTO cycles(campaign_id, cycle, created_at) VALUES(999, 1, 'x')")
        assert list((tmp_path / "backups").glob("*006*")), "migration öncesi yedek alınmalı"
    finally:
        s.close()


def test_fk_off_migration_rolls_back_on_violation(tmp_path, monkeypatch):
    path = tmp_path / "db" / "x.sqlite"
    conn = DB.connect(path)
    DB.migrate(conn)
    bad = tmp_path / "999_bad.sql"
    bad.write_text("-- pragma: foreign_keys=off\nINSERT INTO cycles(campaign_id, cycle, created_at) VALUES(424242, 1, 'x');\n", encoding="utf-8")
    monkeypatch.setattr(DB, "pending_migrations", lambda c: [bad])
    with pytest.raises(Exception, match="yabancı anahtar"):
        DB.migrate(conn)
    assert conn.execute("SELECT COUNT(*) FROM cycles WHERE campaign_id=424242").fetchone()[0] == 0
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


# --- aday sonucu ----------------------------------------------------------------------------------------------------------------
def test_lead_campaign_rules(store):
    pid, prod = _prof(store)
    with pytest.raises(AdMemoryError, match="lead_method"):
        store.campaign_create(pid, prod, "A1", result_type="lead")
    with pytest.raises(AdMemoryError, match="Lead olayı"):
        store.campaign_create(pid, prod, "A2", result_type="lead", lead_method="website")
    c = store.campaign_create(pid, prod, "A3", result_type="lead", lead_method="instant_form")["campaign"]
    assert c["result_type"] == "lead" and c["lead_method"] == "instant_form"
    with pytest.raises(AdMemoryError, match="yalnızca result_type='lead'"):
        store.campaign_create(pid, prod, "A4", result_type="messaging", lead_method="call")
    sig = store.meta_signal_get(pid)["meta_signal"]
    store.meta_signal_set(pid, sig.get("status", "purchase_seen"), "meta_mcp", "veri kümesi D, Lead 7 günde 12", lead_seen=True)
    assert store.campaign_create(pid, prod, "A5", result_type="lead", lead_method="website")["campaign"]["lead_method"] == "website"
    store.meta_signal_set(pid, "purchase_seen", "meta_mcp", "Purchase 7 günde 5")  # lead_seen verilmezse korunur
    assert store.meta_signal_get(pid)["meta_signal"]["lead_seen"] is True
    u = store.campaign_update(pid, c["id"], result_type="messaging")
    assert u["result_type"] == "messaging" and u["lead_method"] is None  # aday dışına geçince yol silinir
    with pytest.raises(AdMemoryError, match="ab_test"):
        store.campaign_update(pid, c["id"], test_structure="ab_test")


def test_service_validation_and_special_category():
    s = validate_service({"duration_min": 45, "capacity_per_week": 30, "booking": "appointment", "area": {"city": "İzmir", "radius_km": 15},
                          "regulated_sector": "health", "special_ad_category": None, "audience_regions": ["tr"]})
    assert s["audience_regions"] == ["TR"]
    for bad, why in (({"duration_min": 0}, "pozitif"), ({"booking": "x"}, "booking"), ({"regulated_sector": "nuclear"}, "regulated_sector"),
                     ({"special_ad_category": "credit"}, "special_ad_category"), ({"audience_regions": ["TUR"]}, "ülke"),
                     ({"note": "ara 0532 123 45 67"}, "telefon")):
        with pytest.raises(AdMemoryError, match=why):
            validate_service(bad)
    assert not special_category_required({"special_ad_category": "housing", "audience_regions": ["TR"]})["required"]
    r = special_category_required({"special_ad_category": "housing", "audience_regions": ["TR", "DE"]})
    assert r["required"] and r["regions"] == ["DE"] and "facebook.com/business/help" in r["source"]


def test_service_product_and_lead_economics(store):
    pid, _ = _prof(store)
    p = store.product_upsert(pid, "Cilt bakımı seansı", kind="service", price=1500, currency="TRY",
                             service_json={"duration_min": 60, "booking": "appointment", "regulated_sector": "health"},
                             economics_json={"contribution": 900, "confirmed": True, "lead_close_rate": 0.2})
    eco = p["economics"]
    assert p["kind"] == "service" and eco["breakeven_cpl"] == 180.0 and eco["target_cpl"] == round(180 * 0.7, 2)
    assert eco["cpl_status"] == "assumed"  # dönüş oranı teyitli değil
    p2 = store.product_upsert(pid, "Cilt bakımı seansı", economics_json={"contribution": 900, "confirmed": True, "lead_close_rate": 0.2,
                                                                       "lead_close_rate_confirmed": True})
    assert p2["economics"]["cpl_status"] == "exact"
    assert target_for("lead", p2["economics"]) == (p2["economics"]["target_cpl"], True)
    assert target_for("purchase", p2["economics"]) == (p2["economics"]["target_cpa"], True)
    assert target_for("messaging", p2["economics"]) == (None, False)
    assert store.product_upsert(pid, "X", economics_json={"contribution": 900, "lead_close_rate": 1.5})["economics"]["cpl_status"] == "unknown"
    with pytest.raises(AdMemoryError, match="kind"):
        store.product_upsert(pid, "Y", kind="subscription")
    assert store.service_info(pid, p["id"])["service"]["regulated_sector"] == "health"


def test_lead_outcomes_rules(store):
    pid, prod = _prof(store)
    cid = store.campaign_create(pid, prod, "L", result_type="lead", lead_method="instant_form")["campaign"]["id"]
    r = store.lead_outcome_set(pid, cid, "2026-03-02", "2026-03-08", 40, reached=30, qualified=12, won=4, revenue=6000, currency="TL")
    assert r["currency"] == "TRY" and r["won"] == 4
    with pytest.raises(AdMemoryError, match="aşamaz"):
        store.lead_outcome_set(pid, cid, "2026-03-09", "2026-03-15", 10, reached=12)
    with pytest.raises(AdMemoryError, match="aşamaz"):
        store.lead_outcome_set(pid, cid, "2026-03-09", "2026-03-15", 10, qualified=5, won=6)
    with pytest.raises(AdMemoryError, match="çakışıyor"):
        store.lead_outcome_set(pid, cid, "2026-03-05", "2026-03-12", 10)
    with pytest.raises(AdMemoryError, match="telefon"):
        store.lead_outcome_set(pid, cid, "2026-03-09", "2026-03-15", 10, note="ayşe 0532 123 45 67")
    with pytest.raises(AdMemoryError, match="para birimi"):
        store.lead_outcome_set(pid, cid, "2026-03-09", "2026-03-15", 10, won=1, revenue=100)
    store.lead_outcome_set(pid, cid, "2026-03-02", "2026-03-08", 42, reached=30, qualified=12, won=5)  # aynı dönem yeniden yazılır
    s = store.lead_outcomes_summary(pid, cid)
    assert len(s["rows"]) == 1 and s["totals"]["leads"] == 42 and s["rates"]["close_rate"] == round(5 / 42, 4)
    f = lead_funnel([{"leads": 10, "reached": None, "qualified": 4, "won": 1}], meta_leads=20)
    assert f["totals"]["reached"] is None and f["rates"]["reach_rate"] is None and f["meta_vs_crm"] == 0.5 and f["meta_vs_crm_note"]


def test_lead_section_in_coach_and_report(store):
    pid, cid, cyid = build_campaign(store)
    store.ex("UPDATE campaigns SET result_type='lead', lead_method='instant_form' WHERE id=?", (cid,))
    store.ex("UPDATE metrics_daily SET results=2")
    store.lead_outcome_set(pid, cid, "2026-03-02", "2026-03-08", 30, reached=25, qualified=9, won=3)
    snap = store.decision_input_snapshot(pid, cid, cyid, "coach_report")
    an = CO.analyze(snap["path"])
    ld = an["lead"]
    assert ld["method"] == "instant_form" and ld["meta_leads"] > 0 and ld["cost_per_lead"] and ld["cost_per_won"]
    assert ld["close_rate_interval"]["lo"] < 0.1 < ld["close_rate_interval"]["hi"]
    md = RP.build(an, json.load(open(snap["path"], encoding="utf-8")), {}, None, None, None)
    assert "Müşteri adayı:" in md and "nitelikli" in md
    store.ex("UPDATE campaigns SET result_type='purchase', lead_method=NULL WHERE id=?", (cid,))
    snap2 = store.decision_input_snapshot(pid, cid, cyid, "coach_report")
    assert CO.analyze(snap2["path"])["lead"] is None
