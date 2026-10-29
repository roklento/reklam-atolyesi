"""1.9.0: huni aşamasına göre içerik planlama — stage ekseni, satın alma engelleri, mesaj kartı, BOFU kanıt kapısı, huni turu,
yeni aşama metrikleri ve QC "aşama farkı yalnız kapanışta" kontrolü."""
from __future__ import annotations

import sqlite3

import pytest

from admem import db as DB
from admem.util import AdMemoryError
from conftest import out_file
from test_s03_portfolio import at_s03, gate


def msg(stage="tofu", **kw):
    m = {"stage": stage, "stage_basis": "assumption", "belief": "bu ürün hediye için uygun", "focus": "need",
         "evidence": [{"kind": "none"}], "expected_action": "profile bakmak"}
    m.update(kw)
    return m


def concept(s, pid, cid, cyid, code, buyer, message, frame="product", emotion=None):
    feats = {"buyer": buyer, **({"emotion": emotion} if emotion else {})}
    k = s.concept_upsert(pid, cid, cyid, code, f"Konsept {code}", "general", decision="accepted", user_said=f"{code} olsun",
                         features=feats, message=message)
    s.hypothesis_add(pid, f"{code} konsepti kendi aşama metriğinde öndedir", "hook_rate", cid, cyid, concept_id=k["id"])
    s.hook_upsert(pid, k["id"], "h1", frame, f"{frame} açılışı", "hareket", "ses", "Örnek metin", decision="accepted", user_said="bu hook")
    return k


def product_id(s, cid):
    return s.q1("SELECT product_id FROM campaigns WHERE id=?", (cid,))["product_id"]


def set_funnel(s, pid, cid, cyid, buyer="alici-a"):
    s.ex("UPDATE cycles SET cycle=2 WHERE id=?", (cyid,)); s.ex("UPDATE campaigns SET cycle=2 WHERE id=?", (cid,))  # huni turu 2. turdan itibaren (kreatif test eşit böler)
    bp = s.q1("SELECT budget_plan_json FROM cycles WHERE id=?", (cyid,))["budget_plan_json"]
    s.cycle_set(pid, cyid, budget_plan_json={**bp, "round_mode": "funnel",
                                             "funnel": {"buyer": buyer, "basis": "1. turda alici-a kazandı", "user_said": "huni turu açalım"}})


def test_taxonomy_has_stage_axis_and_funnel_round(store):
    pid, cid, cyid = at_s03(store)
    t = store.taxonomy_get(pid)
    assert t["taxonomy_version"] == "1.9.0"
    assert set(t["fixed_axes"]["stage"]["values"]) == {"tofu", "mofu", "bofu"}
    assert t["funnel_round"]["distinct_axis"] == "stage" and t["funnel_round"]["shared_axis"] == "buyer"
    with pytest.raises(AdMemoryError, match="sabit eksende yok"):
        store.concept_upsert(pid, cid, cyid, "X", "X", "general", features={"stage": "sicak_kitle"})


def test_migration_007_adds_columns(store):
    assert DB.current_version(store.conn) == DB.SCHEMA_VERSION >= 7
    cols = {r[1] for r in store.conn.execute("PRAGMA table_info(metrics_daily)")}
    assert {"landing_page_views", "view_content", "initiate_checkout"} <= cols
    assert "objections_json" in {r[1] for r in store.conn.execute("PRAGMA table_info(products)")}
    assert "message_json" in {r[1] for r in store.conn.execute("PRAGMA table_info(concepts)")}


def test_objections_need_evidence_to_carry_an_answer(store):
    pid, cid, cyid = at_s03(store)
    prod = product_id(store, cid)
    with pytest.raises(AdMemoryError, match="kanıtıyla"):
        store.product_upsert(pid, "Ürün A", prod, objections_json=[{"code": "kargo", "text": "Kaç günde gelir?", "source": "user",
                                                                    "answer": "2 günde"}])
    with pytest.raises(AdMemoryError, match="source"):
        store.product_upsert(pid, "Ürün A", prod, objections_json=[{"code": "kargo", "text": "Kaç günde gelir?", "source": "tahmin"}])
    p = store.product_upsert(pid, "Ürün A", prod, objections_json=[
        {"code": "kargo", "text": "Kaç günde gelir?", "source": "page_check", "answer": "sayfada 1–3 iş günü yazıyor",
         "evidence": {"kind": "page_info", "ref": "satış sayfası kargo bölümü"}},
        {"code": "boyut", "text": "Görseldeki gibi mi?", "source": "dm_lost_reason"}])
    assert [o["code"] for o in p["objections_json"]] == ["kargo", "boyut"]


def test_message_card_validation(store):
    pid, cid, cyid = at_s03(store)
    up = lambda m: store.concept_upsert(pid, cid, cyid, "A", "A", "general", features={"buyer": "alici-a"}, message=m)
    with pytest.raises(AdMemoryError, match="stage"):
        up(msg(stage="sicak"))
    with pytest.raises(AdMemoryError, match="stage_basis_note"):
        up(msg(stage_basis="data"))
    with pytest.raises(AdMemoryError, match="objection_code"):
        up(msg(focus="objection", objection_code="yok"))
    with pytest.raises(AdMemoryError, match="checked_at"):
        up(msg(evidence=[{"kind": "page_info", "ref": "kargo bilgisi"}]))
    with pytest.raises(AdMemoryError, match="çelişiyor"):
        store.concept_upsert(pid, cid, cyid, "A", "A", "general", features={"buyer": "alici-a", "stage": "mofu"}, message=msg())
    k = up(msg(stage_basis="data", stage_basis_note="hesapta 90 günde sepete ekleme var, satış az"))
    assert k["features_json"]["stage"] == "tofu" and k["message_json"]["stage_basis"] == "data"


def test_bofu_requires_real_evidence(store):
    pid, cid, cyid = at_s03(store)
    prod = product_id(store, cid)
    up = lambda m: store.concept_upsert(pid, cid, cyid, "C", "C", "general", features={"buyer": "alici-a"}, message=m)
    with pytest.raises(AdMemoryError, match="BOFU"):
        up(msg("bofu"))
    with pytest.raises(AdMemoryError, match="izinli"):
        up(msg("bofu", evidence=[{"kind": "review", "ref": 999}]))
    with pytest.raises(AdMemoryError, match="kanıtlanabilir iddia"):
        up(msg("bofu", evidence=[{"kind": "claim", "ref": "en iyisi biziz"}]))
    store.product_upsert(pid, "Ürün A", prod, provable_claims_json=[
        {"claim": "el yapımı", "evidence_kind": "process", "needs_document": False, "verified": True},
        {"claim": "doğal soya", "evidence_kind": "document", "needs_document": True, "verified": False}])
    with pytest.raises(AdMemoryError, match="kanıtlanabilir iddia"):
        up(msg("bofu", evidence=[{"kind": "claim", "ref": "doğal soya"}]))  # belgesi gerekiyor, doğrulanmadı
    assert up(msg("bofu", evidence=[{"kind": "claim", "ref": "El yapımı"}]))["message_json"]["stage"] == "bofu"
    rv = store.review_add(pid, "Görseldeki gibi geldi", "initials", "yazili", "2026-03-01", out_file(store, pid, cid, "izin.pdf"))
    assert up(msg("bofu", evidence=[{"kind": "review", "ref": rv["id"]}]))
    store.review_withdraw(pid, rv["id"], "izin geri çekildi")
    with pytest.raises(AdMemoryError, match="izinli"):
        up(msg("bofu", evidence=[{"kind": "review", "ref": rv["id"]}]))
    # odak engelse ve BOFU ise engelin cevap kanıtı ürün kartında olmalı
    store.product_upsert(pid, "Ürün A", prod, objections_json=[{"code": "boyut", "text": "Görseldeki gibi mi?", "source": "user"}])
    with pytest.raises(AdMemoryError, match="cevap kanıtı yok"):
        up(msg("bofu", focus="objection", objection_code="boyut", evidence=[{"kind": "claim", "ref": "el yapımı"}]))


def test_gate_requires_message_card(store):
    pid, cid, cyid = at_s03(store)
    k = store.concept_upsert(pid, cid, cyid, "A", "A", "general", decision="accepted", user_said="A olsun", features={"buyer": "alici-a"})
    store.hypothesis_add(pid, "A öndedir", "hook_rate", cid, cyid, concept_id=k["id"])
    store.hook_upsert(pid, k["id"], "h1", "product", "ürün", "hareket", "ses", "metin", decision="accepted", user_said="bu")
    concept(store, pid, cid, cyid, "B", "alici-b", msg(), frame="person", emotion="duygu-a")
    with pytest.raises(AdMemoryError, match="konsept A için mesaj kartı"):
        gate(store, pid, cid, cyid)()


def test_explore_round_still_rejects_same_buyer_stage_set(store):
    pid, cid, cyid = at_s03(store)
    concept(store, pid, cid, cyid, "T", "alici-a", msg("tofu"), frame="context", emotion="duygu-a")
    concept(store, pid, cid, cyid, "M", "alici-a", msg("mofu"), frame="product_in_hand", emotion="duygu-b")
    r = store.concept_diversity_check(pid, cid, cyid)
    assert r["round_mode"] == "explore" and not r["passed"] and any("aynı alıcıya" in i for i in r["issues"])


def test_funnel_round_requires_basis(store):
    pid, cid, cyid = at_s03(store)
    bp = store.q1("SELECT budget_plan_json FROM cycles WHERE id=?", (cyid,))["budget_plan_json"]
    with pytest.raises(AdMemoryError, match="huni turu"):
        store.cycle_set(pid, cyid, budget_plan_json={**bp, "round_mode": "funnel"})
    with pytest.raises(AdMemoryError, match="round_mode"):
        store.cycle_set(pid, cyid, budget_plan_json={**bp, "round_mode": "sicak_kitle"})
    funnel = {"buyer": "alici-a", "basis": "kullanıcı isteği", "user_said": "huni turu"}
    with pytest.raises(AdMemoryError, match="ilk turda"):
        store.cycle_set(pid, cyid, budget_plan_json={**bp, "round_mode": "funnel", "funnel": funnel})
    store.ex("UPDATE cycles SET cycle=2 WHERE id=?", (cyid,))
    assert store.cycle_set(pid, cyid, budget_plan_json={**bp, "round_mode": "funnel", "funnel": funnel})


def test_funnel_round_same_buyer_distinct_stages_passes_gate(store):
    pid, cid, cyid = at_s03(store)
    set_funnel(store, pid, cid, cyid)
    store.product_upsert(pid, "Ürün A", product_id(store, cid), provable_claims_json=[
        {"claim": "el yapımı", "evidence_kind": "process", "needs_document": False, "verified": True}])
    concept(store, pid, cid, cyid, "T", "alici-a", msg("tofu"), frame="context")
    concept(store, pid, cid, cyid, "M", "alici-a", msg("tofu", focus="desire"), frame="product_in_hand")
    r = store.concept_diversity_check(pid, cid, cyid)
    assert r["round_mode"] == "funnel" and any("aynı aşamada" in i for i in r["issues"])
    store.concept_upsert(pid, cid, cyid, "M", "Konsept M", "general", message=msg("mofu", focus="desire"))
    concept(store, pid, cid, cyid, "B", "alici-a", msg("bofu", evidence=[{"kind": "claim", "ref": "el yapımı"}]), frame="result")
    r = store.concept_diversity_check(pid, cid, cyid)
    assert r["passed"], r["issues"]
    assert sorted(e["stage"] for e in r["exploration"]) == ["bofu", "mofu", "tofu"]
    gate(store, pid, cid, cyid)()


def test_funnel_round_rejects_mixed_buyers_and_too_many(store):
    pid, cid, cyid = at_s03(store)
    set_funnel(store, pid, cid, cyid)
    concept(store, pid, cid, cyid, "T", "alici-a", msg("tofu"))
    concept(store, pid, cid, cyid, "M", "alici-b", msg("mofu"))
    r = store.concept_diversity_check(pid, cid, cyid)
    assert not r["passed"] and any("aynı alıcıya konuşur" in i for i in r["issues"])
    r1 = store.concept_diversity_check(pid, cid, cyid)
    assert r1["rule"]["max_concepts"] == 3


def test_new_stage_metrics_are_stored_and_aggregated(store):
    from conftest import make_active_profile
    from test_metrics import CTX
    pid = make_active_profile(store)["profile"]["id"]
    rows = [{"meta_ad_id": "9001", "ad_name": "Reklam A", "date": "2026-03-03", "impressions": 1000, "spend": 50, "link_clicks": 20,
             "landing_page_views": 15, "view_content": 12, "add_to_cart": 3, "initiate_checkout": 2, "purchases": 1, "results": 1}]
    store.metrics_ingest(pid, rows, "meta_mcp", CTX)
    m = store.metrics_daily_rows(pid)["rows"][0]
    assert (m["landing_page_views"], m["view_content"], m["initiate_checkout"]) == (15, 12, 2)
    g = store.metrics_query(pid, level="ad")["groups"][0]
    assert g["view_content"] == 12 and g["initiate_checkout"] == 2


def test_claim_usable_accepts_both_claim_shapes():
    from admem.funnel import claim_usable
    assert claim_usable("Örnek iddia", [{"code": "c1", "text": "Örnek iddia", "documented": True}])
    assert not claim_usable("Örnek iddia", [{"code": "c1", "text": "Örnek iddia", "documented": False, "needs_document": True}])
    assert claim_usable("el yapımı", [{"claim": "El yapımı", "needs_document": False}])


def test_coach_stage_section_reads_each_concept_by_its_own_stage():
    import coach as CO
    snap = {"creatives": [{"creative_key": "k1", "concept": "T", "concept_features": {"stage": "tofu"}},
                          {"creative_key": "k2", "concept": "M", "concept_features": '{"stage": "mofu"}'},
                          {"creative_key": "k3", "concept": "B", "concept_features": {"stage": "bofu"}},
                          {"creative_key": "k4", "concept": "X", "concept_features": {}}],
            "cycle": {"budget_plan_json": {"round_mode": "funnel", "funnel": {"buyer": "alici-a", "basis": "x"}}},
            "extra": {"audience_segments": {"B": {"new": 80, "engaged": 15, "existing": 5}}}}
    rows = lambda **kw: [{"impressions": 1000, "spend": 100, "video_3s": 300, "thruplay": 90, "link_clicks": 20, **kw}]
    by = {"T": rows(), "M": rows(landing_page_views=16), "B": rows(add_to_cart=4, purchases=2), "X": rows()}
    st = CO.stage_section(snap, by)
    per = {p["concept"]: p for p in st["per_concept"]}
    assert set(per) == {"T", "M", "B"} and st["round_mode"] == "funnel"
    assert per["T"]["metrics"]["hook_rate"] == 0.3 and per["T"]["metrics"]["hold_rate"] == 0.3
    assert per["M"]["metrics"]["landing_page_view_rate"] == 0.8 and "view_content_rate" in per["M"]["unread"]  # piksel olayı yok: okunamadı
    assert per["B"]["metrics"]["cost_per_purchase"] == 50.0 and "checkout_rate" in per["B"]["unread"]
    assert per["B"]["segments"]["new"] == 0.8 and "yeni kitleye" in per["B"]["segment_note"]
    assert CO.stage_section({"creatives": [], "cycle": {}}, {}) is None


def test_qc_funnel_diff_flags_closing_only_difference():
    import checks as QC
    sc = lambda i, asset, text=None: {"id": f"s{i}", "layers": [{"type": "video", "source": {"kind": "footage", "asset": asset, "in_s": 0, "out_s": 2}}]
                                      + ([{"type": "text", "text": text}] if text else [])}
    tofu = {"scenes": [sc(1, "a1", "Hediye seçmek zor mu geliyor?"), sc(2, "a2"), sc(3, "a3", "Daha fazlası profilde")]}
    bofu_lazy = {"scenes": [sc(1, "a1", "Hediye seçmek zor mu geliyor?"), sc(2, "a2"), sc(3, "a3", "Hemen sipariş ver")]}
    bofu = {"scenes": [sc(1, "a9", "Görseldeki gibi mi geliyor?"), sc(2, "a2"), sc(3, "a3", "Hemen sipariş ver")]}
    r = QC.funnel_diff({"T": tofu, "B": bofu_lazy})
    assert not r["ok"] and "yalnız kapanışta" in r["warnings"][0]["why"]
    assert QC.funnel_diff({"T": tofu, "B": bofu})["ok"]  # aynı çekim (a2, a3) serbest, açılış farklı
    assert not QC.funnel_diff({"T": tofu, "T2": tofu})["ok"]
