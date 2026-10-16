"""Teknik QC kontrolleri (spec bölüm 10, 5.15, 5.19): siyah kare/donma tespiti, güvenli alan, teknik özellikler.

Alt komutlar:
  black   --video v.mp4                       blackdetect + freezedetect (bütün video; örnek karelerden karar verilmez)
  safe    --plan plan.json                    yazı katmanlarının güvenli alanda ve ≥ 1,5 sn ekranda olup olmadığı
  tech    --video v.mp4 [--plan plan.json] [--expect-duration 15] [--format 9x16]
          süre, çözünürlük, fps, codec/profil, yuv420p, AAC 48 kHz, faststart, -14 LUFS ±1, ≤ -1 dBTP, siyah/donma, güvenli alan
Teknik geçer kararı görsel/işitsel insan kontrolünün yerine geçmez (5.15 sınırı).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "audio"))
from common import emit, ffmpeg, ffprobe_json, read_json  # noqa: E402

FORMAT_SIZE = {"9x16": (1080, 1920), "4x5": (1080, 1350), "1x1": (1080, 1080)}
SAFE = {"9x16": {"top": 0.14, "bottom": 0.35, "side": 0.06}, "4x5": {"top": 250 / 1350, "bottom": 250 / 1350, "side": 100 / 1080},
        "1x1": {"top": 0.08, "bottom": 0.08, "side": 0.08}}


def black_freeze(video: str, black_min: float = 0.12, freeze_min: float = 0.5) -> dict:
    r = ffmpeg(["-i", video, "-vf", f"blackdetect=d={black_min}:pix_th=0.06,freezedetect=n=0.002:d={freeze_min}", "-an", "-f", "null", "-"], check=False)
    blacks = [{"start": float(a), "end": float(b), "dur": float(c)} for a, b, c in
              re.findall(r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)", r.stderr)]
    fstarts = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", r.stderr)]
    fdurs = [float(x) for x in re.findall(r"freeze_duration: ([\d.]+)", r.stderr)]
    freezes = [{"start": s, "dur": d} for s, d in zip(fstarts, fdurs)]
    return {"black_segments": blacks, "freeze_segments": freezes, "ok": not blacks and not freezes}


def _text_y(layer: dict, scene_role: str, fmt: str, title_y: float) -> float:
    anchor = layer.get("anchor")
    if anchor == "safe_top":
        return title_y + 0.02
    if anchor == "safe_bottom":
        return 0.58 if fmt == "9x16" else 0.72
    if anchor == "center":
        return 0.42
    y = (layer.get("props") or {}).get("y")
    return float(y) if y is not None else title_y + 0.02


def safe_zone(plan: dict, style: dict | None = None) -> dict:
    fmt = plan["format"]
    z = SAFE[fmt]
    title_y = ((style or {}).get("layout") or {}).get(fmt, {}).get("titleY", 0.12)
    issues, checked = [], 0
    for s in plan["scenes"]:
        for i, l in enumerate(s["layers"]):
            is_text = l.get("type") == "text" or l.get("component") in ("TextReveal", "KineticWords", "SoftType", "LowerThird", "PriceTag", "CaptionTrack", "CTAPulse")
            if not is_text:
                continue
            checked += 1
            y = _text_y(l, s["role"], fmt, title_y)
            if y < z["top"] - 1e-6 or y > 1 - z["bottom"] + 1e-6:
                issues.append({"scene": s["id"], "layer": i, "y": round(y, 3), "issue": f"yazı güvenli alan dışında ({fmt}: üst %{z['top']*100:.0f}, alt %{z['bottom']*100:.0f})"})
            dur = float(l.get("dur_s", s["dur_s"] - float(l.get("start_s", 0))))
            if dur < 1.5:
                issues.append({"scene": s["id"], "layer": i, "issue": f"yazı {dur:.2f} sn ekranda (< 1,5 sn)"})
    return {"checked_text_layers": checked, "issues": issues, "ok": not issues}


def tech(video: str, plan: dict | None, expect_duration: float | None, fmt: str | None) -> dict:
    import loudness as LN
    info = ffprobe_json(video)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), {})
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur = float(info["format"].get("duration") or 0)
    fmt = fmt or (plan or {}).get("format")
    res: dict = {"file": video, "checks": []}
    def check(name, ok, detail):
        res["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
    if fmt:
        w, h = FORMAT_SIZE[fmt]
        check("çözünürlük", v.get("width") == w and v.get("height") == h, f"{v.get('width')}×{v.get('height')} (beklenen {w}×{h})")
    fps_ok = v.get("r_frame_rate") in ("30/1", "30000/1000") and v.get("avg_frame_rate") in ("30/1", "30000/1000")
    check("fps 30 CFR", fps_ok, f"r={v.get('r_frame_rate')} avg={v.get('avg_frame_rate')}")
    check("codec H.264 High", v.get("codec_name") == "h264" and (v.get("profile") or "").lower().startswith("high"), f"{v.get('codec_name')} {v.get('profile')}")
    check("yuv420p", v.get("pix_fmt") == "yuv420p", v.get("pix_fmt"))
    exp = expect_duration or (plan or {}).get("duration_s")
    if exp:
        check("süre", abs(dur - float(exp)) <= 1 / 30 + 0.05, f"{dur:.3f} sn (beklenen {exp})")
    if a:
        check("ses AAC 48 kHz", a.get("codec_name") == "aac" and str(a.get("sample_rate")) == "48000", f"{a.get('codec_name')} {a.get('sample_rate')}")
        m = LN.measure(video)
        check("loudness -14 LUFS ±1", abs(m["lufs"] + 14) <= 1.0, f"{m['lufs']} LUFS")
        check("tepe ≤ -1 dBTP", m["true_peak_dbtp"] <= -1.0 + 0.05, f"{m['true_peak_dbtp']} dBTP")
    else:
        check("ses", False, "ses akışı yok")
    with open(video, "rb") as f:
        head = f.read(1 << 16)
    moov, mdat = head.find(b"moov"), head.find(b"mdat")
    check("+faststart", moov != -1 and (mdat == -1 or moov < mdat), "moov başta" if moov != -1 else "moov baştaki 64 KB'da yok")
    bf = black_freeze(video)
    check("siyah kare/donma yok", bf["ok"], {"black": bf["black_segments"], "freeze": bf["freeze_segments"]})
    if plan:
        sz = safe_zone(plan)
        check("yazılar güvenli alanda ve ≥ 1,5 sn", sz["ok"], sz["issues"])
    res["ok"] = all(c["ok"] for c in res["checks"])
    res["note"] = "Teknik QC; görsel ve işitsel insan kontrolünün yerine geçmez (5.15)."
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("black")
    p.add_argument("--video", required=True)
    p = sp.add_parser("safe")
    p.add_argument("--plan", required=True)
    p.add_argument("--style")
    p = sp.add_parser("tech")
    p.add_argument("--video", required=True)
    p.add_argument("--plan")
    p.add_argument("--expect-duration", type=float)
    p.add_argument("--format")
    a = ap.parse_args()
    if a.cmd == "black":
        emit(black_freeze(a.video))
    elif a.cmd == "safe":
        emit(safe_zone(read_json(a.plan), read_json(a.style) if a.style else None))
    else:
        r = tech(a.video, read_json(a.plan) if a.plan else None, a.expect_duration, a.format)
        emit(r)
        sys.exit(0 if r["ok"] else 1)


if __name__ == "__main__":
    main()
