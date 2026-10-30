"""Sahne sesi uygulaması ve miks (spec 5.13, S11).

Sahne başına audio.mode: original (çekim sesi aynen) · original_clean (afftdn ile temizlenmiş) · user_vo (kullanıcı kaydı) ·
generated (çekim sesi kaldırılır; üretilmiş VO/müzik/efekt) · none (çekim sesi kaldırılır; müzik + efekt).
Çekim sesi ile üretilmiş ses arasındaki geçişler kısa çapraz geçişle; müzik VO/konuşmanın 4–5 dB altında + sidechain; konuşma
sırasında ses efektleri de kısılır (varsayılan 6 dB; konuşma hiçbir zaman efekt yüzünden kısılmaz — 1.5.0);
efektler kare hassasiyetinde; iki geçişli loudnorm → -14 LUFS, ≤ -1 dBTP. Stem'ler ayrı yazılır.

Kullanım: mix.py --plan plan.json --scene-audio scenes_map.json [--music m.wav] [--vo vo.wav] [--sfx-dir dir] --out-dir audio/stems
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit, read_json, write_json  # noqa: E402
import loudness as LN  # noqa: E402

SR = 48000
XFADE = 0.03


def _read(path: str | None, dur: float | None = None) -> np.ndarray | None:
    if not path or not Path(path).exists():
        return None
    import soundfile as sf
    y, sr = sf.read(path, always_2d=True, dtype="float32")
    if sr != SR:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(sr, SR)
        y = resample_poly(y, SR // g, sr // g, axis=0).astype(np.float32)
    if y.shape[1] == 1:
        y = np.repeat(y, 2, axis=1)
    if dur is not None:
        n = int(dur * SR)
        y = y[:n] if len(y) >= n else np.pad(y, ((0, n - len(y)), (0, 0)))
    return y


def _place(track: np.ndarray, clip: np.ndarray, at_s: float, fade_s: float = XFADE) -> None:
    i = int(round(at_s * SR))
    if i < 0:  # negatif konum (ör. music.offset_s < 0): parçanın başı videodan önce kalır, kesilir (2.0.0: önceden dizi hatası)
        clip, i = clip[-i:], 0
    if i >= len(track) or not len(clip):
        return
    c = clip[: len(track) - i].copy()
    f = min(int(fade_s * SR), len(c) // 2)
    if f > 0:
        ramp = np.linspace(0, 1, f, dtype=np.float32)[:, None]
        c[:f] *= ramp
        c[-f:] *= ramp[::-1]
    track[i:i + len(c)] += c


def _write(path: Path, y: np.ndarray, subtype: str = "PCM_16") -> str:
    import soundfile as sf
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), y if subtype == "FLOAT" else np.clip(y, -1, 1), SR, subtype=subtype)
    return str(path)


def speech_activity(y: np.ndarray, frame_s: float = 0.02, thresh: float = 0.005, hold_s: float = 0.12) -> np.ndarray:
    """Konuşma maskesi 20 ms pencerelerin RMS'inden (≈ -46 dBFS eşik) + 120 ms tutma. 2.0.0: önceden örnek başına |x| > 0,01
    bakılıyordu; konuşmanın sıfır geçişleri maskeyi delik deşik ediyor, 150 ms yumuşatmadan sonra müzik 4,5 dB yerine ~2–3 dB kısılıyordu."""
    n = len(y)
    f = max(1, int(frame_s * SR))
    m = int(np.ceil(n / f))
    mono = np.abs(y).max(axis=1) if y.ndim == 2 else np.abs(y)
    pad = np.pad(mono.astype(np.float64), (0, m * f - n))
    active = np.sqrt((pad.reshape(m, f) ** 2).mean(axis=1)) > thresh
    h = int(np.ceil(hold_s / frame_s))
    if h and active.any():
        active = np.convolve(active.astype(int), np.ones(2 * h + 1, int), mode="same") > 0
    return np.repeat(active, f)[:n]


def mix(plan: dict, scene_audio: dict, music: str | None, vo: str | None, sfx: dict[str, str], out_dir: Path,
        duck_db: float = 4.5, sfx_duck_db: float = 6.0) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    total = float(plan["duration_s"])
    n = int(total * SR)
    dialog = np.zeros((n, 2), np.float32)
    effects = np.zeros((n, 2), np.float32)
    applied = []
    speech_mask = np.zeros(n, bool)
    for s in plan["scenes"]:
        mode = s["audio"]["mode"]
        seg_path = scene_audio.get(s["id"])
        if mode in ("original", "original_clean") and seg_path:
            src = seg_path
            if mode == "original_clean":
                cleaned = out_dir / f"{s['id']}_clean.wav"
                LN.clean(seg_path, str(cleaned))
                src = str(cleaned)
            clip = _read(src, s["dur_s"])
            if clip is not None:
                _place(dialog, clip, s["start_s"])
                a, b = int(s["start_s"] * SR), int((s["start_s"] + s["dur_s"]) * SR)
                speech_mask[a:b] = True
        applied.append({"scene": s["id"], "mode": mode, "source": seg_path if mode in ("original", "original_clean") else None})
        for cue in s.get("audio_cues", []) or []:
            p = sfx.get(cue.get("sfx", ""))
            clip = _read(p)
            if clip is not None:
                _place(effects, clip * (10 ** (float(cue.get("gain_db", 0)) / 20)), s["start_s"] + float(cue["at_s"]), 0.004)
    vo_track = np.zeros((n, 2), np.float32)
    vo_clip = _read(vo, total) if vo and any(s["audio"]["mode"] in ("generated", "user_vo") for s in plan["scenes"]) else None
    if vo_clip is not None:
        for s in plan["scenes"]:
            if s["audio"]["mode"] in ("generated", "user_vo"):
                a, b = int(s["start_s"] * SR), int((s["start_s"] + s["dur_s"]) * SR)
                vo_track[a:b] = vo_clip[a:b]
                speech_mask[a:b] |= speech_activity(vo_clip[a:b])
    if speech_mask.any() and np.abs(effects).max() > 0:  # konuşma üstüne gelen efekt kısılır, konuşma değil
        k = int(0.08 * SR)
        senv = np.convolve(np.where(speech_mask, 10 ** (-sfx_duck_db / 20), 1.0), np.ones(k) / k, mode="same").astype(np.float32)
        effects *= senv[:, None]
    music_track = np.zeros((n, 2), np.float32)
    m = _read(music, total)
    if m is not None:
        off = float((plan.get("music") or {}).get("offset_s", 0.0))
        g = 10 ** (float((plan.get("music") or {}).get("gain_db", -6.0)) / 20)
        _place(music_track, m * g, off, 0.5)
        env = np.where(speech_mask, 10 ** (-duck_db / 20), 1.0).astype(np.float32)
        k = int(0.15 * SR)
        env = np.convolve(env, np.ones(k) / k, mode="same").astype(np.float32)
        music_track *= env[:, None]
    stems = {"dialog": _write(out_dir / "stem_dialog.wav", dialog), "vo": _write(out_dir / "stem_vo.wav", vo_track),
             "music": _write(out_dir / "stem_music.wav", music_track), "sfx": _write(out_dir / "stem_sfx.wav", effects)}
    pre = dialog + vo_track + music_track + effects
    # 2.0.0: ara miks kayan noktada ve kırpılmadan yazılır; loudnorm seviyeyi ve tepeyi ayarlar. Önceden PCM16'ya ±1'de kırpılıyordu:
    # yüksek müzik + VO + efekt toplamı 1,25'i aşınca bozulma kalıcı oluyordu.
    pre_path = _write(out_dir / "mix_pre.wav", pre, "FLOAT")
    ln = LN.loudnorm(pre_path, str(out_dir / "mix_final.wav"))
    rep = {"stems": stems, "pre": pre_path, "final": ln["out"], "loudness": ln["verify"], "loudness_ok": ln["ok"], "applied_modes": applied,
           "duck_db": duck_db, "sfx_duck_db": sfx_duck_db}
    write_json(out_dir / "mix_report.json", rep)
    return rep


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--scene-audio", required=True, help="scenes.py çıktısı (audio_segments) ya da {sahne: wav}")
    ap.add_argument("--music")
    ap.add_argument("--vo")
    ap.add_argument("--sfx-map", help="{sfx_anahtarı: wav_yolu}")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--duck-db", type=float, default=4.5)
    a = ap.parse_args()
    sa = read_json(a.scene_audio)
    sa = sa.get("audio_segments", sa)
    rep = mix(read_json(a.plan), sa, a.music, a.vo, read_json(a.sfx_map) if a.sfx_map else {}, Path(a.out_dir), a.duck_db)
    emit(rep)


if __name__ == "__main__":
    main()
