"""Renk ayarı LUT'ları (spec 5.6, 5.12): .cube üretimi ve önizleme uygulaması.

Alt komutlar:
  identity --out luts/identity.cube [--size 17]                       nötr (değişiklik yapmayan) LUT
  make     --out luts/yon-a.cube [--contrast 1.0 --temperature 0.0 --saturation 1.0 --lift 0.0 --gain 1.0] [--size 33]
           Parametre değerleri S08'deki yön kararından gelir; burada varsayılanların hepsi nötrdür.
  apply    --lut x.cube --in frame.png --out frame_graded.png         (önizleme)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import atomic_write, emit, ffmpeg  # noqa: E402


def make_cube(size: int, contrast: float = 1.0, temperature: float = 0.0, saturation: float = 1.0, lift: float = 0.0, gain: float = 1.0,
              title: str = "reklam-atolyesi") -> str:
    lines = [f'TITLE "{title}"', f"LUT_3D_SIZE {size}", "DOMAIN_MIN 0.0 0.0 0.0", "DOMAIN_MAX 1.0 1.0 1.0"]
    grid = np.linspace(0, 1, size)
    for b in grid:
        for g in grid:
            for r in grid:
                c = np.array([r, g, b])
                c = lift + c * (gain - lift)
                c = (c - 0.5) * contrast + 0.5
                c = c + np.array([temperature, 0.0, -temperature]) * 0.1
                lum = float(np.dot(c, [0.2126, 0.7152, 0.0722]))
                c = lum + (c - lum) * saturation
                c = np.clip(c, 0, 1)
                lines.append(f"{c[0]:.6f} {c[1]:.6f} {c[2]:.6f}")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("identity")
    p.add_argument("--out", required=True)
    p.add_argument("--size", type=int, default=17)
    p = sp.add_parser("make")
    p.add_argument("--out", required=True)
    p.add_argument("--size", type=int, default=33)
    for k, d in (("--contrast", 1.0), ("--temperature", 0.0), ("--saturation", 1.0), ("--lift", 0.0), ("--gain", 1.0)):
        p.add_argument(k, type=float, default=d)
    p.add_argument("--title", default="reklam-atolyesi")
    p = sp.add_parser("apply")
    p.add_argument("--lut", required=True)
    p.add_argument("--in", dest="src", required=True)
    p.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "identity":
        emit({"out": a.out, "sha256": atomic_write(a.out, make_cube(a.size, title="identity (nötr)"))})
    elif a.cmd == "make":
        emit({"out": a.out, "sha256": atomic_write(a.out, make_cube(a.size, a.contrast, a.temperature, a.saturation, a.lift, a.gain, a.title))})
    else:
        lp = Path(a.lut).as_posix().replace(":", "\\:")
        ffmpeg(["-i", a.src, "-vf", f"lut3d='{lp}'", a.out])
        emit({"out": a.out})


if __name__ == "__main__":
    main()
