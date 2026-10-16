"""S07 klip ölçümleri (spec 5.5): netlik, pozlama, sarsıntı, hareket, ses, kişi; puanlar (0–1) ve en iyi aralıklar.

Kullanım: measure.py --clip proxy.mp4 [--shake-permille 3.2] [--audio clip.wav] [--out clip_measure.json]
Puanlar ölçümdür; içerik eşlemesi (çekim menüsü numarası, ürün görünürlüğü) footage-analyst ajanının kontak sayfası incelemesidir.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit, write_json  # noqa: E402

SAMPLE_FPS = 4.0


def _frames(path: str, sample_fps: float = SAMPLE_FPS):
    import cv2
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(1, int(round(fps / sample_fps)))
    i = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if i % step == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            yield i / fps, frame
        i += 1
    cap.release()


def video_metrics(path: str) -> dict:
    import cv2
    face = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    rows = []
    prev = None
    for t, frame in _frames(path):
        h, w = frame.shape[:2]
        scale = 360.0 / max(h, w)
        small = cv2.resize(frame, (max(2, int(w * scale)), max(2, int(h * scale))), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        lap = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        clip_hi = float((gray >= 250).mean())
        clip_lo = float((gray <= 5).mean())
        motion = 0.0
        if prev is not None:
            flow = cv2.calcOpticalFlowFarneback(prev, gray, None, 0.5, 2, 13, 2, 5, 1.1, 0)
            motion = float(np.linalg.norm(flow, axis=2).mean())
        faces = face.detectMultiScale(gray, 1.15, 5, minSize=(24, 24)) if face is not None and not face.empty() else []
        rows.append({"t": round(t, 3), "lap": lap, "hi": clip_hi, "lo": clip_lo, "motion": motion, "faces": int(len(faces))})
        prev = gray
    return {"samples": rows}


def audio_metrics(wav: str | None) -> dict | None:
    if not wav or not Path(wav).exists():
        return None
    import soundfile as sf
    y, sr = sf.read(wav, always_2d=True)
    y = y.mean(axis=1)
    if y.size == 0:
        return None
    win = sr
    rms = []
    speech = []
    for i in range(0, len(y), win):
        seg = y[i:i + win]
        if seg.size < sr // 4:
            break
        r = math.sqrt(float(np.mean(seg ** 2)) + 1e-12)
        rms.append(20 * math.log10(r + 1e-12))
        spec = np.abs(np.fft.rfft(seg * np.hanning(seg.size)))
        freqs = np.fft.rfftfreq(seg.size, 1 / sr)
        band = spec[(freqs >= 300) & (freqs <= 3400)].sum()
        total = spec.sum() + 1e-9
        zcr = float(np.mean(np.abs(np.diff(np.sign(seg))) > 0))
        speech.append(bool(band / total > 0.55 and 0.02 < zcr < 0.25 and r > 0.01))
    if not rms:
        return None
    floor = float(np.percentile(rms, 10))
    peak = float(np.percentile(rms, 90))
    snr = peak - floor
    usability = max(0.0, min(1.0, (snr - 6) / 24)) if peak > -45 else 0.0
    return {"rms_db_per_s": [round(x, 2) for x in rms], "noise_floor_db": round(floor, 2), "level_p90_db": round(peak, 2),
            "speech_to_noise_db": round(snr, 2), "speech_seconds": int(sum(speech)), "speech_detected": sum(speech) >= 2,
            "usability": round(usability, 3)}


def scores(vm: dict, shake_permille: float | None, am: dict | None) -> dict:
    s = vm["samples"]
    if not s:
        return {"overall": 0.0}
    lap = np.array([r["lap"] for r in s])
    sharp = np.clip(np.log10(lap + 1) / 3.0, 0, 1)  # var 1000 → 1.0, 100 → 0.67, 10 → 0.35
    expo = np.clip(1 - (np.array([r["hi"] for r in s]) * 6 + np.array([r["lo"] for r in s]) * 3), 0, 1)
    stab = 1.0 if shake_permille is None else float(max(0.0, min(1.0, 1 - shake_permille / 12.0)))
    motion = np.array([r["motion"] for r in s])
    calm = float(np.clip(1 - np.median(motion) / 6.0, 0, 1))
    faces = [r["faces"] for r in s]
    person = sum(1 for f in faces if f > 0) / len(faces) >= 0.3
    overall = float(0.4 * sharp.mean() + 0.3 * expo.mean() + 0.2 * stab + 0.1 * calm)
    return {"sharpness": round(float(sharp.mean()), 3), "exposure": round(float(expo.mean()), 3), "stability": round(stab, 3),
            "motion_calm": round(calm, 3), "overall": round(overall, 3), "person_on_camera": person,
            "audio_usability": (am or {}).get("usability")}


def best_ranges(vm: dict, min_len: float = 2.0, max_len: float = 5.0, k: int = 3) -> list[dict]:
    s = vm["samples"]
    if len(s) < 2:
        return []
    t = np.array([r["t"] for r in s])
    q = np.clip(np.log10(np.array([r["lap"] for r in s]) + 1) / 3.0, 0, 1) * np.clip(1 - np.array([r["hi"] for r in s]) * 6, 0, 1)
    dt = float(np.median(np.diff(t))) if len(t) > 1 else 0.25
    cands = []
    for L in (max_len, (min_len + max_len) / 2, min_len):
        n = max(1, int(round(L / dt)))
        for i in range(0, len(s) - n + 1):
            cands.append((float(q[i:i + n].mean()), float(t[i]), float(t[i] + n * dt)))
    cands.sort(reverse=True)
    out: list[dict] = []
    for score, a, b in cands:
        if all(b <= o["in_s"] or a >= o["out_s"] for o in out):
            out.append({"in_s": round(a, 2), "out_s": round(b, 2), "score": round(score, 3)})
        if len(out) >= k:
            break
    return sorted(out, key=lambda x: x["in_s"])


def bad_ranges(vm: dict) -> dict:
    out = {"unfocused": [], "clipped_whites": []}
    for r in vm["samples"]:
        if r["lap"] < 15:
            out["unfocused"].append(r["t"])
        if r["hi"] > 0.08:
            out["clipped_whites"].append(r["t"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", required=True)
    ap.add_argument("--shake-permille", type=float)
    ap.add_argument("--audio")
    ap.add_argument("--out")
    a = ap.parse_args()
    vm = video_metrics(a.clip)
    am = audio_metrics(a.audio)
    sc = scores(vm, a.shake_permille, am)
    res = {"clip": a.clip, "score": sc, "best_ranges": best_ranges(vm), "bad": bad_ranges(vm),
           "audio": am, "samples": len(vm["samples"]),
           "audio_decision_hint": None if not am else ("konuşma var; kamerada kişi konuşuyorsa yalnızca original/original_clean"
                                                     if am["speech_detected"] and sc.get("person_on_camera") else
                                                     ("çekim sesi kullanılabilir" if (am["usability"] or 0) >= 0.5 else "çekim sesi zayıf; üretilmiş/none önerilebilir"))}
    if a.out:
        write_json(a.out, res)
    emit(res)


if __name__ == "__main__":
    main()
