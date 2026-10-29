"""Ses kütüphanesi araması (spec 5.9 adım 2): önce profil ses kütüphanesi, sonra CC0 çekirdek (Kenney, 1.7.0), sonra ai-product-video
efekt arşivi.

Vendor arşivlerinden yalnızca kaynağı kayıtlı dosyalar listelenir (OVERRIDES.md lisans kuralı):
- sfx-cc0: ATTRIBUTION.md tablosunda satırı olan, lisansı CC0 yazan ve SHA-256'sı tutan dosya,
- ai-product-video: ATTRIBUTION.md'de Mixkit kaynak URL'si kayıtlı dosya.
Eşleşme sözcük bazlıdır (dosya yolundaki sözcükler, camelCase bölünür); Türkçe sorgu sözcükleri İngilizce etiketlere de açılır
(ör. "tık" → click, "geçiş" → whoosh/transition). 1.7.0 öncesi alt dize eşleşmesi "up" sorgusunu "cup"a da eşliyordu.
Kullanım: sfx_library.py --query whoosh [--profile-dir <data_dir>/profiles/<p>] [--limit 10]
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import PLUGIN_ROOT, emit  # noqa: E402
from admem.util import tr_fold  # noqa: E402

VENDOR_AUDIO = PLUGIN_ROOT / "vendor-skills" / "ai-product-video" / "assets" / "audio"
CC0_DIR = PLUGIN_ROOT / "vendor-skills" / "sfx-cc0"
AUDIO_EXT = (".wav", ".mp3", ".flac", ".ogg")
CC0_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*CC0[^|]*\|\s*(https://\S+)\s*\|\s*`([0-9a-f]{64})`\s*\|", re.M)

# Türkçe sorgu sözcüğü (tr_fold'lu) → dosya adlarındaki İngilizce sözcükler
TR_TAGS = {
    "tik": ["click", "tick", "select"], "tikla": ["click", "select"], "klik": ["click"], "dokunma": ["click", "tap", "select"],
    "gecis": ["whoosh", "woosh", "swoosh", "sweep", "transition"], "hisirti": ["whoosh", "swoosh", "sweep"],
    "vurus": ["impact", "hit", "punch"], "darbe": ["impact", "hit", "punch"], "carpma": ["impact"], "yumruk": ["punch"],
    "onay": ["confirmation", "success", "correct"], "basari": ["confirmation", "success", "jingles"], "hata": ["error", "wrong"],
    "uyari": ["error", "question", "alert"], "bildirim": ["notification", "pop", "bong"], "pop": ["pop", "drop"],
    "cam": ["glass"], "metal": ["metal"], "tahta": ["wood", "plank"], "ahsap": ["wood", "plank"], "zil": ["bell", "bong"],
    "adim": ["footstep"], "ayak": ["footstep"], "kapi": ["open", "close"], "ac": ["open", "maximize"], "kapat": ["close", "minimize"],
    "kaydir": ["scroll", "swipe"], "anahtar": ["switch", "toggle"], "dugme": ["click", "switch", "toggle"],
    "lazer": ["laser"], "dijital": ["digital", "zap", "phaser", "tone"], "guc": ["powerup"], "yukselen": ["riser", "phaserup", "up"],
    "inen": ["down", "phaserdown"], "jingle": ["jingles"], "muzik": ["jingles"], "kapanis": ["jingles"], "fiyat": ["coin", "cash", "jingles"],
    "isilti": ["sparkle", "shimmer", "glass"], "kamera": ["camera", "shutter"], "deklansor": ["shutter"], "kagit": ["paper"],
    "yazi": ["typing", "keyboard", "text"], "klavye": ["keyboard", "typing"], "su": ["water", "fluid"], "kalabalik": ["crowd"],
}


def words(s: str) -> list[str]:
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    return [w for w in re.findall(r"[a-z]+", tr_fold(s)) if len(w) >= 2]


def query_terms(query: str) -> list[set[str]]:
    """Her sorgu sözcüğü için kabul edilen sözcük kümesi (kendisi + Türkçe karşılıkları)."""
    out = []
    for w in words(query):
        out.append({w, *TR_TAGS.get(w, [])})
    return out


def score(path: str, terms: list[set[str]]) -> int:
    ws = set(words(path))
    hit = 0
    for alts in terms:
        if any(a in ws or (len(a) >= 4 and any(x.startswith(a) for x in ws)) for a in alts):
            hit += 1
    return hit


def vendor_allowed() -> list[Path]:
    attr = (VENDOR_AUDIO / "ATTRIBUTION.md").read_text(encoding="utf-8") if (VENDOR_AUDIO / "ATTRIBUTION.md").exists() else ""
    ok = []
    for f in sorted((VENDOR_AUDIO / "sfx").rglob("*")) if (VENDOR_AUDIO / "sfx").exists() else []:
        if not f.is_file():
            continue
        line = next((ln for ln in attr.splitlines() if f"`{f.name}`" in ln), "")
        if "https://assets.mixkit.co" in line:
            ok.append(f)
    return ok


@lru_cache(maxsize=1)
def cc0_allowed() -> tuple[tuple[Path, str], ...]:
    """(dosya, kaynak URL) — yalnızca ATTRIBUTION.md satırı olan, CC0 yazan ve hash'i tutan dosyalar."""
    attr = CC0_DIR / "ATTRIBUTION.md"
    if not attr.exists():
        return ()
    out = []
    for rel, url, sha in CC0_ROW.findall(attr.read_text(encoding="utf-8")):
        f = CC0_DIR / rel
        if f.is_file() and f.suffix.lower() in AUDIO_EXT and hashlib.sha256(f.read_bytes()).hexdigest() == sha:
            out.append((f, url))
    return tuple(out)


def search(query: str, profile_dir: Path | None = None, limit: int = 10) -> dict:
    terms = query_terms(query)
    prof = []
    if profile_dir:
        lib = profile_dir / "audio_library"
        prof = [p for p in lib.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_EXT] if lib.exists() else []
    hits = [{"path": str(p), "source": "profile", "score": score(p.as_posix(), terms)} for p in prof]
    hits += [{"path": str(p), "source": "vendor:sfx-cc0 (Kenney, CC0 1.0)", "category": p.relative_to(CC0_DIR).parts[0], "source_url": url,
              "score": score(p.relative_to(CC0_DIR).as_posix(), terms)} for p, url in cc0_allowed()]
    hits += [{"path": str(p), "source": "vendor:ai-product-video (Mixkit SFX Free License)", "category": p.parent.name,
              "score": score(p.relative_to(VENDOR_AUDIO).as_posix(), terms)} for p in vendor_allowed()]
    rank = {"profile": 0, "vendor:sfx-cc0 (Kenney, CC0 1.0)": 1}
    hits = [h for h in hits if h["score"]]
    hits.sort(key=lambda h: (-h["score"], rank.get(h["source"], 2), h["path"]))
    return {"query": query, "results": hits[:limit],
            "note": "Eşleşme yoksa: tasarım sesi kodla (sfx_synth.py), organik ses ElevenLabs sfx ile (fiyat ve onay)."}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--profile-dir")
    ap.add_argument("--limit", type=int, default=10)
    a = ap.parse_args()
    emit(search(a.query, Path(a.profile_dir) if a.profile_dir else None, a.limit))


if __name__ == "__main__":
    main()
