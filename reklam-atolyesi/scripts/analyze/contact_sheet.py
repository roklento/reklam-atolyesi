"""Kontak sayfası (spec 5.5, 5.15): 6×4 kare, zaman damgalı. Video için eşit aralıklı ya da saniyede 1 kare; tek kare listesi de olur.

Yazı şeritleri (1.5.1): kontak sayfasında kare 1080'den 270 px'e iner; 32–36 px yazı (fiyat etiketi, eski fiyat, alt başlık, yorumcu
adı, adres) 8 px'in altına düşer ve harf düzeyindeki kusurlar (yedek fonta düşen ğ/ş/İ, kırpılan harf) görülmez. text_bands planın her
yazılı anından yazının bulunduğu yatay bölgeyi en fazla 540 px genişlikte keser (önizlemede tam çözünürlük: 32 px → 16 px) ve şeritleri
küçültülmeden okunacak sayfalara dizer (sayfa ≤ 540×1500 px: 1568 px / 1,15 MP sınırının altında). Konumlar şablonun çizimini izler
(templates/remotion/src/scenes/index.tsx anchorY ve bileşen varsayılanları).

Kullanım: contact_sheet.py --video in.mp4 --out sheet.jpg [--cols 6 --rows 4] [--per-second] [--times 0.5,1.2,...]
          contact_sheet.py --video in.mp4 --out bands.jpg --text-bands --plan plan.json [--style s.json] [--captions words.json]
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit, ffmpeg, ffprobe_json, read_json, seconds_to_tc  # noqa: E402
import text_layout as TL  # noqa: E402


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


# Yazının dikey yeri şablonla aynı tablodan (lib/text_layout.py ← templates/remotion/src/layout.json); şeride yazının üstünden ve
# altından pay eklenir (animasyonun kayması, harf kuyrukları).
SMALL_TEXT_FIRST = ("PriceTag", "LowerThird", "ReviewCard", "EndCard", "CTAPulse")  # 32–36 px yazı taşıyanlar önce
BAND_W, PAGE_H, MAX_BANDS, LABEL_H = 540, 1500, 12, 22
BAND_PAD = 0.03


def text_moments(plan: dict, style: dict | None = None, captions: list | None = None, duration: float | None = None) -> list[dict]:
    """Planın yazılı anları: [{t, where, component, y0, y1}] (y oranı 0–1). Yazı açılış animasyonu bitsin diye an, yazının ekrandaki
    süresinin %65'indedir."""
    fmt = plan.get("format", "9x16")
    dur = duration or float(plan.get("duration_s") or 0) or None
    out = []
    for s in plan.get("scenes", []):
        for i, l in enumerate(s.get("layers", [])):
            ext = TL.layer_extent(l, s.get("role", ""), fmt, style)
            if not ext:
                continue
            ls = float(l.get("start_s", 0) or 0)
            ld = float(l.get("dur_s", float(s["dur_s"]) - ls))
            t = float(s["start_s"]) + ls + 0.65 * max(0.0, ld)
            if dur:
                t = min(max(0.0, t), dur - 0.05)
            comp = "text" if l.get("type") == "text" else ext["component"]
            out.append({"t": round(t, 3), "where": f"{s.get('id')}/{i}", "component": comp,
                        "y0": max(0.0, ext["y0"] - BAND_PAD), "y1": min(1.0, ext["y1"] + BAND_PAD)})
    cap = TL.captions_extent(plan, captions)
    if cap and captions:
        for c in sorted(captions, key=lambda c: -len(str(c.get("text", ""))))[:2]:
            t = (float(c["start"]) + float(c["end"])) / 2
            out.append({"t": round(t, 3), "where": "altyazı", "component": "CaptionTrack",
                        "y0": max(0.0, cap["y0"] - BAND_PAD), "y1": min(1.0, cap["y1"] + BAND_PAD)})
    out.sort(key=lambda m: (0 if m["component"] in SMALL_TEXT_FIRST else 1, m["t"]))
    return out


def text_bands(video: str, plan: dict, out: str, style: dict | None = None, captions: list | None = None, max_bands: int = MAX_BANDS) -> dict:
    """Yazılı anların şeritleri; sayfalar <out_stem>_<n>.jpg. Dönen: {sheets, bands, skipped, width}."""
    from PIL import Image, ImageDraw, ImageFont
    info = ffprobe_json(video)
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    vw, vh = int(v.get("width") or 0), int(v.get("height") or 0)
    dur = float((info.get("format") or {}).get("duration") or 0) or None
    moments = text_moments(plan, style, captions, dur)
    skipped = [m["where"] for m in moments[max_bands:]]
    moments = sorted(moments[:max_bands], key=lambda m: m["t"])
    w = min(BAND_W, vw) if vw else BAND_W
    try:
        font = ImageFont.load_default(size=16)
    except TypeError:
        font = ImageFont.load_default()
    bands = []
    with tempfile.TemporaryDirectory() as td:
        for k, m in enumerate(moments):
            p = Path(td) / f"b{k:03d}.png"
            y0 = int(vh * m["y0"]) // 2 * 2
            h = max(2, int(vh * (m["y1"] - m["y0"])) // 2 * 2)
            ffmpeg(["-ss", f"{m['t']:.3f}", "-i", video, "-frames:v", "1", "-vf", f"crop={vw}:{h}:0:{y0},scale={w}:-2", str(p)], check=False)
            if p.exists():
                bands.append((m, Image.open(p).convert("RGB")))
        pages, cur, cur_h = [], [], 0
        for m, im in bands:
            need = im.height + LABEL_H
            if cur and cur_h + need > PAGE_H:
                pages.append(cur)
                cur, cur_h = [], 0
            cur.append((m, im))
            cur_h += need
        if cur:
            pages.append(cur)
        stem = Path(out)
        sheets = []
        for n, pg in enumerate(pages, 1):
            canvas = Image.new("RGB", (w, sum(im.height + LABEL_H for _, im in pg)), (24, 24, 24))
            d = ImageDraw.Draw(canvas)
            y = 0
            for m, im in pg:
                d.text((4, y + 3), f"{seconds_to_tc(m['t'])}  {m['where']}  {m['component']}", fill=(235, 235, 235), font=font)
                canvas.paste(im, (0, y + LABEL_H))
                y += im.height + LABEL_H
            path = stem.with_name(f"{stem.stem}_{n}{stem.suffix or '.jpg'}")
            path.parent.mkdir(parents=True, exist_ok=True)
            canvas.save(path, quality=90)
            sheets.append(str(path))
    return {"sheets": sheets, "bands": [m for m, _ in bands], "skipped": skipped, "width": w,
            "note": "şeritler küçültülmeden okunmalı; yazının harf harf doğru, kırpılmamış, zemin üstünde okunur olduğuna bak"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--rows", type=int, default=4)
    ap.add_argument("--per-second", action="store_true")
    ap.add_argument("--times")
    ap.add_argument("--text-bands", action="store_true", help="yazılı anların okunur şeritleri (--plan gerekir)")
    ap.add_argument("--plan")
    ap.add_argument("--style")
    ap.add_argument("--captions", help="altyazı parçaları (captions.words.json)")
    a = ap.parse_args()
    if a.text_bands:
        if not a.plan:
            raise SystemExit("--text-bands için --plan gerekir")
        caps = read_json(a.captions) if a.captions else None
        if isinstance(caps, dict):
            caps = caps.get("captions") or []
        emit(text_bands(a.video, read_json(a.plan), a.out, read_json(a.style) if a.style else None, caps))
        return
    times = [float(x) for x in a.times.split(",")] if a.times else None
    emit(sheet(a.video, a.out, a.cols, a.rows, a.per_second, times))


if __name__ == "__main__":
    main()
