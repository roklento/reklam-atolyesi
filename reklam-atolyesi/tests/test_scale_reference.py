"""1.4.6: ölçekleme katmanı (test ayrı, ölçek tek; kazanan mevcut gönderiyle taşınır), slayt gösterisi riski ve referans video analizi."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

import budget as BU
import coach as CO
import report as RP
import slideshow as SS
from admem import editplan
from admem.util import AdMemoryError
from conftest import make_active_profile

CTX = {"account_id": "act_A", "timezone": "Europe/Istanbul", "currency": "TRY", "result_definition": "purchase",
       "metric_definitions": {}, "attribution_window": "7d_click", "action_report_time": "impression"}


# --- budget.py: ölçekleme uygunluğu ve toplam plan ----------------------------------------
def _chk(**kw):
    base = dict(structure="creative_test", cost_ok=True, target_cpa=28.0, economics_exact=True, proposed_daily=None,
                budget_total=10000, spend_to_date=1000, other_daily=100, days_left=10)
    base.update(kw)
    return BU.scale_check(**base)


def test_scale_check_all_conditions():
    r = _chk()
    assert r["eligible"] and r["min_daily"] == 196.0 and r["proposed_daily"] == 196.0
    assert r["projected_need"] == pytest.approx((196 + 100) * 10)


@pytest.mark.parametrize("kw, failed", [
    ({"structure": "bootstrap"}, "structure"),
    ({"structure": "deviated"}, "structure"),
    ({"economics_exact": False}, "cost"),
    ({"cost_ok": False}, "cost"),
    ({"proposed_daily": 150}, "min_daily"),
    ({"budget_total": 3000}, "fits_total"),
    ({"spend_to_date": None}, "fits_total"),
])
def test_scale_check_each_condition_blocks(kw, failed):
    r = _chk(**kw)
    assert not r["eligible"] and r["checks"][failed] is False and r["reasons"]


def test_scale_check_no_total_limit_is_user_choice():
    r = _chk(budget_total=None)
    assert r["eligible"] and "tanımlanmamış" in r["fits_note"]


def test_budget_plan_counts_scale_layer():
    base = {"cycle_no": 2, "exploration_share": 0.2, "adset_daily": 300, "cpm": 10, "budget_total": 100000, "spend_to_date": 0,
            "data_cutoff": "2026-03-10", "launch_at": "2026-03-10"}
    a = BU.plan(base)
    b = BU.plan({**base, "scale_layer_daily": 200})
    days = b["spend_projection"]["days"]
    assert b["spend_projection"]["scale_layer_daily"] == 200
    assert b["spend_projection"]["projected_additional"] == pytest.approx(a["spend_projection"]["projected_additional"] + 200 * days)


# --- sunucu: kayıt, koruma, yeni tura taşıma, uygulama maddeleri ------------------------------
def _campaign(store):
    a = make_active_profile(store)  # katkı 40 × güvenlik 0,7 → hedef maliyet 28 (exact)
    pid = a["profile"]["id"]
    c = store.campaign_create(pid, a["product"]["id"], "K", result_type="purchase", budget_total=10000)
    cid, cyid = c["campaign"]["id"], c["cycle"]["id"]
    for i, k in enumerate(("A", "B")):
        key = f"MRK_K_{k}_video_15_h1_novo_real_c1_r1"
        f = store.campaign_dir(pid, cid) / "out" / f"{key}_916.mp4"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(bytes([i]) * 32)
        store.ex("""INSERT INTO creatives(campaign_id,cycle_id,creative_key,file_path,file_name,sha256,media_type,source_variant,card_index,delivery_role,
                    duration_s,format,created_at) VALUES(?,?,?,?,?,?, 'video','real',0,'test',15,'9x16','x')""", (cid, cyid, key, str(f), f.name, f"h{i}"))
        store.ex("INSERT INTO concepts(campaign_id,cycle_id,code,name,source,created_at,updated_at) VALUES(?,?,?,?, 'general','x','x')", (cid, cyid, k, k))
        store.ex("UPDATE creatives SET concept_id=(SELECT id FROM concepts WHERE cycle_id=? AND code=?) WHERE creative_key=?", (cyid, k, key))
    return pid, cid, cyid


KEY_A = "MRK_K_A_video_15_h1_novo_real_c1_r1"


def _obj(v):
    return json.loads(v) if isinstance(v, str) else v


def _layer(**kw):
    base = {"campaign_meta_id": "c-olcek", "adset_id": "as-olcek", "daily_budget": 200,
            "members": [{"creative_key": KEY_A, "meta_ad_id": "9001", "post_id": "123_456", "source_meta_ad_id": "901"}]}
    base.update(kw)
    return base


def test_scale_layer_set_validates_and_links(store):
    pid, cid, cyid = _campaign(store)
    with pytest.raises(AdMemoryError, match="post_id"):
        store.scale_layer_set(pid, cid, cyid, _layer(members=[{"creative_key": KEY_A, "meta_ad_id": "9001"}]))
    with pytest.raises(AdMemoryError, match="test edilmiş"):
        store.scale_layer_set(pid, cid, cyid, _layer(members=[{"creative_key": "YOK", "meta_ad_id": "9001", "post_id": "1_2"}]))
    with pytest.raises(AdMemoryError, match="öğrenme sınırlı"):
        store.scale_layer_set(pid, cid, cyid, _layer(daily_budget=100))  # 100 < 7 × 28
    r = store.scale_layer_set(pid, cid, cyid, _layer())
    assert r["scale_layer"]["min_daily"] == 196.0 and r["linked"] == ["9001"]
    ad = store.q1("SELECT * FROM ads WHERE meta_ad_id='9001'")
    assert ad["adset_id"] == "as-olcek" and ad["creative_key"] == KEY_A
    assert store.scale_layer_get(pid, cid)["scale_layer"]["members"][0]["post_id"] == "123_456"


def test_scale_layer_low_budget_needs_explicit_ack(store):
    pid, cid, cyid = _campaign(store)
    r = store.scale_layer_set(pid, cid, cyid, _layer(daily_budget=100), learning_warning_ack="biliyorum, yine de aç")
    assert "öğrenme sınırlı" in r["scale_layer"]["learning_warning"]
    assert store.q1("SELECT 1 FROM decisions WHERE decision='scale_learning_warning'")


def test_s02_plan_does_not_erase_scale_layer(store):
    pid, cid, cyid = _campaign(store)
    store.scale_layer_set(pid, cid, cyid, _layer())
    store.cycle_set(pid, cyid, budget_plan_json={"allowed_test_ads": 3, "fits_total_budget": True})
    bp = _obj(store.q1("SELECT budget_plan_json FROM cycles WHERE id=?", (cyid,))["budget_plan_json"])
    assert bp["allowed_test_ads"] == 3 and bp["scale_layer"]["adset_id"] == "as-olcek"
    with pytest.raises(AdMemoryError, match="scale_layer_set"):
        store.cycle_set(pid, cyid, budget_plan_json={"allowed_test_ads": 3, "scale_layer": {"adset_id": "baska"}})


def test_scale_only_plan_is_not_an_s02_plan(store):
    pid, cid, cyid = _campaign(store)
    store.scale_layer_set(pid, cid, cyid, _layer())
    c = store.q1("SELECT * FROM campaigns WHERE id=?", (cid,))
    cy = store.q1("SELECT * FROM cycles WHERE id=?", (cyid,))
    with pytest.raises(AdMemoryError, match="bütçe planı"):
        store._s02_preconditions(pid, c, cy)
    store.cycle_set(pid, cyid, budget_plan_json={"allowed_test_ads": 3, "fits_total_budget": True, "spend_projection": {"scale_layer_daily": 0}})
    cy = store.q1("SELECT * FROM cycles WHERE id=?", (cyid,))
    assert any("ölçekleme katmanının günlük bütçesi" in b for b in store._s02_blockers(c, cy))
    store.cycle_set(pid, cyid, budget_plan_json={"allowed_test_ads": 3, "fits_total_budget": True, "spend_projection": {"scale_layer_daily": 200}})
    cy = store.q1("SELECT * FROM cycles WHERE id=?", (cyid,))
    assert not any("ölçekleme" in b for b in store._s02_blockers(c, cy))


def test_s17_carries_scale_layer_to_next_cycle(store):
    pid, cid, cyid = _campaign(store)
    store.scale_layer_set(pid, cid, cyid, _layer())
    store.ex("UPDATE campaigns SET stage='S17' WHERE id=?", (cid,))
    run = store.stage_start(pid, "S17", cid, cyid)
    f = store.campaign_dir(pid, cid) / "c1-ogrenme.md"
    f.write_text("öğrenme", encoding="utf-8")
    r = store.stage_complete(pid, "S17", [{"path": str(f)}], "öğrenme", cid, cyid)
    store.gate_approve(pid, r["stage_run"]["id"], r["stage_run"]["output_version"], "onaylıyorum", cycle_id=cyid)
    nxt = store.q1("SELECT * FROM cycles WHERE campaign_id=? AND cycle=2", (cid,))
    assert nxt and _obj(nxt["budget_plan_json"])["scale_layer"]["members"][0]["post_id"] == "123_456"
    assert store.scale_layer_get(pid, cid)["cycle_id"] == nxt["id"]


def test_scale_action_items_rules(store):
    pid, cid, cyid = _campaign(store)
    store.metrics_ingest(pid, [{"meta_ad_id": "901", "ad_name": KEY_A, "date": "2026-03-02", "impressions": 100, "spend": 5}], "synthetic", CTX)
    snap = store.decision_input_snapshot(pid, cid, cyid)
    ref = {"path": snap["path"], "sha256": snap["sha256"]}
    ok = {k: True for k in ("structure", "cost", "min_daily", "fits_total")}
    with pytest.raises(AdMemoryError, match="post_id"):
        store.action_items_set(pid, cid, [{"action": "taşı", "kind": "scale_move", "after": {},
                                           "evidence": {"input_snapshot": ref, "scale_checks": ok}}])
    with pytest.raises(AdMemoryError, match="min_daily"):
        store.action_items_set(pid, cid, [{"action": "taşı", "kind": "scale_move", "after": {"post_id": "1_2"},
                                           "evidence": {"input_snapshot": ref, "scale_checks": {**ok, "min_daily": False}}}])
    with pytest.raises(AdMemoryError, match="structure"):
        store.action_items_set(pid, cid, [{"action": "aç", "kind": "scale_open", "after": {"daily_budget": 200},
                                           "evidence": {"input_snapshot": ref}}])
    r = store.action_items_set(pid, cid, [
        {"action": "Ölçekleme kampanyası aç", "kind": "scale_open", "reason_kind": "structure", "after": {"daily_budget": 200}, "major": False},
        {"action": "A'yı mevcut gönderiyle taşı", "kind": "scale_move", "reason_kind": "performance", "after": {"post_id": "1_2"},
         "target_meta_id": "901", "evidence": {"input_snapshot": ref, "scale_checks": ok}, "major": False},
        {"action": "Aynı gönderiyi test setinde duraklat", "kind": "scale_pause_source", "reason_kind": "structure",
         "after": {"post_id": "1_2"}, "target_meta_id": "901", "major": False}], cycle_id=cyid)
    assert len(r["created"]) == 3


# --- coach.py: ölçekleme satırları test hesabına girmez ----------------------------------
def _scale_snapshot(store, structure="creative_test"):
    pid, cid, cyid = _campaign(store)
    store.cycle_set(pid, cyid, test_start="2026-03-02T00:00:00+03:00", test_end="2026-03-09T00:00:00+03:00", structure_detected=structure,
                    structure_evidence_json={"source": "test"}, adset_budget_daily=100, launch_at="2026-03-02", cycle_days=14)
    rows = []
    for d in range(1, 11):
        for mid, name, imp, res in (("901", KEY_A, 3000, 3), ("902", "MRK_K_B_video_15_h1_novo_real_c1_r1", 3000, 1)):
            rows.append({"meta_ad_id": mid, "ad_name": name, "date": f"2026-03-{d:02d}", "impressions": imp, "video_3s": imp // 3,
                         "link_clicks": imp // 50, "spend": 30.0, "results": res, "purchases": res, "thruplay": 0})
        rows.append({"meta_ad_id": "9001", "ad_name": KEY_A, "date": f"2026-03-{d:02d}", "impressions": 99999, "video_3s": 1,
                     "link_clicks": 1, "spend": 200.0, "results": 0, "purchases": 0, "thruplay": 0, "frequency": 1.5})
    store.metrics_ingest(pid, rows, "synthetic", CTX)
    store.scale_layer_set(pid, cid, cyid, _layer())
    return store.decision_input_snapshot(pid, cid, cyid, "coach_report")


def test_coach_separates_scale_rows_and_proposes_move(store):
    snap = _scale_snapshot(store)
    an = CO.analyze(snap["path"])
    a = an["concepts"]["A"]["totals"]
    assert a["impressions"] < 99999  # ölçekleme satırları test hesabına girmedi
    assert an["scale_layer"]["spend"] == pytest.approx(2000) and an["scale_layer"]["members"][0]["post_id"] == "123_456"
    assert "test verisi değil" in an["scale_layer"]["label"]
    dec = {d["concept"]: d for d in an["decisions"]}
    assert dec["A"]["decision"] == "büyüt"
    cand = {c["concept"]: c for c in an["scale_candidates"]}
    assert cand["A"]["layer_exists"] and cand["A"]["checks"]["structure"] and cand["A"]["checks"]["min_daily"]
    md = RP.build(an, json.load(open(snap["path"], encoding="utf-8")), {}, None, None, None)
    assert "## Ölçekleme katmanı" in md and "123_456" in md


def test_coach_no_scale_move_in_bootstrap(store):
    snap = _scale_snapshot(store, structure="bootstrap")
    an = CO.analyze(snap["path"])
    for c in an["scale_candidates"]:
        assert not c["eligible"] and c["checks"]["structure"] is False


# --- slayt gösterisi riski ----------------------------------------------------------------
def _scene(i, kind, dur=3.0, role="product", camera=None, text_only=False, asset=None):
    layers = [] if text_only else [{"type": "image" if kind in ("still", "ai_image") else "video",
                                    "source": {"kind": kind, "asset": asset or f"a{i}"}}]
    if camera:
        layers.append({"type": "component", "component": camera})
    layers.append({"type": "text", "text": "yazı"})
    return {"id": f"s{i}", "role": role, "start_s": i * dur, "dur_s": dur, "audio": {"mode": "none"}, "layers": layers}


def test_slideshow_plan_dimensions():
    stills = {"scenes": [_scene(i, "still", asset="same") for i in range(5)]}
    moving = {"scenes": [_scene(0, "footage", 1.2, "hook"), _scene(1, "footage", 2.6), _scene(2, "ai_clip", 0.8),
                         _scene(3, "footage", 3.4), _scene(4, "still", 2.0, "endcard", text_only=True)]}
    rs, rm = SS.slideshow_risk(stills), SS.slideshow_risk(moving)
    assert rs["dimensions"]["still_share"] == 1.0 and rs["dimensions"]["repetition"] == 1.0
    assert rs["level"] in ("high", "critical") and rm["level"] == "low" and rs["basis"] == "plan"
    kb = SS.plan_dimensions({"scenes": [_scene(0, "still", camera="KenBurns")]})
    assert kb["still_share"] == 0.5


def test_slideshow_video_dimensions_and_critical():
    still = SS.video_dimensions([(t / 4, 0.01) for t in range(1, 40)])
    assert still["weak_motion"] == 1.0 and still["hook_motion"] == 1.0
    plan = {"scenes": [_scene(0, "footage", 1.0, "hook"), _scene(1, "footage", 2.5), _scene(2, "footage", 1.4)]}
    assert SS.slideshow_risk(plan, samples=[(t / 4, 0.01) for t in range(1, 40)])["level"] == "critical"
    assert SS.slideshow_risk(plan, samples=[(t / 4, 1.2) for t in range(1, 40)])["level"] == "low"


# --- referans video --------------------------------------------------------------------------
def test_edit_plan_rejects_reference_folder():
    plan = {"campaign": "k", "cycle_id": 1, "concept": "A", "hook": "h1", "format": "9x16", "purpose": "production", "status": "draft",
            "version": 1, "duration_s": 3, "fps": 30, "style": "s",
            "scenes": [{"id": "s1", "role": "hook", "start_s": 0, "dur_s": 3, "audio": {"mode": "none"},
                        "layers": [{"type": "video", "source": {"kind": "footage", "path": "campaigns/k/references/rakip/ref.mp4"}}]}]}
    assert any("referans" in e for e in editplan.validate(plan)["errors"])


def test_reference_shot_stats():
    import reference as RF
    s = RF.shot_stats([1.0, 2.5, 6.0], 10.0)
    assert s["shots"] == 4 and s["shot_lengths_s"] == [1.0, 1.5, 3.5, 4.0] and s["first_cut_s"] == 1.0 and s["cuts_per_10s"] == 3.0
    assert RF._bands("0.55-0.72,0.05-0.2") == [(0.55, 0.72), (0.05, 0.2)]
    with pytest.raises(SystemExit):
        RF._bands("0.8-0.2")


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg yok")
def test_reference_analyze_synthetic(tmp_path):
    import reference as RF
    v = tmp_path / "ref.mp4"
    # iki sert kesimli sentetik dikey video (renk değişimi), sessiz
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=red:s=360x640:d=1.5:r=30",
                    "-f", "lavfi", "-i", "color=c=blue:s=360x640:d=1.5:r=30",
                    "-f", "lavfi", "-i", "testsrc2=s=360x640:d=2:r=30",
                    "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0,format=yuv420p", str(v)], check=True)
    res = RF.analyze(str(v), tmp_path / "references" / "ref", bands=[(0.6, 0.7)], motion=False)
    assert res["aspect"] == "9x16" and res["audio"]["present"] is False
    assert res["cuts"]["shots"] == 3 and res["cuts"]["first_cut_s"] == pytest.approx(1.5, abs=0.1)
    assert (tmp_path / "references" / "ref" / "reference.json").exists() and res["sheets"]["contact_1fps"]


# --- 1.4.7: ilk turda aç kalan konsept sonraki teste taşınır ----------------------------------
def test_no_carry_over_when_spend_is_balanced(store):
    an = CO.analyze(_scale_snapshot(store, structure="bootstrap")["path"])
    assert not any(d.get("carry_over") for d in an["decisions"])  # A ve B eşit harcıyor


def test_bootstrap_starved_concept_is_carry_over(store):
    from test_analytics import build_campaign
    pid, cid, cyid = build_campaign(store)  # C konsepti ilk turda aç bırakılmış
    an = CO.analyze(store.decision_input_snapshot(pid, cid, cyid)["path"])
    c = {d["concept"]: d for d in an["decisions"]}["C"]
    assert c["carry_over"] and c["decision"] == "tut" and "yeniden çekim" in c["why"]


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg yok")
def test_carry_over_reexport_keeps_audio(tmp_path):
    import export as EX
    from admem import naming
    src = tmp_path / "eski.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=360x640:d=2:r=30",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(src)], check=True)
    key = naming.build_key("MRKA", "K1", "A", "video", 15, "h1", True, "real", 2, 1)
    out = EX.export_video(str(src), str(src), tmp_path / "out", key, "9x16")
    streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", out["out"]],
                             capture_output=True, text=True).stdout.split()
    assert "audio" in streams and "video" in streams and "_c2_" in Path(out["out"]).name
