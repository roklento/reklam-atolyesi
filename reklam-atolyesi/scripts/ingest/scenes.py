"""Sahne ara dosyaları (spec 5.12): video katmanları Remotion'a ham 4K olarak verilmez.

Her sahnenin kullandığı aralık ffmpeg'de kesilir, klipler arası pozlama/beyaz dengesi eşitlemesi (1.7.0, analyze/color_match.py;
LUT'tan önce, style.json grade.match=false ile kapanır), renk ayarı (lut3d) ve gerekiyorsa sabitlenmiş kopya uygulanır, sahne başına bir
ara dosya üretilir: proxy için 1080 kısa kenar, final için sahnenin dijital yaklaşma payını taşıyan en küçük çözünürlük
(ör. 1,15× yaklaşma için kısa kenar ~1250 px; yaklaşma yoksa 1080). Çekim sesi kullanılan sahnelerde ses parçası ayrıca WAV olarak çıkar.

Kullanım: scenes.py --plan plan.json --assets asset_files.json --out-dir footage/scenes --quality proxy|final [--style style.json]
asset_files.json: {asset_anahtarı: {"cfr_sdr": yol, "proxy": yol, "stabilized": yol|null, "use_stabilized": bool}}
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "compose"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analyze"))
from common import emit, even, ffmpeg, read_json, sha256_file, write_json, x264_threads  # noqa: E402
import color_match as CM  # noqa: E402
from admem import editplan as EP  # noqa: E402
import scene_cache as SC  # noqa: E402

FORMAT_SIZE = {"9x16": (1080, 1920), "4x5": (1080, 1350), "1x1": (1080, 1080)}


def target_size(fmt: str, quality: str, zoom: float) -> tuple[int, int]:
    w, h = FORMAT_SIZE[fmt]
    if quality == "proxy":
        return w, h
    z = max(1.0, float(zoom or 1.0))
    return even(w * z), even(h * z)


def build(plan: dict, assets: dict, out_dir: Path, quality: str, style: dict | None, style_path: str | None, fast: bool = False) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    lut = (style or {}).get("grade", {}).get("lut") if style else None
    lut_path = None
    if lut and style_path:
        cand = [Path(lut), Path(style_path).parent / lut]
        lut_path = next((c for c in cand if c.exists()), None)
    style_sha = sha256_file(style_path) if style_path else None
    lut_sha = sha256_file(lut_path) if lut_path else None
    src_hashes = {}
    for k, v in assets.items():
        p = v.get("stabilized") if v.get("use_stabilized") and v.get("stabilized") else v.get("cfr_sdr")
        if quality == "proxy" and v.get("proxy"):
            p = v["proxy"]
        if p and Path(p).exists():
            src_hashes[k] = sha256_file(p)
    result = {"quality": quality, "scenes": {}, "audio_segments": {}, "reused": 0, "built": 0}
    match = CM.plan_corrections(plan, assets, style)
    write_json(out_dir / "color_match.json", match)
    result["color_match"] = {"report": str(out_dir / "color_match.json"), "enabled": match["enabled"], "ref": match["ref"],
                             "applied": sorted(k for k, v in match["layers"].items() if v.get("applied")),
                             "retake_candidates": match["retake_candidates"]}
    fps = plan["fps"]
    for i, s in enumerate(plan["scenes"]):
        # iş listesi: video katmanları ("<katman>") ve bileşenlerin kaynak alan prop'ları ("<katman>.<prop>", 1.8.0: BeforeAfter,
        # PictureInPicture, PhoneScreen). Bileşen kaynaklarına renk eşitleme uygulanmaz (önce/sonrada fark kanıtın kendisidir).
        jobs = []
        for li, layer in enumerate(s.get("layers", [])):
            src = layer.get("source") or {}
            if layer.get("type") == "video" and src.get("kind") == "footage":
                jobs.append((str(li), src, float((layer.get("camera") or {}).get("zoom", 1.0)), CM.filter_for(match, f"{s['id']}:{li}"), False))
            for prop, v in EP.source_props(layer):
                if isinstance(v, dict) and v.get("kind") == "footage":
                    jobs.append((f"{li}.{prop}", v, 1.0, None, bool(v.get("audio"))))
        voice = any(j[4] for j in jobs)  # konuşan kişi kaynağı işaretliyse sahne sesi ondan
        for lkey, src, zoom, cm, is_voice in jobs:
            akey = src.get("asset")
            a = assets.get(akey)
            if not a:
                raise SystemExit(f"varlık eşlemesi yok: {akey} (sahne {s['id']})")
            path = a.get("stabilized") if a.get("use_stabilized") and a.get("stabilized") else a["cfr_sdr"]
            if quality == "proxy" and a.get("proxy"):
                path = a["proxy"]
            tw, th = target_size(plan["format"], quality, zoom)
            in_s = float(src.get("in_s", 0.0))
            out_s = float(src.get("out_s", in_s + s["dur_s"]))
            # düzeltmesiz zincir 1.6.0 ile aynı kalır (anahtar da); düzeltme kazancı anahtara girer
            comp = "ffmpeg-intermediate-v1" + (f"+cm-{CM.digest(cm)}" if cm else "")
            key = SC.scene_key(plan, i, source_hashes=src_hashes, style_sha=style_sha, quality=quality, scale=1.0, lut_sha=lut_sha,
                               component_sha=comp) + f"_{lkey}"
            dst = out_dir / f"{s['id']}_{lkey}_{quality}_{key[:16]}.mp4"
            if SC.cached(dst):
                result["reused"] += 1
            else:
                vf = [f"trim=start={in_s}:end={out_s}", "setpts=PTS-STARTPTS", f"fps={fps}"]
                if cm:
                    vf.append(cm)
                if lut_path:
                    lp = lut_path.as_posix().replace(":", "\\:")
                    vf.append(f"lut3d='{lp}'")
                vf.append(f"scale={tw}:{th}:force_original_aspect_ratio=increase:flags=lanczos,crop={tw}:{th},format=yuv420p")
                ffmpeg(["-i", str(path), "-vf", ",".join(vf), "-an", "-c:v", "libx264", "-crf", "12" if quality == "final" and not fast else "18",
                        "-preset", "fast" if not fast else "veryfast", "-g", str(fps), "-threads", str(x264_threads()), str(dst)])
                SC.mark_done(dst)
                result["built"] += 1
            result["scenes"].setdefault(s["id"], {})[lkey] = {"path": str(dst), "width": tw, "height": th, "zoom": zoom,
                                                               "frames": round((out_s - in_s) * fps)}
            original = s.get("audio", {}).get("mode") in ("original", "original_clean")
            if original and (is_voice if voice else "." not in lkey):
                wav = out_dir / f"{s['id']}_{lkey}_audio_{key[:16]}.wav"
                if not wav.exists():  # 2.0.0: geçici ada yazılır; yarıda kalan çıkarım (kesinti) sonraki çalıştırmada tam dosya sanılmaz
                    part = wav.with_name(wav.stem + ".part.wav")
                    r = ffmpeg(["-ss", str(in_s), "-to", str(out_s), "-i", str(a["cfr_sdr"]), "-vn", "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le",
                                str(part)], check=False)
                    if r.returncode == 0 and part.exists():
                        part.replace(wav)
                    else:
                        part.unlink(missing_ok=True)
                if wav.exists():
                    result["audio_segments"][s["id"]] = str(wav)
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--quality", choices=["proxy", "final"], default="proxy")
    ap.add_argument("--style")
    ap.add_argument("--map-out")
    ap.add_argument("--fast", action="store_true")
    a = ap.parse_args()
    plan = read_json(a.plan)
    res = build(plan, read_json(a.assets), Path(a.out_dir), a.quality, read_json(a.style) if a.style else None, a.style, a.fast)
    if a.map_out:
        write_json(a.map_out, res)
    emit(res)


if __name__ == "__main__":
    main()
