"""Yerel seslendirme işçisi (1.4.8). Ses motorunun KENDİ sanal ortamında çalışır (DD/.tts/<motor>/.venv); çekirdek ortama torch girmez.

İstek (JSON dosyası): {"op": "normalize" | "synth", "engine": "ema" | "voxcpm", "text": "...",
                       "lexicon": [{"written", "spoken"}] (normalize; okunuş sözlüğü, 2.1.0),
                       "takes": [{"out_wav": "...", "seed": 1729}, ...]  (model bir kez yüklenir, her alım ayrı tohumla),
                       "speed": 1.0 (ema), "sentences": [...], "pause_s": 0.25 (ema; cümle cümle sentez, 2.1.0),
                       "reference_wav": "...", "prompt_text": "..." (voxcpm; referansın metni → devam kipi),
                       "style": "..." (voxcpm, isteğe bağlı)}
Yanıt (JSON dosyası): normalize → {"spoken_text", "speak_text", "spoken_words": [{"text", "src": [i, j]}], "source_tokens": [...],
                                   "reading": {"fallbacks", "hinted", "foreign", "lexicon_applied"}}
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


def apply_lexicon(text: str, lexicon: list[dict] | None) -> tuple[str, list[tuple[int, int]], list[dict]]:
    """Okunuş sözlüğü (2.1.0): yazılı biçim okunuşla değişir ("Wireless'ı" → "vayırlısı"); kesme işaretinden sonraki ek okunuşa
    bitişir. Dönen eşlem okunacak metnin her karakterini özgün metindeki karakter aralığına bağlar: altyazı özgün yazımla kalır."""
    cmap = [(k, k + 1) for k in range(len(text))]
    entries = [e for e in (lexicon or []) if e.get("written") and e.get("spoken")]
    if not entries:
        return text, cmap, []
    by = {e["written"].lower(): e for e in entries}
    alts = "|".join(re.escape(e["written"]) for e in sorted(entries, key=lambda e: -len(e["written"])))
    rx = re.compile(rf"(?<!\w)({alts})(?:['’](\w+))?(?!\w)", re.I)
    out, omap, applied, pos = [], [], [], 0
    for m in rx.finditer(text):
        out.append(text[pos:m.start()])
        omap += cmap[pos:m.start()]
        e = by[m.group(1).lower()]
        rep = e["spoken"] + (m.group(2) or "")
        out.append(rep)
        omap += [(m.start(), m.end())] * len(rep)
        applied.append({"written": m.group(0), "spoken": rep})
        pos = m.end()
    out.append(text[pos:])
    omap += cmap[pos:]
    return "".join(out), omap, applied


ORDINAL = re.compile(r"^\d+\.$")
RANGE = re.compile(r"^\d+\s*[-–]\s*\d+$")
PHONE = re.compile(r"^\+?[\d\s()-]{10,}$")
FOREIGN_RX = re.compile(r"[qwxQWXéèêáàäñëïøå]|[a-zçğıöşü][A-ZÇĞİÖŞÜ]|th|sh|ck|ee|oo|ph|ght")
LATIN_CAPS = re.compile(r"^[A-Z]{2,}(?:-[A-Z0-9]+)?$")


def hint_kind(text: str, after: str) -> str | None:
    """Normalleştiricinin emin olmadığı ifadeye ipucu: "3. kat" sıra sayısı (ardından küçük harfli sözcük gelirse; "Fiyat 3. Hemen"
    cümle sonudur), "1-3 gün" aralık, telefon numarası. Başka biçimlere ipucu verilmez; raporda kalır."""
    t = text.strip()
    if ORDINAL.match(t):
        nxt = after.lstrip()[:1]
        return "ordinal" if nxt and nxt.isalpha() and nxt == nxt.lower() else None
    if RANGE.match(t):
        return "range"
    if PHONE.match(t) and 10 <= sum(c.isdigit() for c in t) <= 13:
        return "telephone"
    return None


def normalize_with_hints(text: str):
    from normalizer_tr import Hint, Normalizer
    n = Normalizer()
    res = n.normalize(text, ambiguity_policy="fallback")
    raw, hints, hinted = text.encode("utf-8"), [], []
    for f in res.fallbacks:
        frag = raw[f.start_byte:f.end_byte].decode("utf-8", "ignore")
        kind = hint_kind(frag, raw[f.end_byte:].decode("utf-8", "ignore"))
        if not kind:
            continue
        h = Hint(f.start_byte, f.end_byte, kind)
        try:  # ipucu ifadenin tamamını kapsamıyorsa normalleştirici reddeder: o ipucu bırakılır, ifade raporda kalır
            n.normalize(text, ambiguity_policy="fallback", hints=[*hints, h])
        except Exception:
            continue
        hints.append(h)
        hinted.append({"start_byte": f.start_byte, "end_byte": f.end_byte, "kind": kind})
    return (n.normalize(text, ambiguity_policy="fallback", hints=hints) if hints else res), hinted


def spoken_map(text: str, lexicon: list[dict] | None = None) -> dict:
    """Yazılı metni okunuşa çevirir ve her okunan sözcüğü kaynak metindeki sözcük(ler)e bağlar (850 TL → sekiz yüz elli Türk lirası).
    2.1.0: önce okunuş sözlüğü, sonra emin olunmayan ifadelere ipucu; kalan belirsizlikler ve yabancı görünen sözcükler `reading`te."""
    speak, cmap, applied = apply_lexicon(text, lexicon)
    res, hinted = normalize_with_hints(speak)
    raw = speak.encode("utf-8")
    char_at = [0] * (len(raw) + 1)  # bayt → karakter
    b = 0
    for c, ch in enumerate(speak):
        n = len(ch.encode("utf-8"))
        for k in range(n):
            char_at[b + k] = c
        b += n
    char_at[len(raw)] = len(speak)
    toks = [(m.group(0), m.start(), m.end()) for m in TOKEN.finditer(text)]

    def orig_range(sb: int, eb: int) -> tuple[int, int] | None:
        cs, ce = char_at[sb], char_at[eb]
        if cs >= ce:
            return None
        return min(cmap[c][0] for c in range(cs, ce)), max(cmap[c][1] for c in range(cs, ce))

    def orig_tokens(sb: int, eb: int) -> list[int]:
        r = orig_range(sb, eb)
        return [i for i, (_, a, z) in enumerate(toks) if r and a < r[1] and z > r[0]]

    def orig_text(sb: int, eb: int) -> str:
        r = orig_range(sb, eb)
        return text[r[0]:r[1]] if r else ""

    spoken, foreign = [], []
    for seg in res.segments:
        if seg.kind == "verbatim":
            seg_text = raw[seg.start_byte:seg.end_byte].decode("utf-8", "ignore")
            for m in TOKEN.finditer(seg_text):
                sb = seg.start_byte + len(seg_text[:m.start()].encode("utf-8"))
                idx = orig_tokens(sb, sb + len(m.group(0).encode("utf-8")))
                if fold(m.group(0)) and idx:
                    spoken.append({"text": m.group(0), "src": [min(idx), max(idx)]})
                    r = orig_range(sb, sb + len(m.group(0).encode("utf-8")))
                    from_lexicon = r and (r[1] - r[0]) != len(m.group(0))
                    word = re.sub(r"['’]\w*$", "", m.group(0).strip(".,;:!?\"()…"))
                    if not from_lexicon and (FOREIGN_RX.search(word) or LATIN_CAPS.match(word)):
                        foreign.append(toks[idx[0]][0].strip(".,;:!?\"()…"))
        else:
            idx = orig_tokens(seg.start_byte, seg.end_byte)
            if not idx:
                continue
            for w in seg.text.split():
                if fold(w):
                    spoken.append({"text": w, "src": [min(idx), max(idx)]})

    def read_as(sb: int, eb: int) -> str:
        return " ".join(s.text for s in res.segments if s.kind != "verbatim" and s.start_byte < eb and s.end_byte > sb).strip()
    fallbacks = [{"text": orig_text(f.start_byte, f.end_byte), "read_as": read_as(f.start_byte, f.end_byte), "reason": f.reason}
                 for f in res.fallbacks]
    hinted_out = [{"text": orig_text(h["start_byte"], h["end_byte"]), "kind": h["kind"], "read_as": read_as(h["start_byte"], h["end_byte"])}
                  for h in hinted]
    return {"spoken_text": res.normalized_text, "speak_text": speak, "spoken_words": spoken, "source_tokens": [t for t, _, _ in toks],
            "reading": {"fallbacks": fallbacks, "hinted": hinted_out, "foreign": list(dict.fromkeys(foreign)), "lexicon_applied": applied}}


PEAK = 0.891  # -1 dBFS: üretilen ses bu tepeyi aşarsa orantılı kısılır (PCM'e yazarken kırpılma olmasın; miks ayrıca -1 dBTP'ye getirir)


def _takes(req: dict) -> list[dict]:
    return req.get("takes") or [{"out_wav": req["out_wav"], "seed": req.get("seed")}]


def _peak_safe(wav):
    import numpy as np
    wav = np.asarray(wav, dtype="float32")
    peak = float(np.max(np.abs(wav))) if wav.size else 0.0
    return (wav * (PEAK / peak), True) if peak > PEAK else (wav, False)


TRIM_REL = 0.01   # cümle başı/sonundaki sessizlik: tepenin %1'i (-40 dB) altı
TRIM_LEAD = 0.02  # konuşmadan önce bırakılan pay (sn)
TRIM_TAIL = 0.06  # konuşmadan sonra bırakılan pay: cümle sonu düşüşü ve sürtünmeli son ses (s, f, ş) kesilmesin


def trim_silence(wav, sr: int):
    """Cümlenin baş ve sonundaki sessizliği kırpar; (ses, baştan kırpılan sn)."""
    import numpy as np
    wav = np.asarray(wav, dtype="float32")
    peak = float(np.max(np.abs(wav))) if wav.size else 0.0
    if peak <= 0:
        return wav, 0.0
    loud = np.flatnonzero(np.abs(wav) > peak * TRIM_REL)
    a = max(0, int(loud[0]) - int(TRIM_LEAD * sr))
    z = min(len(wav), int(loud[-1]) + 1 + int(TRIM_TAIL * sr))
    return wav[a:z], a / sr


def join_sentences(parts: list[tuple], sr: int, pause_s: float):
    """Cümle seslerini kırpıp aralarına `pause_s` sessizlik koyarak birleştirir; sözcük zamanları birleşik sese kaydırılır."""
    import numpy as np
    chunks, words, t = [], [], 0.0
    for k, (audio, ws) in enumerate(parts):
        if k:
            chunks.append(np.zeros(int(round(pause_s * sr)), dtype="float32"))
            t += round(pause_s * sr) / sr
        clip, cut = trim_silence(audio, sr)
        dur = len(clip) / sr
        for text, s, e in ws:
            s2, e2 = min(max(0.0, s - cut), dur), min(max(0.0, e - cut), dur)
            words.append({"text": text, "start": round(t + s2, 3), "end": round(t + max(s2, e2), 3)})
        chunks.append(clip)
        t += dur
    return (np.concatenate(chunks) if chunks else np.zeros(0, dtype="float32")), words


def synth_ema(req: dict) -> dict:
    import ema_lightning
    from ema_lightning import EMA
    from ema_lightning.audio import write_wav  # EMA ortamında soundfile yok; paketin kendi 16-bit PCM yazıcısı
    t0 = time.time()
    tts = EMA(device=req.get("device", "auto"))
    load = time.time() - t0
    out, sr = [], None
    speed, sentences = float(req.get("speed", 1.0)), req.get("sentences")
    for tk in _takes(req):
        t = time.time()
        if sentences:  # 2.1.0: cümle cümle; EMA ~10 sn'ye kadar metni tek parça okur ve cümle aralarına duraklama koymaz
            parts = tts.say(list(sentences), speed=speed, seed=tk.get("seed"))
            sr = parts[0].sample_rate
            audio, words = join_sentences([(p.audio, [(w.text, float(w.start), float(w.end)) for w in p.words]) for p in parts], sr,
                                          float(req.get("pause_s", 0.25)))
            seed = parts[0].seed
        else:
            sp = tts.say(req["text"], speed=speed, seed=tk.get("seed"))
            sr, audio, seed = sp.sample_rate, sp.audio, sp.seed
            words = [{"text": w.text, "start": round(float(w.start), 3), "end": round(float(w.end), 3)} for w in sp.words]
        wav, scaled = _peak_safe(audio)
        write_wav(tk["out_wav"], wav, sr)
        out.append({"wav": tk["out_wav"], "seed": seed, "duration_s": round(len(wav) / sr, 3), "gen_s": round(time.time() - t, 3),
                    "peak_scaled": scaled, "words": words})
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
        out = spoken_map(req["text"], req.get("lexicon"))
    elif req["op"] == "synth":
        out = synth_ema(req) if req["engine"] == "ema" else synth_voxcpm(req)
    else:
        raise SystemExit(f"bilinmeyen işlem: {req['op']}")
    Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
