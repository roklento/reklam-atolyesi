"""Yerel yazıya dökme işçisi (1.4.8). Whisper motorunun KENDİ sanal ortamında çalışır (DD/.tts/whisper/.venv; faster-whisper, torch yok).

İstek (JSON dosyası): {"model": "<hf depo>", "revision": "<sha>", "language": "tr", "files": ["a.wav", "b.mp4", ...],
                       "initial_prompt": "..." (isteğe bağlı), "beam_size": 5, "cpu_threads": 0}
Yanıt (JSON dosyası): {"engine_version", "model", "load_s",
                       "files": [{"in", "duration_s", "language", "language_probability", "asr_s",
                                  "words": [{"text", "start", "end", "prob"}], "segments": [{"start", "end", "text", "no_speech_prob"}],
                                  "energy_db": [10 ms çerçeve enerjisi, dBFS], "hop_s": 0.01}]}
Enerji zarfı çekirdek tarafta sözcük sınırlarını gerçek sese oturtmak için kullanılır (Whisper duraklamadan sonraki sözcüğün başını
sessizliğe çeker, dolgu sesini yazmaz; ölçüldü).
Model kurulumda indirilir; burada ağ kullanılmaz (HF_HUB_OFFLINE, local_files_only). Ses/görüntü dosyası PyAV ile doğrudan okunur.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path


HOP = 160  # 16 kHz'de 10 ms


def main() -> None:
    req = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    import faster_whisper
    from faster_whisper import WhisperModel
    t0 = time.time()
    model = WhisperModel(req["model"], device="cpu", compute_type="int8", cpu_threads=int(req.get("cpu_threads", 0)),
                         local_files_only=True, revision=req.get("revision"))
    load = time.time() - t0
    import numpy as np
    from faster_whisper.audio import decode_audio
    out = []
    for path in req["files"]:
        try:
            out.append(_one(model, path, req, np, decode_audio))
        except Exception as e:  # bozuk/okunamayan dosya: diğer dosyalar yine dökülür
            out.append({"in": path, "error": f"{type(e).__name__}: {e}"[:400]})
    Path(sys.argv[2]).write_text(json.dumps({"engine_version": faster_whisper.__version__, "model": req["model"], "load_s": round(load, 2),
                                             "files": out}, ensure_ascii=False), encoding="utf-8")


def _one(model, path, req, np, decode_audio) -> dict:
    """Tek dosya: enerji zarfı + sözcük zamanlı döküm."""
    t = time.time()
    audio = decode_audio(path, sampling_rate=16000)
    n = len(audio) // HOP
    fr = audio[:n * HOP].reshape(n, HOP) if n else np.zeros((0, HOP), dtype="float32")
    energy = np.round(10 * np.log10((fr.astype("float64") ** 2).mean(axis=1) + 1e-10), 1).tolist()  # 10 ms çerçeve, dBFS
    segs, info = model.transcribe(audio, language=req.get("language", "tr"), word_timestamps=True, beam_size=int(req.get("beam_size", 5)),
                                  condition_on_previous_text=False, initial_prompt=req.get("initial_prompt"),
                                  vad_filter=True, vad_parameters={"min_silence_duration_ms": 700, "speech_pad_ms": 300})
    words, segments = [], []
    for s in segs:  # üreteç: dökme burada yapılır
        segments.append({"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip(),
                         "no_speech_prob": round(float(s.no_speech_prob), 3)})
        for w in s.words or []:
            if w.word.strip():
                words.append({"text": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3), "prob": round(float(w.probability), 3)})
    return {"in": path, "duration_s": round(float(info.duration), 3), "language": info.language,
            "language_probability": round(float(info.language_probability), 3), "asr_s": round(time.time() - t, 2),
            "words": words, "segments": segments, "energy_db": energy, "hop_s": HOP / 16000}


if __name__ == "__main__":
    main()
