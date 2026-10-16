"""Adlandırma kuralı (spec 5.18).

Dosya adı: <MARKA>_<KAMPANYA>_<KONSEPT>_<MEDYA>_<SÜRE>_<HOOK>_<VO>_<KAYNAK>_<TUR>_<REV>_<FORMAT>[_k<KART>]
creative_key / Meta reklam adı: aynı adın FORMAT ve kart numarası çıkarılmış hali.
"""
from __future__ import annotations

import re

MEDIA = ("video", "static", "carousel")
SOURCES = ("real", "ai")
FORMATS = {"9x16": "916", "4x5": "45", "1x1": "11"}
FORMAT_CODES = {v: k for k, v in FORMATS.items()}
_TOKEN = re.compile(r"^[A-Za-z0-9-]+$")
_KEY_RE = re.compile(
    r"^(?P<brand>[A-Za-z0-9-]+)_(?P<campaign>[A-Za-z0-9-]+)_(?P<concept>[A-Za-z0-9-]+)_(?P<media>video|static|carousel)_"
    r"(?P<duration>\d+|na)_(?P<hook>[A-Za-z0-9-]+)_(?P<vo>vo|novo)_(?P<source>real|ai)_(?P<cycle>c\d+)_(?P<rev>r\d+)$")


def _tok(name: str, v: str) -> str:
    v = str(v)
    if not _TOKEN.match(v):
        raise ValueError(f"{name} yalnızca harf/rakam/tire içerebilir: {v!r}")
    return v


def build_key(brand: str, campaign: str, concept: str, media: str, duration_s: float | None, hook: str,
              has_vo: bool, source: str, cycle: int, rev: int) -> str:
    if media not in MEDIA:
        raise ValueError(f"medya: {MEDIA}")
    if source not in SOURCES:
        raise ValueError(f"kaynak: {SOURCES}")
    dur = "na" if media in ("static", "carousel") or duration_s is None else str(int(round(float(duration_s))))
    return "_".join([_tok("marka", brand), _tok("kampanya", campaign), _tok("konsept", concept), media, dur,
                     _tok("hook", hook), "vo" if has_vo else "novo", source, f"c{int(cycle)}", f"r{int(rev)}"])


def build_file_name(creative_key: str, fmt: str, card: int | None = None, ext: str = "mp4") -> str:
    if fmt not in FORMATS:
        raise ValueError(f"format: {list(FORMATS)}")
    parsed = parse_key(creative_key)
    if parsed is None:
        raise ValueError(f"geçersiz creative_key: {creative_key}")
    name = f"{creative_key}_{FORMATS[fmt]}"
    if parsed["media"] == "carousel":
        if not card:
            raise ValueError("carousel dosyası kart numarası ister")
        name += f"_k{int(card)}"
    elif card:
        raise ValueError("kart numarası yalnızca carousel'de")
    return f"{name}.{ext}"


def parse_key(key: str) -> dict | None:
    m = _KEY_RE.match(key or "")
    return m.groupdict() if m else None


def parse_file_name(name: str) -> dict | None:
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", name or "")
    m = re.match(r"^(?P<key>.+)_(?P<fmt>916|45|11)(?:_k(?P<card>\d+))?$", stem)
    if not m:
        return None
    k = parse_key(m.group("key"))
    if not k:
        return None
    return {**k, "creative_key": m.group("key"), "format": FORMAT_CODES[m.group("fmt")],
            "card_index": int(m.group("card") or 0)}


def match_ad_name(ad_name: str) -> str | None:
    """Meta reklam adı → creative_key (adlandırma kuralına uyuyorsa). Format eki taşıyan ayrı reklam adları da çözülür."""
    if not ad_name:
        return None
    name = ad_name.strip()
    if parse_key(name):
        return name
    f = parse_file_name(name)
    return f["creative_key"] if f else None
