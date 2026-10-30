"""S16 analiz boru hattı (spec 6.3–6.11, 6.16). YALNIZCA değişmez karar girdisi kopyasını okur (decision_input_snapshot);
hesap sırasında tablodan tekrar veri almaz. Çıktı deterministiktir: aynı kopya → aynı sonuç.

Kullanım: coach.py --snapshot reports/c1-coach_report-input-v1.json --out reports/c1-analysis-v1.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import emit, read_json, sha256_file, write_json  # noqa: E402
import bayes as B  # noqa: E402
import budget as BU  # noqa: E402

UPPER = ("hook_rate", "hold_rate")
STAGE_METRICS = ("tofu", "mofu", "bofu")
METRICS = ("hook_rate", "hold_rate", "ctr_link", "cvr")


def _sum(rows, k):
    return sum(float(r.get(k) or 0) for r in rows)


def _jobj(v) -> dict:
    if isinstance(v, str):
        import json
        try:
            return json.loads(v) or {}
        except ValueError:
            return {}
    return v or {}


def scale_layer_of(snap: dict) -> dict | None:
    return _jobj(snap["cycle"].get("budget_plan_json")).get("scale_layer")


def scale_split(snap: dict) -> tuple[list[dict], list[dict]]:
    """Ölçekleme setinin satırları test hesabından ayrılır (coach 6a): (test yapısındaki satırlar, ölçekleme satırları)."""
    layer = scale_layer_of(snap)
    sid = str(layer.get("adset_id")) if layer and layer.get("adset_id") else None
    if not sid:
        return list(snap["rows"]), []
    main, scale = [], []
    for r in snap["rows"]:
        (scale if str(r.get("adset_id") or "") == sid else main).append(r)
    return main, scale


def split_rows(snap: dict, rows: list[dict] | None = None) -> dict:
    w = snap.get("test_window") or {}
    full = set(w.get("full_days") or [])
    excl = set(w.get("excluded_boundary_days") or [])
    test, post, pre, boundary = [], [], [], []
    test_end_day = max(full) if full else None
    for r in (snap["rows"] if rows is None else rows):
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


def stage_of_concept(snap: dict) -> dict:
    """Konsept kodu → huni aşaması (1.9.0; mesaj kartından sözlüğe yazılan `stage`). Aşaması olmayan konsept yer almaz."""
    out = {}
    for c in snap.get("creatives", []):
        st = _jobj(c.get("concept_features")).get("stage")
        if c.get("concept") and st in STAGE_METRICS:
            out[c["concept"]] = st
    return out


def round_mode_of(snap: dict) -> str:
    return _jobj(snap["cycle"].get("budget_plan_json")).get("round_mode") or "explore"


def _ratio(num, den):
    return round(num / den, 4) if den else None


def stage_section(snap: dict, by_concept: dict) -> dict | None:
    """Huni aşaması teşhisi (1.9.0). Her konsept KENDİ aşamasının metriğiyle okunur; hüküm yine sonuç türüyle verilir. Piksel bir olayı
    göndermiyorsa o metrik okunamadı yazılır (sıfır sayılmaz). Kitle segmenti dökümü (yeni / etkileşime geçmiş / mevcut müşteri) yalnızca
    girdi olarak verildiyse kullanılır; aşama bir kitle değildir, reklamı kimin gördüğü bu dökümle okunur."""
    stages = stage_of_concept(snap)
    if not stages:
        return None
    seg_in = ((snap.get("extra") or {}).get("audience_segments") or {})
    per = []
    for k in sorted(stages):
        rows = by_concept.get(k, [])
        st = stages[k]

        def tot(col):
            vals = [r.get(col) for r in rows if r.get(col) is not None]
            return sum(float(v) for v in vals) if vals else None
        imp, v3, thru, clicks = tot("impressions"), tot("video_3s"), tot("thruplay"), tot("link_clicks")
        lpv, vc, atc, ic, pur, spend = (tot(c) for c in ("landing_page_views", "view_content", "add_to_cart", "initiate_checkout",
                                                          "purchases", "spend"))
        m = {"tofu": {"hook_rate": _ratio(v3 or 0, imp), "hold_rate": _ratio(thru or 0, v3) if v3 else None,
                      "spend_per_3s_view": round(spend / v3, 4) if (spend and v3) else None},
             "mofu": {"ctr_link": _ratio(clicks or 0, imp), "landing_page_view_rate": _ratio(lpv, clicks) if lpv is not None else None,
                      "view_content_rate": _ratio(vc, clicks) if vc is not None else None},
             "bofu": {"add_to_cart_rate": _ratio(atc, clicks) if atc is not None else None,
                      "checkout_rate": _ratio(ic, clicks) if ic is not None else None,
                      "cost_per_purchase": round(spend / pur, 2) if (spend and pur) else None}}[st]
        unread = [n for n, v in m.items() if v is None]
        seg = None
        raw = seg_in.get(k)
        if isinstance(raw, dict):
            total = sum(float(raw.get(x) or 0) for x in ("new", "engaged", "existing"))
            if total > 0:
                seg = {x: round(float(raw.get(x) or 0) / total, 4) for x in ("new", "engaged", "existing")}
        note = None
        if seg and st == "bofu" and seg["new"] >= 0.5:
            note = "BOFU mesajının harcamasının çoğu yeni kitleye gitti: mesaj tereddüdü olan kişiye değil, yeni kişiye gösterildi"
        per.append({"concept": k, "stage": st, "metrics": m, "unread": unread, "segments": seg, "segment_note": note,
                    "denominators": {"impressions": imp, "video_3s": v3, "link_clicks": clicks}})
    return {"round_mode": round_mode_of(snap), "per_concept": per,
            "segments_read": bool(seg_in),
            "rule": ("Aşama metriği teşhistir, hüküm değildir; hüküm sonuç türüyle verilir. Farklı aşamaların sonuç maliyeti karşılaştırması "
                     "keşiftir (kısa pencere satın almaya yakın mesajı kayırabilir; beklenti, doğrulanmış bulgu değil). Huni oranları çarpılmaz.")}


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


def scale_section(snap: dict, scale_rows: list[dict]) -> dict | None:
    """Ölçekleme katmanı raporu: test verisi değildir; yalnızca harcama, sıklık, sonuç ve yorgunluk (hüküm 'Meta'nın dağıtımı altında')."""
    layer = scale_layer_of(snap)
    if not layer:
        return None
    by_ck = aggregate(scale_rows, lambda r: r.get("creative_key") or r["meta_ad_id"])
    members = []
    for m in layer.get("members") or []:
        rows = sorted(by_ck.get(m["creative_key"], []), key=lambda r: r["date"])
        last7 = rows[-7:]
        sp, res = _sum(rows, "spend"), _sum(rows, "results")
        members.append({"creative_key": m["creative_key"], "meta_ad_id": m["meta_ad_id"], "post_id": m.get("post_id"),
                        "days": len(rows), "spend": round(sp, 2), "impressions": int(_sum(rows, "impressions")), "results": res,
                        "cost_per_result": round(sp / res, 2) if res else None,
                        "frequency_last7": round(statistics.mean([float(r.get("frequency") or 0) for r in last7]), 2) if last7 else None})
    fat = fatigue({f"{k} @ölçekleme": v for k, v in by_ck.items()})
    return {"campaign_meta_id": layer.get("campaign_meta_id"), "adset_id": layer.get("adset_id"), "status": layer.get("status", "active"),
            "daily_budget": layer.get("daily_budget"), "min_daily": layer.get("min_daily"), "learning_warning": layer.get("learning_warning"),
            "spend": round(_sum(scale_rows, "spend"), 2), "members": members, "fatigue": fat,
            "label": "Meta'nın dağıtımı altında · ölçekleme katmanı (test verisi değil)",
            "rule": "Ölçekleme verisi test hükmüne, önsele ya da playbook kanıtına girmez (coach 6a)."}


def _days_left(snap: dict) -> int:
    cyc = snap["cycle"]
    start = (cyc.get("launched_at") or cyc.get("launch_at") or "")[:10]
    cut = (snap.get("data_cutoff") or "")[:10]
    try:
        end = dt.date.fromisoformat(start) + dt.timedelta(days=int(cyc.get("cycle_days") or 0))
        ref = dt.date.fromisoformat(cut) if cut else dt.date.fromisoformat(start)
        return max(0, (end - ref).days)
    except ValueError:
        return int(cyc.get("cycle_days") or 7)


def scale_candidates(dec: list[dict], snap: dict, structure: str | None, test_rows: list[dict], all_rows: list[dict]) -> list[dict]:
    """"Büyüt" hükmü alan her konsept için ölçekleme katmanına taşıma uygunluğu (coach 6a). Gönderi kimliği burada yoktur:
    skill salt okumayla okur; kimlik yoksa madde yazılmaz."""
    from admem.s_lead import target_for
    target, exact = target_for(snap["campaign"].get("result_type"), snap.get("economics"))
    layer = scale_layer_of(snap)
    active = bool(layer and layer.get("status", "active") == "active")
    cmap = concept_of(snap)
    out = []
    for d in dec:
        if d["decision"] != "büyüt":
            continue
        ads = sorted({(r.get("creative_key"), r["meta_ad_id"]) for r in test_rows if cmap.get(r.get("creative_key")) == d["concept"]})
        chk = BU.scale_check(structure=structure, cost_ok=True, target_cpa=target, economics_exact=exact,
                             proposed_daily=float(layer["daily_budget"]) if active else None,
                             budget_total=snap["campaign"].get("budget_total"), spend_to_date=_sum(all_rows, "spend"),
                             other_daily=float(snap["cycle"].get("adset_budget_daily") or 0), days_left=_days_left(snap))
        out.append({"concept": d["concept"], "layer_exists": active, "source_ads": [{"creative_key": k, "meta_ad_id": a} for k, a in ads],
                    **chk, "action": ("mevcut ölçekleme setine mevcut gönderiyle ekle" if active else "ölçekleme kampanyası aç ve mevcut gönderiyle ekle")
                    if chk["eligible"] else "ana reklam setinde kalır; günlük bütçe en fazla %20 artırılır"})
    return out


# Huni teşhisi eşikleri (1.4.7; YEREL sezgisel değerler, Meta kuralı değil): konseptler arası ortancanın %80'i altı "zayıf" sayılır;
# reklam sonrası (sayfa/teklif) şüphesi için kampanyada en az 100 bağlantı tıklaması ve sıfır görünür satış.
WEAK_VS_MEDIAN = 0.8
PAGE_MIN_CLICKS = 100


def _overlaps(row: dict, days: list[str]) -> bool:
    if not days:
        return True
    return not (row.get("period_end", "") < days[0] or row.get("period_start", "") > days[-1])


STORE_CHANNELS = ("site", "shopier", "pazaryeri", "magaza")
PIXEL_CHANNELS = ("site", "shopier")  # Meta pikselinin görebildiği satış yerleri (pazaryeri ve fiziksel mağaza görünmez)
DM_TO_SALES = {"instagram_dm": "instagram_dm", "messenger": "messenger", "whatsapp": "whatsapp", "phone": "telefon",
               "web_chat": "diger", "email": "diger", "other": "diger"}


def _in_days(day, days: list) -> bool:
    return bool(day) and (not days or days[0] <= day <= days[-1])


def channel_summary(snap: dict, days: list) -> dict:
    """Satış ve talepler kanala göre, tek defter (1.4.7, 1.4.8). Öncelik (çift sayım yok): mağaza kanallarında içe aktarılan siparişler
    elle girişten önce gelir; mesaj kanallarında DM modülündeki satışlar (mağaza bağlantısıyla ödenmeyenler) elle girişten önce gelir.
    Öncelikli kaynağı olan kanalda çakışan elle girişler sayılmaz ve not edilir."""
    sales = defaultdict(lambda: {"units": 0, "revenue": 0.0, "source": set()})
    leads = defaultdict(int)
    excluded = []
    imported = defaultdict(lambda: {"orders": 0, "units": 0, "units_unknown": 0, "revenue": 0.0})
    by_day = defaultdict(lambda: {"units": 0, "revenue": 0.0})  # (kanal, gün) → öncelikli kaynaklardaki satış (elle girişle kıyas)
    for o in snap.get("sales_orders") or []:
        if o["status"] == "paid":
            d = by_day[(o["channel"], o.get("date"))]
            d["units"] += int(o["units"] or 0) + int(o.get("units_unknown") or 0)
            d["revenue"] += float(o["amount"] or 0)
        if not _in_days(o.get("date"), days):
            continue
        if o["status"] == "paid":
            b = imported[o["channel"]]
            b["orders"] += int(o["orders"] or 0)
            b["units"] += int(o["units"] or 0)
            b["units_unknown"] += int(o.get("units_unknown") or 0)
            b["revenue"] += float(o["amount"] or 0)
    for ch, b in imported.items():
        s = sales[ch]
        s["units"] += b["units"] + b["units_unknown"]  # adedi bilinmeyen sipariş en az 1 adet sayılır
        s["revenue"] += b["revenue"]
        s["source"].add("içe aktarma")
    dm = (snap.get("dm") or {}).get("threads") or []
    dm_won = defaultdict(lambda: {"units": 0, "revenue": 0.0})
    for t in dm:
        if t["status"] != "won" or t.get("paid_via") == "store_link":
            continue
        day = t.get("closed_date") or (t.get("closed_at") or "")[:10]  # markanın günü (koçluk kopyası verir)
        ch = DM_TO_SALES.get(t["channel"], "diger")
        d = by_day[(ch, day)]
        d["units"] += int(t.get("quantity") or 1)
        d["revenue"] += float(t.get("won_amount") or 0)
        if _in_days(day, days):
            dm_won[ch]["units"] += int(t.get("quantity") or 1)
            dm_won[ch]["revenue"] += float(t.get("won_amount") or 0)
    for ch, b in dm_won.items():
        sales[ch]["units"] += b["units"]
        sales[ch]["revenue"] += b["revenue"]
        sales[ch]["source"].add("DM modülü")
    for r in snap.get("sales_manual") or []:
        if not _overlaps(r, days):
            continue
        ch = r.get("channel") or "belirtilmedi"
        if (r.get("kind") or "sale") == "lead":
            leads[ch] += int(r.get("units") or 1)
            continue
        # Mağaza kanalında dışa aktarım elle girişin dönemini tamamen kapsıyorsa dosya esastır (elle giriş sayılmaz). Kapsamıyorsa ve
        # mesaj kanallarında (DM kaydı eksik tutulabilir) ikisinden büyüğü sayılır: kaynakta olan satış iki kez sayılmaz, kaynağa girmemiş
        # satış kaybolmaz; çakışma rapora yazılır.
        ps, pe = r.get("period_start"), r.get("period_end") or r.get("period_start")
        src_u = sum(v["units"] for (c, d), v in by_day.items() if c == ch and d and ps <= d <= pe)
        src_r = sum(v["revenue"] for (c, d), v in by_day.items() if c == ch and d and ps <= d <= pe)
        mu, mr = int(r.get("units") or 0), float(r.get("revenue") or 0)
        full = any(im.get("channel") == ch and im["from"] <= ps and pe <= im["to"] for im in snap.get("sales_imports") or [])
        add_u, add_r = (0, 0.0) if full else (max(0, mu - src_u), max(0.0, mr - src_r))
        if full or src_u or src_r:
            why = ("mağaza dışa aktarımı bu dönemi kapsıyor; dosya esas alındı, elle giriş sayılmadı" if full else
                   "aynı kanal ve dönem içe aktarılan siparişlerde ya da DM modülünde var; çift sayılmadı" if not (add_u or add_r) else
                   "kaynakta olandan fazlası eklendi (ikisinden büyüğü); kaynak dönemi tam kapsamıyor, kullanıcıyla kontrol edin")
            excluded.append({"channel": ch, "period": [ps, pe], "units": mu, "source_units": src_u, "added_units": add_u, "why": why})
        if add_u or add_r:
            sales[ch]["units"] += add_u
            sales[ch]["revenue"] += add_r
            sales[ch]["source"].add("elle")
    return {"sales": {k: {"units": v["units"], "revenue": round(v["revenue"], 2), "source": sorted(v["source"])}
                      for k, v in sorted(sales.items())},
            "leads": dict(sorted(leads.items())),
            "imported": {k: {**v, "revenue": round(v["revenue"], 2)} for k, v in imported.items()},
            "excluded_manual": excluded,
            "note": "Tek satış defteri: reklamın yarattığı satış sayılmaz, kreatiflere dağıtılmaz. DM/WhatsApp/kurumsal Meta'da görünmez; "
                    "mağaza bağlantısıyla ödenen DM satışı mağaza siparişindedir. Kurumsal fırsat yalnızca site satışına bakılarak "
                    "başarısız sayılmaz."}


def ab_section(snap: dict, kpost: dict, structure: str | None) -> dict | None:
    """Meta A/B testi (1.5.0): Meta kitleyi hücrelere rastgele böler; hücre = konsept. Sonuç oranı (sonuç/harcama) için zayıf
    Gamma önseliyle her hücrenin en düşük sonuç maliyetine sahip olma olasılığı; Meta'nın okunan sonucu (snapshot extra.ab_test,
    ads_experiment_abtest_get_test) ayrıca yazılır ve uyuşup uyuşmadığı belirtilir. Hüküm dilinde 'Meta'nın dağıtımı altında' yoktur."""
    if structure != "ab_test":
        return None
    import numpy as np
    ev = (snap.get("cycle") or {}).get("structure_evidence_json") or {}
    if isinstance(ev, str):
        try:
            ev = json.loads(ev)
        except ValueError:
            ev = {}
    study_cells = set(((ev or {}).get("study_read") or {}).get("cells") or [])
    cells = {k: v["totals"] for k, v in kpost.items() if v["totals"].get("spend") and k != "(konseptsiz)"
             and (not study_cells or k in study_cells)}
    out = {"cells": {}, "meta_read": (snap.get("extra") or {}).get("ab_test"),
           "rule": "Hücre başına ≥ 30 sonuç yerel eşiktir; altında yön olarak okunur."}
    if len(cells) < 2:
        out["note"] = "iki hücreden az harcama verisi: karşılaştırma yok"
        return out
    total_spend = sum(c["spend"] for c in cells.values())
    total_res = sum(c["results"] or 0 for c in cells.values())
    unit = (total_spend / total_res) if total_res else (total_spend / max(1, len(cells)))
    rng = np.random.default_rng(1729)
    draws = {k: rng.gamma(0.5 + float(c["results"] or 0), 1.0 / (0.5 + c["spend"] / unit), size=20000) for k, c in cells.items()}
    stack = np.vstack(list(draws.values()))
    best = np.argmax(stack, axis=0)  # en yüksek sonuç oranı = en düşük sonuç maliyeti
    for i, (k, c) in enumerate(cells.items()):
        res = float(c["results"] or 0)
        out["cells"][k] = {"spend": round(c["spend"], 2), "results": int(res), "cost_per_result": round(c["spend"] / res, 2) if res else None,
                           "p_lowest_cost": round(float(np.mean(best == i)), 4), "threshold_met": res >= 30}
    if not total_res:
        out["note"] = "hiçbir hücrede sonuç yok: önde olan hücre söylenmez"
        return out
    lead = max(out["cells"], key=lambda k: out["cells"][k]["p_lowest_cost"])
    out["leader"] = lead
    mr = out["meta_read"] or {}
    winner = mr.get("winner_concept")
    if winner:
        out["agrees_with_meta"] = winner == lead
        if winner != lead:
            out["disagreement_note"] = ("Meta'nın kazananı ile bu hesabın önde gördüğü hücre farklı: Meta kendi güven ölçüsünü kullanır; karar "
                                        "Meta'nın sonucu ve hücre başına sonuç sayısı birlikte okunarak verilir.")
    return out


LEAD_COVERAGE_MIN = 0.8  # yerel: büyütme kapısı için aday sonrası kaydın test penceresini kapsama oranı


def lead_section(snap: dict, test_rows: list[dict], days: list | None = None) -> dict | None:
    """Müşteri adayı kampanyası (1.5.0): aday maliyeti Meta'dan (sonuç), aday sonrası huni kullanıcı kaydından. Ucuz aday iyi aday
    değildir: nitelikli aday ve satış başına maliyet, gözlenen dönüş oranı ile varsayılan oran kıyaslanır."""
    if snap["campaign"].get("result_type") != "lead":
        return None
    from admem.s_lead import lead_funnel
    spend, results = _sum(test_rows, "spend"), _sum(test_rows, "results")
    allr = snap.get("lead_outcomes") or []
    if days:  # yalnızca test penceresinin İÇİNDEKİ dönemler (harcama da pencereden): taşan dönem maliyeti küçük gösterirdi
        rows = [r for r in allr if days[0] <= r["period_start"] and r["period_end"] <= days[-1]]
        partial = [r for r in allr if _overlaps(r, days) and r not in rows]
    else:
        rows, partial = list(allr), []
    # kayıtların kapsadığı günler: aday sonrası maliyetler ve Meta ↔ kayıt kıyası yalnızca bu günlerin harcaması/adayıyla
    covered = set()
    for r in rows:
        d0, d1 = dt.date.fromisoformat(r["period_start"]), dt.date.fromisoformat(r["period_end"])
        covered |= {(d0 + dt.timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)}
    cov_rows = [x for x in test_rows if x.get("date") in covered]
    cov_spend, cov_leads = _sum(cov_rows, "spend"), _sum(cov_rows, "results")
    window = len(days) if days else len(covered)
    coverage = round(len(covered & set(days or covered)) / window, 3) if window else 0.0
    out = {"method": snap["campaign"].get("lead_method"), "spend": round(spend, 2), "meta_leads": int(results),
           "cost_per_lead": round(spend / results, 2) if results else None, "outcome_coverage": coverage,
           "covered_spend": round(cov_spend, 2), **lead_funnel(rows, cov_leads if rows else None)}
    t = out["totals"]
    for k, label in (("qualified", "cost_per_qualified"), ("won", "cost_per_won")):
        if t.get(k):
            out[label] = round(cov_spend / t[k], 2) if cov_spend else None
    if rows and coverage < LEAD_COVERAGE_MIN:
        out["coverage_note"] = (f"Aday sonrası kayıt test penceresinin %{coverage * 100:.0f}'ini kapsıyor (< %{LEAD_COVERAGE_MIN * 100:.0f}): "
                                "maliyetler yalnızca kapsanan günlerden; büyütme için pencerenin tamamı girilmeli.")
    if t.get("leads", 0) >= 3 and t.get("won") is not None:
        p = B.rate_posterior("ctr_link", t["won"], t["leads"], (1.0, 1.0), None)
        if p:
            out["close_rate_interval"] = {"mean": round(p.mean, 4), "lo": p.lo, "hi": p.hi,
                                          "note": "Beta(1,1) önseliyle %90 aralık; adaylar bağımsız varsayılır"}
    eco = snap.get("economics") or {}
    assumed = eco.get("lead_close_rate")
    if assumed is not None and out.get("close_rate_interval"):
        iv = out["close_rate_interval"]
        if not iv["lo"] <= float(assumed) <= iv["hi"]:
            out["close_rate_check"] = (f"varsayılan dönüş oranı {float(assumed):.0%}, gözlenen %90 aralık {iv['lo']:.0%}–{iv['hi']:.0%}: hedef aday "
                                       "maliyeti yeniden hesaplanmalı (ürün ekonomisinde lead_close_rate)")
    if partial:
        out["partial_periods"] = [[r["period_start"], r["period_end"]] for r in partial]
        out["partial_note"] = ("Test penceresini aşan aday sonrası dönemler maliyet hesabına katılmadı (harcama yalnızca penceredendir): "
                               "kayıtları haftalık ve test haftasıyla aynı günlere girin.")
    if not rows:
        out["note"] = ("Test penceresinde aday sonrası kayıt yok: ucuz aday satış demek değildir; büyütme önerilmez. Haftalık olarak "
                       "adayların kaçına ulaşıldığı, kaçının nitelikli olduğu ve kaçının satışa döndüğü lead_outcome_set ile girilmeli.")
    return out


def dm_section(snap: dict, days: list) -> dict | None:
    """Mesajla satış hunisi test penceresinde (1.4.8). Toplamlar markanın; kampanya bağı yalnızca kanıtlı konuşmalarda."""
    dm = snap.get("dm") or {}
    threads = [t for t in dm.get("threads") or [] if _in_days(t.get("opened_date") or t["opened_at"][:10], days)]
    daily = [d for d in dm.get("daily") or [] if _in_days(d["date"], days)]
    if not threads and not daily:
        return None
    from admem.s_dm import dm_funnel
    out = dm_funnel(threads, daily, snap["campaign"]["id"])
    tot = out["totals"]
    if tot["conversations"] >= 3:
        p = B.rate_posterior("ctr_link", tot["won"], tot["conversations"], (1.0, 1.0), None)
        if p:
            out["won_rate_interval"] = {"mean": round(p.mean, 4), "lo": p.lo, "hi": p.hi,
                                        "note": "Beta(1,1) önseliyle %90 aralık; konuşmalar bağımsız varsayılır"}
    return out


def store_vs_meta(snap: dict, test_rows: list, chan: dict) -> dict | None:
    """Meta'nın reklama atfettiği satın alma ile mağazanın ödenmiş siparişleri (1.4.8). Mağaza toplamı organik ve diğer kaynakları da
    içerir; Meta sayısının mağazadan belirgin fazla olması piksel/olay sorununa işarettir, az olması tek başına sorun değildir."""
    imported = chan.get("imported") or {}
    store_orders = sum(v["orders"] for ch, v in imported.items() if ch in PIXEL_CHANNELS)  # pazaryeri/mağaza pikselde görünmez
    if not store_orders:
        return None
    meta = _sum(test_rows, "purchases")
    if meta > store_orders * 1.1 and meta - store_orders >= 3:
        verdict = "meta_fazla"
        msg = (f"Meta {int(meta)} satın alma sayıyor, mağazada {store_orders} ödenmiş sipariş var: çift olay, test siparişi ya da iade "
               "edilen siparişler olabilir; piksel kurulumu kontrol edilmeli.")
    elif meta == 0:
        verdict = "meta_gormuyor"
        msg = (f"Mağazada {store_orders} ödenmiş sipariş var, Meta reklama hiç satın alma atfetmiyor: piksel/olay kurulumu eksik olabilir ya "
               "da satışlar reklamdan gelmiyor (Meta satış sinyali: S00b 6b).")
    else:
        verdict = "uyumlu"
        msg = (f"Meta {int(meta)} / mağaza {store_orders}: Meta'nın atfettiği, mağaza toplamının içinde (mağaza toplamı reklam dışı "
               "satışları da içerir).")
    return {"verdict": verdict, "meta_purchases": int(meta), "store_paid_orders": store_orders, "msg": msg}

def funnel_diagnosis(kpost: dict, test_rows: list[dict], chan: dict) -> dict:
    """"Reklam mı zayıftı, teklif mi, sayfa mı?" (1.4.7). Konseptler arası göreli karşılaştırma + kampanya düzeyinde tıklama→satış.
    Çıktı hipotezdir, kesin neden değildir; eşik altı veri değerlendirilmez."""
    def mean(k, m):
        r = kpost[k]["rates"].get(m)
        return r["mean"] if r and r.get("threshold_met") else None
    hooks = {k: mean(k, "hook_rate") for k in kpost}
    ctrs = {k: mean(k, "ctr_link") for k in kpost}
    hm = statistics.median([v for v in hooks.values() if v is not None]) if any(v is not None for v in hooks.values()) else None
    cm = statistics.median([v for v in ctrs.values() if v is not None]) if any(v is not None for v in ctrs.values()) else None
    per = []
    for k in sorted(kpost):
        notes = []
        if hooks[k] is None:
            notes.append("açılış için veri yetersiz (< 1.000 gösterim)")
        elif hm and len([v for v in hooks.values() if v is not None]) >= 2 and hooks[k] < hm * WEAK_VS_MEDIAN:
            notes.append("açılış (ilk 2 sn) diğer konseptlerden zayıf → reklam: hook")
        if ctrs[k] is None:
            notes.append("tıklama için veri yetersiz (< 3.000 gösterim)")
        elif cm and len([v for v in ctrs.values() if v is not None]) >= 2 and ctrs[k] < cm * WEAK_VS_MEDIAN:
            notes.append("tıklama oranı diğer konseptlerden düşük → teklif, fiyat gösterimi, son kart/CTA")
        per.append({"concept": k, "notes": notes or ["açılış ve tıklama diğer konseptlerle benzer ya da daha iyi"]})
    clicks = _sum(test_rows, "link_clicks")
    pixel_purchases = _sum(test_rows, "purchases")
    web_units = sum(v["units"] for ch, v in chan["sales"].items() if ch in PIXEL_CHANNELS + ("belirtilmedi",))
    # Mağaza kaydı varsa o esastır (piksel aynı satışları sayar; toplanırsa çift sayılır); yoksa pikselin saydığı.
    sales_seen = web_units if web_units else pixel_purchases
    if clicks >= PAGE_MIN_CLICKS and sales_seen == 0:
        after = {"verdict": "reklam_sonrasi_supheli",
                 "msg": f"{int(clicks)} bağlantı tıklaması var, görünür web satışı yok: sorun reklamdan sonra olabilir (satış sayfası, fiyat, "
                        "kargo, güven, teklif). Bu tur 'video kötüydü' diye öğrenilmez; önce sayfa ve teklif kontrol edilir."}
    elif clicks >= PAGE_MIN_CLICKS:
        after = {"verdict": "olculdu", "cvr": round(sales_seen / clicks, 4),
                 "msg": f"Tıklamadan satışa oran ≈ {sales_seen / clicks:.2%} ({int(sales_seen)} satış / {int(clicks)} tıklama; elle girilen dönem "
                        "satışı dahil, atıf varsayımlı)."}
    else:
        after = {"verdict": "veri_yetersiz", "msg": f"Sayfa/teklif yargısı için tıklama az ({int(clicks)} < {PAGE_MIN_CLICKS})."}
    return {"per_concept": per, "after_click": after, "leads": chan["leads"],
            "rule": "Göreli eşikler yereldir (ortancanın %80'i; ≥ 100 tıklama). Teşhis hipotezdir; kesin neden değildir."}


def metric_basis(snap: dict, cost: dict, test_rows: list[dict]) -> dict:
    """Hangi metrikle karar verildiği (1.4.7): olasılıklar ve kararlar raporda metrik adıyla yazılır."""
    purchases = _sum(test_rows, "purchases")
    cost_ok = [k for k, v in cost.items() if v.get("threshold_met")]
    if snap["campaign"].get("result_type") == "lead":  # aday kampanyası: sonuç adaydır, satış aday sonrası kayıttan (1.5.0)
        leads = _sum(test_rows, "results")
        return {"superiority": "hook oranı (3 sn izlenme / gösterim): konseptin TÜM konseptlerin en iyisi olma olasılığı; aday değil, dikkat ölçüsü",
                "decision": ("aday maliyeti (≥ 10 aday olan konseptlerde: " + ", ".join(sorted(cost_ok)) + ")") if cost_ok
                            else "üst huni (hook ve bağlantı CTR'si): aday maliyeti için yeterli aday yok",
                "meta_sees_sales": purchases > 0, "meta_leads": int(leads),
                "note": (f"Meta bu turda {int(leads)} aday saydı; satış aday sonrası kayıttan okunur (lead_outcomes)." if leads else
                         "Meta bu turda aday saymadı: aday maliyetine dayalı hüküm verilmez.")}
    return {"superiority": "hook oranı (3 sn izlenme / gösterim): konseptin TÜM konseptlerin en iyisi olma olasılığı; satış değil, dikkat ölçüsü",
            "decision": ("sonuç maliyeti (≥ 10 sonuç olan konseptlerde: " + ", ".join(sorted(cost_ok)) + ")") if cost_ok
                        else "üst huni (hook ve bağlantı CTR'si): sonuç maliyeti için yeterli sonuç yok",
            "meta_sees_sales": purchases > 0,
            "note": ("Meta bu turda satış olayı gördü." if purchases > 0 else
                     "Meta bu turda satış olayı görmedi (piksel/yükleme yok ya da satış yok): satışa dayalı hüküm verilmez.")}


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
            out.append({"concept": k, "decision": "tut", "label": "yetersiz veri", "carry_over": True,
                        "why": "Meta bu konsepte harcama payının %10'undan azını verdi; kaybeden sayılmaz. Sonraki turun kreatif testine "
                               "öncelikli aday: hazır kreatifi yeni tur adıyla yeniden dışa aktarılır, yeniden çekim/render gerekmez"})
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


def funnel_stage_guard(dec: list[dict], smap: dict, kpost: dict, priors: dict) -> None:
    """Huni turu (1.9.0): TOFU/MOFU mesajı yalnızca satış maliyetiyle kapatılmaz. Kendi aşama metriği de zayıfsa (aralığın üst ucu
    geçmiş ortalamanın altında) "kapat" korunur; değilse "tut" olur."""
    own = {"tofu": "hook_rate", "mofu": "ctr_link"}
    for d in dec:
        st = smap.get(d["concept"])
        if d["decision"] != "kapat" or st not in own:
            continue
        m = own[st]
        r = (kpost.get(d["concept"], {}).get("rates") or {}).get(m)
        pr = priors.get(m)
        if r and r.get("threshold_met") and pr and r["hi"] < pr[0] / (pr[0] + pr[1]):
            d["why"] += f"; {st.upper()} aşama metriği ({m}) de geçmiş ortalamanın altında (aralık üst ucu {r['hi']:.4f})"
            continue
        d.update(decision="tut", label="huni turu", ads_manager=None, gated="funnel_stage",
                 why=d["why"] + f"; ancak bu {st.upper()} mesajı satın almadan önceki bir karar anına seslenir: yalnızca satış "
                                f"maliyetiyle kapatılmaz; kendi aşama metriği ({m}) zayıf değil ya da geçmiş ortalama yok")


def analyze(snap_path: str) -> dict:
    snap = read_json(snap_path)
    main_rows, scale_rows = scale_split(snap)
    parts = split_rows(snap, main_rows)
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
    from admem.s_lead import target_for
    target, verified = target_for(snap["campaign"].get("result_type"), snap.get("economics"))
    cost = {k: B.cost_posterior(v["totals"]["spend"], v["totals"]["results"], target, verified) for k, v in kpost.items()}
    dist = spend_distribution(by_concept)
    all_rows = snap["rows"]
    rows_main_by_creative = aggregate(main_rows, lambda r: r.get("creative_key") or r["meta_ad_id"])
    fat = fatigue(rows_main_by_creative)
    ret = retention(snap, aggregate(test_rows, lambda r: r.get("creative_key") or r["meta_ad_id"]))
    lim = limit_alerts(snap, all_rows)
    dec = decisions(kpost, dist, snap, structure, cost)
    stg = stage_section(snap, by_concept)
    if stg and stg["round_mode"] == "funnel":
        funnel_stage_guard(dec, stage_of_concept(snap), kpost, priors)
    leads = lead_section(snap, test_rows, parts["full_days"])
    if leads is not None and (not leads.get("periods") or leads.get("outcome_coverage", 0) < LEAD_COVERAGE_MIN):
        for d in dec:  # aday sonrası kayıt yoksa ya da pencerenin çoğunu kapsamıyorsa büyütme yok (ucuz aday ≠ satış)
            if d["decision"] == "büyüt":
                d.update(decision="tut", why=d["why"] + "; ancak aday sonrası kayıt yok ya da test penceresini kapsamıyor — nitelik ve "
                         "satış görülmeden büyütülmez", ads_manager=None, gated="lead_outcomes")
    if structure == "ab_test":  # A/B testinde yalnızca çalışmanın hücreleri hüküm alır
        ev = (snap.get("cycle") or {}).get("structure_evidence_json") or {}
        if isinstance(ev, str):
            try:
                ev = json.loads(ev)
            except ValueError:
                ev = {}
        cells = set(((ev or {}).get("study_read") or {}).get("cells") or [])
        for d in dec:
            if cells and d["concept"] not in cells:
                d.update(decision="tut", label="çalışma dışı", why="A/B çalışmasının hücresi değil: bu turda hüküm verilmez",
                         ads_manager=None)
    scale = scale_section(snap, scale_rows)
    if scale:
        fat += scale["fatigue"]
    scand = scale_candidates(dec, snap, structure, test_rows, all_rows)
    chan = channel_summary(snap, parts["full_days"])
    diag = funnel_diagnosis(kpost, test_rows, chan)
    dms = dm_section(snap, parts["full_days"])
    abt = ab_section(snap, kpost, structure)
    svm = store_vs_meta(snap, test_rows, chan)
    basis = metric_basis(snap, cost, test_rows)
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
            "scale_layer": scale, "scale_candidates": scand, "channels": chan, "funnel_diagnosis": diag, "stages": stg, "metric_basis": basis, "dm": dms, "store_vs_meta": svm, "lead": leads, "ab_test": abt,
            "competitive_context": competitive_context, "predictions": predictions,
            "portfolio_note": "Rol başına sonuç keşif karşılaştırmasıdır; önceden sabitlenmedikçe playbook adayı olmaz (6.16)."}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    res = analyze(a.snapshot)
    sha = write_json(a.out, res, overwrite=False)
    emit({"out": a.out, "sha256": sha, "decisions": res["decisions"], "limit_alerts": res["limit_alerts"], "data_quality": res["data_quality"],
          "scale_candidates": res["scale_candidates"]})


if __name__ == "__main__":
    main()
