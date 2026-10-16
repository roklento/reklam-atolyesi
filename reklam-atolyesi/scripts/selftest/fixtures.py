"""Nötr sentetik fikstürler (spec 12.12, ilke 12): FFmpeg test desenleri, soyut şekiller, "Ürün A" yer tutucusu.
Gerçek ürün türü, marka, sezon ya da kişi içermez. Bütün üretim deterministiktir.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import ffmpeg  # noqa: E402


def clip_plain(path: Path, w: int, h: int, dur: float = 4.0, fps: int = 30, audio: str | None = "tone") -> Path:
    a = []
    if audio == "tone":
        a = ["-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}:sample_rate=48000"]
    elif audio == "speechlike":
        a = ["-f", "lavfi", "-i", f"anoisesrc=d={dur}:c=pink:r=48000:a=0.4:seed=1729,bandpass=f=1000:w=1800,volume='0.6+0.4*sin(2*PI*3*t)':eval=frame"]
    ffmpeg(["-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate={fps}:duration={dur}", *a,
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", *(["-c:a", "aac", "-shortest"] if a else []), str(path)])
    return path


def clip_vfr(path: Path, w: int, h: int, dur: float = 4.0) -> Path:
    """Değişken kare hızlı (telefon benzeri) klip."""
    ffmpeg(["-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate=60:duration={dur}", "-f", "lavfi", "-i", f"sine=frequency=330:duration={dur}",
            "-vf", "select='not(mod(n\\,3))+not(mod(n\\,5))',setpts=N/(37*TB)", "-fps_mode", "vfr",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)])
    return path


def clip_hlg(path: Path, w: int, h: int, dur: float = 3.0) -> Path:
    """HLG (arib-std-b67) işaretli klip."""
    ffmpeg(["-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate=30:duration={dur}", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc",
            "-bsf:v", "h264_metadata=colour_primaries=9:transfer_characteristics=18:matrix_coefficients=9", str(path)])
    return path


def clip_shaky(path: Path, w: int, h: int, dur: float = 4.0) -> Path:
    """Sarsıntılı (el kamerası benzeri) klip: büyük desenden titreyen kırpma."""
    W, H = int(w * 1.25), int(h * 1.25)
    mx, my = (W - w) // 2, (H - h) // 2
    ffmpeg(["-f", "lavfi", "-i", f"testsrc2=size={W}x{H}:rate=30:duration={dur}",
            "-vf", f"crop={w}:{h}:x='{mx}+{int(mx*0.8)}*sin(n*1.9)*sin(n*0.37)':y='{my}+{int(my*0.8)}*sin(n*2.3+1)*cos(n*0.41)'",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(path)])
    return path


def photo_exif(path: Path, w: int = 1200, h: int = 900, orientation: int = 6) -> Path:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), (200, 200, 200))
    d = ImageDraw.Draw(im)
    d.rectangle([w * 0.3, h * 0.2, w * 0.7, h * 0.8], fill=(235, 235, 235), outline=(90, 90, 90), width=6)
    d.text((w * 0.42, h * 0.48), "Ürün A", fill=(60, 60, 60))
    exif = Image.Exif()
    exif[0x0112] = orientation
    im.save(path, "JPEG", exif=exif.tobytes(), quality=92)
    return path


def photo_heic(path: Path, w: int = 800, h: int = 600) -> Path:
    import pillow_heif
    from PIL import Image
    pillow_heif.register_heif_opener()
    im = Image.new("RGB", (w, h), (180, 180, 185))
    im.save(path, format="HEIF", quality=85)
    return path


def click_track(path: Path, bpm: float = 120.0, dur: float = 12.0, sr: int = 48000) -> Path:
    import soundfile as sf
    n = int(sr * dur)
    y = np.zeros(n, np.float32)
    step = 60.0 / bpm
    t = 0.0
    k = 0
    while t < dur:
        i = int(t * sr)
        L = int(0.03 * sr)
        amp = 0.9 if k % 4 == 0 else 0.5
        seg = amp * np.sin(2 * np.pi * (1000 if k % 4 == 0 else 700) * np.arange(L) / sr) * np.exp(-np.arange(L) / (0.006 * sr))
        y[i:i + L] += seg[: max(0, min(L, n - i))]
        t += step
        k += 1
    pad = 0.05 * np.sin(2 * np.pi * 110 * np.arange(n) / sr)
    sf.write(str(path), np.stack([y + pad, y + pad], axis=1), sr)
    return path


def noisy_voice(path: Path, dur: float = 4.0, sr: int = 48000) -> Path:
    import soundfile as sf
    rng = np.random.default_rng(1729)
    t = np.arange(int(sr * dur)) / sr
    voice = 0.3 * np.sin(2 * np.pi * 220 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 4 * t))
    noise = 0.05 * rng.standard_normal(t.size)
    sf.write(str(path), np.stack([voice + noise] * 2, axis=1).astype(np.float32), sr)
    return path
