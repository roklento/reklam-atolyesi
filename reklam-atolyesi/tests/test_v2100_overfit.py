"""2.10.0: ezber önlemleri (RRSI ve HarnessPro fikirleri) — ezber denetimi, kapalı vakalar, oynama payı, harcama, etki özeti."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
import etki_ozeti as EO  # noqa: E402
import ezber_denetimi as EZ  # noqa: E402
import kor_kiyas as KK  # noqa: E402

MATRIX = json.loads((ROOT / "evals" / "senaryo-matrisi.json").read_text(encoding="utf-8"))


# ---------- ezber denetimi ----------

def _fake_cases(tmp_path: Path, alinti: bool = False) -> Path:
    root = tmp_path / "plugin"
    case = root / "evals" / "vakalar" / "ornek-vaka"
    (case / "graders").mkdir(parents=True)
    (case / "prompt.md").write_text("---\nmax_turns: 3\n---\n\nKullanıcı: \"Kırmızı kupa bardağı İstanbul'a yarın teslim edin "
                                    "lütfen hemen.\"\n", encoding="utf-8")
    (case / "graders" / "r1.md").write_text("---\ntype: llm\nweight: 1\n---\n\nGeçer: teslim tarihini uydurmuyor.\n",
                                            encoding="utf-8")
    m = {"eval_cases": {"ornek-vaka": {"product": "P1", "user": "U1", "rubric": ["R1"], **({"alinti": True} if alinti else {})}}}
    (root / "evals" / "senaryo-matrisi.json").write_text(json.dumps(m), encoding="utf-8")
    return root


def test_ezber_flags_copied_phrase_and_case_name(tmp_path):
    cases = EZ.load_cases(_fake_cases(tmp_path))
    lines = [
        ("skills/x/SKILL.md", 10, "Müşteri kırmızı kupa bardağı istanbul'a yarın teslim derse önce sor."),  # 6+ kelime kopya
        ("KURALLAR.md", 3, "ornek-vaka için özel durum."),  # vaka adı
        ("skills/x/SKILL.md", 11, "Teslim tarihi bilinmiyorsa uydurma, seçenekli sor."),  # genel kural: temiz
    ]
    hits = EZ.find(lines, cases)
    kinds = {(h["dosya"], h["tur"]) for h in hits}
    assert ("skills/x/SKILL.md", "birebir parça") in kinds
    assert ("KURALLAR.md", "vaka adı") in kinds
    assert not any(h["satir"] == 11 for h in hits)
    assert all(not h["alinti"] for h in hits)


def test_ezber_turkish_case_folding_and_line_wrap(tmp_path):
    cases = EZ.load_cases(_fake_cases(tmp_path))
    # Büyük İ ve satıra bölünmüş cümle de yakalanır.
    lines = [("hooks/m.json", 5, "KIRMIZI KUPA BARDAĞI"), ("hooks/m.json", 6, "İSTANBUL'A YARIN TESLİM")]
    assert EZ.find(lines, cases)


def test_ezber_quoting_case_is_reported_but_not_blocking(tmp_path):
    cases = EZ.load_cases(_fake_cases(tmp_path, alinti=True))
    hits = EZ.find([("hooks/e.py", 1, "kırmızı kupa bardağı istanbul'a yarın teslim")], cases)
    assert hits and all(h["alinti"] for h in hits)


def test_ezber_watches_behaviour_files_only():
    assert EZ.watched("skills/strategy/SKILL.md") and EZ.watched("KURALLAR.md") and EZ.watched("hooks/menu.json")
    assert EZ.watched("templates/reports/brief.md") and EZ.watched("commands/basla.md")
    assert not EZ.watched("evals/vakalar/a/prompt.md") and not EZ.watched("tests/test_x.py") and not EZ.watched("README.md")


def test_ezber_repo_is_clean_against_previous_release():
    """Bu depoda gerçek fark: bu daldaki değişiklikler hiçbir vakadan engelleyici kopya içermez."""
    try:
        base = EZ.default_base()
    except (RuntimeError, subprocess.CalledProcessError):
        return  # sığ klon: CI fetch-depth 0 ile çalışır
    blocking = [h for h in EZ.find(EZ.added_lines(base), EZ.load_cases()) if not h["alinti"]]
    assert not blocking, blocking


def test_known_quoting_cases_are_marked():
    """Bugünkü 8 ortak parçanın hepsi plugin cümlesini alıntılayan iki vakadan gelir; ikisi de işaretli."""
    hits = EZ.find(EZ.all_lines(), EZ.load_cases())
    assert {h["vaka"] for h in hits} <= {"hata-sonrasi-defter-sorusu", "s02-strateji-yeni-baslayan"}
    assert all(h["alinti"] for h in hits)


# ---------- kapalı vakalar ----------

def test_closed_cases_are_consistent_and_cover_new_ground():
    rubric = (ROOT / "evals" / "rubrik.md").read_text(encoding="utf-8")
    codes = set(re.findall(r"^## (R\d+)\b", rubric, re.M))
    closed = MATRIX["kapali_cases"]
    assert len(closed) >= 3
    open_cells = {(c["product"], c["user"]) for c in MATRIX["eval_cases"].values()}
    open_users = {c["user"] for c in MATRIX["eval_cases"].values()}
    for name, case in closed.items():
        assert name not in MATRIX["eval_cases"], name
        assert case["product"] in MATRIX["products"] and case["user"] in MATRIX["users"], name
        assert (case["product"], case["user"]) not in open_cells, (name, "açık vakayla aynı hücre")
        assert set(case["rubric"]) <= codes
        d = ROOT / "evals" / "kapali" / name
        assert (d / "prompt.md").exists(), name
        graders = sorted((d / "graders").glob("*.md"))
        assert graders, name
        for g in graders:
            head = g.read_text(encoding="utf-8").split("---")[1]
            assert "type: llm" in head and "weight:" in head, g
        used = {m for g in graders for m in re.findall(r"\bR\d+\b", g.read_text(encoding="utf-8"))}
        assert set(case["rubric"]) <= used, name
    on_disk = {p.name for p in (ROOT / "evals" / "kapali").iterdir() if p.is_dir()}
    assert on_disk == set(closed)
    # En az bir kapalı vaka hiçbir açık vakada olmayan bir kullanıcıyı sınar.
    assert {c["user"] for c in closed.values()} - open_users


def test_defter_oku_ignores_closed_cases():
    src = (ROOT / "evals" / "defter_oku.py").read_text(encoding="utf-8")
    assert 'matrix.get("eval_cases")' in src and 'get("kapali_cases")' not in src


def test_kor_kiyas_finds_closed_case_text():
    name = next(iter(MATRIX["kapali_cases"]))
    assert KK.case_dir(name) == ROOT / "evals" / "kapali" / name
    assert KK.case_dir("kapali/" + name) == ROOT / "evals" / "kapali" / name
    assert "Durum:" in KK.judge_prompt(name, "a", "b")
    assert name in KK.closed_cases()


# ---------- oynama payı ve harcama ----------

def _eval_json(path: Path, scores: dict[str, list[float]], cost_per_run: float | None, shape: str) -> str:
    cases = []
    for name, sc in scores.items():
        if shape == "runs":
            runs = [{"score": s, **({"costUsd": cost_per_run} if cost_per_run is not None else {})} for s in sc]
            runs.append({"arm": "without", "score": 0.0, "costUsd": 99.0})  # eklentisiz kol sayılmaz
            cases.append({"name": f"vakalar/{name}", "runs": runs})
        else:  # graders listesiyle
            runs = [{"graders": [{"score": s, "weight": 1}, {"score": s, "weight": 1}],
                     **({"cost_usd": cost_per_run} if cost_per_run is not None else {})} for s in sc]
            cases.append({"case": name, "arms": {"with": {"runs": runs}, "baseline": {"runs": [{"score": 0}]}}})
    total = (cost_per_run or 0) * sum(len(v) for v in scores.values())
    path.write_text(json.dumps({"costUsd": total, "cases": cases}), encoding="utf-8")
    return str(path)


def test_noise_band_separates_real_change_from_noise(tmp_path):
    closed = next(iter(MATRIX["kapali_cases"]))
    old = _eval_json(tmp_path / "e.json", {"a": [0.5, 1.0, 1.0], "b": [1.0, 1.0, 1.0], closed: [1.0, 1.0, 1.0]}, 0.10, "runs")
    new = _eval_json(tmp_path / "y.json", {"a": [1.0, 1.0, 1.0], "b": [1.0, 1.0, 0.5], closed: [0.5, 0.5, 1.0]}, 0.10, "runs")
    r = KK.compare_scores(KK.load_scores(old), KK.load_scores(new), KK.closed_cases())
    res = {x["vaka"]: (x["sonuc"], x["grup"]) for x in r["rows"]}
    assert res["a"] == ("fark yok", "açık")  # +0,17 < oynama 0,5
    assert res["b"] == ("geriledi", "açık")  # oynama 0: her düşüş sayılır
    assert res[closed] == ("geriledi", "kapalı")
    assert KK.main(["puan", "--eski", old, "--yeni", new]) == 1


def test_cost_increase_warns_but_does_not_block(tmp_path, capsys):
    old = _eval_json(tmp_path / "e.json", {"a": [1.0, 1.0, 1.0]}, 0.10, "graders")
    new = _eval_json(tmp_path / "y.json", {"a": [1.0, 1.0, 1.0]}, 0.15, "graders")
    s_old, s_new = KK.load_scores(old), KK.load_scores(new)
    assert abs(s_old["harcama"]["a"] - 0.3) < 1e-9  # yalnızca eklentili kolun harcaması
    assert s_old["puanlar"]["a"] == [1.0, 1.0, 1.0]
    assert KK.main(["puan", "--eski", old, "--yeni", new]) == 0
    out = capsys.readouterr().out
    assert "harcama %50 arttı" in out and "durdurmaz" in out


def test_missing_scores_explain_manual_format(tmp_path):
    f = tmp_path / "bos.json"
    f.write_text(json.dumps({"costUsd": 0, "cases": [{"name": "a", "runs": [{"text": "cevap"}]}]}), encoding="utf-8")
    try:
        KK.load_scores(str(f))
        raise AssertionError("hata bekleniyordu")
    except SystemExit as e:
        assert "puanlar" in str(e)
    m = tmp_path / "elle.json"
    m.write_text(json.dumps({"puanlar": {"a": [1, 0.5]}, "harcama_usd": 2.0}), encoding="utf-8")
    got = KK.load_scores(str(m))
    assert got["puanlar"]["a"] == [1.0, 0.5] and got["toplam_harcama"] == 2.0


# ---------- etki özeti ----------

def test_etki_ozeti_lists_prune_and_unmeasured():
    text = """
## 3.0.0 (x)
| Bileşen | Tür | Etkilenen vaka / hücre | Gerekçe | Gözlenen fark | Harcama farkı | Karar |
|---|---|---|---|---|---|---|
| `skills/a` | uzman bilgisi | — | — | fark yok | ölçülmedi | etkisiz |
| `skills/b` | uzman bilgisi | — | — | — | — | ölçülecek |
| `skills/c` | işleyiş | — | — | — | — | etkisiz |
## 3.1.0 (x)
| Bileşen | Tür | Etkilenen vaka / hücre | Gerekçe | Gözlenen fark | Harcama farkı | Karar |
|---|---|---|---|---|---|---|
| `skills/a`, `hooks/h.py` | uzman bilgisi | — | — | — | — | etkisiz |
| `skills/b` | uzman bilgisi | — | — | — | — | ölçülecek (vaka yeni) |
| `skills/c` | işleyiş | — | — | — | — | yardım etti (test) |
## 3.2.0 (x)
| Bileşen | Tür | Etkilenen vaka / hücre | Gerekçe | Gözlenen fark | Harcama farkı | Karar |
|---|---|---|---|---|---|---|
| `skills/b` | uzman bilgisi | — | — | — | — | ölçülecek |
| `skills/c` | işleyiş | — | — | — | — | etkisiz |
"""
    s = EO.summarize(EO.parse(text))
    assert [c for c, _ in s["silmeye_aday"]] == ["skills/a"]  # c bir kez yardım etti, b hiç etkisiz değil
    assert [c for c, _ in s["olculmemis"]] == ["skills/b"]


def test_etki_defteri_has_new_columns_and_parses():
    text = (ROOT / "evals" / "etki-defteri.md").read_text(encoding="utf-8")
    heads = [ln for ln in text.splitlines() if ln.startswith("| Bileşen |")]
    assert heads and all("Gerekçe" in h and "Harcama farkı" in h for h in heads)
    assert EO.parse(text)
    assert EO.main([]) == 0


def test_ci_runs_memorization_check_with_full_history():
    ci = (ROOT.parent / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "fetch-depth: 0" in ci and "ezber_denetimi.py" in ci
    claude_md = (ROOT.parent / "CLAUDE.md").read_text(encoding="utf-8")
    assert "evals/kapali/" in claude_md and "ezber" in claude_md.lower()
