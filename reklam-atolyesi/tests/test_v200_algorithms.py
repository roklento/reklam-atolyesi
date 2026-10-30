"""2.0.0 algoritma denetimi: amaç başına önsel, kalibrasyon kutuları, yorgunluk penceresi, tutma eğrisi eşleri, eşlenmemiş reklamlar,
aday ekonomisi ve risk sınırı gerekçesi."""
from __future__ import annotations

import pytest

import budget as BU
import calibration as CAL
import coach as CO
from admem.util import jdump, now_iso
from test_analytics import build_campaign


def _priors(store, pid):
    store.priors_set(pid, "OUTCOME_SALES", "hook_rate", 9, 21, 30, "history")
    store.priors_set(pid, "OUTCOME_TRAFFIC", "hook_rate", 2, 28, 30, "history")


def _entities(store, pid, objective="OUTCOME_SALES"):
    ents = [{"level": "campaign", "meta_id": "c1", "objective": objective}, {"level": "adset", "meta_id": "s1", "parent_meta_id": "c1"}]
    ents += [{"level": "ad", "meta_id": f"90{i}", "parent_meta_id": "s1", "name": f"r{i}"} for i in (1, 2, 3)]
    store.meta_entities_upsert(pid, "act_A", ents)


def test_priors_follow_campaign_objective(store):
    pid, cid, cyid = build_campaign(store)
    _priors(store, pid)
    _entities(store, pid)
    pr = CO.read_json(store.decision_input_snapshot(pid, cid, cyid)["path"])["priors"]
    assert pr["objective"] == "OUTCOME_SALES" and {p["objective"] for p in pr["priors"]} == {"OUTCOME_SALES"}
    assert CO.priors_for({"priors": pr})["hook_rate"] == (9, 21)  # önceden metrik başına sıradaki son satır (trafik amacı) kazanıyordu


def test_priors_unknown_objective_with_mixed_history_is_uniform(store):
    pid, cid, cyid = build_campaign(store)
    _priors(store, pid)
    pr = CO.read_json(store.decision_input_snapshot(pid, cid, cyid)["path"])["priors"]
    assert pr["objective"] is None and pr["priors"] == [] and "Beta(1,1)" in pr["objective_basis"]


def test_priors_unknown_objective_single_prior_used(store):
    pid, cid, cyid = build_campaign(store)
    store.priors_set(pid, "*", "hook_rate", 6, 24, 30, "history")  # CSV yolu: amacı bilinmeyen geçmiş
    pr = CO.read_json(store.decision_input_snapshot(pid, cid, cyid)["path"])["priors"]
    assert pr["objective"] == "*" and len(pr["priors"]) == 1


def test_priors_objective_without_history(store):
    pid, cid, cyid = build_campaign(store)
    _priors(store, pid)
    _entities(store, pid, "OUTCOME_LEADS")
    pr = CO.read_json(store.decision_input_snapshot(pid, cid, cyid)["path"])["priors"]
    assert pr["objective"] == "OUTCOME_LEADS" and pr["priors"] == [] and "önsel yok" in pr["objective_basis"]


def _pairs():
    # p=0.3 "kaybeder" der ve kaybetti → isabet; iddia %70 kutusunda (0.7 kayan noktada 0.7 + 0.1'in altında kalmalı)
    out = [{"p": 0.3, "won": False, "chain": f"a{i}"} for i in range(20)]
    out += [{"p": 0.8, "won": True, "chain": f"b{i}"} for i in range(5)] + [{"p": 0.8, "won": False, "chain": f"c{i}"} for i in range(5)]
    out += [{"p": 1.0, "won": True, "chain": "d"}]
    return out


def test_calibration_bins_integer_and_direction():
    r = CAL.calibrate(_pairs())
    bins = {b["claimed"]: b for b in r["bins"]}
    assert set(bins) == {"%70–80", "%80–90", "%90–100"}
    assert bins["%70–80"] == {"claimed": "%70–80", "n": 20, "realized": 1.0}
    assert bins["%80–90"]["n"] == 10 and bins["%80–90"]["realized"] == 0.5 and bins["%90–100"]["n"] == 1


def test_calibration_get_matches_script(store):
    pid, cid, cyid = build_campaign(store)
    for i, p in enumerate(_pairs()):
        store.ex("""INSERT INTO coaching_predictions(campaign_id,cycle_id,subject,metric,p_win,input_snapshot_json,made_at,outcome_json,resolved_at)
                    VALUES(?,?,?,?,?,?,?,?,?)""", (cid, cyid, f"k{i}", "hook_rate", p["p"], "{}", now_iso(), jdump({"latest": {"won": p["won"]}}), now_iso()))
    got = store.calibration_get(pid)
    assert got["bins"] == CAL.calibrate(_pairs())["bins"]


def _day(d, imp, hook, freq=1.0, spend=None, clicks=0):
    return {"date": f"2026-03-{d:02d}", "impressions": imp, "video_3s": int(imp * hook), "link_clicks": clicks, "frequency": freq,
            "spend": spend if spend is not None else imp * 0.05}


def test_fatigue_window_does_not_overlap_base():
    # 7 gün: ilk 3 gün %30, son 4 gün %22 (bazın %73'ü). Bazla örtüşen eski pencere (7 günün tamamı) ~%25,4 → uyarı vermiyordu
    rows = [_day(d, 1000, 0.30) for d in (1, 2, 3)] + [_day(d, 1000, 0.22) for d in (4, 5, 6, 7)]
    al = [a for a in CO.fatigue({"k": rows}) if a["kind"] == "hook_decline"]
    assert al and al[0]["last7"] == pytest.approx(0.22)
    assert not CO.fatigue({"k": rows[:5]})  # 6 günden az veri değerlendirilmez


def _ret_rows(drop):
    return [{"impressions": 1000, "video_3s": 1000, "p25": 800, "p50": int(600 * drop), "p75": int(400 * drop), "p95": 200, "p100": 150}]


def test_retention_expected_from_same_format_and_duration():
    cr = [{"creative_key": "a6", "format": "9x16", "duration_s": 6}, {"creative_key": "b6", "format": "9x16", "duration_s": 6},
          {"creative_key": "a30", "format": "9x16", "duration_s": 30}, {"creative_key": "b30", "format": "9x16", "duration_s": 30}]
    # 6 sn'lik kısa kreatifler doğal olarak orta noktada daha çok tutar; 30 sn'likler kendi aralarında aynı
    rows = {"a6": _ret_rows(1.3), "b6": _ret_rows(1.3), "a30": _ret_rows(0.9), "b30": _ret_rows(0.9)}
    assert CO.retention({"creatives": cr}, rows) == []  # kampanya ortancasıyla 30 sn'likler haksız yere "kayıp" görünürdü
    rows["b30"] = _ret_rows(0.6)
    out = CO.retention({"creatives": cr}, rows)
    assert [o["creative"] for o in out] == ["b30"]


def _concept(spend, results):
    return {"rates": {"hook_rate": {"threshold_met": True}}, "totals": {"spend": spend, "results": results}}


def test_decisions_lead_economics_and_unmapped():
    snap = {"campaign": {"result_type": "lead"}, "economics": {"status": "unknown", "cpl_status": "exact", "target_cpl": 50}}
    cost = {"A": {"threshold_met": True, "p_below_target": 0.95}, CO.UNMAPPED: {"threshold_met": True, "p_below_target": 0.01}}
    dist = {"A": {"share": 0.6}, CO.UNMAPPED: {"share": 0.4}}
    dec = {d["concept"]: d for d in CO.decisions({"A": _concept(500, 20), CO.UNMAPPED: _concept(500, 1)}, dist, snap, "creative_test", cost)}
    assert dec["A"]["decision"] == "büyüt"  # aday ekonomisi doğrulanmış; satış ekonomisinin durumu aday kampanyasını engellemez
    assert dec[CO.UNMAPPED]["decision"] == "tut" and dec[CO.UNMAPPED]["label"] == "eşlenmemiş"  # eşlenmemişe "kapat" verilmez
    snap["economics"] = {"status": "exact", "cpl_status": "unknown"}
    dec = {d["concept"]: d for d in CO.decisions({"A": _concept(500, 20)}, dist, snap, "creative_test", cost)}
    assert dec["A"]["decision"] == "tut"  # satış ekonomisi doğrulanmış diye aday kampanyası büyütülmez


def test_funnel_diagnosis_ignores_unmapped():
    k = {CO.UNMAPPED: {"rates": {"hook_rate": {"mean": 0.9, "threshold_met": True}}, "totals": {}}}
    out = CO.funnel_diagnosis(k, [], {"sales": {}, "leads": {}})
    assert CO.UNMAPPED not in str(out)


def test_budget_reason_names_risk_limit():
    r = BU.plan({"cycle_no": 1, "adset_daily": 100, "cpm": 50, "risk_per_ad": 10, "launch_at": "2026-03-10"})
    assert r["production_blocked"] and "risk sınırı" in r["reason"]
    r = BU.plan({"cycle_no": 1, "adset_daily": 5, "cpm": 50, "launch_at": "2026-03-10"})
    assert r["production_blocked"] and "14 günlük" in r["reason"]


def test_color_match_skips_white_balance_without_neutral_pixels():
    import color_match as CM
    ref = {"median_lin": 0.18, "r_g": 1.0, "b_g": 1.0, "wb_pool": "neutral"}
    red = {"median_lin": 0.18 * 2 ** -0.3, "r_g": 1.10, "b_g": 0.92, "wb_pool": "all"}  # kırmızı ürün yakın çekimi: oran sahnenin rengi
    c = CM.correction(red, ref)
    assert c["applied"] and c["wb_gain_r"] == 1.0 and c["wb_gain_b"] == 1.0 and "wb_note" in c
    gr, gg, gb = c["gain_gamma"]
    assert gr == gg == gb  # yalnız pozlama: ürün rengi kaymaz
    assert not CM.correction({**red, "r_g": 1.3}, ref)["retake"]  # ölçülemeyen beyaz dengesi yeniden çekim gerekçesi olmaz
    assert CM.correction({**red, "wb_pool": "neutral"}, ref)["wb_gain_r"] != 1.0


def test_measured_text_matches_js_slice_with_emoji():
    import text_layout as TL
    text = "😀" * 100 + " son"  # 200 UTF-16 birimi; JavaScript slice(0,160) = 80 emoji
    assert TL._js_head(text) == "😀" * 80 and TL._js_head("kısa") == "kısa"
    layer = {"type": "text", "text": text}
    ext = TL.layer_extent(layer, "hook", "9x16")
    rec = {"component": "TextReveal", "part": "text", "text": "😀" * 80, "heightPx": 400, "height": 1920, "fits": False, "lines": 4, "maxLines": 3}
    m = TL.measured_extent(ext, layer, [rec])
    assert m["measured"] and m["overflow"] and m["y1"] == round(m["y"] + 400 / 1920, 4)


def _tone(path, dur, amp, f=220.0):
    import numpy as np
    import soundfile as sf
    t = np.arange(int(dur * 48000)) / 48000
    sf.write(str(path), np.stack([amp * np.sin(2 * np.pi * f * t)] * 2, axis=1), 48000, subtype="FLOAT")
    return str(path)


def test_speech_mask_is_continuous_and_music_ducked_fully():
    import numpy as np
    import mix as MX
    t = np.arange(48000) / 48000
    y = np.stack([0.3 * np.sin(2 * np.pi * 200 * t)] * 2, axis=1)  # sürekli ses: örneklerin ~%2'si sıfır geçişinde 0,01'in altında
    y[24000:] = 0
    m = MX.speech_activity(y)
    assert m[:23000].all() and not m[30500:].any()  # 120 ms tutmadan sonra sessizlik konuşma sayılmaz


def test_mix_pre_not_clipped_and_negative_music_offset(tmp_path):
    import numpy as np
    import soundfile as sf
    import mix as MX
    music = _tone(tmp_path / "m.wav", 4, 0.9, 110)
    vo = _tone(tmp_path / "vo.wav", 3, 0.9, 330)
    plan = {"duration_s": 3, "fps": 30, "music": {"offset_s": -1.0, "gain_db": 0},
            "scenes": [{"id": "s1", "start_s": 0, "dur_s": 3, "audio": {"mode": "generated"}, "layers": []}]}
    r = MX.mix(plan, {}, music, vo, {}, tmp_path / "stems")
    pre, _ = sf.read(r["pre"], always_2d=True)
    assert np.abs(pre).max() > 1.0  # toplam ±1'i aşıyor ve kırpılmadan saklanıyor
    assert r["loudness_ok"] and r["loudness"]["true_peak_dbtp"] <= -0.95


# --- metrik alımı ----------------------------------------------------------------------------------------------------
from conftest import make_active_profile  # noqa: E402
from test_metrics import CTX as MCTX  # noqa: E402


def _csv(tmp_path, dates):
    p = tmp_path / "d.csv"
    lines = ["Reklam Kimliği;Reklam adı;Gün;Gösterimler;Harcanan Tutar (TRY)"]
    lines += [f"9001;R;{d};1000;50,00" for d in dates]
    p.write_text("\n".join(lines), encoding="utf-8")
    return str(p)


def test_csv_date_order_detected_or_refused(store, tmp_path):
    from admem.util import AdMemoryError
    import meta_tools
    pid = make_active_profile(store)["profile"]["id"]
    us = _csv(tmp_path, ["03/10/2026", "03/13/2026"])  # ay önce: 13 ay olamaz
    assert meta_tools.csv_check(us)["date_order"] == "mdy" and meta_tools.csv_check(us)["date_range"] == ["2026-03-10", "2026-03-13"]
    r = store.metrics_import_csv(pid, us, MCTX)
    assert r["date_order"] == "mdy" and {m["date"] for m in store.metrics_daily_rows(pid)["rows"]} == {"2026-03-10", "2026-03-13"}
    amb = _csv(tmp_path, ["03/04/2026", "04/04/2026"])
    with pytest.raises(AdMemoryError, match="csv_date_order"):
        store.metrics_import_csv(pid, amb, MCTX)
    assert len(store.metrics_daily_rows(pid)["rows"]) == 2  # hiçbir satır yazılmadı
    r = store.metrics_import_csv(pid, amb, {**MCTX, "csv_date_order": "dmy"})
    assert {m["date"] for m in store.metrics_daily_rows(pid)["rows"]} >= {"2026-04-03", "2026-04-04"}
    assert store.metrics_import_csv(pid, _csv(tmp_path, ["02.04.2026"]), MCTX)["date_order"] == "dmy"  # noktalı: gün önce


def test_unmeasured_metric_is_not_zero_and_not_erased(store):
    pid = make_active_profile(store)["profile"]["id"]
    full = [{"meta_ad_id": "9001", "ad_name": "R", "date": "2026-03-01", "impressions": 1000, "spend": 50, "video_3s": 300, "thruplay": 90}]
    store.metrics_ingest(pid, full, "meta_mcp", MCTX)
    store.metrics_ingest(pid, [{"meta_ad_id": "9001", "ad_name": "R", "date": "2026-03-01", "impressions": 1000, "spend": 55}], "csv", MCTX)
    m = store.metrics_daily_rows(pid)["rows"][0]
    assert m["spend"] == 55 and m["video_3s"] == 300 and m["thruplay"] == 90  # yeni değer yazılır, gelmeyen alan silinmez
    store.metrics_ingest(pid, [{"meta_ad_id": "9001", "ad_name": "R", "date": "2026-03-02", "impressions": 1000, "spend": 50, "video_3s": 300}],
                         "meta_mcp", MCTX)
    g = store.metrics_query(pid, level="ad")["groups"][0]
    assert g["hold_rate"] == pytest.approx(90 / 300)  # ThruPlay'i ölçülmemiş gün paydaya girmez
    assert g["cvr"] is None  # satın alma hiç ölçülmedi: %0 değil


def test_coach_rate_none_when_numerator_unmeasured():
    rows = [{"impressions": 5000, "video_3s": 1500, "thruplay": None, "link_clicks": 50, "purchases": None, "spend": 100}]
    post = CO.posteriors({"A": rows}, {})["A"]["rates"]
    assert post["hold_rate"] is None and post["cvr"] is None and post["hook_rate"]["trials"] == 5000


def test_claim_match_turkish_case():
    from admem.funnel import claim_usable
    claims = [{"claim": "14 gün içinde iade", "needs_document": False}]
    assert claim_usable("14 GÜN İÇİNDE İADE", claims) and claim_usable("14 gün  içinde iade", claims)
    assert not claim_usable("ıade", claims)  # noktasız ı ayrı harftir
