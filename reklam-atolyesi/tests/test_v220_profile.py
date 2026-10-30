"""2.2.0: profil kontrolünde Instagram'ın 5 etiket sınırı ve paylaşım başına "kendi ortancasının kaç katı" ölçüsü."""
from __future__ import annotations

import datetime as dt

import profile_check as PC

NOW = dt.datetime(2026, 10, 30, tzinfo=dt.timezone.utc)


def _post(days_ago, kind="REELS", likes=10, comments=0, cap="Sipariş için profildeki bağlantı"):
    ts = (NOW - dt.timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S+0000")
    return {"id": f"p{days_ago}", "timestamp": ts, "media_product_type": kind, "like_count": likes, "comments_count": comments,
            "caption": cap, "permalink": f"https://www.instagram.com/p/x{days_ago}/"}


def _acc():
    return {"username": "marka", "profile_picture_url": "https://x"}


def test_hashtag_limit_is_five():
    five = " ".join(f"#e{i}" for i in range(5))
    six = " ".join(f"#e{i}" for i in range(6))
    ok = PC.check([_post(d, cap="Sipariş DM " + five) for d in range(1, 10)], _acc(), now=NOW)
    assert ok["posts_over_hashtag_max"] == 0 and not [f for f in ok["findings"] if "etiket" in f["what"]]
    over = PC.check([_post(d, cap="Sipariş DM " + (six if d <= 2 else five)) for d in range(1, 10)], _acc(), now=NOW)
    f = [f for f in over["findings"] if "etiket" in f["what"]]
    assert over["posts_over_hashtag_max"] == 2 and len(f) == 1 and f[0]["level"] == "low" and "5" in f[0]["why"]
    # Türkçe harfli etiketler de sayılır
    tr = PC.check([_post(d, cap="Sipariş #ücretsizKargo #kargoŞirketi #a #b #c #d") for d in range(1, 10)], _acc(), now=NOW)
    assert tr["posts_over_hashtag_max"] == 9


def test_outlier_multiple():
    posts = [_post(d, "FEED" if d % 2 else "REELS", likes=10) for d in range(1, 13)]
    posts[0]["like_count"] = 50   # 5 kat
    posts[1]["like_count"] = 2    # 0,2 kat
    o = PC.check(posts, _acc(), now=NOW)["outliers"]
    assert o["median_engagement"] == 10 and o["window"] == 12
    assert o["top"][0]["multiple"] == 5.0 and o["top"][0]["permalink"].endswith("x1/")
    assert o["bottom"][0]["multiple"] == 0.2 and len(o["top"]) == len(o["bottom"]) == 5
    assert set(o["median_multiple_by_type"]) == {"FEED", "REELS"} and "yön gösterir" in o["confidence"]
    assert "İzlenme" in o["note"]


def test_outlier_skipped_when_few_or_zero():
    assert "skipped" in PC.check([_post(d) for d in range(1, 5)], _acc(), now=NOW)["outliers"]
    assert "skipped" in PC.check([_post(d, likes=0) for d in range(1, 10)], _acc(), now=NOW)["outliers"]


def test_outlier_window_is_last_30():
    posts = [_post(d, likes=10) for d in range(1, 41)]
    o = PC.check(posts, _acc(), now=NOW)["outliers"]
    assert o["window"] == 30 and o["confidence"] == "desen için yeterli"


# --- profil puanı, İstatistikler girdisi, organik açıklama denetimi ----------------------------------------------------------------
def _fresh():
    return [_post(d, "REELS" if d % 2 else "FEED", likes=10) for d in range(1, 13)]


def test_score_only_measured_when_no_fields():
    sc = PC.check(_fresh(), _acc(), now=NOW)["score"]
    assert sc["of_100"] is None and "biyografi" in sc["unknown"] and sc["known_max"] == 46
    assert all(i["source"] == "araç" for i in sc["items"])


def test_score_full_profile_and_fix_order():
    good = {"name_field": "Marka | El yapımı mum", "bio": "Doğum günü hediyesi arayanlara el yapımı mum. Tüm Türkiye kargo. Sipariş: DM",
            "link": "https://www.ornek.com/urun", "highlights": ["Fiyat", "Kargo", "Yorumlar", "Nasıl sipariş"], "pinned": 3,
            "contact_button": True, "story_last_7d": True}
    sc = PC.check(_fresh(), _acc(), "https://ornek.com/kampanya", now=NOW, fields=good)["score"]
    assert sc["known_max"] == 100 and sc["of_100"] == sc["earned"] and not sc["unknown"]
    assert {i["id"]: i["points"] for i in sc["items"]}["name_field"] == 10
    weak = {"name_field": "marka", "bio": "", "link": "https://baska.com", "highlights": ["Random", "2023"], "pinned": 0,
            "contact_button": False}
    sc2 = PC.check(_fresh(), _acc(), "https://ornek.com", now=NOW, fields=weak)["score"]
    pts = {i["id"]: i["points"] for i in sc2["items"]}
    assert pts["name_field"] == 3 and pts["bio"] == 0 and pts["link"] == 3 and pts["highlights"] == 2 and pts["pinned"] == 0
    assert sc2["fix_order"][0]["id"] == "bio" and "hikâye (son 7 gün)" in sc2["unknown"] and sc2["of_100"] is None


def test_insights_diagnosis():
    posts = _fresh()
    rows = [{"permalink": p["permalink"], "views": 1000, "reach": 800, "follows": 8, "shares": 4} for p in posts]
    rows[0].update(views=5000, reach=4000, follows=4, shares=60, nonfollower_share=72)   # çok izlendi, takip az → profil
    rows[1].update(views=200, reach=180)                                                   # az izlendi → açılış
    ins = PC.check(posts, _acc(), now=NOW, insights=rows)["insights"]
    assert ins["median_views"] == 1000 and ins["rows"][0]["views_multiple"] == 5.0 and ins["rows"][0]["nonfollower_share"] == 0.72
    d = {x["permalink"]: x["finding"] for x in ins["diagnosis"]}
    assert d[posts[0]["permalink"]] == "görüntü çok, takip az" and d[posts[1]["permalink"]] == "görüntü az"
    assert "insights" not in PC.check(posts, _acc(), now=NOW)


def test_caption_check():
    import caption_check as CC
    ok = CC.check_caption("3 günde kargoda: el yapımı mum, 250 TL.\nSipariş için profildeki bağlantı. #mum #hediye")
    assert ok["warnings"] == 0 and not ok["cut"]
    long_first = "Ç" * 130 + "​" + " DM ya da WhatsApp'tan yazın " + " ".join(f"#ş{i}" for i in range(6))
    r = CC.check_caption(long_first, ["el yapımı"])
    bad = {c["id"] for c in r["checks"] if not c["ok"]}
    assert {"first_line", "hashtags", "one_cta", "concrete_in_view", "invisible_chars", "search_terms"} <= bad
    assert r["cut"] and len(r["visible"]) == 125 and "​" not in r["clean_text"]
