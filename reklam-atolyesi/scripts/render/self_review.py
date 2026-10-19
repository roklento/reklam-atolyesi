"""Görsel öz denetim döngüsü (spec 5.15): her render'dan sonra, kullanıcıya göstermeden önce.

1. Sahne başlarından ve ortalarından kareler + saniyede 1 karelik kontak sayfası (Claude görüntülere bakar).
2. Sayısal kontroller: yazı süresi ve güvenli alan, beat_lock ↔ beats.json (≤ 3 kare), efekt bütçesi, ses seviyesi, bütün videoda
   siyah kare/donma, slayt gösterisi riski (qc/slideshow.py; critical → düzeltilecek bulgu, high → uyarı). Geçişler ve AI sahneler için daha sık kareler. Örnek karelerden bütün video için geçer kararı verilmez.
3. Sorun varsa plan düzeltilip yeniden render (en fazla 3 tur; tur sayısı --round ile izlenir). Kalan sorun kullanıcıya söylenir.
Sınır: akıcılık, kısa süreli ürün bozulması ve ses için tam oynatma/dinleme gerekir; araç yapamıyorsa kullanıcı kontrolü beklenir.

Kullanım: self_review.py --video v.mp4 --plan plan.json --out-dir analysis/review_<ad> [--style s.json] [--beats beats.json] [--round 1]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analyze"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "qc"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "audio"))
from common import emit, ffmpeg, ffprobe_json, read_json, write_json  # noqa: E402
from admem import editplan  # noqa: E402
import checks as QC  # noqa: E402
import contact_sheet as CS  # noqa: E402
import slideshow as SS  # noqa: E402

MAX_ROUNDS = 3


def review(video: str, plan: dict, out_dir: Path, style: dict | None, beats: list[float] | None, rnd: int) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    dur = float(ffprobe_json(video)["format"]["duration"])
    times: list[float] = []
    dense: list[float] = []
    for s in plan["scenes"]:
        times += [s["start_s"] + 0.05, s["start_s"] + s["dur_s"] / 2]
        if (s.get("transition_out") or {}).get("type", "cut") != "cut":
            b = s["start_s"] + s["dur_s"]
            dense += [b - 0.15, b - 0.05, b + 0.05, b + 0.15]
        if any((l.get("source") or {}).get("kind") in ("ai_clip", "ai_image") for l in s["layers"]):
            dense += [s["start_s"] + s["dur_s"] * k / 6 for k in range(1, 6)]
    times = [min(max(0.0, t), dur - 0.05) for t in times]
    dense = [min(max(0.0, t), dur - 0.05) for t in dense]
    key = CS.sheet(video, str(out_dir / "scene_frames.jpg"), cols=min(6, len(times)), rows=(len(times) + 5) // 6, times=times)
    per_s = CS.sheet(video, str(out_dir / "contact_1fps.jpg"), per_second=True)
    dense_sheet = CS.sheet(video, str(out_dir / "dense_frames.jpg"), cols=min(6, max(1, len(dense))), rows=max(1, (len(dense) + 5) // 6),
                           times=dense) if dense else None
    val = editplan.validate(plan, style=style, beats=beats)
    sz = QC.safe_zone(plan, style)
    bf = QC.black_freeze(video)
    audio = None
    if any(s["codec_type"] == "audio" for s in ffprobe_json(video)["streams"]):
        import loudness as LN
        audio = LN.measure(video)
    findings = []
    findings += [{"kind": "plan", "msg": e} for e in val["errors"]]
    findings += [{"kind": "safe_zone", "msg": i["issue"], "scene": i["scene"]} for i in sz["issues"]]
    if not bf["ok"]:
        findings.append({"kind": "black_freeze", "msg": f"siyah {len(bf['black_segments'])} / donma {len(bf['freeze_segments'])} bölüm", "detail": bf})
    if audio and (abs(audio["lufs"] + 14) > 1 or audio["true_peak_dbtp"] > -0.95):
        findings.append({"kind": "loudness", "msg": f"{audio['lufs']} LUFS / {audio['true_peak_dbtp']} dBTP (hedef -14 / ≤ -1)"})
    slide = SS.slideshow_risk(plan, video)
    warnings = list(val["warnings"])
    if slide["level"] == "critical":
        findings.append({"kind": "slideshow_risk", "msg": f"slayt gösterisi riski kritik ({slide['score']}; başlıca: {', '.join(slide['main_drivers'])})",
                         "detail": slide})
    elif slide["level"] == "high":
        warnings.append(f"slayt gösterisi riski yüksek ({slide['score']}; başlıca: {', '.join(slide['main_drivers'])}) — hareketli çekim, "
                        "sahne çeşitliliği ya da açılışta hareket düşünülmeli")
    res = {"round": rnd, "max_rounds": MAX_ROUNDS, "video": video, "duration": dur,
           "frames_to_inspect": [key["sheet"], per_s["sheet"]] + ([dense_sheet["sheet"]] if dense_sheet else []),
           "numeric_findings": findings, "warnings": warnings, "loudness": audio, "slideshow_risk": slide,
           "needs_human": ["akıcılık ve tam oynatma", "kısa süreli ürün bozulması (AI sahneler)", "ses dinleme/telefon testi",
                           "ilk saniye kaydırmayı durdurur mu, marka gibi duruyor mu (insan kapısı)"],
           "next": ("Düzelt ve yeniden render et" if findings and rnd < MAX_ROUNDS else
                    ("3 tur doldu: kalan sorunları kullanıcıya açıkça söyle" if findings else "Sayısal kontroller geçti; karelere bak, gözlemini yaz"))}
    write_json(out_dir / f"self_review_r{rnd}.json", res)
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--style")
    ap.add_argument("--beats")
    ap.add_argument("--round", type=int, default=1)
    a = ap.parse_args()
    beats = None
    if a.beats:
        b = read_json(a.beats)
        beats = b.get("beats") if isinstance(b, dict) else b
    emit(review(a.video, read_json(a.plan), Path(a.out_dir), read_json(a.style) if a.style else None, beats, a.round))


if __name__ == "__main__":
    main()
