"""Ses kütüphanesi araması (spec 5.9 adım 2): önce profil ses kütüphanesi, sonra ai-product-video efekt arşivi.

Vendor arşivinden yalnızca ATTRIBUTION.md'de kaynak URL'si kayıtlı dosyalar listelenir (OVERRIDES.md lisans kuralı).
Arama kategori + dosya adı kelimeleriyle yapılır (alt dize değil; 1.5.4). Arşivdeki adlar İngilizcedir: Türkçe etiketler TR_ALIASES ile
karşılığına çevrilir ("kağıt" → paper, "cam" → glass; "cam" camera'yı bulmaz).
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

# Türkçe etiket (aksansız) → arşivdeki kategori/dosya adı kelimeleri. Sorgu kelimesi bu anahtarlardan biriyle başlıyorsa da eşleşir
# (4+ harfli anahtarlarda: "geçişi" → gecis). Tasarım sesleri (riser, whoosh, shimmer…) için eşleşme yoksa sfx_synth.py.
TR_ALIASES: dict[str, tuple[str, ...]] = {
    "gecis": ("transition", "whoosh", "woosh", "swoosh", "sweep"), "savurma": ("whoosh", "swoosh", "woosh"),
    "vurus": ("impact", "hit"), "darbe": ("impact", "hit"), "carpma": ("impact", "hit"), "yukselen": ("riser", "rise"),
    "yukselis": ("riser", "rise"), "isilti": ("sparkle", "shimmer"), "parilti": ("sparkle", "shimmer"), "isik": ("light",),
    "kamera": ("camera",), "deklansor": ("shutter",), "objektif": ("lens",), "yakinlastirma": ("zoom",),
    "tik": ("click", "tick"), "tiklama": ("click",), "dokunma": ("tap", "touch"), "dugme": ("switch", "click"),
    "klavye": ("keyboard", "typewriter"), "daktilo": ("typewriter",), "yazma": ("write", "pen", "pencil"), "yazi": ("write", "typewriter"),
    "kalem": ("pen", "pencil", "marker"), "tebesir": ("chalk",), "tahta": ("blackboard",),
    "kagit": ("paper",), "sayfa": ("page",), "kitap": ("book",), "makas": ("scissors",), "zimba": ("staple",), "burusturma": ("crumple",),
    "cam": ("glass",), "kirilma": ("break",), "su": ("water",), "sivi": ("liquid", "fluid"), "damla": ("drop",), "sicrama": ("splash",),
    "baloncuk": ("bubble",), "kum": ("sand",), "alkis": ("applause", "clap"), "kalp": ("heart", "heartbeat"),
    "kalabalik": ("crowd", "applause"), "saat": ("clock",), "sayac": ("counter", "countdown"), "sayim": ("countdown",),
    "bildirim": ("notify", "message", "chime"), "mesaj": ("message",), "onay": ("confirm", "success"), "basari": ("success",),
    "secim": ("select", "option"), "patlama": ("pop", "poof"), "zil": ("bell", "chime"), "hata": ("glitch",), "parazit": ("static", "glitch"),
    "bozulma": ("glitch",), "dijital": ("digital",), "veri": ("data",), "elektrik": ("electric",), "kilit": ("lock",), "kapi": ("door",),
    "disli": ("gear",), "makine": ("machine", "mech"), "kaset": ("cassette",), "plak": ("vinyl",), "bant": ("tape",),
    "projektor": ("projector",), "sarma": ("rewind",), "uzay": ("space", "scifi"), "bilimkurgu": ("scifi",),
    "futuristik": ("futuristic",), "ruzgar": ("wind",), "hava": ("air",), "kanat": ("wing",), "hizli": ("fast", "quick"),
    "yavas": ("slow",), "kisa": ("short", "quick"), "yumusak": ("soft",), "sert": ("hard",), "buyuk": ("big",), "derin": ("deep",),
    "kucuk": ("small",), "sinematik": ("cine", "movie", "epic"),
}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", tr_fold(text)))


def _terms(word: str) -> set[str]:
    """Sorgu kelimesinin aranacak karşılıkları: kendisi + Türkçe eş anlamlıları."""
    out = {word}
    for key, vals in TR_ALIASES.items():
        if word == key or (len(key) >= 4 and word.startswith(key)):
            out.update(vals)
    return out


def _hit(term: str, toks: set[str]) -> bool:
    # Kelime eşleşmesi; 4+ harfli terim kelime başını da tutar (sweep → sweeping). Kısa terimler yalnızca tam kelime ("su" ≠ success).
    return term in toks or (len(term) >= 4 and any(t.startswith(term) for t in toks))


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
    q = [_terms(w) for w in re.findall(r"[a-z0-9]+", tr_fold(query)) if len(w) >= 2]

    def score(p: Path, root: Path) -> tuple[int, int]:
        # (eşleşen sorgu kelimesi, eşleşen terim sayısı): "geçiş" için transition/whoosh-fast, data/sweep-digital'in önüne geçer.
        toks = _tokens(p.relative_to(root).with_suffix("").as_posix())
        per = [sum(1 for t in terms if _hit(t, toks)) for terms in q]
        return sum(1 for n in per if n), sum(per)
    prof, lib = [], None
    if profile_dir:
        lib = profile_dir / "audio_library"
        prof = [p for p in lib.rglob("*") if p.is_file() and p.suffix.lower() in (".wav", ".mp3", ".flac")] if lib.exists() else []
    hits = [{"path": str(p), "source": "profile", "score": s[0], "_w": s[1]} for p in prof if (s := score(p, lib))[0]]
    hits += [{"path": str(p), "source": "vendor:ai-product-video (Mixkit SFX Free License)", "category": p.parent.name, "score": s[0],
              "_w": s[1]} for p in vendor_allowed() if (s := score(p, VENDOR_AUDIO / "sfx"))[0]]
    hits.sort(key=lambda h: (-h["score"], -h["_w"], h["source"] != "profile"))
    for h in hits:
        del h["_w"]
    return {"query": query, "results": hits[:limit],
            "note": "Eşleşme yoksa: tasarım sesi (whoosh, riser, shimmer, impact, pop) kodla (sfx_synth.py); organik ses (kağıt, cam, su…) "
                    "önce İngilizce karşılığıyla yeniden aranır, yine yoksa ElevenLabs sfx ile (fiyat ve onay)."}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--profile-dir")
    ap.add_argument("--limit", type=int, default=10)
    a = ap.parse_args()
    emit(search(a.query, Path(a.profile_dir) if a.profile_dir else None, a.limit))


if __name__ == "__main__":
    main()
