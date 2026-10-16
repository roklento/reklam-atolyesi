"""Medya boru hatları (spec 5.4–5.14, 5.19) — küçük çözünürlükte hızlı sentetik testler; 4K uçtan uca duman testindedir (12.12)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import beats as BE
import contact_sheet as CS
import convert as CV
import fixtures as FX
import loudness as LN
import measure as ME
import material_map as MM
import mix as MX
import sfx_synth as SY
import words_align as WA


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    d = tmp_path_factory.mktemp("medya")
    camp = d / "kampanya"
    (camp / "footage" / "raw").mkdir(parents=True)
    (camp / "photos" / "raw").mkdir(parents=True)
    FX.clip_vfr(camp / "footage" / "raw" / "S01_t1.mov", 360, 640)
    FX.clip_hlg(camp / "footage" / "raw" / "S02_t1.mov", 360, 640)
    FX.clip_shaky(camp / "footage" / "raw" / "S03_t1.mov", 360, 640)
    FX.photo_exif(camp / "photos" / "raw" / "F01.jpg")
    FX.photo_heic(camp / "photos" / "raw" / "F02.heic")
    man = CV.ingest(camp, 30, fast=True)
    return {"dir": d, "camp": camp, "manifest": json.loads(Path(man["manifest"]).read_text(encoding="utf-8")), "summary": man}


def test_probe_detects_vfr_and_hlg(media):
    raw = media["camp"] / "footage" / "raw"
    assert CV.probe(raw / "S01_t1.mov")["vfr"]
    p = CV.probe(raw / "S02_t1.mov")
    assert p["hdr"] and p["hdr_kind"] == "HLG"


def test_ingest_outputs(media):
    m = media["manifest"]
    assert not media["summary"]["errors"], media["summary"]["errors"]
    by = {Path(f["source"]).stem: f for f in m["footage"]}
    cfr = CV.probe(by["S01_t1"]["cfr_sdr"])
    assert cfr["avg_fps"] == pytest.approx(30, abs=0.01) and not cfr["vfr"]
    sdr = CV.probe(by["S02_t1"]["cfr_sdr"])
    assert not sdr["hdr"] and sdr["color_transfer"] == "bt709"
    assert by["S03_t1"]["shake"]["shake_permille"] > by["S01_t1"]["shake"]["shake_permille"]
    assert by["S03_t1"]["stabilized"] and Path(by["S03_t1"]["stabilized"]).exists()
    assert by["S01_t1"]["audio_wav"]
    photos = {Path(p["source"]).name: p for p in m["photos"]}
    assert photos["F01.jpg"]["width"] == 900  # EXIF yönü uygulandı (dikey)
    assert photos["F02.heic"]["heic"] and photos["F02.heic"]["output"].endswith(".jpg")
    assert len(by["S01_t1"]["sha256"]) == 64


def test_measure_contact_sheet_material_map(media, tmp_path):
    clip = [f for f in media["manifest"]["footage"] if "S01" in f["source"]][0]
    r = ME.video_metrics(clip["proxy"])
    sc = ME.scores(r, clip["shake"]["shake_permille"], ME.audio_metrics(clip["audio_wav"]))
    assert 0 <= sc["overall"] <= 1 and ME.best_ranges(r)
    s = CS.sheet(clip["proxy"], str(tmp_path / "k.jpg"))
    assert Path(s["sheet"]).exists() and s["grid"] == [6, 4]
    mm = MM.build([{"no": "S01", "concept": "A", "what": "ürün", "ai_ok": False}, {"no": "S09", "concept": "A", "what": "detay", "ai_ok": True}],
                  [{"asset": "a1", "shot_no": "S01", "score": {"overall": 0.8}, "best_ranges": [{"in_s": 0.5, "out_s": 2.5}]}])
    assert mm["ai_completable"] == ["S09"] and not mm["missing"]


def test_beats_click_track(tmp_path):
    p = FX.click_track(tmp_path / "c.wav", 120, 12)
    b = BE.analyze(str(p))
    assert b["tempo_bpm"] == pytest.approx(120, rel=0.05) and len(b["downbeats"]) >= 4
    assert BE.snap(1.02, [1.0], 30) == 1.0 and BE.snap(1.5, [1.0], 30) == 1.5


def test_sfx_loudnorm_phone(tmp_path):
    for k in SY.KINDS:
        out = SY.write(str(tmp_path / f"{k}.wav"), SY.synth(k, 0.5))
        assert Path(out["out"]).exists()
    v = FX.noisy_voice(tmp_path / "v.wav", 6)
    r = LN.loudnorm(str(v), str(tmp_path / "v_ln.wav"))
    assert r["ok"] and abs(r["verify"]["lufs"] + 14) <= 1 and r["verify"]["true_peak_dbtp"] <= -0.95
    assert Path(LN.phone(str(v), str(tmp_path / "ph.wav"))["out"]).exists()
    assert Path(LN.clean(str(v), str(tmp_path / "cl.wav"))["out"]).exists()


def test_mix_modes(tmp_path):
    seg = FX.noisy_voice(tmp_path / "seg.wav", 2)
    music = FX.click_track(tmp_path / "m.wav", 100, 7)
    vo = FX.noisy_voice(tmp_path / "vo.wav", 6)
    sfx = SY.write(str(tmp_path / "w.wav"), SY.synth("whoosh", 0.4))["out"]
    plan = {"duration_s": 6, "fps": 30, "music": {"offset_s": 0, "gain_db": -8}, "scenes": [
        {"id": "s1", "start_s": 0, "dur_s": 2, "audio": {"mode": "original"}, "layers": []},
        {"id": "s2", "start_s": 2, "dur_s": 2, "audio": {"mode": "original_clean"}, "layers": [], "audio_cues": [{"sfx": "w", "at_s": 0.2}]},
        {"id": "s3", "start_s": 4, "dur_s": 2, "audio": {"mode": "generated"}, "layers": []}]}
    r = MX.mix(plan, {"s1": str(seg), "s2": str(seg)}, str(music), str(vo), {"w": sfx}, tmp_path / "stems")
    assert r["loudness_ok"] and {a["mode"] for a in r["applied_modes"]} == {"original", "original_clean", "generated"}
    assert all(Path(p).exists() for p in r["stems"].values())


def test_words_align_matches_script(tmp_path):
    tr = {"words": [{"text": "Örnek", "start": 0.0, "end": 0.4}, {"text": "metin", "start": 0.4, "end": 0.8}, {"text": "burada.", "start": 0.8, "end": 1.3}]}
    (tmp_path / "t.json").write_text(json.dumps(tr), encoding="utf-8")
    (tmp_path / "s.txt").write_text("Örnek metin burada.", encoding="utf-8")
    words = WA.extract_words(tr)
    assert WA.norm_words("Örnek metin burada.") == WA.norm_words(" ".join(w["text"] for w in words))
    assert WA.chunks(words)[0]["text"] == "Örnek metin burada."


def test_palette_svg_and_raster(tmp_path):
    import palette as PA
    from PIL import Image
    svg = tmp_path / "logo.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect fill="#336699" width="10" height="10"/>'
                   '<circle style="fill:#C33" r="3"/><path stroke="rgb(10,20,30)" fill="#336699"/></svg>', encoding="utf-8")
    r = PA.extract(svg, 5)
    hexes = [c["hex"] for c in r["colors"]]
    assert hexes[0] == "#336699" and "#cc3333" in hexes and "#0a141e" in hexes
    png = tmp_path / "logo.png"
    im = Image.new("RGBA", (40, 40), (250, 250, 250, 255))
    for x in range(10, 30):
        for y in range(10, 30):
            im.putpixel((x, y), (20, 120, 60, 255))
    im.save(png)
    r2 = PA.extract(png, 3)
    assert r2["kind"] == "raster" and len(r2["colors"]) >= 2
    bg = [c for c in r2["colors"] if c.get("maybe_background")]
    assert bg and bg[0]["luminance"] > 0.9


def test_preview_scale_is_plain_half():
    """Remotion çift boyut yuvarlamasını kendisi yapar; ölçek büyütülürse tam sayı olmayan piksel boyutu çıkar (4:5 → 540×674)."""
    import render as RE
    for fmt in ("9x16", "4x5", "1x1"):
        assert RE._even_scale(fmt, 0.5) == 0.5


def test_loudnorm_high_lra_hits_target(tmp_path):
    """Ölçülen LRA hedefin üstündeyse ffmpeg dinamik moda düşmesin; -14 LUFS / ≤ -1 dBTP doğrulanır (5.13)."""
    import numpy as np
    import soundfile as sf
    sr = 48000
    t = np.arange(sr * 12) / sr
    y = 0.02 * np.sin(2 * np.pi * 220 * t)
    y[sr * 6:] *= 15  # sessiz yarı + yüksek yarı → yüksek LRA
    sf.write(str(tmp_path / "lra.wav"), np.stack([y, y], axis=1).astype(np.float32), sr)
    r = LN.loudnorm(str(tmp_path / "lra.wav"), str(tmp_path / "lra_out.wav"))
    assert r["ok"], r
    assert abs(r["verify"]["lufs"] + 14) <= 1.0 and r["verify"]["true_peak_dbtp"] <= -0.95


def test_export_keeps_true_peak_after_aac(tmp_path):
    """AAC kodlaması gerçek tepeyi yükseltebilir; teslim dosyası ölçülür ve ≤ -1 dBTP'ye çekilir (5.13, 5.16)."""
    import numpy as np
    import soundfile as sf
    import export as EX
    from common import ffmpeg
    v = tmp_path / "v.mp4"
    ffmpeg(["-f", "lavfi", "-i", "testsrc2=size=360x640:rate=30:duration=3", "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", str(v)])
    sr = 48000
    t = np.arange(sr * 3) / sr
    rng = np.random.default_rng(1729)
    y = np.clip(0.9 * np.sign(np.sin(2 * np.pi * 997 * t)) * (0.6 + 0.4 * rng.random(t.size)), -0.89, 0.89)  # tepeye yakın kare dalga
    sf.write(str(tmp_path / "a.wav"), np.stack([y, y], axis=1).astype(np.float32), sr)
    r = EX.export_video(str(v), str(tmp_path / "a.wav"), tmp_path / "out", "MRKA_K1_A_video_3_h1_vo_real_c1_r1", "9x16")
    assert LN.measure(r["out"])["true_peak_dbtp"] <= -1.0
