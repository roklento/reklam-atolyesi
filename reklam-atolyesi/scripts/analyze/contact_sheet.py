"""Kontak sayfası (spec 5.5, 5.15): 6×4 kare, zaman damgalı. Video için eşit aralıklı ya da saniyede 1 kare; tek kare listesi de olur.

Kullanım: contact_sheet.py --video in.mp4 --out sheet.jpg [--cols 6 --rows 4] [--per-second] [--times 0.5,1.2,...]
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit, ffmpeg, ffprobe_json, seconds_to_tc  # noqa: E402


def extract(video: str, times: list[float], tmp: Path, width: int) -> list[Path]:
    paths = []
    for i, t in enumerate(times):
        p = tmp / f"f{i:03d}.png"
        ffmpeg(["-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", "-vf", f"scale={width}:-2", str(p)], check=False)
        if p.exists():
            paths.append(p)
        else:
            paths.append(None)
    return paths


def sheet(video: str, out: str, cols: int = 6, rows: int = 4, per_second: bool = False, times: list[float] | None = None,
          thumb_w: int = 270) -> dict:
    from PIL import Image, ImageDraw, ImageFont
    dur = float((ffprobe_json(video).get("format") or {}).get("duration") or 0)
    if times is None:
        if per_second:
            times = [min(dur - 0.05, i + 0.5) for i in range(int(max(1, dur)))]
            n = len(times)
            cols = min(6, n)
            rows = (n + cols - 1) // cols
        else:
            n = cols * rows
            times = [dur * (i + 0.5) / n for i in range(n)]
    with tempfile.TemporaryDirectory() as td:
        frames = extract(video, times, Path(td), thumb_w)
        ims = [Image.open(f).convert("RGB") if f else None for f in frames]
        th = max((im.height for im in ims if im), default=480)
        W, H = cols * thumb_w, rows * (th + 22)
        canvas = Image.new("RGB", (W, H), (24, 24, 24))
        d = ImageDraw.Draw(canvas)
        try:
            font = ImageFont.load_default(size=16)
        except TypeError:
            font = ImageFont.load_default()
        for i, (t, im) in enumerate(zip(times, ims)):
            if i >= cols * rows:
                break
            x, y = (i % cols) * thumb_w, (i // cols) * (th + 22)
            if im:
                canvas.paste(im, (x, y))
            d.text((x + 4, y + th + 3), seconds_to_tc(t), fill=(235, 235, 235), font=font)
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        canvas.save(out, quality=88)
    return {"sheet": out, "frames": len(times), "duration": round(dur, 3), "grid": [cols, rows], "times": [round(t, 3) for t in times]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--rows", type=int, default=4)
    ap.add_argument("--per-second", action="store_true")
    ap.add_argument("--times")
    a = ap.parse_args()
    times = [float(x) for x in a.times.split(",")] if a.times else None
    emit(sheet(a.video, a.out, a.cols, a.rows, a.per_second, times))


if __name__ == "__main__":
    main()
