"""Ses kütüphanesi araması (spec 5.9 adım 2): önce profil ses kütüphanesi, sonra ai-product-video efekt arşivi.

Vendor arşivinden yalnızca ATTRIBUTION.md'de kaynak URL'si kayıtlı dosyalar listelenir (OVERRIDES.md lisans kuralı).
Kullanım: sfx_library.py --query whoosh [--profile-dir <data_dir>/profiles/<p>] [--limit 10]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import PLUGIN_ROOT, emit  # noqa: E402
from admem.util import tr_fold  # noqa: E402

VENDOR_AUDIO = PLUGIN_ROOT / "vendor-skills" / "ai-product-video" / "assets" / "audio"


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


def search(query: str, profile_dir: Path | None = None, limit: int = 10) -> dict:
    q = [w for w in re.findall(r"[a-z0-9]+", tr_fold(query)) if len(w) >= 2]
    def score(p: Path) -> int:
        name = tr_fold(p.as_posix())
        return sum(1 for w in q if w in name)
    prof = []
    if profile_dir:
        lib = profile_dir / "audio_library"
        prof = [p for p in lib.rglob("*") if p.is_file() and p.suffix.lower() in (".wav", ".mp3", ".flac")] if lib.exists() else []
    hits = [{"path": str(p), "source": "profile", "score": score(p)} for p in prof if score(p)]
    hits += [{"path": str(p), "source": "vendor:ai-product-video (Mixkit SFX Free License)", "category": p.parent.name, "score": score(p)}
             for p in vendor_allowed() if score(p)]
    hits.sort(key=lambda h: (-h["score"], h["source"] != "profile"))
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
