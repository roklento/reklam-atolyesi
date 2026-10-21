"""1.5.0 bağımsız inceleme bulgularının regresyon testleri."""
from __future__ import annotations

import datetime as dt
import json

import pytest

import coach as CO
from admem import db as DB
from admem.store import Store
from admem.util import AdMemoryError
from conftest import make_active_profile
from test_analytics import build_campaign


def test_economics_chain_not_broken():
    eco = Store.economics({"economics_json": {"contribution": 200, "confirmed": True}, "price": 500})
    assert eco["status"] == "exact" and "note" not in eco  # katkısı bilinen ürüne "bilinmiyor" notu düşmez
    both = Store.economics({"economics_json": {"contribution": 200, "confirmed": True, "contribution_low": 100, "contribution_high": 300}})
    assert both["status"] == "exact"  # kesin katkı aralığı ezmez (önceki davranış)
    rng = Store.economics({"economics_json": {"contribution_low": 100, "contribution_high": 300, "lead_close_rate": 0.2}})
    assert rng["status"] == "range" and rng["cpl_status"] == "range" and rng["breakeven_cpl_range"] == [20.0, 60.0]
    lead = Store.economics({"economics_json": {"contribution": 500, "confirmed": True, "lead_close_rate": 0.1}})
    assert lead["status"] == "exact" and lead["breakeven_cpl"] == 50.0 and lead["cpl_status"] == "assumed"
    assert Store.economics({"economics_json": {"contribution": 500, "lead_close_rate": True}})["cpl_status"] == "unknown"


def test_lead_growth_gated_on_outcomes_and_window_only(store):
    pid, cid, cyid = build_campaign(store)
    store.ex("UPDATE campaigns SET result_type='lead', lead_method='instant_form' WHERE id=?", (cid,))
    store.ex("UPDATE metrics_daily SET results=3")
    an = CO.analyze(store.decision_input_snapshot(pid, cid, cyid, "coach_report")["path"])
    assert not any(d["decision"] == "büyüt" for d in an["decisions"]) and "büyütme önerilmez" in an["lead"]["note"]
    snap = json.load(open(store.decision_input_snapshot(pid, cid, cyid, "coach_report")["path"], encoding="utf-8"))
    eco = {"status": "exact", "target_cpl": 1000.0, "cpl_status": "exact"}
    dec = CO.decisions({"A": {"rates": {"hook_rate": {"threshold_met": True}}}}, {"A": {"share": 1}}, {**snap, "economics": eco},
                       "creative_test", {"A": {"threshold_met": True, "p_below_target": 0.95}})
    assert dec[0]["decision"] == "büyüt"  # saf karar fonksiyonu; kapı analyze içinde uygulanır
    store.lead_outcome_set(pid, cid, "2026-03-01", "2026-03-31", 100, qualified=40, won=10)  # pencereyi aşan aylık kayıt
    an2 = CO.analyze(store.decision_input_snapshot(pid, cid, cyid, "coach_report")["path"])
    assert an2["lead"]["periods"] == 0 and an2["lead"]["partial_periods"] == [["2026-03-01", "2026-03-31"]]
    assert an2["lead"].get("cost_per_won") is None  # taşan dönemle maliyet küçük gösterilmez


def test_lead_outcome_guards(store):
    a = make_active_profile(store)
    pid, prod = a["profile"]["id"], a["product"]["id"]
    msg = store.campaign_create(pid, prod, "M", result_type="messaging")["campaign"]["id"]
    with pytest.raises(AdMemoryError, match="yalnızca müşteri adayı"):
        store.lead_outcome_set(pid, msg, "2026-03-02", "2026-03-08", 5)
    cid = store.campaign_create(pid, prod, "L", result_type="lead", lead_method="call")["campaign"]["id"]
    with pytest.raises(AdMemoryError, match="satış 0"):
        store.lead_outcome_set(pid, cid, "2026-03-02", "2026-03-08", 5, won=0, revenue=100, currency="TRY")
    store.lead_outcome_set(pid, cid, "2026-03-02", "2026-03-08", 5, won=1, revenue=100, currency="TRY")
    store.lead_outcome_set(pid, cid, "2026-03-09", "2026-03-15", 5, won=1, revenue=50, currency="USD")
    s = store.lead_outcomes_summary(pid, cid)
    assert s["totals"]["revenue"] is None and s["revenue_by_currency"] == {"TRY": 100.0, "USD": 50.0}  # birimler toplanmaz
    st = store.campaign_status(pid)
    assert st is not None


def test_ab_check_budget_and_inputs():
    import budget as BU
    assert any("pozitif" in r for r in BU.ab_check({"cells": 2, "daily_total": 0, "expected_cpr": 50, "cpr_source": "history"})["reasons"])
    assert not BU.ab_check({"cells": 2, "daily_total": -100, "expected_cpr": 50})["eligible"]
    assert not BU.ab_check({"cells": 2, "daily_total": 900, "expected_cpr": "abc"})["eligible"]  # çökmez
    r = BU.ab_check({"cells": 2, "daily_total": 900, "expected_cpr": 10, "days": 40})
    assert any("en fazla 30 gün sürer" in x for x in r["reasons"])
    over = BU.ab_check({"cells": 2, "daily_total": 900, "expected_cpr": 10, "remaining_budget": 1000})
    assert any("kalan kampanya sınırını" in x for x in over["reasons"])


def test_ab_section_only_study_cells_and_no_leader_without_results(store):
    pid, cid, cyid = build_campaign(store)
    store.cycle_set(pid, cyid, structure_detected="ab_test", meta_test_id="61",
                    structure_evidence_json={"study_read": {"cells": ["A", "B"], "variable": "creative"}})
    an = CO.analyze(store.decision_input_snapshot(pid, cid, cyid, "coach_report")["path"])
    assert set(an["ab_test"]["cells"]) == {"A", "B"} and "leader" not in an["ab_test"]  # sonuç yok → önde yok


def test_organic_withdrawn_consent_and_null_range():
    import candidates as OC
    assets = [{"id": 7, "kind": "footage", "path": "p.mp4", "score_json": {"overall": 0.9}, "best_ranges_json": [{"in_s": 0, "out_s": 6}],
               "people_json": [{"kind": "person", "consent_id": 3}]},
              {"id": 8, "kind": "footage", "path": "q.mp4", "score_json": {"overall": 0.9}, "best_ranges_json": [{"in_s": 0, "out_s": None}]}]
    r = OC.build(assets, no_consent_assets={"7"})
    assert r["candidates"] == [] and r["skipped"]["no_consent"] == 1 and r["skipped"]["short"] == 1


def test_preexisting_orphan_does_not_block_migration(tmp_path, monkeypatch):
    path = tmp_path / "db" / "x.sqlite"
    conn = DB.connect(path)
    first = sorted(DB.MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))[:5]
    monkeypatch.setattr(DB, "pending_migrations", lambda c: [f for f in first if int(f.name[:3]) > DB.current_version(c)])
    DB.migrate(conn)
    monkeypatch.undo()
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("INSERT INTO products(brand_id, name, created_at) VALUES(99, 'yetim', 'x')")  # 006'dan bağımsız eski ihlal
    conn.execute("PRAGMA foreign_keys=ON")
    DB.migrate(conn)
    assert DB.current_version(conn) == DB.SCHEMA_VERSION


def test_caption_multiword_and_latin_caps_keywords():
    import words_align as WA
    w = lambda xs: [{"text": t, "start": i * 0.3, "end": i * 0.3 + 0.3} for i, t in enumerate(xs)]
    assert WA.chunks(w(["Kapıda", "ödeme", "ve", "hızlı", "teslimat"]), ["kapıda ödeme"])[0]["emph"] == 0
    assert WA.chunks(w(["LINEN", "gömlek", "koleksiyonu"]), ["linen"])[0]["emph"] == 0
    assert WA.chunks(w(["İSTANBUL", "içi", "teslimat"]), ["istanbul"])[0]["emph"] == 0


def test_sfx_unnamed_cues_not_repeats():
    from admem import editplan
    scenes = [{"id": "s0", "start_s": 0, "dur_s": 4, "audio_cues": [{"at_s": 0.2}, {"at_s": 1.5}]}]
    assert editplan.sfx_density(scenes) == []


def test_profile_check_odd_inputs():
    import profile_check as PC
    now = dt.datetime(2026, 10, 21, tzinfo=dt.timezone.utc)
    pages = [{"ig_media": json.dumps([{"timestamp": "2026-10-20T10:00:00", "media_type": "IMAGE"},
                                      {"timestamp": "2026-10-19", "media_type": "IMAGE"}])},
             {"ig_media": [{"timestamp": 1792000000, "media_type": "VIDEO", "media_product_type": "REELS"},
                           {"id": "s", "timestamp": "2026-10-20T10:00:00+0000", "media_product_type": "STORY"},
                           {"id": "bad", "timestamp": "dün"}]}]
    media = PC._media_list(pages)
    assert len(media) == 5  # kimliksiz paylaşımlar tek sayılmaz
    r = PC.check(media, None, now=now)
    assert r["posts_read"] == 3 and r["stories_skipped"] == 1 and r["last_post_days"] == 0
