"""Görüntüden ses efekti aday anları (2.7.0): kesme, ani hareket, hareketin başlaması, hareketin durması.

Önizleme render'ından ya da kullanıcının ham çekiminden çalışır (S10 önizlemesi, S11 efekt ihtiyacı). Bir aday listesidir:
karar sound-designer ajanının ve kullanıcınındır; kareler `--frames-dir` ile yazılır ki bakılabilsin.
  cut     kesme ya da tam kare değişimi            → geçiş (whoosh) ya da kesme vuruşu
  burst   yerel düzeyin çok üstünde ani hareket     → darbe, whoosh
  onset   görüntü duruyordu, bir şey başladı         → pop, tık, açılış
  settle  hareket bitti, görüntü durdu               → iniş sesi: tok vuruş, masaya konma (ürün masaya kondu, kapak oturdu)
`--plan` verilirse adaylar sahnelere çevrilir (sahne kimliği + sahne içi at_s) ve plandaki efektlere 0,15 sn'den yakın olanlar
"covered" işaretlenir; yeni cue önerisi yalnız boş anlara yapılır, plan yoğunluk kuralı (1 sn'de ≤ 2) korunur.

Yöntem fikri Clipwing real-sfx find_moments'tan (kod kopyalanmadı); ölçüm OpenCV ile, 15 fps ve küçük boyutta, hızlıdır.
Kullanım: sfx_moments.py --video preview.mp4 [--plan plan.json] [--max 20] [--fps 15] [--frames-dir dir] [--out moments.json]
"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit, read_json, write_json  # noqa: E402

SUGGEST = {"cut": ("whoosh", "geçiş"), "burst": ("impact", "darbe"), "onset": ("pop", "pop"), "settle": ("knock", "tok vuruş knock")}
STILL = 0.004   # kareler arası ortalama mutlak fark (0–1) alt sınırı: altı "duruyor" (elde çekimde gürültü tabanına uyarlanır)
MOVE = 0.010    # alt sınır: üstü "hareket var"
HOLD_S = 0.30   # duruş/hareketin en az bu kadar sürmesi
MIN_GAP_S = 0.25
COVER_S = 0.15


def series(video: str, fps: float = 15.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(zaman, hareket, kesme) dizileri. hareket: gri kareler arası ortalama mutlak fark; kesme: 1 - histogram korelasyonu."""
    import cv2
    cap = cv2.VideoCapture(video)
    src = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(src / fps)))
    ts, mot, cut = [], [], []
    prev = prev_h = None
    i = 0
    while True:
        if not cap.grab():
            break
        if i % step == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            h, w = frame.shape[:2]
            sc = 160.0 / max(h, w)
            g = cv2.cvtColor(cv2.resize(frame, (max(2, int(w * sc)), max(2, int(h * sc))), interpolation=cv2.INTER_AREA),
                             cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
            hist = cv2.calcHist([frame], [0, 1, 2], None, [8, 8, 8], [0, 256] * 3)
            cv2.normalize(hist, hist)
            if prev is not None:
                ts.append(i / src)
                mot.append(float(np.abs(g - prev).mean()))
                cut.append(float(1.0 - cv2.compareHist(prev_h, hist, cv2.HISTCMP_CORREL)))
            prev, prev_h = g, hist
        i += 1
    cap.release()
    return np.array(ts), np.array(mot), np.array(cut)


def detect(ts: np.ndarray, mot: np.ndarray, cut: np.ndarray, fps: float = 15.0, max_n: int = 20) -> list[dict]:
    if not len(ts):
        return []
    hold = max(2, int(round(HOLD_S * fps)))
    found: list[dict] = []
    med = statistics.median(mot) if len(mot) else 0.0
    # eşikler gürültü tabanına uyarlanır: elde çekimde "duruş" bile biraz kıpırdar
    still = max(STILL, 1.5 * float(np.percentile(mot, 20)))
    move = max(MOVE, 2.5 * still)
    is_cut = np.zeros(len(ts), bool)
    for k in range(len(ts)):
        lo, hi = max(0, k - 8), min(len(ts), k + 9)
        local = float(np.median(mot[lo:hi]))
        if (cut[k] > 0.5 and mot[k] > max(0.05, 3 * med)) or (mot[k] > 0.15 and mot[k] > 6 * max(local, still)):
            is_cut[k] = True
            found.append({"t": ts[k], "kind": "cut", "strength": max(float(cut[k]), min(1.0, mot[k] * 4))})
        elif mot[k] > max(move * 2.5, 3 * local) and mot[k] == mot[lo:hi].max():
            found.append({"t": ts[k], "kind": "burst", "strength": mot[k] / max(local, 1e-4) / 10})
    calm = np.where(is_cut, 0.0, mot)  # kesme karesi duruş/başlama sayılmaz
    for k in range(hold, len(ts) - hold + 1):
        if is_cut[max(0, k - hold):k + hold].any():
            continue
        before, after = calm[k - hold:k], calm[k:k + hold]
        if before.max() < still and after.mean() > move:
            found.append({"t": ts[k], "kind": "onset", "strength": float(after.mean() / move) / 3})
        if before.mean() > move and after.max() < still:
            found.append({"t": ts[k], "kind": "settle", "strength": float(before.mean() / move) / 3})
    found.sort(key=lambda x: -x["strength"])
    out: list[dict] = []
    for f in found:  # güçlüden zayıfa; birbirine 0,25 sn'den yakın adayın zayıfı düşer
        if all(abs(f["t"] - o["t"]) >= MIN_GAP_S for o in out):
            out.append(f)
        if len(out) >= max_n:
            break
    out.sort(key=lambda x: x["t"])
    for o in out:
        role, query = SUGGEST[o["kind"]]
        o.update({"t": round(float(o["t"]), 3), "strength": round(min(1.0, float(o["strength"])), 3), "role": role, "query": query})
    return out


def to_plan(moments: list[dict], plan: dict) -> list[dict]:
    """Adayları sahnelere çevir; mevcut efekte yakınsa covered."""
    existing = [float(s["start_s"]) + float(c["at_s"]) for s in plan.get("scenes", []) for c in (s.get("audio_cues") or [])]
    for m in moments:
        sc = next((s for s in plan.get("scenes", []) if float(s["start_s"]) <= m["t"] < float(s["start_s"]) + float(s["dur_s"])), None)
        if sc:
            m["scene"], m["at_s"] = sc["id"], round(m["t"] - float(sc["start_s"]), 3)
        m["covered"] = any(abs(m["t"] - e) <= COVER_S for e in existing)
    return moments


def write_frames(video: str, moments: list[dict], out_dir: str) -> None:
    import cv2
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(video)
    for m in moments:
        cap.set(cv2.CAP_PROP_POS_MSEC, m["t"] * 1000)
        ok, frame = cap.read()
        if ok:
            p = Path(out_dir) / f"{m['t']:07.3f}_{m['kind']}.jpg"
            cv2.imwrite(str(p), frame)
            m["frame"] = str(p)
    cap.release()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--plan")
    ap.add_argument("--max", type=int, default=20)
    ap.add_argument("--fps", type=float, default=15.0)
    ap.add_argument("--frames-dir")
    ap.add_argument("--out")
    a = ap.parse_args()
    ts, mot, cut = series(a.video, a.fps)
    ms = detect(ts, mot, cut, a.fps, a.max)
    if a.plan:
        ms = to_plan(ms, read_json(a.plan))
    if a.frames_dir:
        write_frames(a.video, ms, a.frames_dir)
    rep = {"video": a.video, "moments": ms, "counts": {k: sum(1 for m in ms if m["kind"] == k) for k in SUGGEST},
           "uncovered": [m for m in ms if not m.get("covered", False)],
           "note": "Aday listesidir: kareye bakarak seç; ürün/kişi hareketi olmayan anlara (yazı animasyonu dışında) efekt koyma. "
                   "Efekt bütçesi: 1 sn'de en fazla 2, aynı efekt 2 sn içinde tekrar yok."}
    if a.out:
        write_json(a.out, rep)
    emit(rep)


if __name__ == "__main__":
    main()
