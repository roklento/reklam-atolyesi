"""Yazı yerleşimi ve blok boyu (5.19): şablonun konum tablosu (templates/remotion/src/layout.json) ve bileşen ölçüleri.

Güvenli alan denetimi (qc/checks.py safe) ve yazı şeritleri (analyze/contact_sheet.py) yazının nerede durduğunu buradan alır; şablon
(layout.ts) aynı tabloyu okur. Blok boyu tahmindir: satırlar sözcük sözcük kırılır (ortalama harf genişliği ≈ 0,56 × font boyu, büyük
harfte 0,6; gerçek render ile ölçüldü), satır yüksekliği ve iç boşluklar bileşenlerin stilinden (components/text.tsx, proof.tsx, product.tsx).
1.6.0: render ölçümü varsa (<çıktı>.layout.json, components/fit.tsx) tahmin yerine o kullanılır: measured_extent.
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
    """Tahmini satır sayısı: açık satır sonları korunur, sözcükler bütün kalır (tarayıcı gibi açgözlü kırma; boşluk ≈ 0,28 em).
    Kutudan uzun tek sözcük sözcük ortasından bölünmez, kendi satırında taşar (taşmayı render ölçümü yakalar)."""
    cw = font_px * (0.6 if upper else 0.56)
    space = font_px * 0.28
    n = 0
    for para in str(text or "").split("\n"):
        cur, k = 0.0, 1
        for w in para.split():
            wl = len(w) * cw
            if cur == 0:
                cur = wl
            elif cur + space + wl <= avail_px:
                cur += space + wl
            else:
                k += 1
                cur = wl
        n += k
    return n or 1


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
    elif comp == "TextMark":  # 1.8.0
        mode = "top"
        fs = _num(props.get("fontSize"), 96)
        px = fs * 1.2 * lines(text, fs, 0.88 * w)
    elif comp == "NumberRoll":  # 1.8.0: sayı tek satır (fit.tsx) + isteğe bağlı açıklama
        mode = "center"
        fs = _num(props.get("fontSize"), 160)
        px = fs * 1.1 + ((10 + 44 * 1.2 * lines(props["label"], 44, 0.88 * w)) if props.get("label") else 0)
    else:  # TextReveal, KineticWords, SoftType ve yazılı bilinmeyen bileşen
        mode = "top"
        fs = _num(props.get("fontSize"), 88)
        px = fs * 1.12 * lines(text, fs, 0.88 * w)
    hh = px / h
    y0, y1 = (y - hh / 2, y + hh / 2) if mode == "center" else (y, y + hh)
    return {"component": comp, "mode": mode, "y": round(y, 4), "y0": round(y0, 4), "y1": round(y1, 4)}


def pip_extent(layer: dict, fmt: str) -> dict | None:
    """PictureInPicture köşe kutusu (oran; components/media.tsx pipRect ile aynı hesap): {x0, x1, y0, y1}."""
    if layer.get("component") != "PictureInPicture":
        return None
    f = fmt_of(fmt)
    w, h = size(f)
    props = layer.get("props") or {}
    b = LAYOUT["pip_box"][f]
    sz = min(0.45, max(0.18, _num(props.get("size"), 0.34)))
    corner = props.get("corner") or "top_right"
    bh = sz * w / h
    x0 = b["side"] if str(corner).endswith("left") else 1 - b["side"] - sz
    y0 = b["top"] if str(corner).startswith("top") else b["bottom"] - bh
    return {"component": "PictureInPicture", "x0": round(x0, 4), "x1": round(x0 + sz, 4), "y0": round(y0, 4), "y1": round(y0 + bh, 4)}


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


MEASURED = {"TextReveal", "KineticWords", "SoftType", "BehindSubjectText", "LowerThird", "CTAPulse", "TextMark"}  # blok boyu ölçümden alınabilenler


def _js_head(t: str, n: int = 160) -> str:
    """fit.tsx'teki text.slice(0, 160) ile aynı kesim: JavaScript UTF-16 birimi sayar; emoji gibi karakterler iki birimdir (2.0.0: Python
    kod noktası saydığı için 160 birimden uzun, emojili metnin ölçümü eşleşmiyor, taşma kaydı kaçıyordu)."""
    return t.encode("utf-16-le", "surrogatepass")[:2 * n].decode("utf-16-le", "surrogatepass")


def _layer_texts(layer: dict) -> set[str]:
    props = layer.get("props") or {}
    out = {str(layer.get("text") or "")}
    out |= {props[k] for k in TEXT_KEYS if isinstance(props.get(k), str)}
    return {_js_head(t) for t in out if t}


def measured_extent(ext: dict, layer: dict, records: list[dict]) -> dict:
    """Ölçülmüş blok: aynı bileşen ve aynı metinli kayıtların heightPx toplamı (LowerThird başlık + alt başlık). Ölçüm yoksa ext aynen,
    'measured': False. Sığmayan parça varsa 'overflow' listesi."""
    texts = _layer_texts(layer)
    recs = [r for r in records or [] if r.get("component") == ext["component"] and r.get("text") in texts]
    if not recs:
        return {**ext, "measured": False}
    overflow = [{"part": r.get("part"), "text": r.get("text"), "lines": r.get("lines"), "maxLines": r.get("maxLines"),
                 "fontSize": r.get("fontSize"), "minFontSize": r.get("minFontSize")} for r in recs if r.get("fits") is False]
    out = {**ext, "measured": True, "overflow": overflow}
    if ext["component"] in MEASURED and ext["mode"] != "full":
        parts = {}
        for r in recs:  # aynı parçanın birden çok kaydı (ör. önizleme ve final ölçeği) varsa en büyüğü
            k = r.get("part") or "text"
            parts[k] = max(parts.get(k, 0.0), float(r.get("heightPx") or 0) / max(1.0, float(r.get("height") or 1)))
        hh = sum(parts.values()) * (1.05 if ext["component"] == "CTAPulse" else 1.0)
        y = ext["y"]
        y0, y1 = (y - hh / 2, y + hh / 2) if ext["mode"] == "center" else (y, y + hh)
        out.update({"y0": round(y0, 4), "y1": round(y1, 4)})
    return out
