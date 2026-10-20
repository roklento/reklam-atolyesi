"""1.4.8: mesajla satış modülü, mağaza sipariş içe aktarma, veri bağlantısı planı, tek satış defteri, Meta ↔ mağaza ve reklam metni uzunluğu."""
from __future__ import annotations

import json

import pytest

import checks as QC
import coach as CO
import report as RP
from admem import db as DB
from admem.store import Store
from admem.util import AdMemoryError
from conftest import make_active_profile
from test_analytics import build_campaign


def _prof(store):
    a = make_active_profile(store)
    return a["profile"]["id"], a["product"]["id"]


# --- DM: kayıt, durum makinesi, kişisel veri ---------------------------------------------------
def test_dm_lifecycle_and_state_machine(store, clock):
    pid, prod = _prof(store)
    clock.advance(days=10)  # olaylar test saatinden sonraki günlere düşüyor; gelecek tarih kuralı ayrıca sınanır
    cid = store.campaign_create(pid, prod, "K", result_type="messaging")["campaign"]["id"]
    t = store.dm_thread_open(pid, "instagram_dm", "2026-03-02T10:00:00+03:00", cid, "ad", "reklamın mesaj düğmesinden geldi",
                             segment="corporate", intent="bulk", quantity=40)
    assert t["ref"] == "M-0001" and t["opened_date"] == "2026-03-02" and t["status"] == "open"
    store.dm_thread_event(pid, "M-0001", "responded", "2026-03-02T10:12:00+03:00")
    store.dm_thread_event(pid, "M-0001", "responded", "2026-03-02T11:00:00+03:00")  # ilk cevap değişmez
    with pytest.raises(AdMemoryError, match="currency"):
        store.dm_thread_event(pid, "M-0001", "quoted", "2026-03-02T12:00:00+03:00", amount=12000)
    store.dm_thread_event(pid, "M-0001", "quoted", "2026-03-02T12:00:00+03:00", amount=12000, currency="try")
    with pytest.raises(AdMemoryError, match="paid_via"):
        store.dm_thread_event(pid, "M-0001", "won", "2026-03-03")
    with pytest.raises(AdMemoryError, match="paid_via"):
        store.dm_thread_event(pid, "M-0001", "won", "2026-03-03", paid_via="havale")
    w = store.dm_thread_event(pid, "M-0001", "won", "2026-03-03T09:00:00+03:00", amount=12000, paid_via="bank_transfer")
    assert w["status"] == "won" and w["closed_at"] and w["first_response_at"] == "2026-03-02T07:12:00Z"
    with pytest.raises(AdMemoryError, match="olmaz"):
        store.dm_thread_event(pid, "M-0001", "lost", "2026-03-04", lost_reason="price")  # kapanmış konuşma
    with pytest.raises(AdMemoryError, match="olay"):
        store.dm_thread_event(pid, "M-0001", "silindi")
    t2 = store.dm_thread_open(pid, "whatsapp", "2026-03-02")
    with pytest.raises(AdMemoryError, match="kayıp nedeni"):
        store.dm_thread_event(pid, t2["ref"], "lost", "2026-03-02")
    store.dm_thread_event(pid, t2["ref"], "qualified", "2026-03-02")  # yalnızca tarih: günün başı, açılıştan önce değil
    store.dm_thread_event(pid, t2["ref"], "lost", "2026-03-02T15:00:00+03:00", lost_reason="price")
    r = store.dm_thread_event(pid, t2["ref"], "reopened", "2026-03-05")
    assert r["status"] == "open" and r["lost_reason"] is None and r["closed_at"] is None
    with pytest.raises(AdMemoryError, match="açılışından önce"):
        store.dm_thread_event(pid, t2["ref"], "note", "2026-03-01")
    with pytest.raises(AdMemoryError, match="gelecekte"):
        store.dm_thread_event(pid, t2["ref"], "note", "2026-04-30")


@pytest.mark.parametrize("note", ["müşteri 0532 123 45 67", "+90 532 1234567", "mail kisi@ornek.com", "@ornek.hesap yazdı",
                                  "IBAN TR12 0006 1000 0000 1234 5678 90", "tc 12345678901"])
def test_dm_rejects_personal_data(store, note):
    pid, _ = _prof(store)
    with pytest.raises(AdMemoryError, match="kişisel veri"):
        store.dm_thread_open(pid, "instagram_dm", note=note)


def test_dm_accepts_plain_notes_and_requires_ad_evidence(store):
    pid, prod = _prof(store)
    cid = store.campaign_create(pid, prod, "K", result_type="messaging")["campaign"]["id"]
    assert store.dm_thread_open(pid, "instagram_dm", note="40 adet buket, logo baskılı, 850 TL dedi")["ref"] == "M-0001"
    with pytest.raises(AdMemoryError, match="kanıt"):
        store.dm_thread_open(pid, "instagram_dm", campaign_id=cid, source="ad")
    with pytest.raises(AdMemoryError, match="campaign_id"):
        store.dm_thread_open(pid, "instagram_dm", source="ad", source_evidence="müşteri reklamı gördüğünü söyledi")
    with pytest.raises(AdMemoryError, match="source='ad'"):
        store.dm_thread_open(pid, "instagram_dm", meta_ad_id="901")
    with pytest.raises(AdMemoryError, match="creative_key"):
        store.dm_thread_open(pid, "instagram_dm", campaign_id=cid, source="ad", source_evidence="x", creative_key="YOK")


def test_dm_daily_totals_and_funnel(store, clock):
    pid, _ = _prof(store)
    store.dm_thread_open(pid, "instagram_dm", "2026-03-02T23:30:00+03:00")  # TR gününde 2 Mart (UTC'de de 2 Mart 20:30)
    t = store.dm_thread_open(pid, "instagram_dm", "2026-03-03T00:30:00+03:00")  # UTC'de 2 Mart 21:30 → TR günü 3 Mart
    assert t["opened_date"] == "2026-03-03"
    store.dm_thread_event(pid, t["ref"], "qualified", "2026-03-03T01:00:00+03:00")
    store.dm_thread_event(pid, t["ref"], "lost", "2026-03-03T02:00:00+03:00", lost_reason="shipping_time")
    with pytest.raises(AdMemoryError, match="aşamaz"):
        store.dm_daily_set(pid, "2026-03-03", "instagram_dm", 5, qualified=6)
    with pytest.raises(AdMemoryError, match="nitelikli"):
        store.dm_daily_set(pid, "2026-03-03", "instagram_dm", 5, qualified=2, quoted=3)
    with pytest.raises(AdMemoryError, match="az olamaz"):
        store.dm_daily_set(pid, "2026-03-03", "instagram_dm", 0)
    store.dm_daily_set(pid, "2026-03-03", "instagram_dm", 6, from_ads=2, qualified=3, quoted=1, won=1)
    with pytest.raises(AdMemoryError, match="aşamaz"):  # günlük toplam doluyken tek tek kayıt toplamı aşamaz
        for _ in range(6):
            store.dm_thread_open(pid, "instagram_dm", "2026-03-03T12:00:00+03:00")
    s = store.dm_summary(pid)
    assert s["totals"]["conversations"] == 1 + 6  # 2 Mart: 1 tekil; 3 Mart: günlük 6
    assert s["totals"]["qualified"] == 3 and s["lost_reasons"] == {"shipping_time": 1}
    # kaybedilen ama nitelikli olmuş konuşma nitelikli sayılır (olaydan)
    only = store.dm_summary(pid, "2026-03-02", "2026-03-02")
    assert only["totals"]["qualified"] == 0 and only["totals"]["conversations"] == 1


def test_dm_follow_ups(store):
    pid, _ = _prof(store)
    a = store.dm_thread_open(pid, "whatsapp", "2026-03-01")
    b = store.dm_thread_open(pid, "whatsapp", "2026-03-02")
    store.dm_thread_event(pid, b["ref"], "follow_up", "2026-03-02", next_follow_up_at="2026-03-02T12:00:00+03:00")
    due = {d["ref"]: d["reason"] for d in store.dm_follow_ups(pid, "2026-03-02T10:00:00Z")["due"]}
    assert b["ref"] in due and "takip zamanı" in due[b["ref"]]
    later = {d["ref"] for d in store.dm_follow_ups(pid, "2026-03-05T10:00:00Z")["due"]}
    assert a["ref"] in later


# --- sipariş içe aktarma -------------------------------------------------------------------------
def _csv(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_order_import_aggregates_dedupes_and_updates(store, tmp_path):
    pid, _ = _prof(store)
    f1 = _csv(tmp_path, "o1.csv", "Name;Created at;Total;Lineitem quantity;Financial Status;Email\n"
                                   "#1001;2026-03-02 10:00:00 +0300;1.700,00;1;paid;x@y.com\n#1001;2026-03-02 10:00:00 +0300;;1;;x@y.com\n"
                                   "#1002;03.03.2026;850,00;1;refunded;z@y.com\n#1003;2026-03-03;850,00;2;pending;q@y.com\n")
    m = {"date": "Created at", "order_id": "Name", "amount": "Total", "units": "Lineitem quantity", "status": "Financial Status"}
    r = store.sales_import_csv(pid, f1, "Shopify", m, status_map={"paid": "paid", "refunded": "refunded"}, currency="TRY")
    assert r["orders"] == 3 and r["new"] == 3 and r["unmapped_statuses"] == {"pending": 1} and r["decimal"] == ","
    rows = store.qa("SELECT * FROM sales_orders ORDER BY date")
    assert rows[0]["amount"] == 1700.0 and rows[0]["units"] == 2  # aynı siparişin iki satırı: tutar ilk dolu, adet toplam
    assert all(len(x["order_hash"]) == 64 for x in rows) and not any("1001" in json.dumps(x) for x in rows)
    assert store.sales_import_csv(pid, f1, "Shopify", m, status_default="paid")["reused"]
    f2 = _csv(tmp_path, "o2.csv", "Name,Created at,Total,Financial Status\n#1003,2026-03-03,850.00,paid\n#1004,2026-03-04,850.00,paid\n")
    r2 = store.sales_import_csv(pid, f2, "Shopify", {"date": "Created at", "order_id": "Name", "amount": "Total", "status": "Financial Status"},
                                status_map={"PAID": "paid"}, currency="TRY")
    assert (r2["new"], r2["updated"]) == (1, 1)
    paid = sum(d["orders"] for d in store.sales_orders_summary(pid)["daily"] if d["status"] == "paid")
    assert paid == 3


def test_order_import_guards(store, tmp_path):
    pid, _ = _prof(store)
    f = _csv(tmp_path, "o.csv", "Sipariş No;Tarih;Tutar\n1;02.03.2026;100\n")
    with pytest.raises(AdMemoryError, match="status_default"):
        store.sales_import_csv(pid, f, "İkas", {"date": "Tarih", "order_id": "Sipariş No"})
    with pytest.raises(AdMemoryError, match="olmayan sütun"):
        store.sales_import_csv(pid, f, "İkas", {"date": "Date", "order_id": "Sipariş No"}, status_default="paid")
    e = _csv(tmp_path, "e.csv", "Order;Date\nkisi@ornek.com;2026-03-02\n")
    with pytest.raises(AdMemoryError, match="e-posta"):
        store.sales_import_csv(pid, e, "Site", {"date": "Date", "order_id": "Order"}, status_default="paid")
    x = tmp_path / "o.xlsx"
    x.write_bytes(b"PK\x03\x04rest")
    with pytest.raises(AdMemoryError, match="CSV"):
        store.sales_import_csv(pid, str(x), "Site", {"date": "Date", "order_id": "Order"}, status_default="paid")
    us = _csv(tmp_path, "us.csv", "Order;Date\nA1;03/04/2026\n")
    r = store.sales_import_csv(pid, us, "Woo", {"date": "Date", "order_id": "Order"}, status_default="paid", date_format="%m/%d/%Y")
    assert store.q1("SELECT date FROM sales_orders WHERE import_id=?", (r["import"]["id"],))["date"] == "2026-03-04"


# --- veri bağlantısı planı -------------------------------------------------------------------------
def test_data_connection_rules(store, tmp_path):
    pid, _ = _prof(store)
    base = {"sales_places": [{"kind": "site", "platform": "Shopify"}], "chosen_paths": ["pixel_code", "order_import"]}
    with pytest.raises(AdMemoryError, match="satış yeri"):
        store.data_connection_set(pid, {"chosen_paths": ["order_import"]})
    with pytest.raises(AdMemoryError, match="events_upload"):
        store.data_connection_set(pid, {**base, "chosen_paths": ["events_upload"], "preference": {"customer_data_to_meta": "undecided"}})
    with pytest.raises(AdMemoryError, match="verified"):
        store.data_connection_set(pid, {**base, "sources": [{"path": "pixel_code", "url": "http://x", "status": "verified"}]})
    store.meta_signal_set(pid, "no_purchase", "meta_mcp", "veri kümesi: Purchase yok")
    with pytest.raises(AdMemoryError, match="Purchase"):
        store.data_connection_set(pid, {**base, "status": "done"})
    store.meta_signal_set(pid, "purchase_seen", "meta_mcp", "veri kümesi: Purchase 4 olay")
    with pytest.raises(AdMemoryError, match="içe aktarma"):
        store.data_connection_set(pid, {**base, "status": "done"})
    f = _csv(tmp_path, "o.csv", "No;Tarih\n1;2026-03-02\n")
    store.sales_import_csv(pid, f, "Shopify", {"date": "Tarih", "order_id": "No"}, status_default="paid")
    r = store.data_connection_set(pid, {**base, "status": "done", "sources": [
        {"path": "pixel_code", "url": "https://www.facebook.com/business/help/x", "checked_at": "2026-10-20", "status": "verified"}]})
    assert r["data_connection"]["status"] == "done"
    g = store.data_connection_get(pid)
    assert g["last_order_import"]["platform"] == "Shopify" and g["meta_signal"]["status"] == "purchase_seen"


# --- koçluk: tek defter, Meta ↔ mağaza, DM -------------------------------------------------------------
def test_ledger_precedence_and_store_vs_meta(store, tmp_path, clock):
    pid, cid, cyid = build_campaign(store)
    clock.advance(days=10)
    store.sales_add(pid, cid, "2026-03-02", "2026-03-08", 5, 4250, "Shopier elle", channel="shopier")
    store.sales_add(pid, cid, "2026-03-02", "2026-03-08", 2, 1700, "DM elle", channel="instagram_dm")
    store.sales_add(pid, cid, "2026-03-02", "2026-03-08", 1, 900, "WhatsApp elle", channel="whatsapp")
    f = _csv(tmp_path, "o.csv", "No;Tarih;Tutar;Durum\nA;2026-03-03;850;Ödendi\nB;2026-03-04;850;Ödendi\nC;2026-03-05;850;İptal\n")
    store.sales_import_csv(pid, f, "Shopier", {"date": "Tarih", "order_id": "No", "amount": "Tutar", "status": "Durum"}, channel="shopier",
                           status_map={"Ödendi": "paid", "İptal": "cancelled"}, currency="TRY")
    t = store.dm_thread_open(pid, "instagram_dm", "2026-03-03")
    store.dm_thread_event(pid, t["ref"], "won", "2026-03-03T18:00:00+03:00", amount=1700, currency="TRY", paid_via="bank_transfer", quantity=2)
    t2 = store.dm_thread_open(pid, "instagram_dm", "2026-03-04")
    store.dm_thread_event(pid, t2["ref"], "won", "2026-03-04T18:00:00+03:00", amount=850, currency="TRY", paid_via="store_link")
    snap = store.decision_input_snapshot(pid, cid, cyid)
    an = CO.analyze(snap["path"])
    ch = an["channels"]
    assert ch["sales"]["shopier"]["units"] == 2 and ch["sales"]["shopier"]["source"] == ["içe aktarma"]  # elle 5 sayılmadı
    assert ch["sales"]["instagram_dm"]["units"] == 2 and ch["sales"]["instagram_dm"]["source"] == ["DM modülü"]  # store_link eklenmedi
    assert ch["sales"]["whatsapp"]["units"] == 1  # öncelikli kaynağı olmayan kanalda elle giriş sayılır
    assert {e["channel"] for e in ch["excluded_manual"]} == {"shopier", "instagram_dm"}
    assert an["store_vs_meta"]["verdict"] == "meta_gormuyor"
    dm = an["dm"]
    assert dm["totals"]["won"] == 2 and dm["won_via_store_link"] == 1 and dm["won_off_store"]["count"] == 1
    md = RP.build(an, json.load(open(snap["path"], encoding="utf-8")), {}, None, None, None)
    assert "Mesajla satış:" in md and "Meta ↔ mağaza" in md and "sayılmadı" in md
    # aynı veri → aynı kopya (bugünün tarihine bağlı değil)
    assert store.decision_input_snapshot(pid, cid, cyid)["reused"]


def test_store_vs_meta_overcount():
    snap = {"sales_orders": [{"date": "2026-03-03", "channel": "site", "status": "paid", "orders": 2, "units": 2, "amount": 100}]}
    chan = CO.channel_summary(snap, ["2026-03-02", "2026-03-08"])
    v = CO.store_vs_meta(snap, [{"purchases": 6}], chan)
    assert v["verdict"] == "meta_fazla"
    assert CO.store_vs_meta(snap, [{"purchases": 2}], chan)["verdict"] == "uyumlu"


# --- reklam metni uzunluğu ---------------------------------------------------------------------------
def test_copy_length_rules():
    plan_silent = {"format": "9x16", "scenes": [{"id": "s1", "role": "hook", "audio": {"mode": "none"},
                                                "layers": [{"type": "video", "source": {"kind": "footage"}}]}]}
    long = "Elde dökülen, hiç solmayan buket. " * 3 + "Şimdi 850 TL, kargo ücretsiz."
    r = QC.copy_length({"primary": long, "headline": "x" * 41, "description": "kısa"}, plan_silent, ["kargo ücretsiz"])
    rules = {(w["field"], w["rule"]) for w in r["warnings"]}
    assert ("primary", "uzunluk") in rules and ("headline", "uzunluk") in rules and ("primary", "görünür mesaj") in rules
    assert any("mesajı yalnızca reklam metni" in i for i in r["info"])
    ok = QC.copy_length({"primary": "Kargo ücretsiz: hiç solmayan el yapımı buket.", "headline": "Solmayan buket"}, plan_silent, ["kargo"])
    assert ok["ok"]
    assert not QC.copy_length({"primary": "a 🌷🌷🌷🌷 #x #y #z"})["ok"]
    assert QC.copy_length({"primary": "x" * 100}, targets={"primary": 90})["warnings"]
    with pytest.raises(SystemExit):
        QC.copy_length({"primary": "x"}, targets={"primary": 200})
    assert QC.visible_len("İğdır şçöü") == 10 and QC.visible_len("👍🏽") == 1
    priced = {"format": "4x5", "scenes": [{"id": "s1", "role": "offer", "audio": {"mode": "generated"},
                                           "layers": [{"type": "component", "component": "PriceTag", "props": {"price": "850 TL"}}]}]}
    assert any("Fiyat videoda" in i for i in QC.copy_length({"primary": "Şimdi 850 TL"}, priced)["info"])


# --- migration 005 ---------------------------------------------------------------------------------------
def test_migration_005_on_004_database(tmp_path, monkeypatch):
    path = tmp_path / "db" / "ad-memory.sqlite"
    conn = DB.connect(path)
    first = sorted(DB.MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))[:4]
    monkeypatch.setattr(DB, "pending_migrations", lambda c: [f for f in first if int(f.name[:3]) > DB.current_version(c)])
    DB.migrate(conn)
    monkeypatch.undo()
    assert DB.current_version(conn) == 4
    now = "2026-01-01T00:00:00Z"
    conn.execute("INSERT INTO brands(id, name, timezone, created_at) VALUES(1, 'Marka A', 'Europe/Istanbul', ?)", (now,))
    conn.execute("INSERT INTO profiles(id, slug, name, brand_id, status, created_at) VALUES(1, 'marka-a', 'Marka A', 1, 'active', ?)", (now,))
    conn.close()
    s = Store(path, tmp_path)
    try:
        assert DB.current_version(s.conn) == DB.SCHEMA_VERSION >= 5
        assert s.data_connection_get(1)["data_connection"] is None
        assert s.dm_thread_open(1, "phone", "2026-01-02")["ref"] == "M-0001"
        assert list((tmp_path / "backups").glob("*005*")), "migration öncesi yedek alınmalı"
        assert s.conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        s.close()
