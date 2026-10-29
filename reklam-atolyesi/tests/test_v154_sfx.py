"""1.5.4: ses kütüphanesi araması — Türkçe etiketler, kelime eşleşmesi, kaynağı kayıtlı dosyalar."""
from __future__ import annotations

import sfx_library as SL


def _names(query, **kw):
    return [r["path"].replace("\\", "/").split("/sfx/")[-1] for r in SL.search(query, **kw)["results"]]


def test_turkish_tags_find_archive():
    assert _names("kağıt") and all(n.startswith("paper/") for n in _names("kağıt"))
    assert _names("kamera") and all(n.startswith("camera/") for n in _names("kamera"))
    assert "crowd/applause-rhythmic-loop.mp3" in _names("alkış")
    assert _names("geçişi")[0].startswith("transition/")  # ek alan sorgu da eşleşir; kategori eşleşmesi öne geçer
    assert _names("ışıltı") and all(n.startswith("light/") for n in _names("ışıltı"))


def test_short_words_match_whole_words_only():
    assert all(n.startswith("glass/") for n in _names("cam"))  # cam bardak, camera değil
    assert "ui/ui-success-soft.mp3" not in _names("su dökme")  # "su" success'in içinde değil
    assert all(n.startswith("fluid/") for n in _names("su"))


def test_english_queries_unchanged():
    assert all("whoosh" in n for n in _names("whoosh"))
    assert _names("paper", limit=50) == _names("kağıt", limit=50)


def test_unsourced_files_absent():
    allowed = {p.name for p in SL.vendor_allowed()}
    files = {p.name for p in (SL.VENDOR_AUDIO / "sfx").rglob("*.mp3")}
    assert files == allowed  # arşivde yalnızca ATTRIBUTION.md'de URL'si kayıtlı dosyalar
    for gone in ("sparkle.mp3", "riser-cine.mp3", "keyboard.mp3", "whoosh-big.mp3", "pop.mp3"):
        assert gone not in files
    assert _names("yükselen") == []  # kayıtlı riser yok → sentez (not)
    assert "sfx_synth.py" in SL.search("yükselen")["note"]


def test_profile_library_first(tmp_path):
    lib = tmp_path / "audio_library"
    lib.mkdir()
    (lib / "kagit-hisirti.wav").write_bytes(b"")
    res = SL.search("kağıt", profile_dir=tmp_path)["results"]
    assert res[0]["source"] == "profile"
