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


GOOD_GPU = {"name": "RTX test", "vram_total_gb": 12.0, "vram_free_gb": 9.0, "compute_cap": 8.6, "driver": "x", "cuda": "12.8"}


@pytest.mark.parametrize("gpu, why", [(None, "bulunamadı"), ({**GOOD_GPU, "compute_cap": 7.5}, "kuşağı eski"),
                                      ({**GOOD_GPU, "vram_total_gb": 6.0}, "belleği yetersiz"), ({**GOOD_GPU, "cuda": "12.4"}, "sürücü"),
                                      ({**GOOD_GPU, "cuda": None}, "sürücü")])
def test_library_check_rejects_unsuitable_hardware(tmp_path, gpu, why):
    import tts_setup as S
    chk = S.library_check(tmp_path, gpu=gpu) if gpu is not None else None
    if gpu is None:
        import unittest.mock as um
        with um.patch.object(S, "gpu_info", return_value=None):
            chk = S.library_check(tmp_path)
    assert not chk["eligible"] and any(why in r for r in chk["reasons"])


def test_library_check_disk_and_busy_vram(tmp_path, monkeypatch):
    import tts_setup as S
    assert S.library_check(tmp_path, gpu=GOOD_GPU)["eligible"] or S._disk_free_gb(tmp_path) < S.LIB_REQ["disk_free_gb"]
    monkeypatch.setattr(S, "_disk_free_gb", lambda p: 3.0)
    assert any("disk" in r for r in S.library_check(tmp_path, gpu=GOOD_GPU)["reasons"])
    assert S.library_check(tmp_path, gpu=GOOD_GPU, need_disk=False)["eligible"]  # kurulu motor için disk aranmaz
    busy = {**GOOD_GPU, "vram_free_gb": 2.0}
    assert S.library_check(tmp_path, gpu=busy, need_disk=False)["eligible"]  # öneri anında boş bellek aranmaz
    assert any("şu an dolu" in r for r in S.library_check(tmp_path, gpu=busy, now=True, need_disk=False)["reasons"])


def test_capability_default_is_ema_and_offer_only_when_suitable(tmp_path, monkeypatch):
    import tts_setup as S
    monkeypatch.setattr(S, "_disk_free_gb", lambda p: 100.0)
    monkeypatch.setattr(S, "gpu_info", lambda: dict(GOOD_GPU))
    c = T.capability(tmp_path)
    assert c["default_voice"] == "ema-varsayilan" and c["library"]["offer"] and not c["library"]["use"]
    assert "--engine voxcpm" in c["library"]["how"] and "İsterseniz" in c["library"]["say"] and len(c["library"]["voices"]) >= 2
    monkeypatch.setattr(S, "gpu_info", lambda: None)
    c = T.capability(tmp_path)
    assert not c["library"]["offer"] and not c["library"]["use"] and "varsayılan ses (EMA)" in c["library"]["say"]


def test_synth_falls_back_to_default_voice(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "library_unavailable", lambda d: "ses kütüphanesi motoru kurulu değil")
    calls = []

    def fake_worker(data_dir, engine, req, **kw):
        calls.append((engine, req["op"]))
        if req["op"] == "normalize":
            return {"spoken_text": "merhaba", "source_tokens": ["Merhaba."], "spoken_words": [{"text": "merhaba", "src": [0, 0]}]}
        for tk in req["takes"]:
            sf.write(tk["out_wav"], np.zeros(1600, dtype="float32"), 16000)
        return {"sample_rate": 16000, "engine_version": "t", "load_s": 0.1,
                "takes": [{"wav": tk["out_wav"], "seed": tk["seed"], "duration_s": 0.1, "words": [{"text": "merhaba", "start": 0.0, "end": 0.1}]}
                          for tk in req["takes"]]}
    monkeypatch.setattr(T, "run_worker", fake_worker)
    r = T.synth(tmp_path, "kadin-sicak", "Merhaba.", tmp_path / "vo.wav", verify=False)
    assert r["voice"] == "ema-varsayilan" and r["voice_requested"] == "kadin-sicak" and "kurulu değil" in r["fallback"]
    assert all(e == "ema" for e, _ in calls)  # kütüphane motoru hiç çağrılmadı
    prov = json.loads((tmp_path / "vo.tts.json").read_text(encoding="utf-8"))
    assert prov["fallback"] and prov["voice"] == "ema-varsayilan" and prov["engine"] == "ema"


def test_setup_refuses_library_on_unsuitable_hardware(tmp_path, monkeypatch, capsys):
    import tts_setup as S
    monkeypatch.setattr(S, "gpu_info", lambda: None)
    monkeypatch.setattr(sys, "argv", ["tts_setup.py", "--data-dir", str(tmp_path), "--engine", "voxcpm", "--yes"])
    with pytest.raises(SystemExit) as e:
        S.main()
    out = json.loads(capsys.readouterr().out)
    assert e.value.code == 4 and "EMA" in out["error"] and not (tmp_path / ".tts").exists()


# --- 2.1.0: okunuş sözlüğü, belirsiz ifade raporu, cümle cümle sentez ----------------------------------------------------------
import tts_worker as W  # noqa: E402


def test_lexicon_keeps_caption_spelling_and_suffix():
    speak, cmap, applied = W.apply_lexicon("Wireless'ı Wi-Fi ile 24/7 kullan.", [{"written": "Wireless", "spoken": "vayırlıs"},
                                                                               {"written": "Wi-Fi", "spoken": "vay fay"},
                                                                               {"written": "24/7", "spoken": "yirmi dört yedi"}])
    assert speak == "vayırlısı vay fay ile yirmi dört yedi kullan."
    assert [a["written"] for a in applied] == ["Wireless'ı", "Wi-Fi", "24/7"]
    assert len(cmap) == len(speak) and cmap[0] == (0, len("Wireless'ı"))  # okunuşun her harfi özgün sözcüğe bağlı


def test_lexicon_longest_entry_wins_and_whole_words_only():
    lex = [{"written": "USB", "spoken": "yu es bi"}, {"written": "USB-C", "spoken": "yu es bi si"}, {"written": "Hz", "spoken": "hertz"}]
    assert W.apply_lexicon("USB-C ve USB", lex)[0] == "yu es bi si ve yu es bi"
    assert W.apply_lexicon("Hzler değil, 120 Hz.", lex)[0] == "Hzler değil, 120 hertz."


@pytest.mark.parametrize("frag, after, kind", [("3.", " kat", "ordinal"), ("3.", " Hemen", None), ("1-3", " gün", "range"),
                                               ("0850 123 45 67", " ara", "telephone"), ("24/7", " destek", None)])
def test_hint_kind(frag, after, kind):
    assert W.hint_kind(frag, after) == kind


def test_lexicon_entry_validation(tmp_path):
    with pytest.raises(SystemExit, match="küçük Türkçe harf"):
        T.check_entry("X5", "iks 5")
    r = T.lexicon_edit(tmp_path, ["wireless=Vayırlıs  Kulaklık".lower(), "Marka X=marka iks"], [])
    prof = {e["written"]: e for e in r["entries"] if e["source"] == "profil"}
    assert prof["wireless"]["spoken"] == "vayırlıs kulaklık" and "Marka X".lower() in {k.lower() for k in prof}
    assert {e["written"] for e in r["entries"] if e["source"] == "genel"} >= {"Wi-Fi", "Bluetooth"}
    r = T.lexicon_edit(tmp_path, [], ["Marka X"])
    assert not any(e["written"].lower() == "marka x" for e in r["entries"])


def test_general_lexicon_is_valid():
    entries = T.load_lexicon()
    assert entries and all(T.SPOKEN_OK.match(e["spoken"]) for e in entries)
    assert len({e["written"].lower() for e in entries}) == len(entries)


def test_split_sentences():
    assert T.split_sentences("sekiz yüz elli Türk lirası. Hemen al! Neden bekliyorsun? ") == [
        "sekiz yüz elli Türk lirası.", "Hemen al!", "Neden bekliyorsun?"]
    assert T.split_sentences("tek cümle") == ["tek cümle"]


def test_join_sentences_trims_pauses_and_shifts_words():
    sr = 1000
    a = np.concatenate([np.zeros(200), 0.5 * np.ones(300), np.zeros(200)]).astype("float32")  # 0,2 sn sessizlik + 0,3 sn ses + 0,2 sn
    b = np.concatenate([np.zeros(100), 0.5 * np.ones(400)]).astype("float32")
    audio, words = W.join_sentences([(a, [("bir", 0.2, 0.5)]), (b, [("iki", 0.1, 0.5)])], sr, 0.25)
    # a: 0,18–0,56 kalır (0,02 önce, 0,06 sonra pay) = 0,38 sn; ardından 0,25 sn duraklama; b: 0,08–0,50 = 0,42 sn
    assert len(audio) == 380 + 250 + 420
    assert words[0] == {"text": "bir", "start": 0.02, "end": 0.32}
    assert words[1]["start"] == pytest.approx(0.38 + 0.25 + 0.02) and words[1]["end"] == pytest.approx(0.38 + 0.25 + 0.42)


def test_synth_sends_sentences_and_lexicon(tmp_path, monkeypatch):
    seen = {}

    def fake_worker(data_dir, engine, req, **kw):
        seen[req["op"]] = req
        if req["op"] == "normalize":
            return {"spoken_text": "vay fay. Hemen al.", "speak_text": "vay fay. Hemen al.", "source_tokens": ["Wi-Fi.", "Hemen", "al."],
                    "spoken_words": [{"text": "vay", "src": [0, 0]}, {"text": "fay.", "src": [0, 0]}, {"text": "Hemen", "src": [1, 1]},
                                     {"text": "al.", "src": [2, 2]}],
                    "reading": {"fallbacks": [], "hinted": [], "foreign": [], "lexicon_applied": [{"written": "Wi-Fi", "spoken": "vay fay"}]}}
        for tk in req["takes"]:
            sf.write(tk["out_wav"], np.zeros(1600, dtype="float32"), 16000)
        ws = [{"text": t, "start": i * 0.2, "end": i * 0.2 + 0.2} for i, t in enumerate(["vay", "fay", "hemen", "al"])]
        return {"sample_rate": 16000, "engine_version": "t", "load_s": 0.1,
                "takes": [{"wav": tk["out_wav"], "seed": tk["seed"], "duration_s": 0.1, "words": ws} for tk in req["takes"]]}
    monkeypatch.setattr(T, "run_worker", fake_worker)
    r = T.synth(tmp_path, "ema-varsayilan", "Wi-Fi. Hemen al.", tmp_path / "vo.wav", verify=False)
    assert seen["normalize"]["lexicon"] and seen["synth"]["sentences"] == ["vay fay.", "Hemen al."]
    assert seen["synth"]["pause_s"] == T.DEFAULT_PAUSE and r["sentences"] == 2 and r["reading"]["ok"]
    words = json.loads((tmp_path / "vo.words.json").read_text(encoding="utf-8"))["words"]
    assert [w["text"] for w in words] == ["Wi-Fi.", "Hemen", "al."]  # altyazı özgün yazımla
    T.synth(tmp_path, "ema-varsayilan", "Wi-Fi. Hemen al.", tmp_path / "vo2.wav", verify=False, pause=0)
    assert "sentences" not in seen["synth"]  # 0 = eski yol: metin tek seferde


def test_reading_summary_lists_what_to_fix():
    r = T.reading_summary({"fallbacks": [{"text": "10x", "read_as": "bir sıfır iks", "reason": "protected_identifier"}], "foreign": ["Fresh"]})
    assert not r["ok"] and len(r["say"]) == 2 and "lexicon" in r["fix"]
    assert T.reading_summary({})["ok"]


def test_install_offer_pairs_ema_with_whisper(tmp_path):
    o = T.install_offer(tmp_path)
    assert o["missing"] == ["ema", "whisper"] and "Whisper" in o["say"] and len(o["how"]) == 2


def test_spoken_map_real_normalizer():
    pytest.importorskip("normalizer_tr")
    lex = T.load_lexicon()
    r = W.spoken_map("Wi-Fi'ı 3. katta, 1-3 günde teslim. Fresh paket alana 10x hediye!", lex)
    assert r["spoken_text"].startswith("vay fayı üçüncü katta, bir ila üç günde teslim.")
    assert {h["kind"] for h in r["reading"]["hinted"]} == {"ordinal", "range"}
    assert {f["text"] for f in r["reading"]["fallbacks"]} == {"10x"} and r["reading"]["foreign"] == ["Fresh"]
    toks = r["source_tokens"]
    assert {toks[w["src"][0]] for w in r["spoken_words"] if w["text"] in ("vay", "fayı")} == {"Wi-Fi'ı"}


def test_verify_accepts_lexicon_spelling(monkeypatch, tmp_path):
    import asr_local as AL
    monkeypatch.setattr(AL, "installed", lambda d: True)
    heard = [{"text": t, "start": i * 0.3, "end": i * 0.3 + 0.3} for i, t in enumerate(["vayırlıs", "geldi"])]
    monkeypatch.setattr(AL, "transcribe_files", lambda d, wavs: {"model": "t", "files": [{"in": str(Path(w).resolve()), "words": heard} for w in wavs]})
    w = str(tmp_path / "a.wav")
    assert not AL.verify_takes(tmp_path, [w], "Wireless geldi")[0]["matches"]
    assert AL.verify_takes(tmp_path, [w], "Wireless geldi", alt_script="vayırlıs geldi")[0]["matches"]
