"""1.4.7: Meta satış sinyali, satış kanalı/talep kaydı, "reklam mı, teklif mi, sayfa mı?" teşhisi ve raporda karar metriği."""
from __future__ import annotations

import json

import pytest

import coach as CO
import report as RP
from admem import db as DB
from admem.store import Store
from admem.util import AdMemoryError
from conftest import make_active_profile
from test_analytics import build_campaign


# --- Meta satış sinyali ----------------------------------------------------------------------
def test_purchase_campaign_requires_signal(store):
    a = make_active_profile(store)
    pid, prod = a["profile"]["id"], a["product"]["id"]
    store.meta_signal_set(pid, "no_purchase", "meta_mcp", "veri kümesi X: son 7 günde Purchase yok", choice="pixel_install")
    with pytest.raises(AdMemoryError, match="Purchase"):
        store.campaign_create(pid, prod, "K", result_type="purchase")
    c = store.campaign_create(pid, prod, "K", result_type="messaging")  # bilinçli başka sonuç: serbest
    with pytest.raises(AdMemoryError, match="Purchase"):
        store.campaign_update(pid, c["campaign"]["id"], result_type="purchase")
    store.meta_signal_set(pid, "purchase_seen", "user_evidence", "Events Manager ekranı: Purchase 3 olay (son 7 gün)")
    assert store.campaign_update(pid, c["campaign"]["id"], result_type="purchase")["result_type"] == "purchase"
    store.meta_signal_set(pid, "no_purchase", "meta_mcp", "piksel kaldırıldı")
    warns = store.campaign_status(pid, c["campaign"]["id"])["campaigns"][0]["warnings"]
    assert any("Meta tıklayanı bulur" in w for w in warns)


def test_meta_signal_validation(store):
    pid = make_active_profile(store)["profile"]["id"]
    with pytest.raises(AdMemoryError, match="kanıt"):
        store.meta_signal_set(pid, "purchase_seen", "meta_mcp", "  ")
    with pytest.raises(AdMemoryError, match="status"):
        store.meta_signal_set(pid, "belki", "meta_mcp", "x")
    with pytest.raises(AdMemoryError, match="choice"):
        store.meta_signal_set(pid, "no_purchase", "meta_mcp", "x", choice="tahmin")
    r = store.meta_signal_set(pid, "purchase_seen", "meta_mcp", "x", choice="pixel_install")
    assert r["meta_signal"]["choice"] is None  # görülen sinyalde yol seçimi anlamsız
    assert store.meta_signal_get(pid)["meta_signal"]["status"] == "purchase_seen"


def test_new_profile_signal_unknown(store):
    p = store.profile_create("Yeni")
    assert store.meta_signal_get(p["id"])["meta_signal"]["status"] == "unknown"


# --- kanal ve talep ---------------------------------------------------------------------------
def test_sales_channel_and_lead(store):
    pid, cid, _ = build_campaign(store)
    with pytest.raises(AdMemoryError, match="kanal"):
        store.sales_add(pid, cid, "2026-03-02", "2026-03-08", 2, 1700, channel="pazar")
    with pytest.raises(AdMemoryError, match="kind"):
        store.sales_add(pid, cid, "2026-03-02", "2026-03-08", 2, 1700, kind="iade")
    s = store.sales_add(pid, cid, "2026-03-02", "2026-03-08", 1, None, "40 adet buket isteği", channel="kurumsal", kind="lead")
    assert s["channel"] == "kurumsal" and s["kind"] == "lead"


# --- teşhis ve rapor --------------------------------------------------------------------------
def test_diagnosis_flags_after_click_and_weak_ctr(store):
    pid, cid, cyid = build_campaign(store)  # tıklama çok, satış yok; B'nin CTR'si düşük
    store.sales_add(pid, cid, "2026-03-02", "2026-03-08", 1, None, "kurumsal DM", channel="kurumsal", kind="lead")
    snap = store.decision_input_snapshot(pid, cid, cyid)
    an = CO.analyze(snap["path"])
    fd = an["funnel_diagnosis"]
    assert fd["after_click"]["verdict"] == "reklam_sonrasi_supheli" and "video kötüydü" in fd["after_click"]["msg"]
    b = {p["concept"]: p for p in fd["per_concept"]}["B"]
    assert any("tıklama oranı" in n for n in b["notes"])
    assert an["channels"]["leads"] == {"kurumsal": 1}
    mb = an["metric_basis"]
    assert "hook oranı" in mb["superiority"] and mb["meta_sees_sales"] is False and "üst huni" in mb["decision"]
    md = RP.build(an, json.load(open(snap["path"], encoding="utf-8")), {}, None, None, None)
    for sec in RP.SECTIONS:
        assert f"## {sec}" in md
    assert "**Karar metriği:**" in md and "en iyi olma olasılığı" in md and "gösterim" in md
    assert "kurumsal: 1 talep" in md


def test_diagnosis_measures_cvr_with_web_sales(store):
    pid, cid, cyid = build_campaign(store)
    store.sales_add(pid, cid, "2026-03-02", "2026-03-08", 12, 10200, "Shopier dökümü", channel="shopier")
    an = CO.analyze(store.decision_input_snapshot(pid, cid, cyid)["path"])
    after = an["funnel_diagnosis"]["after_click"]
    assert after["verdict"] == "olculdu" and after["cvr"] > 0
    assert an["channels"]["sales"]["shopier"]["units"] == 12


# --- migration 004 ---------------------------------------------------------------------------
def test_migration_004_adds_columns_and_keeps_rows(tmp_path, monkeypatch):
    path = tmp_path / "db" / "ad-memory.sqlite"
    conn = DB.connect(path)
    first = sorted(DB.MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))[:3]
    monkeypatch.setattr(DB, "pending_migrations", lambda c: [f for f in first if int(f.name[:3]) > DB.current_version(c)])
    DB.migrate(conn)
    monkeypatch.undo()
    assert DB.current_version(conn) == 3
    now = "2026-01-01T00:00:00Z"
    conn.execute("INSERT INTO brands(id, name, created_at) VALUES(1, 'Marka A', ?)", (now,))
    conn.execute("INSERT INTO profiles(id, slug, name, brand_id, created_at) VALUES(1, 'marka-a', 'Marka A', 1, ?)", (now,))
    conn.execute("INSERT INTO products(id, brand_id, name, created_at) VALUES(1, 1, 'Ürün A', ?)", (now,))
    conn.execute("""INSERT INTO campaigns(id, brand_id, product_id, name, slug, created_at) VALUES(1, 1, 1, 'K', 'k', ?)""", (now,))
    conn.execute("""INSERT INTO sales_manual(id, campaign_id, period_start, period_end, units, revenue, source_note, created_at)
                    VALUES(5, 1, '2026-01-01', '2026-01-07', 3, 300, 'eski kayıt', ?)""", (now,))
    conn.close()
    s = Store(path, tmp_path)
    try:
        assert DB.current_version(s.conn) == DB.SCHEMA_VERSION >= 4
        row = s.q1("SELECT * FROM sales_manual WHERE id=5")
        assert (row["units"], row["source_note"], row["channel"], row["kind"]) == (3, "eski kayıt", None, "sale")
        assert s.meta_signal_get(1)["meta_signal"]["status"] == "unknown"
        assert list((tmp_path / "backups").glob("*004*")), "migration öncesi yedek alınmalı"
    finally:
        s.close()
