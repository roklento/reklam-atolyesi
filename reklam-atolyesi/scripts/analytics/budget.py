"""S02 ekonomi, bütçe, matris boyutu, tur takvimi ve toplam harcama planı (spec 4.4, 6.2, 6.3).

Kullanım: budget.py --input s02_input.json --out budget_plan.json
Girdi alanları (para birimi profilin reklam hesabı birimindedir; üretim/servis ücretleri dahil değildir):
  cycle_no, adset_daily, exploration_share, cpm (+ cpm_source: benchmarks|history|assumption), decision_metric: hook|ctr,
  budget_total (null = sınır yok), spend_to_date (doğrulanmış; null = eşleme eksik), data_cutoff (ISO tarih),
  launch_at (ISO tarih), other_daily_budgets: [..] (aynı kampanyanın diğer aktif reklam setleri), planned_changes: [{from, daily}],
  risk_per_ad (onaylı; null), target_cpa (doğrulanmış; null), result_type, test_start_hour (0 = gece yarısı), creative_test_tool_max,
  scale_layer_daily (açık ölçekleme katmanının günlük bütçesi; budget_plan_json.scale_layer.daily_budget, status active; yoksa 0)
Ölçekleme uygunluğu (coach 6a): scale_check() — coach.py kullanır.
Çıktı: kreatif başına gereken harcama, 7/14 gün testte izin verilen test reklamı sayısı, seçilen test günü, tur süresi, takvim,
       toplam harcama tahmini ve sığma durumu, risk sınırı etkisi, uyarılar. Bu bir tahmindir; Meta'nın günlük harcamasının sabit
       ya da kesin sınırlı olduğu iddia edilmez; gösterim eşiği hesabı güç analizi veya kazanan bulma garantisi değildir.
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit, read_json, write_json  # noqa: E402

THRESHOLD_IMPRESSIONS = {"hook": 1000, "ctr": 3000}
# Ölçekleme seti günlük bütçesi ≥ 7 × hedef maliyet: 7 günde ~50 optimizasyon olayından türetilmiş YEREL eşik (ref-legal-tr-meta §7).
SCALE_MIN_DAILY_MULT = 7


def scale_check(*, structure: str | None, cost_ok: bool, target_cpa: float | None, economics_exact: bool,
                proposed_daily: float | None, budget_total: float | None, spend_to_date: float | None,
                other_daily: float, days_left: int) -> dict:
    """Ölçekleme katmanına taşıma için dört koşul (coach 6a). Sonuç tahmindir; insan Ads Manager'da uygular.
    other_daily: ölçekleme dışındaki aktif günlük bütçeler (ana reklam seti ve varsa açık katman dışı setler)."""
    min_daily = round(SCALE_MIN_DAILY_MULT * float(target_cpa), 2) if (target_cpa and economics_exact) else None
    daily = float(proposed_daily) if proposed_daily else min_daily
    checks = {"structure": structure == "creative_test", "cost": bool(cost_ok and economics_exact),
              "min_daily": bool(min_daily is not None and daily is not None and daily + 1e-9 >= min_daily)}
    reasons = []
    if not checks["structure"]:
        reasons.append("yapı doğrulanmış kreatif test değil (bootstrap/doğrulanmamış): hüküm 'Meta'nın dağıtımı altında'")
    if not checks["cost"]:
        reasons.append("hedef maliyet altı yeterli kanıt yok ya da ekonomi doğrulanmamış")
    if min_daily is None:
        reasons.append("doğrulanmış hedef maliyet yok: öğrenme bütçesi hesaplanamaz")
    elif not checks["min_daily"]:
        reasons.append(f"günlük bütçe {daily:.2f} < {min_daily:.2f} (= {SCALE_MIN_DAILY_MULT} × hedef)")
    need = None
    if daily is not None:
        need = round((daily + float(other_daily)) * max(0, int(days_left)), 2)
    if budget_total is None:
        checks["fits_total"] = True
        fits_note = "toplam harcama sınırı tanımlanmamış (kullanıcı kararı); sığma kontrolü yapılamadı"
    elif spend_to_date is None or need is None:
        checks["fits_total"] = False
        fits_note = "gerçekleşen harcama doğrulanamadı: sığma onay bekler"
        reasons.append(fits_note)
    else:
        remaining = float(budget_total) - float(spend_to_date)
        checks["fits_total"] = need <= remaining + 1e-9
        fits_note = f"tahmini ek harcama {need:.2f}, kalan {remaining:.2f}"
        if not checks["fits_total"]:
            reasons.append(f"toplam sınıra sığmıyor: {fits_note} (eksik {need - remaining:.2f})")
    return {"eligible": all(checks.values()), "checks": checks, "min_daily": min_daily, "proposed_daily": daily,
            "days_left": int(days_left), "projected_need": need, "fits_note": fits_note, "reasons": reasons,
            "note": "Taşıma ayrıca okunmuş gönderi kimliği ister (post_id); yoksa madde yazılmaz. Bu bir tahmindir."}


def per_creative_spend(cpm: float, metric: str) -> float:
    return THRESHOLD_IMPRESSIONS[metric] * cpm / 1000.0


def required_test_days(per_creative: float, n_ads: int, daily_test: float) -> int:
    """gereken_test_günü = max(7, 7 × ceil((kreatif başına harcama × reklam sayısı / günlük test bütçesi) / 7))."""
    if daily_test <= 0:
        raise ValueError("günlük test bütçesi ≤ 0")
    return max(7, 7 * math.ceil((per_creative * n_ads / daily_test) / 7))


def daily_test_budget(cycle_no: int, adset_daily: float, exploration_share: float) -> float:
    return adset_daily if cycle_no <= 1 else adset_daily * exploration_share


def plan(inp: dict) -> dict:
    warnings: list[str] = []
    cycle_no = int(inp.get("cycle_no", 1))
    share = float(inp.get("exploration_share", 0.2))
    if not (0.05 <= share <= 0.2):
        raise SystemExit("exploration_share 0,05–0,2")
    adset_daily = float(inp["adset_daily"])
    daily_test = daily_test_budget(cycle_no, adset_daily, share)
    metric = inp.get("decision_metric", "hook")
    cpm = float(inp["cpm"])
    cpm_src = inp.get("cpm_source", "assumption")
    if cpm_src == "assumption":
        warnings.append("CPM VARSAYIM: account_benchmarks/geçmiş yok")
    pc = per_creative_spend(cpm, metric)
    tool_max = int(inp.get("creative_test_tool_max", 5))
    structure = "bootstrap" if cycle_no <= 1 else "creative_test"
    out: dict = {"structure": structure, "decision_metric": metric, "threshold_impressions": THRESHOLD_IMPRESSIONS[metric],
                 "cpm": cpm, "cpm_source": cpm_src, "per_creative_spend": round(pc, 2), "daily_test_budget": round(daily_test, 2),
                 "exploration_share": share if cycle_no > 1 else None, "creative_test_tool_max": tool_max if structure == "creative_test" else None}
    if daily_test <= 0:
        out.update({"allowed_test_ads": 0, "production_blocked": True, "reason": "günlük test bütçesi ≤ 0: hesap yapılmaz, üretim bekler"})
        return out
    risk = inp.get("risk_per_ad")
    if risk is not None and float(risk) < pc:
        warnings.append(f"onaylı reklam başı risk sınırı ({risk}) kreatif başına gereken harcamanın ({pc:.2f}) altında: bu reklamlar eşiğe ulaşması beklenen sayılmaz")
    by_days = {}
    for d in (7, 14):
        tb = daily_test * d
        n = math.floor(tb / pc) if pc > 0 else 0
        if structure == "creative_test":
            n = min(n, tool_max)
        if risk is not None and float(risk) < pc:
            n = 0
        by_days[d] = {"test_budget": round(tb, 2), "allowed_test_ads": n}
    chosen = 7 if by_days[7]["allowed_test_ads"] >= 2 else (14 if by_days[14]["allowed_test_ads"] >= 2 else None)
    out["by_test_days"] = by_days
    if chosen is None:
        need_daily = 2 * pc / 14
        if structure == "creative_test":
            need_daily_adset = need_daily / share
        else:
            need_daily_adset = need_daily
        out.update({"allowed_test_ads": by_days[14]["allowed_test_ads"], "test_days": None, "production_blocked": True,
                    "required_daily_adset_budget": round(need_daily_adset, 2),
                    "shortfall_daily": round(max(0.0, need_daily_adset - adset_daily), 2),
                    "reason": "14 günlük testte bile iki ayrı reklam eşiğe ulaşamıyor: S03–S14 bekler; bütçe değişikliği uygulanmaz"})
        out["warnings"] = warnings
        return out
    n_allowed = by_days[chosen]["allowed_test_ads"]
    cycle_days = chosen + 7
    out.update({"test_days": chosen, "cycle_days": cycle_days, "allowed_test_ads": n_allowed,
                "required_test_days_formula": required_test_days(pc, n_allowed, daily_test), "production_blocked": False})
    if inp.get("target_cpa") and inp.get("result_type") == "purchase":
        concept_budget = daily_test * chosen / max(1, n_allowed)
        exp_p = concept_budget / float(inp["target_cpa"])
        out["expected_purchases_per_concept"] = round(exp_p, 2)
        if exp_p < 10:
            warnings.append("konsept başına beklenen satın alma < 10: CPA hükmü güvenilir olmaz, yalnızca geniş aralıklı yön tahmini (6.3)")
    if int(inp.get("test_start_hour", 0)) != 0:
        warnings.append("test gece yarısı başlamazsa iki sınır günü kontrollü karşılaştırmadan çıkar (6.4); hesap saat diliminde gece yarısı başlangıç önerilir")
    launch = dt.date.fromisoformat(inp["launch_at"][:10]) if inp.get("launch_at") else None
    if launch:
        test_end = launch + dt.timedelta(days=chosen)
        plan_day = test_end + dt.timedelta(days=3)
        next_launch = plan_day + dt.timedelta(days=4)
        out["calendar"] = {"G0_launch": launch.isoformat(), "test_end": test_end.isoformat(), "plan_day": plan_day.isoformat(),
                           "shoot": [(plan_day + dt.timedelta(days=1)).isoformat(), (plan_day + dt.timedelta(days=2)).isoformat()],
                           "night_production": (plan_day + dt.timedelta(days=2)).isoformat(), "next_launch": next_launch.isoformat(),
                           "cycle_days": cycle_days, "rule": "plan günü = test bitişi + 3, yayın = plan günü + 4"}
    # toplam harcama planı (6.3)
    bt = inp.get("budget_total")
    cutoff = dt.date.fromisoformat(inp["data_cutoff"][:10]) if inp.get("data_cutoff") else (launch or dt.date.today())
    horizon_end = (launch + dt.timedelta(days=cycle_days)) if launch else cutoff + dt.timedelta(days=cycle_days)
    days = max(0, (horizon_end - cutoff).days)
    others = sum(float(x) for x in inp.get("other_daily_budgets", []) or [])
    scale_daily = float(inp.get("scale_layer_daily") or 0)
    if scale_daily < 0:
        raise SystemExit("scale_layer_daily ≥ 0")
    others += scale_daily
    changes = sorted(inp.get("planned_changes", []) or [], key=lambda c: c["from"])
    proj = 0.0
    for i in range(days):
        d = cutoff + dt.timedelta(days=i)
        daily = adset_daily
        for c in changes:
            if dt.date.fromisoformat(c["from"][:10]) <= d:
                daily = float(c["daily"])
        if launch and d < launch and cycle_no <= 1 and not inp.get("ads_running_before_launch"):
            daily = 0.0  # ilk tur: yayından önce harcama yok
        proj += daily + others
    out["spend_projection"] = {"from": cutoff.isoformat(), "to": horizon_end.isoformat(), "days": days, "projected_additional": round(proj, 2),
                               "scale_layer_daily": round(scale_daily, 2),
                               "note": "tek reklam setinin bütçesi eski ve yeni reklamlar için bir kez sayılır; test payı tekrar eklenmez; "
                                       "açık ölçekleme katmanı ayrı kampanya olduğu için günlük bütçesi ayrıca eklenir"}
    if bt is None:
        out["fits_total_budget"] = None
        out["budget_total"] = None
        warnings.append("toplam harcama sınırı tanımlanmadı (NULL, kullanıcı kararı)")
    else:
        std = inp.get("spend_to_date")
        if std is None:
            out["fits_total_budget"] = False
            out["remaining"] = None
            warnings.append("gerçekleşen kampanya harcaması doğrulanamadı (eşleme/tarih eksik): bütçe uygunluğu onayı bekler")
        else:
            remaining = float(bt) - float(std)
            out["remaining"] = round(remaining, 2)
            out["fits_total_budget"] = proj <= remaining + 1e-9
            if not out["fits_total_budget"]:
                out["total_shortfall"] = round(proj - remaining, 2)
                warnings.append(f"tahmini ek harcama {proj:.2f} kalan sınırı {remaining:.2f} aşıyor: S02 üretime geçmez, S14 onaya açılmaz")
        out["budget_total"] = float(bt)
    out["warnings"] = warnings
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out")
    a = ap.parse_args()
    res = plan(read_json(a.input))
    if a.out:
        write_json(a.out, res)
    emit(res)


if __name__ == "__main__":
    main()
