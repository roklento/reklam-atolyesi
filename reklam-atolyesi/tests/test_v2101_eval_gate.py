"""2.10.1: karşılaştırma eksik ya da geçersiz eval sonucunu başarılı saymaz.

Her test, sahte (elle yazılmış) bir `claude plugin eval --json` belgesiyle bir yanlış güven durumunu sınar. Bunlar gerçek Claude
çıktısı değildir; okuyucunun hatalı girdiye karşı davranışını gösterir.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
import kor_kiyas as KK  # noqa: E402

CASES = sorted(KK.expected_cases())


def _run(score=1.0, cost=0.1, **extra) -> dict:
    r = {"score": score, "costUsd": cost, "finalText": f"cevap {score}"}
    r.update(extra)
    return r


def _doc(path: Path, scores: dict | None = None, *, without=True, claude="2.5.0", **top) -> str:
    """Matrisin bütün vakaları, her biri 3 eklentili koşu (varsayılan puan 1.0)."""
    scores = scores or {}
    cases = []
    for name in CASES:
        runs = scores.get(name, [_run(), _run(), _run()])
        arms = {"with": runs}
        if without:
            arms["without"] = [_run(0.0, 9.0, finalText="eklentisiz cevap")]
        cases.append({"name": name, "arms": arms, "aggregates": {"score": 1.0}})
    d = {"schemaVersion": 1, "claudeVersion": claude, "costUsd": 1.0, "cases": cases}
    d.update(top)
    path.write_text(json.dumps(d), encoding="utf-8")
    return str(path)


def _kayit(json_path: str, *, iz="abc", claude="2.5.0", kosu=3) -> None:
    import hashlib  # 2.10.6: kayıt ham sonucun özetini taşır
    KK.kayit_yolu(json_path).write_text(json.dumps({"plugin_surumu": "x", "commit": "0" * 40, "vaka_parmak_izi": iz,
                                                    "vaka_sayisi": len(CASES), "claudeVersion": claude, "kosu": kosu,
                                                    "ham_sha256": hashlib.sha256(Path(json_path).read_bytes()).hexdigest()}),
                                        encoding="utf-8")


def _pair(tmp_path, old_scores=None, new_scores=None, **new_top):
    old = _doc(tmp_path / "eski.json", old_scores)
    new = _doc(tmp_path / "yeni.json", new_scores, **new_top)
    _kayit(old)
    _kayit(new)
    return old, new


def _puan(old, new) -> int:
    return KK.main(["puan", "--eski", old, "--yeni", new])


# ---------- tam ve geçerli sonuç ----------

def test_complete_result_passes(tmp_path, capsys):
    old, new = _pair(tmp_path)
    assert _puan(old, new) == 0
    out = capsys.readouterr().out
    assert "eşit olduğunu kanıtlamaz" in out
    assert "müşterinin kullanım maliyeti değildir" in out
    assert "Claude 2.5.0" in out


# ---------- P0: eksik sonuçta dur ----------

@pytest.mark.parametrize("top, word", [({"partial": True, "partialReason": "bütçe"}, "partial"),
                                       ({"schemaVersion": 2}, "şema sürümü"),
                                       ({"schemaVersion": None}, "şema sürümü")])
def test_partial_or_unknown_schema_stops(tmp_path, top, word):
    old, new = _pair(tmp_path, **top)
    with pytest.raises(SystemExit) as e:
        _puan(old, new)
    assert word in str(e.value)


@pytest.mark.parametrize("bad", [{"error": "zaman aşımı"}, {"aborted": True}, {"skippedPaidGraders": ["r1"]}])
def test_failed_run_is_not_filtered_out(tmp_path, bad):
    old, new = _pair(tmp_path, new_scores={CASES[0]: [_run(), _run(), _run(**bad)]})
    with pytest.raises(SystemExit) as e:
        _puan(old, new)
    assert next(iter(bad)) in str(e.value)


def test_unreadable_score_in_one_run_stops(tmp_path):
    bad = {"costUsd": 0.1, "finalText": "x"}  # puan yok
    old, new = _pair(tmp_path, new_scores={CASES[0]: [_run(), bad, bad]})
    with pytest.raises(SystemExit) as e:
        _puan(old, new)
    assert "puan okunamadı" in str(e.value) and "puanlar" in str(e.value)


def test_grader_without_score_is_not_averaged_away(tmp_path):
    run = {"graders": [{"score": 1.0, "weight": 1}, {"weight": 1}], "costUsd": 0.1}
    assert KK._run_score(run) is None


@pytest.mark.parametrize("val", [math.nan, math.inf, 1.5, -0.1])
def test_invalid_numbers_stop(tmp_path, val):
    old, new = _pair(tmp_path, new_scores={CASES[0]: [_run(val), _run(), _run()]})
    with pytest.raises(SystemExit):
        _puan(old, new)


@pytest.mark.parametrize("val", ["NaN", "Infinity", 2, "x"])
def test_invalid_manual_scores_stop(tmp_path, val):
    f = tmp_path / "elle.json"
    f.write_text('{"puanlar": {"a": [1, %s, 1]}}' % (val if not isinstance(val, str) or val in ("NaN", "Infinity") else json.dumps(val)),
                 encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        KK.load_scores(str(f))
    assert "geçerli bir puan değil" in str(e.value)


def test_duplicate_case_stops(tmp_path):
    p = tmp_path / "y.json"
    _doc(p)
    d = json.loads(p.read_text(encoding="utf-8"))
    d["cases"].append(d["cases"][0])
    p.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        KK.load_scores(str(p))
    assert "iki kez" in str(e.value)


# ---------- P0: kapsam zorunlu ----------

def test_missing_case_stops_including_closed(tmp_path):
    closed = sorted(KK.closed_cases())
    assert len(closed) == 3 and len(CASES) == 16
    old, new = _pair(tmp_path)
    d = json.loads(Path(old).read_text(encoding="utf-8"))
    d["cases"] = [c for c in d["cases"] if c["name"] not in closed]  # 13 vakalık eski yayın sonucu
    Path(old).write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        _puan(old, new)
    assert all(c in str(e.value) for c in closed)


def test_run_count_must_match(tmp_path):
    old, new = _pair(tmp_path, new_scores={CASES[0]: [_run()]})
    with pytest.raises(SystemExit) as e:
        _puan(old, new)
    assert "3 olmalı" in str(e.value)


# ---------- P0: deney kaydı ----------

def test_missing_or_mismatched_record_stops(tmp_path):
    old, new = _pair(tmp_path)
    KK.kayit_yolu(old).unlink()
    with pytest.raises(SystemExit) as e:
        _puan(old, new)
    assert "deney kaydı yok" in str(e.value)
    _kayit(old, iz="baska")
    with pytest.raises(SystemExit) as e:
        _puan(old, new)
    assert "parmak izi" in str(e.value)
    _kayit(old, claude="2.4.0")
    with pytest.raises(SystemExit) as e:
        _puan(old, new)
    assert "Claude sürümü" in str(e.value)


def test_kayit_command_fingerprints_case_files(tmp_path):
    p = _doc(tmp_path / "e.json")
    assert KK.main(["kayit", "--json", p, "--plugin-root", str(ROOT)]) == 0
    k = json.loads(KK.kayit_yolu(p).read_text(encoding="utf-8"))
    assert k["vaka_sayisi"] == 16 and k["claudeVersion"] == "2.5.0" and k["kosu"] == 3
    assert k["vaka_parmak_izi"] == KK.parmak_izi(ROOT)[0]
    # Bir hakem dosyası değişirse parmak izi değişir (kopya üzerinde; vaka içeriği okunmaz).
    import shutil
    cp = tmp_path / "kopya"
    shutil.copytree(ROOT / "evals" / "vakalar", cp / "evals" / "vakalar")
    a = KK.parmak_izi(cp)[0]
    g = next((cp / "evals" / "vakalar").rglob("graders/*.md"))
    g.write_bytes(g.read_bytes() + b"\n")
    assert KK.parmak_izi(cp)[0] != a


# ---------- P0: 0,8 eşiği ----------

def test_threshold_blocks_even_without_regression(tmp_path, capsys):
    old, new = _pair(tmp_path, old_scores={CASES[0]: [_run(0.0), _run(1.0), _run(1.0)]},
                     new_scores={CASES[0]: [_run(0.0), _run(0.0), _run(0.0)]})
    assert _puan(old, new) == 1  # oynama payı 1,0 → "fark yok", ama yeni ortalama 0 < 0,8
    out = capsys.readouterr().out
    assert "fark yok" in out and "EŞİK ALTI" in out


# ---------- P1: harcama ----------

def test_cost_compares_only_same_scope_and_has_tolerance(tmp_path, capsys):
    old, new = _pair(tmp_path, old_scores={c: [_run(cost=1 / 48)] * 3 for c in CASES},
                     new_scores={c: [_run(cost=1.2 / 48)] * 3 for c in CASES})
    assert _puan(old, new) == 0
    out = capsys.readouterr().out
    assert "harcama %20 arttı" in out  # 19,999… = 20 sayılır
    # Bir vakada koşu harcaması eksikse vaka başına toplam kullanılmaz; belge toplamına düşülür.
    s = KK.load_scores(_doc(tmp_path / "k.json", {CASES[0]: [_run(), _run(), {"score": 1.0}]}))
    assert s["harcama"] == {} and "toplam" in s["kaynak"]
    r = KK.compare_scores({"puanlar": {"a": [1.0]}, "harcama": {}, "toplam_harcama": None},
                          {"puanlar": {"a": [1.0]}, "harcama": {}, "toplam_harcama": 3.0}, set())
    assert r["harcama_artis"] is None and r["harcama_kaynak"] == "ölçülemedi"


# ---------- P0: kör karşılaştırma ----------

def test_answer_reader_uses_with_arm_only(tmp_path):
    p = _doc(tmp_path / "y.json")
    got = KK.load_answers(p)
    assert set(got) == set(CASES)
    assert all(v == ["cevap 1.0"] * 3 for v in got.values())  # eklentisiz cevap alınmaz
    # runs[] düzeninde de eklentisiz kol ayıklanır.
    q = tmp_path / "r.json"
    q.write_text(json.dumps({"schemaVersion": 1, "cases": [{"name": "a", "runs": [
        {"arm": "with", "finalText": "P"}, {"arm": "without", "finalText": "B"}]}]}), encoding="utf-8")
    assert KK.load_answers(str(q)) == {"a": ["P"]}


def test_answer_reader_applies_same_checks(tmp_path):
    p = _doc(tmp_path / "y.json", partial=True)
    with pytest.raises(SystemExit):
        KK.load_answers(p)
    q = _doc(tmp_path / "z.json", {CASES[0]: [_run(), _run(), {"score": 1.0}]})  # cevapsız koşu
    with pytest.raises(SystemExit) as e:
        KK.load_answers(q)
    assert "cevap metni okunamadı" in str(e.value)


def test_hazirla_stops_on_missing_case_or_count(tmp_path):
    old = _doc(tmp_path / "e.json")
    new = _doc(tmp_path / "y.json", {CASES[0]: [_run(), _run()]})
    with pytest.raises(SystemExit) as e:
        KK.main(["hazirla", "--eski", old, "--yeni", new, "--out", str(tmp_path / "kor")])
    assert "aynı sayıda koşu" in str(e.value)
    d = json.loads(Path(old).read_text(encoding="utf-8"))
    d["cases"] = d["cases"][1:]
    Path(old).write_text(json.dumps(d), encoding="utf-8")
    new = _doc(tmp_path / "y2.json")
    with pytest.raises(SystemExit) as e:
        KK.main(["hazirla", "--eski", old, "--yeni", new, "--out", str(tmp_path / "kor2")])
    assert "şu vakalar yok" in str(e.value)


def test_hazirla_needs_fresh_folder(tmp_path):
    old, new = _doc(tmp_path / "e.json"), _doc(tmp_path / "y.json")
    out = tmp_path / "kor"
    assert KK.main(["hazirla", "--eski", old, "--yeni", new, "--out", str(out)]) == 0
    assert len(json.loads((out / ".anahtar.json").read_text(encoding="utf-8"))) == 16 * 3
    with pytest.raises(SystemExit) as e:
        KK.main(["hazirla", "--eski", old, "--yeni", new, "--out", str(out)])
    assert "boş değil" in str(e.value)
