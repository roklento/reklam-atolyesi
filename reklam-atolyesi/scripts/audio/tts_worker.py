"""Yerel seslendirme işçisi (1.4.8). Ses motorunun KENDİ sanal ortamında çalışır (DD/.tts/<motor>/.venv); çekirdek ortama torch girmez.

İstek (JSON dosyası): {"op": "normalize" | "synth", "engine": "ema" | "voxcpm", "text": "...",
                       "takes": [{"out_wav": "...", "seed": 1729}, ...]  (model bir kez yüklenir, her alım ayrı tohumla),
                       "speed": 1.0 (ema), "reference_wav": "...", "prompt_text": "..." (voxcpm; referansın metni → devam kipi),
                       "style": "..." (voxcpm, isteğe bağlı)}
Yanıt (JSON dosyası): normalize → {"spoken_text", "spoken_words": [{"text", "src": [i, j]}], "source_tokens": [...]}
                      synth → {"sample_rate", "engine_version", "load_s",
                               "takes": [{"wav", "seed", "duration_s", "gen_s", "peak_scaled", "words": [...] (yalnızca ema)}]}
Bu dosya plugin'in yazdığı koddur; motor paketleri (ema-lightning, voxcpm) kurulum betiğinin pinlediği sürümlerdir.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

TOKEN = re.compile(r"\S+")
WORDCHARS = re.compile(r"[^0-9a-zçğıöşüâîû']+")


def fold(s: str) -> str:
    return WORDCHARS.sub("", s.replace("İ", "i").replace("I", "ı").lower()).strip("'")


def spoken_map(text: str) -> dict:
    """Yazılı metni okunuşa çevirir ve her okunan sözcüğü kaynak metindeki sözcük(ler)e bağlar (850 TL → sekiz yüz elli Türk lirası)."""
    from normalizer_tr import Normalizer
    res = Normalizer().normalize(text, ambiguity_policy="fallback")
    raw = text.encode("utf-8")
    toks = [(m.group(0), len(text[:m.start()].encode("utf-8")), len(text[:m.end()].encode("utf-8"))) for m in TOKEN.finditer(text)]

    def tok_at(byte: int) -> int | None:
        for i, (_, a, b) in enumerate(toks):
            if a <= byte < b:
                return i
        return None

    spoken = []
    for seg in res.segments:
        if seg.kind == "verbatim":
            seg_bytes = raw[seg.start_byte:seg.end_byte]
            seg_text = seg_bytes.decode("utf-8", "ignore")
            for m in TOKEN.finditer(seg_text):
                b = seg.start_byte + len(seg_text[:m.start()].encode("utf-8"))
                i = tok_at(b)
                if fold(m.group(0)) and i is not None:
                    spoken.append({"text": m.group(0), "src": [i, i]})
        else:
            idx = [i for i, (_, a, b) in enumerate(toks) if a < seg.end_byte and b > seg.start_byte]
            if not idx:
                continue
            for w in seg.text.split():
                if fold(w):
                    spoken.append({"text": w, "src": [min(idx), max(idx)]})
    return {"spoken_text": res.normalized_text, "spoken_words": spoken, "source_tokens": [t for t, _, _ in toks]}


PEAK = 0.891  # -1 dBFS: üretilen ses bu tepeyi aşarsa orantılı kısılır (PCM'e yazarken kırpılma olmasın; miks ayrıca -1 dBTP'ye getirir)


def _takes(req: dict) -> list[dict]:
    return req.get("takes") or [{"out_wav": req["out_wav"], "seed": req.get("seed")}]


def _peak_safe(wav):
    import numpy as np
    wav = np.asarray(wav, dtype="float32")
    peak = float(np.max(np.abs(wav))) if wav.size else 0.0
    return (wav * (PEAK / peak), True) if peak > PEAK else (wav, False)


def synth_ema(req: dict) -> dict:
    import ema_lightning
    from ema_lightning import EMA
    from ema_lightning.audio import write_wav  # EMA ortamında soundfile yok; paketin kendi 16-bit PCM yazıcısı
    t0 = time.time()
    tts = EMA(device=req.get("device", "auto"))
    load = time.time() - t0
    out, sr = [], None
    for tk in _takes(req):
        t = time.time()
        sp = tts.say(req["text"], speed=float(req.get("speed", 1.0)), seed=tk.get("seed"))
        wav, scaled = _peak_safe(sp.audio)
        sr = sp.sample_rate
        write_wav(tk["out_wav"], wav, sr)
        out.append({"wav": tk["out_wav"], "seed": sp.seed, "duration_s": round(float(sp.duration), 3), "gen_s": round(time.time() - t, 3),
                    "peak_scaled": scaled,
                    "words": [{"text": w.text, "start": round(float(w.start), 3), "end": round(float(w.end), 3)} for w in sp.words]})
    return {"sample_rate": sr, "engine_version": getattr(ema_lightning, "__version__", "?"), "load_s": round(load, 2), "takes": out}


def synth_voxcpm(req: dict) -> dict:
    import soundfile as sf
    import torch
    import voxcpm
    from voxcpm import VoxCPM
    t0 = time.time()
    model = VoxCPM.from_pretrained(req.get("model", "openbmb/VoxCPM2"), load_denoiser=False, optimize=bool(req.get("optimize", False)))
    load = time.time() - t0
    text = req["text"] if not req.get("style") else f"({req['style']}){req['text']}"
    kw = {"reference_wav_path": req["reference_wav"]}
    if req.get("prompt_text"):  # devam kipi: referans sesi + birebir metni → tını ve okuma biçimi daha tutarlı
        kw.update(prompt_wav_path=req["reference_wav"], prompt_text=req["prompt_text"])
    sr = model.tts_model.sample_rate
    out = []
    for tk in _takes(req):
        if tk.get("seed") is not None:
            torch.manual_seed(int(tk["seed"]))
        t = time.time()
        wav = model.generate(text=text, cfg_value=float(req.get("cfg", 2.0)), inference_timesteps=int(req.get("steps", 10)), **kw)
        gen = time.time() - t
        wav, scaled = _peak_safe(wav)
        sf.write(tk["out_wav"], wav, sr)
        out.append({"wav": tk["out_wav"], "seed": tk.get("seed"), "duration_s": round(len(wav) / sr, 3), "gen_s": round(gen, 3),
                    "peak_scaled": scaled, "words": None})
    return {"sample_rate": sr, "engine_version": getattr(voxcpm, "__version__", "?"), "load_s": round(load, 2), "takes": out}


def main() -> None:
    req = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if req["op"] == "normalize":
        out = spoken_map(req["text"])
    elif req["op"] == "synth":
        out = synth_ema(req) if req["engine"] == "ema" else synth_voxcpm(req)
    else:
        raise SystemExit(f"bilinmeyen işlem: {req['op']}")
    Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
