"""2.10.6: eval araçları (dış kod denetimi, Dalga D). Sahte eval belgeleri; ücretli koşu yok."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
import ezber_denetimi as EZ  # noqa: E402
import kor_kiyas as KK  # noqa: E402
from test_v2100_overfit import _fake_cases  # noqa: E402
from test_v2101_eval_gate import _doc, _kayit, _pair, _puan  # noqa: E402


# ---------- deney kaydı ham sonuca bağlı ----------

def test_record_must_belong_to_the_raw_file(tmp_path):
    old, new = _pair(tmp_path)
    other = _doc(tmp_path / "baska.json", claude="9.9.9")
    KK.kayit_yolu(other).write_text(KK.kayit_yolu(old).read_text(encoding="utf-8"), encoding="utf-8")  # eski kaydı başka dosyaya taşı
    with pytest.raises(SystemExit) as e:
        _puan(other, new)
    msg = str(e.value)
    assert "bu sonuç dosyasına ait değil" in msg and "9.9.9" in msg


def test_record_detects_raw_file_changed_after_recording(tmp_path):
    old, new = _pair(tmp_path)
    Path(old).write_text(Path(old).read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        _puan(old, new)
    assert "özet tutmuyor" in str(e.value)


def test_kayit_command_writes_raw_digest(tmp_path):
    import hashlib
    p = _doc(tmp_path / "k.json")
    assert KK.main(["kayit", "--json", p, "--plugin-root", str(ROOT)]) == 0
    k = json.loads(KK.kayit_yolu(p).read_text(encoding="utf-8"))
    assert k["ham_sha256"] == hashlib.sha256(Path(p).read_bytes()).hexdigest()


def test_matching_record_still_compares(tmp_path, capsys):
    old, new = _pair(tmp_path)
    assert _puan(old, new) == 0
    out = capsys.readouterr().out
    assert "(1.00/1.00/1.00)" in out  # ham koşu puanları raporda


# ---------- cevap okuyucu ----------

def _one(tmp_path, run):
    q = tmp_path / "c.json"
    q.write_text(json.dumps({"schemaVersion": 1, "cases": [{"name": "a", "runs": [run]}]}), encoding="utf-8")
    return str(q)


def test_grader_text_is_not_taken_as_answer(tmp_path):
    run = {"arm": "with", "graders": [{"name": "r1", "text": "Hakem: cevap kurala uyuyor."}], "score": 1.0}
    with pytest.raises(SystemExit) as e:
        KK.load_answers(_one(tmp_path, run))
    assert "okunamadı" in str(e.value)


def test_nested_single_answer_is_read_and_grader_ignored(tmp_path):
    run = {"arm": "with", "transcript": {"final": {"text": "Model cevabı"}}, "grading": {"text": "Hakem gerekçesi"}}
    assert KK.load_answers(_one(tmp_path, run)) == {"a": ["Model cevabı"]}


def test_ambiguous_nested_answers_need_manual_export(tmp_path):
    run = {"arm": "with", "messages": [{"text": "ilk"}, {"text": "ikinci"}]}
    with pytest.raises(SystemExit) as e:
        KK.load_answers(_one(tmp_path, run))
    assert "birden çok aday" in str(e.value)


# ---------- ezber denetimi ----------

def test_allowed_quote_does_not_hide_forbidden_copy_on_same_line(tmp_path):
    cases = EZ.load_cases(_fake_cases(tmp_path, alinti=["Kırmızı kupa bardağı İstanbul'a yarın teslim edin."]))
    line = "kırmızı kupa bardağı istanbul'a yarın teslim edin lütfen hemen"
    hits = EZ.find([("hooks/e.py", 1, line)], cases)
    assert hits and any(not h["alinti"] for h in hits)
    hits = EZ.find([("hooks/e.py", 1, "kırmızı kupa bardağı istanbul'a yarın teslim")], cases)
    assert hits and all(h["alinti"] for h in hits)  # yalnız izinli alıntı: engellemez


# ---------- bağımlılıklar ----------

def test_unused_dependencies_removed():
    txt = (ROOT / "servers" / "ad_memory" / "pyproject.toml").read_text(encoding="utf-8")
    assert '"pandas"' not in txt and '"duckdb"' not in txt
