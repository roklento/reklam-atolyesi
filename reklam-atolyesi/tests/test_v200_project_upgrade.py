"""2.0.0: eski kampanya projesinin güvenli güncellenmesi, eski projeye uymayan planın açık hatası ve projeye bağlı sahne önbelleği anahtarı."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys

import pytest

import render as RD
from conftest import ROOT

SRC = ROOT / "templates" / "remotion" / "src"


def _plan(layers):
    return {"format": "9x16", "fps": 30, "status": "draft", "scenes": [{"id": "s1", "role": "proof", "start_s": 0, "dur_s": 3, "layers": layers}]}


def _old_project(tmp_path, monkeypatch):
    """Güncel şablondan kurulan projede iki dosya "yayımlanmış eski sürüm", biri elle değiştirilmiş, biri eksik."""
    proj = tmp_path / "kampanya" / "src"
    RD.init_project(proj)
    old_scenes = b"// eski sahne sablonu (1.7.0 benzeri: kaynak alan ve odak yok)\nexport const LayerStack = () => null;\n"
    old_camera = (SRC / "components" / "camera.tsx").read_bytes().replace(b'name: "KenBurns"', b'name: "KenBurnsEski"')
    (proj / "scenes" / "index.tsx").write_bytes(old_scenes)
    (proj / "components" / "camera.tsx").write_bytes(old_camera)
    (proj / "style.ts").write_bytes((SRC / "style.ts").read_bytes() + "\n// kampanyaya özel değişiklik\n".encode())
    (proj / "beats.ts").unlink()
    (proj / "components" / "ozel.tsx").write_text('export const OZEL = [{ name: "MarkaRozeti" }];\n', encoding="utf-8")
    hist = json.loads(RD.HISTORY.read_text(encoding="utf-8"))
    hist["files"]["scenes/index.tsx"] = hist["files"]["scenes/index.tsx"] + [hashlib.sha256(old_scenes).hexdigest()]
    hist["files"]["components/camera.tsx"] = hist["files"]["components/camera.tsx"] + [hashlib.sha256(old_camera).hexdigest()]
    hp = tmp_path / "template_history.json"
    hp.write_text(json.dumps(hist), encoding="utf-8")
    monkeypatch.setattr(RD, "HISTORY", hp)
    return proj


def test_history_covers_current_template():
    # yayın koruması: şablon değişip template_history.py yeniden çalıştırılmazsa upgrade güncel dosyayı "özelleştirilmiş" sanardı
    hist = json.loads((ROOT / "templates" / "remotion" / "template_history.json").read_text(encoding="utf-8"))["files"]
    for f in SRC.rglob("*"):
        if f.is_file():
            rel = f.relative_to(SRC).as_posix()
            assert hashlib.sha256(f.read_bytes()).hexdigest() in hist.get(rel, []), rel


def test_state_and_upgrade(tmp_path, monkeypatch):
    proj = _old_project(tmp_path, monkeypatch)
    st = RD.project_template_state(proj)
    assert sorted(st["stale"]) == ["components/camera.tsx", "scenes/index.tsx"]
    assert st["customized"] == ["style.ts"] and st["missing"] == ["beats.ts"]
    dry = RD.upgrade_project(proj, dry_run=True)
    assert dry["updated"] == st["stale"] and (proj / "scenes" / "index.tsx").read_bytes() != (SRC / "scenes" / "index.tsx").read_bytes()
    r = RD.upgrade_project(proj)
    assert sorted(r["updated"]) == ["components/camera.tsx", "scenes/index.tsx"] and r["added"] == ["beats.ts"]
    assert r["kept_customized"] == ["style.ts"] and "Özelleştirilmiş" in r["note"]
    for rel in ("scenes/index.tsx", "components/camera.tsx", "beats.ts"):
        assert (proj / rel).read_bytes() == (SRC / rel).read_bytes(), rel
    assert b"kampanyaya" in (proj / "style.ts").read_bytes()  # elle değiştirilen dosyaya dokunulmaz
    assert (proj / "components" / "ozel.tsx").exists()  # şablonda olmayan profil bileşeni kalır
    assert RD.project_template_state(proj)["stale"] == []


def test_upgrade_refuses_non_project(tmp_path):
    with pytest.raises(SystemExit, match="kampanya projesi değil"):
        RD.upgrade_project(tmp_path)


def test_old_project_gaps_and_render_stops_early(tmp_path, monkeypatch):
    proj = _old_project(tmp_path, monkeypatch)
    ba = {"type": "component", "component": "BeforeAfter", "props": {}}
    kb = {"type": "video", "source": {"path": "x.mp4"}, "camera": {"preset": "kenburns_in", "focus": {"x": 0.3, "y": 0.4}}}
    gaps = RD.project_gaps(proj, _plan([ba, kb, {"type": "component", "component": "KenBurns"}, {"type": "component", "component": "MarkaRozeti"}]))
    assert any("kaynak alan" in g for g in gaps) and any("odak" in g for g in gaps) and "bileşen yok: KenBurns" in gaps
    assert "bileşen yok: MarkaRozeti" in gaps  # klasörde olup kayda (components/index.ts) alınmamış dosya çizilemez
    # init eksik bileşen dosyasını kopyalar ama eski kayıt onu içe aktarmaz: dosyanın varlığı yetmez
    idx = proj / "components" / "index.ts"
    idx.write_bytes(idx.read_bytes().replace(b'import { COMPARE } from "./compare";', b""))
    assert "bileşen yok: BeforeAfter" in RD.project_gaps(proj, _plan([ba]))
    idx.write_bytes(idx.read_bytes() + b'import { OZEL } from "./ozel";\n')
    assert "bileşen yok: MarkaRozeti" not in RD.project_gaps(proj, _plan([{"type": "component", "component": "MarkaRozeti"}]))
    assert RD.project_gaps(proj, _plan([{"type": "component", "component": "TextReveal"}])) == []  # eski proje eski planı çizer
    with pytest.raises(SystemExit, match="render.py upgrade"):
        RD.render_plan(tmp_path / "dd", proj, _plan([ba]), tmp_path / "x.mp4", None, None, None, None, "preview", 1, None, True, None)
    r = RD.upgrade_project(proj)
    assert r["kept_customized"] == ["components/index.ts", "style.ts"]  # elle değiştirilmiş kayıt korunur, listelenir
    idx.write_bytes((SRC / "components" / "index.ts").read_bytes())
    assert RD.project_gaps(proj, _plan([ba, kb])) == []


def test_new_project_has_no_gaps(tmp_path):
    proj = tmp_path / "yeni" / "src"
    RD.init_project(proj)
    layers = [{"type": "component", "component": n, "props": {}} for n in ("BeforeAfter", "NumberRoll", "TextMark", "PictureInPicture", "PhoneScreen")]
    assert RD.project_gaps(proj, _plan(layers + [{"type": "video", "camera": {"preset": "kenburns_out", "settle_s": 0.5}}])) == []
    st = RD.project_template_state(proj)
    assert not st["stale"] and not st["customized"] and not st["missing"]


def test_scene_cache_key_follows_project_code(tmp_path):
    proj = tmp_path / "p" / "src"
    RD.init_project(proj)
    h0 = RD.project_code_hash(proj)
    (proj / "public" / "a.json").write_text("{}", encoding="utf-8")
    (proj / ".segments").mkdir()
    (proj / ".segments" / "x.json").write_text("{}", encoding="utf-8")
    assert RD.project_code_hash(proj) == h0  # varlıklar ve segmentler kod değildir
    (proj / "components" / "ozel.tsx").write_text("export const X = 1;\n", encoding="utf-8")
    assert RD.project_code_hash(proj) != h0  # özel bileşen eklenince eski segmentler yeniden kullanılmaz


def test_upgrade_cli(tmp_path):
    proj = tmp_path / "c" / "src"
    RD.init_project(proj)
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "render" / "render.py"), "upgrade", "--project", str(proj), "--dry-run"],
                         capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    r = json.loads(out.stdout)
    assert r["dry_run"] and r["updated"] == [] and r["kept_customized"] == []
