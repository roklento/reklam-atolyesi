"""Render orkestrasyonu (spec 5.12, 5.15, 5.21).

Alt komutlar:
  init     --project <campaign>/src                        şablonu kampanyaya kopyalar (var olan özelleştirilmiş dosyalar korunur)
  plan     --data-dir D --project P --plan plan.json --out x.mp4 [--style s.json] [--scene-map m.json] [--captions w.json]
           [--quality preview|final] [--parallel-jobs J] [--still N] [--no-cache]
  gallery  --data-dir D --work W --out gallery.png [--components A,B]   (bileşen başına 1 sabit kare + 2 sn test, galeride 4 kare)
  turkish  --data-dir D --work W --out tr.mp4                           (final 2 sn 1080×1920, Türkçe karakterler)
Önizleme 0,5 ölçek (tek sayılar çift sayıya yuvarlanır); final ölçek 1, final ara dosyalardan. Toplam işçi bütçesi
max(1, floor(CPU/2)); dışarıda J paralel render varsa her birinin concurrency'si floor(bütçe/J). Bellek hatasında 1 ile yeniden dener.
Sahne önbelleği: sahne başına segment (frameRange) anahtarla saklanır; değişmeyen sahne yeniden render edilmez; segmentler kayıpsız birleştirilir.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "compose"))
from common import PLUGIN_ROOT, emit, ffmpeg, per_render_concurrency, read_json, render_budget, run, sha256_file, write_json  # noqa: E402
import scene_cache as SC  # noqa: E402

TEMPLATE = PLUGIN_ROOT / "templates" / "remotion"
RENDER_MJS = Path(__file__).resolve().parent / "render.mjs"
COMP = {"9x16": "Master-916", "4x5": "Master-45", "1x1": "Master-11"}


def init_project(project: Path, force_library: bool = False) -> dict:
    """Şablonun src/ içeriğini kampanya projesine kopyalar. Kütüphane dosyaları force_library ile tazelenir; kampanyaya özel dosyalar korunur."""
    project.mkdir(parents=True, exist_ok=True)
    copied = []
    for f in (TEMPLATE / "src").rglob("*"):
        if not f.is_file():
            continue
        dst = project / f.relative_to(TEMPLATE / "src")
        if dst.exists() and not (force_library and "components" in dst.parts):
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
        copied.append(str(dst.relative_to(project)))
    (project / "public").mkdir(exist_ok=True)
    return {"project": str(project), "copied": len(copied)}


def node_dirs(data_dir: Path) -> tuple[Path, Path]:
    nd = data_dir / ".node"
    nm = nd / "node_modules"
    if not (nm / "remotion").exists():
        raise SystemExit(f"Remotion bağımlılıkları yok: {nm} (kurulum 12.6)")
    return nd, nm


def run_node(data_dir: Path, cfg: dict) -> dict:
    nd, nm = node_dirs(data_dir)
    cfg = {**cfg, "nodeModules": str(nm)}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8", dir=str(nd)) as fh:
        json.dump(cfg, fh, ensure_ascii=False)
        cfg_path = fh.name
    try:
        r = run(["node", str(RENDER_MJS), cfg_path], cwd=str(nd), check=False, timeout=3600)
    finally:
        Path(cfg_path).unlink(missing_ok=True)
    line = (r.stdout.strip().splitlines() or ["{}"])[-1]
    try:
        res = json.loads(line)
    except json.JSONDecodeError:
        res = {"ok": False, "error": (r.stderr or r.stdout)[-3000:]}
    if not res.get("ok"):
        err = str(res.get("error", ""))
        if any(k in err.lower() for k in ("out of memory", "enomem", "oom", "allocation failed", "target closed")) and not cfg.get("_retried"):
            for j in cfg["jobs"]:
                j["concurrency"] = 1
            return run_node(data_dir, {**cfg, "_retried": True})
        raise SystemExit(f"render başarısız: {err[:2000]}")
    return res


def _even_scale(fmt: str, scale: float) -> float:
    """Önizleme ölçeği (5.21). Remotion H.264'te kompozisyon boyutunu round(boyut × ölçek) çift olana dek kendisi küçültür
    (4:5 → 1080×1348 × 0,5 = 540×674); bu yüzden ölçek düz verilir. Ölçeği burada büyütmek (ör. 0,5007) tam sayı olmayan
    piksel boyutu üretir ve render'ı bozar."""
    w, h = {"9x16": (1080, 1920), "4x5": (1080, 1350), "1x1": (1080, 1080)}[fmt]
    for d in (w, h):  # Remotion'ın yuvarlamasından sonra boyut × ölçek tam sayı olmalı
        dd = d
        while round(dd * scale) % 2 != 0 or abs(dd * scale - round(dd * scale)) > 1e-9:
            dd -= 1
            if dd <= 0:
                raise SystemExit(f"geçersiz önizleme ölçeği: {scale}")
    return scale


def stage_public(project: Path, scene_map: dict | None) -> dict:
    """Sahne ara dosyalarını public/ altına koyar; inputProps için göreli yollar döner."""
    assets: dict[str, dict[str, str]] = {}
    if not scene_map:
        return assets
    pub = project / "public" / "scenes"
    pub.mkdir(parents=True, exist_ok=True)
    for sid, layers in (scene_map.get("scenes") or {}).items():
        for li, info in layers.items():
            src = Path(info["path"])
            dst = pub / src.name
            if not dst.exists() or dst.stat().st_size != src.stat().st_size:
                try:
                    if dst.exists():
                        dst.unlink()
                    dst.hardlink_to(src)
                except OSError:
                    shutil.copy2(src, dst)
            assets.setdefault(sid, {})[str(li)] = f"scenes/{src.name}"
    return assets


def render_plan(data_dir: Path, project: Path, plan: dict, out: Path, style: dict | None, style_path: str | None, scene_map: dict | None,
                captions: list | None, quality: str, parallel_jobs: int, still: int | None, use_cache: bool, beats: list | None) -> dict:
    if quality == "final" and plan.get("status") != "ready":
        raise SystemExit("taslak (draft) plan final render edilemez (5.2)")
    init_project(project)
    assets = stage_public(project, scene_map)
    scale = 1.0 if quality == "final" else _even_scale(plan["format"], 0.5)
    props = {"plan": plan, "style": style, "assets": assets, "captions": captions or [], "preview": quality != "final", "beats": beats or []}
    comp = COMP[plan["format"]]
    conc = per_render_concurrency(parallel_jobs)
    base = {"entry": str(project / "index.ts"), "publicDir": str(project / "public"), "bundleOut": str(project / ".bundle")}
    t0 = time.time()
    if still is not None:
        res = run_node(data_dir, {**base, "jobs": [{"composition": comp, "inputProps": props, "out": str(out), "still": still, "scale": scale, "quality": quality}]})
        return {"out": str(out), "still": still, "ms": int((time.time() - t0) * 1000), "results": res["results"]}
    fps = plan["fps"]
    seg_dir = project / ".segments"
    seg_dir.mkdir(exist_ok=True)
    src_hashes = {}
    for sid, layers in (scene_map or {}).get("scenes", {}).items():
        for li, info in layers.items():
            src_hashes[f"{sid}:{li}"] = sha256_file(info["path"])
    style_sha = sha256_file(style_path) if style_path else None
    lock = SC.lock_versions(data_dir / ".node")
    segments, jobs = [], []
    for i, s in enumerate(plan["scenes"]):
        a = round(s["start_s"] * fps)
        b = round((s["start_s"] + s["dur_s"]) * fps) - 1
        key = SC.scene_key(plan, i, source_hashes=src_hashes, style_sha=style_sha, quality=quality, scale=scale, render_versions=lock,
                           audio_sha=None, beats_sha=None)
        seg = seg_dir / f"{s['id']}_{quality}_{key[:20]}.mp4"
        segments.append(seg)
        if use_cache and SC.cached(seg):
            continue
        jobs.append({"composition": comp, "inputProps": props, "out": str(seg), "frameRange": [a, b], "scale": scale, "quality": quality,
                     "concurrency": conc})
    res = run_node(data_dir, {**base, "jobs": jobs}) if jobs else {"results": []}
    for j in jobs:
        SC.mark_done(Path(j["out"]))
    listfile = seg_dir / f"concat_{out.stem}.txt"
    listfile.write_text("".join(f"file '{p.as_posix()}'\n" for p in segments), encoding="utf-8")
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listfile), "-c", "copy", "-movflags", "+faststart", str(out)])
    ms = int((time.time() - t0) * 1000)
    return {"out": str(out), "sha256": sha256_file(out), "quality": quality, "scale": scale, "concurrency": conc, "render_budget": render_budget(),
            "segments_total": len(segments), "segments_rendered": len(jobs), "segments_reused": len(segments) - len(jobs), "ms": ms,
            "timing_record": {"format": plan["format"], "scenes": len(plan["scenes"]), "quality": quality, "ms": ms,
                              "glsl": any(l.get("component") in ("LightRays", "ParticleSwirl", "HeatShimmer") for s in plan["scenes"] for l in s["layers"])}}


def gallery(data_dir: Path, work: Path, out: Path, names: list[str] | None, parallel_jobs: int = 1) -> dict:
    """Her bileşen: 1 sabit kare + 2 sn test; galeri her bileşen için 2 sn testten eşit aralıklı 4 kare gösterir (5.12)."""
    from PIL import Image, ImageDraw, ImageFont
    proj = work / "gallery_project"
    init_project(proj, force_library=True)
    reg = (PLUGIN_ROOT / "templates" / "remotion" / "src" / "components")
    if names is None:
        import re
        names = []
        for f in sorted(reg.glob("*.tsx")):
            names += re.findall(r'name:\s*"([A-Z][A-Za-z0-9]+)"', f.read_text(encoding="utf-8"))
        tr = (reg / "transition.tsx").read_text(encoding="utf-8")
        names += re.findall(r'\["([A-Z][A-Za-z0-9]+)",\s*"[a-zA-Z]+",\s*"#', tr)
    names = list(dict.fromkeys(names))
    gdir = work / "gallery"
    gdir.mkdir(parents=True, exist_ok=True)
    conc = per_render_concurrency(parallel_jobs)
    jobs = []
    for n in names:
        jobs.append({"composition": "Gallery", "inputProps": {"component": n}, "out": str(gdir / f"{n}.png"), "still": 30, "scale": 1, "quality": "final"})
        jobs.append({"composition": "Gallery", "inputProps": {"component": n}, "out": str(gdir / f"{n}.mp4"), "scale": 1, "quality": "preview", "concurrency": conc})
    t0 = time.time()
    res = run_node(data_dir, {"entry": str(proj / "index.ts"), "publicDir": str(proj / "public"), "bundleOut": str(proj / ".bundle"), "jobs": jobs})
    tw, th = 180, 320
    cols_per_comp = 4
    comps_per_row = 2
    rows = (len(names) + comps_per_row - 1) // comps_per_row
    W = comps_per_row * (cols_per_comp * tw + 20)
    H = rows * (th + 30)
    canvas = Image.new("RGB", (W, H), (18, 18, 18))
    d = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.load_default(size=16)
    except TypeError:
        font = ImageFont.load_default()
    report = []
    for idx, n in enumerate(names):
        mp4 = gdir / f"{n}.mp4"
        ok = mp4.exists() and (gdir / f"{n}.png").exists()
        frames = []
        if ok:
            for k, t in enumerate((0.25, 0.75, 1.25, 1.75)):
                fp = gdir / f"{n}_f{k}.png"
                ffmpeg(["-ss", f"{t}", "-i", str(mp4), "-frames:v", "1", "-vf", f"scale={tw}:{th}", str(fp)], check=False)
                frames.append(fp)
        r, c = idx // comps_per_row, idx % comps_per_row
        x0, y0 = c * (cols_per_comp * tw + 20), r * (th + 30)
        d.text((x0 + 4, y0 + 4), n, fill=(240, 240, 240), font=font)
        black = 0
        for k, fp in enumerate(frames):
            if fp.exists():
                im = Image.open(fp).convert("RGB")
                canvas.paste(im, (x0 + k * tw, y0 + 26))
                if max(im.convert("L").getextrema()) < 12:
                    black += 1
        report.append({"component": n, "ok": ok and len(frames) == 4, "all_black_frames": black})
    canvas.save(out)
    write_json(work / "gallery_report.json", {"components": report, "ms": int((time.time() - t0) * 1000)})
    return {"gallery": str(out), "sha256": sha256_file(out), "components": len(names), "failed": [r["component"] for r in report if not r["ok"]],
            "frames_all_black": [r["component"] for r in report if r["all_black_frames"] == 4], "report": str(work / "gallery_report.json")}


def turkish(data_dir: Path, work: Path, out: Path) -> dict:
    proj = work / "tr_project"
    init_project(proj)
    res = run_node(data_dir, {"entry": str(proj / "index.ts"), "publicDir": str(proj / "public"), "bundleOut": str(proj / ".bundle"),
                              "jobs": [{"composition": "TurkishTest", "inputProps": {}, "out": str(out), "scale": 1, "quality": "final",
                                        "concurrency": per_render_concurrency(1)},
                                       {"composition": "TurkishTest", "inputProps": {}, "out": str(out.with_suffix(".png")), "still": 30, "scale": 1, "quality": "final"}]})
    return {"out": str(out), "still": str(out.with_suffix(".png")), "results": res["results"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("init")
    p.add_argument("--project", required=True)
    p.add_argument("--force-library", action="store_true")
    p = sp.add_parser("plan")
    for k in ("--data-dir", "--project", "--plan", "--out"):
        p.add_argument(k, required=True)
    p.add_argument("--style")
    p.add_argument("--scene-map")
    p.add_argument("--captions")
    p.add_argument("--beats")
    p.add_argument("--quality", choices=["preview", "final"], default="preview")
    p.add_argument("--parallel-jobs", type=int, default=1)
    p.add_argument("--still", type=int)
    p.add_argument("--no-cache", action="store_true")
    p = sp.add_parser("gallery")
    p.add_argument("--data-dir", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--components")
    p = sp.add_parser("turkish")
    p.add_argument("--data-dir", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "init":
        emit(init_project(Path(a.project), a.force_library))
    elif a.cmd == "plan":
        cap = read_json(a.captions) if a.captions else None
        if isinstance(cap, dict):
            cap = cap.get("captions")
        beats = read_json(a.beats) if a.beats else None
        if isinstance(beats, dict):
            beats = beats.get("beats")
        emit(render_plan(Path(a.data_dir), Path(a.project), read_json(a.plan), Path(a.out), read_json(a.style) if a.style else None, a.style,
                         read_json(a.scene_map) if a.scene_map else None, cap, a.quality, a.parallel_jobs, a.still, not a.no_cache, beats))
    elif a.cmd == "gallery":
        emit(gallery(Path(a.data_dir), Path(a.work), Path(a.out), a.components.split(",") if a.components else None))
    else:
        emit(turkish(Path(a.data_dir), Path(a.work), Path(a.out)))


if __name__ == "__main__":
    main()
