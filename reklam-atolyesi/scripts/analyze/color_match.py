"""Klipler arası pozlama ve beyaz dengesi eşitleme (1.7.0).

Farklı ışıkta çekilmiş klipler yan yana gelince biri koyu ya da sarı kalır; LUT hepsine aynı uygulandığı için farkı kapatmaz. Her video
katmanının kullanılan aralığından 5 kare örneklenir, doğrusal ışıkta ölçülür:
- pozlama: ortanca parlaklık (Rec.709 ağırlıkları, doğrusal) → stop farkı,
- beyaz dengesi: düşük doygunluklu, orta parlaklıktaki piksellerin R/G ve B/G oranı (gri dünya). Böyle piksel yoksa ölçü kırpılmamış
  tüm piksellerden yazılır ama beyaz dengesi eşitlenmez, yalnız pozlama (2.0.0: sahnenin rengi ışığın rengi sanılmasın).
Referans klip `grade.match_ref` (varlık anahtarı) ya da pozlaması en iyi olan klip (ortanca orta griye en yakın, kırpılması en az).
Düzeltme LUT'tan ÖNCE `colorchannelmixer` ile kanal kazancıdır; ffmpeg gama kodlu değerle çarptığı için kazanç g^(1/2,2) yazılır.
Sınırlar: pozlama ±0,5 stop, kanal kazancı ±%12 (~±600 K renk sıcaklığı). Sınırı aşan klip düzeltilmez, "yeniden çekim adayı" olur:
büyük fark renk ayarıyla kapatılırsa gürültü/renk kayması getirir, kararı kullanıcı verir. Ölçüm eşiğin altındaysa filtre eklenmez.

Kapatma: style.json `grade.match: false` (renk doğruluğu ürünün kendisi olan kategoriler: giyim, boya, kozmetik — ürün rengi değişmesin).

Kullanım:
  color_match.py measure --clip a.mp4 [--in 1.2 --out 4.0]
  color_match.py plan --plan plan.json --assets asset_files.json [--style style.json] [--out color_match.json]
  color_match.py compare --report color_match.json --out-dir analysis/color_match   (S08: önce|sonra kareleri)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit, ffmpeg, ffprobe_json, read_json, tool, write_json  # noqa: E402

SAMPLES = 5
SW, SH = 192, 108          # ölçüm küçültmesi (en-boy önemsiz; istatistik)
GAMMA = 2.2
MID_GREY = 0.18
MAX_STOPS = 0.5
MAX_GAIN = 0.12            # kanal kazancı sapması; ~±600 K
MIN_STOPS = 0.05           # altı düzeltilmez (görünmez fark; ara dosya önbelleği boşuna bozulmaz)
MIN_GAIN = 0.01
NEUTRAL_SAT = 0.25
NEUTRAL_MIN_SHARE = 0.02


def _duration(path: str) -> float:
    try:
        return float(ffprobe_json(path).get("format", {}).get("duration") or 0)
    except (RuntimeError, ValueError):
        return 0.0


def sample_times(in_s: float, out_s: float, n: int = SAMPLES) -> list[float]:
    span = max(0.0, out_s - in_s)
    return [in_s + span * (k + 0.5) / n for k in range(n)]


def grab(path: str, t: float, vf_extra: str | None = None) -> np.ndarray | None:
    """t saniyedeki kare, SWxSH rgb24 (0–1, gama kodlu)."""
    vf = (vf_extra + "," if vf_extra else "") + f"scale={SW}:{SH}:flags=area,format=rgb24"
    r = subprocess.run([tool("ffmpeg"), "-hide_banner", "-nostdin", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(path),
                        "-frames:v", "1", "-vf", vf, "-f", "rawvideo", "-"], capture_output=True)
    if r.returncode != 0 or len(r.stdout) < SW * SH * 3:
        return None
    return np.frombuffer(r.stdout[:SW * SH * 3], dtype=np.uint8).reshape(SH, SW, 3).astype(np.float64) / 255.0


def stats(frames: list[np.ndarray]) -> dict | None:
    if not frames:
        return None
    px = np.concatenate([f.reshape(-1, 3) for f in frames])
    lin = px ** GAMMA
    y = lin @ np.array([0.2126, 0.7152, 0.0722])
    hi = float((px.min(axis=1) >= 0.98).mean())  # beyaza patlamış (doygun renkte tek kanalın 1 olması kırpılma sayılmaz)
    lo = float((px.max(axis=1) <= 0.02).mean())
    ok = (px.max(axis=1) < 0.98) & (px.max(axis=1) > 0.02)
    mx = px.max(axis=1)
    sat = np.where(mx > 0, (mx - px.min(axis=1)) / np.maximum(mx, 1e-6), 0)
    neutral = ok & (sat < NEUTRAL_SAT) & (y > 0.03) & (y < 0.7)
    pool = neutral if neutral.mean() >= NEUTRAL_MIN_SHARE else ok
    if not pool.any():
        pool = np.ones(len(px), dtype=bool)
    m = lin[pool].mean(axis=0)
    g = max(float(m[1]), 1e-6)
    med = max(float(np.median(y)), 1e-6)
    return {"median_lin": round(med, 5), "stops": round(math.log2(med / MID_GREY), 3), "r_g": round(float(m[0]) / g, 4),
            "b_g": round(float(m[2]) / g, 4), "clip_hi": round(hi, 4), "clip_lo": round(lo, 4),
            "wb_pool": "neutral" if pool is neutral else "all", "frames": len(frames)}


def measure_frames(path: str, in_s: float | None = None, out_s: float | None = None) -> tuple[dict | None, list[np.ndarray]]:
    a = float(in_s or 0.0)
    b = float(out_s) if out_s is not None else (_duration(path) or a + 1.0)
    frames = [f for f in (grab(path, t) for t in sample_times(a, b)) if f is not None]
    st = stats(frames)
    if st:
        st.update({"path": str(path), "in_s": a, "out_s": b})
    return st, frames


def measure(path: str, in_s: float | None = None, out_s: float | None = None) -> dict | None:
    return measure_frames(path, in_s, out_s)[0]


def exposure_badness(st: dict) -> float:
    return abs(st["stops"]) + 6 * st["clip_hi"] + 3 * st["clip_lo"]


def _refine(lin: list[float], ref: dict, frames: list[np.ndarray], rounds: int = 3, wb: bool = True) -> list[float]:
    """Kazanç örnek karelere uygulanıp yeniden ölçülür ve düzeltilir: nötr piksel havuzu renk kaymasıyla değişir (kayma pikseli
    doygunluk eşiğinin öte yanına iter), tek adımlık oran o yüzden ~%1–3 eksik kalır."""
    for _ in range(rounds):
        coef = np.array(lin) ** (1 / GAMMA)
        st = stats([np.clip(f * coef, 0, 1) for f in frames])
        if not st:
            break
        e = ref["median_lin"] / st["median_lin"]
        if wb:
            lin = [lin[0] * e * ref["r_g"] / st["r_g"], lin[1] * e, lin[2] * e * ref["b_g"] / st["b_g"]]
        else:
            lin = [v * e for v in lin]
    return lin


def correction(st: dict, ref: dict, frames: list[np.ndarray] | None = None) -> dict:
    """Doğrusal kazanç → sınır kontrolü (ham fark üzerinden) → örnek karelerde inceltme → gama alanı colorchannelmixer katsayıları.
    Beyaz dengesi yalnızca iki klipte de nötr (gri/beyaz) piksel havuzu varsa eşitlenir: havuzlardan biri "tüm pikseller"se oran sahnenin
    rengini ölçer (kırmızı ürün yakın çekimi "sıcak ışık" sanılır, ürün rengi değişirdi; 2.0.0) — o zaman yalnız pozlama eşitlenir."""
    stops = math.log2(ref["median_lin"] / st["median_lin"])
    wb = st.get("wb_pool", "neutral") == "neutral" and ref.get("wb_pool", "neutral") == "neutral"
    gr = ref["r_g"] / st["r_g"] if wb and st["r_g"] > 0 else 1.0
    gb = ref["b_g"] / st["b_g"] if wb and st["b_g"] > 0 else 1.0
    out = {"stops": round(stops, 3), "wb_gain_r": round(gr, 4), "wb_gain_b": round(gb, 4)}
    if not wb:
        out["wb_note"] = "nötr (gri/beyaz) alan bulunamadı: beyaz dengesi ölçülemedi, yalnız pozlama eşitlendi"
    over = []
    if abs(stops) > MAX_STOPS:
        over.append(f"pozlama farkı {stops:+.2f} stop (sınır ±{MAX_STOPS})")
    if max(abs(gr - 1), abs(gb - 1)) > MAX_GAIN:
        over.append(f"beyaz dengesi farkı R×{gr:.2f} B×{gb:.2f} (sınır ±%{int(MAX_GAIN * 100)})")
    if over:
        return {**out, "applied": False, "retake": True, "reason": "; ".join(over)}
    if abs(stops) < MIN_STOPS and max(abs(gr - 1), abs(gb - 1)) < MIN_GAIN:
        return {**out, "applied": False, "retake": False, "reason": "fark eşiğin altında"}
    e = 2.0 ** stops
    lin = [e * gr, e, e * gb]
    if frames:
        lin = _refine(lin, ref, frames, wb=wb)
    coef = tuple(round(v ** (1 / GAMMA), 4) for v in lin)
    return {**out, "applied": True, "retake": False, "gain_gamma": list(coef),
            "filter": f"colorchannelmixer=rr={coef[0]}:gg={coef[1]}:bb={coef[2]}"}


def enabled(style: dict | None) -> bool:
    return bool(((style or {}).get("grade") or {}).get("match", True))


def _footage_layers(plan: dict):
    for i, s in enumerate(plan.get("scenes", [])):
        for li, layer in enumerate(s.get("layers", []) or []):
            src = layer.get("source") or {}
            if layer.get("type") == "video" and src.get("kind") == "footage" and src.get("asset"):
                in_s = float(src.get("in_s", 0.0))
                yield i, s, li, src["asset"], in_s, float(src.get("out_s", in_s + s["dur_s"]))


def measure_source(a: dict) -> str | None:
    """Ölçüm proxy'den (yoksa cfr_sdr) — proxy ve final için aynı düzeltme çıksın diye kaliteden bağımsız."""
    for k in ("proxy", "cfr_sdr"):
        if a.get(k) and Path(a[k]).exists():
            return a[k]
    return None


def plan_corrections(plan: dict, assets: dict, style: dict | None) -> dict:
    """Her footage katmanı için ölçüm ve düzeltme. Dönen 'layers' anahtarı '<sahne_id>:<katman>'."""
    rep: dict = {"enabled": enabled(style), "ref": None, "ref_reason": None, "layers": {}, "retake_candidates": [],
                 "limits": {"stops": MAX_STOPS, "gain": MAX_GAIN}}
    if not rep["enabled"]:
        rep["ref_reason"] = "style.json grade.match=false"
        return rep
    rows, frames = [], {}
    for i, s, li, akey, in_s, out_s in _footage_layers(plan):
        a = assets.get(akey) or {}
        src = measure_source(a)
        st, fr = measure_frames(src, in_s, out_s) if src else (None, [])
        frames[f"{s['id']}:{li}"] = fr
        rows.append((f"{s['id']}:{li}", akey, st))
    measured = [r for r in rows if r[2]]
    if len({r[1] for r in measured}) < 2:
        rep["ref_reason"] = "tek kaynak klip; eşitlenecek fark yok"
        for lid, akey, st in rows:
            rep["layers"][lid] = {"asset": akey, "measure": st, "applied": False, "reason": rep["ref_reason"]}
        return rep
    want = ((style or {}).get("grade") or {}).get("match_ref")
    by_asset: dict[str, list[dict]] = {}
    for _, akey, st in measured:
        by_asset.setdefault(akey, []).append(st)
    if want and want not in by_asset and assets.get(want) and measure_source(assets[want]):
        st = measure(measure_source(assets[want]))
        if st:
            by_asset[want] = [st]
    if want and want in by_asset:
        ref_key, rep["ref_reason"] = want, "grade.match_ref"
    else:
        ref_key = min(by_asset, key=lambda k: float(np.mean([exposure_badness(x) for x in by_asset[k]])))
        rep["ref_reason"] = "en iyi pozlama" + (f" (grade.match_ref '{want}' bulunamadı)" if want else "")
    sts = by_asset[ref_key]
    ref = {"median_lin": float(np.exp(np.mean([math.log(x["median_lin"]) for x in sts]))),
           "r_g": float(np.mean([x["r_g"] for x in sts])), "b_g": float(np.mean([x["b_g"] for x in sts]))}
    rep["ref"] = {"asset": ref_key, **{k: round(v, 5) for k, v in ref.items()}}
    ref["wb_pool"] = rep["ref"]["wb_pool"] = "neutral" if all(x.get("wb_pool", "neutral") == "neutral" for x in sts) else "all"
    for lid, akey, st in rows:
        if not st:
            rep["layers"][lid] = {"asset": akey, "measure": None, "applied": False, "reason": "ölçülemedi (kaynak yok ya da okunamadı)"}
            continue
        if akey == ref_key:
            rep["layers"][lid] = {"asset": akey, "measure": st, "applied": False, "reason": "referans klip"}
            continue
        c = correction(st, ref, frames.get(lid))
        rep["layers"][lid] = {"asset": akey, "measure": st, **c}
        if c.get("retake"):
            rep["retake_candidates"].append({"layer": lid, "asset": akey, "reason": c["reason"]})
    return rep


def filter_for(rep: dict | None, layer_id: str) -> str | None:
    r = ((rep or {}).get("layers") or {}).get(layer_id) or {}
    return r.get("filter") if r.get("applied") else None


def digest(filt: str | None) -> str:
    return hashlib.sha256((filt or "").encode()).hexdigest()[:12]


def compare(rep: dict, out_dir: Path) -> list[str]:
    """Düzeltilen her katmanın orta karesi: solda önce, sağda sonra (S08 kapısında gösterilir)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    outs = []
    for lid, r in (rep.get("layers") or {}).items():
        if not r.get("applied"):
            continue
        m = r["measure"]
        t = (m["in_s"] + m["out_s"]) / 2
        dst = out_dir / f"match_{lid.replace(':', '_')}.jpg"
        fc = (f"[0:v]scale=-2:540,split[a][b];[b]{r['filter']}[c];[a]drawtext=text='önce':x=16:y=16:fontsize=28:fontcolor=white:"
              f"box=1:boxcolor=black@0.5[a2];[c]drawtext=text='sonra':x=16:y=16:fontsize=28:fontcolor=white:box=1:boxcolor=black@0.5[c2];"
              f"[a2][c2]hstack")
        try:
            ffmpeg(["-ss", f"{t:.3f}", "-i", m["path"], "-frames:v", "1", "-filter_complex", fc, "-q:v", "3", str(dst)])
        except RuntimeError:  # drawtext yoksa yazısız
            ffmpeg(["-ss", f"{t:.3f}", "-i", m["path"], "-frames:v", "1", "-filter_complex",
                    f"[0:v]scale=-2:540,split[a][b];[b]{r['filter']}[c];[a][c]hstack", "-q:v", "3", str(dst)])
        outs.append(str(dst))
    return outs


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("--clip", required=True)
    m.add_argument("--in", dest="in_s", type=float)
    m.add_argument("--out", dest="out_s", type=float)
    p = sub.add_parser("plan")
    p.add_argument("--plan", required=True)
    p.add_argument("--assets", required=True)
    p.add_argument("--style")
    p.add_argument("--out")
    c = sub.add_parser("compare")
    c.add_argument("--report", required=True)
    c.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    if a.cmd == "measure":
        emit(measure(a.clip, a.in_s, a.out_s))
    elif a.cmd == "plan":
        rep = plan_corrections(read_json(a.plan), read_json(a.assets), read_json(a.style) if a.style else None)
        if a.out:
            write_json(a.out, rep)
        emit(rep)
    else:
        emit({"frames": compare(read_json(a.report), Path(a.out_dir))})


if __name__ == "__main__":
    main()
