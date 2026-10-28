"""1.5.1: küçük yazının öz denetimde görülmesi — font glif kapsamı (qc/font_coverage.py) ve yazı şeritleri (contact_sheet --text-bands)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import contact_sheet as CS
import font_coverage as FC
import self_review as SR

UNICODE = {"latin": "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122",
           "latin-ext": "U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,"
                        "U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF"}


def _subset_css(pkg: str, family: str, subset: str, weight: int) -> str:
    # fontsource alt küme CSS'i: unicode-range YAZMAZ (kapsam paketin unicode.json'undan)
    return (f"/* {pkg}-{subset}-{weight}-normal */\n@font-face {{\n  font-family: '{family}';\n  font-style: normal;\n  font-display: swap;\n"
            f"  font-weight: {weight};\n  src: url(./files/{pkg}-{subset}-{weight}-normal.woff2) format('woff2');\n}}\n")


def _package(nm: Path, pkg: str, family: str, weights=(400, 700)) -> None:
    d = nm / "@fontsource" / pkg
    d.mkdir(parents=True, exist_ok=True)
    (d / "unicode.json").write_text(json.dumps(UNICODE), encoding="utf-8")
    for w in weights:
        for sub in ("latin", "latin-ext"):
            (d / f"{sub}-{w}.css").write_text(_subset_css(pkg, family, sub, w), encoding="utf-8")
        # tam ağırlık CSS'i: her alt küme unicode-range ile
        (d / f"{w}.css").write_text("".join(_subset_css(pkg, family, s, w).replace("format('woff2');", f"format('woff2');\n  unicode-range: {r};")
                                            for s, r in UNICODE.items()), encoding="utf-8")


def _project(root: Path, imports: list[str]) -> Path:
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "index.ts").write_text("export {};\n", encoding="utf-8")
    (src / "style.ts").write_text("".join(f'import "{i}";\n' for i in imports) + "export const x = 1;\n", encoding="utf-8")
    return src


INTER = ["@fontsource/inter/latin-400.css", "@fontsource/inter/latin-ext-400.css", "@fontsource/inter/latin-700.css",
         "@fontsource/inter/latin-ext-700.css"]


def _plan(text: str = "Değişim başlıyor", comp_props: dict | None = None, fmt: str = "9x16", captions_on: bool = False) -> dict:
    scenes = [{"id": "s1", "role": "hook", "start_s": 0.0, "dur_s": 2.0, "audio": {"mode": "none"},
               "layers": [{"type": "text", "preset": "text_reveal", "text": text, "anchor": "safe_top"}]}]
    if comp_props is not None:
        scenes.append({"id": "s2", "role": "offer", "start_s": 2.0, "dur_s": 2.0, "audio": {"mode": "none"},
                       "layers": [{"type": "component", "component": "PriceTag", "props": comp_props}]})
    return {"format": fmt, "fps": 30, "duration_s": 2.0 * len(scenes), "captions": {"on": captions_on, "preset": "plain"}, "scenes": scenes}


def test_font_missing_latin_ext_falls_back(tmp_path):
    nm = tmp_path / "node_modules"
    _package(nm, "inter", "Inter")
    _package(nm, "marka-sans", "Marka Sans", (700,))
    style = {"fonts": {"display": "Marka Sans", "displayWeight": 700}}
    src = _project(tmp_path / "k", INTER + ["@fontsource/marka-sans/latin-700.css"])
    r = FC.coverage(_plan("Değişim başlıyor"), style, src, nm)
    assert r["checked"] and not r["ok"]
    miss = {m["family"]: m for m in r["missing"]}
    assert set("ğĞşŞİ") <= set(miss["Marka Sans"]["chars"]) and "s1/0" in miss["Marka Sans"]["where"]
    assert "ü" not in miss["Marka Sans"]["chars"] and "ı" not in miss["Marka Sans"]["chars"]  # latin alt kümesinde
    assert "Inter" not in miss
    # latin-ext eklenince geçer
    src = _project(tmp_path / "k", INTER + ["@fontsource/marka-sans/latin-700.css", "@fontsource/marka-sans/latin-ext-700.css"])
    assert FC.coverage(_plan("Değişim başlıyor"), style, src, nm)["ok"]


def test_font_only_latin_ext_drops_basic_letters(tmp_path):
    nm = tmp_path / "node_modules"
    _package(nm, "inter", "Inter")
    _package(nm, "marka-sans", "Marka Sans", (700,))
    src = _project(tmp_path / "k", INTER + ["@fontsource/marka-sans/latin-ext-700.css"])
    r = FC.coverage(_plan("Ürün"), {"fonts": {"display": "Marka Sans"}}, src, nm)
    assert not r["ok"] and "r" in r["missing"][0]["chars"] and "Ü" in r["missing"][0]["chars"]


def test_font_full_weight_css_with_unicode_range_and_weight_gap(tmp_path):
    nm = tmp_path / "node_modules"
    _package(nm, "inter", "Inter")
    _package(nm, "marka-sans", "Marka Sans", (700,))
    src = _project(tmp_path / "k", INTER + ["@fontsource/marka-sans/700.css"])
    plan = _plan("Şimdi", {"price": 899, "currency": "₺", "label": "Sınırlı stok", "fontFamily": "Marka Sans"})
    r = FC.coverage(plan, {"fonts": {"display": "Marka Sans"}}, src, nm)
    assert r["ok"], r
    # PriceTag 400 ağırlığında yazı çizer (etiket, eski fiyat); yalnızca 700 yüklü → uyarı, bulgu değil
    assert any(g["family"] == "Marka Sans" and g["weight"] == 400 for g in r["weight_gaps"])


def test_font_not_loaded_and_not_checked(tmp_path):
    nm = tmp_path / "node_modules"
    _package(nm, "inter", "Inter")
    src = _project(tmp_path / "k", INTER + ["@fontsource/yok/latin-700.css"])
    r = FC.coverage(_plan("Örnek"), {"fonts": {"display": "Marka Serif"}}, src, nm)
    assert not r["ok"]
    issues = " ".join(u["issue"] for u in r["unresolved"])
    assert "Marka Serif" in issues and "@fontsource/yok/latin-700.css" in json.dumps(r["unresolved"])
    r = FC.coverage(_plan("Örnek"), None, None, nm)
    assert r["checked"] is False and r["ok"] is False and "denetlenemedi" in r["reason"]


def test_font_captions_upper_and_neutral_inter(tmp_path):
    nm = tmp_path / "node_modules"
    _package(nm, "inter", "Inter")
    src = _project(tmp_path / "k", ["@fontsource/inter/latin-700.css"])  # 400 ve latin-ext eksik
    plan = _plan("Örnek", captions_on=True)
    plan["captions"]["preset"] = "keyword_upper"
    r = FC.coverage(plan, None, src, nm, [{"text": "iğne iplik", "start": 0.2, "end": 1.0}])
    assert not r["ok"] and "İ" in r["missing"][0]["chars"] and "altyazı" in r["missing"][0]["where"]


def test_text_moments_follow_template_positions():
    plan = {"format": "9x16", "duration_s": 12.0, "captions": {"on": True}, "scenes": [
        {"id": "a", "role": "hook", "start_s": 0, "dur_s": 2, "layers": [{"type": "text", "text": "X", "anchor": "safe_top"}]},
        {"id": "b", "role": "reveal", "start_s": 2, "dur_s": 2, "layers": [{"type": "text", "text": "Y"}]},
        {"id": "c", "role": "offer", "start_s": 4, "dur_s": 2, "layers": [{"type": "component", "component": "PriceTag", "props": {"price": 1}}]},
        {"id": "d", "role": "proof", "start_s": 6, "dur_s": 2, "layers": [{"type": "component", "component": "ReviewCard", "props": {"quote": "q"}}]},
        {"id": "e", "role": "product", "start_s": 8, "dur_s": 2, "layers": [{"type": "text", "text": "Z", "props": {"y": 0.5}, "start_s": 0.5, "dur_s": 1.0},
                                                                            {"type": "component", "component": "LightRays"}]},
        {"id": "f", "role": "endcard", "start_s": 10, "dur_s": 2, "layers": [{"type": "component", "component": "Ozel", "props": {"title": "Başlık"}}]}]}
    ms = {m["where"]: m for m in CS.text_moments(plan, {"layout": {"9x16": {"titleY": 0.14}}}, [{"text": "uzun altyazı", "start": 1.0, "end": 2.0}])}
    assert ms["a/0"]["y0"] == pytest.approx(0.14) and ms["a/0"]["t"] == pytest.approx(1.3)
    assert ms["b/0"]["y0"] == pytest.approx(0.68)  # reveal rolünün şablon konumu 0,7
    assert ms["c/0"]["y0"] == pytest.approx(0.61) and ms["c/0"]["y1"] == pytest.approx(0.79)  # PriceTag ortası 0,7
    assert (ms["d/0"]["y0"], ms["d/0"]["y1"]) == (0.28, 0.72)
    assert ms["e/0"]["y0"] == pytest.approx(0.48) and ms["e/0"]["t"] == pytest.approx(8.5 + 0.65)  # props.y anchor'ı ezer
    assert "e/1" not in ms and ms["f/0"]["component"] == "Ozel"  # yazısız bileşen yok; yazılı profil bileşeni var
    assert ms["altyazı"]["t"] == pytest.approx(1.5)
    order = [m["component"] for m in CS.text_moments(plan, None, None)]
    assert order[:2] == ["PriceTag", "ReviewCard"]  # küçük yazılı bileşenler önce (sınır aşılırsa)


def _video(path: Path, w: int = 540, h: int = 960, dur: float = 4.0, stripe=(0.45, 0.55)) -> Path:
    y, hh = int(h * stripe[0]), int(h * (stripe[1] - stripe[0]))
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=c=gray:s={w}x{h}:d={dur}:r=30",
                    "-vf", f"drawbox=x=0:y={y}:w={w}:h={hh}:color=red:t=fill", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def test_text_bands_crop_and_pages(tmp_path):
    from PIL import Image
    v = _video(tmp_path / "v.mp4")
    plan = _plan("Başlık", {"price": 5, "y": 0.5})
    r = CS.text_bands(str(v), plan, str(tmp_path / "bands.jpg"))
    assert r["width"] == 540 and len(r["bands"]) == 2 and r["sheets"]
    im = Image.open(r["sheets"][0]).convert("RGB")
    assert im.width == 540 and im.height <= CS.PAGE_H
    # PriceTag şeridi (y 0,41–0,59) kırmızı şeridi ortalar: şeridin ortası kırmızı
    pt = next(i for i, b in enumerate(sorted(r["bands"], key=lambda b: b["t"])) if b["component"] == "PriceTag")
    assert pt == 1
    px = im.getpixel((270, im.height - int(960 * 0.18) // 2))
    assert px[0] > 180 and px[1] < 90, px
    many = {"format": "9x16", "duration_s": 4.0, "scenes": [{"id": f"s{i}", "role": "proof", "start_s": 0.3 * i, "dur_s": 0.3, "layers": [
        {"type": "component", "component": "ReviewCard", "props": {"quote": "q"}}]} for i in range(13)]}
    r = CS.text_bands(str(v), many, str(tmp_path / "many.jpg"))
    assert len(r["bands"]) == CS.MAX_BANDS and len(r["skipped"]) == 1 and len(r["sheets"]) > 1
    assert all(Image.open(p).height <= CS.PAGE_H for p in r["sheets"])


def test_self_review_reports_fonts_and_bands(tmp_path):
    dd = tmp_path / "veri"
    nm = dd / ".node" / "node_modules"
    _package(nm, "inter", "Inter")
    _package(nm, "marka-sans", "Marka Sans", (700,))
    camp = dd / "profiles" / "marka" / "campaigns" / "k1"
    _project(camp, INTER + ["@fontsource/marka-sans/latin-700.css"])
    v = _video(tmp_path / "v.mp4")
    plan = _plan("Değişim başlıyor", {"price": 5, "currency": "TL"})
    plan["captions"] = {"on": False}
    style = {"fonts": {"display": "Marka Sans", "displayWeight": 700}}
    # --project / --data-dir verilmeden out-dir'in üst klasörlerinden bulunur
    rv = SR.review(str(v), plan, camp / "analysis" / "review_a", style, None, 1)
    assert rv["font_coverage"]["checked"] and any(f["kind"] == "font_glyph" for f in rv["numeric_findings"])
    assert rv["next"].startswith("Düzelt")
    assert rv["text_bands"]["sheets"] and set(rv["text_bands"]["sheets"]) <= set(rv["frames_to_inspect"])
    saved = json.loads((camp / "analysis" / "review_a" / "self_review_r1.json").read_text(encoding="utf-8"))
    assert saved["font_coverage"]["missing"] and saved["text_bands"]["bands"]
    # proje bulunamazsa kontrol yapılmadığı uyarıdır (sessiz geçmez)
    rv = SR.review(str(v), plan, tmp_path / "baska" / "review_b", style, None, 1)
    assert rv["font_coverage"]["checked"] is False and any("denetlenemedi" in w for w in rv["warnings"])
    assert not any(f["kind"].startswith("font_") for f in rv["numeric_findings"])
