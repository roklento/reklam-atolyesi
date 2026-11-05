"""Efekt öz puanlaması ve dinleme listesi (2.7.0, S11 miksten sonra, S13 QC'de de okunur).

Ölçülebilen eksenleri 1–10 puanlar, en kötü üç sorunu zaman koduyla ve kullanıcının KULAKLA dinlemesi gereken en fazla 5 anı verir.
Claude sesi duyamaz: burada "dinlendi" denmez; ölçülen ve gösterilen yazılır, karar kulağa bırakılır.
Eksenler:
  sync      her efektin oturma noktası (sfx_place) efekt izinde gerçekten kareye geldi mi (ms hata; 1 kare = 10 puan)
  level     efektin izdeki tepe seviyesi türünün hedefine yakın mı (konuşma kısması hesaba katılır)
  speech    efekt doruğu konuşmanın üstüne mi düşüyor (kısılsa da sözcüğü örtebilir)
  density   plan yoğunluk kuralı (1 sn'de ≤ 2, aynı efekt 2 sn içinde tekrar yok; admem.editplan.sfx_density)
  coverage  görüntüdeki güçlü anlardan (sfx_moments.py) efektsiz kalanlar; ceza yumuşaktır, her ana ses gerekmez
  cutoff    sesi videonun sonunda kesilen efekt
Geçme eşiği her eksende 8. Fikir kaynağı: Clipwing real-sfx critique (yalnız yöntem; kod kopyalanmadı).
Kullanım: sfx_review.py --mix-report audio/stems/mix_report.json --plan plan.json [--moments moments.json] [--out sfx_review.json]
"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "audio"))
from common import emit, read_json, seconds_to_tc, write_json  # noqa: E402

PASS = 8.0
FRAME_MS = 1000 / 30


def _clamp(v: float) -> float:
    return round(max(1.0, min(10.0, v)), 1)


def _read(p: str | None):
    if not p or not Path(p).exists():
        return None
    import soundfile as sf
    y, _ = sf.read(p, always_2d=True, dtype="float32")
    return y


def measured_anchor(stem: np.ndarray, cue: dict, sr: int) -> tuple[float | None, float]:
    """İzde cue'nun etrafında (−0,25/+0,25 sn) oturma noktasının ölçülen zamanı ve oradaki tepe (dBFS)."""
    import sfx_place as SP
    a = max(0, int((cue["at_s"] - 0.25) * sr))
    b = min(len(stem), int((cue["at_s"] + 0.25) * sr))
    if b - a < 16:
        return None, -120.0
    env = SP.envelope(stem[a:b])
    pk = float(env.max())
    if pk <= 1e-6:
        return None, -120.0
    w = 0.005
    if cue.get("anchor") == "peak":
        i = int(env.argmax())
    elif cue.get("anchor") == "start":
        i = int(np.argmax(env >= pk * 10 ** (-40 / 20)))
    else:
        i = int(np.argmax(env >= pk * 10 ** (-6 / 20)))
    return a / sr + i * w, 20 * float(np.log10(pk))


def review(rep: dict, plan: dict, moments: dict | None = None) -> dict:
    import mix as MX
    sr = MX.SR
    placed = rep.get("sfx_placed") or []
    stems = rep.get("stems") or {}
    sfx = _read(stems.get("sfx"))
    speech = None
    for k in ("vo", "dialog"):
        y = _read(stems.get(k))
        if y is not None:
            act = MX.speech_activity(y)
            speech = act if speech is None else (speech | act[: len(speech)])
    total = float(plan.get("duration_s") or (len(sfx) / sr if sfx is not None else 0))
    problems: list[dict] = []
    sync_err, level_dev, under_speech, cut_off = [], [], [], []
    for c in placed:
        t = c["at_s"]
        if sfx is not None:
            got, pk_db = measured_anchor(sfx, c, sr)
            if got is not None and c.get("anchor") != "start":  # başlangıç noktası önceki efektin kuyruğuyla karışır: yalnız seviye
                e = abs(got - t) * 1000
                sync_err.append(e)
                if e > 2 * FRAME_MS:
                    problems.append({"t": t, "axis": "sync", "sev": e / FRAME_MS,
                                     "msg": f"'{c.get('sfx')}' oturma noktası kareden {e:.0f} ms uzakta ({c['anchor']})"})
            tgt = c.get("target_peak_db")
            if tgt is not None and pk_db > -100:
                ducked = speech is not None and bool(speech[min(len(speech) - 1, int(t * sr))])
                exp = tgt - (6.0 if ducked else 0.0)
                d = pk_db - exp
                level_dev.append(abs(d))
                if abs(d) > 4:
                    problems.append({"t": t, "axis": "level", "sev": abs(d) / 2,
                                     "msg": f"'{c.get('sfx')}' ({c.get('role') or 'tür yok'}) izde {pk_db:.1f} dBFS, hedef {exp:.1f}"})
        if speech is not None and 0 <= int(t * sr) < len(speech) and speech[int(t * sr)]:
            under_speech.append(c)
            problems.append({"t": t, "axis": "speech", "sev": 2.0,
                             "msg": f"'{c.get('sfx')}' konuşmanın üstünde: kısılıyor ama sözcüğü örtebilir; konuşma arasına kaydır"})
        dur = (c.get("measure") or {}).get("dur_s") or 0
        if total and c["start_s"] + dur > total + 0.02:
            cut_off.append(c)
            problems.append({"t": t, "axis": "cutoff", "sev": 2.5, "msg": f"'{c.get('sfx')}' videonun sonunda kesiliyor"})
    # 2.10.2: efekt yerleştirilmiş ama efekt izi okunamıyorsa oturma ve seviye ölçülemedi; ölçülmeyen eksen "geçti" sayılmaz
    unmeasured = ["sync", "level"] if placed and sfx is None else []
    if unmeasured:
        problems.append({"t": 0.0, "axis": "olculemedi", "sev": 10.0,
                         "msg": "efekt izi (stems.sfx) okunamadı: efektin kareye oturması ve ses seviyesi ölçülemedi; miksi yeniden çalıştır"})
    from admem.editplan import sfx_density
    dens = sfx_density(plan.get("scenes", []), plan.get("effects"))
    uncovered = [m for m in (moments or {}).get("moments", []) if not m.get("covered") and m.get("strength", 0) >= 0.5]
    for m in uncovered[:3]:
        problems.append({"t": m["t"], "axis": "coverage", "sev": 1.0,
                         "msg": f"güçlü {m['kind']} anı efektsiz (öneri: {m['role']}, arama '{m['query']}')"})
    med = statistics.median(sync_err) if sync_err else 0.0
    axes = {
        "sync": _clamp(10 - max(0.0, med - FRAME_MS) / FRAME_MS * 2) if sync_err else None,
        "level": _clamp(10 - (statistics.median(level_dev) if level_dev else 0) * 0.75) if level_dev else None,
        "speech": _clamp(10 - 2 * len(under_speech)) if placed else None,
        "density": _clamp(10 - 2 * len(dens)) if placed else None,
        "coverage": _clamp(10 - len(uncovered)) if moments is not None else None,
        "cutoff": _clamp(10 - 3 * len(cut_off)) if placed else None,
    }
    worst = sorted(problems, key=lambda p: -p["sev"])[:3]
    listen: list[dict] = []

    def add(t: float, why: str) -> None:
        if len(listen) < 5 and all(abs(t - x["t"]) > 0.5 for x in listen):
            listen.append({"t": round(t, 3), "tc": seconds_to_tc(t), "why": why})
    for p in worst:
        if p["axis"] != "olculemedi":
            add(p["t"], p["msg"])
    by_role = {}
    for c in placed:
        by_role.setdefault(c.get("role") or "?", c)
    for role in ("logo", "impact", "whoosh", "riser"):
        if role in by_role:
            add(by_role[role]["at_s"], f"{role}: kesmeye oturuyor mu, müzikle çakışıyor mu")
    for c in placed:
        add(c["at_s"], f"'{c.get('sfx')}' görüntüye uyuyor mu")
    scored = [v for v in axes.values() if v is not None]
    return {"axes": axes, "pass": bool(scored) and min(scored) >= PASS and not unmeasured, "unmeasured": unmeasured,
            "pass_threshold": PASS, "worst": worst,
            "listen": listen, "density_issues": dens, "cues": len(placed),
            "note": "Ölçülen eksenlerdir; karakter uyumu, temizlik ve zevk kulakla dinlenir. Listedeki anları telefon hoparlöründe ve "
                    "kulaklıkla dinlet; yalnız en kötü üç sorunu düzelt, yeniden miksle, tekrar puanla."}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mix-report", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--moments")
    ap.add_argument("--out")
    a = ap.parse_args()
    res = review(read_json(a.mix_report), read_json(a.plan), read_json(a.moments) if a.moments else None)
    if a.out:
        write_json(a.out, res)
    emit(res)


if __name__ == "__main__":
    main()
