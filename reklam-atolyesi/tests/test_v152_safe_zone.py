"""1.5.2: yazı konumları ve güvenli alan denetimi şablonla aynı tablodan (templates/remotion/src/layout.json); denetim yazı bloğunun
üst ve alt kenarına bakar, altyazıyı da kapsar."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for sub in ("lib", "qc"):
    sys.path.insert(0, str(ROOT / "scripts" / sub))
import checks as CK  # noqa: E402
import text_layout as TL  # noqa: E402

SRC = ROOT / "templates" / "remotion" / "src"
STYLE = json.loads((ROOT / "templates" / "style.json").read_text(encoding="utf-8"))


def _plan(fmt: str = "9x16", captions: bool = True) -> dict:
    def sc(i, role, layers):
        return {"id": f"s{i}", "role": role, "start_s": 2 * (i - 1), "dur_s": 2, "layers": layers}
    return {"format": fmt, "duration_s": 14, "captions": {"on": captions, "preset": "keyword_upper"}, "scenes": [
        sc(1, "hook", [{"type": "text", "text": "Yeni sezon başladı\nHemen keşfet"}]),
        sc(2, "reveal", [{"type": "text", "text": "Değişimi ilk sen gör"}]),
        sc(3, "offer", [{"type": "text", "text": "Bu hafta özel fiyat"},
                        {"type": "component", "component": "PriceTag", "props": {"price": 899, "currency": "TL", "label": "Sınırlı stok",
                                                                                 "referencePrice": 1199}}]),
        sc(4, "endcard", [{"type": "component", "component": "CTAPulse", "props": {"text": "Hemen sipariş ver"}}]),
        sc(5, "product", [{"type": "component", "component": "LowerThird", "props": {"title": "Ürün adı", "subtitle": "Kısa açıklama"}}]),
        sc(6, "proof", [{"type": "text", "text": "Gerçek yorumlar", "anchor": "safe_bottom"}]),
        sc(7, "demo", [{"type": "text", "text": "Ortada", "anchor": "center"}])]}


CAPS = [{"text": "bu iğne iplik altyazı satırı ikinci satıra taşar", "start": 1.0, "end": 2.0}]


@pytest.mark.parametrize("fmt", ["9x16", "4x5", "1x1"])
def test_template_defaults_are_inside_safe_zone(fmt):
    r = CK.safe_zone(_plan(fmt), STYLE, CAPS)
    assert r["ok"], r["issues"]
    assert r["checked_text_layers"] == 9  # 8 yazı katmanı + altyazı


def test_defaults_hold_with_disclaimer_bottom_40():
    p = _plan("9x16")
    p["disclaimer"] = {"on": True}
    r = CK.safe_zone(p, STYLE, CAPS)
    assert r["zone"]["bottom"] == 0.40 and r["ok"], r["issues"]


def test_old_positions_are_now_caught():
    """1.5.1'e kadar denetimin görmediği konumlar: fiyat 0,7, buton 0,8, reveal 0,7 (9:16 alt %35'te)."""
    for layer in ({"type": "component", "component": "PriceTag", "props": {"price": 1, "currency": "TL", "y": 0.7}},
                  {"type": "component", "component": "CTAPulse", "props": {"text": "Al", "y": 0.8}},
                  {"type": "text", "text": "Y", "props": {"y": 0.7}}):
        p = {"format": "9x16", "captions": {"on": False}, "scenes": [{"id": "a", "role": "reveal", "start_s": 0, "dur_s": 2, "layers": [layer]}]}
        r = CK.safe_zone(p, STYLE)
        assert not r["ok"] and "güvenli alan dışında" in r["issues"][0]["issue"], layer


def test_block_bottom_edge_counts_not_just_top():
    """Üst kenarı güvenli alanda ama uzun metin alt sınırı aşan yazı yakalanır."""
    p = {"format": "9x16", "captions": {"on": False}, "scenes": [{"id": "a", "role": "reveal", "start_s": 0, "dur_s": 2, "layers": [
        {"type": "text", "text": "Bu yazı dört satıra taşacak kadar uzun bir cümle ve devam ediyor ve bitmiyor da"}]}]}
    r = CK.safe_zone(p, STYLE)
    i = r["issues"][0]
    assert not r["ok"] and i["y0"] == pytest.approx(0.48) and i["y1"] > 0.65


def test_props_y_wins_over_anchor_like_renderer():
    p = {"format": "9x16", "captions": {"on": False}, "scenes": [{"id": "a", "role": "hook", "start_s": 0, "dur_s": 2, "layers": [
        {"type": "text", "text": "Y", "anchor": "safe_top", "props": {"y": 0.8}}]}]}
    assert not CK.safe_zone(p, STYLE)["ok"]
    top = copy.deepcopy(p)
    top["scenes"][0]["layers"][0]["props"]["y"] = 0.05  # üst %14'e giren yazı
    assert not CK.safe_zone(top, STYLE)["ok"]


def test_long_captions_hit_disclaimer_zone():
    p = {"format": "9x16", "captions": {"on": True, "preset": "keyword_upper"}, "disclaimer": {"on": True}, "scenes": [
        {"id": "a", "role": "hook", "start_s": 0, "dur_s": 2, "layers": []}]}
    long = [{"text": "çok uzun bir altyazı parçası üç satıra kadar uzayıp gidiyor ve ekranın altına iniyor", "start": 0, "end": 2}]
    r = CK.safe_zone(p, STYLE, long)
    assert not r["ok"] and r["issues"][0]["scene"] == "altyazı"
    assert CK.safe_zone(p, STYLE, CAPS)["ok"]


def test_template_reads_the_same_table():
    """Şablonda konum sabiti kalmadı: sahne ve altyazı konumu layout.ts → layout.json (denetimle aynı dosya)."""
    scenes = (SRC / "scenes" / "index.tsx").read_text(encoding="utf-8")
    master = (SRC / "Master.tsx").read_text(encoding="utf-8")
    layout = (SRC / "layout.ts").read_text(encoding="utf-8")
    assert 'from "../layout"' in scenes and "ROLE_TEXT_Y" not in scenes and "0.58" not in scenes
    assert 'componentY("CaptionTrack", plan.format)' in master
    assert 'import L from "./layout.json"' in layout
    assert TL.LAYOUT == json.loads((SRC / "layout.json").read_text(encoding="utf-8"))
    assert set(TL.LAYOUT["role_y"]) == set(TL.LAYOUT["anchor_y"]) == set(TL.LAYOUT["component_y"]) == set(CK.SAFE)
