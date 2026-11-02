"""2.5.0: metin aşamalarının taslak denetimi (KURALLAR K10) — rubrik, kayıtla tutarlılık, sunucu sayımlı en fazla 2 tur döngü."""
from __future__ import annotations

from pathlib import Path

import pytest

from admem import drafts as DR
from admem.util import AdMemoryError
from conftest import make_active_profile, stage_doc
from test_store_stage import advance_to

import draft_docs as DD

KEY = "MRK_K1_A_video_15_h1_novo_real_c1_r1"
RESERVE = "MRK_K1_A_video_15_h1_novo_real_c1_r2"


def campaign(s, result_type="purchase", budget_total=5000.0, lead_method=None, trial=False):
    a = make_active_profile(s)
    pid, prod = a["profile"]["id"], a["product"]["id"]
    r = s.campaign_create(pid, prod, "Kampanya 1", goal="satış", result_type=result_type, budget_total=budget_total,
                          budget_total_confirmed=True, lead_method=lead_method, trial=trial)
    cid, cyid = r["campaign"]["id"], r["cycle"]["id"]
    s.cycle_set(pid, cyid, adset_budget_daily=250)
    return pid, cid, cyid


def write(s, pid, cid, name, text):
    p = s.campaign_dir(pid, cid) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return str(p)


# ----------------------------------------------------------------------------- saf fonksiyonlar
def test_numbers_turkish_and_english():
    assert DR.has_number("Toplam 1.500 TL", 1500)
    assert DR.has_number("1.500,50 ₺", 1500.5)
    assert DR.has_number("1,500.50 USD", 1500.5)
    assert DR.has_number("günlük 250", 250)
    assert not DR.has_number("günlük 25", 250)
    assert DR.has_number("risk: 300 TRY — onay", 300)


def test_generic_rubric_catches_placeholder_todo_mojibake_and_empty():
    r = DR.check_document("# Başlık\n\nÜrün: {{ürün}} TODO", "S03")
    codes = {i["code"] for i in r["issues"]}
    assert {"placeholder", "todo"} <= codes and r["verdict"] == "fail"
    r = DR.check_document("# Ã–zet\n\nÃ§ok gÃ¼zel bir Ã¼rÃ¼n aÃ§Ä±klamasÄ±", "S03")
    assert any(i["code"] == "encoding" for i in r["issues"])
    assert DR.check_document("# x", "S03")["issues"][0]["code"] == "doc_too_short"
    assert DR.check_document("# Görüşme özeti\n\nKonsept A seçildi; hook h1 kabul edildi.", "S03")["verdict"] == "pass"


def test_template_sections_required_and_optional():
    tmd = (Path(DR.__file__).resolve().parents[3] / "templates" / "reports" / "brief.md").read_text(encoding="utf-8")
    heads = DR.template_headings(tmd)
    assert any("Toplam Meta harcama sınırı" in h for h in heads)
    doc = "# Brief — K · tur 1\n\n## Kampanya\n- Ürün: A\n\n## Varsayımlar ve açık sorular\n- yok\n"
    r = DR.check_document(doc, "S01", {"cycle_no": 1}, tmd)
    missing = [i for i in r["issues"] if i["code"] == "missing_section"]
    # Rakip bağlamı S01b'den sonra doldurulur: başlık yoksa yalnızca uyarı
    assert any("Rakip bağlamı" in i["message"] and i["severity"] == "warn" for i in missing)
    assert any("Ekonomi" in i["message"] and i["severity"] == "critical" for i in missing)


def test_cycle_number_in_title_must_match():
    tmd = "## Özet\n"
    r = DR.check_document("# Rakip analizi — K · tur 1\n\n## Özet\nPazarda iki rakip var.", "S01b", {"cycle_no": 2}, tmd)
    assert any(i["code"] == "cycle_mismatch" for i in r["issues"])


# ----------------------------------------------------------------------------- döngü ve aşama kapısı
def test_loop_rounds_counted_by_server_and_unchanged_recheck_is_not_a_round(store):
    pid, cid, cyid = campaign(store)
    store.stage_start(pid, "S01", cid, cyid)
    good = DD.write_stage_doc(store, pid, "S01", cid, cyid, check=False)
    bad = good["text"].replace("Reklam seti günlük bütçesi: 250", "Reklam seti günlük bütçesi: {{günlük_bütçe}}")
    Path(good["path"]).write_text(bad, encoding="utf-8")
    r1 = store.draft_check(pid, "S01", good["path"], cid, cyid)
    assert r1["verdict"] == "fail" and r1["round"] == 1 and not r1["final_round"]
    assert store.draft_check(pid, "S01", good["path"], cid, cyid)["round"] == 1  # değişmemiş içerik yeni tur değil
    with pytest.raises(AdMemoryError, match="taslak denetimi geçmedi"):
        store.stage_complete(pid, "S01", [{"path": good["path"]}], "brief", cid, cyid)
    Path(good["path"]).write_text(good["text"], encoding="utf-8")
    r2 = store.draft_check(pid, "S01", good["path"], cid, cyid)
    assert r2["verdict"] == "pass" and r2["round"] == 2
    out = store.stage_complete(pid, "S01", [{"path": good["path"]}], "brief", cid, cyid)
    assert out["status"] == "done" and "draft_remaining" not in out
    assert store.q1("SELECT COUNT(*) AS n FROM draft_checks WHERE consumed_by_run_id IS NULL")["n"] == 0


def test_change_after_check_is_rejected(store):
    pid, cid, cyid = campaign(store)
    store.stage_start(pid, "S01", cid, cyid)
    d = DD.write_stage_doc(store, pid, "S01", cid, cyid)
    assert d["check"]["verdict"] == "pass", d["check"]["issues"]
    Path(d["path"]).write_text(d["text"] + "\nSonradan eklenen satır.\n", encoding="utf-8")
    with pytest.raises(AdMemoryError, match="denetimden sonra değişti"):
        store.stage_complete(pid, "S01", [{"path": d["path"]}], "brief", cid, cyid)


def test_final_round_allows_completion_but_returns_remaining_and_gate_records_it(store):
    pid, cid, cyid = campaign(store)
    advance_to(store, pid, cid, cyid, "S02")
    store.cycle_set(pid, cyid, budget_plan_json={"allowed_test_ads": 3, "fits_total_budget": True, "daily_test_budget": 250},
                    test_days=7, cycle_days=14)  # risk sınırı onaylanmadı: belge bunu düzeltemez
    store.strategy_save(pid, cid, cyid, {"positioning": {"type": "gap"}, "portfolio": {"gap": 1, "free": 1}})
    store.stage_start(pid, "S02", cid, cyid)
    d = DD.write_stage_doc(store, pid, "S02", cid, cyid, exhaust=True)
    assert d["check"]["final_round"] and d["check"]["verdict"] == "fail"
    assert any(i["code"] == "risk_limit" for i in d["check"]["issues"])
    out = store.stage_complete(pid, "S02", [{"path": d["path"]}], "strateji", cid, cyid)
    assert out["status"] == "awaiting_gate" and out["draft_remaining"]
    # kalan sorun gizlenmez; kapıyı yine sunucunun S02 engeli tutar (risk sınırı yok)
    with pytest.raises(AdMemoryError, match="zarar-risk"):
        store.gate_approve(pid, out["stage_run"]["id"], out["stage_run"]["output_version"], "onaylıyorum", cycle_id=cyid)


def test_remaining_issue_count_written_to_decision_note(store):
    pid, cid, cyid = campaign(store)
    advance_to(store, pid, cid, cyid, "S03")
    store.taxonomy_value_add(pid, "buyer", "alici-a", "Örnek alıcı", status="active", user_said="bu alıcıya konuşalım")
    k = store.concept_upsert(pid, cid, cyid, "A", "Konsept A", "general", decision="accepted", user_said="A olsun",
                             features={"proof": "process", "first_frame": "product", "buyer": "alici-a"},
                             message={"stage": "mofu", "stage_basis": "assumption", "belief": "b", "focus": "desire",
                                      "evidence": [{"kind": "none"}], "expected_action": "incelemek"})
    store.hypothesis_add(pid, "A öndedir", "hook_rate", cid, cyid, concept_id=k["id"])
    store.hook_upsert(pid, k["id"], "h1", "product", "ürün masada", "yavaş itme", "kağıt sesi", "Örnek", decision="accepted", user_said="tamam")
    store.stage_start(pid, "S03", cid, cyid)
    f = write(store, pid, cid, "c1-gorusme-ozeti.md", "# Görüşme özeti — tur 1\n\nBugün konseptleri konuştuk, karar verildi.\n")
    assert store.draft_check(pid, "S03", f, cid, cyid)["verdict"] == "fail"  # seçilen konsept A özette yok
    Path(f).write_text("# Görüşme özeti — tur 1\n\nBugün konseptleri konuştuk, karar verildi ve not alındı.\n", encoding="utf-8")
    r2 = store.draft_check(pid, "S03", f, cid, cyid)
    assert r2["final_round"] and r2["verdict"] == "fail"
    out = store.stage_complete(pid, "S03", [{"path": f}], "özet", cid, cyid)
    store.gate_approve(pid, out["stage_run"]["id"], out["stage_run"]["output_version"], "olur", cycle_id=cyid)
    note = store.q1("SELECT note FROM decisions WHERE stage='S03' AND decision='approved'")["note"]
    assert "kalan taslak sorunu: 1" in note


def test_template_stage_requires_named_document(store):
    pid, cid, cyid = campaign(store)
    store.stage_start(pid, "S01", cid, cyid)
    f = write(store, pid, cid, "notlar.md", "# Notlar\n\nBu belge brief değildir ama uzunca bir metindir.\n")
    store.draft_check(pid, "S01", f, cid, cyid)
    with pytest.raises(AdMemoryError, match="c<tur>-brief.md"):
        store.stage_complete(pid, "S01", [{"path": f}], "brief", cid, cyid)


def test_new_version_starts_rounds_from_one(store):
    pid, cid, cyid = campaign(store)
    advance_to(store, pid, cid, cyid, "S03")
    store.stage_start(pid, "S03", cid, cyid)
    p = stage_doc(store, pid, cid, cyid, "S03")
    store.stage_complete(pid, "S03", [{"path": p}], "özet v1", cid, cyid)
    Path(p).write_text(Path(p).read_text(encoding="utf-8") + "\nKullanıcı değişiklik istedi.\n", encoding="utf-8")
    assert store.draft_check(pid, "S03", p, cid, cyid)["round"] == 1


def test_draft_check_refuses_other_stage_and_non_md(store):
    pid, cid, cyid = campaign(store)
    f = write(store, pid, cid, "c1-strategy.md", "# Strateji — tur 1\n\nmetin metin metin metin\n")
    with pytest.raises(AdMemoryError, match="S01 aşamasında"):
        store.draft_check(pid, "S02", f, cid, cyid)
    g = write(store, pid, cid, "hooks.csv", "a,b\n1,2\n")
    with pytest.raises(AdMemoryError, match=".md"):
        store.draft_check(pid, "S01", g, cid, cyid)
    with pytest.raises(AdMemoryError, match="metin aşamaları"):
        store.draft_check(pid, "S10", f, cid, cyid)


# ----------------------------------------------------------------------------- belge = kayıt (aşamaya özgü)
def test_s01_budget_result_type_and_economics_consistency(store):
    pid, cid, cyid = campaign(store, budget_total=5000)
    store.stage_start(pid, "S01", cid, cyid)
    d = DD.write_stage_doc(store, pid, "S01", cid, cyid)
    assert d["check"]["verdict"] == "pass", d["check"]["issues"]
    t = d["text"]
    def codes(text):
        Path(d["path"]).write_text(text, encoding="utf-8")
        return {i["code"] for i in store.draft_check(pid, "S01", d["path"], cid, cyid)["issues"] if i["severity"] == "critical"}
    assert "budget_total" in codes(t.replace("5.000", "6.000"))
    assert "result_type" in codes(t.replace("satış (purchase)", "mesaj (messaging)"))
    # şablondaki seçenek listesi parantezi kalsa da karar sayılmaz
    assert "result_type" in codes(t.replace("satış (purchase)", "(purchase · lead · messaging · profile_visit · link_click · engagement)"))
    assert "adset_budget_daily" in codes(t.replace("günlük bütçesi: 250", "günlük bütçesi: 300"))
    assert "economics_value" in codes(t.replace("Başa baş CPA: 40", "Başa baş CPA: 55"))


def test_s01_null_budget_unconfirmed_lead_and_trial(store):
    a = make_active_profile(store)
    pid, prod = a["profile"]["id"], a["product"]["id"]
    store.product_upsert(pid, "Ürün A", product_id=prod, economics_json={"contribution": None})
    r = store.campaign_create(pid, prod, "K", result_type="lead", lead_method="instant_form", budget_total=None)
    cid, cyid = r["campaign"]["id"], r["cycle"]["id"]
    store.cycle_set(pid, cyid, adset_budget_daily=100)
    store.stage_start(pid, "S01", cid, cyid)
    d = DD.write_stage_doc(store, pid, "S01", cid, cyid)
    crit = {i["code"] for i in d["check"]["issues"] if i["severity"] == "critical"}
    assert crit == {"budget_total"}  # NULL kararı teyit edilmedi
    store.campaign_update(pid, cid, budget_total=None, budget_total_confirmed=True)
    d = DD.write_stage_doc(store, pid, "S01", cid, cyid)
    assert d["check"]["verdict"] == "pass", d["check"]["issues"]
    Path(d["path"]).write_text(d["text"].replace("instant_form", "bilinmiyor"), encoding="utf-8")
    assert any(i["code"] == "lead_method" for i in store.draft_check(pid, "S01", d["path"], cid, cyid)["issues"])
    Path(d["path"]).write_text(d["text"].replace("VARSAYIM", "kesin").replace("bilinmiyor", "40"), encoding="utf-8")
    assert any(i["code"] == "economics_honesty" for i in store.draft_check(pid, "S01", d["path"], cid, cyid)["issues"])


def test_s02_plan_numbers_and_fit_statement(store):
    pid, cid, cyid = campaign(store)
    advance_to(store, pid, cid, cyid, "S02")
    rl = {"per_ad": {"amount": 300, "currency": "TRY", "scope": "ad_launch_to_stop", "approved_at": "x", "note": "n"}, "mapping": {}}
    store.cycle_set(pid, cyid, budget_plan_json={"allowed_test_ads": 4, "fits_total_budget": False, "daily_test_budget": 250,
                                                 "creative_test_tool_max": 7}, test_days=7, cycle_days=14, risk_limits_json=rl)
    store.stage_start(pid, "S02", cid, cyid)
    d = DD.write_stage_doc(store, pid, "S02", cid, cyid)
    assert d["check"]["verdict"] == "pass", d["check"]["issues"]
    def codes(text):
        Path(d["path"]).write_text(text, encoding="utf-8")
        return {i["code"] for i in store.draft_check(pid, "S02", d["path"], cid, cyid)["issues"] if i["severity"] == "critical"}
    assert "allowed_test_ads" in codes(d["text"].replace("| 4 (araç sınırı 7) |", "| 6 (araç sınırı 7) |"))
    # parantezdeki araç sınırı izin verilen sayı sanılmaz
    assert "allowed_test_ads" in codes(d["text"].replace("| 4 (araç sınırı 7) |", "| (araç sınırı 4) |"))
    assert "fits_total" in codes(d["text"].replace("sığıyor mu: hayır", "sığıyor mu: evet"))
    assert "risk_limit" in codes(d["text"].replace("| 300 TRY — onay", "| 350 TRY — onay"))


def test_s14_upload_list_reserve_ai_enhancements_lead(store):
    pid, cid, cyid = campaign(store, result_type="lead", lead_method="instant_form")
    advance_to(store, pid, cid, cyid, "S14")
    store.ex("UPDATE campaigns SET test_structure='creative_test' WHERE id=?", (cid,))
    out = store.campaign_dir(pid, cid) / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{KEY}_916.mp4").write_bytes(b"\x00" * 64)
    (out / f"{RESERVE}_916.mp4").write_bytes(b"\x01" * 64)
    t = store.creative_register(pid, cid, cyid, str(out / f"{KEY}_916.mp4"), "test", ai_share=0.3)
    store.creative_register(pid, cid, cyid, str(out / f"{RESERVE}_916.mp4"), "reserve")
    store.creative_set_qc(pid, cid, [t["id"]], "passed", "qc.md")
    rl = store.q1("SELECT risk_limits_json FROM cycles WHERE id=?", (cyid,))["risk_limits_json"]
    rl["mapping"] = {KEY: {"amount": 500}}
    store.cycle_set(pid, cyid, risk_limits_json=rl)
    store.stage_start(pid, "S14", cid, cyid)
    d = DD.write_stage_doc(store, pid, "S14", cid, cyid)
    assert d["check"]["verdict"] == "pass", d["check"]["issues"]
    def codes(text):
        Path(d["path"]).write_text(text, encoding="utf-8")
        return {i["code"] for i in store.draft_check(pid, "S14", d["path"], cid, cyid)["issues"] if i["severity"] == "critical"}
    row = next(ln for ln in d["text"].splitlines() if ln.startswith(f"| {KEY}"))
    assert "reserve_in_upload" in codes(d["text"].replace(row, row + "\n" + row.replace(KEY, RESERVE)))
    assert "upload_list" in codes(d["text"].replace(row, "| - | - | - | - | - | - |"))
    assert "ai_disclosure" in codes(d["text"].replace("AI içeren varyasyonlar için Ads Manager'ın AI etiketi açılır.", "yok"))
    assert "enhancements" in codes(d["text"].replace("iyileştirmelerini KAPAT", "iyileştirmeleri açık kalsın"))
    assert "privacy_policy" in codes(d["text"].replace("Formda gizlilik politikası bağlantısı verilir.", ""))
    # Meta reklam standartları metin taraması aynı kodla (uyarı)
    r = store.draft_check(pid, "S14", write(store, pid, cid, "c1-yayin-paketi.md",
                                            d["text"].replace("Örnek başlık ve örnek açıklama.", "Kilonu 7 günde garantili ver!")), cid, cyid)
    assert any(i["code"] == "meta_text" for i in r["issues"])


def test_s01b_weak_coverage_label(store):
    pid, cid, cyid = campaign(store)
    store.ex("UPDATE campaigns SET stage='S01b' WHERE id=?", (cid,))
    sid = store.ex("""INSERT INTO competitor_snapshots(profile_id,campaign_id,cycle_id,mode,fetched_at,n_ads,coverage_json,source,sha256)
                      VALUES(?,?,?,'full','2026-03-02T09:00:00Z',3,'{"n_concepts": 3, "weak_coverage": true}','synthetic','abcdef0123456789')""",
                   (pid, cid, cyid)).lastrowid
    store.stage_start(pid, "S01b", cid, cyid)
    d = DD.write_stage_doc(store, pid, "S01b", cid, cyid)
    assert d["check"]["verdict"] == "pass", d["check"]["issues"]
    Path(d["path"]).write_text(d["text"].replace(" [zayıf kapsam]", ""), encoding="utf-8")
    assert "weak_coverage" in {i["code"] for i in store.draft_check(pid, "S01b", d["path"], cid, cyid)["issues"]}
    Path(d["path"]).write_text(d["text"].replace(f"#{sid}", "#999"), encoding="utf-8")
    assert "snapshot" in {i["code"] for i in store.draft_check(pid, "S01b", d["path"], cid, cyid)["issues"]}


def test_skills_tell_model_to_run_draft_check_before_stage_complete():
    root = Path(DR.__file__).resolve().parents[3]
    from admem import stages as ST
    for st in DR.DRAFT_STAGES:
        skill = ST.SKILLS[st]
        text = (root / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
        assert "draft_check" in text, f"{skill} skill'i taslak denetimini söylemiyor"
