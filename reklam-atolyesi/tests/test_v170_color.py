"""1.7.0 E: klipler arası pozlama/beyaz dengesi eşitleme — ölçüm, sınırlar, sahne ara dosyasına bağlantı, render önbellek anahtarı."""
from __future__ import annotations

import shutil
import subprocess

import numpy as np
import pytest

import color_match as CM
import doctor as DR
import render as RD
import scenes as SN
from conftest import ROOT

needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg yok")


def _clip(path, stops=0.0, r=1.0, b=1.0, w=320, h=180, fps=25, dur=2.0):
    """Doğal sahneye yakın sentetik çekim: orta tonlu gri degrade + doygunluğu düşük renk lekeleri (kırpılma yok). Kayma doğrusal ışıkta
    uygulanır (farklı ışıkta/beyaz dengesinde çekilmiş klip)."""
    yy, xx = np.mgrid[0:h, 0:w] / np.array([h, w]).reshape(2, 1, 1)
    frames = []
    for k in range(int(fps * dur)):
        t = k / (fps * dur)
        img = np.empty((h, w, 3))
        img[...] = (0.25 + 0.4 * xx)[..., None]
        for cx, cy, col in [(0.25, 0.35, (0.8, 0.6, 0.5)), (0.6, 0.4, (0.3, 0.4, 0.6)), (0.4, 0.75, (0.35, 0.55, 0.3)),
                            (0.8, 0.7, (0.85, 0.85, 0.83))]:
            img[(abs(xx - cx - 0.05 * t) < 0.1) & (abs(yy - cy) < 0.15)] = col
        lin = img ** 2.2 * np.array([r, 1.0, b]) * 2 ** stops
        frames.append((np.clip(lin, 0, 1) ** (1 / 2.2) * 255 + 0.5).astype(np.uint8).tobytes())
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "8", str(path)], input=b"".join(frames), check=True)
    return str(path)


def _plan(keys):
    return {"format": "9x16", "fps": 25, "scenes": [
        {"id": f"s{i}", "start_s": i * 1.5, "dur_s": 1.5,
         "layers": [{"type": "video", "source": {"kind": "footage", "asset": k, "in_s": 0.2, "out_s": 1.7}}]} for i, k in enumerate(keys)]}


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("renk")
    spec = {"ref": {}, "warm": {"stops": -0.4, "r": 1.06, "b": 0.94}, "dark": {"stops": -1.0}}
    return {k: {"cfr_sdr": _clip(d / f"{k}.mp4", **kw), "proxy": None} for k, kw in spec.items()}


@needs_ffmpeg
def test_darker_warmer_clip_is_pulled_to_reference(clips, tmp_path):
    raw = CM.measure(clips["warm"]["cfr_sdr"])
    ref = CM.measure(clips["ref"]["cfr_sdr"])
    assert raw["stops"] - ref["stops"] < -0.3 and raw["r_g"] / ref["r_g"] > 1.04  # ölçüm kaymayı görür
    res = SN.build(_plan(["ref", "warm"]), clips, tmp_path, "proxy", {"grade": {"lut": None}}, None, fast=True)
    cm = res["color_match"]
    assert cm["ref"]["asset"] == "ref" and cm["applied"] == ["s1:0"] and not cm["retake_candidates"]
    a = CM.measure(res["scenes"]["s0"]["0"]["path"])
    b = CM.measure(res["scenes"]["s1"]["0"]["path"])
    assert abs(b["stops"] - a["stops"]) <= 0.1
    assert abs(b["r_g"] / a["r_g"] - 1) <= 0.03 and abs(b["b_g"] / a["b_g"] - 1) <= 0.03
    # piksel düzeyinde de aynı sahne: ortalama fark gama alanında %1'in altında
    fa, fb = CM.grab(res["scenes"]["s0"]["0"]["path"], 0.75), CM.grab(res["scenes"]["s1"]["0"]["path"], 0.75)
    assert float(np.abs(fb - fa).mean()) < 0.01
    assert (tmp_path / "color_match.json").exists()


@needs_ffmpeg
def test_over_limit_clip_is_left_alone_and_listed(clips, tmp_path):
    res = SN.build(_plan(["ref", "dark"]), clips, tmp_path / "a", "proxy", {"grade": {}}, None, fast=True)
    cm = res["color_match"]
    assert cm["applied"] == [] and cm["retake_candidates"][0]["layer"] == "s1:0" and "pozlama" in cm["retake_candidates"][0]["reason"]
    off = SN.build(_plan(["ref", "dark"]), clips, tmp_path / "b", "proxy", {"grade": {"match": False}}, None, fast=True)
    assert off["color_match"]["enabled"] is False and off["color_match"]["applied"] == []
    # düzeltme yoksa zincir ve önbellek anahtarı 1.6.0 ile aynı: iki derlemede dosya adları eşit
    name = lambda r: [r["scenes"][s]["0"]["path"].rsplit("/", 1)[-1].rsplit("\\", 1)[-1] for s in ("s0", "s1")]
    assert name(res) == name(off)


def test_correction_limits_and_gamma_coefficients():
    ref = {"median_lin": 0.18, "r_g": 1.0, "b_g": 1.0}
    c = CM.correction({"median_lin": 0.18 * 2 ** -0.3, "r_g": 1.05, "b_g": 0.95}, ref)
    assert c["applied"] and abs(c["stops"] - 0.3) < 1e-3
    gr, gg, gb = c["gain_gamma"]
    assert abs(gg - 2 ** (0.3 / 2.2)) < 1e-3 and abs(gr - (2 ** 0.3 / 1.05) ** (1 / 2.2)) < 1e-3 and gb > gg > gr
    assert c["filter"].startswith("colorchannelmixer=rr=")
    assert CM.correction({"median_lin": 0.18 * 2 ** -0.7, "r_g": 1.0, "b_g": 1.0}, ref)["retake"]
    assert CM.correction({"median_lin": 0.18, "r_g": 1.2, "b_g": 1.0}, ref)["retake"]
    tiny = CM.correction({"median_lin": 0.18 * 2 ** -0.02, "r_g": 1.005, "b_g": 1.0}, ref)
    assert not tiny["applied"] and not tiny["retake"]
    assert CM.enabled(None) and CM.enabled({"grade": {}}) and not CM.enabled({"grade": {"match": False}})


def test_single_source_and_match_ref():
    rep = CM.plan_corrections(_plan(["x", "x"]), {"x": {"cfr_sdr": "/yok.mp4"}}, None)
    assert rep["ref"] is None and not rep["retake_candidates"]


def test_render_segment_key_follows_intermediate(tmp_path):
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    a.write_bytes(b"1")
    b.write_bytes(b"2")
    plan = _plan(["ref", "warm"])
    smap = {"scenes": {"s0": {"0": {"path": str(a)}}, "s1": {"0": {"path": str(b)}}}}
    h = RD.intermediate_hashes(plan, smap)
    assert set(h["s0"]) == {"ref"} and set(h["s1"]) == {"warm"}
    import scene_cache as SC
    k1 = SC.scene_key(plan, 1, source_hashes=RD._merge_hashes(h["s1"], None), style_sha=None, quality="preview", scale=0.5)
    b.write_bytes(b"3")  # ara dosya değişti (ör. renk eşitleme düzeltmesi)
    h2 = RD.intermediate_hashes(plan, smap)
    k2 = SC.scene_key(plan, 1, source_hashes=RD._merge_hashes(h2["s1"], None), style_sha=None, quality="preview", scale=0.5)
    assert k1 != k2


def test_filter_checked_at_setup_and_documented():
    assert "colorchannelmixer" in DR.FFMPEG_FILTERS
    ps1 = (ROOT / "scripts" / "setup" / "windows" / "kurulum.ps1").read_text(encoding="utf-8-sig")
    assert '"tonemap", "colorchannelmixer")' in ps1
    sd = (ROOT / "skills" / "style-directions" / "SKILL.md").read_text(encoding="utf-8")
    assert "grade.match" in sd and "color_match.py compare" in sd
    assert "color_match.json" in (ROOT / "skills" / "compose" / "SKILL.md").read_text(encoding="utf-8")
