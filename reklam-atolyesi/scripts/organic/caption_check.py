"""Organik açıklama denetimi (2.2.0): akışta görünen baş kısım, etiket sınırı, tek yönlendirme, somut ilk cümle.

Instagram akışta açıklamanın başını gösterip devamını "devamı" altına saklar. Organik açıklama için yayımlanmış bir karakter sayısı yok;
görünen kısım YEREL varsayımla 125 görünür karakter alınır (Meta'nın reklam birincil metni önerisiyle aynı sayı, checks.py COPY_OFFICIAL).
Etiket sınırı 5 (profile_check.HASHTAG_MAX; ikincil kaynak, ref-legal-tr-meta). Sayım Türkçe harfleri ve bileşik emojiyi doğru sayar
(checks.visible_len). Sonuç uyarıdır; taslak sohbette düzeltilir, kaydedilmez.

Kullanım: caption_check.py --text taslak.txt | --json taslaklar.json   (json: ["…", "…"] ya da [{"id": …, "caption": …}])
          [--keywords "el yapımı mum,doğum günü hediyesi"] [--out sonuc.json]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "qc"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import emit, read_json, write_json  # noqa: E402
from checks import COPY_OFFICIAL, graphemes, visible_len  # noqa: E402
from profile_check import HASHTAG_MAX, HASHTAG_RX  # noqa: E402

VISIBLE = COPY_OFFICIAL["primary"]  # yerel varsayım (organik için resmi sayı yok)
CAPTION_MAX = 2200                   # Instagram açıklama üst sınırı (yaygın bilgi; teyit edilmedi)
CONCRETE_RX = re.compile(r"\d|%|₺|\bTL\b", re.I)
# Yönlendirme kanalları: "sipariş", "bilgi al" gibi fiiller kanal değildir; tek yönlendirme = tek kanal (yerel kural, organic adım 3).
CTA_CHANNELS = {"bağlantı": r"link|bağlantı|bio\b|profil", "dm": r"\bdm\b|mesaj", "whatsapp": r"whatsapp", "randevu": r"randevu",
                "telefon": r"\bara\b|arayın|telefon", "yorum": r"yorum(a|lara)? yaz"}
INVISIBLE_RX = re.compile("[​‌⁠­﻿᠎⁢⁣⁤]")


def check_caption(text: str, keywords: list[str] | None = None) -> dict:
    raw = text or ""
    invisible = len(INVISIBLE_RX.findall(raw))
    t = INVISIBLE_RX.sub("", raw).strip()
    g = graphemes(t)
    shown = "".join(g[:VISIBLE])
    first_line = t.split("\n", 1)[0]
    tags = HASHTAG_RX.findall(t)
    ctas = {k for k, rx in CTA_CHANNELS.items() if re.search(rx, t, re.I)}
    kw = [k.strip() for k in (keywords or []) if k.strip()]
    missing = [k for k in kw if k.lower() not in t.lower()]
    items = [
        ("length", visible_len(t) <= CAPTION_MAX, f"{visible_len(t)} / {CAPTION_MAX} karakter"),
        ("first_line", visible_len(first_line) <= VISIBLE,
         f"ilk satır {visible_len(first_line)} karakter" + ("" if visible_len(first_line) <= VISIBLE else f"; {VISIBLE}'te cümle ortasında kesilir")),
        ("concrete_in_view", bool(CONCRETE_RX.search(shown)), "görünen kısımda sayı/fiyat/süre " + ("var" if CONCRETE_RX.search(shown) else "yok")),
        ("hashtags", len(tags) <= HASHTAG_MAX, f"{len(tags)} etiket (sınır {HASHTAG_MAX})"),
        ("one_cta", len(ctas) == 1,
         f"{len(ctas)} yönlendirme kanalı: {', '.join(sorted(ctas)) or '-'}"),
        ("invisible_chars", invisible == 0, f"{invisible} görünmez karakter (temizlendi)" if invisible else "görünmez karakter yok"),
    ]
    if kw:
        items.append(("search_terms", not missing, f"{len(kw) - len(missing)}/{len(kw)} arama sözcüğü" +
                      (f"; eksik: {', '.join(missing)}" if missing else "")))
    return {"visible": shown, "cut": len(g) > VISIBLE, "clean_text": t,
            "checks": [{"id": i, "ok": ok, "detail": d} for i, ok, d in items],
            "warnings": sum(1 for _, ok, _ in items if not ok)}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--text")
    src.add_argument("--json")
    ap.add_argument("--keywords", default="")
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.text:
        drafts = [{"id": "1", "caption": Path(a.text).read_text(encoding="utf-8")}]
    else:
        drafts = [d if isinstance(d, dict) else {"id": str(i + 1), "caption": d} for i, d in enumerate(read_json(a.json))]
    kw = a.keywords.split(",") if a.keywords else []
    res = [{"id": d.get("id"), **check_caption(str(d.get("caption") or ""), kw)} for d in drafts]
    if a.out:
        write_json(a.out, res)
    emit({"drafts": len(res), "warnings": sum(r["warnings"] for r in res),
          "results": [{"id": r["id"], "visible": r["visible"], "cut": r["cut"],
                       "warn": [c["detail"] for c in r["checks"] if not c["ok"]]} for r in res]})


if __name__ == "__main__":
    main()
