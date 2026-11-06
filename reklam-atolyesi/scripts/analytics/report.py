"""Koçluk raporu (spec 6.12): bölümler sabit; dil sade, hükümlerin yanında veri yeterliliği; rekabet bağlamında nedensellik dili yok.

Kullanım: report.py --analysis analysis.json --snapshot input.json --charts charts.json --out reports/c1-coach-report-v1.md
          [--calibration calib.json] [--actions actions.json] [--next next.md]
Bölümler: Özet (3 cümle) · Kararlar · Reklam mı, teklif mi, sayfa mı · Grafikler · Sahne düzeyinde izleyici kaybı · Ölçekleme katmanı · Uygulama listesi ve durumu · Rekabet bağlamı ·
Öğrenilenler · Sonraki tur · Veri yeterliliği · Koçluğun isabeti
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import atomic_write, emit, read_json  # noqa: E402
from admem.util import tr_fold  # noqa: E402

CAUSAL = [r"\bnedeniyle\b", r"\byuzunden\b", r"\bsebep (oldu|olmus)", r"\betkisiyle\b", r"\bdolayisiyla\b", r"\bbecause\b", r"\bcaused\b",
          r"\byol acti\b", r"\bsonucunda\b"]
SECTIONS = ["Özet", "Kararlar", "Reklam mı, teklif mi, sayfa mı", "Grafikler", "Sahne düzeyinde izleyici kaybı", "Ölçekleme katmanı", "Uygulama listesi ve durumu", "Rekabet bağlamı",
            "Öğrenilenler", "Sonraki tur", "Veri yeterliliği", "Koçluğun isabeti"]


DECISION_TR = {"büyüt": "büyüt (bütçesini artır)", "kapat": "durdur", "tut": "şimdilik olduğu gibi bırak"}
STATUS_TR = {"active": "yayında", "paused": "duraklatıldı", "closed": "kapandı"}
ACTION_TR = {"proposed": "önerildi", "approved": "onaylandı", "applied": "uygulandı", "not_applied": "uygulanmadı"}
ROLE_TR = {"proven": "Daha önce işe yaramış fikirler", "gap": "Rakiplerin boş bıraktığı fikirler", "counter": "Rakiplerin tersini söyleyen fikirler",
           "free": "Serbest denemeler"}
QUALITY_TR = {"missing_days": "Bazı günlerin verisi eksik:", "unmapped_ads": "Adı reklam kayıtlarımızla eşleşmeyen reklamlar var:",
              "video_3s_derived": "Bazı günlerde 3 saniyelik izlenme sayısı Meta'dan doğrudan gelmedi; harcamadan hesapladık.",
              "mixed_definitions": "Meta bu dönemde ölçüm tanımını değiştirmiş; farklı tanımlı rakamları birbirine karıştırmadık."}
# Analizden gelen kısa notlardaki terimler raporda sade karşılığıyla yazılır (2.9.0, KURALLAR K16).
PLAIN = [(r"\bhook oranı\b", "açılışı izleme oranı"), (r"\bhook\b", "videonun açılışı"), (r"\bbağlantı CTR'si\b", "bağlantıya tıklama oranı"),
         (r"\bbağlantı CTR\b", "bağlantıya tıklama oranı"), (r"\bCTR\b", "tıklama oranı"), (r"\bCPM\b", "1.000 gösterimin maliyeti"),
         (r"\bkonseptlerin\b", "fikirlerin"), (r"\bkonseptler\b", "fikirler"), (r"\bkonseptin\b", "fikrin"), (r"\bkonsepte\b", "fikre"),
         (r"\bkonsept\b", "fikir"), (r"\bkreatiflere\b", "reklamlara"), (r"\bkreatifinde\b", "reklamında"), (r"\bkreatif testine\b", "reklam denemesine"),
         (r"\bkreatif\b", "reklam"), (r"\bönsele\b", "başlangıç beklentisine"), (r"\bplaybook\b", "kalıcı kural"), (r"\büst huni\b", "ilk izlenim"),
         (r" · ", ", "), (r" → ", ": "), (r"\bTOFU\b", "ilk kez görenlere seslenen"), (r"\bMOFU\b", "tanıyanlara seslenen"),
         (r"\bBOFU\b", "almaya yakın olanlara seslenen"), (r"\(coach 6a\)|\(6\.\d+\)|\(lead_outcomes\)|\(ürün ekonomisinde lead_close_rate\)", ""),
         (r"lead_outcome_set ile", "aday kayıtlarına"), (r"\bS00b 6b\b", "veri bağlantısı adımı"), (r"\bDM\b", "mesaj")]


def _plain(s) -> str:
    out = str(s or "")
    for p, r in PLAIN:
        out = re.sub(p, r, out)
    return re.sub(r"\s+([.,;])", r"\1", out).strip()


def _days(q_: dict) -> str:
    v = q_.get("days") or q_.get("ads") or ""
    return ", ".join(map(str, v)) if isinstance(v, list) else str(v)


def causal_terms(text: str) -> list[str]:
    t = tr_fold(text)
    return [p for p in CAUSAL if re.search(p, t)]


def build(an: dict, snap: dict, charts: dict, calibration: dict | None, actions: list | None, next_md: str | None) -> str:
    camp = snap["campaign"]
    cyc = snap["cycle"]
    q = an.get("verdict_qualifier") or ""
    dec = an["decisions"]
    lines = [f"# Koçluk raporu — {camp['name']} · tur {cyc['cycle']}", "",
             f"_Bu rapor, verilerin değişmeyen bir kopyasından hazırlandı (kayıt kodu {an['snapshot']['sha256'][:12]}); aynı kopyadan hep aynı "
             f"sonuç çıkar._", f"<!-- girdi: {Path(an['snapshot']['path']).name}, model {an.get('model_version')}, "
             f"tohum {(an.get('params') or {}).get('seed')} -->", ""]
    n_ev = sum(1 for d in dec if d["label"].startswith("kanıt"))
    lines += ["## Özet", "",
              f"Bu turda {len(an['concepts'])} reklam fikrini ve {len(an['creatives'])} reklamı ölçtük; {n_ev} fikrin verisi karar vermeye yetti"
              + (f" ({_plain(q)})." if q else "."),
              (f"Bir sonucun kaça mal olduğuna dair yargıyı yalnızca en az 10 sonuç alan fikirlerde verdik; " if any(c.get("threshold_met") for c in an["cost"].values())
               else "Sonuç sayısı az olduğu için yorumlarımız satışa değil, izlenmeye ve tıklamaya dayanıyor; ")
              + "verinin yetmediği bulgular 'yön' diye işaretli: bunlar kesin değil, yalnızca bir eğilim gösterir.",
              ("Onayladığın bir harcama sınırına ulaşıldı ya da yaklaşıldı: ayrıntı Kararlar bölümünde." if an["limit_alerts"] else "Harcama sınırlarında bir sorun yok."), ""]
    mb = an.get("metric_basis")
    if mb:
        lines[-1:-1] = [f"**Karar metriği:** kararları {_plain(mb['decision'])} üzerinden verdik. {_plain(mb['note'])}"]
    lines += ["## Kararlar", ""]
    for d in dec:
        lines.append(f"- **{d['concept']}**: {DECISION_TR.get(d['decision'], d['decision'])} ({_plain(d['label'])}). {_plain(d['why']).rstrip('.')}."
                     + (f" Meta'da yapılacak: {_plain(d['ads_manager']).rstrip('.')}." if d.get("ads_manager") else ""))
    if any("dağıtımı altında" in d["label"] for d in dec):
        lines.append("_\"Meta'nın dağıtımı altında\" şu demek: bütçeyi reklamlar arasında Meta kendisi paylaştırdı. Bu yüzden karşılaştırma tam eşit "
                     "koşullarda yapılmadı; sonuçları dikkatli okumak gerekir._")
    enh = an.get("enhancements") or {}
    if enh.get("recorded") and not enh.get("checked"):
        lines.append("- ⚠ Meta'nın reklamlarda kendiliğinden yaptığı değişiklikler (Advantage+ kreatif iyileştirmeleri) yayında kontrol edilmedi. "
                     "Meta bunların bazılarını kendiliğinden açar; bu yüzden iyi sonucu bizim reklamımızın mı yoksa Meta'nın değişikliğinin mi "
                     "getirdiğini ayırt edemeyebiliriz.")
    elif enh.get("on"):
        scope = "tüm reklamlarda" if enh.get("all") else ", ".join(enh.get("concepts") or [])
        lines.append("- ⚠ Açık kalan Meta iyileştirmeleri (" + ", ".join(i["name"] for i in enh["on"]) + f"; {scope}): bu reklamlarla ilgili "
                     "yorumlar 'Meta iyileştirmesi açık' notuyla yazıldı. Bir sonraki denemede bunları kapatmanı öneririm.")
    for a in an["limit_alerts"]:
        lines.append(f"- ⚠ Harcama sınırı: {a['msg']} ({(a.get('creative_key') or '') + ': ' if a.get('creative_key') else ''}harcanan {a.get('spend', '')}, "
                     f"sınır {a.get('limit', a.get('budget_total', ''))})")
    sup = an.get("superiority_hook") or {}
    if sup:
        lines += ["", f"_Hangi reklam fikrinin en iyi olma olasılığı: {_plain((mb or {}).get('superiority', 'videonun açılışını izleyenlerin oranı'))}_"]
        for k in sorted(sup):
            hr = (an["concepts"].get(k, {}).get("rates") or {}).get("hook_rate") or {}
            pb = sup[k].get("p_best")
            if pb is not None:
                lines.append(f"- {k}: en iyi olma olasılığı %{pb * 100:.0f} (açılışı izleme oranına göre: {int(hr.get('successes', 0))} izlenme, "
                             f"{int(hr.get('trials', 0))} gösterim; {_plain(hr.get('label', '—'))})")
    lines += ["", "## Reklam mı, teklif mi, sayfa mı", ""]
    fd = an.get("funnel_diagnosis")
    if fd:
        for p in fd["per_concept"]:
            lines.append(f"- **{p['concept']}**: " + "; ".join(p["notes"]))
        lines.append(f"- Tıklamadan sonrası: {fd['after_click']['msg']}")
        fs = fd.get("steps")
        if fs:  # 2.4.0: ortak adım tablosu; her oran kendi paydasıyla, birbirleriyle çarpılmaz
            lines.append("- Tıklamadan sonra adım adım (Meta'nın saydığı olaylar; her adımın oranı bir önceki adıma göre hesaplanır):")
            for st in fs["steps"]:
                if st.get("rate") is not None:
                    txt = (f"%{st['rate'] * 100:.1f} ({int(st['count'])} / {int(st['denominator_count'])} {st['denominator_label']}"
                           + ("" if st["canonical"] else "; önceki adım okunamadı, geçmişle kıyaslanmaz") + ")")
                    if st.get("coverage") is not None and st["coverage"] < 0.995:  # 2.10.2: olay her satırda gelmedi
                        txt += (f"; bu olay {st['denominator_label']} sayısının yalnızca %{st['coverage'] * 100:.0f}'inde ölçüldü, "
                                "oran o kısımdan hesaplandı")
                    if st["status"] == "veri_yetersiz":
                        txt += "; veri yetersiz"
                    if st.get("history_mean") is not None:
                        txt += f"; geçmişteki ortalama %{st['history_mean'] * 100:.1f}"
                    if st.get("weak"):
                        txt += "; ⚠ geçmişin altında"
                else:
                    txt = st["msg"].split(": ", 1)[1]
                lines.append(f"  - {st['label']}: {txt}")
            if fs.get("msg"):
                lines.append(f"  - {fs['msg']}")
        ch = an.get("channels") or {}
        if ch.get("sales") or ch.get("leads"):
            parts = [f"{k}: {v['units']} adet" + (f" / {v['revenue']}" if v.get("revenue") else "") for k, v in ch["sales"].items()]
            parts += [f"{k}: {n} talep" for k, n in ch["leads"].items()]
            lines.append("- Satış kanalları: " + ", ".join(parts) + ". Instagram mesajı, WhatsApp ve kurumsal satışlar Meta'da görünmez.")
        for chn, curs in (ch.get("other_currency") or {}).items():  # 2.10.3: farklı para birimi toplanmaz
            for cur, v in curs.items():
                lines.append(f"- ⚠ {chn} kanalında {cur} cinsinden {v['units']} adet / {v['revenue']} {cur} satış var. Para birimi "
                             f"{ch.get('currency') or 'esas para birimi'} olmadığı için gelire eklenmedi.")
        for ex in ch.get("excluded_manual") or []:
            lines.append(f"- ⚠ Elle girilen {ex['channel']} satışı ({ex['period'][0]}–{ex['period'][1]}, {ex['units']} adet): {ex['why']}.")
        svm = an.get("store_vs_meta")
        if svm:
            lines.append(f"- Meta ve mağaza karşılaştırması: {svm['msg']}")
        dm = an.get("dm")
        if dm:
            t = dm["totals"]
            line = (f"- Mesajla satış: {t['conversations']} konuşmanın {t['qualified']} tanesi ciddi talepti (nitelikli), {t['quoted']} tanesine "
                    f"teklif verildi, {t['won']} tanesi satışa döndü"
                    + (f" (gerçek satış oranı büyük olasılıkla %{dm['won_rate_interval']['lo'] * 100:.0f} ile %{dm['won_rate_interval']['hi'] * 100:.0f} arasında)"
                       if dm.get("won_rate_interval") else ""))
            if dm.get("median_first_response_min") is not None:
                line += f"; mesajlara ilk cevap genelde {dm['median_first_response_min']:.0f} dakikada verildi"
            lines.append(line + ".")
            if dm.get("lost_reasons"):
                lines.append("  - Kayıp nedenleri: " + ", ".join(f"{k} {v}" for k, v in dm["lost_reasons"].items()))
            if dm.get("open_quote_pipeline"):
                lines.append("  - Açık teklifler: " + ", ".join(f"{v} {k}" for k, v in dm["open_quote_pipeline"].items()))
            if dm.get("campaign_attributed"):
                ca = dm["campaign_attributed"]
                lines.append(f"  - Bu kampanyaya kanıtla bağlı konuşma {ca['threads']}, satış {ca['won']} (günlük toplamlar kampanyaya bölünmez).")
        ab = an.get("ab_test")
        if ab and ab.get("cells"):
            lines.append("- Meta A/B testi (kitle rastgele ve eşit bölündü): " + "; ".join(
                f"{k}: {v['results']} sonuç" + (f", sonuç başı {v['cost_per_result']}" if v.get("cost_per_result") else "")
                + f", en düşük maliyetli olma olasılığı %{v['p_lowest_cost'] * 100:.0f}" + ("" if v["threshold_met"] else " (yön)")
                for k, v in ab["cells"].items()) + ".")
            mr = ab.get("meta_read") or {}
            if mr:
                lines.append(f"  - Meta'nın sonucu: kazanan {mr.get('winner_concept') or 'belirlenmedi'}"
                             + (f", güven {mr['confidence']}" if mr.get("confidence") is not None else "") + ".")
            if ab.get("disagreement_note"):
                lines.append(f"  - {ab['disagreement_note']}")
        ld = an.get("lead")
        if ld:
            t = ld["totals"]
            seg = [f"{ld['meta_leads']} aday (Meta)" + (f", aday başı {ld['cost_per_lead']}" if ld.get("cost_per_lead") else "")]
            if ld.get("periods"):
                seg.append(f"kayıtlarda {t['leads']} aday var: " + ", ".join(
                    f"{t[k] if t.get(k) is not None else '?'} {lab}" for k, lab in (("reached", "tanesine ulaşıldı"), ("qualified", "tanesi ciddi talepti (nitelikli)"),
                                                                                    ("won", "tanesi satışa döndü"))))
            if ld.get("cost_per_qualified"):
                seg.append(f"nitelikli aday başı {ld['cost_per_qualified']}")
            if ld.get("cost_per_won"):
                seg.append(f"satış başı {ld['cost_per_won']}")
            if ld.get("close_rate_interval"):
                iv = ld["close_rate_interval"]
                seg.append(f"adayların satışa dönme oranı büyük olasılıkla %{iv['lo'] * 100:.0f} ile %{iv['hi'] * 100:.0f} arasında")
            lines.append("- Müşteri adayı: " + "; ".join(seg) + ".")
            for k in ("meta_vs_crm_note", "coverage_note", "partial_note", "close_rate_check", "note"):
                if ld.get(k):
                    lines.append(f"  - {_plain(ld[k])}")
        lines.append(f"_{_plain(fd['rule'])}_")
    else:
        lines.append("- Teşhis yok.")
    stg = an.get("stages")
    if stg:
        names = {"tofu": "ürünü ilk kez görenler", "mofu": "ürünü tanıyanlar", "bofu": "almaya yakın olanlar"}
        labels = {"hook_rate": "açılışı izleme oranı", "hold_rate": "izlemeye devam oranı", "spend_per_3s_view": "3 saniyelik bir izlenmenin maliyeti",
                  "ctr_link": "bağlantıya tıklama oranı", "landing_page_view_rate": "tıklayıp sayfayı açanlar",
                  "view_content_rate": "tıklayıp ürüne bakanlar", "add_to_cart_rate": "tıklayıp sepete ekleyenler",
                  "checkout_rate": "tıklayıp ödemeye geçenler", "cost_per_purchase": "bir satışın maliyeti"}
        lines += ["", "## Huni aşamaları", "",
                  ("Huni turu: reklam fikirleri aynı alıcıya, karar verme sürecinin farklı anlarında seslendi." if stg["round_mode"] == "funnel"
                   else "Normal tur: bu bilgi yalnızca sorunun nerede olduğunu anlamak için.")]
        for p in stg["per_concept"]:
            vals = [f"{labels[n]} {v:.2%}" if (isinstance(v, float) and n.endswith("rate")) else f"{labels[n]} {v}"
                    for n, v in p["metrics"].items() if v is not None]
            line = f"- **{p['concept']}** ({names[p['stage']]}): " + ("; ".join(vals) if vals else "bu aşamanın ölçüsü okunamadı")
            if p["unread"]:
                line += "; okunamayanlar: " + ", ".join(labels[n] for n in p["unread"])
            if p["segments"]:
                s = p["segments"]
                line += (f"; harcamanın %{s['new'] * 100:.0f} kadarı yeni kişilere, %{s['engaged'] * 100:.0f} kadarı daha önce etkileşime geçenlere, "
                         f"%{s['existing'] * 100:.0f} kadarı mevcut müşterilere gitti")
            lines.append(line)
            if p.get("segment_note"):
                lines.append(f"  - {_plain(p['segment_note'])}")
        if not stg["segments_read"]:
            lines.append("- Reklamı kimin gördüğünü okuyamadık (Meta'da kitle grupları tanımlı değil ya da döküm girilmedi).")
        lines.append(f"_{_plain(stg['rule'])}_")
    lines += ["", "## Grafikler", ""]
    captions = {"funnel": "Her reklam fikri için izlenme, tıklama ve sonuç oranları; her oran kendi tabanına göre hesaplandı, birbirleriyle çarpılmaz.",
                "intervals_hook": "Videonun açılışını (ilk 3 saniye) izleyenlerin oranı ve olası aralığı; açık renkli noktalar az veriye dayanır, yalnızca yön gösterir.",
                "intervals_ctr": "Reklamı görüp bağlantıya tıklayanların oranı ve olası aralığı; 3.000 gösterimin altındakiler yalnızca yön gösterir.",
                "spend": "Meta'nın bütçeyi reklamlar arasında nasıl paylaştırdığı; az bütçe alan fikir kaybetmiş sayılmaz.",
                "timeseries": "Günlere göre açılışı izleme oranı; düşüş, izleyenlerin reklamı görmekten sıkıldığını düşündürebilir ama kesin değildir.",
                "retention": "İzleyenlerin beklenenden hızlı ayrıldığı saniyeler; Meta bunu az noktada ölçtüğü için bu bir olasılıktır."}
    for k, p in charts.items():
        lines += [f"![{k}]({Path(p).parent.name}/{Path(p).name})", f"_{captions.get(k, '')}_", ""]
    lines += ["## Sahne düzeyinde izleyici kaybı", ""]
    lines += [f"- {_plain(r['statement'])}" for r in an["retention"]] or ["- İzleyenlerin ayrılışında beklenmedik bir şey görmedik ya da karşılaştırma için yeterli reklam yok."]
    lines += ["", "## Ölçekleme katmanı", ""]
    sl = an.get("scale_layer")
    if sl:
        lines.append(f"- İyi giden reklamları büyüttüğümüz kampanya ({_plain(sl['label'])}): günlük bütçe {sl.get('daily_budget')}, "
                     f"durum {STATUS_TR.get(sl.get('status'), sl.get('status'))}, toplam harcama {sl['spend']}."
                     + (f" ⚠ {sl['learning_warning']}" if sl.get("learning_warning") else ""))
        for m in sl["members"]:
            cpr = f", sonuç başı {m['cost_per_result']}" if m.get("cost_per_result") is not None else ""
            lines.append(f"  - {m['creative_key']} (gönderi {m.get('post_id')}): harcama {m['spend']}, sonuç {m['results']}{cpr}; son 7 günde bir kişi "
                         f"bu reklamı ortalama {m.get('frequency_last7')} kez gördü")
        lines += [f"  - Dikkat: {_plain(f['msg'])} ({f['creative']})" for f in sl["fatigue"]]
    for c in an.get("scale_candidates") or []:
        if c["eligible"]:
            lines.append(f"- **{c['concept']}**: {_plain(c['action'])} (günlük bütçe en az {c['min_daily']}; {_plain(c['fits_note'])}). Bunun için "
                         "gönderinin numarası Ads Manager'dan okunur; okunamazsa reklam taşınmaz.")
        else:
            lines.append(f"- **{c['concept']}**: {_plain(c['action'])}. Ayrı kampanyada büyütmeyi önermiyorum, çünkü: {_plain('; '.join(c['reasons']))}.")
    if not sl and not an.get("scale_candidates"):
        lines.append("- İyi giden reklamları büyüttüğümüz ayrı bir kampanya yok ve bu turda büyütmeye değer bir fikir çıkmadı.")
    lines += ["_Büyütülen reklamların sonuçları, deneme sonuçlarına, başlangıç beklentilerimize ya da kalıcı kurallarımıza karıştırılmaz._"]
    lines += ["", "## Uygulama listesi ve durumu", ""]
    lines += [f"- [{ACTION_TR.get(a.get('status', 'proposed'), a.get('status', 'proposed'))}] {_plain(a['action'])}" for a in (actions or [])] \
        or ["- Bu raporla yeni bir adım önermedim."]
    lines += ["", "## Rekabet bağlamı", ""]
    cc = an.get("competitive_context") or {}
    stm = cc.get("statements") or []
    lines += [f"- {s}" for s in stm] or ["- Deneme süresinde rakiplerde kayda değer bir değişiklik görmedik ya da karşılaştıracak önceki inceleme yok."]
    lines += ["_Rakiplerdeki değişiklikler yalnızca bilgi içindir; sonuçlarımızı onlara bağlamıyoruz ve kararlarımıza katmıyoruz._", ""]
    lines += ["## Öğrenilenler", ""]
    roles = an.get("roles") or {}
    if roles:
        for r, v in sorted(roles.items()):
            hr = (v["rates"].get("hook_rate") or {})
            lines.append(f"- **{ROLE_TR.get(r, r)}**: açılışı izleme oranı ortalaması %{hr.get('mean', 0) * 100:.1f} ({_plain(hr.get('label', '—'))}). "
                         "Bu yalnızca bir ön karşılaştırmadır.")
    lines += [f"- Dikkat: {_plain(f['msg'])} ({f['creative']})" for f in an["fatigue"]]
    lines += ["", "## Sonraki tur", "", next_md or "- Sonraki tur önerileri, bu turdan öğrendiklerimizle birlikte yeni reklam özetine eklenecek; "
              "rakiplere yeniden bakmamız gerekip gerekmediğini de not edeceğim.", ""]
    lines += ["## Veri yeterliliği", ""]
    w = an["window"]
    ex_days = ", ".join(w["excluded_boundary_days"])
    lines.append(f"- Denemenin tam gün sayısı: {len(w['full_days'])}." + (f" Başlangıç ve bitiş günleri yarım olduğu için karşılaştırmaya katılmadı ({ex_days}); "
                 "bu günlerin harcaması toplamda sayıldı." if ex_days else ""))
    lines += [f"- {QUALITY_TR.get(q_['kind'], _plain(q_.get('msg', '')))} {_days(q_)}".rstrip() for q_ in an["data_quality"]] \
        or ["- Verilerde bir sorun görmedik."]
    lines.append("- Son 3 günün rakamları Meta'da hâlâ değişebilir; satışlar birkaç gün geç yazılabildiği için bu günler kesin sayılmaz.")
    lines += ["", "## Koçluğun isabeti", ""]
    if calibration:
        lines.append(f"- {_plain(calibration.get('summary', ''))}" + (f" {_plain(calibration.get('note'))}" if calibration.get("note") else ""))
    else:
        lines.append("- Önceki tahminlerimizin doğru çıkıp çıkmadığını görmek için henüz yeterli sonuç yok.")
    text = "\n".join(lines) + "\n"
    comp_part = text.split("## Rekabet bağlamı", 1)[1].split("## Öğrenilenler", 1)[0]
    bad = causal_terms(comp_part)
    if bad:
        raise SystemExit(f"Rekabet bağlamında nedensellik dili: {bad} (6.16)")
    return text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--analysis", required=True)
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--charts")
    ap.add_argument("--calibration")
    ap.add_argument("--actions")
    ap.add_argument("--next")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    md = build(read_json(a.analysis), read_json(a.snapshot), read_json(a.charts) if a.charts else {}, read_json(a.calibration) if a.calibration else None,
               read_json(a.actions) if a.actions else None, Path(a.next).read_text(encoding="utf-8") if a.next else None)
    sha = atomic_write(a.out, md, overwrite=False)
    emit({"out": a.out, "sha256": sha, "sections": [s for s in SECTIONS if f"## {s}" in md]})


if __name__ == "__main__":
    main()
