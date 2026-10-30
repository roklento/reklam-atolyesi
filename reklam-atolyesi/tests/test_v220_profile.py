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
