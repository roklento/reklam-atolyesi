"""2.10.2: bağımsız sürüm denetiminin bulduğu açıklar. Ölçülmeyen değer sonuç sayılmaz, eski denetim yeni kayda taşınmaz,
çağıranın beyanı sunucu kaydının yerine geçmez."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from admem.util import AdMemoryError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
import defter_oku as DO  # noqa: E402
import etki_ozeti as EO  # noqa: E402


# ----------------------------------------------------------------------------- huni: pay ve payda aynı satırlardan
def test_funnel_rate_uses_rows_where_both_counts_were_measured():
    import coach
    fs = coach.funnel_steps([{"link_clicks": 1000, "landing_page_views": 800},
                             {"link_clicks": 1000, "landing_page_views": None}])
    st = fs["steps"][0]
    assert st["rate"] == pytest.approx(0.8)
    assert st["denominator_count"] == 1000 and st["coverage"] == pytest.approx(0.5)


def test_funnel_rate_withheld_when_event_measured_in_too_few_rows():
    import coach
    fs = coach.funnel_steps([{"link_clicks": 300, "landing_page_views": 250},
                             {"link_clicks": 700, "landing_page_views": None}])
    st = fs["steps"][0]
    assert st.get("rate") is None and st["status"] == "veri_yetersiz" and "%30" in st["msg"]


def test_funnel_full_coverage_unchanged():
    import coach
    fs = coach.funnel_steps([{"link_clicks": 500, "landing_page_views": 400}, {"link_clicks": 500, "landing_page_views": 300}])
    st = fs["steps"][0]
    assert st["rate"] == pytest.approx(0.7) and st["coverage"] == pytest.approx(1.0)


def test_paired_totals_ignores_rows_without_denominator():
    import coach
    assert coach.paired_totals([{"a": 5, "b": None}, {"a": 3, "b": 10}], "a", "b") == (3.0, 10.0, 1.0)
    assert coach.paired_totals([{"a": None, "b": 10}], "a", "b") == (None, None, None)


# ----------------------------------------------------------------------------- taslak kapısı
def test_draft_check_not_reusable_under_another_document_name(store):
    from test_v250_drafts import campaign, write
    pid, cid, cyid = campaign(store)
    store.stage_start(pid, "S01", cid, cyid)
    p = Path(write(store, pid, cid, "notlar.md", "# Notlar\n\nŞablona bağlı olmayan, uzunca bir not metni.\n"))
    assert store.draft_check(pid, "S01", str(p), cid, cyid)["verdict"] == "pass"
    q = p.with_name("c1-brief.md")
    q.write_bytes(p.read_bytes())
    with pytest.raises(AdMemoryError, match="başka bir adla"):
        store.stage_complete(pid, "S01", [{"path": str(q)}], "brief", cid, cyid)


def test_draft_check_rechecked_against_current_record(store):
    from test_v250_drafts import campaign
    import draft_docs
    pid, cid, cyid = campaign(store)
    store.stage_start(pid, "S01", cid, cyid)
    d = draft_docs.write_stage_doc(store, pid, "S01", cid, cyid)
    assert d["check"]["verdict"] == "pass"
    store.cycle_set(pid, cyid, adset_budget_daily=500)
    with pytest.raises(AdMemoryError, match="kayıt değişti"):
        store.stage_complete(pid, "S01", [{"path": d["path"]}], "brief", cid, cyid)
    d2 = draft_docs.write_stage_doc(store, pid, "S01", cid, cyid)  # güncel kayıttan yeniden yazılır → tamamlanır
    assert d2["check"]["verdict"] == "pass"
    store.stage_complete(pid, "S01", [{"path": d2["path"]}], "brief", cid, cyid)


# ----------------------------------------------------------------------------- okunuş sözlüğü
@pytest.mark.parametrize("text,expected", [
    ("WİFİ bağlantısı", "vayfay bağlantısı"),
    ("WIFI bağlantısı", "vayfay bağlantısı"),
    ("Wifi'yi aç", "vayfayyi aç"),
])
def test_lexicon_turkish_and_english_uppercase(text, expected):
    import tts_worker as T
    out, cmap, _ = T.apply_lexicon(text, [{"written": "wifi", "spoken": "vayfay"}])
    assert out == expected and len(cmap) == len(out)


def test_lexicon_turkish_dotted_and_dotless_entries():
    import tts_worker as T
    lex = [{"written": "Işık", "spoken": "ışık-okunuş"}, {"written": "İnce", "spoken": "ince-okunuş"}]
    out, cmap, applied = T.apply_lexicon("IŞIK ve İNCE", lex)
    assert out == "ışık-okunuş ve ince-okunuş" and len(applied) == 2 and len(cmap) == len(out)


# ----------------------------------------------------------------------------- efekt öz denetimi
def test_sfx_review_unmeasured_without_sfx_stem():
    import sfx_review
    rep = {"stems": {}, "sfx_placed": [{"sfx": "x", "at_s": 1, "start_s": 1, "anchor": "arrive", "role": "click",
                                        "target_peak_db": -14, "measure": {"dur_s": 0.1}}]}
    r = sfx_review.review(rep, {"duration_s": 5, "scenes": []})
    assert r["pass"] is False and r["unmeasured"] == ["sync", "level"]
    assert any(p["axis"] == "olculemedi" for p in r["worst"])
    assert all("okunamadı" not in x["why"] for x in r["listen"])


# ----------------------------------------------------------------------------- playbook adayı
def _playbook_setup(store, structure="creative_test", enhancements=None):
    from test_analytics import build_campaign
    pid, cid, cyid = build_campaign(store)
    store.ex("UPDATE cycles SET test_start='2026-04-01T00:00:00Z' WHERE id=?", (cyid,))
    prod = store.q1("SELECT product_id FROM campaigns WHERE id=?", (cid,))["product_id"]
    other = store.campaign_create(pid, prod, "Keşif", result_type="purchase")
    h = store.hypothesis_add(pid, "Hipotez", "ctr_link", cid, cyid, is_primary=True,
                             pre_registration={"arm_a": "A", "arm_b": "B", "metric": "ctr_link", "direction": "A>B", "comparison_ids": [1, 2]})
    store.ex("UPDATE cycles SET structure_detected=? WHERE id=?", (structure, cyid))
    if enhancements is not None:
        store.cycle_set(pid, cyid, enhancements_json=enhancements)
    ev = {"hypothesis_id": h["id"], "discovery_cycle_id": other["cycle"]["id"], "validation_cycle_id": cyid,
          "discovery_same_direction": True, "p_superiority_validation_only": 0.97, "sufficient_data": True,
          "structure_verified": True, "bootstrap": False,
          "lower_funnel": {"metric": "cvr", "same_direction": True, "sufficient": True, "preselected": True}}
    return pid, ev


def test_playbook_refuses_when_enhancements_were_on(store):
    pid, ev = _playbook_setup(store, enhancements={"checked": True, "source": "user", "on": [{"name": "Müzik", "kind": "audio"}]})
    with pytest.raises(AdMemoryError, match="iyileştirmeleri açıktı"):
        store.playbook_propose(pid, "Kural", ev)


def test_playbook_refuses_when_enhancements_unchecked(store):
    pid, ev = _playbook_setup(store, enhancements={"checked": False})
    with pytest.raises(AdMemoryError, match="kontrol edilmemiş"):
        store.playbook_propose(pid, "Kural", ev)


def test_playbook_refuses_recorded_unverified_structure_despite_caller_claim(store):
    pid, ev = _playbook_setup(store, structure="deviated")
    with pytest.raises(AdMemoryError, match="deviated"):
        store.playbook_propose(pid, "Kural", ev)


def test_playbook_accepts_clean_controlled_cycle(store):
    pid, ev = _playbook_setup(store, enhancements={"checked": True, "source": "user", "on": [], "off": ["Müzik"]})
    assert store.playbook_propose(pid, "Kural", ev)["status"] == "proposed"


# ----------------------------------------------------------------------------- hata defteri araçları
def _ledger(v, days, n, stages=None):
    return {"plugin_version": v, "period_days": days, "stages": stages or {},
            "imzalar": [{"asama": "S01", "sinyal": "arac_hatasi", "kod": "k", "hucre": "P1.U1", "n": n}]}


def test_ledger_versions_compared_per_day_not_per_ledger():
    ds = [_ledger("1.0.0", 7, 7), _ledger("1.1.0", 30, 30)]
    assert DO.version_changes(DO.signatures(ds), DO.field_indicators(ds)) == []


def test_ledger_versions_compared_per_stage_run_when_known():
    ds = [_ledger("1.0.0", 30, 4, {"S01": {"completed": 4}}), _ledger("1.1.0", 30, 20, {"S01": {"completed": 20}})]
    assert DO.version_changes(DO.signatures(ds), DO.field_indicators(ds)) == []
    ds[1]["imzalar"][0]["n"] = 60
    ch = DO.version_changes(DO.signatures(ds), DO.field_indicators(ds))
    assert ch and ch[0][0] == "kötüleşti" and "S01 aşaması başına" in ch[0][6]


def test_ledger_coverage_requires_matching_error_code():
    cases = {"s01-ornek": {"product": "P1", "user": "U1"}, "s01-kodlu": {"product": "P1", "user": "U1", "kodlar": ["k"]}}
    assert DO.covering_cases(("S01", "taslak_son_tur_kaldi", "baska_kod", "P1.U1"), cases) == []
    assert DO.related_cases(("S01", "taslak_son_tur_kaldi", "baska_kod", "P1.U1"), cases) == ["s01-ornek", "s01-kodlu"]
    assert DO.covering_cases(("S01", "taslak_son_tur_kaldi", "k", "P1.U1"), cases) == ["s01-kodlu"]
    assert DO.covering_cases(("S01", "duzeltme_istendi", "-", "P1.U1"), cases) == ["s01-ornek", "s01-kodlu"]


# ----------------------------------------------------------------------------- etki özeti
def test_impact_summary_lists_components_without_eval_evidence():
    text = """
## 9.0.0 (x)
| Bileşen | Tür | Etkilenen vaka / hücre | Gerekçe | Gözlenen fark | Harcama farkı | Karar |
|---|---|---|---|---|---|---|
| `a.py` (yeni ) → `b` | işleyiş | — | — | — | — | yardım etti (test) |
| `c.py` | işleyiş | — | — | iyileşti | +%5 | yardım etti |
"""
    data = EO.parse(text)
    assert set(data) == {"a.py", "b", "c.py"}
    assert [c for c, _ in EO.summarize(data)["eval_kaniti_yok"]] == ["a.py", "b"]
