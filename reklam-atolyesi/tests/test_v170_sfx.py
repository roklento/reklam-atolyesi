"""1.7.0 L: CC0 ses efekti çekirdeği (soundcn üzerinden Kenney) — dosya başına kaynak kaydı, kayıtsız/değişmiş dosya listelenmez,
WoW koleksiyonu yok, Türkçe sorgu."""
from __future__ import annotations

import json
import shutil

import doctor as DR
import sfx_library as SL
from conftest import ROOT

V = ROOT / "vendor-skills" / "sfx-cc0"


def test_only_recorded_kenney_files_are_listed():
    allowed = SL.cc0_allowed()
    assert len(allowed) == 377
    rels = {p.relative_to(V).as_posix() for p, _ in allowed}
    assert {r.split("/")[0] for r in rels} == {"interface-sounds", "digital-audio", "impact-sounds", "music-jingles"}
    assert "digital-audio/Preview.ogg" not in rels and (V / "digital-audio" / "Preview.ogg").exists()
    assert all(u.startswith("https://github.com/kapishdima/soundcn/blob/7cbfbb3f56e8548b81fb26410bdcea657447d087/assets/kenney_")
               for _, u in allowed)
    assert not list(V.rglob("*wow*")) and not (V / "wow").exists()
    attr = (V / "ATTRIBUTION.md").read_text(encoding="utf-8")
    assert "Blizzard" in attr and "Alınmadı" in attr


def test_unrecorded_or_changed_file_is_not_listed(tmp_path, monkeypatch):
    d = tmp_path / "sfx-cc0"
    (d / "interface-sounds").mkdir(parents=True)
    for n in ("click_001.ogg", "click_002.ogg"):
        shutil.copy(V / "interface-sounds" / n, d / "interface-sounds" / n)
    (d / "interface-sounds" / "kayitsiz.ogg").write_bytes(b"OggS")
    rows = [ln for ln in (V / "ATTRIBUTION.md").read_text(encoding="utf-8").splitlines()
            if "`interface-sounds/click_001.ogg`" in ln or "`interface-sounds/click_002.ogg`" in ln]
    (d / "ATTRIBUTION.md").write_text("| Dosya | Lisans | Kaynak URL | SHA-256 |\n|---|---|---|---|\n" + "\n".join(rows) + "\n", encoding="utf-8")
    with open(d / "interface-sounds" / "click_002.ogg", "ab") as f:  # kayıttan sonra değişmiş
        f.write(b"\0")
    monkeypatch.setattr(SL, "CC0_DIR", d)
    SL.cc0_allowed.cache_clear()
    try:
        assert [p.name for p, _ in SL.cc0_allowed()] == ["click_001.ogg"]
    finally:
        SL.cc0_allowed.cache_clear()


def test_turkish_query_and_whole_word_match():
    res = SL.search("tık", limit=3)["results"]
    assert res and all("click" in r["path"] and r["source"].startswith("vendor:sfx-cc0") and r["source_url"] for r in res)
    assert all("impactGlass" in r["path"] for r in SL.search("darbe cam", limit=5)["results"])
    assert SL.score("sfx/x/cupboard.ogg", SL.query_terms("up")) == 0  # eskiden alt dize eşleşirdi
    assert SL.score("digital-audio/phaserUp3.ogg", SL.query_terms("up")) == 1


def test_vendor_record_complete():
    lock = {e["repo"]: e for e in json.loads((ROOT / "vendor-skills" / "vendor.lock.json").read_text(encoding="utf-8"))}
    e = lock["kapishdima/soundcn"]
    assert e["status"] == "vendored" and "wow" not in e["parts"]
    sh = (ROOT / "scripts" / "setup" / "vendor-skills.sh").read_text(encoding="utf-8")
    assert f'"kapishdima/soundcn|{e["pin"]}|MIT|{e["parts"]}"' in sh
    assert "kapishdima/soundcn" in (ROOT / "vendor-skills" / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    r = DR.Report()
    DR.check_vendor(r)
    assert r.items[0]["ok"], r.items[0]
