"""Yerel seslendirme (1.4.8): ücretsiz, bilgisayardan çıkmayan Türkçe VO ve kelime zamanları. ElevenLabs'in yerine VO için varsayılan yol.

Motorlar (her biri kendi sanal ortamında: DD/.tts/<motor>/.venv; kurulum `scripts/setup/tts_setup.py`):
  ema     EMA Lightning (Apache-2.0, 8,6M parametre, CPU'da gerçek zamanın birkaç katı hızlı, tek ses, kelime zamanı modelden)
  voxcpm  VoxCPM2 (Apache-2.0, ~5 GB, NVIDIA GPU önerilir) — ses kütüphanesindeki tasarlanmış (gerçek kişiye ait olmayan) seslerle
Kelime zamanları: ema → modelin kendi zamanları; voxcpm → aynı metnin EMA okunuşu ile ses özellikleri üzerinden DTW hizalaması.
Altyazı metni VO metniyle birebir: okunuş "sekiz yüz elli Türk lirası" olsa da altyazı "850 TL" yazar (okunuş eşlemesi normalizer-tr'den).

Kullanım:
  tts_local.py synth --data-dir DD --voice <ses> --script vo.txt --out audio/vo/<ad>.wav [--takes 1-4] [--speed 1.0] [--seed 1729]
     [--pause 0.25] [--profile-dir DD/profiles/<slug>] [--no-verify]
     (--pause: EMA'da cümleler ayrı okunur, aralarına bu kadar sessizlik konur; 0 = metin tek seferde (EMA'nın kendi bölmesi))
     (--takes N: model bir kez yüklenir; 1. alım <ad>.wav, sonrakiler <ad>_alim2.wav …; tohumlar seed, seed+1, …)
     Okunuş denetimi: Whisper motoru kuruluysa her alım dökülür ve VO metniyle karşılaştırılır (`pronunciation_ok`, `diffs`);
     metinle birebir alımlar listede öne gelir. Denetim dinlemenin yerine geçmez (ton, vurgu kullanıcının kulağıyla).
  tts_local.py voices [--data-dir DD]       ses kütüphanesi (DD verilirse her sesin bu bilgisayarda kullanılabilirliği)
  tts_local.py capability --data-dir DD     varsayılan ses ve ses kütüphanesi önerisi (ekran kartı, bellek, sürücü, disk)
  tts_local.py status --data-dir DD         kurulu motorlar
  tts_local.py check --data-dir DD --script vo.txt [--profile-dir P]   okunuş raporu (sentezden önce, ses üretmez; 2.1.0)
  tts_local.py lexicon [--profile-dir P] [--add "Wireless=vayırlıs" …] [--remove Wireless …]   okunuş sözlüğü
Okunuş sözlüğü (2.1.0): genel liste templates/voices/okunus-genel.json + marka profili <profil>/okunus.json (profil önce gelir).
Sözlükteki yazım yalnızca okunuşta değişir; altyazı özgün yazımla kalır ("Wireless" yazar, "vayırlıs" okunur).
Varsayılan ses her zaman EMA'dır. Kütüphane sesi (VoxCPM2) yalnızca uygun ekran kartında kullanılır; seçilmiş kütüphane sesi bu
bilgisayarda (ya da şu an) çalışamıyorsa üretim EMA sesiyle yapılır ve sonuçta `fallback` gerekçesiyle yazılır.
Çıktılar: <ad>.wav, <ad>.words.json (words_align biçimi: words, captions, matches_script), <ad>.tts.json (kaynak bilgisi).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "setup"))
from common import emit, write_json  # noqa: E402
import words_align as WA  # noqa: E402
import tts_setup as TS  # noqa: E402

PR = Path(__file__).resolve().parents[2]
VOICES = PR / "templates" / "voices" / "voices.json"
LEXICON_GENERAL = PR / "templates" / "voices" / "okunus-genel.json"
LEXICON_FILE = "okunus.json"
DEFAULT_PAUSE = 0.25  # EMA'nın kendi bölme noktasında koyduğu cümle duraklamasıyla aynı (ema_lightning/chunker.py SENTENCE_PAUSE)
MAX_PAUSE = 1.0
SPOKEN_OK = re.compile(r"^[a-zçğıöşüâîû' ]+$")
WORKER = Path(__file__).resolve().parent / "tts_worker.py"
MAX_CHARS = 900
WORKER_TIMEOUT = 3600
_BAD = [(re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]"), "emoji/simge"),
        (re.compile(r"(?<!\w)#\w+"), "etiket (#)"), (re.compile(r"(?<!\w)@\w+"), "@kullanıcı adı"),
        (re.compile(r"https?://|www\.", re.I), "bağlantı")]


class TTSError(SystemExit):
    pass


def check_script(text: str) -> str:
    """Seslendirme metni denetimi: okunuşu bozan öğe varsa reddedilir (normalizer bunları harf harf okur; ör. emoji 'unikod u artı…')."""
    t = (text or "").strip()
    if not t:
        raise TTSError("seslendirme metni boş")
    if len(t) > MAX_CHARS:
        raise TTSError(f"metin {len(t)} karakter > {MAX_CHARS}: kurgu süresine göre kısaltın (15 sn ≈ 30–35 kelime)")
    for rx, kind in _BAD:
        if rx.search(t):
            raise TTSError(f"seslendirme metninde {kind} var: yüksek sesle okunur ve altyazıyla uyuşmaz; metinden çıkarın")
    return t


def load_voices() -> dict:
    return json.loads(VOICES.read_text(encoding="utf-8"))


def _lexicon_entries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return list(json.loads(path.read_text(encoding="utf-8")).get("entries") or [])
    except (OSError, ValueError) as e:
        raise TTSError(f"okunuş sözlüğü okunamadı ({path}): {e}")


def check_entry(written: str, spoken: str) -> dict:
    """Okunuş yalnızca küçük Türkçe harf ve boşluk: rakam ya da işaret okunuşta yeniden normalleştirilir, amaç kaybolur."""
    w, sp = (written or "").strip(), " ".join((spoken or "").split())
    if not w or not sp:
        raise TTSError("sözlük girdisi 'yazım=okunuş' biçiminde olmalı")
    if not SPOKEN_OK.match(sp):
        raise TTSError(f"okunuş yalnızca küçük Türkçe harf ve boşluk olmalı: '{sp}' (ör. 'vayırlıs', 'yu es bi si')")
    return {"written": w, "spoken": sp}


def load_lexicon(profile_dir: Path | None = None) -> list[dict]:
    """Genel liste + profil sözlüğü; aynı yazımda profil kazanır."""
    merged: dict[str, dict] = {}
    for src, path in (("genel", LEXICON_GENERAL), ("profil", profile_dir / LEXICON_FILE if profile_dir else None)):
        for e in _lexicon_entries(path) if path else []:
            merged[e["written"].lower()] = {**check_entry(e["written"], e["spoken"]), "source": src}
    return list(merged.values())


def lexicon_edit(profile_dir: Path, add: list[str], remove: list[str]) -> dict:
    path = profile_dir / LEXICON_FILE
    entries = {e["written"].lower(): e for e in _lexicon_entries(path)}
    for item in add:
        if "=" not in item:
            raise TTSError(f"sözlük girdisi 'yazım=okunuş' biçiminde olmalı: {item}")
        e = check_entry(*item.split("=", 1))
        entries[e["written"].lower()] = e
    for w in remove:
        entries.pop(w.strip().lower(), None)
    if add or remove:
        write_json(path, {"version": 1, "entries": sorted(entries.values(), key=lambda e: e["written"].lower())})
    return {"path": str(path), "entries": load_lexicon(profile_dir)}


def split_sentences(spoken_text: str) -> list[str]:
    """Okunuş metnini cümlelere böler (normalleştirmeden sonra: "Dr." ya da "5.3" artık sözcüktür, yanlış bölme yapmaz)."""
    return [x for x in re.split(r"(?<=[.!?…])[\"')]*\s+", spoken_text.strip()) if re.search(r"[^\W\d_]", x)]


def reading_summary(reading: dict) -> dict:
    """Okunuş raporu: belirsiz ifadeler ve yabancı görünen sözcükler kullanıcıya gösterilir; sözlükle ya da metinle düzeltilir."""
    fb, fr = reading.get("fallbacks") or [], reading.get("foreign") or []
    lines = [f"'{x['text']}' → \"{x['read_as']}\" okunacak (emin değil)" for x in fb]
    lines += [f"'{w}' Türkçe harflerle okunacak (yabancı görünüyor)" for w in fr]
    return {**reading, "ok": not fb and not fr, "say": lines,
            "fix": None if not lines else ("yazımı değiştir (ör. '10x' → '10 kat') ya da okunuşu sözlüğe ekle: "
                                           "tts_local.py lexicon --profile-dir <profil> --add \"Wireless=vayırlıs\"")}


def check_reading(data_dir: Path, script: str, profile_dir: Path | None = None) -> dict:
    text = check_script(script)
    spoken = run_worker(data_dir, "ema", {"op": "normalize", "engine": "ema", "text": text, "lexicon": load_lexicon(profile_dir)},
                        offline=True)
    return {"spoken_text": spoken["spoken_text"], "sentences": len(split_sentences(spoken["spoken_text"])),
            "reading": reading_summary(spoken.get("reading") or {})}


def engine_python(data_dir: Path, engine: str) -> Path:
    base = data_dir / ".tts" / engine / ".venv"
    py = base / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    how = f"PY PR/scripts/setup/tts_setup.py --data-dir <DD> --engine {engine} --yes (indirme boyutu kurulumda gösterilir)"
    if not py.exists():
        raise TTSError(f"'{engine}' ses motoru kurulu değil: {how}")
    rec_path = data_dir / ".tts" / "engines.json"
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8")).get(engine) if rec_path.exists() else None
    except (OSError, ValueError):
        rec = None
    model, rev = (rec or {}).get("model"), (rec or {}).get("revision")
    snaps = data_dir / ".tts" / "hf" / "hub" / f"models--{model.replace('/', '--')}" / "snapshots" if model else None
    ok = snaps is None or (snaps.exists() and ((snaps / rev).is_dir() if rev else any(snaps.iterdir())))
    if rec is None or not ok:
        raise TTSError(f"'{engine}' kurulumu tamamlanmamış (model dosyası yok ya da sürüm eski): kurulumu yeniden çalıştırın: {how}")
    return py


def run_worker(data_dir: Path, engine: str, req: dict, worker: Path = WORKER, offline: bool = False) -> dict:
    py = engine_python(data_dir, engine)
    with tempfile.TemporaryDirectory() as td:
        rq, rs = Path(td) / "req.json", Path(td) / "res.json"
        rq.write_text(json.dumps(req, ensure_ascii=False), encoding="utf-8")
        env = {"HF_HOME": str(data_dir / ".tts" / "hf"), "PYTHONIOENCODING": "utf-8", "HF_HUB_DISABLE_TELEMETRY": "1"}
        if offline:  # model kurulumda indi; çalışırken ağa çıkılmaz
            env["HF_HUB_OFFLINE"] = "1"
        import os
        full = {**os.environ, **env}
        try:
            r = subprocess.run([str(py), "-I", str(worker), str(rq), str(rs)], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", env=full, timeout=WORKER_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise TTSError(f"{engine} işçisi {WORKER_TIMEOUT // 60} dakikada bitmedi: dosyayı bölün ya da daha az dosyayla çalıştırın")
        if r.returncode != 0 or not rs.exists():
            raise TTSError(f"{engine} işçisi başarısız: {(r.stderr or r.stdout)[-1500:]}")
        return json.loads(rs.read_text(encoding="utf-8"))


def _fold(s: str) -> str:
    return re.sub(r"[^0-9a-zçğıöşüâîû']+", "", s.replace("İ", "i").replace("I", "ı").lower()).strip("'")


def map_to_script(spoken: dict, engine_words: list[dict]) -> tuple[list[dict], bool]:
    """Motorun okunan sözcük zamanlarını kaynak metindeki sözcüklere bağlar; altyazı yazımı kaynak metinden."""
    sw = [w for w in spoken["spoken_words"] if _fold(w["text"])]
    ew = [w for w in engine_words if _fold(w["text"])]
    a, b = [_fold(w["text"]) for w in sw], [_fold(w["text"]) for w in ew]
    pairs: list[tuple[int, int]] = []
    if a == b:
        pairs = [(i, i) for i in range(len(a))]
    else:
        import difflib
        for blk in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_matching_blocks():
            pairs += [(blk.a + k, blk.b + k) for k in range(blk.size)]
    groups: dict[tuple[int, int], list[dict]] = {}
    for i, j in pairs:
        groups.setdefault(tuple(sw[i]["src"]), []).append(ew[j])
    toks = spoken["source_tokens"]
    words = []
    for (s0, s1), ws in sorted(groups.items()):
        words.append({"text": " ".join(toks[s0:s1 + 1]), "start": round(min(w["start"] for w in ws), 3),
                      "end": round(max(w["end"] for w in ws), 3)})
    covered = set()
    for s0, s1 in groups:
        covered.update(range(s0, s1 + 1))
    needed = {i for i, t in enumerate(toks) if _fold(t)}
    return words, needed <= covered and len(pairs) == len(a) == len(b)


def dtw_transfer(ref_wav: str, ref_words: list[dict], tgt_wav: str) -> list[dict]:
    """Aynı metnin iki okunuşu arasında MFCC + DTW ile zaman eşlemesi; referansın kelime sınırları hedef sese taşınır."""
    import librosa
    import numpy as np
    sr, hop = 16000, 160

    def feat(p):
        y, _ = librosa.load(p, sr=sr, mono=True)
        # baştaki/sondaki sessizlik DTW'ye girmez: uç noktalar konuşmanın başı ve sonuna eşlenir (yavaş, duraklamalı okumada
        # baştaki sessizlik ilk sözcüğü 0. saniyeye çekiyordu)
        _, (i0, i1) = librosa.effects.trim(y, top_db=40, frame_length=512, hop_length=hop)
        m = librosa.feature.mfcc(y=y[i0:i1], sr=sr, n_mfcc=20, hop_length=hop, n_fft=512)
        m = (m - m.mean(axis=1, keepdims=True)) / (m.std(axis=1, keepdims=True) + 1e-6)
        return m, i0 / sr, len(y) / sr
    fa, a0, _ = feat(ref_wav)
    fb, b0, db = feat(tgt_wav)
    _, wp = librosa.sequence.dtw(X=fa, Y=fb, metric="cosine")
    wp = wp[::-1]
    ta, tb = a0 + wp[:, 0] * hop / sr, b0 + wp[:, 1] * hop / sr

    def mapt(t: float) -> float:
        k = int(np.searchsorted(ta, t))
        k = min(max(k, 0), len(tb) - 1)
        return float(min(tb[k], db))
    out = []
    for w in ref_words:
        out.append({"text": w["text"], "start": round(mapt(w["start"]), 3), "end": round(mapt(w["end"]), 3)})
    for i in range(1, len(out)):  # tekdüze artan zaman
        out[i]["start"] = max(out[i]["start"], out[i - 1]["start"])
        out[i]["end"] = max(out[i]["end"], out[i]["start"])
    return out


def sha256(p: str | Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


MAX_TAKES = 4


def take_paths(out: Path, n: int) -> list[Path]:
    return [out] + [out.with_name(f"{out.stem}_alim{k}{out.suffix}") for k in range(2, n + 1)]


def synth(data_dir: Path, voice_id: str, script: str, out: Path, speed: float = 1.0, seed: int = 1729, takes: int = 1,
          verify: bool = True, pause: float = DEFAULT_PAUSE, profile_dir: Path | None = None) -> dict:
    text = check_script(script)
    if not 1 <= takes <= MAX_TAKES:
        raise TTSError(f"alım sayısı 1–{MAX_TAKES} olmalı")
    if not 0 <= pause <= MAX_PAUSE:
        raise TTSError(f"cümle arası duraklama 0–{MAX_PAUSE} sn olmalı")
    voices = load_voices()["voices"]
    v = next((x for x in voices if x["id"] == voice_id), None)
    if not v:
        raise TTSError(f"ses yok: {voice_id}; seçenekler: {', '.join(x['id'] for x in voices)}")
    requested, fallback = voice_id, None
    if v["engine"] != "ema":  # kütüphane sesi: motor kurulu ve ekran kartı şu an uygun değilse varsayılan sese düşülür
        why = library_unavailable(data_dir)
        if why:
            fallback = why
            voice_id = DEFAULT_VOICE
            v = next(x for x in voices if x["id"] == DEFAULT_VOICE)
    out.parent.mkdir(parents=True, exist_ok=True)
    plan = [{"out_wav": str(p), "seed": seed + k} for k, p in enumerate(take_paths(out, takes))]
    spoken = run_worker(data_dir, "ema", {"op": "normalize", "engine": "ema", "text": text, "lexicon": load_lexicon(profile_dir)},
                        offline=True)
    # motorlara okunuş metni verilir: sözlük ve ipuçları uygulanmış, sayılar okunmuş (EMA yeniden normalleştirir; değişmez)
    say_text = spoken.get("spoken_text") or text
    sentences = split_sentences(say_text) if pause > 0 else []
    if v["engine"] == "ema":
        req = {"op": "synth", "engine": "ema", "text": say_text, "takes": plan, "speed": speed}
        if len(sentences) > 1:
            req.update(sentences=sentences, pause_s=pause)
        res = run_worker(data_dir, "ema", req, offline=True)
        timings = [(tk["words"], "model") for tk in res["takes"]]
    else:
        ref = PR / "templates" / "voices" / v["reference"]
        if not ref.exists() or sha256(ref) != v["reference_sha256"]:
            raise TTSError(f"ses dosyası eksik ya da değişmiş ({v['reference']}): kütüphane bütünlüğü bozuk")
        res = run_worker(data_dir, v["engine"], {"op": "synth", "engine": v["engine"], "text": spoken["spoken_text"], "takes": plan,
                                                 "reference_wav": str(ref), "prompt_text": v.get("reference_text"), "style": v.get("style")},
                         offline=True)
        with tempfile.TemporaryDirectory() as td:  # kelime zamanı rehberi: aynı metnin EMA okunuşu (tek rehber tüm alımlara yeter)
            guide = Path(td) / "ema_guide.wav"
            g = run_worker(data_dir, "ema", {"op": "synth", "engine": "ema", "text": say_text,
                                             "takes": [{"out_wav": str(guide), "seed": seed}]}, offline=True)
            gw = g["takes"][0]["words"]
            timings = [(dtw_transfer(str(guide), gw, tk["wav"]), "dtw_from_ema") for tk in res["takes"]]
    import asr_local as AL  # döngüsel içe aktarma olmasın diye burada
    checks = AL.verify_takes(data_dir, [tk["wav"] for tk in res["takes"]], text, alt_script=spoken.get("speak_text")) if verify else [{"checked": False, "how": "--no-verify"}] * len(res["takes"])
    results = []
    for tk, (engine_words, timing), chk in zip(res["takes"], timings, checks):
        wav = Path(tk["wav"])
        words, complete = map_to_script(spoken, engine_words)
        wj = wav.with_suffix(".words.json")
        write_json(wj, {"words": words, "captions": WA.chunks(words), "matches_script": complete, "timing": timing,
                        "note": None if complete else "Bazı sözcükler okunuşla eşlenemedi; altyazı bu VO için elle kontrol edilmeli."})
        prov = {"engine": v["engine"], "engine_version": res.get("engine_version"), "voice": voice_id, "voice_label": v["label"],
                "speed": speed, "seed": tk.get("seed"), "script_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "wav_sha256": sha256(wav), "duration_s": tk["duration_s"], "sample_rate": res["sample_rate"], "gen_s": tk.get("gen_s"),
                "load_s": res.get("load_s"), "peak_scaled": tk.get("peak_scaled"), "timing": timing, "ai_generated": True,
                "license": v["license"], "pronunciation": chk, "voice_requested": requested, "fallback": fallback,
                "pause_s": pause if len(sentences) > 1 and v["engine"] == "ema" else None,
                "lexicon_applied": (spoken.get("reading") or {}).get("lexicon_applied") or [],
                "note": "Yapay zekâ ile üretilmiş ses: Meta AI açıklaması gerekir (ref-legal-tr-meta). Gerçek bir kişinin sesi değildir."}
        write_json(wav.with_suffix(".tts.json"), prov)
        results.append({"wav": str(wav), "words": str(wj), "matches_script": complete, "seed": prov["seed"], "duration_s": prov["duration_s"],
                        "pronunciation_ok": chk.get("matches") if chk.get("checked") else None, "diffs": chk.get("diffs")})
    # okunuşu metinle birebir olan alımlar öne (dinleme sırası); denetim yoksa sıra değişmez
    results.sort(key=lambda r: 0 if r["pronunciation_ok"] else (1 if r["pronunciation_ok"] is None else 2))
    return {"engine": v["engine"], "voice": voice_id, "voice_requested": requested, "fallback": fallback, "timing": timings[0][1],
            "load_s": res.get("load_s"), "takes": results, "pronunciation_check": checks[0].get("checked", False),
            "sentences": len(sentences) or 1, "pause_s": pause if len(sentences) > 1 and v["engine"] == "ema" else None,
            "reading": reading_summary(spoken.get("reading") or {}),
            **({"note": f"İstenen ses ({requested}) kullanılamadı: {fallback}. Varsayılan EMA sesiyle üretildi."} if fallback else {})}


DEFAULT_VOICE = "ema-varsayilan"
LIBRARY_ENGINE = "voxcpm"


def library_unavailable(data_dir: Path) -> str | None:
    """Kütüphane sesi şu an kullanılamıyorsa gerekçe; kullanılabiliyorsa None."""
    try:
        engine_python(data_dir, LIBRARY_ENGINE)
    except TTSError:
        return "ses kütüphanesi motoru kurulu değil"
    chk = TS.library_check(data_dir, now=True, need_disk=False)
    return "; ".join(chk["reasons"]) or None


def capability(data_dir: Path) -> dict:
    """Varsayılan ses ve kütüphane önerisi: uygun ekran kartı + yer varsa ve kurulu değilse 'offer' (kullanıcıya öneri)."""
    try:
        engine_python(data_dir, LIBRARY_ENGINE)
        installed = True
    except TTSError:
        installed = False
    chk = TS.library_check(data_dir, need_disk=not installed)
    lib = [x for x in load_voices()["voices"] if x["engine"] == LIBRARY_ENGINE]
    pin = TS.PINS[LIBRARY_ENGINE]
    out = {"default_voice": DEFAULT_VOICE, "install": install_offer(data_dir), "library": {
        "eligible": chk["eligible"], "reasons": chk["reasons"], "installed": installed, "gpu": chk["gpu"], "disk_free_gb": chk["disk_free_gb"],
        "requirements": chk["requirements"], "voices": [{"id": x["id"], "label": x["label"], "gender": x["gender"]} for x in lib],
        "offer": chk["eligible"] and not installed, "use": chk["eligible"] and installed}}
    if out["library"]["offer"]:
        out["library"]["how"] = f"PY PR/scripts/setup/tts_setup.py --data-dir <DD> --engine {LIBRARY_ENGINE} --yes"
        out["library"]["download_gb"] = round(pin["env_gb"] + pin["model_gb"] + 2.5, 1)
        out["library"]["say"] = (f"Bu bilgisayarın ekran kartı ({chk['gpu']['name']}, {chk['gpu']['vram_total_gb']} GB) ses kütüphanesini "
                                 f"çalıştırabilir: {len(lib)} ek ses (kadın/erkek, farklı tonlar). Kurulum ≈ {out['library']['download_gb']} GB "
                                 f"indirir (diskte {chk['disk_free_gb']} GB boş). İsterseniz kurarım; istemezseniz varsayılan ses kullanılır.")
    elif not chk["eligible"]:
        out["library"]["say"] = "Bu bilgisayarda varsayılan ses (EMA) kullanılır; ses kütüphanesi için: " + "; ".join(chk["reasons"]) + "."
    return out


def install_offer(data_dir: Path) -> dict:
    """Varsayılan yol iki motordur: EMA (seslendirme) + Whisper (okunuş denetimi, kelime zamanları). Eksikler tek öneride (2.1.0):
    Whisper'sız EMA'nın yanlış okuduğu sözcükler sessizce geçer."""
    missing = []
    for e in ("ema", "whisper"):
        try:
            engine_python(data_dir, e)
        except TTSError:
            missing.append(e)
    if not missing:
        return {"missing": [], "say": None}
    gb = {e: round(TS.PINS[e]["env_gb"] + TS.PINS[e]["model_gb"], 1) for e in missing}
    what = {"ema": "seslendirme (EMA", "whisper": "okunuş denetimi ve kelime zamanları (Whisper"}
    parts = [f"{what[e]}, ≈ {str(gb[e]).replace('.', ',')} GB)" for e in missing]
    return {"missing": missing, "download_gb": round(sum(gb.values()), 1),
            "how": [f"PY PR/scripts/setup/tts_setup.py --data-dir <DD> --engine {e} --yes" for e in missing],
            "say": ("Ücretsiz ve bilgisayarınızdan çıkmayan seslendirme için " + " ve ".join(parts) + " kurulsun mu? "
                    "İkisi birlikte önerilir: okunuş denetimi, sesin metni doğru okuyup okumadığını her alımda kontrol eder.")}


def status(data_dir: Path) -> dict:
    out = {}
    for e in ("ema", "voxcpm", "whisper"):
        try:
            out[e] = {"installed": True, "python": str(engine_python(data_dir, e))}
        except TTSError as ex:
            out[e] = {"installed": False, "how": str(ex)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("synth")
    p.add_argument("--data-dir", required=True)
    p.add_argument("--voice", default="ema-varsayilan")
    p.add_argument("--script", required=True, help="VO metni dosyası")
    p.add_argument("--out", required=True)
    p.add_argument("--speed", type=float, default=1.0)
    p.add_argument("--seed", type=int, default=1729)
    p.add_argument("--takes", type=int, default=1)
    p.add_argument("--no-verify", action="store_true", help="Whisper okunuş denetimini atla")
    p.add_argument("--pause", type=float, default=DEFAULT_PAUSE, help="cümle arası duraklama (sn); 0 = tek seferde")
    p.add_argument("--profile-dir", help="marka profili klasörü (okunus.json)")
    p = sp.add_parser("check")
    p.add_argument("--data-dir", required=True)
    p.add_argument("--script", required=True)
    p.add_argument("--profile-dir")
    p = sp.add_parser("lexicon")
    p.add_argument("--profile-dir")
    p.add_argument("--add", action="append", default=[])
    p.add_argument("--remove", action="append", default=[])
    p = sp.add_parser("voices")
    p.add_argument("--data-dir")
    p = sp.add_parser("capability")
    p.add_argument("--data-dir", required=True)
    p = sp.add_parser("status")
    p.add_argument("--data-dir", required=True)
    a = ap.parse_args()
    if a.cmd == "synth":
        emit(synth(Path(a.data_dir), a.voice, Path(a.script).read_text(encoding="utf-8"), Path(a.out), a.speed, a.seed, a.takes,
                   verify=not a.no_verify, pause=a.pause, profile_dir=Path(a.profile_dir) if a.profile_dir else None))
    elif a.cmd == "check":
        emit(check_reading(Path(a.data_dir), Path(a.script).read_text(encoding="utf-8"), Path(a.profile_dir) if a.profile_dir else None))
    elif a.cmd == "lexicon":
        if (a.add or a.remove) and not a.profile_dir:
            raise TTSError("sözlüğe ekleme/çıkarma marka profiline yapılır: --profile-dir")
        emit(lexicon_edit(Path(a.profile_dir), a.add, a.remove) if a.profile_dir else {"entries": load_lexicon()})
    elif a.cmd == "voices":
        cat = load_voices()
        if a.data_dir:
            why = library_unavailable(Path(a.data_dir))
            for x in cat["voices"]:
                x["available_here"] = x["engine"] == "ema" or why is None
                if x["engine"] != "ema" and why:
                    x["unavailable_reason"] = why
        emit(cat)
    elif a.cmd == "capability":
        emit(capability(Path(a.data_dir)))
    else:
        emit(status(Path(a.data_dir)))


if __name__ == "__main__":
    main()
