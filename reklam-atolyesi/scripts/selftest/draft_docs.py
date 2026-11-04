"""Sentetik aşama belgeleri (2.5.0): duman testi, pytest ve senaryo matrisi için taslak denetiminden geçen nötr belgeler.

Belgeler veritabanındaki kayıtlardan (bütçe, sınır, sonuç türü, kreatifler) üretilir; böylece "belge = kayıt" kuralı (KURALLAR K10)
gerçek bir belgeyle sınanır. Gerçek kullanıcı belgesi değildir: dil ve ikna gücü burada sınanmaz (evals/ rubriği).
Kullanım (Python): write_stage_doc(store, profile_id, stage, campaign_id, cycle_id, scope_key=None) -> {"path", "check"}
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "servers" / "ad_memory"))

from admem import drafts as DR  # noqa: E402
from admem import stages as ST  # noqa: E402


def _n(v) -> str:
    if v is None:
        return "yok"
    v = float(v)
    if abs(v - round(v)) < 1e-9:
        i = int(round(v))
        return f"{i:,}".replace(",", ".")
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _cur(ctx: dict) -> str:
    return (ctx.get("product") or {}).get("currency") or "TRY"


RESULT_TR = {"purchase": "satış (purchase)", "lead": "müşteri adayı (lead)", "messaging": "mesaj (messaging)",
             "profile_visit": "profil ziyareti (profile_visit)", "link_click": "bağlantı tıklaması (link_click)",
             "engagement": "etkileşim (engagement)"}


def render_s01(ctx: dict) -> str:
    c = ctx.get("campaign") or {}
    eco = ctx.get("economics") or {}
    cur = _cur(ctx)
    rt = c.get("result_type")
    lines = [f"# Reklamın özeti — Örnek kampanya · tur {ctx.get('cycle_no', 1)}", "", "## Kampanya", "- Ürün: Ürün A (tanışma: tamam)",
             "- Kampanya amacı: satış", f"- Sonuç türü: {RESULT_TR.get(rt, rt or 'bilinmiyor')}"]
    if rt == "lead":
        lines.append(f"- Müşteri adayı yolu: {c.get('lead_method') or 'bilinmiyor'}")
    lines += [f"- Sezon / hedef tarih: {c.get('season') or 'yok'} / yok", f"- Kampanya modu: {'hızlı tur' if c.get('mode') == 'quick' else 'tam tur'}",
              f"- Reklam seti günlük bütçesi: {_n((ctx.get('cycle') or {}).get('adset_budget_daily'))} {cur}", "",
              "## Toplam Meta harcama sınırı (6.3)"]
    bt = c.get("budget_total")
    lines.append(f"- `budget_total`: {_n(bt)} {cur}" if bt is not None else "- `budget_total`: NULL — kullanıcı sınır tanımlamadı (açık karar)")
    lines += ["- Kullanıcı teyidi: «evet, bu»", "", "## Ekonomi (6.2)"]
    st = eco.get("status")
    if eco.get("breakeven_cpa") is not None:
        lines.append(f"- Başa baş CPA: {_n(eco['breakeven_cpa'])} · hedef CPA: {_n(eco.get('target_cpa'))} · durum: {st}")
    elif eco.get("breakeven_cpa_range"):
        lo, hi = eco["breakeven_cpa_range"]
        lines.append(f"- Başa baş CPA aralığı: {_n(lo)}–{_n(hi)} · durum: aralık")
    else:
        lines.append(f"- Başa baş CPA: bilinmiyor · durum: {st or 'unknown'}")
    if rt == "lead":
        cs = eco.get("cpl_status") or "unknown"
        if eco.get("breakeven_cpl") is not None:
            lines.append(f"- Başa baş aday maliyeti: {_n(eco['breakeven_cpl'])} · hedef: {_n(eco.get('target_cpl'))} · durum: {cs}")
        elif eco.get("breakeven_cpl_range"):
            lo, hi = eco["breakeven_cpl_range"]
            lines.append(f"- Başa baş aday maliyeti aralığı: {_n(lo)}–{_n(hi)} · durum: aralık")
        else:
            lines.append(f"- Başa baş aday maliyeti: bilinmiyor · durum: {cs}")
        if cs != "exact":
            lines.append("- Aday maliyeti VARSAYIM: dönüş oranı ya da katkı teyitli değil")
    if st != "exact":
        lines.append("- VARSAYIM: ekonomi doğrulanmadı" + (" (katkı ≤ 0: her satış zarar)" if st == "non_positive" else ""))
    if c.get("trial"):
        lines.append("- ekonomi VARSAYIMSAL (ürün tanışması atlandı)")
    lines += ["", "## Rakip bağlamı", "S01b sonrası doldurulur.", "", "## Varsayımlar ve açık sorular", "- Örnek varsayım."]
    return "\n".join(lines) + "\n"


def render_s01b(ctx: dict) -> str:
    snap = ctx.get("snapshot") or {}
    weak = " [zayıf kapsam]" if snap.get("weak") else ""
    return "\n".join([
        f"# Rakip analizi — Örnek kampanya · tur {ctx.get('cycle_no', 1)}", "",
        "> Bütün 'işe yarıyor' çıkarımları VEKİL sinyaldir (proxy); performans kanıtı değildir.", "",
        "## Özet", f"Pazarda 2 rakip, {snap.get('n_concepts', 0)} konsept gördüm.{weak}", "",
        "## Rakip seti", "| Rakip | Tür | Aktif reklam | Konsept | Uzun soluklu (≥ 30 gün) |", "|---|---|---|---|---|",
        "| Rakip A | direct | 3 | 2 | 1 |", "",
        "## Rekabet haritası (sözlük eksenleri × rakipler)", "| Eksen | Rakip A |", "|---|---|", "| kanıt: süreç | 1 |", "",
        "## Bulgular", "| Tür | Bulgu | Etiket | Kanıt (library_id, tarih) |", "|---|---|---|---|", f"| norm | örnek bulgu{weak} | proxy | 1 |", "",
        "## Fark (önceki görüntüye göre)", "İlk görüntü: önceki yok.", "",
        "## Kapsam ve güven", f"- Görüntü: #{snap.get('id', 0)} SHA-256 {str(snap.get('sha256', ''))[:12]}{weak}", ""])


def render_s02(ctx: dict) -> str:
    bp = ctx.get("budget_plan") or {}
    cy = ctx.get("cycle") or {}
    per = ((ctx.get("risk_limits") or {}).get("per_ad") or {})
    cur = _cur(ctx)
    fits = bp.get("fits_total_budget")
    fits_txt = "evet" if fits is True else ("hayır" if fits is False else "sınır yok (NULL)")
    rows = [
        f"| Kreatif başına gereken harcama | {_n(bp.get('per_creative_spend'))} {cur} |",
        f"| Günlük test bütçesi | {_n(bp.get('daily_test_budget'))} {cur} |",
        f"| Test günü / tur süresi | {cy.get('test_days') or bp.get('test_days') or '-'} / {cy.get('cycle_days') or bp.get('cycle_days') or '-'} gün |",
        f"| İzin verilen test reklamı sayısı | {bp.get('allowed_test_ads', 0)} (araç sınırı {bp.get('creative_test_tool_max', 7)}) |",
        f"| Toplam harcama planı | ek {_n((bp.get('spend_projection') or {}).get('projected_additional'))} · sığıyor mu: {fits_txt} |",
        f"| Zarar-risk sınırı (reklam başı, kapsam ad_launch_to_stop) | {_n(per.get('amount'))} {cur} — onay: «tamam» |",
    ]
    lines = [f"# Strateji — Örnek kampanya · tur {ctx.get('cycle_no', 1)}", "", "## (A) Ekonomi, bütçe ve takvim", "| Kalem | Değer |",
             "|---|---|", *rows, "", "Bu bir tahmindir; Meta'nın günlük harcamasının sabit ya da kesin sınırlı olduğu iddia edilmez."]
    if bp.get("production_blocked"):
        lines.append("Bütçe iki reklama yetmiyor: üretim bekler.")
    if (ctx.get("economics") or {}).get("status") == "non_positive":
        lines.append("Katkı ≤ 0: her satış zarar; kullanıcı bunu bilerek sürdürüyor (loss_acknowledged).")
    lines += ["", "## (B) Stratejik yön", "- Konumlandırma: boşluk: örnek tek cümle",
              f"- Tur modu: {'huni turu' if ctx.get('round_mode') == 'funnel' else 'normal (farklı alıcılar)'}", "",
              "## Reddedilen konumlandırmalar (sonraki tur için saklanır)", "- yok"]
    return "\n".join(lines) + "\n"


def render_s03(ctx: dict) -> str:
    lines = [f"# Görüşme özeti — tur {ctx.get('cycle_no', 1)}", ""]
    lines += [f"- Konsept {c}: seçildi" for c in ctx.get("accepted_concepts") or []] or ["- Seçilen konsept yok."]
    return "\n".join(lines) + "\n"


def render_s04(ctx: dict) -> str:
    n = max(1, int(ctx.get("accepted_test_hooks") or 0))
    rows = [f"| S{i + 1:02d} | A | ürün masada | 5 sn | yavaş itme | odak | hayır | evet |" for i in range(n)]
    return "\n".join([
        f"# Çekim rehberi — Örnek kampanya · tur {ctx.get('cycle_no', 1)}", "",
        "## Hazırlık (bir kez)", "- Telefon şarjlı, lens temiz.", "", "## 7 altın kural", "1. Doğal ışık.", "",
        "## Ürüne özgü tarif kartları", "- Kart 1: örnek.", "",
        "## Çekim menüsü (numaralı)", "| No | Konsept | Ne çekiyoruz | Süre | Kamera hareketi | Tek dikkat noktası | AI ile tamamlanabilir mi | Öncelikli |",
        "|---|---|---|---|---|---|---|---|", *rows, "", "## Ses", "Çekimdeki ses kullanılmıyor.", "",
        "## Fotoğraf listesi (konsept başına 5–8, telefonun FOTOĞRAF modunda)", "- Ürün önden.", "",
        "## İzin hatırlatması", "Tanınabilir kişi varsa kullanım izni kaydı alınır.", "",
        "## Teslim", "Sıkıştırmadan gönder.", "", "## Üretilecek efektlerin başlangıç listesi (sfx_plan)", "- yok", ""])


def render_s14(ctx: dict) -> str:
    cur = _cur(ctx)
    rl = ctx.get("risk_limits") or {}
    mapping = rl.get("mapping") or {}
    per = (rl.get("per_ad") or {}).get("amount")
    rows = [f"| {k} | {k}_9x16.mp4 | {k}_4x5.mp4 | video | {'evet' if ctx.get('has_ai') else 'hayır'} | "
            f"{_n((mapping.get(k) or {}).get('amount', per))} {cur} |" for k in ctx.get("test_keys") or []]
    c = ctx.get("campaign") or {}
    bt = c.get("budget_total")
    test = ctx.get("structure") in ("creative_test", "ab_test")
    lines = [
        f"# Yayın paketi — Örnek kampanya · tur {ctx.get('cycle_no', 1)}", "",
        "> Plugin Meta'ya YAZMAZ: yayın, bütçe ve limitleri insan Ads Manager'da uygular.", "",
        "## Yüklenecek dosyalar (yalnızca test kreatifleri; yedekler listede yok)",
        "| creative_key (= Meta reklam adı) | 9:16 dosyası | 4:5 dosyası | Medya | AI içeriği | Risk sınırı |", "|---|---|---|---|---|---|",
        *(rows or ["| - | - | - | - | - | - |"]), "",
        "## Metinler", "- Birincil metin: Örnek başlık ve örnek açıklama.", "",
        "## Ads Manager kurulum talimatı", "Tek kampanya, tek reklam seti." if not test else "Aynı reklam setinde kreatif test.",
        "Adım adım: hesabın güncel ekranında doğrulanır.", "",
        "## Advantage+ kreatif iyileştirmeleri (her reklamda kontrol)",
        "- Metin, görsel, müzik ve varış yeri iyileştirmelerini KAPAT." if test else "- İyileştirmeler senin seçimin.", "",
        "## Harcama ve bitiş sınırları (insan uygular)",
        f"- Kampanya toplam sınırı: {_n(bt) + ' ' + cur if bt is not None else 'sınır yok (NULL)'}",
        f"- Reklam başı zarar-risk sınırı: {_n(per)} {cur}", "",
        "## AI açıklaması", "AI içeren varyasyonlar için Ads Manager'ın AI etiketi açılır." if ctx.get("has_ai") else "AI içeriği yok.", "",
        "## Planlanan takvim", "- Planlanan yayın: örnek tarih.", "",
        "## Yayından sonra (kullanıcı)", "\"Yayına aldım\" de."]
    if c.get("result_type") == "lead":
        lines.append("Formda gizlilik politikası bağlantısı verilir.")
    return "\n".join(lines) + "\n"


def render_generic(stage: str, ctx: dict) -> str:
    return (f"# {ST.STAGE_NAMES.get(stage, stage)} — tur {ctx.get('cycle_no', 1)}\n\n"
            "Sentetik aşama belgesi: kayıtlar ad-memory'de, bu özet kullanıcıya gösterilen metindir.\n")


RENDER = {"S01": render_s01, "S01b": render_s01b, "S02": render_s02, "S03": render_s03, "S04": render_s04, "S14": render_s14}
DOC_NAME = {"S01": "brief", "S01b": "competitive/c{n}-rakip-analizi", "S02": "strategy", "S04": "cekim-rehberi", "S14": "yayin-paketi"}


def doc_path(store, profile_id: int, stage: str, campaign_id: int | None, cycle_no: int | None, scope_key: str | None) -> Path:
    if stage in ST.CAMPAIGN_STAGES:
        base = store.campaign_dir(profile_id, campaign_id)
        name = DOC_NAME.get(stage)
        if name and "{n}" in name:
            return base / (name.format(n=cycle_no) + ".md")
        return base / (f"c{cycle_no}-{name}.md" if name else f"c{cycle_no}-{stage.lower()}.md")
    sub = "brand" if stage == "S00a" else "products"
    tag = (scope_key or "").replace(":", "-") or stage.lower()
    return store.profile_dir(profile_id) / sub / f"{stage.lower()}-{tag}.md"


def write_stage_doc(store, profile_id: int, stage: str, campaign_id: int | None = None, cycle_id: int | None = None,
                    scope_key: str | None = None, check: bool = True, exhaust: bool = False) -> dict:
    ctx = store._draft_ctx(profile_id, stage, campaign_id, cycle_id) if stage in ST.CAMPAIGN_STAGES else {}
    text = RENDER.get(stage, lambda c: render_generic(stage, c))(ctx) if stage in RENDER else render_generic(stage, ctx)
    p = doc_path(store, profile_id, stage, campaign_id, ctx.get("cycle_no"), scope_key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    res = store.draft_check(profile_id, stage, str(p), campaign_id, cycle_id, scope_key) if (check and stage in DR.DRAFT_STAGES) else None
    # exhaust: kritik sorun kasıtlıysa (ör. kapı engelini sınayan test) tur sınırına kadar farklı içerikle yeniden denetlenir
    while exhaust and res and res["verdict"] == "fail" and not res["final_round"]:
        text += f"\nDüzeltme turu {res['round'] + 1}.\n"
        p.write_text(text, encoding="utf-8")
        res = store.draft_check(profile_id, stage, str(p), campaign_id, cycle_id, scope_key)
    return {"path": str(p), "check": res, "text": text}
