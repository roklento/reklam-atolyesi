"""1.8.0 bileşenleri: BeforeAfter, PictureInPicture, TextMark, NumberRoll, PhoneScreen, KenBurns odağı — kayıt eşleşmesi, plan kuralları,
bileşen kaynaklarının ara dosyaları, render önbellek anahtarı, güvenli alan."""
from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess

import pytest

import checks as CK
import render as RD
import scenes as SN
import text_layout as TL
from admem import editplan as EP
from conftest import ROOT, make_active_profile

SRC = ROOT / "templates" / "remotion" / "src"
NEW = {"TextMark", "BeforeAfter", "NumberRoll", "PictureInPicture", "PhoneScreen"}
needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg yok")


def _ts_names() -> set[str]:
    names = set()
    for f in (SRC / "components").glob("*.tsx"):
        names |= set(re.findall(r'name:\s*"([A-Z][A-Za-z0-9]+)"', f.read_text(encoding="utf-8")))
    tr = (SRC / "components" / "transition.tsx").read_text(encoding="utf-8")
    names |= set(re.findall(r'\["([A-Z][A-Za-z0-9]+)",\s*"[a-zA-Z]+",\s*"#', tr))
    return names


def test_registry_matches_validator_and_pins():
    assert _ts_names() == set(EP.ALL_COMPONENTS) and len(EP.ALL_COMPONENTS) == 42 and NEW <= set(EP.ALL_COMPONENTS)
    idx = (SRC / "components" / "index.ts").read_text(encoding="utf-8")
    m = re.search(r"SOURCE_PROPS: Record<string, string\[\]> = (\{.*?\});", idx)
    assert json.loads(re.sub(r"(\w+):", r'"\1":', m.group(1))) == EP.SOURCE_PROPS
    assert '"PictureInPicture"]);' in idx  # sarmalayıcı
    pkg = json.loads((ROOT / "templates" / "remotion" / "package.json").read_text(encoding="utf-8"))["dependencies"]
    assert pkg["@remotion/rough-notation"] == pkg["remotion"] == "4.0.532"
    lock = json.loads((ROOT / "templates" / "remotion" / "package-lock.json").read_text(encoding="utf-8"))["packages"]
    assert lock["node_modules/@remotion/rough-notation"]["version"] == "4.0.532" and lock["node_modules/roughjs"]["license"] == "MIT"
    cam = (SRC / "components" / "camera.tsx").read_text(encoding="utf-8")
    assert 'name: "KenBurns", category: "camera", version: "1.1.0"' in cam and "settleFrames" in cam and "focus" in cam


def _plan(layers, dur=6, status="draft", extra_scenes=()):
    scenes = [{"id": "s1", "role": "proof", "start_s": 0, "dur_s": dur, "audio": {"mode": "none", "decision_id": "d1"}, "layers": layers}]
    scenes += list(extra_scenes)
    total = sum(s["dur_s"] for s in scenes)
    return {"campaign": "k", "cycle_id": 1, "concept": "A", "hook": "h", "format": "9x16", "purpose": "production", "status": status,
            "version": 1, "style_snapshot_sha256": "x", "duration_s": total, "fps": 30, "style": "s.json", "scenes": scenes}


FOOT = lambda a: {"kind": "footage", "asset": a, "in_s": 0, "out_s": 3}  # noqa: E731
BA = lambda **p: {"type": "component", "component": "BeforeAfter", "props": {"before": FOOT("a1"), "after": FOOT("a2"), "category": "general", **p}}  # noqa: E731
CTX = {"concept_proof": "before_after", "regulated_sector": None, "claims": [{"code": "c1", "text": "1.250 adet satıldı", "documented": True},
                                                                            {"claim": "Belgesiz 30", "needs_document": True}], "product_price": 100}


def _errs(plan, ctx=CTX):
    return EP.validate(plan, context=ctx)


def test_before_after_rules():
    assert _errs(_plan([BA()]))["valid"]
    r = _errs(_plan([BA(after={"kind": "ai_clip", "asset": "g1"})]))
    assert any("AI kaynak olamaz" in e for e in r["errors"]) and any("gerçek çekim olmalı" in e for e in r["errors"])
    assert any("category" in e for e in _errs(_plan([BA(category=None)]))["errors"])
    assert any("cilt beyazlatma" in e for e in _errs(_plan([BA(category="skin_whitening")]))["errors"])
    w = _errs(_plan([BA(category="cosmetic")]))
    assert w["valid"] and any("18+" in x for x in w["warnings"])
    assert any("before_after seçilmiş" in e for e in _errs(_plan([BA()]), {**CTX, "concept_proof": "demo"})["errors"])
    assert any("sağlık hizmetinde" in e for e in _errs(_plan([BA()]), {**CTX, "regulated_sector": "health"})["errors"])
    local = EP.validate(_plan([BA()]))  # bağlamsız yol: uyarı, karar sunucuda
    assert local["valid"] and any("bu yolda denetlenmedi" in x for x in local["warnings"])
    r = _errs(_plan([BA(before={"kind": "footage", "path": "profiles/p/competitors/x.mp4"})]))
    assert any("rakip" in e for e in r["errors"])


def _nr(**p):
    return {"type": "component", "component": "NumberRoll", "props": {"value": 1250, **p}}


def test_number_roll_needs_price_or_proven_claim():
    assert any("ya fiyat" in e for e in _errs(_plan([_nr()]))["errors"])
    assert any("para birimi" in e for e in _errs(_plan([_nr(kind="price")]))["errors"])
    assert _errs(_plan([_nr(kind="price", value=100, currency="TRY")]))["valid"]
    assert any("farklı" in x for x in _errs(_plan([_nr(kind="price", value=90, currency="TRY")]))["warnings"])
    ok = _errs(_plan([_nr(kind="claim", claimIndex=0)]))
    assert ok["valid"] and not any("geçmiyor" in x for x in ok["warnings"])
    assert _errs(_plan([_nr(kind="claim", claimRef="c1")]))["valid"]
    assert any("listesinde yok" in e for e in _errs(_plan([_nr(kind="claim", claimIndex=5)]))["errors"])
    assert any("belge istiyor" in e for e in _errs(_plan([_nr(kind="claim", claimIndex=1, value=30)]))["errors"])
    assert any("geçmiyor" in x for x in _errs(_plan([_nr(kind="claim", claimIndex=0, value=999)]))["warnings"])


def test_phone_screen_personal_data_and_text_mark_budget():
    ps = lambda **p: {"type": "component", "component": "PhoneScreen", "props": {"screen": FOOT("a3"), **p}}  # noqa: E731
    assert any("kapıda sorulmadı" in x for x in _errs(_plan([ps()]))["warnings"])
    assert any("kapıda sorulmadı" in e for e in _errs(_plan([ps()], status="ready"))["errors"])
    assert any("blurRegions boş" in e for e in _errs(_plan([ps(personalData="blurred")]))["errors"])
    assert _errs(_plan([ps(personalData="blurred", blurRegions=[{"x": 0, "y": 0, "w": 1, "h": 0.1}])]))["valid"]
    tm = lambda t="Işık her köşede İYİ", m="iyi": {"type": "component", "component": "TextMark", "props": {"text": t, "mark": m}}  # noqa: E731
    assert _errs(_plan([tm(), tm()]))["valid"]  # Türkçe katlama: İYİ ↔ iyi
    assert any("en fazla 2" in e for e in _errs(_plan([tm(), tm(), tm()]))["errors"])
    assert any("metinde yok" in e for e in _errs(_plan([tm(m="başka")]))["errors"])


def test_pip_inset_speaker_counts_as_speaking_and_overlap_flagged():
    pip = {"type": "component", "component": "PictureInPicture",
           "props": {"inset": {**FOOT("a4"), "speaking_person": True, "audio": True}, "corner": "bottom_left"}}
    r = _errs(_plan([{"type": "video", "source": FOOT("a1")}, pip]))
    assert any("konuşan kişi" in e for e in r["errors"])  # ses 'none' iken
    box = TL.pip_extent(pip, "9x16")
    lay = json.loads((SRC / "layout.json").read_text(encoding="utf-8"))["pip_box"]["9x16"]
    assert box["y1"] == pytest.approx(lay["bottom"]) and box["x0"] == pytest.approx(lay["side"])
    plan = _plan([{"type": "video", "source": FOOT("a1")}, pip,
                  {"type": "component", "component": "NumberRoll", "props": {"value": 5, "kind": "price", "currency": "TRY", "y": 0.55}}])
    issues = CK.safe_zone(plan)["issues"]
    assert any(i.get("component") == "PictureInPicture" and "çakışıyor" in i["issue"] for i in issues)
    plan["scenes"][0]["layers"][1]["props"]["corner"] = "top_right"
    assert not any(i.get("component") == "PictureInPicture" for i in CK.safe_zone(plan)["issues"])


def test_render_key_maps_component_sources(tmp_path):
    a, b = tmp_path / "x.mp4", tmp_path / "y.mp4"
    a.write_bytes(b"1")
    b.write_bytes(b"2")
    plan = _plan([BA()])
    h = RD.intermediate_hashes(plan, {"scenes": {"s1": {"0.before": {"path": str(a)}, "0.after": {"path": str(b)}}}})
    assert set(h["s1"]) == {"a1", "a2"}


def _clip(path, tone, dur=3.0, audio=False):
    args = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x{tone:02x}{tone:02x}{tone:02x}:s=320x180:r=25:d={dur}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}", "-c:a", "aac", "-shortest"]
    subprocess.run(args + ["-pix_fmt", "yuv420p", "-c:v", "libx264", str(path)], check=True)
    return str(path)


@needs_ffmpeg
def test_scenes_builds_component_sources_without_color_match(tmp_path):
    assets = {k: {"cfr_sdr": _clip(tmp_path / f"{k}.mp4", t, audio=(k == "sp"))} for k, t in (("bg", 120), ("b", 60), ("a", 180), ("sp", 140))}
    layers = [{"type": "video", "source": {"kind": "footage", "asset": "bg", "in_s": 0, "out_s": 2}},
              {"type": "component", "component": "PictureInPicture",
               "props": {"inset": {"kind": "footage", "asset": "sp", "in_s": 0, "out_s": 2, "audio": True, "speaking_person": True}}}]
    plan = _plan(layers, dur=2)
    plan["scenes"][0]["audio"]["mode"] = "original"
    plan["scenes"].append({"id": "s2", "role": "proof", "start_s": 2, "dur_s": 2, "audio": {"mode": "none"},
                           "layers": [{"type": "component", "component": "BeforeAfter",
                                       "props": {"before": {"kind": "footage", "asset": "b", "in_s": 0, "out_s": 2},
                                                 "after": {"kind": "footage", "asset": "a", "in_s": 0, "out_s": 2}, "category": "general"}}]})
    plan["duration_s"] = 4
    res = SN.build(plan, assets, tmp_path / "out", "proxy", {"grade": {}}, None, fast=True)
    assert set(res["scenes"]["s1"]) == {"0", "1.inset"} and set(res["scenes"]["s2"]) == {"0.before", "0.after"}
    assert "1.inset" in res["audio_segments"]["s1"]  # sahne sesi konuşan kişinin kaynağından
    cm = json.loads((tmp_path / "out" / "color_match.json").read_text(encoding="utf-8"))
    assert set(cm["layers"]) == {"s1:0"}  # önce/sonra ve köşe kaynakları eşitlenmez


def test_docs_cover_new_components():
    ref = (ROOT / "skills" / "ref-remotion-components" / "SKILL.md").read_text(encoding="utf-8")
    assert all(n in ref for n in NEW) and "settle_s" in ref and "personalData" in ref
    assert "BeforeAfter" in (ROOT / "skills" / "ref-legal-tr-meta" / "SKILL.md").read_text(encoding="utf-8")
    assert "claimRef" in (ROOT / "skills" / "compose" / "SKILL.md").read_text(encoding="utf-8")


def test_server_context_from_concept_and_product(store):
    a = make_active_profile(store)
    pid, prod = a["profile"]["id"], a["product"]["id"]
    c = store.campaign_create(pid, prod, "K")
    cid, cyid = c["campaign"]["id"], c["cycle"]["id"]
    with store.tx():
        store.ex("""INSERT INTO concepts(campaign_id,cycle_id,code,name,source,features_json,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?)""", (cid, cyid, "A", "Konsept A", "general", json.dumps({"proof": "before_after"}), "t", "t"))
    ctx = store._plan_rules_context(pid, cid, {"concept": "A"})
    assert ctx["concept_proof"] == "before_after" and ctx["product_price"] == 100 and ctx["claims"][0]["code"] == "c1"
    p = _plan([BA()])
    r = store.edit_plan_validate(pid, cid, plan=copy.deepcopy(p))
    assert not any("before_after seçilmiş" in e or "sağlık" in e for e in r["errors"]), r["errors"]
    with store.tx():
        store.ex("UPDATE products SET service_json=? WHERE id=?", (json.dumps({"regulated_sector": "health"}), prod))
    r = store.edit_plan_validate(pid, cid, plan=copy.deepcopy(p))
    assert any("sağlık hizmetinde" in e for e in r["errors"])


def test_old_project_fallbacks_match_layout():
    """init --force-library components/ dışını tazelemez: media.tsx eski layout.json'da pip_box yoksa aynı değerleri kullanır ve
    eski sahne şablonunun geçirdiği ham kaynak nesnesini şema kabul eder (çökme yerine açık yer tutucu)."""
    comp = ROOT / "templates" / "remotion" / "src" / "components"
    media = (comp / "media.tsx").read_text(encoding="utf-8")
    layout = json.loads((ROOT / "templates" / "remotion" / "src" / "layout.json").read_text(encoding="utf-8"))
    for fmt, box in layout["pip_box"].items():
        m = re.search(r'"%s": \{ top: ([\d.]+), bottom: ([\d.]+), side: ([\d.]+) \}' % re.escape(fmt), media)
        assert m and tuple(map(float, m.groups())) == (box["top"], box["bottom"], box["side"]), fmt
    assert "KAYNAK ÇÖZÜLEMEDİ" in media
    assert "inset: zSource" in media and "screen: zSource" in media
    assert "before: zSource, after: zSource" in (comp / "compare.tsx").read_text(encoding="utf-8")
