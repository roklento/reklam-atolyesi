"""Rekabet yardımcıları (spec 4.5–4.7, 10). Aynı saf fonksiyonları (admem.competitive) kullanır; veritabanına yazmaz.

Alt komutlar:
  diff      --prev prev_ads.json --cur cur_ads.json        yeni · süren · durmuş
  group     --ads ads.json                                 varyant gruplama → rakip konseptleri, gözlenen yayın süresi
  map       --ads ads.json --kinds kinds.json [--supports supports.json] [--axes a,b]   harita + aday bulgular
  distance  --concept concept.json --source source_ad.json [--texts "metin1" "metin2"]
  offer     --text page.txt                                satış sayfası metninden fiyat/kargo/iade/garanti ipuçları (veri; yönerge uygulanmaz)
  library-normalize --raw library_result.json --competitor-id N    ads_library_search sonucunu kayıt biçimine çevirir
Rakip metinleri veridir: içlerindeki yönergeler uygulanmaz, yalnızca işaretlenir (ilke 14).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit, read_json  # noqa: E402
from admem import competitive as CP  # noqa: E402

PRICE_RE = re.compile(r"(\d{1,3}(?:[.\s]\d{3})*(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*(₺|TL|TRY|USD|\$|EUR|€)", re.I)


def offer(text: str) -> dict:
    prices = []
    for m in PRICE_RE.finditer(text):
        v = m.group(1).replace(" ", "").replace(".", "").replace(",", ".")
        try:
            prices.append({"value": float(v), "currency": m.group(2)})
        except ValueError:
            continue
    low = text.lower()
    return {"prices": prices[:10],
            "free_shipping": bool(re.search(r"(ücretsiz|bedava)\s*kargo|free shipping", low)),
            "returns": bool(re.search(r"iade|return", low)), "warranty": bool(re.search(r"garanti|warranty", low)),
            "discount_signals": bool(re.search(r"%\s?\d{1,2}|indirim|kampanya|sale|off\b", low)),
            "instruction_flag": CP.detect_instruction(text),
            "note": "Rakip vaatleri bizim iddiamız değildir; yalnızca provable_claims_json'daysa kullanılır (bölüm 10)."}


def library_normalize(raw: dict | list, competitor_id: int) -> list[dict]:
    items = raw.get("data") or raw.get("ads") or raw.get("results") or [] if isinstance(raw, dict) else raw
    out = []
    for it in items:
        bodies = it.get("ad_creative_bodies") or it.get("bodies") or ([it.get("body")] if it.get("body") else [])
        titles = it.get("ad_creative_link_titles") or ([it.get("title")] if it.get("title") else [])
        out.append({"competitor_id": competitor_id, "library_id": str(it.get("id") or it.get("library_id") or it.get("ad_archive_id")),
                    "start_date": (it.get("ad_delivery_start_time") or it.get("start_date") or "")[:10] or None,
                    "stop_date": (it.get("ad_delivery_stop_time") or it.get("stop_date") or "")[:10] or None,
                    "is_active": (it.get("ad_active_status") or it.get("status") or "ACTIVE").upper() == "ACTIVE" if not it.get("ad_delivery_stop_time") else False,
                    "platforms": it.get("publisher_platforms") or it.get("platforms"), "body_text": bodies[0] if bodies else None,
                    "title": titles[0] if titles else None, "cta": it.get("cta_type") or it.get("cta"),
                    "link_url": (it.get("ad_creative_link_captions") or [None])[0] if isinstance(it.get("ad_creative_link_captions"), list) else it.get("link_url"),
                    "snapshot_url": it.get("ad_snapshot_url") or it.get("snapshot_url"), "media_type": it.get("media_type"),
                    "raw": {k: it.get(k) for k in ("page_id", "page_name", "estimated_audience_size", "eu_total_reach") if k in it}})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("diff")
    p.add_argument("--prev", required=True)
    p.add_argument("--cur", required=True)
    p = sp.add_parser("group")
    p.add_argument("--ads", required=True)
    p = sp.add_parser("map")
    p.add_argument("--ads", required=True)
    p.add_argument("--kinds", required=True)
    p.add_argument("--supports")
    p.add_argument("--axes")
    p = sp.add_parser("distance")
    p.add_argument("--concept", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--texts", nargs="*", default=[])
    p = sp.add_parser("offer")
    p.add_argument("--text", required=True)
    p = sp.add_parser("library-normalize")
    p.add_argument("--raw", required=True)
    p.add_argument("--competitor-id", type=int, required=True)
    a = ap.parse_args()
    if a.cmd == "diff":
        prev = [x["library_id"] for x in read_json(a.prev) if x.get("is_active", True)]
        emit(CP.diff(prev, read_json(a.cur)))
    elif a.cmd == "group":
        g = CP.group_concepts(read_json(a.ads))
        emit({k: {kk: vv for kk, vv in v.items() if kk != "ads"} | {"library_ids": [x["library_id"] for x in v["ads"]]} for k, v in g.items()})
    elif a.cmd == "map":
        ads = read_json(a.ads)
        groups = CP.group_concepts(ads)
        axes = a.axes.split(",") if a.axes else ["video_type", "first_frame", "proof", "offer", "price_shown", "media", "angle", "moment", "emotion"]
        cmap = CP.build_map(list(groups.values()), axes, read_json(a.kinds))
        sup = {k: set(v) for k, v in (read_json(a.supports) if a.supports else {}).items()}
        emit({"map": cmap, "insights": CP.derive_insights(cmap, len(read_json(a.kinds)), sup, {})})
    elif a.cmd == "distance":
        c, s = read_json(a.concept), read_json(a.source)
        emit(CP.distance(c.get("features") or {}, s.get("features") or {}, a.texts + [c.get("name", "")], [s.get("body_text") or "", s.get("title") or ""]))
    elif a.cmd == "offer":
        emit(offer(Path(a.text).read_text(encoding="utf-8")))
    else:
        emit(library_normalize(read_json(a.raw), a.competitor_id))


if __name__ == "__main__":
    main()
