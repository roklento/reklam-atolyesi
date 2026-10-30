"""Koçluk istatistiği (spec 6.6): Beta-Binom oranlar, Gamma sonuç maliyeti, eşikler ve hüküm dili.

- Oranlar: hesap önseli (aynı profil + objective, test öncesi, dondurulmuş) → kreatif Beta-Binom; konsept için uygun pay/payda toplanır.
- Önsel yoksa Beta(1,1). Hesap: Beta(a+başarı, b+payda−başarı); %90 eşit kuyruklu aralık; uygun geçmişe ve diğer konsepte üstünlük
  olasılığı 10.000 sonsal örnek, sabit tohum 1729, girdi sırası kimliğe göre sabit.
- Sonuç maliyeti: doğrulanmış hedef T>0 → s=harcama/T, λ ~ Gamma(0.5+y, rate 0.5+s); maliyet örnekleri T/λ; P(λ>1) hedef altı olasılığı.
- Eşikler: hook ≥ 1.000 gösterim; CTR ≥ 3.000 gösterim; sonuç maliyeti ≥ 10 uygun sonuç. Eşik altı → 'yön/yetersiz veri'.
- Huni oranları iç içe koşullu olasılık değildir ve çarpılmaz. Bunlar model koşullarındaki belirsizlik ölçüleridir;
  Meta dağıtımının seçim yanlılığını ortadan kaldırmaz.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats

SEED = 1729
DRAWS = 10_000
INTERVAL = 0.90
THRESHOLDS = {"hook_rate": ("impressions", 1000), "ctr_link": ("impressions", 3000), "hold_rate": ("video_3s", 1000),
              "cvr": ("link_clicks", 300),
              # 2.4.0 tıklama sonrası adımlar: payda (bir önceki adım) en az 30 kişi. YEREL sezgisel eşik, Meta kuralı değil.
              **{m: ("previous_step", 30) for m in ("step_landing", "step_view", "step_cart", "step_checkout", "step_purchase")}}
RESULT_THRESHOLD = 10
RATE_DEF = {"hook_rate": ("video_3s", "impressions"), "hold_rate": ("thruplay", "video_3s"),
            "ctr_link": ("link_clicks", "impressions"), "cvr": ("purchases", "link_clicks")}


@dataclass
class RatePosterior:
    metric: str
    a: float
    b: float
    successes: float
    trials: float
    mean: float
    lo: float
    hi: float
    threshold_met: bool
    label: str

    def as_dict(self) -> dict:
        return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in self.__dict__.items()}


def rate_posterior(metric: str, successes: float, trials: float, prior: tuple[float, float] | None = None,
                   threshold_basis: float | None = None) -> RatePosterior | None:
    """Pay > payda ya da binom modele uymayan oranlar model dışında kalır (None)."""
    if trials is None or trials <= 0 or successes is None or successes < 0 or successes > trials:
        return None
    a0, b0 = prior or (1.0, 1.0)
    s, n = float(round(successes)), float(round(trials))
    a, b = a0 + s, b0 + (n - s)
    lo, hi = stats.beta.ppf([(1 - INTERVAL) / 2, 1 - (1 - INTERVAL) / 2], a, b)
    basis_name, thr = THRESHOLDS.get(metric, ("trials", 0))
    basis = threshold_basis if threshold_basis is not None else n
    met = basis >= thr
    return RatePosterior(metric, a, b, s, n, a / (a + b), float(lo), float(hi), met, "kanıt" if met else "yön/yetersiz veri")


def superiority(posts: dict[str, RatePosterior], reference_mean: float | None = None, seed: int = SEED, draws: int = DRAWS) -> dict:
    """Her öznenin diğerlerinin en iyisine ve hesap geçmişi ortalamasına üstünlük olasılığı. Girdi sırası kimliğe göre sabit."""
    keys = sorted(posts)
    if not keys:
        return {}
    rng = np.random.default_rng(seed)
    samp = {k: rng.beta(posts[k].a, posts[k].b, size=draws) for k in keys}
    out = {}
    for k in keys:
        others = [samp[o] for o in keys if o != k]
        p_best = float(np.mean(samp[k] > np.max(np.vstack(others), axis=0))) if others else None
        p_ref = float(np.mean(samp[k] > reference_mean)) if reference_mean is not None else None
        out[k] = {"p_best": p_best, "p_above_history": p_ref}
    return out


def pairwise(a: RatePosterior, b: RatePosterior, seed: int = SEED, draws: int = DRAWS) -> float:
    rng = np.random.default_rng(seed)
    x = rng.beta(a.a, a.b, size=draws)
    y = rng.beta(b.a, b.b, size=draws)
    return float(np.mean(x > y))


def cost_posterior(spend: float, results: float, target: float | None, verified_target: bool, seed: int = SEED, draws: int = DRAWS) -> dict:
    """Sabit zayıf Gamma(0.5, 0.5) önsel; hesap geçmişi eklenmez. Hedef yoksa gerçekleşen maliyet gösterilir, olasılık üretilmez."""
    y = float(results or 0)
    realized = (spend / y) if y > 0 else None
    out = {"spend": spend, "results": y, "realized_cost": realized, "threshold_met": y >= RESULT_THRESHOLD,
           "label": "kanıt" if y >= RESULT_THRESHOLD else "yön/yetersiz veri"}
    if not target or target <= 0 or not verified_target:
        out["note"] = "doğrulanmış hedef maliyet yok: olasılık üretilmez"
        return out
    s = spend / target
    shape, rate = 0.5 + y, 0.5 + s
    rng = np.random.default_rng(seed)
    lam = rng.gamma(shape, 1.0 / rate, size=draws)
    costs = target / lam
    lo, hi = np.quantile(costs, [(1 - INTERVAL) / 2, 1 - (1 - INTERVAL) / 2])
    out.update({"gamma_shape": shape, "gamma_rate": rate, "p_below_target": float(np.mean(lam > 1.0)),
                "p_below_target_exact": float(stats.gamma.sf(1.0, shape, scale=1.0 / rate)),
                "cost_interval": [float(lo), float(hi)], "cost_median": float(np.median(costs))})
    return out


def prior_from_mean(m: float, n_source: float, n_cap: float = 30) -> tuple[float, float]:
    n_eff = min(n_source, n_cap)
    a, b = max(0.001, m * n_eff), max(0.001, (1 - m) * n_eff)
    if a + b > n_cap:
        k = n_cap / (a + b)
        a, b = a * k, b * k
    return a, b


def verdict_language(threshold_met: bool, structure: str | None, enhanced: bool = False) -> str:
    base = "kanıt" if threshold_met else "yön/yetersiz veri"
    tail = " · Meta iyileştirmesi açık" if enhanced else ""  # 2.3.0: açık Advantage+ kreatif iyileştirmesi ikinci değişkendir
    if structure in ("bootstrap", "unverified", "deviated", None):
        return base + " · Meta'nın dağıtımı altında" + (" · doğrulanmamış yapı" if structure in ("unverified", "deviated") else "") + tail
    return base + tail


def coverage_simulation(true_p: float, n: int, reps: int = 2000, seed: int = SEED) -> dict:
    """Simülasyon raporu: gerçekleşen kapsama (nominal kapsama her veri düzeninde garanti edilmez; 6.15)."""
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(reps):
        s = rng.binomial(n, true_p)
        lo, hi = stats.beta.ppf([0.05, 0.95], 1 + s, 1 + n - s)
        hits += int(lo <= true_p <= hi)
    return {"true_p": true_p, "n": n, "reps": reps, "realized_coverage": hits / reps, "nominal": INTERVAL}


def isfinite(x) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False
