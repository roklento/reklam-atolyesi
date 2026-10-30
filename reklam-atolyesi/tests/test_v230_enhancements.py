"""2.3.0: Advantage+ kreatif iyileştirmeleri — yayın kaydında durum, durum uyarıları, koçluk hükmünde "Meta iyileştirmesi açık" kaydı,
§7'de Andromeda 2026 / iyileştirme / ürün gezinme satırları ve yayın paketi talimatı."""
from __future__ import annotations

import pytest

import bayes as B
import coach as CO
import report as RP
from admem import db as DB
from admem.s_stage import normalize_enhancements
from admem.util import AdMemoryError
from conftest import ROOT, out_file
from test_analytics import build_campaign
from test_store_stage import advance_to, new_campaign

KEY = "MRK_K1_A_video_15_h1_novo_real_c1_r1"


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def at_launch(s):
    pid, cid, cyid = new_campaign(s)
    advance_to(s, pid, cid, cyid, "S14")
    f = s.campaign_dir(pid, cid) / "out" / f"{KEY}_916.mp4"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"\x00" * 64)
    cr = s.creative_register(pid, cid, cyid, str(f), "test")
    s.creative_set_qc(pid, cid, [cr["id"]], "passed", "qc.md")
    rl = s.q1("SELECT risk_limits_json FROM cycles WHERE id=?", (cyid,))["risk_limits_json"]
    rl["mapping"] = {KEY: {"amount": 500}}
    s.cycle_set(pid, cyid, risk_limits_json=rl)
    s.stage_start(pid, "S14", cid, cyid)
    run = s.stage_complete(pid, "S14", [{"path": out_file(s, pid, cid, "paket.md")}], "paket", cid, cyid)["stage_run"]
    s.gate_approve(pid, run["id"], run["output_version"], "paket onaylı", cycle_id=cyid)
    return pid, cid, cyid, run


def launch(s, pid, cid, cyid, run, **kw):
    return s.launch_confirm(pid, cid, cyid, run["id"], run["output_version"], [{"meta_ad_id": "111", "creative_key": KEY}],
                            "2026-03-05T00:00:00+03:00", "yayına aldım", **kw)


def test_migration_adds_column(store):
    assert DB.current_version(store.conn) == DB.SCHEMA_VERSION >= 8
    cols = {r[1] for r in store.conn.execute("PRAGMA table_info(cycles)")}
    assert "enhancements_json" in cols


def test_normalize_validates():
    assert normalize_enhancements(None) == {"checked": False, "source": None, "on": [], "off": []}
    ok = normalize_enhancements({"source": "advanced_preview", "on": [{"name": "Müzik", "kind": "audio"}], "off": ["Metin iyileştirmeleri"]})
    assert ok["checked"] and ok["on"] == [{"name": "Müzik", "kind": "audio"}] and ok["off"] == ["Metin iyileştirmeleri"]
    for bad in ({"on": [{"name": "X", "kind": "bilinmeyen"}]}, {"on": [{"kind": "text"}]}, {"source": "tahmin"},
                {"checked": False, "on": [{"name": "X", "kind": "text"}]}, "hepsi kapalı"):
        with pytest.raises(AdMemoryError):
            normalize_enhancements(bad)
    with pytest.raises(AdMemoryError):
        normalize_enhancements({"on": [{"name": "X", "kind": "text", "creative_keys": ["YOK"]}]}, {KEY})


def test_launch_without_check_records_and_warns(store):
    pid, cid, cyid, run = at_launch(store)
    res = launch(store, pid, cid, cyid, run)
    assert res["enhancements"]["checked"] is False and res["warnings"] and "kontrol edilmedi" in res["warnings"][0]
    assert store.q1("SELECT enhancements_json FROM cycles WHERE id=?", (cyid,))["enhancements_json"]["checked"] is False
    st = store.campaign_status(pid, cid)
    assert any("kontrol edilmedi" in w for c in st["campaigns"] for w in c["warnings"])


def test_launch_all_off_is_silent_and_on_warns(store):
    pid, cid, cyid, run = at_launch(store)
    res = launch(store, pid, cid, cyid, run, enhancements={"source": "advanced_preview", "on": [], "off": ["Müzik", "Ürün gezinme"]})
    assert res["warnings"] == [] and res["enhancements"]["off"] == ["Müzik", "Ürün gezinme"]
    # yayından sonra açık bırakıldığı fark edilirse cycle_set ile kayıt; durum ekranı uyarır
    store.cycle_set(pid, cyid, enhancements_json={"source": "user", "on": [{"name": "Ürün gezinme", "kind": "destination", "creative_keys": [KEY]}]})
    st = store.campaign_status(pid, cid)
    assert any("Ürün gezinme (destination)" in w for c in st["campaigns"] for w in c["warnings"])
    with pytest.raises(AdMemoryError):
        store.cycle_set(pid, cyid, enhancements_json={"on": [{"name": "X", "kind": "text", "creative_keys": ["BAŞKA"]}]})


def test_launch_rejects_unknown_key_in_enhancements(store):
    pid, cid, cyid, run = at_launch(store)
    with pytest.raises(AdMemoryError):
        launch(store, pid, cid, cyid, run, enhancements={"on": [{"name": "Metin", "kind": "text", "creative_keys": ["YEDEK"]}]})
    assert store.q1("SELECT launched_at FROM cycles WHERE id=?", (cyid,))["launched_at"] is None  # reddedilen kayıt yarım kalmaz


def test_verdict_language_enhanced():
    assert B.verdict_language(True, "creative_test") == "kanıt"
    assert B.verdict_language(True, "creative_test", True) == "kanıt · Meta iyileştirmesi açık"
    assert B.verdict_language(False, "bootstrap", True).endswith("Meta'nın dağıtımı altında · Meta iyileştirmesi açık")


def test_coach_marks_enhanced_concepts(store, tmp_path):
    pid, cid, cyid = build_campaign(store)
    base = CO.analyze(store.decision_input_snapshot(pid, cid, cyid)["path"])
    assert not base["enhancements"]["recorded"] and not any("iyileştirme" in d["label"] for d in base["decisions"])
    key_a = "MRK_K_A_video_15_h1_novo_real_c1_r1"
    store.cycle_set(pid, cyid, enhancements_json={"source": "advanced_preview", "on": [{"name": "Metin varyasyonları", "kind": "text", "creative_keys": [key_a]}]})
    an = CO.analyze(store.decision_input_snapshot(pid, cid, cyid)["path"])
    dec = {d["concept"]: d for d in an["decisions"]}
    assert "Meta iyileştirmesi açık" in dec["A"]["label"] and "iyileştirme" not in dec["B"]["label"]
    assert an["enhancements"]["concepts"] == ["A"] and "iyileştirme" not in an["verdict_qualifier"]
    store.cycle_set(pid, cyid, enhancements_json={"source": "user", "on": [{"name": "Müzik", "kind": "audio"}]})
    an2 = CO.analyze(store.decision_input_snapshot(pid, cid, cyid)["path"])
    assert an2["enhancements"]["all"] and "Meta iyileştirmesi açık" in an2["verdict_qualifier"]
    snap = store.decision_input_snapshot(pid, cid, cyid)
    md = RP.build(an2, CO.read_json(snap["path"]), {}, None, None, None)
    assert "Açık kalan Meta iyileştirmeleri (Müzik; tüm reklamlarda)" in md and not RP.causal_terms(md)


def test_docs_and_sources():
    legal = read("skills/ref-legal-tr-meta/SKILL.md").split("## 7. Meta platform kuralları", 1)[1].split("## 8.", 1)[0]
    assert "2026/10/28/ml-applications/meta-andromeda-next-gen-ads-retrieval-gpu-co-design" in legal
    assert "1082295769403815" in legal and "ürün gezinme" in legal.lower()
    assert "koçluk eşiğine, tahmine ya da kullanıcıya vaade çevrilmez" in legal
    pack = read("skills/launch-pack/SKILL.md")
    assert "5a. **Advantage+ kreatif iyileştirmeleri" in pack and "enhancements" in pack and "gelişmiş önizleme" in pack
    assert "Advantage+ kreatif iyileştirmeleri" in read("templates/reports/yayin-paketi.md")
    assert "Meta iyileştirmesi açık" in read("skills/coach/SKILL.md")
    assert "enhancements" in read("servers/ad_memory/server.py")
