"""1.4.8: yerel yazıya dökme (Whisper) — Türkçe okunuş eşlemesi, metin ↔ döküm hizalaması, okunuş denetimi, konuşmalı kurgu kesim
önerisi, kurgu zamanına taşınan altyazı. Motor testte kurulu değildir; döküm sentetik verilir."""
from __future__ import annotations

from pathlib import Path

import pytest

import asr_local as A
from admem import editplan


@pytest.mark.parametrize("n, words", [(0, "sıfır"), (11, "on bir"), (100, "yüz"), (101, "yüz bir"), (850, "sekiz yüz elli"),
                                      (1000, "bin"), (1250, "bin iki yüz elli"), (2000, "iki bin"), (15000, "on beş bin"),
                                      (1000000, "bir milyon"), (2500000, "iki milyon beş yüz bin")])
def test_say_int(n, words):
    assert " ".join(A.say_int(n)) == words


@pytest.mark.parametrize("tok, out", [("850", "sekiz yüz elli"), ("TL,", "lira"), ("%20", "yüzde yirmi"), ("2,5", "iki virgül beş"),
                                      ("1.250", "bin iki yüz elli"), ("2'de", "ikide"), ("₺99", "doksan dokuz lira"),
                                      ("İstanbul'a", "istanbula"), ("lirası", "lira")])
def test_spoken_forms(tok, out):
    assert " ".join(A.spoken(tok)) == out


def test_fillers():
    assert all(A.is_filler(x) for x in ["ııı", "Eee,", "hmm", "ıhh"]) and not any(A.is_filler(x) for x in ["e", "evet", "ama", "bu"])


def W(spec, t=0.2):
    """Sentetik döküm: sözcük ya da (sayı → o kadar sessizlik)."""
    out = []
    for x in spec:
        if isinstance(x, float):
            t += x
            continue
        d = 0.08 * len(x) + 0.1
        out.append({"text": x, "start": round(t, 3), "end": round(t + d, 3), "prob": 0.9})
        t += d + 0.05
    return out


def test_align_numbers_and_spelling():
    asr = W(["Şimdi", "sekiz", "yüz", "elli", "Türk", "lirası,", "kargo", "iki", "günde!"])
    r = A.align("Şimdi 850 TL, kargo 2 günde!", asr)
    assert r["matches_script"] and r["diffs"] == []
    assert [w["text"] for w in r["words"]] == ["Şimdi", "850", "TL,", "kargo", "2", "günde!"]
    assert r["words"][1]["start"] == asr[1]["start"] and r["words"][1]["end"] == asr[3]["end"]
    # döküm rakamla yazılmışsa da aynı
    assert A.align("Şimdi 850 TL, kargo 2 günde!", W(["Şimdi", "850", "TL,", "kargo", "2", "günde!"]))["matches_script"]


def test_align_reports_mispronunciation_and_missing():
    r = A.align("Şimdi 850 TL, kargo 2 günde!", W(["Şimdi", "sekiz", "yüz", "altmış", "lira,", "kargo", "günde!"]))
    kinds = {d["kind"] for d in r["diffs"]}
    assert not r["matches_script"] and kinds == {"okunuş farkı", "metinde var, duyulmadı"}
    farki = next(d for d in r["diffs"] if d["kind"] == "okunuş farkı")
    assert farki["script"] == "850" and "altmış" in farki["heard"]
    ts = [(w["start"], w["end"]) for w in r["words"]]  # her sözcük zamanlı ve tekdüze
    assert all(s is not None and e >= s for s, e in ts) and all(ts[i][0] <= ts[i + 1][0] for i in range(len(ts) - 1))


def test_align_ignores_fillers_and_words_doc():
    asr = W(["Merhaba", "ııı", "dünya."])
    doc = A.words_doc("Merhaba dünya.", {"words": asr})
    assert doc["matches_script"] and [w["text"] for w in doc["words"]] == ["Merhaba", "dünya."] and doc["captions"]
    raw = A.words_doc(None, {"words": asr})
    assert raw["matches_script"] is None and [w["text"] for w in raw["words"]] == ["Merhaba", "dünya."] and "kullanıcı" in raw["note"]


def _talk():
    return W(["Bu", "mum", "el", "yapımı", "ve", 1.2, "Bu", "mum", "el", "yapımı", "ve", "doğal", "soya.", 0.9, "ııı", 0.6,
              "Kokusu", "çok", "çok", "güzel.", 0.5, "Hemen", "sipariş", "verin", "sipariş", "verin."])


def test_cuts_fillers_pauses_retakes_repeats():
    words = _talk()
    tr = {"words": words, "duration_s": words[-1]["end"] + 0.5, "in": "C:/x/klip.mp4"}
    c = A.plan_cuts(tr)
    reasons = {r["reason"].split(":")[0] for r in c["removed"]}
    assert reasons == {"dolgu sesi", "yeniden başlama"}  # yarım alım ve art arda tekrar edilen öbek; önceki çıkar
    kept = " ".join(s["text"] for s in c["segments"])
    assert kept == "Bu mum el yapımı ve doğal soya. Kokusu çok çok güzel. Hemen sipariş verin."  # ikileme (çok çok) korunur
    assert c["kept_s"] < c["duration_s"] - 2.5
    # parçalar kaynakta sıralı, örtüşmesiz, kare ızgarasında
    segs = c["segments"]
    assert all(segs[i]["out_s"] <= segs[i + 1]["in_s"] for i in range(len(segs) - 1))
    assert all(abs(x * 30 - round(x * 30)) < 0.01 for s in segs for x in (s["in_s"], s["out_s"]))
    # dönüşümlü yakınlaştırma ve kurgu planı sahneleri
    assert [s["zoom"] for s in segs][:2] == [1.0, 1.12]
    sc = c["scenes"]
    assert all(s["speaking_person"] and s["audio"]["mode"] == "original" for s in sc)
    assert all(abs(sc[i]["start_s"] + sc[i]["dur_s"] - sc[i + 1]["start_s"]) < 1e-6 for i in range(len(sc) - 1))
    assert sc[1]["layers"][0]["camera"] == {"preset": "punch_in", "zoom": 1.12} and "camera" not in sc[0]["layers"][0]
    # altyazı kurgu zamanında: ilk sözcük 0'a yakın, toplam kurgu süresini aşmaz, metin tutulan sözlerle aynı
    cw = c["captions"]["words"]
    assert cw[0]["start"] < 0.1 and cw[-1]["end"] <= c["kept_s"] + 1e-6
    assert " ".join(w["text"] for w in cw) == kept


def test_cuts_restore_and_keep_retakes():
    words = _talk()
    tr = {"words": words, "duration_s": words[-1]["end"] + 0.5}
    c = A.plan_cuts(tr)
    rid = next(r["id"] for r in c["removed"] if r["reason"].startswith("yeniden"))
    c2 = A.plan_cuts(tr, restore={rid})
    assert next(r for r in c2["removed"] if r["id"] == rid)["restored"] and c2["segments"][0]["text"].startswith("Bu mum el yapımı ve")
    c3 = A.plan_cuts(tr, keep_retakes=True)
    assert not any(r["reason"].startswith("yeniden") for r in c3["removed"])
    assert [r["id"] for r in A.plan_cuts(tr)["removed"]] == [r["id"] for r in c["removed"]]  # kimlikler kararlı (zamandan)
    assert rid == f"r{words[0]['start']:.2f}"


def test_sentence_retake_with_different_ending_and_no_false_positive():
    words = W(["Bu", "mum", "el", "yapımı", "ve", "çok", 1.0, "Bu", "mum", "el", "yapımı", "ve", "doğal", "soya."])  # yarıda kalan alım
    c = A.plan_cuts({"words": words, "duration_s": words[-1]["end"] + 0.3})
    assert [r["reason"].split(":")[0] for r in c["removed"]] == ["yeniden başlanan cümle"]
    assert " ".join(s["text"] for s in c["segments"]) == "Bu mum el yapımı ve doğal soya."
    ok = W(["Bu", "mum", "el", "yapımı.", 0.9, "Bu", "kase", "seramik."])
    assert A.plan_cuts({"words": ok, "duration_s": ok[-1]["end"] + 0.3})["removed"] == []


def test_partial_word_restart():
    words = W(["Bu", "mum", "el", "yap", "bu", "mum", "el", "yapımı."])
    c = A.plan_cuts({"words": words, "duration_s": words[-1]["end"] + 0.3})
    assert c["removed"] and c["removed"][0]["text"] == "Bu mum el yap" and c["segments"][-1]["text"].endswith("yapımı.")


def _energy(voiced, dur, hop=0.01, floor=-60.0, level=-20.0):
    e = [floor] * int(dur / hop)
    for a, b in voiced:
        for k in range(int(a / hop), min(len(e), int(b / hop))):
            e[k] = level
    return e


def test_refine_words_snaps_to_voice_and_finds_unwritten_filler():
    # gerçek ses: söz 0.40–1.80, dolgu 2.70–3.06, söz 3.66–5.00; Whisper ikinci sözün başını 2.30'a çekmiş, dolguyu yazmamış
    e = _energy([(0.40, 1.80), (2.70, 3.06), (3.66, 5.00)], 5.5)
    raw = [{"text": "bir", "start": 0.12, "end": 1.0}, {"text": "iki", "start": 1.0, "end": 1.62},
           {"text": "üç", "start": 2.30, "end": 4.2}, {"text": "dört", "start": 4.2, "end": 4.9}]
    words, nonword = A.refine_words(raw, e)
    assert words[0]["start"] == pytest.approx(0.40, abs=0.02) and words[1]["end"] == pytest.approx(1.80, abs=0.02)
    assert words[2]["start"] == pytest.approx(3.66, abs=0.02) and words[2]["raw"] == [2.30, 4.2]
    assert words[3]["end"] == pytest.approx(5.00, abs=0.02)
    assert nonword == [{"start": pytest.approx(2.70, abs=0.02), "end": pytest.approx(3.06, abs=0.02)}]
    c = A.plan_cuts({"words": words, "nonspeech": nonword, "duration_s": 5.5})
    assert any(r["reason"].startswith("dökümde olmayan ses") for r in c["removed"])
    assert all(not (s["in_s"] < 3.0 < s["out_s"]) for s in c["segments"])  # dolgu kesildi
    assert "…" not in " ".join(w["text"] for w in c["captions"]["words"])
    assert A.refine_words(raw, []) == ([dict(w) for w in raw], [])  # enerji yoksa dokunulmaz


def test_cuts_corrected_script_spelling_and_at():
    words = W(["bu", "mumu", "850", "liraya", "aldım."])
    tr = {"words": words, "duration_s": words[-1]["end"] + 0.3}
    c = A.plan_cuts(tr, script="Bu mumu 850 TL'ye aldım.", at=2.0)
    assert [w["text"] for w in c["captions"]["words"]][0] == "Bu" and c["scenes"][0]["start_s"] == 2.0
    assert c["captions"]["words"][0]["start"] >= 2.0


def test_cut_scenes_pass_plan_validation():
    words = _talk()
    c = A.plan_cuts({"words": words, "duration_s": words[-1]["end"] + 0.5, "in": "footage/raw/k1.mp4"}, role="proof")
    dur = round(sum(s["dur_s"] for s in c["scenes"]), 4)
    plan = {"campaign": "c", "cycle_id": 1, "concept": "k", "hook": "h", "format": "9x16", "purpose": "production", "status": "draft",
            "version": 1, "duration_s": dur, "fps": 30, "style": "s", "scenes": c["scenes"]}
    v = editplan.validate(plan)
    assert not [e for e in v["errors"] if "şema" in e or "punch_in" in e or "bitişik" in e or "konuşan" in e], v["errors"]
    bad = {**plan, "scenes": [{**c["scenes"][1], "start_s": 0.0,
                               "layers": [{**c["scenes"][1]["layers"][0], "camera": {"preset": "punch_in", "zoom": 1.5}}]}],
           "duration_s": c["scenes"][1]["dur_s"]}
    assert any("punch_in" in e for e in editplan.validate(bad)["errors"])
    none_zoom = {**bad, "scenes": [{**bad["scenes"][0], "layers": [{**bad["scenes"][0]["layers"][0], "camera": {"preset": "punch_in", "zoom": None}}]}]}
    assert not any("punch_in" in e for e in editplan.validate(none_zoom)["errors"])  # zoom yok → 1,0 (çökmez)


def test_engine_missing_paths(tmp_path):
    assert not A.installed(tmp_path)
    chk = A.verify_takes(tmp_path, ["a.wav", "b.wav"], "Merhaba.")
    assert len(chk) == 2 and not chk[0]["checked"] and "whisper" in chk[0]["how"]
    with pytest.raises(SystemExit, match="kurulu değil"):
        A.transcribe_files(tmp_path, [__file__])


def test_cut_scenes_use_asset_and_merge_captions(tmp_path):
    import json
    words = _talk()
    c = A.plan_cuts({"words": words, "duration_s": words[-1]["end"] + 0.5, "in": "C:/x/k.wav"}, asset="ast_12", at=3.0)
    assert all(s["layers"][0]["source"]["asset"] == "ast_12" and "path" not in s["layers"][0]["source"] for s in c["scenes"])
    (tmp_path / "vo.json").write_text(json.dumps({"words": [{"text": "Yeni", "start": 0.1, "end": 0.5}, {"text": "koleksiyon.", "start": 0.5, "end": 1.2}]}),
                                      encoding="utf-8")
    (tmp_path / "konusma.json").write_text(json.dumps(c["captions"]), encoding="utf-8")
    assert A._part(str(tmp_path / "a@b" / "x.json")) == (tmp_path / "a@b" / "x.json", 0.0) and A._part("v.json@2.5") == (Path("v.json"), 2.5)
    m = A.merge_captions([(tmp_path / "vo.json", 0.0), (tmp_path / "konusma.json", 0.0)])
    assert m["words"][0]["text"] == "Yeni" and m["words"][2]["start"] >= 3.0 and m["overlaps"] == [] and m["captions"]
    late = A.merge_captions([(tmp_path / "vo.json", 3.2), (tmp_path / "konusma.json", 0.0)])
    assert late["overlaps"] and "üst üste" in late["note"]


@pytest.mark.parametrize("tok, out", [("1.249,90", "bin iki yüz kırk dokuz virgül doksan"), ("1,250.50", "bin iki yüz elli virgül elli"),
                                      ("21.10.2026", "yirmi bir ekim iki bin yirmi altı"), ("850 TL'ye".split()[1], "lira")])
def test_spoken_turkish_prices_and_dates(tok, out):
    assert " ".join(A.spoken(tok)) == out
    assert A.spoken("12.34.56.78")  # okunamayan biçim çökertmez


def test_align_money_forms_match():
    assert A.align("Sadece 99,90 TL", W(["sadece", "doksan", "dokuz", "lira", "doksan", "kuruş"]))["matches_script"]
    assert A.align("Sadece 1.249,90 TL.", W(["Sadece", "1249", "TL", "90", "kuruş."]))["matches_script"]
    assert A.align("Şimdi 850 TL'ye", W(["şimdi", "850", "liraya"]))["matches_script"]
    assert not A.align("Sadece 99,90 TL", W(["sadece", "doksan", "dokuz", "lira"]))["matches_script"]  # kuruş duyulmadı


@pytest.mark.parametrize("talk", [["Her", "gün", "kullan.", 0.9, "Her", "gün", "yıka."],
                                  ["Hızlı", "kargo", "var.", 0.9, "Hızlı", "kargo", "bedava."],
                                  ["Bu", "ürün", "çok", "güzel.", 0.9, "Bu", "ürün", "çok", "dayanıklı."]])
def test_parallel_sentences_are_not_retakes(talk):
    words = W(talk)
    assert A.plan_cuts({"words": words, "duration_s": words[-1]["end"] + 0.3})["removed"] == []


def test_long_parallel_sentences_are_not_restarts():
    words = W(["Bu", "krem", "cildini", "her", "gün", "nemlendirir.", 0.6, "Bu", "krem", "cildini", "her", "gün", "korur."])
    assert A.plan_cuts({"words": words, "duration_s": words[-1]["end"] + 0.3})["removed"] == []


def test_buçuk_equals_virgül_beş():
    assert A.align("2,5 kilo", W(["iki", "buçuk", "kilo"]))["matches_script"]
    assert A.align("2,5 kilo", W(["iki", "virgül", "beş", "kilo"]))["matches_script"]


def test_transcribe_files_isolates_bad_file(tmp_path, monkeypatch):
    good, bad = tmp_path / "g.wav", tmp_path / "b.wav"
    good.write_bytes(b"0")
    bad.write_bytes(b"0")
    res = {"engine_version": "t", "model": "m", "load_s": 0.1,
           "files": [{"in": str(good.resolve()), "words": [], "duration_s": 1.0}, {"in": str(bad.resolve()), "error": "InvalidDataError: x"}]}
    monkeypatch.setattr(A.TL, "run_worker", lambda *a, **k: res)
    out = A.transcribe_files(tmp_path, [str(good), str(bad)])
    assert [f["in"] for f in out["files"]] == [str(good.resolve())] and out["errors"][0]["in"] == str(bad.resolve())


def test_breath_does_not_split_sentence():
    words = W(["Bu", "kupa", 0.5, "el", "yapımı.", 0.9, "Bu", "kupa", "hediye", "için", "ideal."])
    nonspeech = [{"start": words[1]["end"] + 0.1, "end": words[1]["end"] + 0.35}]
    c = A.plan_cuts({"words": words, "nonspeech": nonspeech, "duration_s": words[-1]["end"] + 0.3})
    assert [r["reason"].split(":")[0] for r in c["removed"]] == ["dökümde olmayan ses"]
    assert "Bu kupa el yapımı." in " ".join(s["text"] for s in c["segments"])


def test_last_word_in_partial_frame_not_clipped():
    words = [{"text": "son", "start": 0.5, "end": 1.011}]
    c = A.plan_cuts({"words": words, "duration_s": 1.02})
    w = c["captions"]["words"][0]
    assert w["end"] >= w["start"] and c["segments"][0]["out_s"] >= 1.011


def test_transcribe_cli_unique_names_and_partial_errors(tmp_path, monkeypatch):
    import json
    import sys
    a, b = tmp_path / "x" / "k.wav", tmp_path / "y" / "k.wav"
    for f in (a, b):
        f.parent.mkdir()
        f.write_bytes(b"0")
    fake = {"engine_version": "t", "model": "m", "load_s": 0.1, "errors": [],
            "files": [{"in": str(f), "duration_s": 1.0, "asr_s": 0.1, "words": W(["merhaba."]), "energy_db": [], "hop_s": 0.01}
                      for f in (a, b)]}
    monkeypatch.setattr(A, "transcribe_files", lambda *x, **k: json.loads(json.dumps(fake)))
    monkeypatch.setattr(sys, "argv", ["asr_local.py", "transcribe", "--data-dir", str(tmp_path), "--in", str(a), "--in", str(b),
                                      "--out-dir", str(tmp_path / "o")])
    A.main()
    names = sorted(p.name for p in (tmp_path / "o").iterdir())
    assert names == ["k.transcript.json", "k.words.json", "k_wav.transcript.json", "k_wav.words.json"]


def test_verify_takes_survives_worker_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "installed", lambda d: True)

    def boom(*a, **k):
        raise SystemExit("işçi çöktü")
    monkeypatch.setattr(A, "transcribe_files", boom)
    chk = A.verify_takes(tmp_path, ["a.wav"], "Merhaba.")
    assert chk == [{"checked": False, "how": "okunuş denetimi çalışmadı: işçi çöktü"}]


def test_low_confidence_words_marked_only_for_reading():
    """1.6.0: Whisper sözcük güveni < 0,5 → dökümde [?sözcük] ve low_confidence; altyazı ve words metni değişmez, dolgu işaretlenmez."""
    asr = [{"text": "Kargo", "start": 0.0, "end": 0.4, "prob": 0.95}, {"text": "Örnekköy'den", "start": 0.4, "end": 1.0, "prob": 0.31},
           {"text": "eee", "start": 1.0, "end": 1.3, "prob": 0.2}, {"text": "bedava", "start": 1.3, "end": 1.8, "prob": 0.88}]
    raw = A.words_doc(None, {"words": asr})
    assert raw["text_marked"] == "Kargo [?Örnekköy'den] eee bedava"
    assert [x["text"] for x in raw["low_confidence"]] == ["Örnekköy'den"] and "[?sözcük]" in raw["note"]
    assert all("[?" not in w["text"] for w in raw["words"]) and all("[?" not in c["text"] for c in raw["captions"])
    assert A.low_confidence([{"text": "eski", "start": 0, "end": 1}]) == []  # prob'suz eski döküm
    assert "low_confidence" not in A.words_doc("Kargo bedava", {"words": asr})  # metinli yol değişmez
