"""S16 analiz boru hattı (spec 6.3–6.11, 6.16). YALNIZCA değişmez karar girdisi kopyasını okur (decision_input_snapshot);
hesap sırasında tablodan tekrar veri almaz. Çıktı deterministiktir: aynı kopya → aynı sonuç.

Kullanım: coach.py --snapshot reports/c1-coach_report-input-v1.json --out reports/c1-analysis-v1.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import emit, read_json, sha256_file, write_json  # noqa: E402
import bayes as B  # noqa: E402

UPPER = ("hook_rate", "hold_rate")
METRICS = ("hook_rate", "hold_rate", "ctr_link", "cvr")


def _sum(rows, k):
    return sum(float(r.get(k) or 0) for r in rows)


def split_rows(snap: dict) -> dict:
    w = snap.get("test_window") or {}
    full = set(w.get("full_days") or [])
    excl = set(w.get("excluded_boundary_days") or [])
    test, post, pre, boundary = [], [], [], []
    test_end_day = max(full) if full else None
    for r in snap["rows"]:
        d = r["date"]
        if d in full:
            test.append(r)
        elif d in excl:
            boundary.append(r)
        elif test_end_day and d > test_end_day:
            post.append(r)
        else:
            pre.append(r)
    return {"test": test, "post": post, "pre": pre, "boundary": boundary, "full_days": sorted(full), "excluded_days": sorted(excl)}


def concept_of(snap: dict) -> dict:
    return {c["creative_key"]: c.get("concept") for c in snap.get("creatives", [])}


def role_of(snap: dict) -> dict:
    return {c["creative_key"]: c.get("competitive_role") for c in snap.get("creatives", [])}


def priors_for(snap: dict) -> dict:
    out = {}
    for p in (snap.get("priors") or {}).get("priors", []) or []:
        out[p["metric"]] = (float(p["a"]), float(p["b"]))
    return out


def aggregate(rows: list[dict], key) -> dict:
    g = defaultdict(list)
    for r in rows:
        g[key(r)].append(r)
    return g


def posteriors(groups: dict, priors: dict) -> dict:
    out = {}
    for k, rows in groups.items():
        tot = {c: _sum(rows, c) for c in ("impressions", "video_3s", "thruplay", "link_clicks", "purchases", "spend", "results", "revenue")}
        d = {"totals": tot, "rates": {}}
        for m in METRICS:
            num, den = B.RATE_DEF[m]
            basis = tot["impressions"] if m in ("hook_rate", "ctr_link") else tot[den]
            post = B.rate_posterior(m, tot[num], tot[den], priors.get(m), basis)
            d["rates"][m] = post.as_dict() if post else None
        out[k] = d
    return out


def spend_distribution(groups: dict) -> dict:
    total = sum(_sum(rows, "spend") for rows in groups.values()) or 0.0
    out = {}
    for k, rows in groups.items():
        sp = _sum(rows, "spend")
        share = sp / total if total else 0.0
        out[k] = {"spend": round(sp, 2), "share": round(share, 4), "starved": share < 0.10}
    return out


def fatigue(rows_by_creative: dict) -> list[dict]:
    """6.7: 7 günlük hook oranı ilk 3 günlük bazın %20'den fazla altı; frekans artarken CTR düşüşü; CPM 1,5× sıçrama."""
    alerts = []
    for k, rows in rows_by_creative.items():
        rows = sorted(rows, key=lambda r: r["date"])
        if len(rows) < 6:
            continue
        base = rows[:3]
        last7 = rows[-7:]
        def rate(rs, n, d):
            den = _sum(rs, d)
            return _sum(rs, n) / den if den else None
        hb, h7 = rate(base, "video_3s", "impressions"), rate(last7, "video_3s", "impressions")
        if hb and h7 is not None and h7 < hb * 0.8:
            alerts.append({"creative": k, "kind": "hook_decline", "base": round(hb, 4), "last7": round(h7, 4),
                           "msg": "7 günlük hook oranı ilk 3 günlük bazın %20'den fazla altında (yorgunluk olasılığı; neden kesin değil)"})
        f_first = statistics.mean([float(r.get("frequency") or 0) for r in base])
        f_last = statistics.mean([float(r.get("frequency") or 0) for r in last7])
        c_first, c_last = rate(base, "link_clicks", "impressions"), rate(last7, "link_clicks", "impressions")
        if f_last > f_first * 1.15 and c_first and c_last is not None and c_last < c_first * 0.85:
            alerts.append({"creative": k, "kind": "freq_up_ctr_down", "msg": "frekans artarken CTR düşüyor (yorgunluk olasılığı)"})
        cpm_base = _sum(base, "spend") / _sum(base, "impressions") * 1000 if _sum(base, "impressions") else None
        for r in last7:
            if cpm_base and r.get("impressions") and float(r["spend"] or 0) / float(r["impressions"]) * 1000 > cpm_base * 1.5:
                alerts.append({"creative": k, "kind": "cpm_spike", "date": r["date"], "msg": "CPM bazın 1,5 katına sıçradı (açık artırma/hedefleme uyarısı)"})
                break
    return alerts


def retention(snap: dict, rows_by_creative: dict) -> list[dict]:
    """6.8: p25…p100 → tutma eğrisi; beklenen eğri = aynı format/süredeki kreatiflerin ortancası (yoksa kampanya ortancası).
    Kayıp sahneye olasılık cümlesiyle bağlanır; kesin neden yüklenmez."""
    plans = snap.get("edit_plans") or {}
    cr = {c["creative_key"]: c for c in snap.get("creatives", [])}
    curves = {}
    for k, rows in rows_by_creative.items():
        plays = _sum(rows, "video_3s") or _sum(rows, "impressions")
        if plays <= 0 or k not in cr:
            continue
        pts = [_sum(rows, p) / plays for p in ("p25", "p50", "p75", "p95", "p100")]
        if not any(pts):
            continue
        curves[k] = pts
    if len(curves) < 2:
        return []
    expected = [statistics.median(c[i] for c in curves.values()) for i in range(5)]
    out = []
    for k, pts in curves.items():
        dev = [pts[i] - expected[i] for i in range(5)]
        i = min(range(5), key=lambda j: dev[j])
        if dev[i] > -0.05:
            continue
        c = cr[k]
        plan = plans.get(str(c.get("edit_plan_id"))) or plans.get(c.get("edit_plan_id")) or {}
        dur = float(c.get("duration_s") or plan.get("duration_s") or 15)
        frac = [0.25, 0.5, 0.75, 0.95, 1.0][i]
        t_end = dur * frac
        t_start = dur * ([0.0, 0.25, 0.5, 0.75, 0.95][i])
        scene = None
        for s in plan.get("scenes", []):
            if s["start_s"] <= (t_start + t_end) / 2 < s["start_s"] + s["dur_s"]:
                scene = s
        out.append({"creative": k, "interval_s": [round(t_start, 2), round(t_end, 2)], "deviation": round(dev[i], 4),
                    "scene": scene["id"] if scene else None, "role": scene["role"] if scene else None,
                    "statement": (f"{k} kreatifinde izleyici {round(t_start,1)}–{round(t_end,1)} sn aralığında beklenenden hızlı kayboluyor olabilir"
                                  + (f" (sahne {scene['id']}, {scene['role']})" if scene else "")
                                  + "; 5 ölçüm noktasıyla bu bir olasılık cümlesidir, kesin neden değildir.")})
    return out


def limit_alerts(snap: dict, all_rows: list[dict]) -> list[dict]:
    """6.3/6.10: onaylı reklam başı harcama sınırı ve kampanya toplam sınırı; sonuç sayısı 10'un altında ya da sıfır olsa da uyarır."""
    alerts = []
    cyc = snap["cycle"]
    rl = cyc.get("risk_limits_json") or {}
    if isinstance(rl, str):
        import json
        rl = json.loads(rl)
    per = (rl.get("per_ad") or {}).get("amount")
    mapping = rl.get("mapping") or {}
    by_ad = aggregate(all_rows, lambda r: r["meta_ad_id"])
    for ck, m in mapping.items():
        for ad in m.get("meta_ad_ids", []):
            sp = _sum(by_ad.get(ad, []), "spend")
            if per and sp >= float(per):
                res = _sum(by_ad.get(ad, []), "results")
                alerts.append({"kind": "risk_limit", "creative_key": ck, "meta_ad_id": ad, "spend": round(sp, 2), "limit": per, "results": res,
                               "msg": "onaylı reklam harcama sınırına ulaşıldı/aşıldı: insan için durdurma/limit düzenleme önerisi "
                                      "(istatistiksel 'kaybeden' kararı değildir)"})
    bt = snap["campaign"].get("budget_total")
    if bt is not None:
        total = _sum(all_rows, "spend")
        daily = float(cyc.get("adset_budget_daily") or 0)
        remaining = float(bt) - total
        if remaining <= 0:
            alerts.append({"kind": "total_exceeded", "spend": round(total, 2), "budget_total": bt, "msg": "kampanya toplam harcama sınırı aşıldı"})
        elif daily and remaining < daily:
            alerts.append({"kind": "total_near", "remaining": round(remaining, 2), "msg": "kalan tutar bir sonraki günlük kontrole kadarki planlı harcamaya yetmiyor"})
    return alerts


def decisions(concepts: dict, dist: dict, snap: dict, structure: str | None, cost: dict) -> list[dict]:
    """tut / büyüt / kapat / yenile — gerekçeli; eşik altı → yön; aç kalan konsept kaybeden sayılmaz; 'kapat' performans gerekçesiyle
    yalnızca eşik geçilmiş ve Meta harcama veriyorsa; büyütme için yeterli sonuç ve doğrulanmış ekonomi gerekir."""
    out = []
    eco = snap.get("economics") or {}
    eco_ok = eco.get("status") == "exact"
    for k, c in concepts.items():
        hook = c["rates"].get("hook_rate")
        ctr = c["rates"].get("ctr_link")
        d = dist.get(k, {})
        co = cost.get(k, {})
        label = B.verdict_language(bool(hook and hook["threshold_met"]), structure)
        if d.get("starved") and structure in ("bootstrap", None, "unverified"):
            out.append({"concept": k, "decision": "tut", "label": "yetersiz veri", "why": "Meta bu konsepte harcama payının %10'undan azını verdi; kaybeden sayılmaz, sonraki kreatif teste aday"})
            continue
        if co.get("threshold_met") and co.get("p_below_target", 0) >= 0.9 and eco_ok:
            out.append({"concept": k, "decision": "büyüt", "label": label, "why": f"yeterli sonuç; hedef maliyet altı olasılığı {co['p_below_target']:.2f}",
                        "ads_manager": "reklam setinin günlük bütçesini en fazla %20 artır ve konseptin yeni varyantlarını sonraki teste ekle"})
        elif co.get("threshold_met") and co.get("p_below_target", 1) <= 0.1 and d.get("share", 0) >= 0.1:
            out.append({"concept": k, "decision": "kapat", "label": label, "why": f"yeterli sonuç; hedef altı olasılığı {co['p_below_target']:.2f} ve Meta harcama veriyor",
                        "ads_manager": "bu konseptin reklamlarını durdur"})
        else:
            out.append({"concept": k, "decision": "tut", "label": label,
                        "why": "eşik altı ya da belirsiz: istatistiksel kazanan/kaybeden hükmü verilmez" if not (hook and hook["threshold_met"]) else "veri yeterli ama net üstünlük yok"})
    return out


def analyze(snap_path: str) -> dict:
    snap = read_json(snap_path)
    parts = split_rows(snap)
    cmap = concept_of(snap)
    rmap = role_of(snap)
    priors = priors_for(snap)
    cyc = snap["cycle"]
    structure = cyc.get("structure_detected")
    test_rows = parts["test"]
    by_creative = aggregate(test_rows, lambda r: r.get("creative_key") or f"(eşlenmemiş) {r['meta_ad_id']}")
    by_concept = aggregate(test_rows, lambda r: cmap.get(r.get("creative_key")) or "(konseptsiz)")
    by_role = aggregate(test_rows, lambda r: rmap.get(r.get("creative_key")) or "(rolsüz)")
    cpost = posteriors(by_creative, priors)
    kpost = posteriors(by_concept, priors)
    rpost = posteriors(by_role, priors)
    hook_posts = {k: B.RatePosterior(**v["rates"]["hook_rate"]) for k, v in kpost.items() if v["rates"].get("hook_rate")}
    hist_mean = None
    if "hook_rate" in priors:
        a, b = priors["hook_rate"]
        hist_mean = a / (a + b)
    sup = B.superiority(hook_posts, hist_mean)
    eco = snap.get("economics") or {}
    target = eco.get("target_cpa") if snap["campaign"].get("result_type") == "purchase" else None
    verified = eco.get("status") == "exact"
    cost = {k: B.cost_posterior(v["totals"]["spend"], v["totals"]["results"], target, verified) for k, v in kpost.items()}
    dist = spend_distribution(by_concept)
    all_rows = snap["rows"]
    rows_all_by_creative = aggregate(all_rows, lambda r: r.get("creative_key") or r["meta_ad_id"])
    fat = fatigue(rows_all_by_creative)
    ret = retention(snap, aggregate(test_rows, lambda r: r.get("creative_key") or r["meta_ad_id"]))
    lim = limit_alerts(snap, all_rows)
    dec = decisions(kpost, dist, snap, structure, cost)
    quality = []
    days = sorted({r["date"] for r in all_rows})
    if days:
        d0, d1 = dt.date.fromisoformat(days[0]), dt.date.fromisoformat(days[-1])
        missing = [(d0 + dt.timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1) if (d0 + dt.timedelta(days=i)).isoformat() not in days]
        if missing:
            quality.append({"kind": "missing_days", "days": missing})
    unmapped = sorted({r["meta_ad_id"] for r in all_rows if not r.get("creative_key")})
    if unmapped:
        quality.append({"kind": "unmapped_ads", "ads": unmapped, "msg": "reklam adı ↔ creative_key eşleşmeyen reklam"})
    derived = sum(1 for r in all_rows if r.get("video_3s_derived"))
    if derived:
        quality.append({"kind": "video_3s_derived", "rows": derived, "msg": "3 sn izlenme amount_spent / cost_per_video_view ile türetildi"})
    fps_ = sorted({r["measurement_fingerprint"] for r in all_rows})
    if len(fps_) > 1:
        quality.append({"kind": "mixed_definitions", "fingerprints": fps_, "msg": "farklı ölçüm tanımları aynı havuzda karıştırılmaz"})
    comp = snap.get("competitor_snapshot")
    competitive_context = {"snapshot": comp, "statements": (snap.get("extra") or {}).get("competitor_changes", []),
                           "rule": "Rekabet bağlamı nedensellik iddia etmez; hüküm diline ve karar eşiklerine girmez (6.16)."}
    predictions = []
    for k, s in sup.items():
        if s.get("p_best") is not None:
            predictions.append({"subject": f"concept:{k}", "metric": "hook_rate", "p_win": round(s["p_best"], 4),
                                "interval": {"lo": kpost[k]["rates"]["hook_rate"]["lo"], "hi": kpost[k]["rates"]["hook_rate"]["hi"]}})
    return {"snapshot": {"path": snap_path, "sha256": sha256_file(snap_path)}, "model_version": snap.get("model_version"), "params": snap.get("params"),
            "structure": structure, "verdict_qualifier": B.verdict_language(True, structure).replace("kanıt", "").strip(" ·"),
            "window": {"full_days": parts["full_days"], "excluded_boundary_days": parts["excluded_days"], "test_rows": len(test_rows),
                       "post_rows": len(parts["post"]), "note": "sınır günleri saat oranıyla bölünmez; toplam harcamada tam sayılır"},
            "creatives": cpost, "concepts": kpost, "roles": rpost, "superiority_hook": sup, "cost": cost, "spend_distribution": dist,
            "fatigue": fat, "retention": ret, "limit_alerts": lim, "decisions": dec, "data_quality": quality,
            "competitive_context": competitive_context, "predictions": predictions,
            "portfolio_note": "Rol başına sonuç keşif karşılaştırmasıdır; önceden sabitlenmedikçe playbook adayı olmaz (6.16)."}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    res = analyze(a.snapshot)
    sha = write_json(a.out, res, overwrite=False)
    emit({"out": a.out, "sha256": sha, "decisions": res["decisions"], "limit_alerts": res["limit_alerts"], "data_quality": res["data_quality"]})


if __name__ == "__main__":
    main()
