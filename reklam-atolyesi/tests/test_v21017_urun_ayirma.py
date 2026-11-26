"""2.10.17: tetik metni (`when_to_use`) taranır, görseli hareketlendiren skill'ler çakışma sayılır; yerel ürün ayırma aracı.

Sentetik skill klasörleri ve sentetik görseller; ağ yok, model indirilmez, hiçbir dış dosya çalıştırılmaz.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import cutout as CU
import doctor as DR
import plugin_scan as PS
import sade_dil as SD
from conftest import ROOT

CUTOUT = ROOT / "scripts" / "compose" / "cutout.py"


def _home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "ev"
    (home / ".claude" / "skills").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


def _skill(home: Path, name: str, front: str) -> None:
    d = home / ".claude" / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\n{front}\n---\n\n# {name}\n", encoding="utf-8")


def test_frontmatter_reads_trigger_text_and_block_values(tmp_path):
    """Kısa açıklama + uzun tetik metni (`when_to_use`) ve çok satırlı (>/|) değerler birleştirilerek okunur."""
    f = tmp_path / "SKILL.md"
    f.write_bytes(b"---\r\nname: ornek\r\ndescription: >\r\n  Bir satir\r\n  iki satir\r\nwhen_to_use: \"Use when the user says animate this photo\"\r\n"
                  b"metadata:\r\n  version: \"1\"\r\n---\r\n")
    fm = PS._frontmatter(f)
    assert fm == {"name": "ornek", "description": "Bir satir iki satir", "when_to_use": "Use when the user says animate this photo"}
    assert "animate this photo" in PS.trigger_text(fm)


def test_image_animation_skill_is_flagged_but_screen_recorder_is_not(tmp_path, monkeypatch):
    """Görseli döngü videoya çeviren skill (kısa açıklamada 'video' geçmese de) yakalanır; yalnızca GIF kaydı yapan araç yakalanmaz."""
    home = _home(tmp_path, monkeypatch)
    _skill(home, "resim-canlandirici", "name: resim-canlandirici\ndescription: Turn one image into a short looping animation.\n"
                                       "when_to_use: Use when the user gives a product shot and wants MP4 output.")
    _skill(home, "tetiksiz", "name: tetiksiz\ndescription: Turn one image into a short looping animation.")
    _skill(home, "tr-hareket", "name: tr-hareket\ndescription: Fotoğrafı hareketlendirir.")
    _skill(home, "tarayici-kaydi", "name: tarayici-kaydi\ndescription: Drive the browser; record a GIF of the steps.")
    assert DR.global_skill_clash() == ["resim-canlandirici", "tetiksiz", "tr-hareket"]
    info = {"skills": [{"name": "resim-canlandirici", "description": "Turn one image into a short animation.",
                        "when_to_use": "wants MP4 output"}, {"name": "tarayici-kaydi", "description": "record a GIF"}]}
    assert PS.classify(info)["video"] == ["resim-canlandirici"]


def test_plugin_inspect_carries_trigger_text(tmp_path):
    base = tmp_path / "eklenti"
    (base / "skills" / "a").mkdir(parents=True)
    (base / "skills" / "a" / "SKILL.md").write_text("---\ndescription: short\nwhen_to_use: render an mp4 clip\n---\n", encoding="utf-8")
    info = PS.inspect(str(base))
    assert info["skills"][0]["when_to_use"] == "render an mp4 clip" and PS.classify(info)["video"] == ["a"]


def _photo(w=200, h=260):
    rgb = np.zeros((h, w, 3), np.uint8)
    rgb[:] = (200, 190, 170)
    mask = np.zeros((h, w), np.uint8)
    rgb[80:220, 70:130] = (30, 70, 160)
    mask[80:220, 70:130] = 255
    return rgb, mask


def test_outputs_cutout_plate_and_mask(tmp_path):
    """Kesik ürünün saydamlığı maskedir; arka planda ürünün yerine çevresinin rengi gelir (ürün iki kez görünmez)."""
    rgb, mask = _photo()
    res = CU.build_outputs(rgb, mask, tmp_path, "urun")
    urun = np.asarray(Image.open(res["urun"]))
    assert urun.shape == (260, 200, 4) and (urun[..., 3] == mask).all()
    plate = np.asarray(Image.open(res["arka"])).astype(int)
    assert np.abs(plate[150, 100] - [200, 190, 170]).max() < 25  # ürünün ortası artık arka plan rengi
    assert (plate[10, 10] == [200, 190, 170]).all()  # boşluktan uzak pikseller değişmez
    assert res["size"] == [200, 260] and res["uyari"] is None and 0.1 < res["urun_orani"] < 0.25


def test_unreliable_separation_warns_in_plain_words(tmp_path):
    rgb, _ = _photo()
    empty = CU.build_outputs(rgb, np.zeros(rgb.shape[:2], np.uint8), tmp_path, "bos")
    full = CU.build_outputs(rgb, np.full(rgb.shape[:2], 255, np.uint8), tmp_path, "dolu")
    for r in (empty, full):
        assert r["uyari"] and SD.scan_text(r["uyari"]) == []
    assert SD.scan_text(CU.OFFER) == []


def _run(*args):
    return subprocess.run([sys.executable, str(CUTOUT), *args], capture_output=True, text=True, encoding="utf-8")


def test_install_needs_yes_and_downloads_nothing_without_it(tmp_path):
    r = _run("kur", "--data-dir", str(tmp_path))
    assert r.returncode == 2
    out = json.loads(r.stdout)
    assert out["plan"]["kullaniciya"] == CU.OFFER and out["plan"]["download_estimate_gb"] == 0.3
    assert not (tmp_path / ".gorsel").exists()


def test_separate_without_install_offers_download_and_paid_fallback(tmp_path):
    img = tmp_path / "u.png"
    Image.fromarray(_photo()[0]).save(img)
    r = _run("ayir", "--data-dir", str(tmp_path), "--image", str(img), "--out-dir", str(tmp_path / "o"))
    assert r.returncode == 5
    out = json.loads(r.stdout)
    assert out["kullaniciya"] == CU.OFFER and "ücretli" in out["alternatif"] and not (tmp_path / "o").exists()


def test_wrong_model_file_is_rejected_and_removed(tmp_path):
    src = tmp_path / "sahte.onnx"
    src.write_bytes(b"x" * 10)
    dest = tmp_path / "models" / "m.onnx"
    with pytest.raises(CU.CutoutError):
        CU.download(src.as_uri(), dest, 10, "0" * 64)
    assert not dest.exists() and not dest.with_suffix(".onnx.part").exists()


def test_installed_requires_record_env_and_exact_model(tmp_path):
    py = CU.engine_python(tmp_path)
    py.parent.mkdir(parents=True)
    py.write_text("")
    mp = CU.model_path(tmp_path)
    mp.parent.mkdir(parents=True)
    mp.write_bytes(b"eksik")
    (CU.base_dir(tmp_path) / "engines.json").write_text(json.dumps({"cutout": {"sha256": CU.MODEL["sha256"]}}), encoding="utf-8")
    assert not CU.installed(tmp_path)  # boyutu tutmayan model dosyası kurulu sayılmaz


def test_wiring_skills_doctor_manifest():
    recipes = (ROOT / "skills" / "ref-production-recipes" / "SKILL.md").read_text(encoding="utf-8")
    comps = (ROOT / "skills" / "ref-remotion-components" / "SKILL.md").read_text(encoding="utf-8")
    assert "scripts/compose/cutout.py ayir" in recipes and "yerel `cutout.py`" in recipes
    assert ".arka.png" in comps and ".urun.png" in comps
    assert ".gorsel" in DR.DATA_ALLOWED
    man = (ROOT / "scripts" / "setup" / "manifest.py").read_text(encoding="utf-8")
    assert "scripts/compose/cutout.py" in man and "scripts/compose/cutout_worker.py" in man
    assert CU.MODEL["url"].startswith("https://github.com/") and len(CU.MODEL["sha256"]) == 64
    assert all("==" in p for p in CU.PACKAGES)
