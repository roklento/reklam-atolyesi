"""Logodan renk çıkarımı (spec 17.5, 5.6): S00a'da renkler logodan otomatik çıkarılır ve onaya sunulur; ayrıca sorulmaz.

- SVG: fill/stroke/stop-color öznitelikleri ve style içindeki #hex / rgb() değerleri, geçiş sayısına göre sıralanır.
- Raster (PNG/JPG/WebP): saydam pikseller atılır, PIL ile en fazla N renge nicelenir, pay sırasıyla.
Çıktı öneridir: hangi rengin ink/accent/bg olacağına kullanıcı karar verir; kenar rengi arka plan olabilir diye işaretlenir.

Kullanım: palette.py --logo logo.svg|logo.png [--n 5] [--out palette.json]
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit, write_json  # noqa: E402

HEX = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
RGB = re.compile(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})")
ATTR = re.compile(r"(?:fill|stroke|stop-color|color)\s*[:=]\s*[\"']?([^;\"'>\s]+)")


def _norm_hex(h: str) -> str:
    h = h.lstrip("#").lower()
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "#" + h


def _lum(hexv: str) -> float:
    r, g, b = (int(hexv[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def from_svg(text: str, n: int) -> list[dict]:
    cnt: Counter[str] = Counter()
    for val in ATTR.findall(text):
        m = HEX.search(val)
        if m:
            cnt[_norm_hex(m.group(0))] += 1
            continue
        m = RGB.search(val)
        if m:
            r, g, b = (min(255, int(x)) for x in m.groups())
            cnt[f"#{r:02x}{g:02x}{b:02x}"] += 1
    for m in HEX.finditer(text):  # style blokları ve CSS
        cnt[_norm_hex(m.group(0))] += 0  # yalnızca var olduğunu kaydet; sayım öznitelikten
    total = sum(cnt.values()) or 1
    return [{"hex": h, "share": round(c / total, 4), "luminance": round(_lum(h), 3)} for h, c in cnt.most_common(n) if c > 0]


def from_raster(path: Path, n: int) -> list[dict]:
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGBA")
        im.thumbnail((256, 256))
        data = im.get_flattened_data() if hasattr(im, "get_flattened_data") else im.getdata()
        px = [p for p in data if p[3] >= 128]
        if not px:
            return []
        w, h = im.size
        edge = [im.getpixel((x, y)) for x in range(w) for y in (0, h - 1)] + [im.getpixel((x, y)) for y in range(h) for x in (0, w - 1)]
    rgb = Image.new("RGB", (len(px), 1))
    rgb.putdata([p[:3] for p in px])
    q = rgb.quantize(colors=max(1, n), method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette() or []
    counts = sorted(q.getcolors() or [], reverse=True)
    out = []
    edge_rgb = Counter(p[:3] for p in edge if p[3] >= 128)
    edge_top = edge_rgb.most_common(1)[0][0] if edge_rgb else None
    for c, idx in counts[:n]:
        r, g, b = pal[idx * 3: idx * 3 + 3]
        hx = f"#{r:02x}{g:02x}{b:02x}"
        item = {"hex": hx, "share": round(c / len(px), 4), "luminance": round(_lum(hx), 3)}
        if edge_top and sum(abs(a - b2) for a, b2 in zip((r, g, b), edge_top)) < 40:
            item["maybe_background"] = True
        out.append(item)
    return out


def extract(logo: Path, n: int = 5) -> dict:
    if logo.suffix.lower() == ".svg":
        colors = from_svg(logo.read_text(encoding="utf-8", errors="replace"), n)
        kind = "svg"
    else:
        colors = from_raster(logo, n)
        kind = "raster"
    return {"logo": str(logo), "kind": kind, "colors": colors,
            "note": "Öneridir; ink/accent/bg eşlemesini kullanıcı onaylar (17.5). Renk bulunamadıysa elle sorulur."}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--logo", required=True)
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--out")
    a = ap.parse_args()
    res = extract(Path(a.logo), a.n)
    if a.out:
        write_json(a.out, res)
    emit(res)


if __name__ == "__main__":
    main()
