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


def causal_terms(text: str) -> list[str]:
    t = tr_fold(text)
    return [p for p in CAUSAL if re.search(p, t)]


def build(an: dict, snap: dict, charts: dict, calibration: dict | None, actions: list | None, next_md: str | None) -> str:
    camp = snap["campaign"]
    cyc = snap["cycle"]
    q = an.get("verdict_qualifier") or ""
    dec = an["decisions"]
    lines = [f"# Koçluk raporu — {camp['name']} · tur {cyc['cycle']}", "",
             f"_Girdi kopyası: `{Path(an['snapshot']['path']).name}` (SHA-256 {an['snapshot']['sha256'][:12]}…), model {an.get('model_version')}, tohum {(an.get('params') or {}).get('seed')}._", ""]
    n_ev = sum(1 for d in dec if d["label"].startswith("kanıt"))
    lines += ["## Özet", "",
              f"Bu turda {len(an['concepts'])} konsept ve {len(an['creatives'])} kreatif ölçüldü; {n_ev} konseptin verisi karar eşiğini geçti"
              + (f" ({q})." if q else "."),
              (f"Sonuç maliyetine dair hüküm yalnızca yeterli sonuç (≥ 10) olan konseptlerde verildi; " if any(c.get("threshold_met") for c in an["cost"].values())
               else "Sonuç sayısı az olduğu için bu hüküm satışa değil, dikkat ve tıklamaya dayanıyor; ")
              + "eşik altındaki bulgular 'yön' etiketlidir.",
              ("Onaylı harcama sınırı uyarısı var: ayrıntı Kararlar bölümünde." if an["limit_alerts"] else "Harcama sınırı uyarısı yok."), ""]
    mb = an.get("metric_basis")
    if mb:
        lines[-1:-1] = [f"**Karar metriği:** {mb['decision']}. {mb['note']}"]
    lines += ["## Kararlar", ""]
    for d in dec:
        lines.append(f"- **{d['concept']}** → {d['decision']} ({d['label']}): {d['why']}" + (f" — Ads Manager: {d['ads_manager']}" if d.get("ads_manager") else ""))
    for a in an["limit_alerts"]:
        lines.append(f"- ⚠ Sınır: {a['msg']} ({a.get('creative_key') or ''} {a.get('spend', '')} / {a.get('limit', a.get('budget_total', ''))})")
    sup = an.get("superiority_hook") or {}
    if sup:
        lines += ["", f"_Olasılıklar — {(mb or {}).get('superiority', 'hook oranı')}:_"]
        for k in sorted(sup):
            hr = (an["concepts"].get(k, {}).get("rates") or {}).get("hook_rate") or {}
            pb = sup[k].get("p_best")
            if pb is not None:
                lines.append(f"- {k}: en iyi olma olasılığı {pb:.0%} (hook oranı; {int(hr.get('successes', 0))} izlenme / "
                             f"{int(hr.get('trials', 0))} gösterim; {hr.get('label', '—')})")
    lines += ["", "## Reklam mı, teklif mi, sayfa mı", ""]
    fd = an.get("funnel_diagnosis")
    if fd:
        for p in fd["per_concept"]:
            lines.append(f"- **{p['concept']}**: " + "; ".join(p["notes"]))
        lines.append(f"- Tıklamadan sonrası: {fd['after_click']['msg']}")
        ch = an.get("channels") or {}
        if ch.get("sales") or ch.get("leads"):
            parts = [f"{k}: {v['units']} adet" + (f" / {v['revenue']}" if v.get("revenue") else "") for k, v in ch["sales"].items()]
            parts += [f"{k}: {n} talep" for k, n in ch["leads"].items()]
            lines.append("- Kanallar: " + " · ".join(parts) + ". DM/WhatsApp/kurumsal Meta'da görünmez.")
        for ex in ch.get("excluded_manual") or []:
            lines.append(f"- ⚠ Elle girilen {ex['channel']} satışı ({ex['period'][0]}–{ex['period'][1]}) sayılmadı: {ex['why']}.")
        svm = an.get("store_vs_meta")
        if svm:
            lines.append(f"- Meta ↔ mağaza: {svm['msg']}")
        dm = an.get("dm")
        if dm:
            t = dm["totals"]
            line = (f"- Mesajla satış: {t['conversations']} konuşma → {t['qualified']} nitelikli → {t['quoted']} teklif → {t['won']} satış"
                    + (f" (satış oranı %90 aralık {dm['won_rate_interval']['lo']:.0%}–{dm['won_rate_interval']['hi']:.0%})"
                       if dm.get("won_rate_interval") else ""))
            if dm.get("median_first_response_min") is not None:
                line += f"; ilk cevap ortanca {dm['median_first_response_min']:.0f} dk"
            lines.append(line + ".")
            if dm.get("lost_reasons"):
                lines.append("  - Kayıp nedenleri: " + ", ".join(f"{k} {v}" for k, v in dm["lost_reasons"].items()))
            if dm.get("open_quote_pipeline"):
                lines.append("  - Açık teklifler: " + ", ".join(f"{v} {k}" for k, v in dm["open_quote_pipeline"].items()))
            if dm.get("campaign_attributed"):
                ca = dm["campaign_attributed"]
                lines.append(f"  - Bu kampanyaya kanıtla bağlı konuşma {ca['threads']}, satış {ca['won']} (günlük toplamlar kampanyaya bölünmez).")
        lines.append(f"_{fd['rule']}_")
    else:
        lines.append("- Teşhis yok.")
    lines += ["", "## Grafikler", ""]
    captions = {"funnel": "Konsept başına izlenme, tıklama ve sonuç oranları kendi paydalarıyla; oranlar birbirleriyle çarpılmaz.",
                "intervals_hook": "Hook oranı aralıkları; açık renkli noktalar eşik altıdır ve yalnızca yön gösterir.",
                "intervals_ctr": "Bağlantı CTR aralıkları; 3.000 gösterim altı yön etiketlidir.",
                "spend": "Meta'nın bütçeyi nasıl dağıttığı; aç kalan konsept kaybeden sayılmaz.",
                "timeseries": "Günlük hook oranı; düşüş yorgunluk olasılığıdır, nedeni kesin değildir.",
                "retention": "Beklenenden hızlı kayıp görülen aralıklar; 5 ölçüm noktasıyla olasılık cümlesidir."}
    for k, p in charts.items():
        lines += [f"![{k}]({Path(p).parent.name}/{Path(p).name})", f"_{captions.get(k, '')}_", ""]
    lines += ["## Sahne düzeyinde izleyici kaybı", ""]
    lines += [f"- {r['statement']}" for r in an["retention"]] or ["- Beklenen eğriden belirgin sapma yok ya da karşılaştırma için yeterli kreatif yok."]
    lines += ["", "## Ölçekleme katmanı", ""]
    sl = an.get("scale_layer")
    if sl:
        lines.append(f"- Katman ({sl['label']}): günlük {sl.get('daily_budget')}, durum {sl.get('status')}, toplam harcama {sl['spend']}."
                     + (f" ⚠ {sl['learning_warning']}" if sl.get("learning_warning") else ""))
        for m in sl["members"]:
            cpr = f", sonuç başı {m['cost_per_result']}" if m.get("cost_per_result") is not None else ""
            lines.append(f"  - {m['creative_key']} (gönderi {m.get('post_id')}): harcama {m['spend']}, sonuç {m['results']}{cpr}, son 7 gün sıklık {m.get('frequency_last7')}")
        lines += [f"  - Yorgunluk: {f['msg']} ({f['creative']})" for f in sl["fatigue"]]
    for c in an.get("scale_candidates") or []:
        if c["eligible"]:
            lines.append(f"- **{c['concept']}** → {c['action']} (günlük ≥ {c['min_daily']}; {c['fits_note']}). Gönderi kimliği Ads Manager'dan okunur; yoksa taşınmaz.")
        else:
            lines.append(f"- **{c['concept']}** → {c['action']}. Ölçekleme önerilmedi: {'; '.join(c['reasons'])}.")
    if not sl and not an.get("scale_candidates"):
        lines.append("- Ölçekleme katmanı yok ve bu turda 'büyüt' hükmü alan konsept yok.")
    lines += ["_Ölçekleme katmanının verisi test hükmüne, önsele ya da playbook kanıtına girmez._"]
    lines += ["", "## Uygulama listesi ve durumu", ""]
    lines += [f"- [{a.get('status', 'proposed')}] {a['action']}" for a in (actions or [])] or ["- Bu raporla yeni madde önerilmedi."]
    lines += ["", "## Rekabet bağlamı", ""]
    cc = an.get("competitive_context") or {}
    stm = cc.get("statements") or []
    lines += [f"- {s}" for s in stm] or ["- Test penceresinde kayda değer rakip değişikliği görülmedi ya da fark görüntüsü yok."]
    lines += ["_Rekabet bağlamı bilgi içindir; nedensellik iddia edilmez ve hüküm diline girmez._", ""]
    lines += ["## Öğrenilenler", ""]
    roles = an.get("roles") or {}
    if roles:
        for r, v in sorted(roles.items()):
            hr = (v["rates"].get("hook_rate") or {})
            lines.append(f"- Portföy rolü **{r}**: hook oranı ortalaması {hr.get('mean', 0):.3f} ({hr.get('label', '—')}) — keşif karşılaştırmasıdır.")
    lines += [f"- Yorgunluk/anomali: {f['msg']} ({f['creative']})" for f in an["fatigue"]]
    lines += ["", "## Sonraki tur", "", next_md or "- Sonraki tur önerileri S17'de brief taslağına işlenir; rakip görüntüsü tazelenmeli mi notu eklenir.", ""]
    lines += ["## Veri yeterliliği", ""]
    w = an["window"]
    lines.append(f"- Test penceresi tam günleri: {len(w['full_days'])}; dışlanan sınır günleri: {', '.join(w['excluded_boundary_days']) or 'yok'} (bölünmez, toplam harcamada sayılır).")
    lines += [f"- {q_['kind']}: {q_.get('msg', '')} {q_.get('days', q_.get('ads', ''))}" for q_ in an["data_quality"]] or ["- Veri kalitesi kontrollerinde sorun yok."]
    lines.append("- Son 72 saatin verisi geçicidir; sonuç metrikleri olgunluk penceresi dolmadan kesin sayılmaz.")
    lines += ["", "## Koçluğun isabeti", ""]
    if calibration:
        lines.append(f"- {calibration.get('summary', '')}" + (f" · {calibration.get('note')}" if calibration.get("note") else ""))
    else:
        lines.append("- Henüz çözülmüş tahmin yok.")
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
