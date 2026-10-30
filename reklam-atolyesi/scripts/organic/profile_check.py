"""Instagram profil kontrolü (1.5.0; 2.2.0: etiket sınırı ve kendi ortancasına göre kat): reklamı gören kişi profile baktığında güven buluyor mu.

Girdi yalnızca salt okuma araçlarının döndürdüğü alanlardır (ads_get_ig_accounts: username, profile_picture_url; ads_get_ig_media:
caption, like_count, comments_count, media_type, media_product_type, permalink, timestamp — 21.10.2026'da bağlı hesapta okundu).
Biyografi, profildeki bağlantı, takipçi sayısı, öne çıkanlar ve erişim bu araçlarda YOK: bunlar kullanıcıya kontrol listesi olarak sorulur,
tahmin edilmez. Eşikler YEREL kurallardır (Meta/Instagram kuralı değil).

Kullanım: profile_check.py --media media.json [--account account.json] [--cta-url https://…] [--followers N] [--now 2026-10-21]
          --out profil.json   (media.json: araç sonucundaki ig_media listesi; sayfalar birleştirilmiş olabilir)
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit, read_json, write_json  # noqa: E402

STALE_DAYS = 14          # son paylaşım bundan eskiyse profil durgun görünür (yerel)
GRID_MIN = 9             # ızgarada ilk bakışta görülen paylaşım sayısı (3 × 3; yerel)
REELS_SHARE_MIN = 0.3    # son paylaşımlarda video/Reels payı (yerel)
HASHTAG_MAX = 5          # Instagram'ın paylaşım/Reels başına etiket sınırı (Aralık 2025; ikincil kaynak, yardım merkezinde teyit edilmedi)
OUTLIER_WINDOW = 30      # "kaç kat" ölçüsünde taban: son 30 paylaşımın ortancası (yerel)
OUTLIER_MIN_POSTS = 6    # bundan az paylaşımda kat hesaplanmaz; desen için ~30 gerekir (yerel)
OUTLIER_TOP = 5          # en iyi/en zayıf kaç paylaşım gösterilir (yerel)
HASHTAG_RX = re.compile(r"#\w+")
CTA_RX = re.compile(r"(sipariş|satın al|dm|mesaj|link|bağlantı|profil|bio|whatsapp|randevu|ara\b|bilgi al|teklif)", re.I)


def _ts(s) -> dt.datetime:
    """ISO (saat dilimli/dilimsiz), yalnızca tarih ya da Unix zamanı → UTC'li zaman; dilimsiz zaman UTC sayılır."""
    if isinstance(s, (int, float)) or re.fullmatch(r"\d{9,13}", str(s)):
        v = float(s)
        if v > 1e11:  # milisaniye
            v /= 1000.0
        try:
            return dt.datetime.fromtimestamp(v, tz=dt.timezone.utc)
        except (OSError, OverflowError) as e:
            raise ValueError(f"zaman okunamadı: {s}") from e
    s = str(s).replace("Z", "+00:00")
    if re.search(r"[+-]\d{4}$", s):
        s = s[:-2] + ":" + s[-2:]
    d = dt.datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def _media_list(raw) -> list[dict]:
    """Araç sonucu (tek sayfa ya da sayfa listesi: [{ig_media: …}, …]) → tekilleştirilmiş paylaşım listesi."""
    import json

    def items(x):
        if isinstance(x, str):
            try:
                x = json.loads(x)
            except ValueError:
                return []
        if isinstance(x, dict):
            if any(k in x for k in ("ig_media", "media", "data")):
                return items(x.get("ig_media") or x.get("media") or x.get("data") or [])
            return [x] if ("timestamp" in x or "media_type" in x) else []
        if isinstance(x, list):
            return [m for e in x for m in items(e)]
        return []
    seen, out = set(), []
    for m in items(raw):
        k = str(m.get("id") or m.get("permalink") or (m.get("timestamp"), m.get("caption")))
        if k not in seen:
            seen.add(k)
            out.append(m)
    return out


def _n(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def check(media: list[dict], account: dict | None = None, cta_url: str | None = None, followers: int | None = None,
          now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    stories = [m for m in media if m.get("media_product_type") == "STORY"]
    posts = []
    for m in media:  # hikâyeler ızgarada görünmez: profil ölçüsüne girmez (ayrıca sayılır); zamanı okunamayan atlanır
        if m.get("media_product_type") == "STORY" or not m.get("timestamp"):
            continue
        try:
            _ts(m["timestamp"])
        except (TypeError, ValueError):
            continue
        posts.append(m)
    posts.sort(key=lambda m: _ts(m["timestamp"]), reverse=True)
    findings, manual = [], []
    out: dict = {"posts_read": len(posts), "stories_skipped": len(stories),
                 "account": {k: (account or {}).get(k) for k in ("username", "profile_picture_url")},
                 "scope": "ads_get_ig_media reklam verilebilir paylaşımları döndürür; profildeki her paylaşım olmayabilir"}
    if not posts:
        findings.append({"level": "high", "what": "paylaşım okunamadı ya da yok",
                         "why": "reklamdan profile gelen kişi boş profil görür; güven kurulmaz",
                         "fix": "yayından önce en az 9 paylaşım (ürün, kullanım, süreç, yorum)"})
        out.update(findings=findings, manual_checklist=_manual(cta_url))
        return out
    last = _ts(posts[0]["timestamp"])
    age = (now - last).days
    d30 = [p for p in posts if (now - _ts(p["timestamp"])).days <= 30]
    d90 = [p for p in posts if (now - _ts(p["timestamp"])).days <= 90]
    recent = posts[:12]
    reels = [p for p in recent if (p.get("media_product_type") == "REELS" or p.get("media_type") == "VIDEO")]
    eng = [_n(p.get("like_count")) + _n(p.get("comments_count")) for p in recent]
    by_type: dict[str, list[int]] = {}
    for p in recent:
        t = p.get("media_product_type") or p.get("media_type") or "?"
        by_type.setdefault(t, []).append(_n(p.get("like_count")) + _n(p.get("comments_count")))
    caps = [str(p.get("caption") or "") for p in recent]
    out.update({"last_post_days": age, "posts_last_30d": len(d30), "posts_last_90d": len(d90),
                "per_week_90d": round(len(d90) / (90 / 7), 2), "reels_share_recent": round(len(reels) / len(recent), 2),
                "median_engagement_recent": statistics.median(eng) if eng else 0,
                "median_engagement_by_type": {k: statistics.median(v) for k, v in by_type.items()},
                "captions_with_cta": sum(1 for c in caps if CTA_RX.search(c)),
                "avg_hashtags": round(sum(len(HASHTAG_RX.findall(c)) for c in caps) / len(caps), 1),
                "posts_over_hashtag_max": sum(1 for c in caps if len(HASHTAG_RX.findall(c)) > HASHTAG_MAX)})
    if followers:
        out["engagement_rate_recent"] = round(out["median_engagement_recent"] / followers, 4)
    if age > STALE_DAYS:
        findings.append({"level": "high", "what": f"son paylaşım {age} gün önce", "why": "reklamla gelen kişi işletmenin çalışıp çalışmadığını "
                         "sorgular", "fix": "reklam yayındayken haftada en az 2 paylaşım (organik adaylar listesinden)"})
    if len(posts) < GRID_MIN:
        findings.append({"level": "medium", "what": f"profilde {len(posts)} paylaşım okundu (< {GRID_MIN})", "why": "ilk bakışta ızgara boş görünür",
                         "fix": "ürün yakın çekim, kullanım anı, süreç, müşteri yorumu (izinli) paylaşımları"})
    if out["reels_share_recent"] < REELS_SHARE_MIN:
        findings.append({"level": "medium", "what": f"son paylaşımlarda video payı %{out['reels_share_recent'] * 100:.0f}",
                         "why": "reklamlar video; profil aynı dili konuşmuyor", "fix": "çekim artıklarından kısa videolar (organik adaylar)"})
    if out["captions_with_cta"] == 0:
        findings.append({"level": "low", "what": "son paylaşımlarda yönlendirme yok", "why": "ilgilenen kişi nasıl alacağını bilmez",
                         "fix": "açıklamalarda tek, net yönlendirme (profildeki bağlantı / DM / randevu)"})
    if out["posts_over_hashtag_max"]:
        findings.append({"level": "low", "what": f"son paylaşımlardan {out['posts_over_hashtag_max']} tanesinde {HASHTAG_MAX}'ten fazla etiket",
                         "why": f"Instagram Aralık 2025'ten beri paylaşım ve Reels başına en fazla {HASHTAG_MAX} etikete izin veriyor; "
                                "eski açıklamalar bu sınırın öncesinden kalmış olabilir",
                         "fix": f"yeni paylaşımlarda 3–{HASHTAG_MAX} ilgili etiket"})
    if not out["account"].get("profile_picture_url"):
        findings.append({"level": "medium", "what": "profil fotoğrafı okunamadı", "why": "tanınırlık ve güven", "fix": "logo ya da ürün simgesi"})
    top = sorted(recent, key=lambda p: -(_n(p.get("like_count")) + _n(p.get("comments_count"))))[:3]
    out["top_recent"] = [{"permalink": p.get("permalink"), "type": p.get("media_product_type") or p.get("media_type"),
                          "engagement": _n(p.get("like_count")) + _n(p.get("comments_count"))} for p in top]
    out["outliers"] = _outliers(posts[:OUTLIER_WINDOW])
    out["findings"] = findings
    out["manual_checklist"] = _manual(cta_url)
    out["note"] = ("Eşikler yereldir. Beğeni/yorum erişime göre değil mutlak sayıdır (erişim bu araçta yok); türler arası kıyas yön gösterir. "
                   "Kişi yorumları/kullanıcı adları rapora yazılmaz.")
    return out


def _outliers(posts: list[dict]) -> dict:
    """Her paylaşımın etkileşimi (beğeni+yorum) hesabın kendi ortancasının kaç katı; en iyi ve en zayıf paylaşımlar ve türe göre kat.

    Ham sayı hesabın büyüklüğünü ölçer; kat, paylaşımın o hesap için olağan mı, öne çıkmış mı olduğunu gösterir. İzlenme ve erişim bu
    araçta yok: kat yalnızca beğeni+yorumdan hesaplanır ve izlenme katı yerine geçmez.
    """
    if len(posts) < OUTLIER_MIN_POSTS:
        return {"skipped": f"{len(posts)} paylaşım (< {OUTLIER_MIN_POSTS}); kat hesaplanmadı"}
    eng = [_n(p.get("like_count")) + _n(p.get("comments_count")) for p in posts]
    base = statistics.median(eng)
    if base <= 0:
        return {"skipped": "ortanca etkileşim 0; kat hesaplanamadı"}
    rows = [{"permalink": p.get("permalink"), "date": _ts(p["timestamp"]).date().isoformat(),
             "type": p.get("media_product_type") or p.get("media_type") or "?", "engagement": e, "multiple": round(e / base, 2),
             "has_cta": bool(CTA_RX.search(str(p.get("caption") or "")))} for p, e in zip(posts, eng)]
    ranked = sorted(rows, key=lambda r: -r["multiple"])
    k = min(OUTLIER_TOP, len(rows) // 2)
    top, bottom = ranked[:k], ranked[-k:][::-1]
    by_type: dict[str, list[float]] = {}
    for r in rows:
        by_type.setdefault(r["type"], []).append(r["multiple"])
    return {"window": len(rows), "median_engagement": base, "top": top, "bottom": bottom,
            "median_multiple_by_type": {t: {"n": len(v), "median": round(statistics.median(v), 2)} for t, v in by_type.items()},
            "top_types": [r["type"] for r in top], "bottom_types": [r["type"] for r in bottom],
            "confidence": "desen için yeterli" if len(rows) >= 30 else f"{len(rows)} paylaşım: yön gösterir, kesin desen değil",
            "note": "kat = beğeni+yorum / son paylaşımların ortancası; 3 kat üzeri öne çıkan, 1,5 kat altı olağan gün (yerel okuma). "
                    "İzlenme, erişim, kaydetme ve gönderme bu araçta yok."}


def _manual(cta_url: str | None) -> list[dict]:
    return [
        {"item": "biyografi: ne satılıyor, kime, nerede/nasıl teslim — tek bakışta anlaşılıyor mu", "source": "kullanıcı bakar (araçta yok)"},
        {"item": "profildeki bağlantı reklamın gittiği adresle aynı ve açılıyor" + (f" ({cta_url})" if cta_url else ""),
         "source": "kullanıcı bakar (araçta yok)"},
        {"item": "öne çıkanlar: fiyat/kargo, yorumlar (izinli), sık sorulanlar, nasıl sipariş verilir", "source": "kullanıcı bakar (araçta yok)"},
        {"item": "iletişim düğmesi / DM otomatik karşılama (mesaj sonuçlu kampanyada)", "source": "kullanıcı bakar (araçta yok)"},
        {"item": "sabitlenmiş paylaşımlar: en güçlü ürün videosu ve güven paylaşımı", "source": "kullanıcı bakar (araçta yok)"},
    ]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--media", required=True)
    ap.add_argument("--account")
    ap.add_argument("--cta-url")
    ap.add_argument("--followers", type=int)
    ap.add_argument("--now")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    acc = read_json(a.account) if a.account else None
    if isinstance(acc, dict) and "ig_accounts" in acc:
        import json
        lst = acc["ig_accounts"]
        acc = (json.loads(lst) if isinstance(lst, str) else lst or [None])[0]
    now = _ts(a.now + "T00:00:00+00:00") if a.now else None
    res = check(_media_list(read_json(a.media)), acc, a.cta_url, a.followers, now)
    write_json(a.out, res)
    emit({"out": a.out, "posts_read": res["posts_read"], "findings": len(res["findings"])})


if __name__ == "__main__":
    main()
