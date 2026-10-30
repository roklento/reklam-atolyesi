"""Instagram profil kontrolü (1.5.0; 2.2.0: etiket sınırı, kendi ortancasına göre kat, profil puanı, İstatistikler girdisi): reklamı gören kişi profile baktığında güven buluyor mu.

Girdi yalnızca salt okuma araçlarının döndürdüğü alanlardır (ads_get_ig_accounts: username, profile_picture_url; ads_get_ig_media:
caption, like_count, comments_count, media_type, media_product_type, permalink, timestamp — 21.10.2026'da bağlı hesapta okundu).
Biyografi, profildeki bağlantı, takipçi sayısı, öne çıkanlar ve erişim bu araçlarda YOK: bunlar kullanıcıya kontrol listesi olarak sorulur,
tahmin edilmez. Eşikler YEREL kurallardır (Meta/Instagram kuralı değil).

Kullanım: profile_check.py --media media.json [--account account.json] [--cta-url https://…] [--followers N] [--now 2026-10-21]
          [--fields alanlar.json] [--insights istatistik.json] --out profil.json
          (media.json: araç sonucundaki ig_media listesi; sayfalar birleştirilmiş olabilir)
alanlar.json (2.2.0, kullanıcının söylediği ya da ekran görüntüsünden okunan; bilinmeyen alan yazılmaz): name_field, bio, link,
  highlights (ad listesi), pinned (sayı), contact_button (bool), story_last_7d (bool). Profil puanı yalnızca bilinen maddelerden hesaplanır.
istatistik.json (2.2.0, Instagram İstatistikler ekran görüntüsünden; araçta yok): [{permalink|date, views, reach, nonfollower_share,
  shares, saves, follows, hold_3s}] — bilinmeyen alan yazılmaz, tahmin edilmez.
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
OFFER_RX = re.compile(r"(kargo|teslim|gönderim|sipariş|randevu|adres|şube|online|tüm türkiye|şehir|el yapımı|üretim|kişiye özel)", re.I)
BUYER_Q_RX = re.compile(r"(fiyat|kargo|yorum|değerlendirme|sss|soru|sipariş|nasıl|hakkı|ürün|katalog|teslim|iade|kampanya)", re.I)
# Profil puanı (yerel ağırlıklar, toplam 100). Ağırlık, reklamdan gelen kişinin ilk bakışta işlediği alanlara göre verildi.
SCORE_MAX = {"recency": 12, "frequency": 8, "video_share": 8, "grid": 6, "photo": 4, "captions_cta": 6, "hashtags": 2,
             "name_field": 10, "bio": 12, "link": 8, "highlights": 8, "pinned": 8, "contact": 4, "story": 4}
SCORE_LABEL = {"recency": "son paylaşım", "frequency": "haftalık sıklık", "video_share": "video payı", "grid": "ızgara dolu",
               "photo": "profil fotoğrafı", "captions_cta": "açıklamalarda yönlendirme", "hashtags": "etiket sınırı",
               "name_field": "isim alanı", "bio": "biyografi", "link": "profildeki bağlantı", "highlights": "öne çıkanlar",
               "pinned": "sabitlenmiş paylaşımlar", "contact": "iletişim düğmesi", "story": "hikâye (son 7 gün)"}
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
          now: dt.datetime | None = None, fields: dict | None = None, insights: list[dict] | None = None) -> dict:
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
        out.update(findings=findings, manual_checklist=_manual(cta_url), score=score(out, fields, cta_url))
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
    if insights:
        out["insights"] = _insights(insights, posts)
    out["score"] = score(out, fields, cta_url)
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


def _host(u: str | None) -> str:
    m = re.match(r"^(?:https?://)?(?:www\.)?([^/?#]+)", str(u or "").strip().lower())
    return m.group(1) if m else ""


def score(out: dict, fields: dict | None, cta_url: str | None) -> dict:
    """Profil puanı (100, yerel ağırlıklar): ölçülen maddeler araçtan, yazılı alanlar kullanıcıdan (alanlar.json).

    Bilinmeyen madde puanlanmaz ve paydadan düşer; puan "kazanılan / bilinen" olarak verilir. Metnin iyi yazılıp yazılmadığını betik
    ölçmez: yalnızca yapı kontrol edilir (var mı, sınırda mı, yönlendirme/teslim bilgisi geçiyor mu); yeniden yazımı skill yapar.
    """
    f = fields or {}
    got: dict[str, tuple[int | None, str]] = {}
    if out.get("posts_read"):
        age = out.get("last_post_days", 999)
        got["recency"] = (12 if age <= 7 else 6 if age <= STALE_DAYS else 0, f"{age} gün önce")
        pw = out.get("per_week_90d", 0)
        got["frequency"] = (8 if pw >= 2 else 4 if pw >= 1 else 0, f"haftada {pw}")
        vs = out.get("reels_share_recent", 0)
        got["video_share"] = (8 if vs >= 0.5 else 4 if vs >= REELS_SHARE_MIN else 0, f"%{vs * 100:.0f}")
        got["captions_cta"] = (6 if out.get("captions_with_cta", 0) >= 3 else 3 if out.get("captions_with_cta") else 0,
                               f"{out.get('captions_with_cta', 0)} açıklamada")
        got["hashtags"] = (0 if out.get("posts_over_hashtag_max") else 2, f"{out.get('posts_over_hashtag_max', 0)} paylaşım sınır üstü")
    got["grid"] = (6 if out.get("posts_read", 0) >= GRID_MIN else 0, f"{out.get('posts_read', 0)} paylaşım")
    got["photo"] = (4 if (out.get("account") or {}).get("profile_picture_url") else 0, "")
    name = f.get("name_field")
    if name is not None:
        name = str(name).strip()
        user = re.sub(r"[^a-z0-9]", "", str((out.get("account") or {}).get("username") or "").lower())
        words = [w for w in re.split(r"[\s|·,/-]+", name) if w]
        only_handle = re.sub(r"[^a-z0-9]", "", name.lower()) == user
        p = 0 if not name else 3 if (len(words) < 2 or only_handle) else 10
        got["name_field"] = (p if len(name) <= 30 else min(p, 5), f"{len(name)} karakter, {len(words)} sözcük")
    bio = f.get("bio")
    if bio is not None:
        bio = str(bio).strip()
        p = (4 if bio else 0) + (2 if bio and len(bio) <= 150 else 0) + (3 if CTA_RX.search(bio) else 0) + (3 if OFFER_RX.search(bio) else 0)
        got["bio"] = (p, f"{len(bio)} karakter; yönlendirme {'var' if CTA_RX.search(bio) else 'yok'}, "
                         f"teslim/sunum bilgisi {'var' if OFFER_RX.search(bio) else 'yok'}")
    if "link" in f:
        link = str(f.get("link") or "").strip()
        same = bool(link and cta_url and _host(link) == _host(cta_url))
        got["link"] = (8 if same else 3 if link else 0,
                       "reklam adresiyle aynı alan adı" if same else ("reklam adresi bilinmiyor" if link and not cta_url else
                                                                    "reklam adresinden farklı" if link else "bağlantı yok"))
    if f.get("highlights") is not None:
        hl = [str(h) for h in f.get("highlights") or []]
        q = sum(1 for h in hl if BUYER_Q_RX.search(h))
        got["highlights"] = ((4 if 4 <= len(hl) <= 6 else 2 if hl else 0) + (4 if q >= 2 else 2 if q else 0),
                             f"{len(hl)} öne çıkan, {q} tanesi alıcı sorusuna adlı")
    if f.get("pinned") is not None:
        n = _n(f.get("pinned"))
        got["pinned"] = (8 if n >= 3 else 4 if n >= 1 else 0, f"{n} sabitlenmiş")
    for k, src in (("contact", "contact_button"), ("story", "story_last_7d")):
        if f.get(src) is not None:
            got[k] = (SCORE_MAX[k] if f.get(src) else 0, "var" if f.get(src) else "yok")
    items = [{"id": k, "label": SCORE_LABEL[k], "points": got[k][0], "max": SCORE_MAX[k], "detail": got[k][1],
              "source": "kullanıcı" if k in ("name_field", "bio", "link", "highlights", "pinned", "contact", "story") else "araç"}
             for k in SCORE_MAX if k in got]
    unknown = [SCORE_LABEL[k] for k in SCORE_MAX if k not in got]
    earned, known = sum(i["points"] for i in items), sum(i["max"] for i in items)
    fix = sorted((i for i in items if i["points"] < i["max"]), key=lambda i: -(i["max"] - i["points"]))
    return {"earned": earned, "known_max": known, "of_100": earned if not unknown else None, "items": items, "unknown": unknown,
            "fix_order": [{"id": i["id"], "label": i["label"], "lost": i["max"] - i["points"]} for i in fix],
            "note": "Ağırlıklar yereldir (Meta/Instagram puanı değil). Bilinmeyen madde puanlanmaz; puan 'kazanılan / bilinen' okunur. "
                    "Betik metnin kalitesini değil yapısını ölçer."}


def _insights(rows: list[dict], posts: list[dict]) -> dict:
    """İstatistikler ekran görüntüsünden gelen sayılar: izlenme katı, takipçi dışı erişim, erişim başına gönderme/takip ve teşhis.

    Araç izlenme/erişim vermez; bu sayılar yalnızca kullanıcının verdiği paylaşımlar içindir, tahmin edilmez. Görüntü çok ama takip az ise
    sorun açılış değil profildir; görüntü az ise açılış (ilk 3 sn) sorunudur.
    """
    by_link = {p.get("permalink"): p for p in posts}
    out_rows = []
    for r in rows:
        p = by_link.get(r.get("permalink")) or {}
        row = {"permalink": r.get("permalink"), "date": r.get("date") or (p.get("timestamp") or "")[:10],
               "type": p.get("media_product_type") or p.get("media_type") or r.get("type")}
        for k in ("views", "reach", "shares", "saves", "follows"):
            if r.get(k) is not None:
                row[k] = _n(r[k])
        for k in ("nonfollower_share", "hold_3s"):
            if r.get(k) is not None:
                v = float(r[k])
                row[k] = round(v / 100 if v > 1 else v, 3)
        if row.get("reach"):
            for k, nm in (("shares", "shares_per_reach"), ("follows", "follows_per_reach"), ("saves", "saves_per_reach")):
                if k in row:
                    row[nm] = round(row[k] / row["reach"], 4)
        out_rows.append(row)
    views = [r["views"] for r in out_rows if r.get("views")]
    base = statistics.median(views) if views else 0
    for r in out_rows:
        if base and r.get("views"):
            r["views_multiple"] = round(r["views"] / base, 2)
    diag = []
    fpr = [r["follows_per_reach"] for r in out_rows if "follows_per_reach" in r]
    fpr_med = statistics.median(fpr) if fpr else None
    for r in out_rows:
        if r.get("views_multiple", 0) >= 2 and fpr_med is not None and r.get("follows_per_reach", fpr_med) < fpr_med:
            diag.append({"permalink": r["permalink"], "finding": "görüntü çok, takip az", "next": "profil (biyografi, sabitlenmiş, bağlantı)"})
        elif r.get("views_multiple") is not None and r["views_multiple"] < 0.5:
            diag.append({"permalink": r["permalink"], "finding": "görüntü az", "next": "açılış (ilk 3 sn)"})
    rank = sorted(out_rows, key=lambda r: (-(r.get("views_multiple") or 0), -(r.get("shares_per_reach") or 0)))
    return {"n": len(out_rows), "median_views": base, "rows": rank, "diagnosis": diag, "source": "kullanıcı (İstatistikler ekran görüntüsü)",
            "confidence": "desen için yeterli" if len(out_rows) >= 30 else f"{len(out_rows)} paylaşım: yön gösterir, kesin desen değil",
            "note": "Sıralama izlenme katı ve erişim başına gönderme ile; ham izlenme hesabın büyüklüğünü ölçer. Bu sayılar reklam "
                    "kararlarına girmez."}


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
    ap.add_argument("--fields")
    ap.add_argument("--insights")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    acc = read_json(a.account) if a.account else None
    if isinstance(acc, dict) and "ig_accounts" in acc:
        import json
        lst = acc["ig_accounts"]
        acc = (json.loads(lst) if isinstance(lst, str) else lst or [None])[0]
    now = _ts(a.now + "T00:00:00+00:00") if a.now else None
    ins = read_json(a.insights) if a.insights else None
    if isinstance(ins, dict):
        ins = ins.get("rows") or ins.get("posts") or []
    res = check(_media_list(read_json(a.media)), acc, a.cta_url, a.followers, now,
                read_json(a.fields) if a.fields else None, ins)
    write_json(a.out, res)
    sc = res["score"]
    emit({"out": a.out, "posts_read": res["posts_read"], "findings": len(res["findings"]),
          "score": f"{sc['earned']}/{sc['known_max']}", "unknown": len(sc["unknown"])})


if __name__ == "__main__":
    main()
