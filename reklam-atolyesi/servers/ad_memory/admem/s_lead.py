"""Form ile müşteri adayı (lead) sonucu ve hizmet işletmesi (1.5.0).

- Aday kampanyası: result_type='lead' + lead_method: instant_form (Meta anlık form; piksel gerekmez) · website (sitedeki form; Meta'nın
  Lead olayını görmesi gerekir) · call (arama). Meta alanları (ads_get_field_context, 21.10.2026): `lead` (bağlı araçlar + Meta içi),
  `onsite_conversion_lead_grouped` (Meta içi formlar/sohbetler), `cost_per_lead`; amaç OUTCOME_LEADS; optimizasyon LEAD_GENERATION,
  QUALITY_LEAD (dönüşüm adayı), QUALITY_CALL.
- Aday sonrası huni dönem toplamıdır (kişisel veri yok): adaylar → ulaşılan → nitelikli → satış (+ gelir). Kaynak CRM dışa aktarımı,
  Meta potansiyel müşteri merkezi sayımı ya da elle. Aday kişisel verisi (ad, telefon, e-posta) bu sisteme girmez.
- Hizmet (products.kind='service'): süre, kapasite, bölge, randevu biçimi, düzenlenen sektör ve Meta özel reklam kategorisi service_json'da.
"""
from __future__ import annotations

from typing import Any

from .util import AdMemoryError, jdump, jload, now_iso

LEAD_METHODS = ("instant_form", "website", "call")
LEAD_SOURCES = ("crm_export", "meta_leads_center", "manual")
BOOKING = ("appointment", "walk_in", "online", "on_site", "mixed")
REGULATED = ("health", "legal", "financial", "education", "real_estate", "employment", "alcohol_tobacco", "gambling", "other", None)
SPECIAL_AD_CATEGORIES = ("housing", "employment", "financial_products_services", None)
# Meta özel reklam kategorisi zorunluluğu (resmi: facebook.com/business/help/399587795372584, okundu 21.10.2026): ABD'deki reklamveren
# ya da ABD, Kanada veya listelenen Avrupa bölgelerine gösterim. Türkiye listede yok. Liste kısaltılmadan saklanır (ISO-3166 alpha-2).
SAC_REGIONS = {"US", "CA", "AD", "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "GF", "DE", "GR", "GP", "HU", "IS", "IE",
               "IM", "IT", "LV", "LI", "LT", "LU", "MT", "MQ", "YT", "MC", "NL", "NO", "PL", "PT", "RE", "RO", "MF", "SM", "SK", "SI",
               "ES", "SE", "CH", "GB", "VA", "GG", "JE"}


def validate_service(sj: Any) -> dict:
    data = jload(sj, None) if isinstance(sj, str) else sj
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise AdMemoryError("service_json bir nesne olmalı")
    from .s_dm import pii_check
    for k in ("duration_min", "capacity_per_week"):
        v = data.get(k)
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0):
            raise AdMemoryError(f"service_json.{k} pozitif sayı olmalı")
    if data.get("booking") is not None and data["booking"] not in BOOKING:
        raise AdMemoryError(f"service_json.booking: {' | '.join(BOOKING)}")
    if data.get("regulated_sector") not in REGULATED:
        raise AdMemoryError(f"service_json.regulated_sector: {' | '.join(x for x in REGULATED if x)} ya da boş")
    if data.get("special_ad_category") not in SPECIAL_AD_CATEGORIES:
        raise AdMemoryError(f"service_json.special_ad_category: {' | '.join(x for x in SPECIAL_AD_CATEGORIES if x)} ya da boş")
    regions = data.get("audience_regions")
    if regions is not None:
        if not isinstance(regions, list) or not all(isinstance(r, str) and len(r) == 2 and r.isalpha() for r in regions):
            raise AdMemoryError("service_json.audience_regions: ülke kodları listesi (ör. ['TR'])")
        data["audience_regions"] = [r.upper() for r in regions]
    area = data.get("area")
    if area is not None:
        if not isinstance(area, dict):
            raise AdMemoryError("service_json.area: {city?, districts?, radius_km?, online?}")
        r = area.get("radius_km")
        if r is not None and (isinstance(r, bool) or not isinstance(r, (int, float)) or r <= 0):
            raise AdMemoryError("service_json.area.radius_km pozitif sayı olmalı")
    pii_check(data.get("note"), "hizmet notu")
    return data


def special_category_required(service: dict) -> dict:
    """Özel reklam kategorisi seçimi gerekiyor mu (yalnızca kayıtlı bilgiye göre; karar kullanıcının Ads Manager seçimidir)."""
    cat = service.get("special_ad_category")
    regions = set(service.get("audience_regions") or [])
    if not cat:
        return {"required": False, "category": None}
    hit = sorted(regions & SAC_REGIONS)
    return {"required": bool(hit), "category": cat, "regions": hit,
            "note": ("Ads Manager'da kampanya oluştururken özel reklam kategorisi seçilmeli; hedefleme kısıtlanır." if hit else
                     "Kitle bu kategorinin zorunlu olduğu bölgelerde değil (resmi liste); kitle değişirse yeniden bakılır."),
            "source": "https://www.facebook.com/business/help/399587795372584"}


def lead_funnel(rows: list[dict], meta_leads: float | None = None) -> dict:
    """Saf hesap (koçluk kopyasında da): dönem toplamlarından oranlar. meta_leads: Meta'nın aynı dönemde saydığı aday (sonuç).
    Gelir para birimine göre ayrı toplanır (farklı birimler toplanmaz)."""
    out = _lead_funnel(rows, meta_leads)
    by_cur: dict[str, float] = {}
    for r in rows:
        if r.get("revenue"):
            by_cur[r.get("currency") or "?"] = round(by_cur.get(r.get("currency") or "?", 0.0) + float(r["revenue"]), 2)
    out["revenue_by_currency"] = by_cur
    if len(by_cur) > 1:
        out["totals"]["revenue"] = None
    return out


def _lead_funnel(rows: list[dict], meta_leads: float | None = None) -> dict:
    """Saf hesap (koçluk kopyasında da): dönem toplamlarından oranlar. meta_leads: Meta'nın aynı dönemde saydığı aday (sonuç)."""
    tot = {"leads": 0, "reached": 0, "qualified": 0, "won": 0, "revenue": 0.0}
    known = {"reached": True, "qualified": True, "won": True}
    for r in rows:
        tot["leads"] += int(r["leads"] or 0)
        for k in ("reached", "qualified", "won"):
            if r.get(k) is None:
                known[k] = False
            else:
                tot[k] += int(r[k])
        tot["revenue"] += float(r.get("revenue") or 0)
    def rate(a, b):
        return round(a / b, 4) if b else None
    out = {"totals": {**{k: (v if k in ("leads", "revenue") or known[k] else None) for k, v in tot.items()}},
           "rates": {"reach_rate": rate(tot["reached"], tot["leads"]) if known["reached"] else None,
                     "qualify_rate": rate(tot["qualified"], tot["leads"]) if known["qualified"] else None,
                     "close_rate": rate(tot["won"], tot["leads"]) if known["won"] else None},
           "periods": len(rows)}
    if meta_leads is not None:
        out["meta_leads"] = int(meta_leads)
        if tot["leads"] and meta_leads:
            gap = tot["leads"] / meta_leads
            out["meta_vs_crm"] = round(gap, 3)
            if gap < 0.8:
                out["meta_vs_crm_note"] = ("Kayıttaki aday sayısı Meta'nın saydığından belirgin az: formlar indirilmemiş/aktarılmamış olabilir "
                                           "ya da Meta tekrarlı/geçersiz adayları da sayıyor; aday sonrası oranlar bu farkla okunur.")
            elif gap > 1.2:
                out["meta_vs_crm_note"] = ("Kayıttaki aday sayısı Meta'nın saydığından belirgin fazla: başka kaynaklardan (organik, tavsiye, "
                                           "farklı kampanya) gelen adaylar da sayılmış olabilir; reklamın payı bu farkla okunur.")
    return out


class LeadMixin:
    def lead_outcome_set(self, profile_id: int, campaign_id: int, period_start: str, period_end: str, leads: int,
                         reached: int | None = None, qualified: int | None = None, won: int | None = None, revenue: float | None = None,
                         currency: str | None = None, source: str = "manual", note: str | None = None) -> dict:
        """Aday sonrası dönem toplamı (aynı dönem yeniden yazılır). Her aşama bir öncekini aşamaz; kişisel veri reddedilir."""
        c = self._campaign(profile_id, campaign_id)
        if c["result_type"] != "lead":
            raise AdMemoryError("aday sonrası kayıt yalnızca müşteri adayı (lead) sonuçlu kampanyada tutulur; mesajla gelen talepler için "
                                "dm-sales, elle satış/talep için sales_add")
        from .s_dm import _pos_int, _pos_num, pii_check
        from .s_meta import _date
        from .s_conn import currency_code
        if source not in LEAD_SOURCES:
            raise AdMemoryError(f"source: {' | '.join(LEAD_SOURCES)}")
        pii_check(note, "not")
        ps, pe = _date(period_start), _date(period_end)
        if ps > pe:
            raise AdMemoryError("period_start, period_end'den sonra olamaz")
        n = _pos_int(leads, "leads")
        if n is None:
            raise AdMemoryError("leads (dönemde gelen aday sayısı) zorunlu")
        vals = {"reached": _pos_int(reached, "reached"), "qualified": _pos_int(qualified, "qualified"), "won": _pos_int(won, "won")}
        chain = [("leads", n), ("reached", vals["reached"]), ("qualified", vals["qualified"]), ("won", vals["won"])]
        last = None
        for k, v in chain:
            if v is None:
                continue
            if last is not None and v > last[1]:
                raise AdMemoryError(f"{k} ({v}) bir önceki aşamayı ({last[0]}: {last[1]}) aşamaz")
            last = (k, v)
        rev = _pos_num(revenue, "revenue")
        if rev and vals["won"] == 0:
            raise AdMemoryError("satış 0 iken gelir girilemez")
        cur = currency_code(currency)
        if rev is not None and not cur:
            raise AdMemoryError("gelir verildiyse para birimi (currency) gerekli")
        now = now_iso()
        with self.tx():
            ex = self.q1("SELECT id FROM lead_outcomes WHERE campaign_id=? AND period_start=? AND period_end=?", (c["id"], ps, pe))
            if ex:
                self.ex("""UPDATE lead_outcomes SET leads=?, reached=?, qualified=?, won=?, revenue=?, currency=?, source=?, note=?, updated_at=?
                           WHERE id=?""", (n, vals["reached"], vals["qualified"], vals["won"], rev, cur, source, note, now, ex["id"]))
            else:
                overlap = self.q1("""SELECT period_start, period_end FROM lead_outcomes WHERE campaign_id=? AND period_start<=? AND period_end>=?""",
                                  (c["id"], pe, ps))
                if overlap:
                    raise AdMemoryError(f"dönem başka bir kayıtla çakışıyor ({overlap['period_start']}–{overlap['period_end']}): aynı adaylar "
                                        "iki kez sayılmasın; o dönemi aynen yeniden yazın ya da çakışmayan dönem verin")
                self.ex("""INSERT INTO lead_outcomes(campaign_id,period_start,period_end,leads,reached,qualified,won,revenue,currency,source,
                           note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (c["id"], ps, pe, n, vals["reached"], vals["qualified"], vals["won"], rev, cur, source, note, now, now))
        return self.q1("SELECT * FROM lead_outcomes WHERE campaign_id=? AND period_start=? AND period_end=?", (c["id"], ps, pe))

    def lead_outcomes_summary(self, profile_id: int, campaign_id: int) -> dict:
        c = self._campaign(profile_id, campaign_id)
        rows = self.qa("SELECT * FROM lead_outcomes WHERE campaign_id=? ORDER BY period_start", (c["id"],))
        return {"campaign_id": c["id"], "rows": rows, **lead_funnel(rows)}

    def service_info(self, profile_id: int, product_id: int) -> dict:
        prod = self._product(profile_id, product_id)
        sj = jload(prod.get("service_json"), {}) if isinstance(prod.get("service_json"), (str, type(None))) else prod.get("service_json")
        return {"product_id": prod["id"], "kind": prod.get("kind") or "product", "service": sj or {},
                "special_ad_category": special_category_required(sj or {})}


def target_for(result_type: str | None, eco: dict | None) -> tuple[float | None, bool]:
    """Sonuç türüne göre hedef maliyet ve doğrulanmış mı: satış → hedef CPA, aday → hedef aday maliyeti; diğerleri hedefsiz."""
    eco = eco or {}
    if result_type == "purchase":
        return eco.get("target_cpa"), eco.get("status") == "exact"
    if result_type == "lead":
        return eco.get("target_cpl"), eco.get("cpl_status") == "exact"
    return None, False


def lead_economics(eco: dict, contrib: float | None, contrib_confirmed: bool, sf: float,
                   contrib_range: list | None = None) -> dict:
    """Başa baş aday maliyeti = satış başına katkı × adaydan satışa dönüş oranı (yerel tanım; 6.2'nin aday karşılığı)."""
    r = eco.get("lead_close_rate")
    if isinstance(r, bool):
        r = "x"  # True/False oran değildir
    if r is None:
        return {"cpl_status": "unknown", "cpl_note": "Adaydan satışa dönüş oranı bilinmiyor: başa baş aday maliyeti hesaplanmaz "
                                                      "(lead_outcome_set ile gözlenen oran birikince önerilir)"}
    try:
        r = float(r)
    except (TypeError, ValueError):
        return {"cpl_status": "unknown", "cpl_note": "lead_close_rate sayı değil"}
    if not 0 < r <= 1:
        return {"cpl_status": "unknown", "cpl_note": "lead_close_rate 0–1 arasında olmalı"}
    if (contrib is None or contrib <= 0) and contrib_range:
        lo, hi = float(contrib_range[0]), float(contrib_range[1])
        return {"cpl_status": "range", "lead_close_rate": r, "breakeven_cpl_range": [round(lo * r, 2), round(hi * r, 2)],
                "target_cpl_range": [round(lo * r * sf, 2), round(hi * r * sf, 2)],
                "cpl_note": "Katkı aralık: aday maliyeti de aralıktır; büyütme hükmü verilmez"}
    if contrib is None or contrib <= 0:
        return {"cpl_status": "unknown", "lead_close_rate": r, "cpl_note": "satış başına katkı bilinmiyor: aday maliyeti hesaplanmaz"}
    exact = contrib_confirmed and bool(eco.get("lead_close_rate_confirmed"))
    return {"cpl_status": "exact" if exact else "assumed", "lead_close_rate": r, "breakeven_cpl": round(contrib * r, 2),
            "target_cpl": round(contrib * r * sf, 2),
            **({} if exact else {"cpl_note": "Katkı ya da dönüş oranı teyitli değil: aday maliyeti VARSAYIMSAL; büyütme hükmü verilmez"})}
