"""2.10.16: tek tek kurulan video skill'leri kurulum denetiminde görünür; yeni bileşenden önce kütüphaneye bakılır.

Sentetik skill klasörleri; ağ yok, hiçbir dosya çalıştırılmaz.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import doctor as DR
import kurulum_dogrula as KD
from conftest import ROOT

sys.path.insert(0, str(ROOT / "servers" / "ad_memory"))
from admem.editplan import ALL_COMPONENTS, COMPONENTS  # noqa: E402


def _skill(home: Path, name: str, desc: str) -> None:
    d = home / ".claude" / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\n\n# {name}\n", encoding="utf-8")


def _home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "ev"
    (home / ".claude" / "skills").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


def test_video_skill_installed_as_plain_skill_is_flagged(tmp_path, monkeypatch):
    """Plugin olmadan ~/.claude/skills altına kurulan video/kurgu skill'i adı ne olursa olsun çakışma sayılır; ilgisiz skill sayılmaz."""
    home = _home(tmp_path, monkeypatch)
    _skill(home, "html-render-araci", "Write HTML and render it to an MP4 video with captions.")
    _skill(home, "tablo-yardimcisi", "Spreadsheet formulas and pivot tables.")
    (home / ".claude" / "skills" / "remotion-render").mkdir()  # eski kural: ada göre, SKILL.md gerekmez
    (home / ".claude" / "skills" / "bos-klasor").mkdir()
    assert DR.global_skill_clash() == ["html-render-araci", "remotion-render"]


def test_acceptance_is_per_name_and_new_skill_is_asked_again(tmp_path, monkeypatch, data_dir):
    """'Dokunma' kararı kaydedilen adları kapsar; sonradan kurulan yeni video skill'i maddeyi yeniden engel yapar (plugin kabulü gibi)."""
    home = _home(tmp_path, monkeypatch)
    _skill(home, "kurgu-araci", "Edit a video: cut, captions, music.")
    rec, det = KD.handle_global_skills(data_dir, "birak", interactive=False)
    assert rec["skills"] == ["kurgu-araci"] and rec["status"] == "accepted"
    monkeypatch.setattr(DR, "load_install_deviations", lambda _dd: [rec])
    rec2, det2 = KD.handle_global_skills(data_dir, "sor", interactive=False)
    assert rec2 is None and "kabul" in det2["karar"]
    r = DR.Report()
    DR.check_global_skills(r, {"global_skills": rec["deviation"]}, [rec])
    assert r.items[0]["ok"] is False and r.items[0]["accepted_deviation"] and not r.blocking()

    _skill(home, "yeni-video-skill", "Generate short reels from a prompt.")
    rec3, det3 = KD.handle_global_skills(data_dir, "sor", interactive=False)
    assert rec3 is None and "verilmedi" in det3["karar"]
    r = DR.Report()
    DR.check_global_skills(r, {"global_skills": rec["deviation"]}, [rec])
    assert not r.items[0]["accepted_deviation"] and r.blocking()


def test_old_acceptance_without_names_covers_only_old_rule(tmp_path, monkeypatch):
    """2.10.16 öncesi kayıt adları listelemez: yalnızca eski kuralın yakaladığı (remotion*, vendor adı) skill'leri kapsar."""
    home = _home(tmp_path, monkeypatch)
    (home / ".claude" / "skills" / "remotion-render").mkdir()
    old = {"id": "global_remotion_skills", "check": "global_skills", "decided_by": "user", "status": "accepted", "deviation": "eski"}
    r = DR.Report()
    DR.check_global_skills(r, {"global_skills": "eski"}, [old])
    assert r.items[0]["accepted_deviation"]
    _skill(home, "kurgu-araci", "Edit a video: cut, captions, music.")
    r = DR.Report()
    DR.check_global_skills(r, {"global_skills": "eski"}, [old])
    assert not r.items[0]["accepted_deviation"] and r.blocking()


def test_library_lookup_before_new_component():
    """compose yeni bileşenden önce kütüphaneye ve profilin onaylı bileşenlerine bakar; dizin tablosundaki her ad gerçek bir bileşendir ve
    kullanıcıya görünen geçiş/yardımcı dışındaki her bileşen tabloda vardır."""
    compose = (ROOT / "skills" / "compose" / "SKILL.md").read_text(encoding="utf-8")
    adim = compose.replace("\r\n", "\n").split("## Adımlar", 1)[1].split("\n## ", 1)[0]
    assert "Önce kütüphanede ara" in adim and "İhtiyaca göre mevcut bileşen" in adim and "profiles/<slug>/components" in adim
    assert adim.index("Önce kütüphanede ara") < adim.index("Gereken efekt kütüphanede yoksa yazılır")
    ref = (ROOT / "skills" / "ref-remotion-components" / "SKILL.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    tablo = ref.split("## İhtiyaca göre mevcut bileşen", 1)[1].split("\n## ", 1)[0]
    adlar = set(re.findall(r"`([A-Z][A-Za-z0-9]+)`", tablo))
    assert adlar <= set(ALL_COMPONENTS)
    beklenen = set(ALL_COMPONENTS) - set(COMPONENTS["transition"]) - set(COMPONENTS["helper"])
    assert beklenen <= adlar, sorted(beklenen - adlar)
    assert ref.index("## İhtiyaca göre mevcut bileşen") < ref.index("## Yeni bileşen kuralı")
