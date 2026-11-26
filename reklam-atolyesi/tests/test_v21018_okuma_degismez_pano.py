"""2.10.18: yazının okuma süresi uzunluğa göre; AI klipte ürünün değişmezleri ve sabit ilk kare; canlı ilerleme panosu (yalnızca okur).

Sentetik plan ve sentetik veritabanı; ağ yok, ücretli araç çağrılmaz.
"""
from __future__ import annotations

import copy
import json
import sqlite3
import subprocess
import sys

from admem import editplan as EP
from admem.util import now_iso
from conftest import ROOT, make_active_profile

for sub in ("lib", "qc", "analytics"):
    sys.path.insert(0, str(ROOT / "scripts" / sub))
import checks as CK  # noqa: E402
import pano as PN  # noqa: E402
import sade_dil as SD  # noqa: E402

PANO = ROOT / "scripts" / "analytics" / "pano.py"
STYLE = json.loads((ROOT / "templates" / "style.json").read_text(encoding="utf-8"))


def test_reading_seconds_grows_with_length_and_keeps_floor():
    assert EP.reading_seconds("") == EP.READ_MIN_S
    assert EP.reading_seconds("Yeni") == 1.5  # kısa yazıda alt sınır değişmedi
    long = "Kapıda ödeme ve ücretsiz kargo iki iş günü içinde"
    assert EP.reading_seconds(long) > 3.0
    assert EP.reading_seconds("a b") == EP.reading_seconds("ab")  # boşluklar sayılmaz
    assert EP.layer_text({"type": "component", "props": {"price": 899, "currency": "TL", "label": "Sınırlı", "y": 0.7}}) == "Sınırlı TL 899"


def _plan(text: str, dur: float = 2, status: str = "ready") -> dict:
    return {"campaign": "k", "cycle_id": 1, "concept": "A", "hook": "h1", "format": "9x16", "purpose": "production", "status": status,
            "version": 1, "style_snapshot_sha256": "x", "duration_s": dur + 4, "fps": 30, "style": "styles/v1.json",
            "scenes": [
                {"id": "s1", "role": "hook", "start_s": 0, "dur_s": dur, "audio": {"mode": "none", "decision_id": "d1"},
                 "layers": [{"type": "video", "source": {"kind": "footage", "asset": "a1"}},
                            {"type": "text", "preset": "text_reveal", "text": text, "anchor": "safe_top"}]},
                {"id": "s2", "role": "reveal", "start_s": dur, "dur_s": 2, "audio": {"mode": "none", "decision_id": "d2"},
                 "layers": [{"type": "video", "source": {"kind": "footage", "asset": "a2"}}]},
                {"id": "s3", "role": "endcard", "start_s": dur + 2, "dur_s": 2, "audio": {"mode": "none", "decision_id": "d3"},
                 "layers": [{"type": "component", "component": "EndCard", "props": {"brand": "Marka A", "cta": "Al"}}]}]}


def _reading_warn(r: dict) -> list[str]:
    return [w for w in r["warnings"] if "okunması için" in w]


def test_editplan_warns_when_long_text_is_too_short_on_screen():
    long = "Kapıda ödeme ve ücretsiz kargo iki iş günü içinde"
    assert _reading_warn(EP.validate(_plan(long, dur=2)))
    assert not _reading_warn(EP.validate(_plan(long, dur=4)))
    assert not _reading_warn(EP.validate(_plan("Yeni", dur=2)))


def test_qc_safe_zone_uses_same_reading_rule():
    long = "Kapıda ödeme ve ücretsiz kargo iki iş günü içinde"
    p = {"format": "9x16", "captions": {"on": False}, "scenes": [
        {"id": "a", "role": "hook", "start_s": 0, "dur_s": 2, "layers": [{"type": "text", "text": long}]}]}
    r = CK.safe_zone(p, STYLE)
    assert any("bu uzunluktaki yazı" in i["issue"] for i in r["issues"])
    p["scenes"][0]["dur_s"] = 4
    assert not any("bu uzunluktaki yazı" in i["issue"] for i in CK.safe_zone(p, STYLE)["issues"])


def test_ai_clip_needs_invariants_and_first_frame_when_ready():
    p = _plan("Yeni")
    p["scenes"][1]["layers"][0]["source"] = {"kind": "ai_clip", "asset": "g1", "real_twin": "a9"}
    w = EP.validate(p)["warnings"]
    assert any("değişmezleri" in x for x in w) and any("first_frame" in x for x in w)
    p["scenes"][1]["layers"][0]["source"].update(invariants=["silüet", "kapak rengi"], first_frame="photos/onayli.png",
                                                  last_frame="photos/onayli.png")
    r = EP.validate(p)
    assert r["valid"], r["errors"]
    assert not any("değişmezleri" in x or "first_frame" in x for x in r["warnings"])
    d = copy.deepcopy(p)
    d["status"] = "draft"
    d["scenes"][1]["layers"][0]["source"] = {"kind": "ai_image", "asset": "g2"}
    assert not any("değişmezleri" in x for x in EP.validate(d)["warnings"])  # taslakta uyarı yok
    bad = copy.deepcopy(p)
    bad["scenes"][1]["layers"][0]["source"]["invariants"] = [""]
    assert not EP.validate(bad)["valid"]  # boş madde şemaya aykırı


def test_pano_without_campaign(store, data_dir):
    a = make_active_profile(store)
    d = PN.collect(data_dir, a["profile"]["id"])
    assert d["campaign"] is None
    page = PN.render_html(d, now="01.01.2026 10:00:00")
    assert "Henüz etkin bir kampanya yok" in page and 'http-equiv="refresh"' in page


def test_pano_shows_stages_scenes_generations_and_is_read_only(store, data_dir):
    a = make_active_profile(store)
    pid = a["profile"]["id"]
    r = store.campaign_create(pid, a["product"]["id"], "Kış kampanyası", goal="satış", result_type="purchase")
    cid, cyid = r["campaign"]["id"], r["cycle"]["id"]
    plan = _plan("Yeni")
    store.ex("""INSERT INTO edit_plans(campaign_id, cycle_id, format, purpose, status, version, plan_json, sha256, created_at)
                VALUES (?,?,?,?,?,?,?,?,?)""", (cid, cyid, "9x16", "production", "draft", 2, json.dumps(plan), "x", now_iso()))
    store.ex("""INSERT INTO generations(profile_id, campaign_id, cycle_id, provider, model, kind, tool_name, params_json, params_hash,
                estimate_credits, cost_credits, status, accepted, updated_at, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
             (pid, cid, cyid, "p", "m1", "video", "t", "{}", "h", 12.0, 11.5, "completed", 1, now_iso(), now_iso()))
    store.close()
    db = data_dir / "db" / "ad-memory.sqlite"
    before = db.read_bytes()
    d = PN.collect(data_dir, pid)
    assert d["campaign"]["id"] == cid and d["stages"][0]["state"] == "running" and d["spent_credits"] == 11.5
    assert [s["role"] for s in d["scenes"]] == ["açılış", "ürünün görünüşü", "kapanış"] and d["scenes"][0]["yazi"] == "Yeni"
    page = PN.render_html(d)
    assert "Kış kampanyası" in page and "açılış" in page and "11.5" in page
    out = data_dir / "pano.html"
    res = subprocess.run([sys.executable, str(PANO), "--data-dir", str(data_dir), "--profile-id", str(pid), "--out", str(out)],
                         capture_output=True, text=True, encoding="utf-8")
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout)["pano"] == str(out) and out.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert db.read_bytes() == before  # pano veritabanına yazmaz
    try:
        con = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
        assert con.execute("SELECT count(*) FROM generations").fetchone()[0] == 1
    finally:
        con.close()


def test_pano_user_facing_words_are_plain():
    texts = [*PN.ROLE_TR.values(), *PN.SOURCE_TR.values(), *PN.GEN_STATUS_TR.values(), *PN.STAGE_STATE_TR.values(),
             "Henüz etkin bir kampanya yok. Kampanya başlayınca bu sayfa dolacak.",
             "Senin onayını bekliyor. Sohbete dönüp onaylayabilir ya da değişiklik isteyebilirsin.",
             "Henüz ücretli bir üretim yok. Her ücretli üretimden önce fiyatı sana sorulur."]
    for t in texts:
        assert SD.scan_text(t) == [], t


def test_wiring_skills_manifest():
    materials = (ROOT / "skills" / "materials" / "SKILL.md").read_text(encoding="utf-8")
    recipes = (ROOT / "skills" / "ref-production-recipes" / "SKILL.md").read_text(encoding="utf-8")
    qc = (ROOT / "skills" / "qc" / "SKILL.md").read_text(encoding="utf-8")
    assert "değişmez" in materials and "İlk ve son kare" in materials
    assert "source.invariants" in recipes and "scripts/analytics/pano.py" in recipes
    assert "saniyede 15 harf" in qc
    man = (ROOT / "scripts" / "setup" / "manifest.py").read_text(encoding="utf-8")
    assert "scripts/analytics/pano.py" in man
