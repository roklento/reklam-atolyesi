"""Yazı yerleşimi ve blok boyu (5.19): şablonun konum tablosu (templates/remotion/src/layout.json) ve bileşen ölçüleri.

Güvenli alan denetimi (qc/checks.py safe) ve yazı şeritleri (analyze/contact_sheet.py) yazının nerede durduğunu buradan alır; şablon
(layout.ts) aynı tabloyu okur. Blok boyu tahmindir: satır sayısı karakter sayısından (ortalama harf genişliği ≈ 0,56 × font boyu, büyük
harfte 0,6; gerçek render ile ölçüldü), satır yüksekliği ve iç boşluklar bileşenlerin stilinden (components/text.tsx, proof.tsx, product.tsx).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
LAYOUT = json.loads((PLUGIN_ROOT / "templates" / "remotion" / "src" / "layout.json").read_text(encoding="utf-8"))
TITLE_Y = {"9x16": 0.14, "4x5": 0.19, "1x1": 0.1}  # style.ts varsayılanı
TEXT_PRESETS = {"text_reveal": "TextReveal", "kinetic": "KineticWords", "kinetic_words": "KineticWords", "soft_type": "SoftType",
                "lower_third": "LowerThird"}
SCHEMA_Y = {"TextReveal": 0.14, "KineticWords": 0.14, "SoftType": 0.14, "BehindSubjectText": 0.32}  # tabloda olmayan şema varsayılanları
TEXT_KEYS = ("text", "title", "subtitle", "label", "quote", "displayName", "brand", "cta", "url")
FULL = ("ReviewCard", "EndCard")  # ekran ortasında kart; y yok


def fmt_of(plan_or_fmt) -> str:
    f = plan_or_fmt.get("format", "9x16") if isinstance(plan_or_fmt, dict) else plan_or_fmt
    return f if f in LAYOUT["size"] else "9x16"


def size(fmt: str) -> tuple[int, int]:
    w, h = LAYOUT["size"][fmt_of(fmt)]
    return int(w), int(h)


def title_y(style: dict | None, fmt: str) -> float:
    return float((((style or {}).get("layout") or {}).get(fmt) or {}).get("titleY", TITLE_Y.get(fmt, 0.12)))


def anchor_y(anchor: str | None, role: str, ty: float, fmt: str) -> float:
    f = fmt_of(fmt)
    if anchor == "safe_top":
        return ty + 0.02
    a = LAYOUT["anchor_y"][f].get(anchor or "")
    if a is not None:
        return float(a)
    r = LAYOUT["role_y"][f].get(role, "layout")
    return float(r) if isinstance(r, (int, float)) else ty + 0.02


def component_y(name: str, fmt: str) -> float | None:
    v = LAYOUT["component_y"][fmt_of(fmt)].get(name)
    return float(v) if v is not None else SCHEMA_Y.get(name)


def lines(text: str, font_px: float, avail_px: float, upper: bool = False) -> int:
    cpl = max(1, int(avail_px / (font_px * (0.6 if upper else 0.56))))
    return sum(max(1, math.ceil(len(p.strip()) / cpl)) for p in str(text or "").split("\n")) or 1


def _num(v, d):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else d


def layer_extent(layer: dict, role: str, fmt: str, style: dict | None = None) -> dict | None:
    """Katmandaki yazının dikey yeri: {component, mode, y, y0, y1} (oran) ya da yazı yoksa None. mode: top (y üst kenar),
    center (y orta nokta), full (kart ekran ortasında)."""
    f = fmt_of(fmt)
    w, h = size(f)
    props = layer.get("props") or {}
    if layer.get("type") == "text":
        comp = TEXT_PRESETS.get(layer.get("preset") or "text_reveal", "TextReveal")
        text = layer.get("text") or ""
        y = _num(props.get("y"), anchor_y(layer.get("anchor"), role, title_y(style, f), f))
    elif layer.get("type") == "component" and layer.get("component"):
        comp = layer["component"]
        text = props.get("text") or props.get("title") or ""
        if comp in FULL:
            return {"component": comp, "mode": "full", "y": None, "y0": 0.28, "y1": 0.72}
        dy = component_y(comp, f)
        if dy is None and not any(isinstance(props.get(k), str) and props.get(k) for k in TEXT_KEYS):
            return None
        if dy is None and not isinstance(props.get("y"), (int, float)):
            return {"component": comp, "mode": "full", "y": None, "y0": 0.28, "y1": 0.72}
        y = _num(props.get("y"), dy)
    else:
        return None
    if comp == "LowerThird":
        mode = "top"
        title = layer.get("text") or props.get("title") or ""
        px = 44 + 54 * 1.2 * lines(title, 54, 0.88 * w) + (36 * 1.2 * lines(props["subtitle"], 36, 0.88 * w) if props.get("subtitle") else 0)
    elif comp == "PriceTag":
        mode = "center"
        price = 72 * 1.2 if props.get("price") is not None and props.get("currency") else 40 * 1.2
        px = 36 + price + (32 * 1.2 if props.get("label") else 0) + (34 * 1.2 if props.get("referencePrice") is not None else 0)
    elif comp == "CTAPulse":
        mode = "center"
        px = (48 + 56 * 1.2 * lines(text, 56, 0.88 * w)) * 1.05
    elif comp == "BehindSubjectText":
        mode = "top"
        fs = _num(props.get("fontSize"), 220)
        px = fs * 1.1 * lines(text, fs, w, upper=True)
    elif comp == "CaptionTrack":
        mode = "top"
        fs = _num(props.get("fontSize"), 58)
        px = fs * 1.15 * 2
    else:  # TextReveal, KineticWords, SoftType ve yazılı bilinmeyen bileşen
        mode = "top"
        fs = _num(props.get("fontSize"), 88)
        px = fs * 1.12 * lines(text, fs, 0.88 * w)
    hh = px / h
    y0, y1 = (y - hh / 2, y + hh / 2) if mode == "center" else (y, y + hh)
    return {"component": comp, "mode": mode, "y": round(y, 4), "y0": round(y0, 4), "y1": round(y1, 4)}


def captions_extent(plan: dict, captions: list | None = None) -> dict | None:
    """Altyazı bloğu (Master.tsx: CaptionTrack, y format tablosundan). Parça metni verilmezse 2 satır varsayılır."""
    cap = plan.get("captions") or {}
    if not cap.get("on"):
        return None
    f = fmt_of(plan)
    w, h = size(f)
    upper = cap.get("preset") == "keyword_upper"
    n = max((lines(c.get("text", ""), 58, 0.84 * w, upper) for c in captions or []), default=2)
    y = component_y("CaptionTrack", f)
    return {"component": "CaptionTrack", "mode": "top", "y": y, "y0": y, "y1": round(y + 58 * 1.15 * n / h, 4), "lines": n}
