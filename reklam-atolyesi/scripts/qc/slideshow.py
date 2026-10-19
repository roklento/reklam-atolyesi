"""Slayt gösterisi riski (1.4.6; spec 5.15 öz denetimine ek): videonun "hareketli reklam" yerine "art arda duran kareler" gibi
görünme riskini altı boyutta puanlar. Fikir açık kaynak OpenMontage'ın slideshow risk denetiminden alındı; kod ve eşikler bu
plugin'indir. Eşikler YEREL sezgisel değerlerdir (Meta kuralı değildir); karar insan kapısındadır.

Boyutlar (0 = risk yok, 1 = yüksek risk):
  still_share     görüntüsü yalnızca durağan kaynaktan (still/ai_image/graphic) gelen sahnelerin süre payı; kamera hareketi
                  (KenBurns, Parallax25D, HandheldDrift, FakeRackFocus) olan durağan sahne yarım sayılır
  weak_motion     render edilmiş videoda (4 kare/sn, 360 px) kare arası optik akış ortalaması eşiğin altında kalan örnek payı
  hook_motion     ilk 1,5 sn'nin hareketi zayıfsa 1 (açılış kaydırmayı durdurmalı)
  repetition      art arda iki sahnenin aynı kaynak varlığı kullanma payı
  pacing          sahne sürelerinin tekdüzeliği (değişim katsayısı düşük ve ortalama uzun)
  text_reliance   görüntü katmanı olmayan (yalnızca yazı/bileşen) sahnelerin payı; kapanış kartı hariç

Kullanım: slideshow.py --plan plan.json [--video v.mp4] [--out risk.json]
Video verilmezse weak_motion ve hook_motion hesaplanmaz (plan tabanlı ön kontrol). Düzey: low < 0,35 ≤ medium < 0,50 ≤ high < 0,65 ≤
critical; weak_motion ≥ 0,8 tek başına critical. critical öz denetimde düzeltilecek bulgudur, high uyarıdır.
"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit, read_json, write_json  # noqa: E402

STILL_KINDS = {"still", "ai_image", "graphic"}
MOVING_KINDS = {"footage", "ai_clip"}
CAMERA_MOVES = {"KenBurns", "Parallax25D", "HandheldDrift", "FakeRackFocus"}
WEIGHTS = {"still_share": 0.25, "weak_motion": 0.25, "hook_motion": 0.15, "repetition": 0.10, "pacing": 0.10, "text_reliance": 0.15}
MOTION_FLOOR = 0.15     # 360 px'te kare arası ortalama optik akış (piksel); altı "duruyor" sayılır — yerel eşik
HOOK_WINDOW_S = 1.5
LEVELS = ((0.35, "low"), (0.50, "medium"), (0.65, "high"))


def _visual_layers(scene: dict) -> list[dict]:
    return [l for l in scene.get("layers", []) if l.get("type") in ("video", "image", "graphic") and l.get("source")]


def _scene_still_weight(scene: dict) -> float:
    vis = _visual_layers(scene)
    if not vis:
        return 0.0
    if any((l["source"].get("kind") in MOVING_KINDS) for l in vis):
        return 0.0
    moved = any(l.get("component") in CAMERA_MOVES or (l.get("camera") or {}) for l in scene.get("layers", []))
    return 0.5 if moved else 1.0


def _asset_key(scene: dict) -> str | None:
    vis = _visual_layers(scene)
    if not vis:
        return None
    s = vis[0]["source"]
    return s.get("asset") or s.get("path")


def plan_dimensions(plan: dict) -> dict:
    scenes = plan.get("scenes") or []
    total = sum(float(s["dur_s"]) for s in scenes) or 1.0
    still = sum(float(s["dur_s"]) * _scene_still_weight(s) for s in scenes) / total
    keys = [_asset_key(s) for s in scenes]
    pairs = list(zip(keys, keys[1:]))
    rep = (sum(1 for a, b in pairs if a and a == b) / len(pairs)) if pairs else 0.0
    durs = [float(s["dur_s"]) for s in scenes]
    pacing = 0.0
    if len(durs) >= 3:
        mean = statistics.mean(durs)
        cv = statistics.pstdev(durs) / mean if mean else 0.0
        # tekdüze (cv düşük) ve uzun ortalama sahne → risk; 2,5 sn altı ortalama ritim sayılır
        pacing = max(0.0, min(1.0, (0.35 - cv) / 0.35)) * max(0.0, min(1.0, (mean - 1.5) / 2.0))
    body = [s for s in scenes if s.get("role") != "endcard"]
    text_only = sum(1 for s in body if not _visual_layers(s) and any(l.get("type") in ("text", "component") for l in s.get("layers", [])))
    text_rel = text_only / len(body) if body else 0.0
    return {"still_share": round(still, 4), "repetition": round(rep, 4), "pacing": round(pacing, 4), "text_reliance": round(text_rel, 4)}


def motion_samples(video: str) -> list[tuple[float, float]]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analyze"))
    import measure as M  # noqa: E402
    rows = M.video_metrics(video)["samples"]
    return [(r["t"], r["motion"]) for r in rows[1:]]  # ilk örneğin önceki karesi yok


def video_dimensions(samples: list[tuple[float, float]]) -> dict:
    if not samples:
        return {"weak_motion": None, "hook_motion": None, "motion_mean": None}
    weak = sum(1 for _, m in samples if m < MOTION_FLOOR) / len(samples)
    hook = [m for t, m in samples if t <= HOOK_WINDOW_S]
    hook_weak = 1.0 if hook and statistics.mean(hook) < MOTION_FLOOR else 0.0
    return {"weak_motion": round(weak, 4), "hook_motion": hook_weak, "motion_mean": round(statistics.mean(m for _, m in samples), 4)}


def score(dims: dict) -> dict:
    used = {k: v for k, v in dims.items() if k in WEIGHTS and v is not None}
    wsum = sum(WEIGHTS[k] for k in used) or 1.0
    s = sum(WEIGHTS[k] * float(v) for k, v in used.items()) / wsum
    level = next((name for lim, name in LEVELS if s < lim), "critical")
    if (dims.get("weak_motion") or 0) >= 0.8:
        level = "critical"
    top = sorted(used.items(), key=lambda kv: -WEIGHTS[kv[0]] * float(kv[1]))[:2]
    return {"score": round(s, 4), "level": level, "dimensions": dims, "main_drivers": [k for k, v in top if v > 0],
            "basis": "plan+video" if dims.get("weak_motion") is not None else "plan",
            "note": "Yerel sezgisel eşikler; ham/UGC türünde düşük efekt kendi başına kusur değildir. Karar insan kapısındadır."}


def slideshow_risk(plan: dict, video: str | None = None, samples: list[tuple[float, float]] | None = None) -> dict:
    dims = plan_dimensions(plan)
    if samples is None and video:
        samples = motion_samples(video)
    if samples is not None:
        dims.update(video_dimensions(samples))
    else:
        dims.update({"weak_motion": None, "hook_motion": None})
    return score(dims)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--video")
    ap.add_argument("--out")
    a = ap.parse_args()
    res = slideshow_risk(read_json(a.plan), a.video)
    if a.out:
        write_json(a.out, res)
    emit(res)


if __name__ == "__main__":
    main()
