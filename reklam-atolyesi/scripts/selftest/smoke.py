"""Sentetik duman testi (spec 12.12): gerçek marka/hesap olmadan, <data_dir>/.selftest/ içinde uçtan uca.

Adımlar: 1 profiller ve yalıtım · 2 aşama makinesi, hızlı tur, geri dönüş, tur takvimi · 3 4K dikey klipler (VFR, HLG, sarsıntılı) ve
fotoğraf → ingest → analiz, malzeme haritası, çekim kütüphanesi · 4 sentetik kurgu planından 15 sn render (9:16 + 4:5, 1:1 yolu),
Türkçe karakter, sahne başına farklı audio.mode → miks (-14 LUFS, ≤ -1 dBTP) → öz denetim (efekt bütçesi aşımı yakalanır) → varyasyon
yaması → teknik QC; ayrıca bir sahne final kalite ve ölçek 1 · 5 sentetik metrik CSV → içe alma → koçluk → öğrenme · 6 hafıza ·
7 hata senaryoları · 8 rekabet · 9 ElevenLabs/Meta'ya hiçbir çağrı yapılmaz.
Fikstürler nötrdür ("Marka A", "Ürün A", "Örnek başlık"); test bitince .selftest silinir (--keep ile tutulur).

Kullanım: smoke.py --data-dir <data_dir> --out <sonuç.json> [--keep] [--only 3,4]
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "servers" / "ad_memory"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
for _sub in ("analytics", "audio", "analyze", "compose", "competitive", "ingest", "meta", "qc", "render", "selftest"):
    sys.path.insert(0, str(ROOT / "scripts" / _sub))

from common import ffmpeg, safe_rmtree, sha256_file, write_json  # noqa: E402


class Ctx:
    def __init__(self, data_dir: Path, base: Path):
        self.data_dir = data_dir
        self.base = base
        self.store = None
        self.shared: dict = {}


def _pytest(ctx: Ctx, label: str, targets: list[str], kexpr: str | None = None) -> dict:
    bt = ctx.base / "pytest" / label
    bt.parent.mkdir(parents=True, exist_ok=True)
    args = [sys.executable, "-m", "pytest", *targets, "-q", "-p", "no:cacheprovider", f"--basetemp={bt}"]
    if kexpr:
        args += ["-k", kexpr]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(args, cwd=str(ROOT), capture_output=True, timeout=1800, env=env)
    out = r.stdout.decode("utf-8", "replace")
    m = re.search(r"(\d+) passed", out)
    f = re.search(r"(\d+) failed", out)
    e = re.search(r"(\d+) error", out)
    res = {"targets": targets, "k": kexpr, "passed": int(m.group(1)) if m else 0, "failed": int(f.group(1)) if f else 0,
           "errors": int(e.group(1)) if e else 0, "returncode": r.returncode}
    if r.returncode != 0:
        res["tail"] = out[-3000:]
    assert r.returncode == 0, f"pytest {label} başarısız: {res}"
    return res


def _active_profile(s, name: str, account: str, product: str) -> dict:
    p = s.profile_create(name, synthetic=True)
    s.brand_upsert(p["id"], name=name, meta_ad_account_id=account, timezone="Europe/Istanbul", tone="nötr")
    s.profile_update(p["id"], meta_data_mode="csv", history_status="no_history")
    s.stage_start(p["id"], "S00a")
    f = s.profile_dir(p["id"]) / "brand" / "marka-ozeti.md"
    f.write_text("Marka A özeti (sentetik)", encoding="utf-8")
    r = s.stage_complete(p["id"], "S00a", [{"path": str(f)}], "marka tanışması (sentetik)")
    s.gate_approve(p["id"], r["stage_run"]["id"], r["stage_run"]["output_version"], "onaylıyorum (duman testi)")
    s.profile_update(p["id"], status="active")
    prod = s.product_upsert(p["id"], product, price=100, currency="TRY",
                            economics_json={"contribution": 40, "confirmed": True, "net_basket": 120},
                            provable_claims_json=[{"code": "c1", "text": "Örnek iddia", "proof_type": "process", "documented": True}],
                            occasions_json=[{"code": "an-a", "label": "Örnek an"}])
    pf = s.profile_dir(p["id"]) / "products" / "urun-karti.md"
    pf.write_text("Ürün A kartı (sentetik)", encoding="utf-8")
    r = s.stage_complete(p["id"], "S00c", [{"path": str(pf)}], "ürün tanışması (sentetik)", scope_key=f"product:{prod['id']}")
    s.gate_approve(p["id"], r["stage_run"]["id"], r["stage_run"]["output_version"], "onaylıyorum (duman testi)")
    return {"profile_id": p["id"], "product_id": prod["id"]}


# --- 1 ---------------------------------------------------------------------------------------------------------------
def step1_profiles(ctx: Ctx) -> dict:
    from admem.store import Store
    from admem.util import AdMemoryError
    s = Store(ctx.base / "db" / "ad-memory.sqlite", ctx.base)
    ctx.store = s
    n0 = s.profile_list(include_synthetic=True)["count"]
    a = _active_profile(s, "Marka A", "act_SELFTEST_A", "Ürün A")
    n1 = s.profile_list(include_synthetic=True)["count"]
    b = _active_profile(s, "Marka B", "act_SELFTEST_B", "Ürün B")
    s.profile_set_active(a["profile_id"])
    isolation_ok = False
    try:
        s.meta_entities_upsert(b["profile_id"], "act_SELFTEST_A", [{"level": "campaign", "meta_id": "c1", "name": "x"}])
    except AdMemoryError:
        isolation_ok = True
    dup_ok = False
    try:
        s.brand_upsert(b["profile_id"], meta_ad_account_id="act_SELFTEST_A")
    except AdMemoryError:
        dup_ok = True
    ctx.shared.update(a=a, b=b)
    unit = _pytest(ctx, "s1", ["tests/test_store_stage.py"], "profile or isolation or explicit or activation")
    assert n0 == 0 and n1 == 1 and isolation_ok and dup_ok
    return {"profiles_0_to_1": [n0, n1], "meta_isolation": isolation_ok, "same_account_rejected": dup_ok, "unit": unit}


# --- 2 ---------------------------------------------------------------------------------------------------------------
def step2_stage_machine(ctx: Ctx) -> dict:
    import budget as BU
    base = {"cycle_no": 1, "adset_daily": 300, "exploration_share": 0.2, "cpm": 60, "cpm_source": "assumption", "decision_metric": "hook",
            "budget_total": None, "spend_to_date": 0, "data_cutoff": "2026-03-01", "launch_at": "2026-03-07", "risk_per_ad": 200,
            "result_type": "purchase", "test_start_hour": 0, "creative_test_tool_max": 5}
    p7 = BU.plan(base)
    p14 = BU.plan({**base, "adset_daily": 9})
    slip = BU.plan({**base, "launch_at": "2026-03-10"})
    stable = BU.plan({**base, "cycle_no": 2, "adset_daily": 1500})
    assert p7["test_days"] == 7 and p7["cycle_days"] == 14, p7
    assert p14["test_days"] == 14 and p14["cycle_days"] == 21, p14
    assert slip["calendar"]["plan_day"] != p7["calendar"]["plan_day"]
    unit = _pytest(ctx, "s2", ["tests/test_store_stage.py"],
                   "full_machine or quick_mode or back_marks or cycle_rolls or s01b_skip or gate_bound or s02_blocked")
    return {"calendar_7_14": p7["calendar"], "calendar_14_21": p14["calendar"], "slip_recomputed": slip["calendar"],
            "stable_cycle_test_days": stable["test_days"], "unit": unit}


# --- 3 ---------------------------------------------------------------------------------------------------------------
def step3_media(ctx: Ctx) -> dict:
    import contact_sheet as CS
    import convert as CV
    import fixtures as FX
    import material_map as MM
    import measure as ME
    s = ctx.store
    a = ctx.shared["a"]
    pid = a["profile_id"]
    c = s.campaign_create(pid, a["product_id"], "Kampanya A")
    cid, cyid = c["campaign"]["id"], c["cycle"]["id"]
    cdir = Path(c["dir"])
    raw, praw = cdir / "footage" / "raw", cdir / "photos" / "raw"
    W, H = 2160, 3840  # dikey 4K
    FX.clip_plain(raw / "S01_t1.mov", W, H, 4.0, audio="speechlike")
    FX.clip_vfr(raw / "S02_t1.mov", W, H, 4.0)
    FX.clip_hlg(raw / "S03_t1.mov", W, H, 3.2)
    FX.clip_shaky(raw / "S04_t1.mov", W, H, 4.0)
    FX.photo_exif(praw / "F01.jpg")
    FX.photo_heic(praw / "F02.heic")
    raw_hash_before = {p.name: sha256_file(p) for p in raw.iterdir()}
    man = CV.ingest(cdir, 30, fast=True)
    assert not man["errors"], man["errors"]
    m = json.loads(Path(man["manifest"]).read_text(encoding="utf-8"))
    notes = {Path(f["source"]).name: f["notes"] for f in m["footage"]}
    assert any("VFR" in n for n in notes["S02_t1.mov"]) and any("SDR" in n for n in notes["S03_t1.mov"])
    shaky = next(f for f in m["footage"] if f["source"].endswith("S04_t1.mov"))
    assert shaky["stabilized"] and Path(shaky["stabilized"]).exists(), shaky["shake"]
    assert {p.name: sha256_file(p) for p in raw.iterdir()} == raw_hash_before, "ham çekim değişti"
    assets, clips = {}, []
    for f in m["footage"]:
        shot = Path(f["source"]).stem.split("_")[0]
        vm = ME.video_metrics(f["proxy"])
        am = ME.audio_metrics(f["audio_wav"]) if f.get("audio_wav") else None
        sc = ME.scores(vm, f["shake"]["shake_permille"], am)
        br = ME.best_ranges(vm)
        sheet = CS.sheet(f["proxy"], str(cdir / "analysis" / f"{shot}_sheet.jpg"))
        rec = s.asset_register(pid, "footage", f["cfr_sdr"], campaign_id=cid, product_id=a["product_id"], source="shoot", shot_no=shot,
                               score=sc, best_ranges=br, audio={"wav": f.get("audio_wav")}, meta={"proxy": f["proxy"], "stabilized": f["stabilized"]})
        assets[shot] = {"cfr_sdr": f["cfr_sdr"], "proxy": f["proxy"], "stabilized": f["stabilized"], "use_stabilized": bool(f["stabilized"]),
                        "wav": f.get("audio_wav"), "asset_id": rec["id"]}
        clips.append({"asset": rec["id"], "shot_no": shot, "score": sc, "best_ranges": br, "used_in": [], "path": f["cfr_sdr"]})
        assert Path(sheet["sheet"]).exists()
    for ph in m["photos"]:
        s.asset_register(pid, "photo", ph["output"], campaign_id=cid, product_id=a["product_id"], source="shoot")
    menu = [{"no": n, "concept": "A", "what": f"Örnek çekim {n}", "hook": "h1" if n == "S01" else None, "ai_ok": n == "S05",
             "real_twin_for": None} for n in ("S01", "S02", "S03", "S04", "S05")]
    mm = MM.build(menu, clips)
    (cdir / "analysis" / "material-map.md").write_text(MM.to_md(mm), encoding="utf-8")
    lib = s.asset_query(pid, scope="profile", kind="footage")
    n_lib = len(lib.get("assets", lib if isinstance(lib, list) else []))
    ctx.shared.update(campaign_id=cid, cycle_id=cyid, cdir=cdir, assets=assets)
    assert n_lib >= 4
    return {"footage": man["footage"], "photos": man["photos"], "notes": notes, "shake": shaky["shake"],
            "material_map_missing": mm.get("missing"), "library_assets": n_lib}


# --- 4 ---------------------------------------------------------------------------------------------------------------
def _plan(fmt: str, style_path: Path, style_sha: str) -> dict:
    T = "Örnek başlık ğüşıİçö ĞÜŞIİÇÖ"

    def vid(asset, a, b, zoom=1.0, preset=None):
        return {"type": "video", "source": {"kind": "footage", "asset": asset, "in_s": a, "out_s": b},
                "camera": {"preset": preset or ("kenburns_in" if zoom > 1 else "static"), "zoom": zoom}}
    return {"campaign": "kampanya-a", "cycle_id": 1, "concept": "A", "hook": "h1", "format": fmt, "purpose": "production", "status": "ready",
            "version": 1, "style_snapshot_sha256": style_sha, "duration_s": 15, "fps": 30, "style": str(style_path),
            "music": {"asset": "mus_sentetik", "offset_s": 0.0, "gain_db": -8}, "vo": {"asset": "vo_sentetik"}, "captions": {"on": False},
            "scenes": [
                {"id": "s1", "role": "hook", "start_s": 0.0, "dur_s": 3.0, "audio": {"mode": "original", "decision_id": "d1"},
                 "layers": [vid("S01", 0.5, 3.5, 1.1), {"type": "text", "preset": "text_reveal", "text": T, "anchor": "safe_top"}],
                 "transition_out": {"type": "crossfade", "dur_s": 0.3}},
                {"id": "s2", "role": "context", "start_s": 3.0, "dur_s": 3.0, "audio": {"mode": "original_clean", "decision_id": "d2"},
                 "layers": [vid("S02", 0.2, 3.2, 1.12, "punch_in")], "audio_cues": [{"sfx": "sfx_01", "at_s": 0.1}]},
                {"id": "s3", "role": "reveal", "start_s": 6.0, "dur_s": 3.0, "beat_lock": "downbeat", "audio": {"mode": "none", "decision_id": "d3"},
                 "layers": [vid("S03", 0.0, 3.0), {"type": "component", "component": "LightRays"},
                            {"type": "text", "preset": "kinetic", "text": "Ürün A", "anchor": "safe_top"}]},
                {"id": "s4", "role": "process", "start_s": 9.0, "dur_s": 3.0, "audio": {"mode": "user_vo", "decision_id": "d4", "user_vo_asset": "kullanici_kaydi_sentetik"},
                 "layers": [vid("S04", 0.5, 3.5)], "transition_out": {"type": "crossfade", "dur_s": 0.3}},
                {"id": "s5", "role": "endcard", "start_s": 12.0, "dur_s": 3.0, "audio": {"mode": "generated", "decision_id": "d5"},
                 "layers": [{"type": "component", "component": "EndCard", "props": {"brand": "Marka A", "cta": "Örnek çağrı", "url": "ornek.test"}}]}],
            "provenance": {"ai_share": 0.0, "ai_layers": []}}


def step4_render(ctx: Ctx) -> dict:
    import beats as BE
    import checks as QC
    import fixtures as FX
    import loudness as LN
    import mix as MX
    import render as RE
    import scenes as SCN
    import self_review as SR
    import sfx_synth as SY
    from admem import editplan
    from admem import naming
    import export as EX
    s = ctx.store
    cdir: Path = ctx.shared["cdir"]
    assets = ctx.shared["assets"]
    work = cdir / "selftest"
    work.mkdir(parents=True, exist_ok=True)
    style_path = work / "style.json"
    shutil.copy2(ROOT / "templates" / "style.json", style_path)
    style = json.loads(style_path.read_text(encoding="utf-8"))
    style_sha = sha256_file(style_path)
    music = FX.click_track(work / "music.wav", 120.0, 17.0)
    vo = FX.noisy_voice(work / "kullanici_kaydi_sentetik.wav", 15.0)
    whoosh = SY.write(str(work / "whoosh.wav"), SY.synth("whoosh", 0.4))["out"]
    bt = BE.analyze(str(music))
    beats = bt["beats"]
    out: dict = {"tempo": bt["tempo_bpm"]}
    project = cdir / "src"
    plans = {}
    for fmt in ("9x16", "4x5"):
        p = _plan(fmt, style_path, style_sha)
        v = editplan.validate(p, style=style, beats=beats)
        assert v["valid"], (fmt, v["errors"])
        plans[fmt] = p
    p916 = plans["9x16"]
    sm = SCN.build(p916, assets, cdir / "footage" / "scenes", "proxy", style, str(style_path), fast=True)
    t0 = time.time()
    r916 = RE.render_plan(ctx.data_dir, project, p916, work / "taslak_916.mp4", style, str(style_path), sm, None, "preview", 1, None, True, beats)
    out["render_916"] = {"ms": r916["ms"], "segments": r916["segments_total"], "scale": r916["scale"]}
    sm45 = SCN.build(plans["4x5"], assets, cdir / "footage" / "scenes", "proxy", style, str(style_path), fast=True)
    r45 = RE.render_plan(ctx.data_dir, project, plans["4x5"], work / "taslak_45.mp4", style, str(style_path), sm45, None, "preview", 1, None, True, beats)
    out["render_45"] = {"ms": r45["ms"], "segments": r45["segments_total"]}
    p11 = copy.deepcopy(p916)
    p11["format"] = "1x1"
    p11["captions"] = {"on": True, "preset": "keyword_upper"}  # vurgulu altyazı + Türkçe büyük harf (1.5.0) gerçek render'da
    import words_align as WA
    cap = WA.chunks([{"text": t, "start": 6.0 + i * 0.3, "end": 6.3 + i * 0.3} for i, t in enumerate(["İğne", "iplik", "şimdi", "850", "TL."])])
    sm11 = SCN.build(p11, assets, cdir / "footage" / "scenes", "proxy", style, str(style_path), fast=True)
    r11 = RE.render_plan(ctx.data_dir, project, p11, work / "kare_11.png", style, str(style_path), sm11, cap, "preview", 1, 200, True, beats)
    assert Path(r11["out"]).exists()
    out["render_11_still"] = r11["out"]
    # ses: sahne başına farklı audio.mode
    mx = MX.mix(p916, sm["audio_segments"], str(music), str(vo), {"sfx_01": whoosh}, work / "stems")
    assert mx["loudness_ok"], mx["loudness"]
    modes = {x["mode"] for x in mx["applied_modes"]}
    assert modes == {"original", "original_clean", "none", "user_vo", "generated"}, modes
    out["mix"] = {"loudness": mx["loudness"], "modes": sorted(modes)}
    # export + teknik QC (önizleme; çözünürlük final'de ayrıca)
    key = naming.build_key("MRKA", "K1", "A", "video", 15, "h1", True, "real", 1, 1)
    ex = EX.export_video(str(work / "taslak_916.mp4"), mx["final"], work / "out", key, "9x16")
    tq = QC.tech(ex["out"], None, 15, None)
    failed = [c for c in tq["checks"] if not c["ok"]]
    assert not failed, failed
    assert QC.safe_zone(p916, style)["ok"]
    out["tech_qc_preview"] = {"ok": tq["ok"], "file": ex["file_name"]}
    # öz denetim + efekt bütçesi aşımının yakalanması
    rv = SR.review(ex["out"], p916, work / "review_r1", style, beats, 1)
    assert not [f for f in rv["numeric_findings"] if f["kind"] == "plan"], rv["numeric_findings"]
    bad = copy.deepcopy(p916)
    bad["scenes"][4]["layers"].append({"type": "component", "component": "ParticleSwirl"})
    bad["scenes"][1]["transition_out"] = {"type": "whipPan", "dur_s": 0.3}
    bad["scenes"][2]["transition_out"] = {"type": "filmBurn", "dur_s": 0.3}
    rb = SR.review(ex["out"], bad, work / "review_bad", style, beats, 2)
    caught = [f["msg"] for f in rb["numeric_findings"] if f["kind"] == "plan"]
    assert any("imza" in m for m in caught) and any("geçiş" in m for m in caught), caught
    out["self_review"] = {"frames": rv["frames_to_inspect"], "effect_budget_caught": caught}
    # varyasyon yaması: 15 → 6 sn
    p6 = editplan.apply_patch(p916, [{"op": "trim", "duration_s": 6}])
    assert editplan.validate(p6, style=style)["valid"]
    sm6 = SCN.build(p6, assets, cdir / "footage" / "scenes", "proxy", style, str(style_path), fast=True)
    r6 = RE.render_plan(ctx.data_dir, project, p6, work / "varyasyon_6sn.mp4", style, str(style_path), sm6, None, "preview", 1, None, True, beats)
    tq6 = QC.tech(r6["out"], None, 6, None)
    assert all(c["ok"] for c in tq6["checks"] if c["check"] not in ("ses",)), tq6
    out["variant_6s"] = {"version": p6["version"], "ms": r6["ms"]}
    # bir sahne final kalite, ölçek 1 (4K kaynaktan final ara dosya)
    pf = copy.deepcopy(p916)
    pf["scenes"] = [copy.deepcopy(p916["scenes"][0])]
    pf["scenes"][0]["transition_out"] = None
    pf["scenes"][0].pop("transition_out")
    pf["duration_s"] = 3.0
    smf = SCN.build(pf, assets, cdir / "footage" / "scenes", "final", style, str(style_path), fast=True)
    seg = next(iter(smf["scenes"]["s1"].values()))
    assert seg["width"] >= 1080 and seg["height"] >= 1920, seg
    rf = RE.render_plan(ctx.data_dir, project, pf, work / "final_sahne.mp4", style, str(style_path), smf, None, "final", 1, None, True, beats)
    a3 = work / "mix_3sn.wav"
    ffmpeg(["-i", mx["final"], "-t", "3", "-c:a", "pcm_s16le", str(work / "mix_3sn_raw.wav")])
    LN.loudnorm(str(work / "mix_3sn_raw.wav"), str(a3))
    keyf = naming.build_key("MRKA", "K1", "A", "video", 3, "h1", True, "real", 1, 2)
    exf = EX.export_video(rf["out"], str(a3), work / "out", keyf, "9x16")
    tqf = QC.tech(exf["out"], None, 3, "9x16")
    bad_f = [c for c in tqf["checks"] if not c["ok"] and c["check"] not in ("loudness -14 LUFS ±1",)]
    assert not bad_f, bad_f
    out["final_scene"] = {"resolution_ok": next(c for c in tqf["checks"] if c["check"] == "çözünürlük")["ok"], "scale": rf["scale"],
                          "intermediate": [seg["width"], seg["height"]]}
    return out


# --- 5–8 -------------------------------------------------------------------------------------------------------------
def step5_coaching(ctx: Ctx) -> dict:
    import meta_tools as MT
    s = ctx.store
    a = ctx.shared["a"]
    csv = ctx.base / "sentetik_meta.csv"
    MT.synth_csv(str(csv), 3, 10, 1729, "2026-01-05")
    chk = MT.csv_check(str(csv))
    ctx_m = {"account_id": "act_SELFTEST_A", "timezone": "Europe/Istanbul", "currency": "TRY", "result_definition": "purchase",
             "metric_definitions": {"hook_rate": "video_3s/impressions"}, "attribution_window": "7d_click_1d_view",
             "action_report_time": "impression"}
    imp = s.metrics_import_csv(a["profile_id"], str(csv), ctx_m)
    unit = _pytest(ctx, "s5", ["tests/test_metrics.py", "tests/test_analytics.py"])
    return {"csv_check": {k: chk[k] for k in chk if k in ("ok", "rows", "date_range")}, "import": {k: imp.get(k) for k in ("inserted", "updated", "rows")},
            "unit": unit}


def step6_memory(ctx: Ctx) -> dict:
    return {"unit": _pytest(ctx, "s6", ["tests/test_memory.py", "tests/test_store_stage.py"], "memory or checkpoint or resume or test_memory")}


def step7_errors(ctx: Ctx) -> dict:
    return {"unit": _pytest(ctx, "s7", ["tests/test_generation.py", "tests/test_hooks.py", "tests/test_store_stage.py"],
                            "generation or reservation or hook or cost or meta or gate or jobs or runtime or risk")}


def step8_competitive(ctx: Ctx) -> dict:
    return {"unit": _pytest(ctx, "s8", ["tests/test_competitive.py", "tests/test_editplan.py", "tests/test_hooks.py"],
                            "competitive or snapshot or diff or map or distance or strategy or taxonomy or differentiator or competitor or library")}


def step9_no_external(ctx: Ctx) -> dict:
    # Duman testi yalnızca yerel Store, script'ler ve Remotion/FFmpeg kullanır; ElevenLabs ve Meta MCP araçları hiç çağrılmaz.
    src = Path(__file__).read_text(encoding="utf-8")
    forbidden = [w for w in ("creative_generate", "ads_get_", "ads_library_search(", "urllib.request", "requests.") if w in src.split("def step9")[0]]
    assert not forbidden, forbidden
    return {"external_calls": 0, "note": "OAuth henüz yok; canlı kısım ilk açılışta (12.10)."}


STEPS = [(1, "profiller ve yalıtım", step1_profiles), (2, "aşama makinesi ve takvim", step2_stage_machine),
         (3, "ingest ve analiz (4K dikey)", step3_media), (4, "render, ses, öz denetim, varyasyon, QC", step4_render),
         (5, "metrik CSV ve koçluk", step5_coaching), (6, "hafıza", step6_memory), (7, "hata senaryoları", step7_errors),
         (8, "rekabet", step8_competitive), (9, "dış çağrı yok", step9_no_external)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args()
    data_dir = Path(a.data_dir).resolve()
    base = data_dir / ".selftest"
    if base.exists():
        safe_rmtree(base)
    base.mkdir(parents=True)
    ctx = Ctx(data_dir, base)
    only = {int(x) for x in a.only.split(",")} if a.only else None
    results = []
    t_all = time.time()
    for no, title, fn in STEPS:
        if only and no not in only and no not in (1,):
            continue
        t0 = time.time()
        try:
            det = fn(ctx)
            results.append({"step": no, "title": title, "ok": True, "seconds": round(time.time() - t0, 1), "detail": det})
        except (Exception, SystemExit) as e:  # adım hatası raporlanır, sonraki adımlar denenir
            results.append({"step": no, "title": title, "ok": False, "seconds": round(time.time() - t0, 1),
                            "error": f"{type(e).__name__}: {e}"[:4000], "trace": traceback.format_exc()[-4000:]})
    if ctx.store is not None:
        ctx.store.close()
    summary = {"ok": all(r["ok"] for r in results) and (only is None), "partial": only is not None,
               "seconds": round(time.time() - t_all, 1), "steps": results, "selftest_dir_removed": not a.keep}
    if not a.keep:
        safe_rmtree(base)
    write_json(a.out, summary)
    print(json.dumps({"ok": summary["ok"], "steps": [(r["step"], r["ok"], r["seconds"]) for r in results]}, ensure_ascii=False))
    sys.exit(0 if all(r["ok"] for r in results) else 1)


if __name__ == "__main__":
    main()
