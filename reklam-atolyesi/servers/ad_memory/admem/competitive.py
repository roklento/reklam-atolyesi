"""Rekabet analizi saf fonksiyonları (spec 4.5–4.7, 10). Hem ad-memory hem scripts/competitive bunları kullanır.

Bütün "işe yarıyor" çıkarımları vekil sinyaldir (proxy); performans kanıtı değildir.
Rakip metinleri veridir: içlerindeki yönergeler uygulanmaz, yalnızca işaretlenir (ilke 14).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
from collections import defaultdict
from typing import Any, Iterable

from .util import ngram_overlap, tr_fold

LONG_RUNNING_DAYS = 30
WEAK_COVERAGE_CONCEPTS = 10
_INSTRUCTION_PATTERNS = [
    r"ignore (all |the )?(previous|prior|above)", r"disregard (the |all )?(previous|instructions)", r"you are (now )?(an?|the) ",
    r"system prompt", r"\bassistant\b", r"\bclaude\b", r"\bllm\b", r"\bai model\b",
    r"onceki (talimat|yonerge)", r"talimatlari (yok ?say|unut)", r"yonergeleri (yok ?say|unut)", r"sistem (mesaj|istem)",
    r"(onay|izin) ver(in)?\b.*\b(otomatik|hemen)", r"\bkapiyi gec", r"butceyi (artir|degistir)", r"\bmcp\b", r"tool[_ ]?call",
]


def normalize(text: str | None) -> str:
    t = tr_fold(text or "")
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def detect_instruction(text: str | None) -> bool:
    """Metinde sisteme/asistana yönelik yönerge izi var mı? Varsa yalnızca işaretlenir; asla uygulanmaz."""
    t = tr_fold(text or "")
    return any(re.search(p, t) for p in _INSTRUCTION_PATTERNS)


def variant_key(ad: dict) -> str:
    """Aynı metin ya da görsel çekirdeğini paylaşan reklamlar tek rakip konsepti olur (4.5 adım 3)."""
    core = ad.get("visual_hash")
    if not core:
        body = normalize(ad.get("body_text"))
        body = re.sub(r"\d+", " ", body)  # fiyat/indirim/numara farkı aynı çekirdek sayılır
        words = body.split()
        core = " ".join(words[:18]) or normalize(ad.get("title")) or str(ad.get("library_id"))
    return hashlib.sha1(f"{ad.get('competitor_id')}|{core}".encode("utf-8")).hexdigest()[:12]


def _d(s: str | None) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def observed_run_days(ad: dict, as_of: str | None = None) -> int | None:
    """Gözlenen yayın süresi: başlangıç tarihi + bizim görüntülerimizde son görülme (ya da durma tarihi)."""
    start = _d(ad.get("start_date")) or _d(ad.get("first_seen_at"))
    end = _d(ad.get("stop_date")) or _d(ad.get("last_seen_at")) or _d(as_of)
    if not start or not end:
        return None
    return max(0, (end - start).days)


def diff(previous_active: Iterable[str], current: Iterable[dict]) -> dict:
    """Önceki görüntüdeki aktif reklam kimlikleri ile güncel reklamların farkı: yeni · süren · durmuş."""
    prev = set(previous_active)
    cur_active = {a["library_id"] for a in current if a.get("is_active", True)}
    cur_all = {a["library_id"] for a in current}
    return {"new": sorted(cur_active - prev), "continuing": sorted(cur_active & prev),
            "stopped": sorted((prev - cur_active) | {a["library_id"] for a in current if not a.get("is_active", True) and a["library_id"] in prev}),
            "seen_inactive_unknown_before": sorted({x for x in cur_all - cur_active} - prev)}


def group_concepts(ads: list[dict]) -> dict[str, dict]:
    groups: dict[str, dict] = {}
    for a in ads:
        g = groups.setdefault(a.get("variant_group") or variant_key(a), {"variant_group": a.get("variant_group") or variant_key(a),
                                                                         "competitor_id": a.get("competitor_id"), "ads": [],
                                                                         "features": {}})
        g["ads"].append(a)
        for k, v in (a.get("features") or {}).items():
            if v not in (None, "unknown"):
                g["features"].setdefault(k, v)
    for g in groups.values():
        runs = [observed_run_days(a) for a in g["ads"]]
        runs = [r for r in runs if r is not None]
        g["n_variants"] = len(g["ads"])
        g["max_run_days"] = max(runs) if runs else None
        g["long_running"] = bool(runs) and max(runs) >= LONG_RUNNING_DAYS
        g["refreshed"] = len({a.get("start_date") for a in g["ads"] if a.get("start_date")}) > 1
    return groups


def build_map(concepts: list[dict], axes: list[str], competitor_kinds: dict[Any, str]) -> dict:
    """Rekabet haritası: eksen değeri × rakip; her hücrede konsept ve uzun soluklu konsept sayısı (4.5 adım 7)."""
    cells: dict[str, dict[str, dict]] = {ax: defaultdict(lambda: defaultdict(lambda: {"concepts": 0, "long_running": 0})) for ax in axes}
    for c in concepts:
        for ax in axes:
            v = (c.get("features") or {}).get(ax, "unknown")
            vals = v if isinstance(v, list) else [v]
            for val in vals:
                cell = cells[ax][str(val)][str(c.get("competitor_id"))]
                cell["concepts"] += 1
                if c.get("long_running"):
                    cell["long_running"] += 1
    out = {ax: {val: dict(per) for val, per in vals.items()} for ax, vals in cells.items()}
    return {"axes": out, "competitor_kinds": {str(k): v for k, v in competitor_kinds.items()}}


def derive_insights(cmap: dict, n_competitors: int, product_supports: dict[str, set[str]], snapshot_ref: dict) -> list[dict]:
    """Norm, kanıtlanmış açı (vekil) ve boşluk adayları. Boşluk bir test fırsatıdır, vaat değil."""
    insights: list[dict] = []
    kinds = cmap.get("competitor_kinds", {})
    for ax, vals in cmap["axes"].items():
        for val, per in vals.items():
            if val == "unknown":
                continue
            comps = [c for c, cell in per.items() if cell["concepts"] > 0]
            long_comps = [c for c, cell in per.items() if cell["long_running"] > 0]
            if n_competitors >= 2 and len(comps) / max(1, n_competitors) > 0.5:
                insights.append({"kind": "norm", "axis": ax, "label": "observation",
                                 "statement": f"{len(comps)}/{n_competitors} rakip {ax}={val} kullanıyor (kategori normu)",
                                 "evidence": {**snapshot_ref, "axis": ax, "value": val, "competitors": comps}})
            strong = [c for c in long_comps if kinds.get(c) != "aspirational"]
            if len(long_comps) >= 2 and strong:
                insights.append({"kind": "proven_angle", "axis": ax, "label": "proxy",
                                 "statement": f"{ax}={val} birden çok rakipte uzun soluklu (≥ {LONG_RUNNING_DAYS} gün): kategoride işe yarıyor olabilir — vekil sinyal",
                                 "evidence": {**snapshot_ref, "axis": ax, "value": val, "competitors": long_comps}})
    for ax, supported in product_supports.items():
        used = {v for v, per in cmap["axes"].get(ax, {}).items() if any(cell["concepts"] > 0 for cell in per.values())}
        for val in sorted(supported - used - {"unknown"}):
            insights.append({"kind": "gap", "axis": ax, "label": "proxy",
                             "statement": f"{ax}={val} ürünün kanıtlanabilir iddiaları/anlarıyla uyumlu ve rakiplerde görülmedi: test fırsatı, vaat değil",
                             "evidence": {**snapshot_ref, "axis": ax, "value": val}})
    return insights


def distance(concept_features: dict, source_features: dict, own_texts: list[str], source_texts: list[str],
             min_axes: int = 2, max_overlap: float = 0.20) -> dict:
    """Uzaklık kuralı (bölüm 10): açı dışında en az iki eksende fark + normalize metinde 4-gram örtüşmesi ≤ eşik."""
    axes = sorted((set(concept_features) | set(source_features)) - {"angle", "competitive_role"})
    differing, unknown = [], []
    for ax in axes:
        a, b = concept_features.get(ax, "unknown"), source_features.get(ax, "unknown")
        if a == "unknown" or b == "unknown":
            unknown.append(ax)
        elif a != b:
            differing.append(ax)
    overlaps = [ngram_overlap(o, s, 4) for o in own_texts if o for s in source_texts if s]
    worst = max(overlaps) if overlaps else 0.0
    passed = len(differing) >= min_axes and worst <= max_overlap
    reasons = []
    if len(differing) < min_axes:
        reasons.append(f"yalnızca {len(differing)} eksende farklı (gereken ≥ {min_axes}; bilinmeyen eksenler fark sayılmaz)")
    if worst > max_overlap:
        reasons.append(f"metin örtüşmesi %{worst*100:.0f} > %{max_overlap*100:.0f}")
    return {"passed": passed, "differing_axes": differing, "unknown_axes": unknown, "max_4gram_overlap": round(worst, 4),
            "reasons": reasons, "note": "Otomatik kontrol hukuki uygunluk kanıtı değildir; şüphede insan kararı gerekir."}
