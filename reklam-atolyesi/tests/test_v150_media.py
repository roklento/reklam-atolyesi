"""1.5.0: vurgulu altyazı, ses efekti yoğunluğu, Meta A/B testi, profil kontrolü ve organik adaylar."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

import coach as CO
import report as RP
from admem.util import AdMemoryError
from test_analytics import build_campaign


# --- vurgulu altyazı --------------------------------------------------------------------------------------------------------------
def _w(xs):
    return [{"text": t, "start": i * 0.3, "end": i * 0.3 + 0.3} for i, t in enumerate(xs)]


def test_caption_emphasis_rules():
    import words_align as WA
    ch = WA.chunks(_w(["Bu", "hafta", "sadece", "850", "TL."]))
    assert ch[0]["emph"] == 3 and len(ch[0]["words"]) == 5  # sayı/fiyat öncelikli
    ch = WA.chunks(_w(["El", "yapımı", "doğal", "soya", "mumu."]), keywords=["soya"])
    assert ch[0]["emph"] == 3  # anahtar kelime en öncelikli
    ch = WA.chunks(_w(["Kokusu", "gerçekten", "çok", "güzel."]))
    assert ch[0]["words"][ch[0]["emph"]]["text"] == "gerçekten"  # en uzun anlamlı sözcük
    assert WA.chunks(_w(["ve", "bu", "da"]))[0]["emph"] is None  # aday yok → vurgu yok
    many = WA.chunks(_w(["Hemen", "sipariş", "verin.", "Kargo", "ücretsiz", "bugün."]))
    assert len(many) == 2 and all(isinstance(c["emph"], (int, type(None))) for c in many)  # parça başına en fazla bir


def test_caption_keywords_through_merge(tmp_path):
    import asr_local as A
    (tmp_path / "vo.json").write_text(json.dumps({"words": _w(["El", "yapımı", "soya", "mumu."])}), encoding="utf-8")
    m = A.merge_captions([(tmp_path / "vo.json", 0.0)], keywords=["soya"])
    assert m["captions"][0]["emph"] == 2


def test_caption_preset_validated():
    from admem import editplan
    base = {"campaign": "c", "cycle_id": 1, "concept": "k", "hook": "h", "format": "9x16", "purpose": "production", "status": "draft",
            "version": 1, "duration_s": 2, "fps": 30, "style": "s",
            "scenes": [{"id": "s1", "role": "hook", "start_s": 0, "dur_s": 2, "audio": {"mode": "none"}, "layers": []}]}
    assert not [e for e in editplan.validate({**base, "captions": {"on": True, "preset": "keyword_upper"}})["errors"] if "şema" in e]
    assert any("şema" in e for e in editplan.validate({**base, "captions": {"on": True, "preset": "neon"}})["errors"])


# --- ses efekti yoğunluğu --------------------------------------------------------------------------------------------------------
def _sfx_plan(cues_by_scene):
    scenes, t = [], 0.0
    for i, cues in enumerate(cues_by_scene):
        scenes.append({"id": f"s{i}", "role": "hook" if i == 0 else "product", "start_s": t, "dur_s": 2.0, "audio": {"mode": "none"},
                       "layers": [], "audio_cues": [{"sfx": n, "at_s": a} for n, a in cues]})
        t += 2.0
    return {"campaign": "c", "cycle_id": 1, "concept": "k", "hook": "h", "format": "9x16", "purpose": "production", "status": "draft",
            "version": 1, "duration_s": t, "fps": 30, "style": "s", "scenes": scenes}


def test_sfx_density_rules():
    from admem import editplan
    ok = _sfx_plan([[("whoosh", 0.2), ("pop", 1.4)], [("whoosh", 0.5)]])  # whoosh 0,2 ve 2,5 sn: 2,3 sn arayla
    assert not [e for e in editplan.validate(ok)["errors"] if "efekt" in e]
    dense = _sfx_plan([[("a", 0.1), ("b", 0.4), ("c", 0.8)], []])
    assert any("yoğunluğu" in e for e in editplan.validate(dense)["errors"])
    rep = _sfx_plan([[("whoosh", 0.2)], [("whoosh", 0.0)]])  # 0,2 ve 2,0 sn: 1,8 sn
    assert any("tekrarı" in e for e in editplan.validate(rep)["errors"])
    outside = _sfx_plan([[("a", 2.5)], []])
    assert any("dışında" in e for e in editplan.validate(outside)["errors"])
    pair = _sfx_plan([[("a", 0.2), ("b", 0.9)], []])
    assert not editplan.sfx_density(pair["scenes"])
    assert any("yoğunluğu" in e for e in editplan.sfx_density(pair["scenes"], {"sfxMaxPerSec": 1}))  # stil daha sıkı yapabilir
    assert not editplan.sfx_density(ok["scenes"], {"sfxMaxPerSec": 9, "sfxRepeatGapS": 0.5})  # gevşetemez


def test_mix_ducks_sfx_not_speech(tmp_path):
    import numpy as np
    import soundfile as sf
    import mix as MX
    sr = 48000
    speech = (0.3 * np.sin(2 * np.pi * 220 * np.arange(2 * sr) / sr)).astype("float32")
    sf.write(tmp_path / "seg.wav", np.stack([speech, speech], 1), sr)
    tone = (0.5 * np.sin(2 * np.pi * 900 * np.arange(int(0.5 * sr)) / sr)).astype("float32")
    sf.write(tmp_path / "pop.wav", np.stack([tone, tone], 1), sr)
    plan = {"duration_s": 4, "fps": 30, "music": None, "scenes": [
        {"id": "s1", "start_s": 0, "dur_s": 2, "audio": {"mode": "original"}, "layers": [], "audio_cues": [{"sfx": "pop", "at_s": 0.5}]},
        {"id": "s2", "start_s": 2, "dur_s": 2, "audio": {"mode": "none"}, "layers": [], "audio_cues": [{"sfx": "pop", "at_s": 0.5}]}]}
    r = MX.mix(plan, {"s1": str(tmp_path / "seg.wav")}, None, None, {"pop": str(tmp_path / "pop.wav")}, tmp_path / "stems")
    fx, _ = sf.read(r["stems"]["sfx"])
    dl, _ = sf.read(r["stems"]["dialog"])
    under = np.abs(fx[int(0.6 * sr):int(0.9 * sr)]).max()
    free = np.abs(fx[int(2.6 * sr):int(2.9 * sr)]).max()
    assert under < free * 0.6 and r["sfx_duck_db"] == 6.0  # konuşma üstündeki efekt ~6 dB kısık
    assert abs(np.abs(dl[int(0.6 * sr):int(0.9 * sr)]).max() - 0.3) < 0.02  # konuşma kısılmadı


# --- A/B testi -----------------------------------------------------------------------------------------------------------------
def test_ab_check_rules():
    import budget as BU
    ok = BU.ab_check({"cells": 3, "daily_total": 900, "expected_cpr": 60, "cpr_source": "history"})
    assert ok["eligible"] and ok["days"] == 7 and ok["expected_results_per_cell"] >= 30
    long = BU.ab_check({"cells": 2, "daily_total": 50, "expected_cpr": 60, "cpr_source": "history"})
    assert not long["eligible"] and any("en fazla 30" in r for r in long["reasons"])
    assert not BU.ab_check({"cells": 6, "daily_total": 9000, "expected_cpr": 10})["eligible"]
    assert not BU.ab_check({"cells": 1, "daily_total": 900, "expected_cpr": 10})["eligible"]
    nocost = BU.ab_check({"cells": 3, "daily_total": 900, "expected_cpr": None})
    assert not nocost["eligible"] and any("maliyeti yok" in r for r in nocost["reasons"])
    short = BU.ab_check({"cells": 2, "daily_total": 900, "expected_cpr": 10, "cpr_source": "target_exact", "days": 5})
    assert not short["eligible"] and any("en az 7" in r for r in short["reasons"])
    assert "facebook.com/business/help" in ok["rules"]["source"][0] and "yerel" in ok["rules"]["local"]
    assert BU.scale_check(structure="ab_test", cost_ok=True, target_cpa=50, economics_exact=True, proposed_daily=400, budget_total=None,
                          spend_to_date=0, other_daily=0, days_left=7)["checks"]["structure"]


def test_ab_structure_requires_read_study_and_coach_section(store):
    pid, cid, cyid = build_campaign(store)
    with pytest.raises(AdMemoryError, match="meta_test_id"):
        store.cycle_set(pid, cyid, structure_detected="ab_test", structure_evidence_json={"source": "kullanıcı söyledi"})
    store.cycle_set(pid, cyid, structure_detected="ab_test", meta_test_id="6120000000001",
                    structure_evidence_json={"study_read": {"cells": ["A", "B", "C"], "variable": "creative", "start": "2026-03-02"}})
    store.ex("UPDATE metrics_daily SET results=CASE WHEN ad_id IN (SELECT id FROM ads WHERE meta_ad_id='901') THEN 9 WHEN ad_id IN (SELECT id FROM ads WHERE meta_ad_id='903') THEN 0 ELSE 3 END")
    snap = store.decision_input_snapshot(pid, cid, cyid, "coach_report",
                                         extra={"ab_test": {"study_id": "6120000000001", "winner_concept": "A", "confidence": 0.93}})
    an = CO.analyze(snap["path"])
    ab = an["ab_test"]
    assert ab["leader"] == "A" and ab["agrees_with_meta"] and ab["cells"]["A"]["p_lowest_cost"] > 0.8
    assert ab["cells"]["B"]["p_lowest_cost"] < 0.05 and not ab["cells"]["C"]["threshold_met"]  # az harcamalı 0 sonuçlu hücre belirsiz kalır
    assert all("Meta'nın dağıtımı altında" not in d["label"] for d in an["decisions"])
    md = RP.build(an, json.load(open(snap["path"], encoding="utf-8")), {}, None, None, None)
    assert "Meta A/B testi" in md and "kazanan A" in md


def test_allowlist_has_eligibility_read_only():
    al = json.loads((Path(__file__).resolve().parents[1] / "hooks" / "meta_allowlist.json").read_text(encoding="utf-8"))
    assert "ads_experiment_check_eligibility" in al["allow"]
    assert not any(t.endswith(("create_test", "update_test")) for t in al["allow"])  # çalışma oluşturma/değiştirme yok


# --- profil kontrolü ve organik adaylar ---------------------------------------------------------------------------------------
NOW = dt.datetime(2026, 10, 21, tzinfo=dt.timezone.utc)


def _media(days_ago, kind="REELS", likes=10, comments=2, cap="Sipariş için profildeki bağlantı"):
    ts = (NOW - dt.timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S+0000")
    return {"id": f"m{days_ago}{kind}", "timestamp": ts, "media_product_type": kind, "media_type": "VIDEO" if kind == "REELS" else "IMAGE",
            "like_count": likes, "comments_count": comments, "caption": cap, "permalink": f"https://www.instagram.com/p/x{days_ago}/"}


def test_profile_check():
    import profile_check as PC
    fresh = [_media(d, "REELS" if d % 4 == 1 else "FEED") for d in range(1, 22, 2)]
    r = PC.check(fresh, {"username": "marka", "profile_picture_url": "https://x"}, "https://ornek.com", followers=1000, now=NOW)
    assert r["posts_read"] == 11 and r["last_post_days"] == 1 and not [f for f in r["findings"] if f["level"] == "high"]
    assert r["engagement_rate_recent"] == round(12 / 1000, 4) and len(r["manual_checklist"]) >= 4
    stale = PC.check([_media(40, "FEED", cap="güzel"), _media(50, "FEED", cap="güzel")], {"username": "m"}, now=NOW)
    whats = " ".join(f["what"] for f in stale["findings"])
    for part in ("40 gün", "2 paylaşım", "video payı", "yönlendirme", "fotoğraf"):
        assert part in whats, part
    assert PC.check([], None, now=NOW)["findings"][0]["level"] == "high"
    assert len(PC._media_list({"ig_media": json.dumps([_media(1), _media(1)])})) == 1


def test_organic_candidates():
    import candidates as OC
    assets = [
        {"id": 1, "kind": "footage", "path": "a.mp4", "score_json": {"overall": 0.8}, "best_ranges_json": [{"in_s": 0, "out_s": 5}],
         "tags": "process", "used_in_json": [], "people_json": []},
        {"id": 2, "kind": "footage", "path": "b.mp4", "score_json": {"overall": 0.9}, "best_ranges_json": [{"in_s": 0, "out_s": 5}],
         "tags": "", "used_in_json": ["ad1"], "people_json": []},
        {"id": 3, "kind": "footage", "path": "c.mp4", "score_json": {"overall": 0.3}, "best_ranges_json": [{"in_s": 0, "out_s": 5}]},
        {"id": 4, "kind": "footage", "path": "d.mp4", "score_json": {"overall": 0.9}, "best_ranges_json": [{"in_s": 0, "out_s": 5}],
         "people_json": [{"t": 1, "kind": "face"}]},
        {"id": 5, "kind": "footage", "path": "e.mp4", "score_json": {"overall": 0.9}, "best_ranges_json": [{"in_s": 0, "out_s": 1.5}]},
    ]
    an = {"decisions": [{"concept": "A", "decision": "büyüt", "label": "kanıt"}, {"concept": "B", "decision": "tut", "label": "yön/yetersiz veri"}]}
    r = OC.build(assets, an, [{"in": "k.wav", "words": [{"text": "x"}] * 20}], per_week=3, start=dt.date(2026, 10, 22))
    assert [c["kind"] for c in r["candidates"]] == ["winning_ad", "talking_clip", "unused_clip"]
    assert r["candidates"][2]["angle"] == "süreç / nasıl yapılıyor"
    assert r["skipped"] == {"used_in_ads": 1, "organic_posted": 0, "low_score": 1, "no_consent": 1, "short": 1}
    posted = [{**assets[0], "used_in_json": [{"creative_key": "organic:2026-10-22", "role": "organic"}]}]
    assert OC.build(posted)["skipped"]["organic_posted"] == 1  # paylaşılan klip yeniden önerilmez
    assert [c["date"] for c in r["calendar"]] == ["2026-10-22", "2026-10-24", "2026-10-27"]
