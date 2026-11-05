#!/usr/bin/env python3
"""Hata defterlerini toplu okur (2.8.0, admin tarafı; müşteride çalışmaz).

Müşterilerden gelen hata defteri dosyalarını (logs/hata-defteri/*.json; 2.5.0'dakiler logs/geri-bildirim/*.json) bir arada okur ve
tek bir Markdown rapor yazar:

1. Sürüm başına saha göstergeleri: kaç defter, ilk turda geçen taslak oranı, düzeltme/geri dönüş/takılma/hata sayıları.
   Bu tablo `evals/etki-defteri.md`'deki sürüm satırının "sahada" bölümüne yapıştırılır.
2. Tekrarlayan imzalar: aşama · ne oldu · kod · senaryo hücresi (ürün × kullanıcı) → kaç kez, kaç defterde.
3. Kapsam: her tekrarlayan imza için onu kapsayan AÇIK eval vakası var mı (evals/senaryo-matrisi.json → eval_cases; kapalı
   vakalara (kapali_cases) bilerek bakılmaz, 2.10.0)? Yoksa
   `--iskelet <klasör>` verilirse oraya doldurulmaya hazır bir vaka iskeleti yazar (prompt.md + graders/). İskelet bilerek evals/
   dışına yazılır: `claude plugin eval` evals/ altındaki her prompt.md'yi çalıştırır; iskelet doldurulup vakalar/ altına taşınınca ve
   matrise eklenince sete girer.
4. Sürüm karşılaştırması: aynı imzanın defter başına sıklığı yeni sürümde arttıysa "kötüleşti", azaldıysa "iyileşti".

Kullanım:
    python evals/defter_oku.py <dosya-ya-da-klasör>... [--out rapor.md] [--esik 2] [--iskelet /tmp/yeni-vakalar]

Yalnızca standart kütüphane. Defterler anonimdir (sayılar ve sabit kodlar); rapor da yalnızca bunları içerir.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MATRIX = HERE / "senaryo-matrisi.json"

SIGNAL_TEXT = {
    "duzeltme_istendi": "kullanıcı değişiklik istedi",
    "geri_donuldu": "önceki adıma geri dönüldü",
    "takildi": "adım 3 günden uzun bekliyor",
    "taslak_son_tur_kaldi": "taslak son turda da denetimi geçemedi",
    "sorunla_onaylandi": "kalan sorunla onaylandı",
    "kreatif_red": "kreatif kalite kontrolünden geçemedi",
    "arac_hatasi": "araç hata verdi",
}
PRODUCT_SETS = {"P1-3": {"P1", "P2", "P3"}, "Px": None}
USER_SETS = {"Ux": {"U1", "U2", "U7", "U8"}}


def vkey(v: str) -> tuple:
    out = []
    for p in str(v).split("."):
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    return tuple(out)


def load_defters(paths: list[str]) -> tuple[list[dict], list[str]]:
    files: list[Path] = []
    for p in paths:
        pp = Path(p)
        if pp.is_dir():
            files += sorted(x for x in pp.rglob("*.json") if x.is_file())
        elif pp.is_file():
            files.append(pp)
    seen, out, notes = set(), [], []
    for f in files:
        raw = f.read_bytes()
        h = hashlib.sha256(raw).hexdigest()
        if h in seen:
            notes.append(f"aynı dosya iki kez geldi, bir kez sayıldı: {f.name}")
            continue
        try:
            d = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            notes.append(f"okunamadı (JSON değil): {f.name}")
            continue
        if not isinstance(d, dict) or not str(d.get("schema", "")).startswith("reklam-atolyesi-geri-bildirim/"):
            notes.append(f"hata defteri değil, atlandı: {f.name}")
            continue
        seen.add(h)
        out.append(d)
    return out, notes


def field_indicators(defters: list[dict]) -> dict[str, dict]:
    by_v: dict[str, dict] = {}
    for d in defters:
        v = str(d.get("plugin_version") or "unknown")
        e = by_v.setdefault(v, {"defter": 0, "rates": [], "duzeltme": 0, "geri": 0, "takili": 0, "hata": 0, "son_tur_kaldi": 0,
                                "gun": 0, "kosu": 0, "asama_kosusu": {}})
        e["defter"] += 1
        e["gun"] += int(d.get("period_days", 0) or 0)  # 2.10.2: sürümler gözlem süresi ve iş miktarıyla eşitlenerek kıyaslanır
        for stg, s in (d.get("stages") or {}).items():
            k = int(s.get("completed", 0) or 0) + int(s.get("skipped", 0) or 0)
            e["kosu"] += k
            e["asama_kosusu"][stg] = e["asama_kosusu"].get(stg, 0) + k
        r = (d.get("draft_checks") or {}).get("pass_first_round_rate")
        if isinstance(r, (int, float)):
            e["rates"].append(float(r))
        for s in (d.get("stages") or {}).values():
            e["duzeltme"] += int(s.get("corrections", 0) or 0)
            e["geri"] += int(s.get("back_to", 0) or 0)
        e["takili"] += sum(int(x.get("open_runs", 0) or 0) for x in d.get("stuck") or [])
        e["hata"] += int((d.get("errors") or {}).get("count", 0) or 0)
        e["son_tur_kaldi"] += sum(int(b.get("final_round_fail", 0) or 0) for b in ((d.get("draft_checks") or {}).get("by_stage") or {}).values())
    for e in by_v.values():
        e["ilk_tur_orani"] = round(sum(e["rates"]) / len(e["rates"]), 2) if e["rates"] else None
        del e["rates"]
    return by_v


def signatures(defters: list[dict]) -> dict[tuple, dict]:
    agg: dict[tuple, dict] = {}
    for i, d in enumerate(defters):
        v = str(d.get("plugin_version") or "unknown")
        for s in d.get("imzalar") or []:
            k = (str(s.get("asama")), str(s.get("sinyal")), str(s.get("kod")), str(s.get("hucre")))
            e = agg.setdefault(k, {"n": 0, "defterler": set(), "by_version": {}})
            n = int(s.get("n", 0) or 0)
            e["n"] += n
            e["defterler"].add(i)
            e["by_version"][v] = e["by_version"].get(v, 0) + n
    return agg


def cell_sets(cell: str) -> tuple[set | None, set | None]:
    if cell in ("-", "", None) or "." not in cell:
        return None, None
    p, u = cell.split(".", 1)
    ps = PRODUCT_SETS.get(p, {p})
    us = USER_SETS.get(u, {u})
    return ps, us


def covering_cases(sig: tuple, cases: dict) -> list[str]:
    """Kapsayan vaka (2.10.2): imzanın bir hata kodu varsa vaka o kodu `kodlar` listesinde açıkça taşımalı; aynı aşama ve hücre tek
    başına kapsama değildir (yalnızca ilgili olabilir, bkz. related_cases). Kodsuz davranış sinyallerinde ("-") aşama ve hücre yeterlidir."""
    code = sig[2]
    rel = related_cases(sig, cases)
    if code in ("-", "", "None"):
        return rel
    return [n for n in rel if code in (cases[n].get("kodlar") or [])]


def related_cases(sig: tuple, cases: dict) -> list[str]:
    """Aynı aşama ve aynı ürün × kullanıcı hücresindeki vakalar: imzayla ilgili olabilir, onu yeniden ürettiği gösterilmedi."""
    stage, _signal, _code, cell = sig
    ps, us = cell_sets(cell)
    out = []
    for name, c in cases.items():
        if stage not in ("-", "QC") and not name.lower().startswith(stage.lower() + "-"):
            continue
        if ps is not None and c.get("product") not in ps:
            continue
        if us is not None and c.get("user") not in us:
            continue
        out.append(name)
    return out


def case_slug(sig: tuple) -> str:
    stage, signal, code, cell = sig
    raw = f"{stage}-{signal}-{code}-{cell}".lower()
    keep = "".join(ch if ch.isalnum() else "-" for ch in raw)
    while "--" in keep:
        keep = keep.replace("--", "-")
    return "saha-" + keep.strip("-")[:60]


def write_skeleton(root: Path, sig: tuple, matrix: dict) -> Path:
    stage, signal, code, cell = sig
    ps, us = cell_sets(cell)
    p = sorted(ps)[0] if ps else "P1"
    u = sorted(us)[0] if us else "U1"
    pa = (matrix.get("products", {}).get(p) or {}).get("ad", p)
    ua = (matrix.get("users", {}).get(u) or {}).get("ad", u)
    d = root / case_slug(sig)
    (d / "graders").mkdir(parents=True, exist_ok=True)
    (d / "prompt.md").write_text(
        "---\nmax_turns: 12\nallowed_tools: [Read, Glob, Grep, Skill]\n---\n\n"
        "Sen reklam-atolyesi plugin'i açık bir oturumdasın (plugin modu açık). Bu bir değerlendirme senaryosudur: ad-memory ya da Meta\n"
        "araçlarını ÇAĞIRMA ve kayıt yapma; gerekirse plugin'in skill'lerini ve `KURALLAR.md` dosyasını oku. Senaryodaki durumu araç\n"
        "sonuçlarıyla öğrenmiş gibi kabul et ve yalnızca kullanıcıya vereceğin cevabı Türkçe yaz.\n\n"
        f"Senaryo: {p} ({pa}) × {u} ({ua}).\n\n"
        f"Durum: DOLDUR — sahadan gelen imza: {stage} adımında {SIGNAL_TEXT.get(signal, signal)} (kod: {code}). Hatayı yeniden\n"
        "üretecek durumu yaz; vaka düzeltmeden ÖNCE kalmalı.\n\n"
        "Kullanıcı: \"DOLDUR\"\n", encoding="utf-8")
    (d / "graders" / "r1-kural-uyumu.md").write_text(
        "---\ntype: llm\nweight: 1\n---\n\nR1 Kural uyumu (evals/rubrik.md): cevap KURALLAR.md'deki değişmez kuralları çiğnemiyor.\n\n"
        "Geçer: DOLDUR. Kalır: DOLDUR.\n", encoding="utf-8")
    (d / "KAYNAK.md").write_text(
        f"Saha imzası: {stage} · {signal} · {code} · {cell}\n\nDoldurduktan sonra: klasörü evals/vakalar/ altına taşı, "
        f"senaryo-matrisi.json → eval_cases'e {{\"product\": \"{p}\", \"user\": \"{u}\", \"rubric\": [\"R1\"]}} ekle, bu dosyayı sil.\n",
        encoding="utf-8")
    return d


def _payda(ind_old: dict, ind_new: dict, stage: str) -> tuple[float, float, str]:
    """Sürüm kıyasının paydası (2.10.2). Ham sayı ya da defter sayısı farklı gözlem sürelerini ve farklı kullanım yoğunluğunu
    karşılaştırırdı. Sıra: aynı aşamanın tamamlanma sayısı → bütün aşamaların tamamlanma sayısı → gözlem günü → defter."""
    for a, b, ad in ((ind_old["asama_kosusu"].get(stage, 0), ind_new["asama_kosusu"].get(stage, 0), f"{stage} aşaması başına"),
                     (ind_old["kosu"], ind_new["kosu"], "aşama başına"),
                     (ind_old["gun"], ind_new["gun"], "gün başına")):
        if a and b:
            return float(a), float(b), ad
    return float(max(ind_old["defter"], 1)), float(max(ind_new["defter"], 1)), "defter başına (süre ve iş miktarı bilinmiyor)"


def version_changes(agg: dict, ind: dict) -> list[tuple]:
    vs = sorted(ind, key=vkey)
    if len(vs) < 2:
        return []
    old, new = vs[-2], vs[-1]
    out = []
    for k, e in agg.items():
        po, pn, birim = _payda(ind[old], ind[new], k[0])
        a = e["by_version"].get(old, 0) / po
        b = e["by_version"].get(new, 0) / pn
        if b > a * 1.5 and e["by_version"].get(new, 0) >= 2:
            out.append(("kötüleşti", k, a, b, birim))
        elif a > 0 and b < a * 0.5:
            out.append(("iyileşti", k, a, b, birim))
    out.sort(key=lambda x: (x[0] != "kötüleşti", -abs(x[3] - x[2])))
    return [(t, k, round(a, 2), round(b, 2), old, new, birim) for t, k, a, b, birim in out]


def render(defters, notes, esik, skel_root: Path | None) -> str:
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    cases = matrix.get("eval_cases") or {}
    ind = field_indicators(defters)
    agg = signatures(defters)
    L = ["# Hata defterleri: toplu okuma", "", f"Okunan defter: {len(defters)}.", ""]
    if notes:
        L += ["Notlar:"] + [f"- {n}" for n in notes] + [""]
    L += ["## 1. Sürüm başına saha göstergeleri", "",
          "| Sürüm | Defter | Taslağın ilk turda geçme oranı | Son turda da kalan taslak | Değişiklik isteği | Geri dönüş | Bekleyen adım | Araç hatası |",
          "|---|---|---|---|---|---|---|---|"]
    for v in sorted(ind, key=vkey):
        e = ind[v]
        L.append(f"| {v} | {e['defter']} | {e['ilk_tur_orani'] if e['ilk_tur_orani'] is not None else '-'} | {e['son_tur_kaldi']} | "
                 f"{e['duzeltme']} | {e['geri']} | {e['takili']} | {e['hata']} |")
    L += ["", "## 2. Tekrarlayan imzalar", ""]
    rows = sorted(agg.items(), key=lambda kv: (-len(kv[1]["defterler"]), -kv[1]["n"]))
    rec = [(k, e) for k, e in rows if len(e["defterler"]) >= esik or e["n"] >= max(3, esik)]
    if not any(d.get("imzalar") for d in defters):
        L.append("Defterlerde imza yok (2.8.0 öncesi sürümler imza taşımaz); yalnızca 1. tablo kullanılabilir.")
    elif not rec:
        L.append(f"Eşiği ({esik} defter ya da en az {max(3, esik)} kez) geçen imza yok.")
    else:
        L += ["| Adım | Ne oldu | Kod | Ürün × kullanıcı | Kaç kez | Kaç defterde | Kapsayan vaka |", "|---|---|---|---|---|---|---|"]
        skel_made = []
        for k, e in rec:
            cov = covering_cases(k, cases)
            rel = [n for n in related_cases(k, cases) if n not in cov]
            ilgili = f" (ilgili olabilir, hatayı ürettiği gösterilmedi: {', '.join(rel)})" if rel else ""
            cell = "—" if not cov else ", ".join(cov)
            if not cov and k[1] != "arac_hatasi":
                cell = "YOK" + ilgili
                if skel_root is not None:
                    skel_made.append(write_skeleton(skel_root, k, matrix))
            elif not cov:
                cell = "YOK (araç hatası: tests/ altında birim testiyle yeniden üret)" + ilgili
            L.append(f"| {k[0]} | {SIGNAL_TEXT.get(k[1], k[1])} | {k[2]} | {k[3]} | {e['n']} | {len(e['defterler'])} | {cell} |")
        if skel_made:
            L += ["", f"Vaka iskeleti yazıldı ({len(skel_made)}):"] + [f"- {p}" for p in skel_made]
    ch = version_changes(agg, ind)
    L += ["", "## 3. Sürüm karşılaştırması (aşama, gün ya da defter başına sıklık)", ""]
    if not ch:
        L.append("Karşılaştırılacak iki sürüm yok ya da belirgin değişiklik yok.")
    else:
        L += [f"| Sonuç | İmza | {ch[0][4]} | {ch[0][5]} | Ölçü |", "|---|---|---|---|---|"]
        for t, k, a, b, _o, _n, birim in ch:
            L.append(f"| {t} | {k[0]} · {SIGNAL_TEXT.get(k[1], k[1])} · {k[2]} · {k[3]} | {a} | {b} | {birim} |")
    L += ["", "Sıradaki adım: kapsanmayan imzalar için vaka yaz (önce kalmalı), düzelt, eski vakaların bozulmadığını kör",
          "karşılaştırmayla göster, sonucu evals/etki-defteri.md'ye yaz.", ""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Hata defterlerini toplu okur (admin).")
    ap.add_argument("yollar", nargs="+", help="defter dosyaları ya da klasörleri")
    ap.add_argument("--out", help="raporu bu dosyaya yaz (yoksa ekrana)")
    ap.add_argument("--esik", type=int, default=2, help="tekrarlayan sayılmak için en az kaç defterde görülmeli (varsayılan 2)")
    ap.add_argument("--iskelet", help="kapsanmayan imzalar için vaka iskeletini bu klasöre yaz (evals/ dışında olmalı)")
    a = ap.parse_args(argv)
    skel = None
    if a.iskelet:
        skel = Path(a.iskelet).resolve()
        if HERE in skel.parents or skel == HERE:
            print("--iskelet evals/ dışında olmalı (claude plugin eval evals/ altındaki her prompt.md'yi çalıştırır).", file=sys.stderr)
            return 2
    defters, notes = load_defters(a.yollar)
    if not defters:
        print("Okunacak hata defteri bulunamadı.", file=sys.stderr)
        return 1
    text = render(defters, notes, max(1, a.esik), skel)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(a.out)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
