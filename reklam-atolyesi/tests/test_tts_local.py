"""1.4.8: yerel seslendirme — metin denetimi, okunuş → altyazı eşlemesi, DTW zaman aktarımı, ses kütüphanesi bütünlüğü, kurulum planı.
Motorlar (EMA, VoxCPM2) testte kurulu değildir; motor çıktıları sentetik verilir."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

import tts_local as T

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("text, kind", [("Harika 🌷", "emoji"), ("Yeni ürün #hediye", "etiket"), ("Bize @marka yazın", "@kullanıcı"),
                                        ("Detay: https://ornek.com", "bağlantı"), ("", "boş")])
def test_script_guard(text, kind):
    with pytest.raises(SystemExit, match=kind):
        T.check_script(text)


def test_script_length_and_ok():
    assert T.check_script("  Şimdi 850 TL, kargo 2 günde!  ") == "Şimdi 850 TL, kargo 2 günde!"
    with pytest.raises(SystemExit, match="karakter"):
        T.check_script("a" * (T.MAX_CHARS + 1))


def _spoken():
    # normalizer-tr çıktısının biçimi: okunan sözcük → kaynak sözcük aralığı
    toks = ["Şimdi", "850", "TL,", "kargo", "2", "günde!"]
    sw = [("Şimdi", [0, 0]), ("sekiz", [1, 2]), ("yüz", [1, 2]), ("elli", [1, 2]), ("Türk", [1, 2]), ("lirası", [1, 2]),
          ("kargo", [3, 3]), ("iki", [4, 4]), ("günde!", [5, 5])]
    return {"spoken_text": "", "source_tokens": toks, "spoken_words": [{"text": t, "src": s} for t, s in sw]}


def test_map_to_script_groups_numbers_and_keeps_spelling():
    ew = [{"text": t, "start": i * 0.3, "end": i * 0.3 + 0.3} for i, t in
          enumerate(["şimdi", "sekiz", "yüz", "elli", "türk", "lirası,", "kargo", "iki", "günde!"])]
    words, complete = T.map_to_script(_spoken(), ew)
    assert complete and [w["text"] for w in words] == ["Şimdi", "850 TL,", "kargo", "2", "günde!"]
    assert words[1]["start"] == 0.3 and words[1]["end"] == pytest.approx(1.8)


def test_map_to_script_flags_mismatch():
    ew = [{"text": t, "start": i * 0.3, "end": i * 0.3 + 0.3} for i, t in enumerate(["şimdi", "sekiz", "yüz", "kargo", "iki", "günde"])]
    words, complete = T.map_to_script(_spoken(), ew)
    assert not complete and any(w["text"] == "kargo" for w in words)


def _tone_seq(path, segs, sr=16000):
    """Farklı frekanslı ton bölümleri (sözcük gibi) ve aralarında sessizlik."""
    parts, t, marks = [], 0.0, []
    for f, d, gap in segs:
        n = int(d * sr)
        x = 0.3 * np.sin(2 * np.pi * f * np.arange(n) / sr) * np.hanning(n)
        marks.append((t, t + d))
        parts += [x, np.zeros(int(gap * sr))]
        t += d + gap
    sf.write(path, np.concatenate(parts), sr)
    return marks


def test_dtw_transfer_on_time_stretched_signal(tmp_path):
    freqs = [300, 520, 410, 700, 260, 610]
    a = _tone_seq(tmp_path / "a.wav", [(f, 0.30, 0.10) for f in freqs])
    b = _tone_seq(tmp_path / "b.wav", [(f, 0.42, 0.18) for f in freqs])  # yavaş okunuş
    ref_words = [{"text": f"w{i}", "start": s, "end": e} for i, (s, e) in enumerate(a)]
    out = T.dtw_transfer(str(tmp_path / "a.wav"), ref_words, str(tmp_path / "b.wav"))
    err = [abs(o["start"] - s) for o, (s, _) in zip(out, b)]
    assert max(err) < 0.06 and all(out[i]["start"] <= out[i + 1]["start"] for i in range(len(out) - 1))


def test_voice_catalog_integrity():
    cat = T.load_voices()
    ids = [v["id"] for v in cat["voices"]]
    assert len(ids) == len(set(ids)) and "ema-varsayilan" in ids
    for v in cat["voices"]:
        assert v["engine"] in ("ema", "voxcpm") and v["gender"] in ("kadın", "erkek") and v["license"] and v["fits"]
        if v["engine"] != "ema":
            ref = ROOT / "templates" / "voices" / v["reference"]
            assert ref.exists() and hashlib.sha256(ref.read_bytes()).hexdigest() == v["reference_sha256"]
            assert v.get("design_instruction") and "gerçek" in cat["note"]
            assert v["mode"] in ("ref", "ref+prompt") and (v["mode"] == "ref") != bool(v.get("reference_text"))
    by_gender = {g: [v for v in cat["voices"] if v["gender"] == g] for g in ("kadın", "erkek")}
    assert all(len(vs) >= 1 for vs in by_gender.values())  # her iki cinsiyette en az bir seçenek


def test_engine_missing_is_explained(tmp_path):
    with pytest.raises(SystemExit, match="kurulu değil"):
        T.engine_python(tmp_path, "ema")


@pytest.mark.parametrize("engine", ["ema", "whisper"])
def test_setup_plan_needs_yes(tmp_path, engine):
    import tts_setup as S
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "setup" / "tts_setup.py"), "--data-dir", str(tmp_path), "--engine", engine],
                       capture_output=True, text=True, encoding="utf-8")
    out = json.loads(r.stdout)
    pin = S.PINS[engine]
    if S.path_budget(tmp_path / ".tts" / engine / ".venv", (tmp_path / ".tts" / "hf").resolve(), pin["model"]) < 0:
        assert r.returncode == 3 and "çok uzun" in out["error"]  # uzun geçici klasör (Windows, uzun yol kapalı): kurulum baştan reddedilir
    else:
        assert r.returncode == 2 and out["plan"]["engine"] == engine and out["plan"]["model"] == pin["model"]
    assert not (tmp_path / ".tts").exists()  # onaysız hiçbir şey yazılmaz


def test_setup_path_budget(monkeypatch):
    import tts_setup as S
    monkeypatch.setattr(S, "long_paths_enabled", lambda: False)
    short = Path("C:/ReklamAtolyesi/veri/.tts")
    for e, pin in S.PINS.items():  # müşteri varsayılan yolu her motorda sığar
        assert S.path_budget(short / e / ".venv", short / "hf", pin["model"]) > 0
    deep = Path("C:/" + "x" * 120 + "/.tts")
    assert S.path_budget(deep / "whisper" / ".venv", deep / "hf", S.PINS["whisper"]["model"]) < 0
    # model önbelleği ortamdan derin olabilir: yalnızca ortama bakmak yetmez (ölçülen hata)
    assert S.hf_snapshot_len(deep / "hf", S.PINS["whisper"]["model"]) > len(str(deep / "whisper" / ".venv" / "Lib" / "site-packages"))
    monkeypatch.setattr(S, "long_paths_enabled", lambda: True)
    assert S.path_budget(deep / "whisper" / ".venv", deep / "hf", S.PINS["whisper"]["model"]) > 0
    assert S.PINS["whisper"].get("torch") is False and len(S.PINS["whisper"]["revision"]) == 40


def test_take_paths_and_limit(tmp_path):
    out = tmp_path / "vo" / "hook.wav"
    assert [p.name for p in T.take_paths(out, 3)] == ["hook.wav", "hook_alim2.wav", "hook_alim3.wav"]
    with pytest.raises(SystemExit, match="alım sayısı"):
        T.synth(tmp_path, "ema-varsayilan", "Merhaba.", out, takes=T.MAX_TAKES + 1)


def test_worker_peak_safety():
    sys.path.insert(0, str(ROOT / "scripts" / "audio"))
    import tts_worker as W
    loud, scaled = W._peak_safe(np.array([0.2, -0.99, 0.5]))
    assert scaled and float(np.max(np.abs(loud))) == pytest.approx(W.PEAK)
    quiet, scaled = W._peak_safe(np.array([0.2, -0.5]))
    assert not scaled and float(np.max(np.abs(quiet))) == pytest.approx(0.5)


def test_doctor_voice_engines_is_informational(tmp_path):
    import doctor as D
    r = D.Report()
    D.check_voice_engines(r, tmp_path)
    assert r.items[-1]["ok"] and r.items[-1]["detail"]["not_installed"] == ["ema", "voxcpm", "whisper"]
    (tmp_path / ".tts").mkdir()
    (tmp_path / ".tts" / "engines.json").write_text(json.dumps({"whisper": {"engine": "whisper"}}), encoding="utf-8")
    r = D.Report()
    D.check_voice_engines(r, tmp_path)
    d = r.items[-1]["detail"]
    assert r.items[-1]["ok"] and d["broken"] == ["whisper"] and "--engine whisper" in d["fix"][0] and not r.blocking()


def test_engine_without_model_is_incomplete(tmp_path):
    py = tmp_path / ".tts" / "whisper" / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    py.parent.mkdir(parents=True)
    py.write_bytes(b"")
    with pytest.raises(SystemExit, match="tamamlanmamış"):
        T.engine_python(tmp_path, "whisper")  # kayıt yok
    (tmp_path / ".tts" / "engines.json").write_text(json.dumps({"whisper": {"model": "org/m"}}), encoding="utf-8")
    with pytest.raises(SystemExit, match="model dosyası yok"):
        T.engine_python(tmp_path, "whisper")
    snap = tmp_path / ".tts" / "hf" / "hub" / "models--org--m" / "snapshots" / ("0" * 40)
    snap.mkdir(parents=True)
    assert T.engine_python(tmp_path, "whisper") == py
    (tmp_path / ".tts" / "engines.json").write_text(json.dumps({"whisper": {"model": "org/m", "revision": "1" * 40}}), encoding="utf-8")
    with pytest.raises(SystemExit, match="sürüm eski"):
        T.engine_python(tmp_path, "whisper")  # sabit sürüm inmemiş (sürüm yükseltmesinden sonra kurulum yinelenmeli)
    import doctor as D
    r = D.Report()
    D.check_voice_engines(r, tmp_path)
    assert r.items[-1]["detail"]["broken"] == ["whisper"]


def test_all_engine_models_pinned():
    import tts_setup as S
    assert all(len(p.get("revision") or "") == 40 for p in S.PINS.values())
