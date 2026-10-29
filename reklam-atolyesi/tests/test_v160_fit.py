"""1.6.0 B: gerçek ölçümlü yazı sığdırma — şablon bağlantısı, render ölçümünün toplanması ve güvenli alan denetiminde kullanımı."""
from __future__ import annotations

import json
import re

import checks as CK
import render as RD
import text_layout as TL
from conftest import ROOT

SRC = ROOT / "templates" / "remotion" / "src"


def test_layout_utils_pinned_with_remotion():
    pkg = json.loads((ROOT / "templates" / "remotion" / "package.json").read_text(encoding="utf-8"))["dependencies"]
    assert pkg["@remotion/layout-utils"] == pkg["remotion"] == "4.0.532"
    lock = json.loads((ROOT / "templates" / "remotion" / "package-lock.json").read_text(encoding="utf-8"))
    assert lock["packages"]["node_modules/@remotion/layout-utils"]["version"] == "4.0.532"


def test_text_components_use_measured_fit():
    fit = (SRC / "components" / "fit.tsx").read_text(encoding="utf-8")
    assert 'from "@remotion/layout-utils"' in fit and "validateFontIsLoaded: false" in fit and "YAZI SIĞMIYOR" in fit
    assert "document.fonts.check(" not in fit  # @font-face eklenmeden check true döner; yedek fontla ölçülürdü (render'da görüldü)
    assert 'console.log(line)' in fit and '"RA_LAYOUT "' in fit
    src = "".join((SRC / "components" / f).read_text(encoding="utf-8") for f in ("text.tsx", "proof.tsx", "product.tsx"))
    for comp in ("TextReveal", "KineticWords", "SoftType", "LowerThird", "PriceTag", "CTAPulse", "EndCard", "BehindSubjectText"):
        assert re.search(r'component: "%s"' % comp, src), comp
        assert re.search(r'name: "%s", category: "\w+", version: "1\.1\.0"' % comp, src), comp
    mjs = (ROOT / "scripts" / "render" / "render.mjs").read_text(encoding="utf-8")
    assert mjs.count("onBrowserLog: lay.onBrowserLog") == 2 and ".layout.json" in mjs


def test_lines_wraps_whole_words():
    # eski tahmin karakter/satırdan bölüyordu; sözcük bütün kalınca satır artar
    assert TL.lines("aaaa bbbb", 10, 45) == 2  # 22,4 + 2,8 + 22,4 > 45
    assert TL.lines("aaaa bb", 10, 70) == 1
    assert TL.lines("ilk\nikinci", 10, 1000) == 2
    assert TL.lines("çokuzunsözcük", 10, 20) == 1  # sözcük bölünmez, taşma ölçümle yakalanır


def _plan(text: str, y: float = 0.14):
    return {"format": "9x16", "scenes": [{"id": "s1", "role": "hook", "dur_s": 3,
                                          "layers": [{"type": "text", "text": text, "preset": "text_reveal", "props": {"y": y}}]}]}


def _rec(text: str, **kw):
    r = {"component": "TextReveal", "part": "text", "text": text, "requested": 88, "minFontSize": 52, "fontSize": 88, "lines": 2, "maxLines": 3,
         "fits": True, "heightPx": 197, "y": 0.14, "mode": "top", "width": 1080, "height": 1920}
    return {**r, **kw}


def test_safe_zone_uses_measurement_and_flags_overflow():
    text = "Kısa başlık"
    est = CK.safe_zone(_plan(text, 0.55))
    assert est["ok"] and "measured_layers" not in est
    # ölçüm blok boyunu belirler: 6 satırlık ölçülmüş blok alt sınırı (1 - 0,35) aşar
    tall = CK.safe_zone(_plan(text, 0.55), layout={"records": [_rec(text, lines=6, heightPx=6 * 88 * 1.12)]})
    assert not tall["ok"] and tall["measured_layers"] == 1 and "güvenli alan dışında" in tall["issues"][0]["issue"]
    over = CK.safe_zone(_plan(text), layout={"records": [_rec(text, fits=False, lines=5, fontSize=52)]})
    assert not over["ok"] and any("yazı sığmıyor" in i["issue"] and i["layer"] == 0 for i in over["issues"])
    stray = CK.safe_zone(_plan(text), layout={"records": [_rec("başka", component="EndCard", part="brand", fits=False, mode="full")]})
    assert any("eşlenemedi" in i["issue"] for i in stray["issues"])


def test_merge_layout_reads_cached_segments(tmp_path):
    a, b, c = (tmp_path / f"s{i}.mp4" for i in range(3))
    a.with_name(a.name + ".layout.json").write_text(json.dumps({"records": [_rec("x")]}), encoding="utf-8")
    b.with_name(b.name + ".layout.json").write_text(json.dumps({"records": [_rec("x"), _rec("y")]}), encoding="utf-8")
    m = RD.merge_layout([a, b, c])
    assert [r["text"] for r in m["records"]] == ["x", "y"] and m["unmeasured_segments"] == ["s2.mp4"]
