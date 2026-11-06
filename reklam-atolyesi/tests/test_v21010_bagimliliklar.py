"""2.10.10: bağımlılık güncellemesi (dış bağımsız denetim B9). Ağ gerektirmez."""
from __future__ import annotations

import json
import sys

import pytest

from conftest import ROOT

sys.path.insert(0, str(ROOT / "scripts" / "ingest"))
sys.path.insert(0, str(ROOT / "scripts" / "setup"))


def test_python_security_pins():
    import certifi
    import PIL
    assert int(PIL.__version__.split(".")[0]) >= 13
    assert certifi.__version__ >= "2026.10.23"


def test_heic_photo_converts_to_jpeg(tmp_path):
    pillow_heif = pytest.importorskip("pillow_heif")
    from PIL import Image
    pillow_heif.register_heif_opener()
    import convert as CV
    src = tmp_path / "foto.heic"
    Image.new("RGB", (80, 40), (180, 30, 30)).save(src)
    out = CV.process_photo(src, tmp_path)
    assert out["heic"] and (out["width"], out["height"]) == (80, 40)
    with Image.open(out["output"]) as j:
        assert j.format == "JPEG"


def test_photo_exif_rotation_applied(tmp_path):
    from PIL import Image
    import convert as CV
    src = tmp_path / "foto.jpg"
    im = Image.new("RGB", (80, 40), (180, 30, 30))
    ex = im.getexif()
    ex[0x0112] = 6  # 90° döndürülmüş çekim
    im.save(src, exif=ex.tobytes())
    dst = tmp_path / "out"
    dst.mkdir()
    out = CV.process_photo(src, dst)
    assert out["exif_orientation"] == 6 and (out["width"], out["height"]) == (40, 80)


def test_remotion_and_zod_pins_match_lock():
    pkg = json.loads((ROOT / "templates" / "remotion" / "package.json").read_text(encoding="utf-8"))["dependencies"]
    lock = json.loads((ROOT / "templates" / "remotion" / "package-lock.json").read_text(encoding="utf-8"))["packages"]
    rem = {k: v for k, v in pkg.items() if k == "remotion" or k.startswith("@remotion/")}
    assert len(set(rem.values())) == 1, rem  # bütün Remotion paketleri aynı sürüm
    for k, v in rem.items():
        assert lock[f"node_modules/{k}"]["version"] == v
    major, minor, patch = (int(x) for x in pkg["zod"].split("."))
    assert (major, minor, patch) >= (4, 6, 7)
    assert lock["node_modules/zod"]["version"] == pkg["zod"]


def test_audit_report_never_blocks(monkeypatch, capsys):
    import bagimlilik_denetimi as BD
    monkeypatch.setattr(BD.shutil, "which", lambda name: None)
    assert BD.main() == 0
    out = capsys.readouterr().out
    assert "denetlenemedi" in out and '"checked": false' in out


def test_ci_runs_audit_report():
    ci = (ROOT.parent / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "bagimlilik_denetimi.py" in ci and "continue-on-error: true" in ci
