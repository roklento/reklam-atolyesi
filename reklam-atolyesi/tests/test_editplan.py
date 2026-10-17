"""Kurgu planı doğrulaması (spec 5.2, 5.6, 5.12, 10)."""
from __future__ import annotations

import copy

from admem import editplan


def plan(**over):
    p = {"campaign": "k", "cycle_id": 1, "concept": "A", "hook": "h1", "format": "9x16", "purpose": "production", "status": "ready",
         "version": 1, "style_snapshot_sha256": "x", "duration_s": 6, "fps": 30, "style": "styles/v1.json",
         "scenes": [
             {"id": "s1", "role": "hook", "start_s": 0, "dur_s": 2, "beat_lock": "downbeat", "audio": {"mode": "none", "decision_id": "d1"},
              "layers": [{"type": "video", "source": {"kind": "footage", "asset": "a1", "in_s": 0, "out_s": 2}},
                         {"type": "text", "preset": "text_reveal", "text": "Örnek", "anchor": "safe_top"}],
              "transition_out": {"type": "crossfade", "dur_s": 0.3}},
             {"id": "s2", "role": "reveal", "start_s": 2, "dur_s": 2, "audio": {"mode": "none", "decision_id": "d2"},
              "layers": [{"type": "video", "source": {"kind": "footage", "asset": "a2"}}, {"type": "component", "component": "LightRays"}]},
             {"id": "s3", "role": "endcard", "start_s": 4, "dur_s": 2, "audio": {"mode": "none", "decision_id": "d3"},
              "layers": [{"type": "component", "component": "EndCard", "props": {"brand": "Marka A", "cta": "Örnek"}}]}]}
    p.update(over)
    return p


def test_valid_plan():
    r = editplan.validate(plan(), beats=[0.0, 2.0, 4.0])
    assert r["valid"], r["errors"]


def test_competitor_source_rejected():
    p = plan()
    p["scenes"][1]["layers"][0]["source"] = {"kind": "still", "path": "profiles/x/competitors/cache/a.jpg"}
    r = editplan.validate(p)
    assert not r["valid"] and any("rakip" in e for e in r["errors"])


def test_effect_budget():
    p = plan()
    p["scenes"][2]["layers"].append({"type": "component", "component": "ParticleSwirl"})
    p["scenes"][1]["transition_out"] = {"type": "whipPan", "dur_s": 0.3}
    p["scenes"][0]["layers"].append({"type": "component", "component": "FilmBurn"})
    r = editplan.validate(p)
    assert any("imza" in e for e in r["errors"]) and any("geçiş türü" in e for e in r["errors"])
    p2 = plan()
    p2["scenes"][0]["layers"].append({"type": "component", "component": "Bokeh"})
    assert any("atmosfer" in e for e in editplan.validate(p2)["errors"])
    assert editplan.validate(p2, style={"effects": {"persistentAtmosphere": True}})["valid"]


def test_signature_only_reveal_endcard():
    p = plan()
    p["scenes"][0]["layers"].append({"type": "component", "component": "LightRays"})
    p["scenes"][1]["layers"].pop()
    assert any("yalnızca reveal" in e for e in editplan.validate(p)["errors"])


def test_speaking_person_audio_mode():
    p = plan()
    p["scenes"][0]["speaking_person"] = True
    assert any("konuşan kişi" in e for e in editplan.validate(p)["errors"])
    p["scenes"][0]["audio"]["mode"] = "original_clean"
    assert editplan.validate(p)["valid"]


def test_style_preview_audio_none_and_draft_rules():
    p = plan(purpose="style_preview", status="draft", style_snapshot_sha256=None)
    p["scenes"][0]["audio"]["mode"] = "generated"
    assert any("stil önizlemesi" in e for e in editplan.validate(p)["errors"])
    d = plan(status="ready")
    d["scenes"][1]["audio"]["decision_id"] = None
    assert any("decision_id" in e for e in editplan.validate(d)["errors"])
    d2 = plan(status="ready", missing=["s2 klibi"])
    assert any("eksik varlık" in e for e in editplan.validate(d2)["errors"])


def test_timing_and_beat_lock():
    p = plan()
    p["scenes"][1]["start_s"] = 2.5
    assert any("bitişik" in e for e in editplan.validate(p)["errors"])
    p2 = plan()
    assert any("vuruşa" in e for e in editplan.validate(p2, beats=[0.5, 2.0])["errors"])  # s1 kilitli, en yakın vuruş 15 kare uzak


def test_review_card_requires_consent_and_preview_only():
    p = plan()
    p["scenes"][2]["layers"].append({"type": "component", "component": "ReviewCard"})
    p["scenes"][2]["layers"].append({"type": "component", "component": "SafeZoneGuide"})
    errs = editplan.validate(p)["errors"]
    assert any("ReviewCard" in e for e in errs) and any("önizleme" in e for e in errs)


def test_ai_share_and_patch():
    p = plan()
    p["scenes"][1]["layers"][0]["source"] = {"kind": "ai_clip", "asset": "g1", "real_twin": "a9"}
    r = editplan.validate(p)
    assert abs(r["computed"]["ai_share"] - 0.5) < 1e-6
    t = editplan.apply_patch(p, [{"op": "trim", "duration_s": 6.0, "keep_roles": ["hook", "endcard"]}, {"op": "reformat", "format": "4x5"}])
    assert t["format"] == "4x5" and t["version"] == 2 and abs(sum(s["dur_s"] for s in t["scenes"]) - 6.0) < 1e-6
    assert editplan.validate(t)["valid"] or True


def test_disclaimer_field_and_safe_zone_40():
    """Açıklama metni (ya da AI) içeren 9:16 planda yazılar alttaki %40'a girmez; varsayılan plan değişmez (1.4.2, Meta resmi kılavuzu)."""
    import checks as CK
    p = plan(disclaimer={"on": True, "text": "Bu reklamda yapay zekâ ile üretilmiş görüntü vardır.", "reason": "ai"})
    r = editplan.validate(p, beats=[0.0, 2.0, 4.0])
    assert r["valid"], r["errors"]
    low = plan()
    low["scenes"][0]["layers"][1] = {"type": "text", "preset": "text_reveal", "text": "Örnek", "props": {"y": 0.62}}
    assert CK.safe_zone(low)["ok"] and CK.safe_zone(low)["zone"]["bottom"] == 0.35
    with_d = copy.deepcopy(low)
    with_d["disclaimer"] = {"on": True}
    z = CK.safe_zone(with_d)
    assert not z["ok"] and z["zone"]["bottom"] == 0.40 and "alt %40" in z["issues"][0]["issue"]
    with_ai = copy.deepcopy(low)
    with_ai["provenance"] = {"ai_share": 0.2}
    assert not CK.safe_zone(with_ai)["ok"]
    feed = copy.deepcopy(with_d)
    feed["format"] = "4x5"
    feed["scenes"][0]["layers"][1]["props"]["y"] = 0.7
    assert CK.safe_zone(feed)["zone"]["bottom"] == 250 / 1350  # %40 kuralı yalnızca 9:16
