"""2.8.0: hata defteri ve geliştirme döngüsü — imzalar + senaryo hücresi, admin tarafı defter okuyucu, kör karşılaştırma, CI kontrolleri."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from admem import drafts as DR
from admem import feedback as FB
from conftest import make_active_profile

import draft_docs as DD

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
sys.path.insert(0, str(ROOT / "scripts" / "setup"))
import defter_oku as DO  # noqa: E402
import kor_kiyas as KK  # noqa: E402

SECRET = ["GizliMarka", "Zeta", "SırÜrün", "Omega", "act_ZZ"]


def test_cells_follow_matrix_axes():
    assert FB.product_cell("product", "non_positive", None, "purchase", None) == "P8"
    assert FB.product_cell("service", "exact", None, "lead", "instant_form") == "P4"
    assert FB.product_cell("product", "range", None, "purchase", None) == "P7"
    assert FB.product_cell("product", "unknown", None, "purchase", None) == "P6"
    assert FB.product_cell("product", "exact", "yılbaşı", "purchase", None) == "P5"
    assert FB.product_cell("product", "exact", None, "purchase", None) == "P1-3"
    assert FB.product_cell(None, None, None, None, None) == "Px"
    assert FB.user_cell(3, "mcp", "TRY", 1) == "U4"
    assert FB.user_cell(1, "csv", "TRY", 1) == "U5"
    assert FB.user_cell(1, "mcp", "USD", 1) == "U6"
    assert FB.user_cell(1, "mcp", "TRY", 2) == "U3"
    assert FB.user_cell(1, "mcp", "TRY", 1) == "Ux"
    for c in ("P1-3.Ux", "P8.U5", "Px.Ux"):
        assert FB.SAFE_TOKEN.match(c)


def seeded_loss_csv(store, data_dir):
    a = make_active_profile(store, name="GizliMarka Zeta", account="act_ZZ", product="SırÜrün", mode="csv")
    pid, prod = a["profile"]["id"], a["product"]["id"]
    store.product_upsert(pid, "SırÜrün", price=100, currency="TRY",
                         economics_json={"net_basket": 100, "variable_costs": {"urun": 80, "kargo": 40}, "confirmed": True})
    r = store.campaign_create(pid, prod, "Kampanya Omega", result_type="purchase", budget_total=1234, budget_total_confirmed=True)
    cid, cyid = r["campaign"]["id"], r["cycle"]["id"]
    store.cycle_set(pid, cyid, adset_budget_daily=150)
    store.stage_start(pid, "S01", cid, cyid)
    d = DD.write_stage_doc(store, pid, "S01", cid, cyid, check=False)
    p = Path(d["path"])
    for i in range(DR.MAX_DRAFT_ROUNDS):  # kasıtlı kritik sorun: son tura kadar kalır
        p.write_text(d["text"] + f"\n{{{{eksik}}}}\nTur {i}\n", encoding="utf-8")
        store.draft_check(pid, "S01", str(p), cid, cyid)
    store._decision_insert(pid, cid, cyid, None, None, "S01", None, "correction", "x", "user")
    logs = data_dir / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "kullanim-hatasi-1.json").write_text(json.dumps({
        "time": "2026-03-02T08:00:00+00:00", "tool": "mcp__plugin_reklam-atolyesi_ad-memory__stage_complete",
        "error": "GizliMarka Zeta için c1-brief.md bulunamadı"}), encoding="utf-8")
    return pid, cid


def test_defter_carries_signatures_with_cell_and_stays_anonymous(store, data_dir, clock):
    seeded_loss_csv(store, data_dir)
    prev = store.feedback_preview(30)
    rep = prev["report"]
    FB.assert_anonymous(rep)
    assert rep["schema"].endswith("/2")
    sig = {(s["asama"], s["sinyal"], s["kod"], s["hucre"]): s["n"] for s in rep["imzalar"]}
    assert sig.get(("S01", "taslak_son_tur_kaldi", "placeholder", "P8.U5")) == 1, sig
    assert sig.get(("S01", "duzeltme_istendi", "-", "P8.U5")) == 1, sig
    assert sig.get(("-", "arac_hatasi", "stage_complete:not_found", "-")) == 1, sig
    # müşteriye sade dil: teknik terim yok, ne yapılacağı açık
    text = " ".join(prev["summary"]) + " " + prev["next"]
    assert "hata defterine" in prev["next"] and "geliştiriciye" in prev["next"]
    for word in ("paket", "önizleme", "dışa aktarma"):
        assert word not in " ".join(prev["summary"]).lower(), word
    assert "S01 adımında" in text
    out = store.feedback_export("evet, yazalım", 30)
    assert "hata-defteri" in out["path"] and "WhatsApp" in out["next"]
    body = open(out["path"], encoding="utf-8").read()
    for w in SECRET + [str(data_dir)]:
        assert w not in body, w


def _defter(version, imzalar, rate=0.5):
    return {"schema": "reklam-atolyesi-geri-bildirim/2", "plugin_version": version, "period_days": 90,
            "stages": {"S01": {"completed": 1, "back_to": 0, "corrections": 2}}, "stuck": [],
            "draft_checks": {"pass_first_round_rate": rate, "by_stage": {"S01": {"checks": 3, "final_round_fail": 1}}},
            "errors": {"count": 1}, "imzalar": imzalar}


def test_defter_oku_aggregates_finds_gaps_and_compares_versions(tmp_path):
    s_loss = {"asama": "S02", "sinyal": "duzeltme_istendi", "kod": "-", "hucre": "P8.U2", "n": 2}
    s_new = {"asama": "S03", "sinyal": "taslak_son_tur_kaldi", "kod": "claim_unverified", "hucre": "P4.U1", "n": 3}
    d = tmp_path / "gelen"
    d.mkdir()
    (d / "a.json").write_text(json.dumps(_defter("2.7.0", [s_loss])), encoding="utf-8")
    (d / "b.json").write_text(json.dumps(_defter("2.8.0", [s_loss, s_new])), encoding="utf-8")
    (d / "c.json").write_text(json.dumps(_defter("2.8.0", [s_new])), encoding="utf-8")
    (d / "kopya.json").write_bytes((d / "c.json").read_bytes())
    (d / "baska.json").write_text("{}", encoding="utf-8")
    skel = tmp_path / "iskelet"
    defters, notes = DO.load_defters([str(d)])
    assert len(defters) == 3 and any("iki kez" in n for n in notes) and any("değil" in n for n in notes)
    md = DO.render(defters, notes, 2, skel)
    assert "| 2.7.0 | 1 |" in md and "| 2.8.0 | 2 |" in md
    # S02 × P8 imzasını mevcut vaka kapsıyor; S03 × P4 için vaka yok → iskelet
    assert "s02-zararina-urun" in md
    assert "YOK" in md
    made = list(skel.iterdir())
    assert len(made) == 1 and (made[0] / "prompt.md").exists() and (made[0] / "graders" / "r1-kural-uyumu.md").exists()
    assert "P4" in (made[0] / "prompt.md").read_text(encoding="utf-8")
    # sürüm karşılaştırması: S03 imzası 2.8.0'da çıktı → kötüleşti
    assert "kötüleşti" in md and "S03" in md.split("## 3.")[1]
    # iskelet evals/ altına yazılamaz
    assert DO.main([str(d), "--iskelet", str(ROOT / "evals" / "x")]) == 2


def test_kor_kiyas_hides_versions_and_flags_regression(tmp_path):
    old, new = tmp_path / "eski", tmp_path / "yeni"
    for root, txt in ((old, "eski cevap"), (new, "yeni cevap")):
        for case in ("s02-zararina-urun", "geri-bildirim-paketi"):
            (root / case).mkdir(parents=True)
            (root / case / "1.md").write_text(f"{txt} {case}", encoding="utf-8")
    out = tmp_path / "kor"
    assert KK.main(["hazirla", "--eski", str(old), "--yeni", str(new), "--out", str(out)]) == 0
    key = json.loads((out / ".anahtar.json").read_text(encoding="utf-8"))
    assert set(key) == {"s02-zararina-urun", "geri-bildirim-paketi"}
    hp = (out / "s02-zararina-urun" / "hakem.md").read_text(encoding="utf-8")
    assert "eski cevap" in hp and "yeni cevap" in hp and "hangi sürümden geldiğini bilmiyorsun" in hp
    assert KK.main(["sonuc", "--dir", str(out)]) == 1  # karar yok → eksik
    for pair, k in key.items():
        pick = [L for L in ("A", "B") if k[L] == "yeni"][0]
        (out / pair / "karar.md").write_text(f"yeni daha net\n```secim\n{pick}\n```\n", encoding="utf-8")
    assert KK.main(["sonuc", "--dir", str(out)]) == 0
    k = key["geri-bildirim-paketi"]
    pick = [L for L in ("A", "B") if k[L] == "eski"][0]
    (out / "geri-bildirim-paketi" / "karar.md").write_text(f"```secim\n{pick}\n```", encoding="utf-8")
    assert KK.main(["sonuc", "--dir", str(out)]) == 1  # regresyon


def test_ci_checks_script_refs_and_rules_size():
    import ci_check as CI
    import plugin_mode as PM

    assert CI.missing_script_refs() == []
    assert len(PM.rules_block(ROOT / "KURALLAR.md")) <= CI.RULES_BLOCK_MAX


def test_eval_cases_only_under_vakalar():
    # claude plugin eval evals/**/prompt.md'yi vaka sayar: vaka klasörleri yalnızca vakalar/ altında, betikler ve etki defteri vaka değil
    prompts = {p.parent.parent.name for p in (ROOT / "evals").rglob("prompt.md") if "results" not in p.parts}
    assert prompts == {"vakalar"}, prompts
    assert (ROOT / "evals" / "etki-defteri.md").exists() and (ROOT / "evals" / "defter_oku.py").exists()
