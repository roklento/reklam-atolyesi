"""2.7.0: efektin oturma noktası (başlangıç / gövdenin gelişi / doruk), türe göre seviye, görüntüden aday anlar, efekt öz puanlaması."""
from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

import mix as MX
import sfx_moments as SM
import sfx_place as SP
import sfx_review as SR
from admem import editplan
from conftest import ROOT

RATE = 48000
E = ROOT / "vendor-skills" / "sfx-earshot"


def _riser(path, dur=1.0, peak_at=0.9):
    t = np.arange(int(dur * RATE)) / RATE
    env = np.where(t < peak_at, (t / peak_at) ** 3, np.exp(-(t - peak_at) * 40))
    y = (0.6 * env * np.sin(2 * np.pi * 600 * t)).astype("float32")
    sf.write(path, np.stack([y, y], 1), RATE)
    return str(path)


def _hit(path, silence=0.12):
    n0 = int(silence * RATE)
    t = np.arange(int(0.3 * RATE)) / RATE
    y = np.concatenate([np.zeros(n0), 0.9 * np.exp(-t * 25) * np.sin(2 * np.pi * 120 * t)]).astype("float32")
    sf.write(path, np.stack([y, y], 1), RATE)
    return str(path)


def test_anchor_from_role_path_and_shape(tmp_path):
    r = _riser(tmp_path / "riser_up.wav")
    clip = MX._read(r)
    res = SP.resolve({"at_s": 1}, r, clip)
    assert res["role"] == "riser" and res["anchor"] == "peak" and abs(res["offset_s"] - 0.9) < 0.02
    h = _hit(tmp_path / "impact_deep.wav")
    res = SP.resolve({"at_s": 1}, h, MX._read(h))
    assert res["anchor"] == "arrive" and abs(res["offset_s"] - 0.12) < 0.01
    # tür bilinmiyor: yavaş yükselen ses doruğuna, hızlı yükselen gövdesine oturur
    assert SP.resolve({"at_s": 1}, str(tmp_path / "x.wav"), clip)["anchor_from"] == "shape"
    assert SP.resolve({"at_s": 1}, str(tmp_path / "x.wav"), clip)["anchor"] == "peak"
    # açıkça verilen her zaman geçerli; 2.6 davranışı anchor=start
    assert SP.resolve({"at_s": 1, "anchor": "start"}, r, clip)["offset_s"] < 0.2
    assert SP.role_from_path(str(E / "logo_sting" / "spark.ogg")) == "logo"
    assert SP.role_from_path(str(E / "pro_sub_drop" / "low.ogg")) == "sub_drop"
    assert SP.role_from_path("sfx-cc0/interface-sounds/click_001.ogg") == "click"
    assert SP.role_from_path("/home/hit/profiles/x/kagit.wav") is None  # mutlak yoldaki klasör adı tür sayılmaz


def test_role_levels_and_file_level(tmp_path):
    h = _hit(tmp_path / "impact.wav")
    clip = MX._read(h)
    r = SP.resolve({"at_s": 0}, h, clip)
    assert r["target_peak_db"] == -4.0 and abs(r["measure"]["peak_db"] + r["gain_db"] + 4.0) < 0.2
    assert SP.resolve({"at_s": 0, "gain_db": -3}, h, clip)["gain_db"] == pytest.approx(r["gain_db"] - 3, abs=0.01)
    f = SP.resolve({"at_s": 0, "level": "file", "gain_db": -2}, h, clip)
    assert f["gain_db"] == -2 and f["target_peak_db"] is None
    quiet = (clip * 1e-3).astype("float32")  # çok kısık dosya en fazla 18 dB yükseltilir
    assert SP.resolve({"at_s": 0}, h, quiet)["gain_db"] <= SP.MAX_BOOST_DB + 1e-6


def test_mix_places_peak_on_frame(tmp_path):
    r = _riser(tmp_path / "riser.wav", 1.0, 0.9)
    plan = {"duration_s": 4, "fps": 30, "music": None, "scenes": [
        {"id": "s1", "start_s": 0, "dur_s": 4, "audio": {"mode": "none"}, "layers": [], "audio_cues": [{"sfx": "r", "at_s": 2.0}]}]}
    rep = MX.mix(plan, {}, None, None, {"r": r}, tmp_path / "stems")
    fx, _ = sf.read(rep["stems"]["sfx"], always_2d=True)
    peak_t = np.abs(fx).max(axis=1).argmax() / RATE
    assert abs(peak_t - 2.0) < 0.02  # 2.6'da doruk 2,9 sn'deydi
    p = rep["sfx_placed"][0]
    assert p["anchor"] == "peak" and p["role"] == "riser" and abs(p["start_s"] - 1.1) < 0.02


def test_schema_accepts_new_cue_fields():
    item = editplan.SCHEMA["$defs"]["scene"]["properties"]["audio_cues"]["items"] if "$defs" in editplan.SCHEMA else None
    props = (item or {}).get("properties") or _find_cue_props(editplan.SCHEMA)
    assert {"anchor", "role", "level", "gain_db"} <= set(props)
    assert props["anchor"]["enum"] == list(SP.ANCHORS)


def _find_cue_props(node):
    if isinstance(node, dict):
        if "audio_cues" in node and isinstance(node["audio_cues"], dict):
            return node["audio_cues"]["items"]["properties"]
        for v in node.values():
            r = _find_cue_props(v)
            if r:
                return r
    if isinstance(node, list):
        for v in node:
            r = _find_cue_props(v)
            if r:
                return r
    return None


def _video(path, fps=30):
    """0–1 sn duruyor, 1–2 sn kare sağa kayıyor, 2–3 sn duruyor, 3 sn'de kesme (renk değişir), 3–4 sn duruyor."""
    import cv2
    w, h = 160, 284
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for i in range(4 * fps):
        t = i / fps
        img = np.full((h, w, 3), (40, 40, 40) if t < 3 else (30, 160, 220), np.uint8)
        x = 5 if t < 1 else (5 + int((min(t, 2) - 1) * 90))
        cv2.rectangle(img, (x, 110), (x + 60, 170), (255, 255, 255), -1)
        vw.write(img)
    vw.release()
    return str(path)


def test_moments_from_picture(tmp_path):
    v = _video(tmp_path / "v.mp4")
    ts, mot, cut = SM.series(v)
    ms = SM.detect(ts, mot, cut)
    kinds = {m["kind"]: m["t"] for m in ms}
    assert "cut" in kinds and abs(kinds["cut"] - 3.0) < 0.15
    assert "onset" in kinds and abs(kinds["onset"] - 1.0) < 0.2
    assert "settle" in kinds and abs(kinds["settle"] - 2.0) < 0.2
    plan = {"scenes": [{"id": "a", "start_s": 0, "dur_s": 3, "audio_cues": [{"sfx": "x", "at_s": 1.0}]},
                       {"id": "b", "start_s": 3, "dur_s": 1}]}
    pm = SM.to_plan(ms, plan)
    on = next(m for m in pm if m["kind"] == "onset")
    assert on["covered"] and on["scene"] == "a"
    c = next(m for m in pm if m["kind"] == "cut")
    assert not c["covered"] and c["scene"] == "b" and c["role"] == "whoosh"


def test_review_axes_and_listen_list(tmp_path):
    r = _riser(tmp_path / "riser.wav")
    h = _hit(tmp_path / "impact.wav")
    speech = (0.3 * np.sin(2 * np.pi * 220 * np.arange(2 * RATE) / RATE)).astype("float32")
    sf.write(tmp_path / "seg.wav", np.stack([speech, speech], 1), RATE)
    plan = {"duration_s": 4, "fps": 30, "music": None, "scenes": [
        {"id": "s1", "start_s": 0, "dur_s": 2, "audio": {"mode": "original"}, "layers": [], "audio_cues": [{"sfx": "hit", "at_s": 1.0}]},
        {"id": "s2", "start_s": 2, "dur_s": 2, "audio": {"mode": "none"}, "layers": [],
         "audio_cues": [{"sfx": "riser", "at_s": 1.0}, {"sfx": "hit", "at_s": 1.9}]}]}
    rep = MX.mix(plan, {"s1": str(tmp_path / "seg.wav")}, None, None, {"hit": h, "riser": r}, tmp_path / "stems")
    res = SR.review(rep, plan, {"moments": [{"t": 0.5, "kind": "cut", "strength": 0.9, "covered": False, "role": "whoosh",
                                              "query": "geçiş"}]})
    ax = res["axes"]
    assert ax["sync"] >= 9  # yerleştirme ölçümle doğrulanır
    assert ax["speech"] < 10 and any(p["axis"] == "speech" for p in res["worst"] + [])  # 1 sn'deki darbe konuşmanın üstünde
    assert ax["cutoff"] < 10  # 3,9 sn'deki darbe 4 sn'de kesiliyor
    assert ax["coverage"] == 9
    assert 1 <= len(res["listen"]) <= 5 and all("tc" in x for x in res["listen"])
    assert res["pass"] is False
