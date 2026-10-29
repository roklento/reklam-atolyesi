"""Tasarım sesleri kodla sentez (spec 5.9): whoosh, shimmer, riser, impact, pop, tone. Deterministik (tohumlu).

Kullanım: sfx_synth.py --kind whoosh --dur 0.6 --out whoosh.wav [--seed 7] [--gain-db -6]
Organik sesler (kağıt, kumaş, sıvı…) önce ses kütüphanesinden (sfx_library.py), yoksa ElevenLabs sfx ile, fiyat ve onayla; burası
yalnızca tasarım sesleri.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit  # noqa: E402

SR = 48000
KINDS = ("whoosh", "shimmer", "riser", "impact", "pop", "tone")


def _env(n: int, a: float, r: float) -> np.ndarray:
    t = np.linspace(0, 1, n)
    return np.clip(t / max(a, 1e-3), 0, 1) * np.clip((1 - t) / max(r, 1e-3), 0, 1)


def synth(kind: str, dur: float, seed: int = 7, freq: float = 440.0) -> np.ndarray:
    from scipy import signal
    rng = np.random.default_rng(seed)
    n = int(SR * dur)
    t = np.arange(n) / SR
    if kind == "whoosh":
        x = rng.standard_normal(n)
        sweep = np.geomspace(300, 4000, n)
        out = np.zeros(n)
        for i in range(0, n, 1024):
            f = sweep[i]
            b, a_ = signal.butter(2, [max(50, f * 0.6) / (SR / 2), min(0.99, f * 1.6 / (SR / 2))], btype="band")
            seg = x[max(0, i - 2048): i + 1024]
            out[i:i + 1024] = signal.lfilter(b, a_, seg)[-min(1024, n - i):]
        y = out * _env(n, 0.45, 0.4)
    elif kind == "shimmer":
        y = sum(np.sin(2 * np.pi * f * t) * (0.6 ** k) for k, f in enumerate([2093, 2637, 3136, 4186]))
        y = y * (0.6 + 0.4 * np.sin(2 * np.pi * 9 * t)) * _env(n, 0.1, 0.7)
    elif kind == "riser":
        f = np.geomspace(150, 1800, n)
        y = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.5 + rng.standard_normal(n) * 0.15 * np.linspace(0.2, 1, n)
        y = y * np.linspace(0.05, 1, n) ** 2 * _env(n, 0.05, 0.03)
    elif kind == "impact":
        thump = np.sin(2 * np.pi * 55 * t) * np.exp(-t * 9)
        b, a_ = signal.butter(2, 900 / (SR / 2))
        burst = signal.lfilter(b, a_, rng.standard_normal(n)) * np.exp(-t * 30)
        y = thump + burst * 0.6
    elif kind == "pop":
        y = np.sin(2 * np.pi * 880 * t * (1 - t * 2)) * np.exp(-t * 60)
    elif kind == "tone":
        y = np.sin(2 * np.pi * freq * t) * _env(n, 0.02, 0.05)
    else:
        raise SystemExit(f"tür: {KINDS}")
    y = y / (np.max(np.abs(y)) + 1e-9) * 0.8
    return np.stack([y, y], axis=1).astype(np.float32)


def write(path: str, y: np.ndarray, gain_db: float = -6.0) -> dict:
    import soundfile as sf
    y = y * (10 ** (gain_db / 20))
    fade = int(SR * 0.005)
    if len(y) > 2 * fade:
        ramp = np.linspace(0, 1, fade)[:, None]
        y[:fade] *= ramp
        y[-fade:] *= ramp[::-1]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, y, SR, subtype="PCM_16")
    return {"out": path, "dur_s": round(len(y) / SR, 3), "peak_dbfs": round(20 * np.log10(np.max(np.abs(y)) + 1e-9), 2)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True, choices=KINDS)
    ap.add_argument("--dur", type=float, default=0.6)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--freq", type=float, default=440.0)
    ap.add_argument("--gain-db", type=float, default=-6.0)
    a = ap.parse_args()
    emit({"kind": a.kind, **write(a.out, synth(a.kind, a.dur, a.seed, a.freq), a.gain_db)})


if __name__ == "__main__":
    main()
