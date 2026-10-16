"""Export (spec 5.16–5.18): teslim dosyası, adlandırma, statik ve carousel.

Alt komutlar:
  video    --video v.mp4 --audio mix_final.wav --out-dir out/ --key <creative_key> --format 9x16
           H.264 High, yuv420p, 30 fps CFR, CRF 16–18 (Remotion final render), AAC 48 kHz 256 kbps, +faststart.
           Ses miksi -14 LUFS / ≤ -1 dBTP'ye getirilmiş olmalı (mix.py).
  name     --key <creative_key> --format 4x5 [--card 2] [--ext jpg]   (adlandırma kuralıyla dosya adı)
  key      --brand MRK --campaign K1 --concept A --media video --duration 15 --hook h1 --vo|--no-vo --source real --cycle 1 --rev 1
Statik/carousel: Master-45 (ya da Master-11) kompozisyonundan tek kare render edilir (render.py plan --still), fotoğraf
öncelikli (5.17); bu script dosyaları adlandırır ve doğrular.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit, ffmpeg, ffprobe_json, sha256_file  # noqa: E402
from admem import naming  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "audio"))
TP_LIMIT = -1.0
TP_TARGET = -1.2  # AAC kodlaması gerçek tepeyi birkaç onda bir dB yükseltebilir; teslim dosyası ölçülür


def export_video(video: str, audio: str | None, out_dir: Path, key: str, fmt: str) -> dict:
    name = naming.build_file_name(key, fmt, None, "mp4")
    out = out_dir / name
    if out.exists():
        raise SystemExit(f"{name} zaten var; aynı anahtar/format farklı içerikle üzerine yazılmaz, yeni revizyon açın (5.18)")
    out_dir.mkdir(parents=True, exist_ok=True)
    args = ["-i", video]
    if audio:
        args += ["-i", audio, "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-shortest"]
    else:
        args += ["-map", "0:v:0", "-an"]
    v = next((s for s in ffprobe_json(video)["streams"] if s["codec_type"] == "video"), {})
    full_range = v.get("pix_fmt") == "yuvj420p" or v.get("color_range") == "pc"
    if v.get("codec_name") == "h264" and v.get("pix_fmt") == "yuv420p" and not full_range and (v.get("profile") or "").lower().startswith("high"):
        args += ["-c:v", "copy"]
    else:  # tam aralık (pc/yuvj) ya da farklı biçim: BT.709 sınırlı aralığa dönüştürerek yeniden kodla
        args += ["-vf", "scale=out_range=tv:out_color_matrix=bt709,format=yuv420p", "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
                 "-crf", "17", "-preset", "medium", "-r", "30", "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709",
                 "-color_trc", "bt709"]
    tmp = out.with_suffix(".tmp.mp4")
    ffmpeg([*args, "-movflags", "+faststart", str(tmp)])
    audio_fix = None
    if audio:  # teslim dosyasında gerçek tepe ≤ -1 dBTP (5.13); AAC aşımı varsa kazanç düşürülüp yeniden kodlanır (en fazla 2 kez)
        import loudness as LN
        reduced = 0.0
        i = args.index("-c:a")
        for _ in range(2):
            m = LN.measure(str(tmp))
            if m["true_peak_dbtp"] <= TP_LIMIT:
                break
            reduced = round(reduced + m["true_peak_dbtp"] - TP_TARGET, 3)
            tmp.unlink(missing_ok=True)
            ffmpeg([*args[:i], "-af", f"volume=-{reduced}dB", *args[i:], "-movflags", "+faststart", str(tmp)])
            audio_fix = {"reduced_db": reduced, "tp_before": m["true_peak_dbtp"]}
    tmp.replace(out)
    info = ffprobe_json(out)
    vs = next(s for s in info["streams"] if s["codec_type"] == "video")
    return {"out": str(out), "file_name": name, "creative_key": key, "format": fmt, "sha256": sha256_file(out),
            "video": {"codec": vs.get("codec_name"), "profile": vs.get("profile"), "pix_fmt": vs.get("pix_fmt"), "w": vs.get("width"), "h": vs.get("height"),
                      "fps": vs.get("r_frame_rate")}, "duration": float(info["format"]["duration"]), "audio_tp_fix": audio_fix}


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("video")
    p.add_argument("--video", required=True)
    p.add_argument("--audio")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--key", required=True)
    p.add_argument("--format", required=True, choices=list(naming.FORMATS))
    p = sp.add_parser("name")
    p.add_argument("--key", required=True)
    p.add_argument("--format", required=True, choices=list(naming.FORMATS))
    p.add_argument("--card", type=int)
    p.add_argument("--ext", default="mp4")
    p = sp.add_parser("key")
    for k in ("--brand", "--campaign", "--concept", "--media", "--hook", "--source"):
        p.add_argument(k, required=True)
    p.add_argument("--duration", type=float)
    p.add_argument("--vo", dest="vo", action="store_true")
    p.add_argument("--no-vo", dest="vo", action="store_false")
    p.add_argument("--cycle", type=int, required=True)
    p.add_argument("--rev", type=int, default=1)
    a = ap.parse_args()
    if a.cmd == "video":
        emit(export_video(a.video, a.audio, Path(a.out_dir), a.key, a.format))
    elif a.cmd == "name":
        emit({"file_name": naming.build_file_name(a.key, a.format, a.card, a.ext)})
    else:
        emit({"creative_key": naming.build_key(a.brand, a.campaign, a.concept, a.media, a.duration, a.hook, a.vo, a.source, a.cycle, a.rev)})


if __name__ == "__main__":
    main()
