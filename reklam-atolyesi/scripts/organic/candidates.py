"""Organik paylaşım adayları (1.5.0): reklam için çekilmiş ama kullanılmamış iyi klipler, kazanan reklamlar ve konuşma dökümleri.

Kaynaklar (yalnızca yerel kayıtlar): asset_query(scope='profile', kind='footage') sonucu (puan, en iyi aralıklar, etiketler, used_in),
isteğe bağlı koçluk analizi (decisions: 'büyüt'/'tut' konseptleri) ve konuşma dökümleri (analysis/speech/*.transcript.json).
Paylaşım yapılmaz: aday listesi, önerilen biçim ve haftalık takvim üretilir; metin taslaklarını skill yazar, kullanıcı paylaşır.
Kişili klipte izin (consent) yoksa aday olmaz.

Kullanım: candidates.py --assets assets.json [--analysis analysis.json] [--speech-dir analysis/speech] [--per-week 3] [--start 2026-10-22]
          --out organik.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit, read_json, write_json  # noqa: E402

MIN_SCORE = 0.6     # yerel: organik için de görüntü kalitesi eşiği
MIN_RANGE_S = 3.0   # en kısa kullanılabilir aralık
ANGLE_BY_TAG = {"process": "süreç / nasıl yapılıyor", "detail": "yakın çekim doku", "hands": "el işçiliği", "packaging": "paketleme",
                "unboxing": "kutu açılışı", "use": "kullanım anı", "behind": "kamera arkası", "person": "kişi / kurucu"}


def _j(v, default):
    if v is None:
        return default
    if isinstance(v, str):
        import json
        try:
            return json.loads(v)
        except ValueError:
            return default
    return v


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def build(assets: list[dict], analysis: dict | None = None, transcripts: list[dict] | None = None, per_week: int = 3,
          start: dt.date | None = None, no_consent_assets: set | None = None) -> dict:
    """no_consent_assets: consent_query(...).assets_without_valid_consent kimlikleri (geri çekilmiş izin dahil)."""
    bad_consent = {int(x) for x in (no_consent_assets or set()) if str(x).isdigit()}
    cands, skipped = [], {"used_in_ads": 0, "organic_posted": 0, "low_score": 0, "no_consent": 0, "short": 0}
    for a in assets:
        if a.get("kind") not in (None, "footage"):
            continue
        score = (_j(a.get("score_json"), {}) or {}).get("overall", 0) or 0
        used = _j(a.get("used_in_json"), []) or []
        people = _j(a.get("people_json"), []) or []
        tags = [t for t in (a.get("tags") or "").split(",") if t]
        if used:
            organic = all(isinstance(u, dict) and u.get("role") == "organic" for u in used)
            skipped["organic_posted" if organic else "used_in_ads"] += 1
            continue
        if score < MIN_SCORE:
            skipped["low_score"] += 1
            continue
        if a.get("id") in bad_consent or "izinsiz" in tags or \
                any((p.get("kind") in ("person", "face") or p.get("speaking")) and not p.get("consent_id") for p in people):
            skipped["no_consent"] += 1
            continue
        ranges = [r for r in (_j(a.get("best_ranges_json"), []) or []) if isinstance(r, dict) and _f(r.get("out_s")) - _f(r.get("in_s")) >= MIN_RANGE_S]
        if not ranges:
            skipped["short"] += 1
            continue
        angle = next((ANGLE_BY_TAG[t] for t in tags if t in ANGLE_BY_TAG), "ürün anı")
        cands.append({"kind": "unused_clip", "asset_id": a.get("id"), "path": a.get("path"), "ranges": ranges[:3], "score": round(score, 2),
                      "angle": angle, "format": "Reels 9:16, 7–15 sn", "why": "reklam için çekildi, reklamda kullanılmadı"})
    for d in (analysis or {}).get("decisions", []) or []:
        if d.get("decision") in ("büyüt", "tut") and "kanıt" in (d.get("label") or ""):
            cands.append({"kind": "winning_ad", "concept": d["concept"], "format": "aynı kreatif (gönderi olarak) ya da sessiz/altyazılı kurgu",
                          "why": f"reklamda {d['decision']} hükmü aldı; organikte de aynı mesaj", "note": "reklam gönderisi zaten profildeyse yeniden "
                          "paylaşılmaz; ölçekleme için gönderi kimliğiyle taşıma ayrı iştir"})
    for t in transcripts or []:
        words = t.get("words") or []
        if len(words) >= 12:
            cands.append({"kind": "talking_clip", "source": t.get("in"), "format": "konuşmalı kısa video (kurgu: asr_local.py cuts)",
                          "words": len(words), "why": "kameraya konuşma çekimi var: ipucu / soru-cevap / kurucu anlatımı"})
    order = {"winning_ad": 0, "talking_clip": 1, "unused_clip": 2}
    cands.sort(key=lambda c: (order[c["kind"]], -(c.get("score") or 0)))
    start = start or dt.date.today()
    per_week = max(1, min(int(per_week), 7))
    gap = 7 / per_week
    plan = [{"date": (start + dt.timedelta(days=round(i * gap))).isoformat(), "candidate": i} for i in range(min(len(cands), per_week * 2))]
    return {"candidates": cands, "skipped": skipped, "calendar": plan, "per_week": per_week,
            "note": "Paylaşımı kullanıcı yapar. Organik performans yalnızca beğeni/yorum sayısıyla izlenir (erişim bu bağlantıda yok); "
                    "reklam kararlarına girmez."}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets", required=True)
    ap.add_argument("--analysis")
    ap.add_argument("--speech-dir")
    ap.add_argument("--per-week", type=int, default=3)
    ap.add_argument("--consent", help="consent_query sonucu (assets_without_valid_consent): izni geçersiz kişili klipler aday olmaz")
    ap.add_argument("--start")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    assets = read_json(a.assets)
    if isinstance(assets, dict):
        assets = assets.get("assets") or []
    trs = [read_json(p) for p in sorted(Path(a.speech_dir).glob("*.transcript.json"))] if a.speech_dir and Path(a.speech_dir).is_dir() else []
    bad = {str(x.get("asset_id")) for x in (read_json(a.consent).get("assets_without_valid_consent") or [])} if a.consent else set()
    res = build(assets, read_json(a.analysis) if a.analysis else None, trs, a.per_week,
                dt.date.fromisoformat(a.start) if a.start else None, bad)
    write_json(a.out, res)
    emit({"out": a.out, "candidates": len(res["candidates"]), "skipped": res["skipped"]})


if __name__ == "__main__":
    main()
