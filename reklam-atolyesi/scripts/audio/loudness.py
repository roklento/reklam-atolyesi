"""Ses işlemleri (spec 5.13): temizlik (afftdn + yüksek geçiren), ducking (sidechaincompress), iki geçişli loudnorm
(-14 LUFS entegre, ≤ -1 dBTP) ve pyloudnorm ile doğrulama, telefon hoparlörü simülasyonu.

Alt komutlar:
  clean    --in a.wav --out b.wav                 (ücretsiz afftdn; yetmezse voice-isolator ücretli ve onaylı — bu script yapmaz)
  duck     --music m.wav --voice v.wav --out x.wav [--duck-db 4.5]
  loudnorm --in a.wav --out b.wav [--target -14 --tp -1]
  measure  --in a.wav|mp4
  phone    --in a.wav --out phone.wav            (bant geçiren 300–3400 Hz, mono; dinleme kullanıcıya/doğrulanmış araca)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit, ffmpeg  # noqa: E402


def clean(src: str, dst: str) -> dict:
    ffmpeg(["-i", src, "-af", "highpass=f=80,afftdn=nf=-25,afftdn=nf=-30", "-ar", "48000", "-c:a", "pcm_s16le", dst])
    return {"out": dst, "method": "afftdn (ücretsiz)"}


def duck(music: str, voice: str, dst: str, duck_db: float = 4.5) -> dict:
    """Müzik VO/konuşmanın 4–5 dB altında + konuşma anlarında sidechaincompress ile ek kısma."""
    gain = 10 ** (-duck_db / 20)
    ffmpeg(["-i", music, "-i", voice, "-filter_complex",
            f"[0:a]volume={gain:.4f}[m0];[1:a]asplit=2[sc][v];[m0][sc]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=300[m];"
            f"[m][v]amix=inputs=2:normalize=0:duration=longest", "-ar", "48000", "-c:a", "pcm_s16le", dst])
    return {"out": dst, "duck_db": duck_db}


def _loudnorm_pass1(src: str, target: float, tp: float, lra: float = 11.0) -> dict:
    r = ffmpeg(["-i", src, "-af", f"loudnorm=I={target}:TP={tp}:LRA={lra}:print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if not m:
        raise RuntimeError("loudnorm ölçümü okunamadı")
    return json.loads(m.group(0))


def true_peak_db(y: np.ndarray, sr: int) -> float:
    from scipy.signal import resample_poly
    up = resample_poly(y, 4, 1, axis=0)
    return float(20 * np.log10(np.max(np.abs(up)) + 1e-12))


def measure(src: str) -> dict:
    import pyloudnorm as pyln
    import soundfile as sf
    tmp = None
    p = src
    if not src.lower().endswith(".wav"):
        tmp = str(Path(src).with_suffix(".measure.wav"))
        ffmpeg(["-i", src, "-vn", "-ac", "2", "-ar", "48000", "-c:a", "pcm_f32le", tmp])
        p = tmp
    y, sr = sf.read(p, always_2d=True)
    if tmp:
        Path(tmp).unlink(missing_ok=True)
    meter = pyln.Meter(sr)
    lufs = float(meter.integrated_loudness(y)) if len(y) > sr * 0.5 else float("nan")
    return {"lufs": round(lufs, 2), "true_peak_dbtp": round(true_peak_db(y, sr), 2), "duration_s": round(len(y) / sr, 3)}


def _limit(path: str, tp: float) -> None:
    lim = 10 ** ((tp - 0.3) / 20)
    tmp = path + ".lim.wav"
    ffmpeg(["-i", path, "-af", f"alimiter=limit={lim:.4f}:attack=2:release=50:level=false", "-ar", "48000", "-c:a", "pcm_s16le", tmp])
    Path(tmp).replace(path)


def loudnorm(src: str, dst: str, target: float = -14.0, tp: float = -1.0) -> dict:
    """İki geçişli loudnorm (5.13): 1. geçiş ölçer, 2. geçiş doğrusal uygular. Ölçülen LRA hedef LRA'dan büyükse ffmpeg doğrusal
    moddan dinamik moda düşer ve hedefi kaçırabilir; bu yüzden LRA hedefi ölçülen değerin altına çekilmez (en az 11). Doğrulama
    pyloudnorm ile; hedeften > 0,5 LU sapma kalırsa doğrusal kazanç + tepe sınırlayıcı yedeği uygulanır ve yeniden ölçülür."""
    m0 = _loudnorm_pass1(src, target, tp)
    lra = max(11.0, min(50.0, float(m0["input_lra"]) + 1.0))
    m = _loudnorm_pass1(src, target, tp, lra) if lra != 11.0 else m0
    af = (f"loudnorm=I={target}:TP={tp}:LRA={lra}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true:print_format=json")
    ffmpeg(["-i", src, "-af", af, "-ar", "48000", "-c:a", "pcm_s16le", dst])
    v = measure(dst)
    if v["true_peak_dbtp"] > tp + 0.05:  # doğrusal mod tepe sınırını aşarsa hafif limiter + yeniden ölç
        _limit(dst, tp)
        v = measure(dst)
    method = "loudnorm_linear"
    if abs(v["lufs"] - target) > 0.5:
        src_l = measure(src)["lufs"]
        gain = target - src_l
        ffmpeg(["-i", src, "-af", f"volume={gain:.3f}dB", "-ar", "48000", "-c:a", "pcm_s16le", dst])
        if measure(dst)["true_peak_dbtp"] > tp + 0.05:
            _limit(dst, tp)
            v1 = measure(dst)
            if abs(v1["lufs"] - target) > 0.5:  # sınırlayıcı seviyeyi düşürdüyse bir kez telafi et
                ffmpeg(["-i", dst, "-af", f"volume={target - v1['lufs']:.3f}dB,alimiter=limit={10 ** ((tp - 0.3) / 20):.4f}:attack=2:release=50:level=false",
                        "-ar", "48000", "-c:a", "pcm_s16le", dst + ".t.wav"])
                Path(dst + ".t.wav").replace(dst)
        v = measure(dst)
        method = "linear_gain_limiter"
    ok = abs(v["lufs"] - target) <= 1.0 and v["true_peak_dbtp"] <= tp + 0.05
    return {"out": dst, "pass1": {k: m[k] for k in ("input_i", "input_tp", "input_lra")}, "verify": v, "ok": ok, "method": method,
            "lra_target": lra, "target": {"lufs": target, "tp": tp}}


def phone(src: str, dst: str) -> dict:
    ffmpeg(["-i", src, "-af", "highpass=f=300,lowpass=f=3400,pan=mono|c0=0.5*c0+0.5*c1", "-ar", "48000", "-c:a", "pcm_s16le", dst])
    return {"out": dst, "note": "Küçük hoparlör simülasyonu. Ölçüm, sesin doğal ya da anlaşılır olduğunu tek başına doğrulamaz; dinleyen, dosya sürümü ve sonuç S11/S13 çıktısına yazılır."}


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("clean", "loudnorm", "phone"):
        p = sp.add_parser(name)
        p.add_argument("--in", dest="src", required=True)
        p.add_argument("--out", required=True)
        if name == "loudnorm":
            p.add_argument("--target", type=float, default=-14.0)
            p.add_argument("--tp", type=float, default=-1.0)
    p = sp.add_parser("duck")
    p.add_argument("--music", required=True)
    p.add_argument("--voice", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--duck-db", type=float, default=4.5)
    p = sp.add_parser("measure")
    p.add_argument("--in", dest="src", required=True)
    a = ap.parse_args()
    if a.cmd == "clean":
        emit(clean(a.src, a.out))
    elif a.cmd == "duck":
        emit(duck(a.music, a.voice, a.out, a.duck_db))
    elif a.cmd == "loudnorm":
        emit(loudnorm(a.src, a.out, a.target, a.tp))
    elif a.cmd == "phone":
        emit(phone(a.src, a.out))
    else:
        emit(measure(a.src))


if __name__ == "__main__":
    main()
