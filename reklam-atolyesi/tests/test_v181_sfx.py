"""1.8.1: efekt aramasında eksik Türkçe etiketler, ekli sorgular, sıralama; kaynaksız arşiv dosyaları silindi."""
from __future__ import annotations

import sfx_library as SL


def _rel(query, **kw):
    return [r["path"].replace("\\", "/").split("/vendor-skills/")[-1] for r in SL.search(query, **kw)["results"]]


def test_missing_turkish_tags():
    assert SL.tr_tags("alkis") == ["applause", "clap"] and SL.tr_tags("kalp") == ["heart", "heartbeat"]
    # 2.10.14: Mixkit arşivi paketten çıktı; alkış ve kalp atışı paketteki bankalarda yok (profil kütüphanesi ya da ElevenLabs)
    assert not any("ai-product-video" in r for r in _rel("alkış") + _rel("kalp"))
    assert _rel("ışıltı") and all("shimmer/" in r for r in _rel("ışıltı"))


def test_suffixed_query_uses_root():
    assert _rel("geçişi") == _rel("geçiş")
    assert _rel("alkışlar") == _rel("alkış")
    assert SL.tr_tags("ac") == SL.TR_TAGS["ac"] and SL.tr_tags("acil") == []  # 2-3 harfli kök ekli biçimde açılmaz


def test_category_breaks_ties():
    # 2.6.0: Earshot whoosh aileleri "geçiş" ailesidir
    assert all("whoosh" in r.split("/")[-2] for r in _rel("geçiş", limit=5))
    assert all("interface-sounds/click" in r for r in _rel("tık", limit=3))  # CC0 önceliği korunur


def test_profile_scored_relative(tmp_path):
    prof = tmp_path / "zeytinyagi"
    lib = prof / "audio_library"
    lib.mkdir(parents=True)
    (lib / "kagit-hisirti.wav").write_bytes(b"")
    assert SL.search("zeytinyagi", profile_dir=prof)["results"] == []  # mutlak yoldaki profil klasörü adı eşleşmez
    assert SL.search("kağıt", profile_dir=prof)["results"][0]["source"] == "profile"


def test_unsourced_archive_files_removed():
    # 2.10.14 (B18): Mixkit arşivi bütünüyle çıkarıldı; paketteki ses dosyaları yalnız CC0 ve Earshot bankalarındadır
    from conftest import ROOT
    assert not (ROOT / "vendor-skills" / "ai-product-video" / "assets").exists()
    shipped = [p for p in (ROOT / "vendor-skills").rglob("*") if p.suffix.lower() in SL.AUDIO_EXT]
    assert shipped and all(p.relative_to(ROOT / "vendor-skills").parts[0] in ("sfx-cc0", "sfx-earshot") for p in shipped)
    assert not any("mixkit" in r["source"].lower() for q in ("geçiş", "ışıltı", "tık", "alkış") for r in SL.search(q, limit=50)["results"])
