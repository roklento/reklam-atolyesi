"""2.5.0: senaryo matrisi (evals/senaryo-matrisi.json) — her ürün türü × her kullanıcı profili gerçek aşama makinesiyle yürütülür.

Her birleşimde: profil ve ürün tanışması → S01 brief → S01b → S02 bütçe planı (scripts/analytics/budget.py) + risk sınırı + strateji →
S03…S13 → S14 yayın paketi → yayın kaydı. Beklenen sonuçlar matristen okunur (kodun kendisinden türetilmez):
  * kayıtlardan üretilen belge her metin aşamasında İLK turda taslak denetiminden geçer (yanlış alarm yok);
  * belgedeki bir sayı kayıttan saptırılınca denetim kritik sorun bulur (kaçırma yok);
  * S02 kapısı matrisin beklediği nedenle açılır ya da kapanır (bütçe yetmiyor, toplam sınır, zararına ürün);
  * ajans kullanıcısında başka profilin belgesi denetlenemez; risk sınırı hesabın para biriminde olmalıdır.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import pytest

import budget as BU
import draft_docs as DD
from admem import drafts as DR
from admem.util import AdMemoryError

ROOT = Path(__file__).resolve().parents[1]
MATRIX = json.loads((ROOT / "evals" / "senaryo-matrisi.json").read_text(encoding="utf-8"))
PRODUCTS, USERS = MATRIX["products"], MATRIX["users"]
COMBOS = [(p, u) for p in PRODUCTS for u in USERS]
LAUNCH = "2026-03-10"


def TM(stage: str) -> str:
    """Aşama şablonu: aşamaya özgü denetimler yalnızca şablona bağlı (adı şablona uyan) belgede çalışır."""
    return (ROOT / "templates" / "reports" / DR.TEMPLATES[stage][0]).read_text(encoding="utf-8")


def _money(v, fx):
    return None if v is None else round(float(v) * fx, 2)


def _economics(spec: dict, fx: float) -> dict:
    eco = {}
    for k, v in (spec.get("economics") or {}).items():
        if k in ("contribution", "contribution_low", "contribution_high", "net_basket"):
            eco[k] = _money(v, fx)
        elif k == "variable_costs":
            eco[k] = {kk: _money(vv, fx) for kk, vv in v.items()}
        else:
            eco[k] = v
    return eco


def build_profile(s, user: dict, product: dict, n: int = 1) -> dict:
    fx = user["fx"]
    p = s.profile_create(f"Marka {n}")
    s.brand_upsert(p["id"], name=f"Marka {n}", meta_ad_account_id=f"act_{n}", timezone="Europe/Istanbul", tone="nötr")
    s.profile_update(p["id"], meta_data_mode=user["mode"], history_status="no_history")
    if product["result_type"] == "purchase":
        src = "csv" if user["mode"] == "csv" else "meta_mcp"
        s.meta_signal_set(p["id"], "purchase_seen", src, "sentetik veri kümesi: Purchase son 7 gün")
    s.stage_start(p["id"], "S00a")
    r = s.stage_complete(p["id"], "S00a", [{"path": DD.write_stage_doc(s, p["id"], "S00a")["path"]}], "marka tanışması")
    s.gate_approve(p["id"], r["stage_run"]["id"], r["stage_run"]["output_version"], "onaylıyorum")
    s.profile_update(p["id"], status="active")
    prod = s.product_upsert(p["id"], f"Ürün {n}", price=_money(product["price"], fx), currency=user["currency"],
                            economics_json=_economics(product, fx),
                            provable_claims_json=[{"code": "c1", "text": "Örnek iddia", "proof_type": "process", "documented": True}],
                            occasions_json=[{"code": "an-a", "label": "Örnek an"}],
                            buyers_json=[{"code": "alici-a", "label": "Örnek alıcı"}])
    sk = f"product:{prod['id']}"
    d = DD.write_stage_doc(s, p["id"], "S00c", scope_key=sk)
    assert d["check"]["verdict"] == "pass", d["check"]["issues"]
    r = s.stage_complete(p["id"], "S00c", [{"path": d["path"]}], "ürün tanışması", scope_key=sk)
    s.gate_approve(p["id"], r["stage_run"]["id"], r["stage_run"]["output_version"], "evet onaylıyorum")
    camp = s.campaign_create(p["id"], prod["id"], f"Kampanya {n}", goal="sonuç", result_type=product["result_type"],
                             budget_total=_money(user["budget_total"], 1), budget_total_confirmed=True,
                             lead_method=product.get("lead_method"))
    cid, cyid = camp["campaign"]["id"], camp["cycle"]["id"]
    if product.get("season"):
        s.campaign_update(p["id"], cid, season=product["season"])
    s.cycle_set(p["id"], cyid, adset_budget_daily=user["adset_daily"])
    return {"pid": p["id"], "prod": prod["id"], "cid": cid, "cyid": cyid}


def doc_round1(s, pid, cid, cyid, stage) -> dict:
    """Kayıtlardan üretilen belge ilk turda geçmeli: geçmezse denetim ürün/kullanıcı türüne göre yanlış alarm veriyordur."""
    d = DD.write_stage_doc(s, pid, stage, cid, cyid)
    chk = d["check"]
    assert chk["round"] == 1 and chk["verdict"] == "pass", (stage, [i for i in chk["issues"] if i["severity"] == "critical"])
    return d


def complete(s, pid, cid, cyid, stage, path) -> dict:
    r = s.stage_complete(pid, stage, [{"path": path}], f"{stage} tamam", cid, cyid)
    assert r["status"] in ("awaiting_gate", "done"), r
    assert not r.get("draft_remaining"), r.get("draft_remaining")
    return r


def approve(s, pid, cyid, r, text="onaylıyorum"):
    if r["status"] == "done":  # kapısız aşama
        return r
    return s.gate_approve(pid, r["stage_run"]["id"], r["stage_run"]["output_version"], text, cycle_id=cyid)


def mutate_number(text: str, line_label: str, value: float) -> str:
    """Belgede `line_label` satırındaki kayıtlı sayıyı farklı bir sayıyla değiştirir (denetim bunu kaçırmamalı)."""
    out = []
    hit = False
    for line in text.splitlines():
        if not hit and DR.fold(line_label) in DR.fold(line) and DR.has_number(line, value):
            line = re.sub(r"\d[\d.,]*", "987654", line)
            hit = True
        out.append(line)
    assert hit, f"{line_label} satırı belgede yok"
    return "\n".join(out) + "\n"


def budget_input(user: dict, eco: dict, product: dict, cycle_no: int = 1) -> dict:
    inp = {"cycle_no": cycle_no, "adset_daily": user["adset_daily"], "cpm": user["cpm"], "cpm_source": user["cpm_source"],
           "decision_metric": user["decision_metric"], "budget_total": user["budget_total"], "spend_to_date": 0,
           "launch_at": LAUNCH, "risk_per_ad": user["risk_per_ad"], "result_type": product["result_type"]}
    if product["result_type"] == "purchase" and eco.get("status") == "exact":
        inp["target_cpa"] = eco.get("target_cpa")
    if product["result_type"] == "lead" and eco.get("target_cpl"):
        inp["target_cpl"] = eco["target_cpl"]
    if cycle_no > 1:
        inp["exploration_share"] = (user.get("cycle2") or {}).get("exploration_share", 0.2)
    return inp


def run_s02(s, ids, user, product, ack: bool) -> tuple[dict, dict]:
    pid, cid, cyid = ids["pid"], ids["cid"], ids["cyid"]
    eco = s.economics(s._product(pid, ids["prod"]))
    plan = BU.plan(budget_input(user, eco, product))
    s.cycle_set(pid, cyid, budget_plan_json=plan, test_days=plan.get("test_days"), cycle_days=plan.get("cycle_days"),
                risk_limits_json={"per_ad": {"amount": user["risk_per_ad"], "currency": user["currency"], "scope": "ad_launch_to_stop",
                                             "approved_at": "2026-03-02T09:00:00Z", "note": "kullanıcı onayı"}, "mapping": {}})
    n = int(plan.get("allowed_test_ads") or 0)
    strategy = {"positioning": {"type": "gap", "statement": "örnek"}, "portfolio": ({"gap": 1, "free": 1} if n >= 2 else {})}
    if ack:
        strategy["loss_acknowledged"] = "biliyorum, ilk müşteriler için zararına sürdürüyorum"
    s.strategy_save(pid, cid, cyid, strategy)
    s.stage_start(pid, "S02", cid, cyid)
    d = doc_round1(s, pid, cid, cyid, "S02")
    return plan, complete(s, pid, cid, cyid, "S02", d["path"])


def to_s14(s, pid, cid, cyid):
    """S03…S13: konsept/hook kaydı, çekim, kreatif üretimi. Metin aşamaları ilk turda geçmeli."""
    for _ in range(30):
        st = s.q1("SELECT stage FROM campaigns WHERE id=?", (cid,))["stage"]
        if st == "S14":
            return
        if st == "W":
            raw = s.campaign_dir(pid, cid) / "footage" / "raw" / "S01_t1.mov"
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_bytes(b"x" * 100)
            old = time.time() - 600
            os.utime(raw, (old, old))
            s.shoot_mark_done(pid, cid, cyid)
            continue
        if st == "S03":
            s.taxonomy_value_add(pid, "buyer", "alici-a", "Örnek alıcı", status="active", user_said="bu alıcıya konuşalım")
            k = s.concept_upsert(pid, cid, cyid, "A", "Konsept A", "general", decision="accepted", user_said="A olsun",
                                 features={"proof": "process", "first_frame": "product", "buyer": "alici-a"},
                                 message={"stage": "mofu", "stage_basis": "assumption", "belief": "örnek düşünce",
                                          "focus": "desire", "evidence": [{"kind": "none"}], "expected_action": "ürün sayfasını incelemek"})
            s.hypothesis_add(pid, "A konsepti hook oranında öndedir", "hook_rate", cid, cyid, concept_id=k["id"])
            s.hook_upsert(pid, k["id"], "h1", "product", "ürün masada", "yavaş itme", "kağıt sesi", "Örnek metin", decision="accepted",
                          user_said="h1 tamam")
        s.stage_start(pid, st, cid, cyid)
        if st in DR.DRAFT_STAGES:
            path = doc_round1(s, pid, cid, cyid, st)["path"]
        else:
            f = s.campaign_dir(pid, cid) / f"out_{st}.md"
            f.write_text(f"{st} çıktısı", encoding="utf-8")
            path = str(f)
        r = s.stage_complete(pid, st, [{"path": path}], f"{st} tamam", cid, cyid)
        if r["status"] == "awaiting_gate":
            approve(s, pid, cyid, r)
    raise AssertionError("S14'e ulaşılamadı")


@pytest.mark.parametrize("pk,uk", COMBOS, ids=[f"{p}-{u}" for p, u in COMBOS])
def test_scenario_matrix(store, pk, uk):
    s, product, user = store, PRODUCTS[pk], USERS[uk]
    ids = build_profile(s, user, product)
    pid, cid, cyid = ids["pid"], ids["cid"], ids["cyid"]
    eco = s.economics(s._product(pid, ids["prod"]))
    exp_eco = (product.get("expect") or {}).get("economics_status")
    if exp_eco:
        assert eco["status"] == exp_eco

    # --- S01: kayıtlardan üretilen brief ilk turda geçer; saptırılan günlük bütçe yakalanır
    s.stage_start(pid, "S01", cid, cyid)
    d = doc_round1(s, pid, cid, cyid, "S01")
    bad = mutate_number(d["text"], "günlük bütçe", user["adset_daily"])
    ctx = s._draft_ctx(pid, "S01", cid, cyid)
    res = DR.check_document(bad, "S01", ctx, TM("S01"))
    assert any(i["code"] == "adset_budget_daily" and i["severity"] == "critical" for i in res["issues"])
    if product["result_type"] == "lead":  # aday maliyeti kayıttan saptırılırsa yakalanır
        assert eco.get("breakeven_cpl") is not None
        bad = mutate_number(d["text"], "başa baş aday maliyeti", eco["breakeven_cpl"])
        res = DR.check_document(bad, "S01", ctx, TM("S01"))
        assert any(i["code"] == "economics_value" for i in res["issues"])
    if product.get("season"):
        res = DR.check_document(d["text"].replace(product["season"], "yok"), "S01", ctx, TM("S01"))
        assert any(i["code"] == "season" for i in res["issues"])
    if eco.get("status") in ("unknown", "range", "non_positive"):  # dürüstlük etiketi silinirse yakalanır
        stripped = re.sub(r"(?im)^- VARSAYIM.*$", "", d["text"])
        stripped = re.sub(r"(?i)aralık|bilinmiyor|zarar|≤ 0", "x", stripped)
        res = DR.check_document(stripped, "S01", ctx, TM("S01"))
        assert any(i["code"] == "economics_honesty" for i in res["issues"]), res["issues"]
    approve(s, pid, cyid, complete(s, pid, cid, cyid, "S01", d["path"]))

    # --- S01b
    s.stage_start(pid, "S01b", cid, cyid)
    approve(s, pid, cyid, complete(s, pid, cid, cyid, "S01b", doc_round1(s, pid, cid, cyid, "S01b")["path"]))

    # --- S02: matrisin beklediği kapı sonucu
    loss = eco.get("status") == "non_positive" and product["result_type"] in ("purchase", "lead")
    plan, r = run_s02(s, ids, user, product, ack=False)
    expected = user["expect"]["s02"]
    reasons = [] if expected == "pass" else [MATRIX["blockers"][expected]]
    if loss:
        reasons.append(MATRIX["blockers"]["blocked_loss"])
    if expected == "blocked_two_ads":
        assert plan["production_blocked"] is True and plan["allowed_test_ads"] < 2
    if expected == "blocked_total":
        assert plan["fits_total_budget"] is False and plan["total_shortfall"] > 0
    if expected == "pass":
        assert plan["production_blocked"] is False and plan["fits_total_budget"] in (True, None)
    if reasons:
        with pytest.raises(AdMemoryError) as e:
            approve(s, pid, cyid, r)
        for why in reasons:
            assert why in str(e.value), (why, str(e.value))
        if expected != "pass":
            return  # bütçe kullanıcıyla yeniden konuşulur; üretim başlamaz (K09)
        # zararına ürün: kullanıcı bilerek sürdürürse ifadesiyle kaydedilir ve kapı açılır
        with pytest.raises(AdMemoryError):
            s.strategy_save(pid, cid, cyid, {"positioning": {"type": "gap", "statement": "örnek"}, "loss_acknowledged": "  "})
        plan, r = run_s02(s, ids, user, product, ack=True)
    # saptırılan test reklamı sayısı yakalanır
    d2 = DD.write_stage_doc(s, pid, "S02", cid, cyid, check=False)
    ctx2 = s._draft_ctx(pid, "S02", cid, cyid)
    res = DR.check_document(mutate_number(d2["text"], "test reklamı sayısı", plan["allowed_test_ads"]), "S02", ctx2, TM("S02"))
    assert any(i["code"] == "allowed_test_ads" for i in res["issues"])
    approve(s, pid, cyid, r)

    # --- S03…S13
    to_s14(s, pid, cid, cyid)

    # --- S14: test kreatifi, risk eşlemesi, paket belgesi
    key = "MRK_K1_A_video_15_h1_novo_real_c1_r1"
    f = s.campaign_dir(pid, cid) / "out" / f"{key}_916.mp4"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"\x00" * 64)
    cr = s.creative_register(pid, cid, cyid, str(f), "test")
    s.creative_set_qc(pid, cid, [cr["id"]], "passed", "qc.md")
    rl = s.q1("SELECT risk_limits_json FROM cycles WHERE id=?", (cyid,))["risk_limits_json"]
    rl["mapping"] = {key: {"amount": user["risk_per_ad"]}}
    s.cycle_set(pid, cyid, risk_limits_json=rl)
    s.stage_start(pid, "S14", cid, cyid)
    d14 = doc_round1(s, pid, cid, cyid, "S14")
    if product["result_type"] == "lead":
        ctx14 = s._draft_ctx(pid, "S14", cid, cyid)
        res = DR.check_document(d14["text"].replace("gizlilik", "x"), "S14", ctx14, TM("S14"))
        assert any(i["severity"] == "critical" for i in res["issues"])
    r = complete(s, pid, cid, cyid, "S14", d14["path"])
    run = approve(s, pid, cyid, r)
    assert s.q1("SELECT stage FROM campaigns WHERE id=?", (cid,))["stage"] == "S14"  # paket onayı yayın değildir (K03)
    res = s.launch_confirm(pid, cid, cyid, r["stage_run"]["id"], r["stage_run"]["output_version"],
                           [{"meta_ad_id": "111", "creative_key": key}], "2026-03-10T00:00:00+03:00", "yayına aldım")
    assert res["launched"] and s.q1("SELECT stage FROM campaigns WHERE id=?", (cid,))["stage"] == "S15"
    assert run is not None

    # --- ajans: ikinci profil; belgeler ve kayıtlar karışmaz (K06)
    if user.get("agency"):
        other = build_profile(s, user, product, n=2)
        s.stage_start(other["pid"], "S01", other["cid"], other["cyid"])
        foreign = DD.write_stage_doc(s, pid, "S14", cid, cyid, check=False)["path"]
        with pytest.raises(AdMemoryError):
            s.draft_check(other["pid"], "S01", foreign, other["cid"], other["cyid"])
        with pytest.raises(AdMemoryError):
            s.draft_check(other["pid"], "S01", DD.doc_path(s, other["pid"], "S01", other["cid"], 1, None).as_posix(), cid, cyid)
        doc_round1(s, other["pid"], other["cid"], other["cyid"], "S01")


@pytest.mark.parametrize("uk", [u for u in USERS if USERS[u].get("cycle2")])
def test_cycle2_creative_test_structure(uk):
    """İkinci turda keşif payıyla kreatif test yapısı; S14'te Advantage+ iyileştirmeleri kapatılmalı (K10 denetimi)."""
    user = USERS[uk]
    plan = BU.plan(budget_input(user, {}, {"result_type": "purchase"}, cycle_no=2))
    assert plan["structure"] == user["cycle2"]["expect_structure"]
    assert plan["daily_test_budget"] == pytest.approx(user["adset_daily"] * user["cycle2"]["exploration_share"])
    assert 2 <= plan["allowed_test_ads"] <= BU.CREATIVE_TEST_TOOL_MAX
    ctx = {"cycle_no": 2, "structure": "creative_test", "campaign": {"result_type": "purchase", "budget_total": user["budget_total"]},
           "risk_limits": {"per_ad": {"amount": user["risk_per_ad"]}, "mapping": {"K": {"amount": user["risk_per_ad"]}}},
           "product": {"currency": user["currency"]}, "test_keys": ["K"], "reserve_only_keys": [], "test_keys_not_passed": [],
           "has_ai": False, "meta_text_warnings": []}
    text = DD.render_s14(ctx)
    assert DR.check_document(text, "S14", ctx, TM("S14"))["verdict"] == "pass"
    res = DR.check_document(text.replace("KAPAT", "aç"), "S14", ctx, TM("S14"))
    assert res["verdict"] == "fail"


def test_currency_mismatch_blocks_s02(store):
    """USD hesapta TRY ile onaylanmış risk sınırı kapıyı açmaz (para birimi karışmaz)."""
    user, product = USERS["U6"], PRODUCTS["P1"]
    ids = build_profile(store, user, product)
    pid, cid, cyid = ids["pid"], ids["cid"], ids["cyid"]
    store.campaign_update(pid, cid, budget_total_confirmed=True)
    for st in ("S01", "S01b"):
        store.stage_start(pid, st, cid, cyid)
        approve(store, pid, cyid, complete(store, pid, cid, cyid, st, doc_round1(store, pid, cid, cyid, st)["path"]))
    plan, r = run_s02(store, ids, user, product, ack=False)
    rl = store.q1("SELECT risk_limits_json FROM cycles WHERE id=?", (cyid,))["risk_limits_json"]
    rl["per_ad"]["currency"] = "TRY"
    store.cycle_set(pid, cyid, risk_limits_json=rl)
    with pytest.raises(AdMemoryError, match="para birimi"):
        approve(store, pid, cyid, r)


@pytest.mark.parametrize("bad", [{"cpm": 0}, {"cpm": -5}, {"cpm": float("nan")}, {"adset_daily": "abc"}, {"risk_per_ad": 0},
                                 {"decision_metric": "roas"}, {"cycle_no": 0}])
def test_budget_rejects_invalid_inputs(bad):
    inp = {"cycle_no": 1, "adset_daily": 100, "cpm": 50, "launch_at": LAUNCH, **bad}
    with pytest.raises(SystemExit):
        BU.plan(inp)


def test_budget_non_positive_daily_is_blocked_with_warnings():
    out = BU.plan({"cycle_no": 1, "adset_daily": 0, "cpm": 50})
    assert out["production_blocked"] is True and out["allowed_test_ads"] == 0 and out["warnings"]


def test_daily_budget_must_be_positive(store):
    ids = build_profile(store, USERS["U1"], PRODUCTS["P1"])
    for v in (0, -10, float("inf"), "x"):
        with pytest.raises(AdMemoryError):
            store.cycle_set(ids["pid"], ids["cyid"], adset_budget_daily=v)


def test_matrix_and_eval_cases_are_consistent():
    """Matris ve değerlendirme vakaları birbirine bağlı: her vaka geçerli ürün/kullanıcıya ve rubrik ölçütüne dayanır, her
    vakanın dosyaları vardır; her ürün ve kullanıcı en az bir birleşimde pytest ile yürür (COMBOS tam çarpımdır)."""
    rubric = (ROOT / "evals" / "rubrik.md").read_text(encoding="utf-8")
    codes = set(re.findall(r"^## (R\d+)\b", rubric, re.M))
    assert codes, "rubrikte ölçüt yok"
    for name, case in MATRIX["eval_cases"].items():
        assert case["product"] in PRODUCTS and case["user"] in USERS, name
        assert set(case["rubric"]) <= codes, (name, case["rubric"])
        d = ROOT / "evals" / "vakalar" / name
        assert (d / "prompt.md").exists(), name
        graders = sorted((d / "graders").glob("*.md"))
        assert graders, name
        for g in graders:
            head = g.read_text(encoding="utf-8").split("---")[1]
            assert "type: llm" in head and "weight:" in head, g
        used = {m for g in graders for m in re.findall(r"\bR\d+\b", g.read_text(encoding="utf-8"))}
        assert set(case["rubric"]) <= used, (name, "rubrik ölçütü grader'da yok")
    on_disk = {p.name for p in (ROOT / "evals" / "vakalar").iterdir() if p.is_dir()}
    assert on_disk == set(MATRIX["eval_cases"]), on_disk ^ set(MATRIX["eval_cases"])
    assert len(COMBOS) == len(PRODUCTS) * len(USERS)
