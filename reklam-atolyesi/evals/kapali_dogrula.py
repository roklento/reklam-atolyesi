#!/usr/bin/env python3
"""Kapalı vakaların biçimini ve çalışırlığını içeriğini göstermeden denetler (2.10.15, admin tarafı; ücretsiz).

Neden: kapalı vakaları bu projede düzeltme yazan oturumlar görmemelidir. Vakaları başka biri yazar; yönetici de onları açmadan
"bunlar yayın testinde çalışır mı?" sorusuna cevap ister. Bu betik vaka metnini hiçbir zaman yazdırmaz. Yalnızca "geçerli" der ya da
hangi vakanın hangi dosyasında hangi alanın eksik ya da yanlış olduğunu söyler. Vaka adları da varsayılan olarak "vaka 1, vaka 2"
diye gizlenir (adlar senaryoyu ele verebilir); kendi bilgisayarında adları görmek isteyen `--adlarla` verir.

Denetlenenler (her biri yayın testinde ya da depo testlerinde bir yeri bozar):
  - kapali-matris.json: {"kapali_cases": {ad: {"product", "user", "rubric"}}}; ürün ve kullanıcı senaryo matrisinde var, rubrik
    kodları rubrik.md'de var, vaka başına 2 ya da 3 ölçüt; açık bir vakayla aynı ad ya da aynı ürün × kullanıcı hücresi yok;
    kapalı vakalar arasında aynı hücre yok; en az 3 vaka ve en az biri hiçbir açık vakada olmayan bir kullanıcıyı sınar.
  - Klasörler kayıtla birebir aynı; `claude plugin eval` her prompt.md'yi vaka saydığı için iç içe ya da fazla prompt.md yok.
  - prompt.md: UTF-8 (BOM'suz); ön bilgi yalnızca max_turns (1–30) ve allowed_tools (Read, Glob, Grep, Skill içinden);
    gövdede kayıttaki hücreyi matristeki adlarıyla veren "Senaryo:" satırı, "Durum:" ve "Kullanıcı:" satırları.
  - graders/r<N>-<ad>.md: ön bilgi yalnızca `type: llm` ve pozitif `weight`; gövde kendi R kodunu açıklayan cümleyle başlar ve
    "Geçer:" ile "Kalır:" tariflerini taşır; kayıttaki her ölçütün bir dosyası var, kayıtta olmayan ölçüt dosyası yok.
  - Ezber: vaka metni plugin metniyle (ezber denetiminin izlediği dosyalar) 6 kelimelik ortak parça taşımaz, vaka adı plugin
    metninde geçmez; açık vakalardan (hepsinde ortak olan giriş kalıbı dışında) 6 kelimelik kopya yoktur.
  - Çalışırlık: kor_kiyas.py vakaları bulur, hakem metnini kurar, beklenen vaka setine katar.

Kullanım:
    python evals/kapali_dogrula.py                       # evals/kapali/ (yayın öncesi kopya)
    python evals/kapali_dogrula.py --dizin <klasör>      # başka bir klasördeki kapalı vakalar
    python evals/kapali_dogrula.py --adlarla             # sorunlarda vaka adını göster (yalnızca kendi bilgisayarında)
Çıkış kodu: 0 = geçerli (uyarılar olabilir), 1 = sorun var, 2 = klasör ya da kayıt okunamadı.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import ezber_denetimi as EZ  # noqa: E402
import kor_kiyas as KK  # noqa: E402

KAYIT = "kapali-matris.json"
ARACLAR = {"Read", "Glob", "Grep", "Skill"}
PROMPT_ANAHTAR = {"max_turns", "allowed_tools"}
HAKEM_ANAHTAR = {"type", "weight"}
VAKA_ANAHTAR = {"product", "user", "rubric"}
AD = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")
HAKEM_AD = re.compile(r"^r(\d+)-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
EN_AZ_VAKA = 3
ONERILEN_VAKA = 5
PROMPT_SINIR = 4000
HAKEM_SINIR = 1500


def _front(text: str) -> tuple[dict | None, str]:
    """Basit ön bilgi okuyucu: `anahtar: değer` satırları. Ön bilgi yoksa (None, metin)."""
    m = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", text, re.S)
    if not m:
        return None, text
    out: dict = {}
    for ln in m.group(1).splitlines():
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        k, sep, v = ln.partition(":")
        out[k.strip()] = v.strip() if sep else None
    return out, text[m.end():]


def _metin(f: Path, sorun: list[str], etiket: str) -> str | None:
    raw = f.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        sorun.append(f"{etiket}: dosya BOM ile başlıyor; BOM'suz UTF-8 kaydedin")
        raw = raw[3:]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        sorun.append(f"{etiket}: UTF-8 değil")
        return None


def _gramlar(metin: str) -> set[tuple]:
    w = EZ.words(metin)
    return {tuple(w[i:i + EZ.KELIME_ESIGI]) for i in range(len(w) - EZ.KELIME_ESIGI + 1)}


def _sablon_disi(metin: str) -> str:
    """Matristen ve rubrikten gelen kalıp satırları (Senaryo satırı, ölçüt başlığı) açık vaka kopyası sayılmaz."""
    return "\n".join(ln for ln in metin.splitlines() if not re.match(r"\s*(Senaryo:|R\d+\b)", ln))


def _acik_vaka_gramlari() -> tuple[dict[tuple, set[str]], set[tuple]]:
    """{6-kelime: hangi açık vakalarda} ve ortak kalıp (iki ya da daha çok açık vakada geçen parça: giriş metni, ölçüt başlığı)."""
    sahip: dict[tuple, set[str]] = {}
    base = HERE / "vakalar"
    for d in sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []:
        for f in [d / "prompt.md", *sorted((d / "graders").glob("*.md"))]:
            if f.exists():
                for g in _gramlar(_sablon_disi(_front(f.read_text(encoding="utf-8"))[1])):
                    sahip.setdefault(g, set()).add(d.name)
    ortak = {g for g, s in sahip.items() if len(s) >= 2}
    return sahip, ortak


def _plugin_gramlari() -> set[tuple]:
    """Ezber denetiminin izlediği plugin metni (KURALLAR, skill'ler, ajanlar, komutlar, hook'lar, şablonlar). Satır sonunda bölünen
    cümleler için ardışık satırlar birlikte alınır (ezber_denetimi.find ile aynı)."""
    out: set[tuple] = set()
    satirlar = EZ.all_lines()
    for i, (yol, no, metin) in enumerate(satirlar):
        sonraki = satirlar[i + 1] if i + 1 < len(satirlar) and satirlar[i + 1][0] == yol else None
        out |= _gramlar(metin + (" " + sonraki[2] if sonraki else ""))
    return out


def _plugin_metni_kucuk() -> list[str]:
    return [EZ.tr_lower(t) for _, _, t in EZ.all_lines()]


def denetle(dizin: Path, adlarla: bool = False) -> tuple[list[str], list[str], dict]:
    """(sorunlar, uyarılar, özet). Hiçbir mesaj vaka metninden parça taşımaz."""
    sorun: list[str] = []
    uyari: list[str] = []
    matris = json.loads((HERE / "senaryo-matrisi.json").read_text(encoding="utf-8"))
    urunler, kullanicilar = matris["products"], matris["users"]
    acik = matris.get("eval_cases") or {}
    acik_hucre = {(c["product"], c["user"]) for c in acik.values()}
    acik_kullanici = {c["user"] for c in acik.values()}
    kodlar = set(re.findall(r"^## (R\d+)\b", (HERE / "rubrik.md").read_text(encoding="utf-8"), re.M))

    if not dizin.is_dir():
        raise FileNotFoundError(f"klasör yok: {dizin}")
    kf = dizin / KAYIT
    if not kf.exists():
        raise FileNotFoundError(f"{KAYIT} yok ({dizin} içinde)")
    try:
        kayit = json.loads(kf.read_text(encoding="utf-8-sig"))
    except ValueError as e:
        raise FileNotFoundError(f"{KAYIT} geçerli JSON değil (satır {getattr(e, 'lineno', '?')})") from None
    if (kf.read_bytes()[:3] == b"\xef\xbb\xbf"):
        sorun.append(f"{KAYIT}: dosya BOM ile başlıyor; BOM'suz UTF-8 kaydedin")
    if not isinstance(kayit, dict) or set(kayit) != {"kapali_cases"} or not isinstance(kayit.get("kapali_cases"), dict):
        sorun.append(f"{KAYIT}: tek anahtar \"kapali_cases\" olmalı ve değeri {{vaka adı: kayıt}} sözlüğü olmalı")
        return sorun, uyari, {}
    vakalar: dict = kayit["kapali_cases"]
    adlar = sorted(vakalar)
    takma = {ad: (ad if adlarla else f"vaka {i}") for i, ad in enumerate(adlar, 1)}

    # ---------- kayıt ----------
    if len(vakalar) < EN_AZ_VAKA:
        sorun.append(f"{KAYIT}: {len(vakalar)} vaka var; en az {EN_AZ_VAKA} olmalı")
    elif len(vakalar) < ONERILEN_VAKA:
        uyari.append(f"{len(vakalar)} vaka var; senaryo matrisini kapsamak için en az {ONERILEN_VAKA} önerilir")
    hucreler: dict[tuple, list[str]] = {}
    for ad in adlar:
        v, t = vakalar[ad], takma[ad]
        if not AD.match(ad):
            sorun.append(f"{t}: vaka adı küçük harf, rakam ve tireyle en az iki parçadan oluşmalı (ör. kelime-kelime)")
        if ad in acik:
            sorun.append(f"{t}: bu ad açık vakalarda da var")
        if not isinstance(v, dict):
            sorun.append(f"{t}: kayıt bir sözlük olmalı ({sorted(VAKA_ANAHTAR)})")
            continue
        eksik, fazla = VAKA_ANAHTAR - set(v), set(v) - VAKA_ANAHTAR
        if eksik:
            sorun.append(f"{t}: {KAYIT} kaydında alan eksik: {', '.join(sorted(eksik))}")
        if fazla:
            sorun.append(f"{t}: {KAYIT} kaydında beklenmeyen alan: {', '.join(sorted(fazla))} (yalnızca product, user, rubric;"
                         " kapalı vaka plugin cümlesi alıntılamaz, \"alinti\" kullanılmaz)")
        p, u, r = v.get("product"), v.get("user"), v.get("rubric")
        if p not in urunler:
            sorun.append(f"{t}: product senaryo matrisinde yok ({sorted(urunler)} içinden biri olmalı)")
        if u not in kullanicilar:
            sorun.append(f"{t}: user senaryo matrisinde yok ({sorted(kullanicilar)} içinden biri olmalı)")
        if (p, u) in acik_hucre:
            sorun.append(f"{t}: bu ürün × kullanıcı hücresi bir açık vakada zaten var; açık vakalarda olmayan bir hücre seçin")
        hucreler.setdefault((p, u), []).append(t)
        if not isinstance(r, list) or not all(isinstance(x, str) for x in r):
            sorun.append(f"{t}: rubric bir kod listesi olmalı (ör. [\"R1\", \"R4\"])")
        else:
            if set(r) - kodlar:
                sorun.append(f"{t}: rubric'te rubrik.md'de olmayan kod var ({sorted(kodlar)} içinden seçin)")
            if len(set(r)) != len(r):
                sorun.append(f"{t}: rubric'te aynı kod iki kez var")
            if not 2 <= len(set(r)) <= 3:
                sorun.append(f"{t}: rubric'te {len(set(r))} ölçüt var; her vaka 2 ya da 3 ölçüt kullanır (rubrik.md)")
    for (p, u), ts in hucreler.items():
        if len(ts) > 1 and p in urunler and u in kullanicilar:
            sorun.append(f"{', '.join(ts)}: kapalı vakalar aynı ürün × kullanıcı hücresini kullanıyor; her vaka ayrı hücre olmalı")
    gecerli = [v for v in vakalar.values() if isinstance(v, dict)]
    if gecerli and not ({v.get("user") for v in gecerli} - acik_kullanici):
        sorun.append("en az bir kapalı vaka, hiçbir açık vakada olmayan bir kullanıcı profilini sınamalı")
    urun_say = len({v.get("product") for v in gecerli})
    kul_say = len({v.get("user") for v in gecerli})
    if gecerli and len(gecerli) >= ONERILEN_VAKA and (urun_say < ONERILEN_VAKA or kul_say < ONERILEN_VAKA):
        uyari.append(f"vakalar {urun_say} farklı ürün türü ve {kul_say} farklı kullanıcı kullanıyor; en az {ONERILEN_VAKA}'er "
                     "farklı olması önerilir")

    # ---------- klasörler ----------
    klasorler = {p.name for p in dizin.iterdir() if p.is_dir() and not p.name.startswith(".")}
    for ad in sorted(klasorler - set(vakalar)):
        sorun.append(f"kayıtta olmayan bir vaka klasörü var ({ad if adlarla else 'adı gizli'}); ya kaydedin ya kaldırın")
    for ad in adlar:
        if ad not in klasorler:
            sorun.append(f"{takma[ad]}: kayıtta var ama klasörü yok")
    for f in sorted(p for p in dizin.iterdir() if p.is_file() and not p.name.startswith(".")):
        if f.name != KAYIT:
            uyari.append(f"kök klasörde vaka olmayan bir dosya var ({f.name}); yayın testi onu okumaz, kaldırılabilir")
    for f in sorted(dizin.rglob("*")):
        rel = f.relative_to(dizin).parts
        if any(x.startswith(".") for x in rel) or not f.is_file():
            continue
        if f.name in ("case.yaml", "case.yml"):
            sorun.append(f"{takma.get(rel[0], 'kök')}: case.yaml var; bu sette vakalar yalnızca prompt.md ve graders/ ile yazılır")
        if f.name == "prompt.md" and len(rel) != 2:
            sorun.append(f"{takma.get(rel[0], 'kök')}: vaka klasörünün içinde ikinci bir prompt.md var; yayın testi onu ayrı vaka sayar")

    # ---------- dosyalar ----------
    acik_sahip, ortak = _acik_vaka_gramlari()
    plugin_g = _plugin_gramlari()
    plugin_kucuk = _plugin_metni_kucuk()
    hakem_sayisi = 0
    for ad in adlar:
        v, t, d = vakalar[ad], takma[ad], dizin / ad
        if not d.is_dir() or not isinstance(v, dict):
            continue
        govdeler: list[str] = []
        pf = d / "prompt.md"
        if not pf.exists():
            sorun.append(f"{t}: prompt.md yok")
        else:
            tx = _metin(pf, sorun, f"{t} · prompt.md")
            if tx is not None:
                fm, govde = _front(tx)
                govdeler.append(govde)
                if fm is None:
                    sorun.append(f"{t} · prompt.md: dosya --- ile açılıp kapanan ön bilgiyle başlamalı (max_turns, allowed_tools)")
                else:
                    for k in sorted(PROMPT_ANAHTAR - set(fm)):
                        sorun.append(f"{t} · prompt.md: ön bilgide alan eksik: {k}")
                    for k in sorted(set(fm) - PROMPT_ANAHTAR):
                        sorun.append(f"{t} · prompt.md: ön bilgide beklenmeyen alan: {k} (koşu sayısı ve diğer ayarlar "
                                     "komut satırından verilir)")
                    mt = fm.get("max_turns")
                    if "max_turns" in fm and not (mt and mt.isdigit() and 1 <= int(mt) <= 30):
                        sorun.append(f"{t} · prompt.md: max_turns 1 ile 30 arasında bir tam sayı olmalı")
                    at = fm.get("allowed_tools")
                    if "allowed_tools" in fm:
                        m = re.fullmatch(r"\[(.*)\]", at or "")
                        araclar = [x.strip().strip("\"'") for x in m.group(1).split(",")] if m else []
                        if not m or not araclar or not all(araclar):
                            sorun.append(f"{t} · prompt.md: allowed_tools [Read, Glob, Grep, Skill] biçiminde bir liste olmalı")
                        elif set(araclar) - ARACLAR:
                            sorun.append(f"{t} · prompt.md: allowed_tools yalnızca Read, Glob, Grep, Skill içerebilir "
                                         "(vakalar araç çağırmaz, dosya yazmaz)")
                satirlar = [ln.strip() for ln in govde.splitlines()]
                p, u = v.get("product"), v.get("user")
                if p in urunler and u in kullanicilar:
                    bekl = f"Senaryo: {p} ({urunler[p]['ad']}) × {u} ({kullanicilar[u]['ad']})."
                    if not any(ln.startswith("Senaryo:") for ln in satirlar):
                        sorun.append(f"{t} · prompt.md: \"Senaryo:\" satırı yok")
                    elif bekl not in satirlar:
                        sorun.append(f"{t} · prompt.md: \"Senaryo:\" satırı kayıttaki hücreyle tutmuyor; satır tam olarak "
                                     "\"Senaryo: <ürün kodu> (<matristeki ürün adı>) × <kullanıcı kodu> (<matristeki kullanıcı "
                                     "adı>).\" olmalı")
                for etiket in ("Durum:", "Kullanıcı:"):
                    if not any(ln.startswith(etiket) for ln in satirlar):
                        sorun.append(f"{t} · prompt.md: \"{etiket}\" ile başlayan satır yok")
                if len(govde) > PROMPT_SINIR:
                    sorun.append(f"{t} · prompt.md: gövde {len(govde)} karakter; en fazla {PROMPT_SINIR}")
        gd = d / "graders"
        hakemler = sorted(gd.glob("*.md")) if gd.is_dir() else []
        if not hakemler:
            sorun.append(f"{t}: graders/ klasöründe ölçüt dosyası yok")
        bulunan: set[str] = set()
        for i, g in enumerate(hakemler, 1):
            hakem_sayisi += 1
            et = f"{t} · {g.name if adlarla else f'{i}. ölçüt dosyası'}"
            m = HAKEM_AD.match(g.name)
            if not m:
                sorun.append(f"{et}: dosya adı r<N>-<ad>.md biçiminde olmalı (ör. r1-kural-uyumu.md)")
            tx = _metin(g, sorun, et)
            if tx is None:
                continue
            fm, govde = _front(tx)
            govdeler.append(govde)
            if fm is None:
                sorun.append(f"{et}: dosya --- ile açılıp kapanan ön bilgiyle başlamalı (type: llm, weight)")
            else:
                for k in sorted(HAKEM_ANAHTAR - set(fm)):
                    sorun.append(f"{et}: ön bilgide alan eksik: {k}")
                for k in sorted(set(fm) - HAKEM_ANAHTAR):
                    sorun.append(f"{et}: ön bilgide beklenmeyen alan: {k}")
                if "type" in fm and fm["type"] != "llm":
                    sorun.append(f"{et}: type llm olmalı")
                if "weight" in fm:
                    try:
                        ok = float(fm["weight"]) > 0
                    except (TypeError, ValueError):
                        ok = False
                    if not ok:
                        sorun.append(f"{et}: weight pozitif bir sayı olmalı")
            ilk = next((ln.strip() for ln in govde.splitlines() if ln.strip()), "")
            km = re.match(r"(R\d+)\b", ilk)
            if not km:
                sorun.append(f"{et}: gövde ölçüt koduyla başlamalı (ör. \"R1 Kural uyumu (evals/rubrik.md): …\")")
            else:
                bulunan.add(km.group(1))
                if m and f"R{m.group(1)}" != km.group(1):
                    sorun.append(f"{et}: dosya adındaki numara gövdedeki ölçüt koduyla aynı değil")
                if km.group(1) not in kodlar:
                    sorun.append(f"{et}: ölçüt kodu rubrik.md'de yok")
            for etiket in ("Geçer:", "Kalır:"):
                if etiket not in govde:
                    sorun.append(f"{et}: \"{etiket}\" tarifi yok; her ölçüt neyin geçip neyin kaldığını ayrı ayrı yazar")
            if len(govde) > HAKEM_SINIR:
                sorun.append(f"{et}: gövde {len(govde)} karakter; en fazla {HAKEM_SINIR}")
        r = v.get("rubric") if isinstance(v.get("rubric"), list) else []
        for k in sorted(set(r) - bulunan):
            sorun.append(f"{t}: kayıttaki {k} ölçütünün graders/ altında dosyası yok")
        for k in sorted(bulunan - set(r)):
            sorun.append(f"{t}: graders/ altında kayıtta olmayan bir ölçüt dosyası var ({k}); kayda ekleyin ya da dosyayı kaldırın")

        # ---------- ezber ----------
        gram = set().union(*(_gramlar(x) for x in govdeler)) if govdeler else set()
        n_plugin = len(gram & plugin_g)
        if n_plugin:
            sorun.append(f"{t}: plugin metniyle {n_plugin} tane 6 kelimelik ortak parça var; vaka plugin cümlesini alıntılamaz, "
                         "kendi sözleriyle yazılır (ezber denetimi ve depo testleri bunu yakalar)")
        rx = re.compile(r"(?<![\w-])" + re.escape(ad) + r"(?![\w-])", re.I)
        if any(rx.search(x) for x in plugin_kucuk):
            sorun.append(f"{t}: vaka adı plugin metninde geçiyor; daha ayırt edici bir ad seçin")
        kopya = {g for x in govdeler for g in _gramlar(_sablon_disi(x)) if g in acik_sahip and g not in ortak}
        if kopya:
            sorun.append(f"{t}: açık vakalardan {len(kopya)} tane 6 kelimelik kopya parça var; kapalı vaka açık vakaların "
                         "cümlelerinden bağımsız yazılır (yalnızca bütün vakalarda ortak giriş metni serbesttir)")

    # ---------- çalışırlık (kor_kiyas.py) ----------
    eski = KK.KAPALI
    try:
        KK.KAPALI = dizin
        kk = KK.kapali_matrix(dizin)
        if set(kk) != set(vakalar):
            sorun.append("kor_kiyas.py kayıttaki vakaları tam okuyamadı")
        for ad in adlar:
            if (dizin / ad / "prompt.md").exists() and KK.case_dir(ad) != dizin / ad:
                sorun.append(f"{takma[ad]}: kor_kiyas.py bu vakayı kapalı klasörde bulamıyor (aynı adda açık vaka var)")
            elif (dizin / ad / "prompt.md").exists() and "Durum:" not in KK.judge_prompt(ad, "a", "b"):
                sorun.append(f"{takma[ad]}: kor_kiyas.py hakem metnini bu vakadan kuramadı")
    finally:
        KK.KAPALI = eski
    ozet = {"vaka": len(vakalar), "hakem": hakem_sayisi, "urun": urun_say, "kullanici": kul_say}
    return sorun, uyari, ozet


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Kapalı vakaların biçimini içeriğini göstermeden denetler (admin).")
    ap.add_argument("--dizin", default=str(KK.KAPALI), help="kapalı vaka klasörü (varsayılan: evals/kapali)")
    ap.add_argument("--adlarla", action="store_true", help="sorunlarda vaka ve dosya adlarını göster (yalnızca kendi bilgisayarında)")
    a = ap.parse_args(argv)
    try:
        sorun, uyari, ozet = denetle(Path(a.dizin).resolve(), a.adlarla)
    except FileNotFoundError as e:
        print(f"Kapalı vaka denetimi yapılamadı: {e}.")
        return 2
    if not sorun:
        print(f"Kapalı vakalar GEÇERLİ: {ozet['vaka']} vaka, {ozet['hakem']} ölçüt dosyası, {ozet['urun']} farklı ürün türü, "
              f"{ozet['kullanici']} farklı kullanıcı.")
    else:
        print(f"Kapalı vakalar GEÇERSİZ: {len(sorun)} sorun.")
        for s in sorun:
            print(f"  - {s}")
    for u in uyari:
        print(f"  Uyarı: {u}")
    return 1 if sorun else 0


if __name__ == "__main__":
    raise SystemExit(main())
