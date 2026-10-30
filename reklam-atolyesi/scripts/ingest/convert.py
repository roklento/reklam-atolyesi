"""S06 Ingest (spec 5.4): telefon çekimlerini kurguya güvenli girdiye çevirir. Ham çekime dokunulmaz.

Alt komutlar:
  probe <dosya>                                  → ffprobe özeti (VFR, HDR, döndürme, ses)
  ingest --campaign-dir <k> [--fps 30] [--fast]  → footage/raw ve photos/raw'daki her dosyayı işler, analysis/ingest_manifest.json yazar
Kayıtlar (assets) ad-memory'ye asset_register ile işlenir; bu script veritabanına yazmaz (7.4).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit, ffmpeg, ffprobe_json, sha256_file, write_json, x264_threads  # noqa: E402

VIDEO_EXT = {".mov", ".mp4", ".m4v", ".mkv", ".avi", ".3gp", ".webm"}
PHOTO_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}
SHAKE_THRESHOLD_PERMILLE = 4.0


def _fps(s: str | None) -> float:
    try:
        return float(Fraction(s)) if s and s != "0/0" else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe(path: str | Path) -> dict:
    info = ffprobe_json(path)
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not v:
        return {"path": str(path), "video": False}
    r, avg = _fps(v.get("r_frame_rate")), _fps(v.get("avg_frame_rate"))
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(sd["rotation"])
    rot = rot or int((v.get("tags") or {}).get("rotate", 0) or 0)
    trc = (v.get("color_transfer") or "").lower()
    hdr = trc in ("arib-std-b67", "smpte2084") or "bt2020" in (v.get("color_primaries") or "")
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    if abs(rot) in (90, 270):
        w, h = h, w
    return {"path": str(path), "video": True, "width": w, "height": h, "rotation": rot,
            "r_fps": round(r, 3), "avg_fps": round(avg, 3), "vfr": bool(r and avg and abs(r - avg) > 0.01) or (v.get("codec_tag_string") == "vfr"),
            "color_transfer": trc or None, "color_primaries": v.get("color_primaries"), "hdr": hdr,
            "hdr_kind": "HLG" if trc == "arib-std-b67" else ("PQ" if trc == "smpte2084" else None),
            "codec": v.get("codec_name"), "duration": float((info.get("format") or {}).get("duration") or v.get("duration") or 0),
            "audio": {"channels": a.get("channels"), "sample_rate": a.get("sample_rate"), "codec": a.get("codec_name")} if a else None}


def to_cfr_sdr(src: Path, dst: Path, fps: int, hdr: bool, fast: bool = False) -> None:
    """VFR → sabit kare hızı; HLG/PQ → Rec.709 SDR (zscale + tonemap); 4K korunur (5.4)."""
    if hdr:
        vf = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,"
              f"zscale=t=bt709:m=bt709:r=tv,format=yuv420p,fps={fps}")
    else:
        vf = f"fps={fps},format=yuv420p"
    ffmpeg(["-i", str(src), "-vf", vf, "-c:v", "libx264", "-crf", "14" if not fast else "20", "-preset", "slow" if not fast else "veryfast",
            "-threads", str(x264_threads()), "-x264-params", "rc-lookahead=20",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
            "-c:a", "pcm_s16le", "-ar", "48000", str(dst)])


def make_proxy(src: Path, dst: Path, fast: bool = False) -> None:
    """Kurgu önizlemesi: 1080 kısa kenar, H.264 yüksek kalite (5.4)."""
    ffmpeg(["-i", str(src), "-vf", "scale='if(lt(iw,ih),1080,-2)':'if(lt(iw,ih),-2,1080)':flags=lanczos,format=yuv420p",
            "-c:v", "libx264", "-crf", "18" if not fast else "23", "-preset", "medium" if not fast else "veryfast",
            "-threads", str(x264_threads()), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(dst)])


_VIDSTAB_FILEFORMAT: bool | None = None


def _vidstab_has_fileformat() -> bool:
    """libvidstab 1.1.1+ varsayılan olarak ikili TRF yazar ve `fileformat` seçeneğini getirir; eski sürümlerde seçenek yoktur
    (verilirse FFmpeg 8 koduyla çıkar) ve TRF zaten metindir."""
    global _VIDSTAB_FILEFORMAT
    if _VIDSTAB_FILEFORMAT is None:
        try:
            out = ffmpeg(["-h", "filter=vidstabdetect"], check=False)
            _VIDSTAB_FILEFORMAT = "fileformat" in (out.stdout or "")
        except Exception:
            _VIDSTAB_FILEFORMAT = True
    return _VIDSTAB_FILEFORMAT


def detect_shake(src: Path, trf: Path) -> dict:
    """vidstabdetect (1. geçiş); S07'nin sarsıntı puanı bu ölçümdür. Yerel hareket vektörlerinden kare başına RMS, genişliğe göre ‰."""
    tr = trf.as_posix().replace(":", "\\:")
    fmt = "fileformat=ascii:" if _vidstab_has_fileformat() else ""
    ffmpeg(["-i", str(src), "-vf", f"vidstabdetect=shakiness=6:accuracy=15:{fmt}result='{tr}'", "-f", "null", "-"])
    width = probe(src).get("width") or 1080
    per_frame = []
    vec = re.compile(r"\(LM\s+(-?\d+)\s+(-?\d+)")
    for line in trf.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("Frame"):
            continue
        vs = [(int(a), int(b)) for a, b in vec.findall(line)]
        if vs:
            vs.sort(key=lambda t: t[0] * t[0] + t[1] * t[1])
            mid = vs[len(vs) // 2]
            per_frame.append(math.hypot(*mid))
    if not per_frame:
        return {"shake_permille": 0.0, "frames": 0}
    diffs = [abs(per_frame[i] - per_frame[i - 1]) for i in range(1, len(per_frame))] or [0.0]
    score = (sum(diffs) / len(diffs)) / width * 1000
    return {"shake_permille": round(score, 3), "frames": len(per_frame), "threshold_permille": SHAKE_THRESHOLD_PERMILLE}


def stabilize(src: Path, trf: Path, dst: Path, fast: bool = False) -> None:
    """vidstabtransform (2. geçiş): sabitlenmiş ayrı kopya; ham ve sabitlenmiş ikisi de saklanır (5.4)."""
    tr = trf.as_posix().replace(":", "\\:")
    ffmpeg(["-i", str(src), "-vf", f"vidstabtransform=input='{tr}':smoothing=20:zoom=3,unsharp=5:5:0.6,format=yuv420p",
            "-c:v", "libx264", "-crf", "14" if not fast else "20", "-preset", "slow" if not fast else "veryfast",
            "-threads", str(x264_threads()), "-c:a", "copy", str(dst)])


def extract_audio(src: Path, dst: Path) -> bool:
    try:
        ffmpeg(["-i", str(src), "-vn", "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", str(dst)])
        return dst.exists() and dst.stat().st_size > 1000
    except RuntimeError:
        return False


def process_photo(src: Path, dst_dir: Path) -> dict:
    """EXIF yönü uygulanır, HEIC ise JPEG'e çevrilir (pillow-heif) (5.4)."""
    from PIL import Image, ImageOps
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    with Image.open(src) as im:
        exif_orient = (im.getexif() or {}).get(0x0112)
        im2 = ImageOps.exif_transpose(im).convert("RGB")
        dst = dst_dir / (src.stem + ".jpg")
        im2.save(dst, "JPEG", quality=95)
        return {"source": str(src), "sha256": sha256_file(src), "output": str(dst), "output_sha256": sha256_file(dst),
                "width": im2.width, "height": im2.height, "exif_orientation": exif_orient, "heic": src.suffix.lower() in (".heic", ".heif")}


def ingest(campaign_dir: Path, fps: int = 30, fast: bool = False, only: list[str] | None = None) -> dict:
    raw = campaign_dir / "footage" / "raw"
    out = {"footage": [], "photos": [], "errors": []}
    for sub in ("proxy", "graded", "stab", "scenes"):
        (campaign_dir / "footage" / sub).mkdir(parents=True, exist_ok=True)
    (campaign_dir / "audio" / "raw").mkdir(parents=True, exist_ok=True)
    (campaign_dir / "analysis" / "trf").mkdir(parents=True, exist_ok=True)
    for src in sorted(raw.glob("*")):
        if src.suffix.lower() not in VIDEO_EXT or (only and src.name not in only):
            continue
        try:
            meta = probe(src)
            stem = src.stem
            sdr = campaign_dir / "footage" / "graded" / f"{stem}_cfr.mov"
            to_cfr_sdr(src, sdr, fps, meta["hdr"], fast)
            proxy = campaign_dir / "footage" / "proxy" / f"{stem}_proxy.mp4"
            make_proxy(sdr, proxy, fast)
            trf = campaign_dir / "analysis" / "trf" / f"{stem}.trf"
            shake = detect_shake(proxy, trf)
            stab = None
            if shake["shake_permille"] > SHAKE_THRESHOLD_PERMILLE:
                stab = campaign_dir / "footage" / "stab" / f"{stem}_stab.mov"
                trf_full = campaign_dir / "analysis" / "trf" / f"{stem}_full.trf"
                detect_shake(sdr, trf_full)
                stabilize(sdr, trf_full, stab, fast)
            wav = campaign_dir / "audio" / "raw" / f"{stem}.wav"
            has_audio = bool(meta.get("audio")) and extract_audio(src, wav)
            out["footage"].append({"source": str(src), "sha256": sha256_file(src), "probe": meta,
                                   "cfr_sdr": str(sdr), "cfr_sdr_sha256": sha256_file(sdr), "proxy": str(proxy),
                                   "proxy_sha256": sha256_file(proxy), "shake": shake,
                                   "stabilized": str(stab) if stab else None, "stabilized_sha256": sha256_file(stab) if stab else None,
                                   "audio_wav": str(wav) if has_audio else None, "fps": fps,
                                   "notes": [n for n in ["VFR → CFR" if meta["vfr"] else None,
                                                         f"{meta['hdr_kind'] or 'HDR'} → SDR" if meta["hdr"] else None] if n]})
        except Exception as e:  # tek klip hatası bütün ingest'i durdurmaz; rapora yazılır
            out["errors"].append({"source": str(src), "error": str(e)[:500]})
    praw = campaign_dir / "photos" / "raw"
    pdst = campaign_dir / "photos"
    for src in sorted(praw.glob("*")) if praw.exists() else []:
        if src.suffix.lower() in PHOTO_EXT and (not only or src.name in only):
            try:
                out["photos"].append(process_photo(src, pdst))
            except Exception as e:
                out["errors"].append({"source": str(src), "error": str(e)[:500]})
    mpath = campaign_dir / "analysis" / "ingest_manifest.json"
    if only and mpath.exists():
        # 2.0.0: --only (yarıda kalan ingest'in yalnızca eksiklerini işleme) önceki kayıtları korur; önceden manifest yalnızca bu
        # çalıştırmanın kliplerini içeriyordu ve önceden işlenmiş klipler S07–S10'da görünmez oluyordu
        try:
            prev = json.loads(mpath.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prev = {}
        done = {Path(x["source"]).name for x in out["footage"] + out["photos"]} | {Path(e["source"]).name for e in out["errors"]}
        keep = lambda xs: [x for x in xs or [] if Path(x.get("source", "")).name not in done]
        out = {"footage": keep(prev.get("footage")) + out["footage"], "photos": keep(prev.get("photos")) + out["photos"],
               "errors": keep(prev.get("errors")) + out["errors"]}
    sha = write_json(mpath, out)
    return {"manifest": str(mpath), "sha256": sha, "footage": len(out["footage"]), "photos": len(out["photos"]), "errors": out["errors"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p1 = sp.add_parser("probe")
    p1.add_argument("path")
    p2 = sp.add_parser("ingest")
    p2.add_argument("--campaign-dir", required=True)
    p2.add_argument("--fps", type=int, default=30, choices=[30, 60])
    p2.add_argument("--fast", action="store_true", help="test/önizleme için hızlı kodlama (final değil)")
    p2.add_argument("--only", nargs="*")
    a = ap.parse_args()
    if a.cmd == "probe":
        emit(probe(a.path))
    else:
        emit(ingest(Path(a.campaign_dir), a.fps, a.fast, a.only))


if __name__ == "__main__":
    main()
