"""1.8.1: efekt aramasında eksik Türkçe etiketler, ekli sorgular, sıralama; kaynaksız arşiv dosyaları silindi."""
from __future__ import annotations

import sfx_library as SL


def _rel(query, **kw):
    return [r["path"].replace("\\", "/").split("/vendor-skills/")[-1] for r in SL.search(query, **kw)["results"]]


def test_missing_turkish_tags():
    assert "ai-product-video/assets/audio/sfx/crowd/applause-rhythmic-loop.mp3" in _rel("alkış")
    assert _rel("kalp") == ["ai-product-video/assets/audio/sfx/crowd/heartbeat-single.mp3"]
    assert _rel("ışıltı") and all("/sfx/light/" in r for r in _rel("ışıltı"))  # önceden cam kırılma sesleri önce geliyordu


def test_suffixed_query_uses_root():
    assert _rel("geçişi") == _rel("geçiş")
    assert _rel("alkışlar") == _rel("alkış")
    assert SL.tr_tags("ac") == SL.TR_TAGS["ac"] and SL.tr_tags("acil") == []  # 2-3 harfli kök ekli biçimde açılmaz


def test_category_breaks_ties():
    assert all("/sfx/transition/" in r for r in _rel("geçiş", limit=5))
    assert all("interface-sounds/click" in r for r in _rel("tık", limit=3))  # CC0 önceliği korunur


def test_profile_scored_relative(tmp_path):
    prof = tmp_path / "zeytinyagi"
    lib = prof / "audio_library"
    lib.mkdir(parents=True)
    (lib / "kagit-hisirti.wav").write_bytes(b"")
    assert SL.search("zeytinyagi", profile_dir=prof)["results"] == []  # mutlak yoldaki profil klasörü adı eşleşmez
    assert SL.search("kağıt", profile_dir=prof)["results"][0]["source"] == "profile"


def test_unsourced_archive_files_removed():
    files = {p.name for p in (SL.VENDOR_AUDIO / "sfx").rglob("*.mp3")}
    assert files == {p.name for p in SL.vendor_allowed()}
    for gone in ("sparkle.mp3", "riser-cine.mp3", "keyboard.mp3", "whoosh-big.mp3", "pop.mp3"):
        assert gone not in files
