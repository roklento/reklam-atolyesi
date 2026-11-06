"""2.10.5: video ve görsel denetimi (dış kod denetimi, Dalga C). Sentetik dosyalar; ağ yok."""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

import pytest

import checks
import convert
import render
import scene_cache as SC


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


# ----------------------------------------------------------------------------- siyah kare ve donma
def test_black_freeze_missing_file_is_unmeasured(tmp_path):
    r = checks.black_freeze(str(tmp_path / "yok.mp4"))
    assert r["ok"] is False and r["measured"] is False and r["error"]


def test_black_freeze_counts_freeze_until_end(tmp_path):
    v = tmp_path / "sabit.mp4"
    _ffmpeg("-f", "lavfi", "-i", "color=c=red:s=64x64:d=2", "-pix_fmt", "yuv420p", str(v))
    r = checks.black_freeze(str(v))
    assert r["measured"] and not r["ok"]
    f = r["freeze_segments"][-1]
    assert f["until_end"] and f["dur"] and f["dur"] >= 1.0


def test_black_freeze_moving_video_is_clean(tmp_path):
    v = tmp_path / "hareketli.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc=s=64x64:d=2:r=25", "-pix_fmt", "yuv420p", str(v))
    r = checks.black_freeze(str(v))
    assert r["ok"] and r["measured"] and r["freeze_segments"] == []


# ----------------------------------------------------------------------------- fotoğraf çıktısı
def test_same_stem_photos_get_separate_outputs(tmp_path):
    from PIL import Image
    src = tmp_path / "raw"
    src.mkdir()
    Image.new("RGB", (8, 8), "red").save(src / "IMG_1.png")
    Image.new("RGB", (8, 8), "blue").save(src / "IMG_1.jpg")
    Image.new("RGB", (8, 8), "green").save(src / "IMG_2.jpg")
    out = tmp_path / "out"
    out.mkdir()
    names = {convert.process_photo(src / n, out)["output"] for n in ("IMG_1.png", "IMG_1.jpg", "IMG_2.jpg")}
    assert {Path(n).name for n in names} == {"IMG_1_png.jpg", "IMG_1_jpg.jpg", "IMG_2.jpg"}
    assert convert.process_photo(src / "IMG_2.jpg", out)["output"] in names  # aynı kaynak aynı çıktıya (yeniden çalıştırma)


# ----------------------------------------------------------------------------- sarsıntı
def _trf(tmp_path, vectors):
    lines = ["VID.STAB 1"]
    for i, (x, y) in enumerate(vectors):
        lines.append(f"Frame {i} (List 1 [(LM {x} {y} 10 10 20 20 0.5 0)])")
    p = tmp_path / "a.trf"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_shake_counts_direction_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(convert, "ffmpeg", lambda *a, **k: None)
    monkeypatch.setattr(convert, "probe", lambda p: {"width": 1000})
    monkeypatch.setattr(convert, "_vidstab_has_fileformat", lambda: True)
    jitter = convert.detect_shake(Path("x.mp4"), _trf(tmp_path, [(5, 0), (-5, 0)] * 10))
    steady = convert.detect_shake(Path("x.mp4"), _trf(tmp_path, [(5, 0)] * 20))
    assert jitter["shake_permille"] == pytest.approx(10.0) and steady["shake_permille"] == 0.0
    assert jitter["measured"] and steady["measured"]


def test_shake_without_vectors_is_unmeasured(tmp_path, monkeypatch):
    monkeypatch.setattr(convert, "ffmpeg", lambda *a, **k: None)
    monkeypatch.setattr(convert, "probe", lambda p: {"width": 1000})
    monkeypatch.setattr(convert, "_vidstab_has_fileformat", lambda: True)
    r = convert.detect_shake(Path("x.mp4"), _trf(tmp_path, []))
    assert r["measured"] is False and r["frames"] == 0


# ----------------------------------------------------------------------------- render ara dosyaları ve önbellek anahtarı
def test_stage_public_follows_content_and_keeps_same_names_apart(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "s.mp4").write_bytes(b"AAAA")
    (b / "s.mp4").write_bytes(b"CCCC")
    proj = tmp_path / "proj"
    sm = {"scenes": {"S1": {"0": {"path": str(a / "s.mp4")}}, "S2": {"0": {"path": str(b / "s.mp4")}}}}
    r1 = render.stage_public(proj, sm)
    assert r1["S1"]["0"] != r1["S2"]["0"]
    assert (proj / "public" / r1["S2"]["0"]).read_bytes() == b"CCCC"
    (a / "s.mp4").unlink()
    (a / "s.mp4").write_bytes(b"BBBB")  # aynı boyut, farklı içerik
    r2 = render.stage_public(proj, sm)
    assert (proj / "public" / r2["S1"]["0"]).read_bytes() == b"BBBB"


def _plan(props):
    return {"fps": 30, "format": "9x16", "scenes": [{"id": "S1", "start_s": 0, "dur_s": 2, "role": "hook",
                                                     "layers": [{"component": "Bilesen", "props": props}]}]}


def test_scene_key_follows_files_in_component_props():
    plan = _plan({"image": {"asset": "logo"}})
    k1 = SC.scene_key(plan, 0, source_hashes={"logo": "h1"}, style_sha=None, quality="draft", scale=1.0, component_sha="c")
    k2 = SC.scene_key(plan, 0, source_hashes={"logo": "h2"}, style_sha=None, quality="draft", scale=1.0, component_sha="c")
    assert k1 != k2


def test_scene_key_follows_unnamed_intermediate_of_its_scene():
    plan = _plan({"title": "yazı"})
    base = dict(style_sha=None, quality="draft", scale=1.0, component_sha="c")
    k1 = SC.scene_key(plan, 0, source_hashes={"S1:0.image": "h1", "S9:0": "x"}, **base)
    k2 = SC.scene_key(plan, 0, source_hashes={"S1:0.image": "h2", "S9:0": "x"}, **base)
    k3 = SC.scene_key(plan, 0, source_hashes={"S1:0.image": "h1", "S9:0": "y"}, **base)  # başka sahnenin dosyası etkilemez
    assert k1 != k2 and k1 == k3
