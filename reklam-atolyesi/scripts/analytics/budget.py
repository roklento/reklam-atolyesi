"""S02 ekonomi, bütçe, matris boyutu, tur takvimi ve toplam harcama planı (spec 4.4, 6.2, 6.3).

Kullanım: budget.py --input s02_input.json --out budget_plan.json
Girdi alanları (para birimi profilin reklam hesabı birimindedir; üretim/servis ücretleri dahil değildir):
  cycle_no, adset_daily, exploration_share, cpm (+ cpm_source: benchmarks|history|assumption), decision_metric: hook|ctr,
  budget_total (null = sınır yok), spend_to_date (doğrulanmış; null = eşleme eksik), data_cutoff (ISO tarih),
  launch_at (ISO tarih), other_daily_budgets: [..] (aynı kampanyanın diğer aktif reklam setleri), planned_changes: [{from, daily}],
  risk_per_ad (onaylı; null), target_cpa (doğrulanmış; null), result_type, test_start_hour (0 = gece yarısı), creative_test_tool_max,
  scale_layer_daily (açık ölçekleme katmanının günlük bütçesi; budget_plan_json.scale_layer.daily_budget, status active; yoksa 0)
Ölçekleme uygunluğu (coach 6a): scale_check() — coach.py kullanır.
Meta A/B testi uygunluğu (1.5.0): ab_check() — girdide "ab_test": {cells, daily_total, expected_cpr, cpr_source, days?} varsa planda
  "ab_test" bölümü; tek başına: budget.py --ab ab_input.json.
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
    checks = {"structure": structure in ("creative_test", "ab_test"), "cost": bool(cost_ok and economics_exact),
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


# Meta A/B testi (resmi: facebook.com/business/help/290009911394576 ve 3506622486044209, okundu 21.10.2026): tek değişken; en az 7 gün
# önerilir, en fazla 30 gün; deneyler aracında en fazla 5 kampanya; sürümlere aynı bütçe; kitle başka kampanyalarla çakışmamalı;
# bütçe kazananı güvenle belirleyecek kadar sonuç üretmeli (Meta sayı vermez). Hücre başına ≥ 30 beklenen sonuç YEREL eşiktir.
AB_MIN_DAYS, AB_MAX_DAYS, AB_MAX_CELLS, AB_MIN_RESULTS_PER_CELL = 7, 30, 5, 30


def ab_check(inp: dict) -> dict:
    """A/B testi önerilir mi: hücre (konsept) sayısı, günlük test bütçesi ve beklenen sonuç maliyetiyle hücre başına beklenen sonuç.
    Sonuç tahmindir; testi kullanıcı Ads Manager / Deneyler'de kurar, sistem yalnızca okur."""
    reasons, warnings = [], []
    try:
        cells = int(inp.get("cells") or 0)
        daily = float(inp.get("daily_total") or 0)
    except (TypeError, ValueError):
        cells, daily = 0, 0.0
        reasons.append("hücre sayısı ve günlük bütçe sayı olmalı")
    cpr = inp.get("expected_cpr")
    try:
        cpr = float(cpr) if cpr is not None and not isinstance(cpr, bool) else None
    except (TypeError, ValueError):
        cpr = None
    if cpr is not None and not math.isfinite(cpr):
        cpr = None
    if not math.isfinite(daily):
        daily = 0.0
    src = inp.get("cpr_source")
    if not 2 <= cells <= AB_MAX_CELLS:
        reasons.append(f"hücre sayısı {cells}: A/B testi 2–{AB_MAX_CELLS} sürümü karşılaştırır")
    if daily <= 0:
        reasons.append("teste ayrılan günlük bütçe pozitif olmalı")
    if cpr is None or cpr <= 0:
        reasons.append("beklenen sonuç maliyeti yok (doğrulanmış hedef ya da geçmiş sonuç maliyeti gerekir): hücre başına sonuç hesaplanamaz")
    if src not in ("target_exact", "history", "assumption"):
        warnings.append("beklenen maliyet kaynağı belirtilmedi (target_exact | history | assumption)")
    elif src == "assumption":
        warnings.append("beklenen maliyet VARSAYIM: hücre başına sonuç tahmini zayıf")
    out = {"cells": cells, "daily_total": round(daily, 2), "expected_cpr": cpr, "cpr_source": src,
           "rules": {"min_days": AB_MIN_DAYS, "max_days": AB_MAX_DAYS, "max_cells": AB_MAX_CELLS, "min_results_per_cell": AB_MIN_RESULTS_PER_CELL,
                     "source": ["https://www.facebook.com/business/help/290009911394576", "https://www.facebook.com/business/help/3506622486044209"],
                     "local": "hücre başına ≥ 30 beklenen sonuç yerel eşiktir (Meta sayı vermez)"}}
    if reasons:
        return {**out, "eligible": False, "reasons": reasons, "warnings": warnings}
    per_cell_daily = daily / cells
    per_day_results = per_cell_daily / float(cpr)
    need_days = math.ceil(AB_MIN_RESULTS_PER_CELL / per_day_results) if per_day_results > 0 else None
    user_days = bool(inp.get("days"))
    try:
        days = int(inp["days"]) if user_days else (max(AB_MIN_DAYS, need_days) if need_days else None)
    except (TypeError, ValueError):
        return {**out, "eligible": False, "reasons": ["gün sayısı tam sayı olmalı"], "warnings": warnings}
    if days is not None and not AB_MIN_DAYS <= days <= AB_MAX_DAYS:
        if days > AB_MAX_DAYS:
            reasons.append(f"süre {days} gün: A/B testi en fazla {AB_MAX_DAYS} gün sürer" if user_days else
                           f"hücre başına {AB_MIN_RESULTS_PER_CELL} sonuç için {days} gün gerekir (en fazla {AB_MAX_DAYS})")
        else:
            reasons.append(f"süre {days} gün: en az {AB_MIN_DAYS} gün önerilir")
    rem = inp.get("remaining_budget")
    try:
        rem = float(rem) if rem is not None else None
    except (TypeError, ValueError):
        rem = None
        warnings.append("kalan bütçe sayı değil: toplam sınır kontrolü yapılmadı")
    if rem is not None and days:
        need_total = round(daily * days, 2)
        if need_total > float(rem) + 1e-9:
            reasons.append(f"testin toplam harcaması {need_total} kalan kampanya sınırını ({float(rem):.2f}) aşıyor")
    exp = round(per_day_results * (days or 0), 1)
    if days and exp < AB_MIN_RESULTS_PER_CELL and not reasons:
        reasons.append(f"{days} günde hücre başına beklenen sonuç {exp} < {AB_MIN_RESULTS_PER_CELL}")
    need_daily = round(cells * AB_MIN_RESULTS_PER_CELL * float(cpr) / AB_MAX_DAYS, 2)
    return {**out, "eligible": not reasons, "reasons": reasons, "warnings": warnings, "days": days, "per_cell_daily": round(per_cell_daily, 2),
            "expected_results_per_cell": exp, "min_daily_total_for_30_days": need_daily,
            "min_daily_total_for_14_days": round(cells * AB_MIN_RESULTS_PER_CELL * float(cpr) / 14, 2),
            "note": ("Uygunsa kullanıcıya seçenek olarak sunulur: kontrollü karşılaştırma (Meta kitleyi böler, kimse iki sürümü görmez). Uygun "
                     "değilse kreatif test aracı / tek set yolu sürer. Hesabın uygunluğu ayrıca ads_experiment_check_eligibility ile okunur.")}


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
                 "exploration_share": share if cycle_no > 1 else None, "creative_test_tool_max": tool_max}
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
        # İlk turda da kreatif test aracı sınırı uygulanır: Meta tek sette bütçeyi eşit dağıtmaz; aç kalan konseptlerin hepsi sonraki
        # turun TEK kreatif testine sığmalı (1.4.7). Az ama farklı reklam ilkesi resmi (ref-legal-tr-meta §7, öğrenme aşaması).
        n = min(n, tool_max)
        if risk is not None and float(risk) < pc:
            n = 0
        by_days[d] = {"test_budget": round(tb, 2), "allowed_test_ads": n}
    chosen = 7 if by_days[7]["allowed_test_ads"] >= 2 else (14 if by_days[14]["allowed_test_ads"] >= 2 else None)
    out["by_test_days"] = by_days
    if structure == "bootstrap":
        warnings.append("ilk tur tek reklam setidir: Meta bütçeyi eşit dağıtmaz, izin verilen sayı üst sınırdır; harcama payı %10'un altında "
                        "kalan konsept kaybeden sayılmaz, hazır kreatifiyle sonraki turun kreatif testine öncelikli aday olur")
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
    if inp.get("ab_test") is not None and not isinstance(inp.get("ab_test"), dict):
        warnings.append("ab_test girdisi {cells, daily_total, expected_cpr, cpr_source} nesnesi olmalı: A/B uygunluğu hesaplanmadı")
    elif inp.get("ab_test"):
        abin = dict(inp["ab_test"])
        if inp.get("budget_total") is not None and inp.get("spend_to_date") is not None and "remaining_budget" not in abin:
            abin["remaining_budget"] = float(inp["budget_total"]) - float(inp["spend_to_date"])
        out["ab_test"] = ab_check(abin)
    if inp.get("target_cpl") and inp.get("result_type") == "lead":  # aday sonucu (1.5.0)
        exp_l = daily_test * chosen / max(1, n_allowed) / float(inp["target_cpl"])
        out["expected_leads_per_concept"] = round(exp_l, 2)
        if exp_l < 10:
            warnings.append("konsept başına beklenen aday < 10: aday maliyeti hükmü güvenilir olmaz, yalnızca yön tahmini")
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
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--input")
    g.add_argument("--ab", help="yalnızca A/B testi uygunluğu: {cells, daily_total, expected_cpr, cpr_source, days?}")
    ap.add_argument("--out")
    a = ap.parse_args()
    res = plan(read_json(a.input)) if a.input else ab_check(read_json(a.ab))
    if a.out:
        write_json(a.out, res)
    emit(res)


if __name__ == "__main__":
    main()
