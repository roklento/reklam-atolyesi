"""Vuruş haritası (spec 5.8, 5.13): librosa ile tempo, vuruşlar, başlangıçlar (onset), enerji eğrisi → beats.json.

Kullanım: beats.py --audio music.wav --out beats.json
Kesim kuralı (5.2): aksiyon kesimi en yakın vuruşa ≤ 3 kare ise vuruşa yaslanır; beat_lock anları vuruşa kilitlenir (snap()).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit, write_json  # noqa: E402


def analyze(path: str) -> dict:
    import librosa
    y, sr = librosa.load(path, sr=22050, mono=True)
    if y.size == 0:
        raise SystemExit("boş ses dosyası")
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    beats = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, units="time").tolist()
    rms = librosa.feature.rms(y=y, hop_length=int(sr * 0.25))[0]
    energy = (rms / (rms.max() + 1e-9)).round(4).tolist()
    downbeats: list[float] = []
    if beats:
        strength = [float(onset_env[min(len(onset_env) - 1, int(f))]) for f in beat_frames]
        best_phase = max(range(4), key=lambda ph: sum(strength[ph::4]) if strength[ph::4] else 0)
        downbeats = beats[best_phase::4]
    t = float(np.atleast_1d(tempo)[0])
    return {"source": path, "tempo_bpm": round(t, 2), "beats": [round(b, 4) for b in beats], "downbeats": [round(b, 4) for b in downbeats],
            "onsets": [round(o, 4) for o in onsets], "energy_step_s": 0.25, "energy": energy, "duration_s": round(len(y) / sr, 3),
            "locks": sorted(set(round(b, 4) for b in beats))}


def snap(t: float, beats: list[float], fps: int = 30, max_frames: int = 3) -> float:
    """Aksiyon kesimini en yakın vuruşa yaslar (≤ max_frames kare ise); değilse aksiyonda bırakır."""
    if not beats:
        return t
    b = min(beats, key=lambda x: abs(x - t))
    return round(b, 4) if abs(b - t) * fps <= max_frames + 1e-9 else t


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    res = analyze(a.audio)
    sha = write_json(a.out, res)
    emit({"out": a.out, "sha256": sha, "tempo_bpm": res["tempo_bpm"], "beats": len(res["beats"]), "downbeats": len(res["downbeats"])})


if __name__ == "__main__":
    main()
