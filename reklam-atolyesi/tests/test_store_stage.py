"""Aşama makinesi, profil yalıtımı, kapılar, tur ve yayın kaydı (spec 2.3, 4.1–4.4, 7.4, 12.12 adım 1–2, 7)."""
from __future__ import annotations

import json

import pytest

from admem.util import AdMemoryError
from conftest import make_active_profile, out_file


def advance_to(s, pid, cid, cyid, target, gate_text="onaylıyorum"):
    """Yardımcı: mevcut aşamadan hedefe kadar çıktı yazıp kapıları geçer (kapılar testte otomatik onaylanır; 12.12 adım 2)."""
    for _ in range(40):
        c = s.q1("SELECT * FROM campaigns WHERE id=?", (cid,))
        st = c["stage"]
        if st == target:
            return c
        if st == "W":
            raw = s.campaign_dir(pid, cid) / "footage" / "raw" / "S01_t1.mov"
            raw.write_bytes(b"x" * 100)
            import os, time
            old = time.time() - 600
            os.utime(raw, (old, old))
            s.shoot_mark_done(pid, cid, cyid)
            continue
        if st == "S02":
            s.cycle_set(pid, cyid, budget_plan_json={"allowed_test_ads": 3, "fits_total_budget": True}, test_days=7, cycle_days=14,
                        risk_limits_json={"per_ad": {"amount": 500, "currency": "TRY", "scope": "ad_launch_to_stop", "approved_at": "2026-03-02T09:00:00Z", "note": "test"}, "mapping": {}})
            s.strategy_save(pid, cid, cyid, {"positioning": {"type": "gap", "line": "örnek"}, "portfolio": {"proven": 1, "gap": 1, "free": 1}})
        if st == "S03":
            k = s.concept_upsert(pid, cid, cyid, "A", "Konsept A", "general", decision="accepted", user_said="A olsun",
                                 features={"proof": "process", "first_frame": "product"})
            h = s.hypothesis_add(pid, "A konsepti hook oranında öndedir", "hook_rate", cid, cyid, concept_id=k["id"])
            s.hook_upsert(pid, k["id"], "h1", "product", "ürün masada", "yavaş itme", "kağıt sesi", "Örnek metin", decision="accepted", user_said="h1 tamam")
        if st == "S13":
            for cr in s.qa("SELECT id FROM creatives WHERE cycle_id=?", (cyid,)):
                s.creative_set_qc(pid, cid, [cr["id"]], "passed", "rapor.md")
        if st == "S14":
            return c
        if st == "S15":
            return c
        s.stage_start(pid, st, cid, cyid)
        f = out_file(s, pid, cid, f"out_{st}.md", f"{st} çıktısı")
        r = s.stage_complete(pid, st, [{"path": f}], f"{st} tamam", cid, cyid)
        if r["status"] == "awaiting_gate":
            s.gate_approve(pid, r["stage_run"]["id"], r["stage_run"]["output_version"], gate_text, cycle_id=cyid)
    raise AssertionError("hedefe ulaşılamadı")


def new_campaign(s, mode="full"):
    a = make_active_profile(s)
    pid, prod = a["profile"]["id"], a["product"]["id"]
    r = s.campaign_create(pid, prod, "Kampanya 1", goal="satış", result_type="purchase", budget_total=None, mode=mode)
    return pid, r["campaign"]["id"], r["cycle"]["id"]


def test_profile_count_and_isolation(store):
    assert store.profile_list()["count"] == 0
    a = make_active_profile(store, "Marka A", "act_1", "Ürün A")
    assert store.profile_list()["count"] == 1
    b = make_active_profile(store, "Marka B", "act_2", "Ürün B")
    with pytest.raises(AdMemoryError):
        store.brand_upsert(b["profile"]["id"], meta_ad_account_id="act_1")  # aynı hesap iki profile bağlanamaz
    with pytest.raises(AdMemoryError):
        store._product(b["profile"]["id"], a["product"]["id"])  # başka profilin ürünü
    with pytest.raises(AdMemoryError):
        store.memory_card(None)


def test_explicit_profile_required(store):
    with pytest.raises(AdMemoryError):
        store.campaign_list(None)


def test_activation_requires_onboarding(store):
    p = store.profile_create("Marka C")
    store.brand_upsert(p["id"], name="Marka C", meta_ad_account_id="act_c")
    with pytest.raises(AdMemoryError):
        store.profile_update(p["id"], status="active")


def test_campaign_requires_product_onboarding(store):
    a = make_active_profile(store)
    pid = a["profile"]["id"]
    raw = store.product_upsert(pid, "Ürün Z", price=10, currency="TRY")
    with pytest.raises(AdMemoryError):
        store.campaign_create(pid, raw["id"], "K")
    r = store.campaign_create(pid, raw["id"], "Deneme", trial=True)
    assert r["trial_note"] and "VARSAYIMSAL" in r["trial_note"]


def test_empty_output_not_complete(store):
    pid, cid, cyid = new_campaign(store)
    with pytest.raises(AdMemoryError):
        store.stage_complete(pid, "S01", [], "boş", cid, cyid)
    with pytest.raises(AdMemoryError):
        store.stage_complete(pid, "S01", [{"path": str(store.campaign_dir(pid, cid) / "yok.md")}], "yok", cid, cyid)


def test_full_machine_s01_to_s15(store):
    pid, cid, cyid = new_campaign(store)
    c = advance_to(store, pid, cid, cyid, "S14")
    assert c["stage"] == "S14"
    # S14 paketini hazırla: test kreatifi + risk eşlemesi
    key = "MRK_K1_A_video_15_h1_novo_real_c1_r1"
    f = store.campaign_dir(pid, cid) / "out" / f"{key}_916.mp4"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"\x00" * 64)
    cr = store.creative_register(pid, cid, cyid, str(f), "test")
    store.creative_set_qc(pid, cid, [cr["id"]], "passed", "qc.md")
    cy = store.q1("SELECT risk_limits_json FROM cycles WHERE id=?", (cyid,))
    rl = cy["risk_limits_json"]
    rl["mapping"] = {key: {"amount": 500}}
    store.cycle_set(pid, cyid, risk_limits_json=rl)
    store.stage_start(pid, "S14", cid, cyid)
    r = store.stage_complete(pid, "S14", [{"path": out_file(store, pid, cid, "paket.md")}], "paket", cid, cyid)
    run = r["stage_run"]
    store.gate_approve(pid, run["id"], run["output_version"], "paket onaylı", cycle_id=cyid)
    # paket onayı yayın sayılmaz: S15'e geçmez
    assert store.q1("SELECT stage FROM campaigns WHERE id=?", (cid,))["stage"] == "S14"
    with pytest.raises(AdMemoryError):
        store.stage_complete(pid, "S15", [{"path": out_file(store, pid, cid, "x.md")}], "x", cid, cyid)
    res = store.launch_confirm(pid, cid, cyid, run["id"], run["output_version"], [{"meta_ad_id": "111", "creative_key": key}],
                               "2026-03-05T00:00:00+03:00", "yayına aldım")
    assert res["launched"]
    assert store.q1("SELECT stage FROM campaigns WHERE id=?", (cid,))["stage"] == "S15"
    # yayından sonra S14 ve öncesine dönülmez
    with pytest.raises(AdMemoryError):
        store.stage_back(pid, cid, cyid, "S10", "değişiklik")


def test_gate_bound_to_version_and_cycle(store):
    pid, cid, cyid = new_campaign(store)
    advance_to(store, pid, cid, cyid, "S02")
    store.cycle_set(pid, cyid, budget_plan_json={"allowed_test_ads": 3, "fits_total_budget": True}, test_days=7, cycle_days=14,
                    risk_limits_json={"per_ad": {"amount": 500, "currency": "TRY", "scope": "ad_launch_to_stop", "approved_at": "x", "note": "n"}, "mapping": {}})
    store.strategy_save(pid, cid, cyid, {"positioning": {"type": "gap"}, "portfolio": {"gap": 1, "free": 1}})
    store.stage_start(pid, "S02", cid, cyid)
    r1 = store.stage_complete(pid, "S02", [{"path": out_file(store, pid, cid, "s1.md")}], "v1", cid, cyid)
    store.stage_start(pid, "S02", cid, cyid)
    r2 = store.stage_complete(pid, "S02", [{"path": out_file(store, pid, cid, "s2.md")}], "v2", cid, cyid)
    with pytest.raises(AdMemoryError):  # eski sürümün onayı geçersiz
        store.gate_approve(pid, r1["stage_run"]["id"], r1["stage_run"]["output_version"], "evet", cycle_id=cyid)
    with pytest.raises(AdMemoryError):  # başka turun onayı kullanılamaz
        store.gate_approve(pid, r2["stage_run"]["id"], r2["stage_run"]["output_version"], "evet", cycle_id=cyid + 999)
    with pytest.raises(AdMemoryError):  # açık onay ifadesi zorunlu
        store.gate_approve(pid, r2["stage_run"]["id"], r2["stage_run"]["output_version"], "  ", cycle_id=cyid)
    ok = store.gate_approve(pid, r2["stage_run"]["id"], r2["stage_run"]["output_version"], "onaylıyorum", cycle_id=cyid)
    assert ok["next_stage"] == "S03"


def test_s02_blocked_without_risk_limit(store):
    pid, cid, cyid = new_campaign(store)
    advance_to(store, pid, cid, cyid, "S02")
    store.cycle_set(pid, cyid, budget_plan_json={"allowed_test_ads": 1, "fits_total_budget": True}, test_days=7, cycle_days=14)
    store.stage_start(pid, "S02", cid, cyid)
    r = store.stage_complete(pid, "S02", [{"path": out_file(store, pid, cid, "s.md")}], "v", cid, cyid)
    with pytest.raises(AdMemoryError) as e:
        store.gate_approve(pid, r["stage_run"]["id"], r["stage_run"]["output_version"], "evet", cycle_id=cyid)
    assert "risk" in str(e.value) and "iki reklama" in str(e.value)


def test_quick_mode_skips_s04_to_s06(store):
    pid, cid, cyid = new_campaign(store, mode="quick")
    c = advance_to(store, pid, cid, cyid, "S07")
    assert c["stage"] == "S07"
    skipped = {r["stage"] for r in store.qa("SELECT stage FROM stage_runs WHERE cycle_id=? AND status='skipped'", (cyid,))}
    assert {"S04", "S05", "W", "S06"} <= skipped


def test_back_marks_later_stale_and_keeps_paid(store):
    pid, cid, cyid = new_campaign(store)
    advance_to(store, pid, cid, cyid, "S09")
    store.generation_log(pid, cid, cyid, "creative_generate_speech", {"prompt": "x", "model_id": "eleven_v4", "voice_id": "v"}, 10)
    store.ex("UPDATE generations SET status='completed'")
    r = store.stage_back(pid, cid, cyid, "S03", "konsepti değiştirelim")
    assert r["stale_runs"] >= 1 and r["reusable_generations"] == 1
    assert store.q1("SELECT stage FROM campaigns WHERE id=?", (cid,))["stage"] == "S03"


def test_s01b_skip_records_decision(store):
    pid, cid, cyid = new_campaign(store)
    advance_to(store, pid, cid, cyid, "S01b")
    r = store.stage_complete(pid, "S01b", [], "atlandı", cid, cyid, skipped_reason="kullanıcı rakip analizi istemedi")
    assert r["status"] == "skipped"
    d = store.q1("SELECT * FROM decisions WHERE stage='S01b' AND decision='skipped'")
    assert d and "istemedi" in d["note"]
    assert store.q1("SELECT stage FROM campaigns WHERE id=?", (cid,))["stage"] == "S02"


def test_s03_requires_user_decision_and_hook_parts(store):
    pid, cid, cyid = new_campaign(store)
    advance_to(store, pid, cid, cyid, "S03")
    with pytest.raises(AdMemoryError):
        store.concept_upsert(pid, cid, cyid, "B", "Konsept B", "general", decision="accepted")  # kullanıcı ifadesi yok
    k = store.concept_upsert(pid, cid, cyid, "B", "Konsept B", "general")
    with pytest.raises(AdMemoryError):
        store.hook_upsert(pid, k["id"], "h1", "product", "", "hareket", "ses", "metin")  # dört parça zorunlu
    store.stage_start(pid, "S03", cid, cyid)
    r = store.stage_complete(pid, "S03", [{"path": out_file(store, pid, cid, "ozet.md")}], "özet", cid, cyid)
    with pytest.raises(AdMemoryError):  # seçilmiş konsept yok
        store.gate_approve(pid, r["stage_run"]["id"], r["stage_run"]["output_version"], "evet", cycle_id=cyid)


def test_checkpoint_atomic_with_decision_and_size_limit(store):
    pid, cid, cyid = new_campaign(store)
    advance_to(store, pid, cid, cyid, "S03")
    store.concept_upsert(pid, cid, cyid, "A", "Konsept A", "product", decision="deferred", user_said="sonra bakalım",
                         checkpoint={"next_step": "hook seçimi", "decisions": ["A ertelendi"]})
    cp = store.checkpoint_get(pid, cid, cyid, "S03")["open"]
    assert cp and cp[0]["state_json"]["next_step"] == "hook seçimi"
    with pytest.raises(AdMemoryError):
        store.checkpoint_save(pid, "S03", {"dump": "x" * 4000}, cid, cyid)
    # karar mutasyonu başarısızsa devam notu da yazılmaz (atomik)
    with pytest.raises(AdMemoryError):
        store.concept_upsert(pid, cid, cyid, "Z", "Z", "yanlis_kaynak", checkpoint={"next_step": "BOZUK"})
    assert store.checkpoint_get(pid, cid, cyid, "S03")["open"][0]["state_json"]["next_step"] == "hook seçimi"


def test_resume_detects_missing_and_unknown(store):
    pid, cid, cyid = new_campaign(store)
    f = out_file(store, pid, cid, "ara.md")
    from admem.util import sha256_file
    store.checkpoint_save(pid, "S01", {"next_step": "devam", "files": [{"path": f, "sha256": sha256_file(f)}, {"path": f + ".yok"}]}, cid, cyid)
    store.generation_log(pid, cid, cyid, "creative_generate_speech", {"prompt": "x", "model_id": "eleven_v4", "voice_id": "v"}, 5)
    store.ex("UPDATE generations SET status='unknown'")
    rep = store.stage_resume(pid, cid, cyid)["resume"][0]
    assert rep["verified_files"] and rep["missing_files"] and rep["unresolved_generations"]


def test_cycle_rolls_after_s17(store):
    pid, cid, cyid = new_campaign(store)
    store.ex("UPDATE campaigns SET stage='S16' WHERE id=?", (cid,))
    store.ex("UPDATE cycles SET launched_at='2026-03-01T00:00:00Z', status='measuring' WHERE id=?", (cyid,))
    for st in ("S16", "S17"):
        store.stage_start(pid, st, cid, cyid)
        r = store.stage_complete(pid, st, [{"path": out_file(store, pid, cid, f"{st}.md")}], st, cid, cyid)
        store.gate_approve(pid, r["stage_run"]["id"], r["stage_run"]["output_version"], "onaylıyorum", cycle_id=cyid)
    c = store.q1("SELECT * FROM campaigns WHERE id=?", (cid,))
    assert c["cycle"] == 2 and c["stage"] == "S01"
    assert store.q1("SELECT status FROM cycles WHERE id=?", (cyid,))["status"] == "closed"


def test_jobs_atomic_claim_and_identity(store):
    pid, cid, cyid = new_campaign(store)
    with pytest.raises(AdMemoryError):
        store.job_upsert(pid, "karar-hazirla", cid)  # tur kimliği zorunlu
    j = store.job_upsert(pid, "takip", cid, schedule="09:00")
    j2 = store.job_upsert(pid, "takip", cid, schedule="09:00")
    assert j["job_id"] == j2["job_id"]  # kampanya başına tek takip
    a = store.job_claim(pid, j["job_id"], "oturum-aaaa")
    b = store.job_claim(pid, j["job_id"], "oturum-bbbb")
    assert a["claimed"] and not b["claimed"]
    store.job_finish(pid, j["job_id"], "oturum-aaaa", "ok", data_version="v1")
    assert store.job_claim(pid, j["job_id"], "oturum-bbbb")["claimed"]
    # başka profil görev hedefini değiştiremez
    other = make_active_profile(store, "Marka B", "act_b", "Ürün B")
    with pytest.raises(AdMemoryError):
        store.job_upsert(other["profile"]["id"], "takip", cid)


def test_risk_limit_validation(store):
    pid, cid, cyid = new_campaign(store)
    for bad in ({"per_ad": {"amount": 0, "currency": "TRY", "scope": "ad_launch_to_stop", "approved_at": "x"}},
                {"per_ad": {"amount": float("inf"), "currency": "TRY", "scope": "ad_launch_to_stop", "approved_at": "x"}},
                {"per_ad": {"amount": 10, "currency": "TRY", "scope": "cpa", "approved_at": "x"}}):
        with pytest.raises(AdMemoryError):
            store.cycle_set(pid, cyid, risk_limits_json=bad)


def test_runtime_record_scoped_and_stale(store, tmp_path):
    m = {"plugin_version": "1.4.0", "live_checks": [{"id": "x1", "required": True, "components": ["c"]}], "component_hashes": {"c": "h1"}}
    store.plugin_root = tmp_path / "plug"
    store.plugin_root.mkdir()
    (store.plugin_root / "system_manifest.json").write_text(json.dumps(m), encoding="utf-8")
    store.runtime_record("x1", "passed", component_hashes={"c": "h1"})
    v = store.system_manifest_get()
    # statik kontrol (doctor) geçmeden canlı maddeler kurulumu doğrulanmış saydırmaz (1.4.1)
    assert v["live"]["common_required_ok"] and not v["setup_verified_at"] and not v["setup_verified_effective"]
    store.settings_set("setup_static_ok_at", "2026-03-02T09:00:00Z")
    v = store.mark_verified_if_ready()
    assert v["setup_verified_at"] and v["setup_verified_effective"]
    store.runtime_record("x1", "failed", scope="profile:7")
    assert store.system_manifest_get()["live"]["checks"][0]["status"] == "passed"  # başka kapsamın kaydı ezilmez
    m["component_hashes"]["c"] = "h2"
    m["extra"] = 1
    (store.plugin_root / "system_manifest.json").write_text(json.dumps(m), encoding="utf-8")
    v2 = store.system_manifest_get()
    assert v2["live"]["checks"][0]["status"] == "stale" and not v2["setup_verified_effective"]
    with pytest.raises(AdMemoryError):
        store.runtime_record("tanimsiz", "passed")
    with pytest.raises(AdMemoryError):
        store.runtime_record("x1", "not_applicable")


def test_install_deviations_live_in_data_dir_not_manifest(store):
    """Kuruluma/makineye özgü sapmalar dağıtılan manifestte değil data_dir ayarında tutulur (12.13, ilke 12)."""
    import json as _json
    rec = [{"id": "x", "check": "disk_data", "spec": "12.10", "deviation": "örnek", "decided_by": "user", "status": "accepted"}]
    store.settings_set("install_deviations_json", _json.dumps(rec, ensure_ascii=False))
    v = store.system_manifest_get()
    assert v["install_deviations"] == rec


def test_economics_unknown_cost_and_range(store):
    """Bilinmeyen maliyet kalemi (null/metin) çökme yerine 'bilinmiyor'; verilen aralık kalemlerden çıkan tek sayıyla ezilmez (1.4.1)."""
    eco = {"net_basket": 850, "variable_costs": {"product": 300, "shipping": 50, "commission": 34, "expected_returns": None},
           "contribution_low": 425, "contribution_high": 466}
    r = store.economics({"economics_json": eco})
    assert r["status"] == "range" and r["breakeven_cpa_range"] == [425.0, 466.0]
    eco2 = {"net_basket": 850, "variable_costs": {"product": 300, "expected_returns": "bilinmiyor; %0-5 varsayımı"}}
    r = store.economics({"economics_json": eco2})
    assert r["status"] == "unknown" and r["unknown_costs"] == ["expected_returns"] and "bilinmeyen kalemler" in r["note"]
    r = store.economics({"economics_json": {"net_basket": 850, "variable_costs": {"product": "300", "shipping": 50}}})
    assert r["status"] == "assumed" and r["breakeven_cpa"] == 500.0


def test_profile_level_single_open_checkpoint(store):
    """Tanışmada tek 'kaldığımız yer' vardır: yeni profil düzeyi not öncekini kapatır; kampanya notlarına dokunmaz (1.4.1)."""
    pid = store.profile_create("Marka C")["id"]
    st = {"completed_steps": [], "decisions": [], "open_questions": [], "next_step": "x", "refs": {}}
    store.checkpoint_save(pid, "S00a", st, scope_key=f"profile:{pid}")
    store.checkpoint_save(pid, "S00b", {**st, "next_step": "y"}, scope_key=f"profile:{pid}")
    open_ = store.checkpoint_get(pid)["open"]
    assert [o["stage"] for o in open_] == ["S00b"]


def test_campaign_create_closes_onboarding_checkpoints(store):
    pid, cid, cyid = new_campaign(store)
    st = {"completed_steps": [], "decisions": [], "open_questions": [], "next_step": "x", "refs": {}}
    store.checkpoint_save(pid, "S03", st, campaign_id=cid, cycle_id=cyid)
    store.checkpoint_save(pid, "S00b", st, scope_key=f"profile:{pid}")
    prod = store.product_list(pid)["products"][0]
    store.campaign_create(pid, prod["id"], "İkinci kampanya")
    assert [o["stage"] for o in store.checkpoint_get(pid)["open"]] == ["S03"]  # kampanya notuna dokunulmaz
