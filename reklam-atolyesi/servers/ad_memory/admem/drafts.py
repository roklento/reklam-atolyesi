"""Metin aşamalarının taslak denetimi (2.5.0): kullanıcıya giden belge önce bu ölçütten geçer.

Kural (KURALLAR.md K10): metin aşamasının belgesi `draft_check` ile denetlenir; kritik sorun varsa düzeltilip yeniden denetlenir.
En fazla MAX_DRAFT_ROUNDS tur; turu sunucu sayar (değişmemiş dosyanın yeniden denetimi yeni tur sayılmaz). Tur sınırı dolunca kalan
sorunlar kullanıcıya açıkça söylenir ve karar insanındır. Kod yalnızca ölçülebilir olanı denetler (eksik bölüm, doldurulmamış alan,
veritabanıyla çelişen sayı, zorunlu uyarının yokluğu); dilin sadeliği ve ikna gücü değerlendirme setindeki (evals/) LLM rubriğinin işidir.

Bu modül saf fonksiyonlardır: veritabanı bağlamı (ctx) s_draft.DraftMixin tarafından kurulur.
"""
from __future__ import annotations

import re
import unicodedata

DRAFT_STAGES = ("S00a", "S00c", "S01", "S01b", "S02", "S03", "S04", "S14", "S16", "S17")
MAX_DRAFT_ROUNDS = 2
DRAFT_SUFFIXES = (".md",)

# Şablonlu aşamalar: (şablon dosyası, aşamanın belge adı kalıbı). Kalıba uyan .md dosyası şablon bölümleriyle de denetlenir.
TEMPLATES = {
    "S01": ("brief.md", r"(^|[\\/])c\d+-brief\.md$"),
    "S01b": ("rakip-analizi.md", r"(^|[\\/])c\d+-rakip-analizi\.md$"),
    "S02": ("strategy.md", r"(^|[\\/])c\d+-strategy\.md$"),
    "S04": ("cekim-rehberi.md", r"(^|[\\/])c\d+-cekim-rehberi\.md$"),
    "S14": ("yayin-paketi.md", r"(^|[\\/])c\d+-yayin-paketi\.md$"),
}
# Boş kalabilen bölümler (o aşamada henüz doldurulamayan ya da duruma bağlı olan); başlık yoksa yalnızca uyarı.
OPTIONAL_SECTIONS = {
    "S01": {"rakip bağlamı"},                      # S01b'den sonra doldurulur
    "S01b": {"fark"},                              # ilk görüntüde önceki yok
    "S02": {"reddedilen konumlandırmalar"},
    "S04": {"ses", "üretilecek efektlerin başlangıç listesi"},
    "S14": {"ai açıklaması"},                      # AI içeren kreatif varsa aşağıda ayrıca zorunlu
}

RESULT_LABELS = {
    "purchase": ("purchase", "satış", "satın alma"),
    "lead": ("lead", "müşteri adayı", "potansiyel müşteri"),
    "messaging": ("messaging", "mesaj"),
    "profile_visit": ("profile_visit", "profil ziyareti"),
    "link_click": ("link_click", "bağlantı tıklaması", "link tıklaması"),
    "engagement": ("engagement", "etkileşim"),
}
LEAD_METHOD_LABELS = {
    "instant_form": ("instant_form", "anlık form"),
    "website": ("website", "sitedeki form", "web sitesi", "site formu", "sitede form"),
    "call": ("call", "arama", "telefon"),
}
NULL_WORDS = ("null", "sınır yok", "sınır tanımlanmadı", "tanımlanmadı", "tanımlamadı", "sınırsız", "yok")

PLACEHOLDER = re.compile(r"\{\{.*?\}\}", re.S)
TODO = re.compile(r"\b(TODO|TBD|FIXME|XXX)\b|lorem ipsum", re.I)
# UTF-8 metnin Latin-1/CP1252 diye okunup yeniden yazılması (Windows'ta sık): "Ã§", "Ä±", "ÅŸ", "â€™"
MOJIBAKE = re.compile(r"Ã[\u0080-\u00bf§¶¼½¾]|Ä[±°Ÿž\u009f\u009e]|Å[Ÿž\u009f\u009e]|â€")
CURRENCY_AMOUNT = re.compile(r"(?:₺|\$|€)\s?\d[\d.,]*|\d[\d.,]*\s?(?:TL|₺|TRY|USD|EUR|€|\$)", re.I)


def fold(s: str) -> str:
    """Türkçe büyük/küçük harf duyarsız karşılaştırma için."""
    s = unicodedata.normalize("NFC", s or "")
    return s.replace("I", "ı").replace("İ", "i").lower()


def _strip_parens(s: str) -> str:
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"\([^()]*\)", "", s)
    return s


def norm_heading(h: str) -> str:
    h = PLACEHOLDER.sub("", h)
    h = _strip_parens(h)
    h = re.sub(r"[`*_#>:—–\-·.,;!?✅]", " ", fold(h))
    return re.sub(r"\s+", " ", h).strip()


def numbers_in(text: str) -> set[float]:
    """Metindeki sayılar; Türkçe (1.500,50) ve İngilizce (1,500.50 / 1500.5) yazımın ikisi de aday değer olarak döner."""
    out: set[float] = set()
    for tok in re.findall(r"(?<![\w.,])\d[\d.,]*", text or ""):
        tok = tok.rstrip(".,")
        if not tok:
            continue
        cands = set()
        if re.fullmatch(r"\d+", tok):
            cands.add(tok)
        else:
            # Türkçe: nokta binlik, virgül ondalık
            if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?|\d+,\d+", tok):
                cands.add(tok.replace(".", "").replace(",", "."))
            # İngilizce: virgül binlik, nokta ondalık
            if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?|\d+\.\d+", tok):
                cands.add(tok.replace(",", ""))
        for c in cands:
            try:
                out.add(float(c))
            except ValueError:
                pass
    return out


def has_number(text: str, value: float | int | None, tol: float = 0.011) -> bool:
    if value is None:
        return False
    v = float(value)
    return any(abs(n - v) <= max(tol, abs(v) * 1e-6) for n in numbers_in(text))


def parse_sections(md: str) -> list[dict]:
    """'## ' ve '### ' başlıklarına göre bölümler: [{level, title, norm, body}]. '# ' başlık ayrı tutulur (level 1)."""
    secs: list[dict] = []
    cur = {"level": 0, "title": "", "norm": "", "lines": []}
    in_code = False
    for line in (md or "").splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
        m = None if in_code else re.match(r"^(#{1,3})\s+(.*)$", line)
        if m:
            secs.append(cur)
            cur = {"level": len(m.group(1)), "title": m.group(2).strip(), "norm": norm_heading(m.group(2)), "lines": []}
        else:
            cur["lines"].append(line)
    secs.append(cur)
    for s in secs:
        s["body"] = "\n".join(s.pop("lines")).strip()
    return secs


def template_headings(template_md: str) -> list[str]:
    return [s["title"] for s in parse_sections(template_md) if s["level"] == 2]


def _find(secs: list[dict], heading: str) -> dict | None:
    """Şablon başlığına karşılık gelen bölüm (parantezler ve alan işaretleri atılarak; önek eşleşmesi kabul)."""
    key = norm_heading(heading)
    if not key:
        return None
    for s in secs:
        if s["level"] >= 2 and (s["norm"] == key or s["norm"].startswith(key) or (len(s["norm"]) >= 8 and key.startswith(s["norm"]))):
            return s
    return None


def section_text(secs: list[dict], heading: str, include_sub: bool = True) -> str | None:
    """Bölümün gövdesi; include_sub ise alt başlıkları (###) da içerir."""
    key = norm_heading(heading)
    for i, s in enumerate(secs):
        if s["level"] >= 2 and (s["norm"] == key or s["norm"].startswith(key)):
            parts = [s["body"]]
            if include_sub:
                for t in secs[i + 1:]:
                    if t["level"] <= s["level"]:
                        break
                    parts.append(t["title"] + "\n" + t["body"])
            return "\n".join(parts).strip()
    return None


def row_value(text: str, label: str) -> str | None:
    """Etiketin geçtiği satırın değer kısmı: tablo satırında etiket hücresinden sonraki hücreler, liste satırında ':' sonrası."""
    line = _line_with(text, label)
    if line is None:
        return None
    if line.strip().startswith("|"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        f = fold(label)
        for i, c in enumerate(cells):
            if f in fold(c):
                return " | ".join(cells[i + 1:])
        return " | ".join(cells[1:])
    return line.split(":", 1)[1] if ":" in line else line


def _line_with(text: str, label: str) -> str | None:
    f = fold(label)
    for line in (text or "").splitlines():
        if f in fold(line):
            return line
    return None


def table_rows(text: str) -> list[list[str]]:
    """Markdown tablosunun veri satırları (başlık ve ayraç hariç); bütün hücreleri boş satır sayılmaz."""
    rows = [ln.strip() for ln in (text or "").splitlines() if ln.strip().startswith("|")]
    out = []
    for i, r in enumerate(rows):
        cells = [c.strip() for c in r.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c or "") for c in cells if c) and any(cells):
            continue  # ayraç
        if i == 0:
            continue  # başlık
        if not any(cells):
            continue
        out.append(cells)
    return out


def _meaningful(body: str) -> bool:
    t = re.sub(r"^\s*>.*$", "", body or "", flags=re.M)        # alıntı/şablon notu tek başına içerik değildir
    t = re.sub(r"^\s*\|?[\s:\-|]*\|?\s*$", "", t, flags=re.M)  # boş tablo iskeleti
    t = re.sub(r"[\s\-*•|]", "", t)
    return len(t) >= 2


def _issue(code: str, severity: str, message: str, section: str | None = None) -> dict:
    d = {"code": code, "severity": severity, "message": message}
    if section:
        d["section"] = section
    return d


def generic_checks(text: str) -> list[dict]:
    issues: list[dict] = []
    visible = re.sub(r"\s+", "", re.sub(r"[#>*|`\-]", "", text or ""))
    if len(visible) < 20:
        issues.append(_issue("doc_too_short", "critical", "belge neredeyse boş (anlamlı içerik yok)"))
    ph = PLACEHOLDER.findall(text or "")
    if ph:
        sample = ", ".join(sorted({p[:40] for p in ph})[:5])
        issues.append(_issue("placeholder", "critical", f"doldurulmamış şablon alanı kaldı ({len(ph)}): {sample}"))
    if TODO.search(text or ""):
        issues.append(_issue("todo", "critical", "TODO/TBD/lorem gibi taslak işareti kaldı"))
    if MOJIBAKE.search(text or ""):
        issues.append(_issue("encoding", "critical",
                             "Türkçe karakterler bozuk görünüyor (ör. 'Ã§', 'Ä±'): dosya UTF-8 olarak yeniden yazılmalı"))
    if "\ufffd" in (text or ""):
        issues.append(_issue("encoding", "critical", "dosyada okunamayan karakter (�) var"))
    return issues


def template_checks(text: str, template_md: str, stage: str) -> list[dict]:
    issues: list[dict] = []
    secs = parse_sections(text)
    optional = OPTIONAL_SECTIONS.get(stage, set())
    for h in template_headings(template_md):
        key = norm_heading(h)
        is_opt = any(key.startswith(o) for o in optional)
        s = _find(secs, h)
        if s is None:
            issues.append(_issue("missing_section", "warn" if is_opt else "critical", f"şablondaki bölüm yok: «{_strip_parens(h).strip()}»"))
            continue
        body = section_text(secs, s["title"]) or ""
        if not is_opt and not _meaningful(body):
            issues.append(_issue("empty_section", "critical", f"bölüm boş: «{s['title']}»", s["title"]))
        tlines = [ln for ln in body.splitlines() if ln.strip().startswith("|")]
        if len(tlines) >= 2 and not table_rows(body) and not is_opt:
            issues.append(_issue("empty_table", "critical", f"tablo yalnızca başlıktan oluşuyor: «{s['title']}»", s["title"]))
    return issues


def _title_cycle_check(text: str, cycle_no: int | None) -> list[dict]:
    if not cycle_no:
        return []
    h1 = next((s["title"] for s in parse_sections(text) if s["level"] == 1), None)
    if h1 is None:
        return [_issue("title", "warn", "belgenin başlığı (# …) yok")]
    m = re.search(r"\btur\s*(\d+)", fold(h1))
    if m and int(m.group(1)) != int(cycle_no):
        return [_issue("cycle_mismatch", "critical", f"başlıktaki tur ({m.group(1)}) güncel tur ({cycle_no}) değil: eski turun belgesi olabilir")]
    if not m:
        return [_issue("title", "warn", f"başlıkta tur numarası yok (güncel tur {cycle_no})")]
    return []


def _money_or_null(body: str, value: float | None, what: str, code: str, section: str) -> list[dict]:
    if body is None:
        return []
    if value is None:
        if not any(w in fold(body) for w in NULL_WORDS):
            return [_issue(code, "critical", f"{what} kayıtlı değil (açık 'sınır yok' kararı); belge bunu söylemiyor", section)]
        return []
    if not has_number(body, value):
        return [_issue(code, "critical", f"{what} belgede kayıtlı değerle ({_fmt(value)}) aynı değil", section)]
    return []


def _fmt(v: float | None) -> str:
    if v is None:
        return "yok"
    v = float(v)
    return f"{int(v)}" if abs(v - round(v)) < 1e-9 else f"{v:.2f}".replace(".", ",")


def _mentions_any(text: str, words) -> bool:
    f = fold(text)
    return any(fold(w) in f for w in words)


# "kar" alt dizgisi "karar" içinde de geçer; zarar beyanı kelime sınırıyla aranır (2.5.0)
LOSS_RX = re.compile(r"\bzarar|\bnegatif\b|kâr\s*(?:etmiyor|yok|bırakmıyor)|kar\s*(?:etmiyor|yok|bırakmıyor)|\bkârsız|\bkarsız|"
                     r"katkı[^\n]{0,24}(?:≤|<=|<|eksi|sıfır|0\b)", re.I)


def mentions_loss(text: str) -> bool:
    return bool(LOSS_RX.search(fold(text or "")))


# --------------------------------------------------------------------------- aşamaya özgü denetimler
def check_s01(text: str, ctx: dict) -> list[dict]:
    issues: list[dict] = []
    secs = parse_sections(text)
    camp = ctx.get("campaign") or {}
    rt = camp.get("result_type")
    line = _line_with(text, "sonuç türü")
    if not rt:
        issues.append(_issue("result_type", "critical", "sonuç türü kaydedilmedi (campaign_update result_type) — brief'in temel kararı"))
    elif line is None:
        issues.append(_issue("result_type", "critical", "belgede 'Sonuç türü' satırı yok"))
    else:
        core = line
        # şablondaki seçenek listesi parantezi kaldıysa o parantez karar sayılmaz
        for grp in re.findall(r"\([^()]*\)", line):
            if sum(1 for k in RESULT_LABELS if k in grp) >= 3:
                core = core.replace(grp, "")
        if not _mentions_any(core, RESULT_LABELS[rt]):
            issues.append(_issue("result_type", "critical", f"belgedeki sonuç türü kayıtla ({rt}) uyuşmuyor"))
        others = [k for k in RESULT_LABELS if k != rt and k in fold(core)]
        if others:
            issues.append(_issue("result_type", "warn", f"sonuç türü satırında başka türler de geçiyor ({', '.join(others)}): tek karar yazılmalı"))
        if rt == "lead":
            lm = camp.get("lead_method")
            if not lm:
                issues.append(_issue("lead_method", "critical", "müşteri adayı sonucunda yol (instant_form · website · call) kaydedilmedi"))
            elif not _mentions_any(text, LEAD_METHOD_LABELS.get(lm, (lm,))):
                issues.append(_issue("lead_method", "critical", f"belgede müşteri adayı yolu ({lm}) yazılmamış"))
    season = str(camp.get("season") or "").strip()
    if season and fold(season) not in ("yok", "none"):
        sl = _line_with(text, "sezon")
        if sl is None or fold(season) not in fold(sl):
            issues.append(_issue("season", "critical", f"kayıtlı sezon ({season}) brief'in 'Sezon' satırında yok"))
    if not camp.get("budget_total_confirmed"):
        issues.append(_issue("budget_total", "critical", "toplam Meta harcama sınırı kullanıcıya sorulup teyit edilmedi (tutar ya da açık 'sınır yok')"))
    body = section_text(secs, "Toplam Meta harcama sınırı")
    issues += _money_or_null(body, camp.get("budget_total"), "toplam Meta harcama sınırı", "budget_total", "Toplam Meta harcama sınırı")
    daily = (ctx.get("cycle") or {}).get("adset_budget_daily")
    if daily is None:
        issues.append(_issue("adset_budget_daily", "critical", "reklam seti günlük bütçesi kaydedilmedi (cycle_set adset_budget_daily)"))
    else:
        dl = _line_with(text, "günlük bütçe") or _line_with(text, "günlük reklam seti")
        if dl is None or not has_number(dl, daily):
            issues.append(_issue("adset_budget_daily", "critical", f"reklam seti günlük bütçesi ({_fmt(daily)}) belgede yazılı değil ya da farklı"))
    eco = ctx.get("economics") or {}
    eco_body = section_text(secs, "Ekonomi") or ""
    status = eco.get("status")
    if status and status != "exact" and not _mentions_any(eco_body, ("varsayım", "varsayim", "bilinmiyor", "aralık", "aralik")):
        issues.append(_issue("economics_honesty", "critical",
                             f"ekonomi durumu '{status}' ama Ekonomi bölümü bunu VARSAYIM/aralık/bilinmiyor diye söylemiyor"))
    if (status in ("exact", "assumed") and rt in (None, "purchase") and eco.get("breakeven_cpa") is not None
            and not has_number(eco_body, eco["breakeven_cpa"])):
        issues.append(_issue("economics_value", "critical", f"başa baş CPA kayıtlı değerle ({_fmt(eco['breakeven_cpa'])}) aynı değil"))
    if status == "range" and rt in (None, "purchase") and eco.get("breakeven_cpa_range"):
        lo, hi = eco["breakeven_cpa_range"]
        if not (has_number(eco_body, lo) and has_number(eco_body, hi)):
            issues.append(_issue("economics_value", "critical", f"başa baş CPA aralığı ({_fmt(lo)}–{_fmt(hi)}) belgede yok"))
    if rt == "lead":  # aday sonucu: başa baş aday maliyeti ve dürüstlük etiketi de kayıtla aynı olmalı (1.5.0, 2.5.0)
        cs = eco.get("cpl_status")
        if eco.get("breakeven_cpl") is not None and not has_number(eco_body, eco["breakeven_cpl"]):
            issues.append(_issue("economics_value", "critical", f"başa baş aday maliyeti kayıtlı değerle ({_fmt(eco['breakeven_cpl'])}) aynı değil"))
        if eco.get("breakeven_cpl_range"):
            lo, hi = eco["breakeven_cpl_range"]
            if not (has_number(eco_body, lo) and has_number(eco_body, hi)):
                issues.append(_issue("economics_value", "critical", f"başa baş aday maliyeti aralığı ({_fmt(lo)}–{_fmt(hi)}) belgede yok"))
        if cs and cs != "exact" and not _mentions_any(eco_body, ("varsayım", "varsayim", "bilinmiyor", "aralık", "aralik")):
            issues.append(_issue("economics_honesty", "critical",
                                 f"aday maliyeti durumu '{cs}' ama Ekonomi bölümü bunu VARSAYIM/aralık/bilinmiyor diye söylemiyor"))
    if status == "non_positive" and not mentions_loss(eco_body):
        issues.append(_issue("economics_honesty", "critical", "ürünün katkısı ≤ 0 (her satış zarar): brief bunu açıkça söylemeli"))
    if camp.get("trial") and "varsayımsal" not in fold(text):
        issues.append(_issue("trial", "critical", "deneme kampanyası: ekonomi 'VARSAYIMSAL' diye yazılmalı (ürün tanışması atlandı)"))
    return issues


def check_s01b(text: str, ctx: dict) -> list[dict]:
    issues: list[dict] = []
    snap = ctx.get("snapshot")
    if snap:
        if f"#{snap['id']}" not in text and not re.search(rf"\b{snap['id']}\b", _line_with(text, "görüntü") or ""):
            issues.append(_issue("snapshot", "critical", f"dayanılan rakip görüntüsü (#{snap['id']}) belgede yok"))
        if snap.get("sha256") and snap["sha256"][:8] not in text:
            issues.append(_issue("snapshot", "warn", "rakip görüntüsünün SHA-256 özeti belgede yok (en az ilk 8 karakter)"))
        if snap.get("weak") and "zayıf kapsam" not in fold(text):
            issues.append(_issue("weak_coverage", "critical", f"görüntüde {snap.get('n_concepts', '?')} konsept var (< 10): bulgular 'zayıf kapsam' etiketi taşımalı"))
    if not _mentions_any(text, ("vekil", "proxy")):
        issues.append(_issue("proxy_label", "warn", "'işe yarıyor' çıkarımlarının vekil sinyal olduğu (performans kanıtı değil) yazılmamış"))
    return issues


def check_s02(text: str, ctx: dict) -> list[dict]:
    issues: list[dict] = []
    bp = ctx.get("budget_plan") or {}
    cy = ctx.get("cycle") or {}
    a = section_text(parse_sections(text), "(A) Ekonomi, bütçe ve takvim") or text
    n = bp.get("allowed_test_ads")
    val = row_value(a, "test reklamı sayısı")
    if n is not None:
        if val is None or not has_number(_strip_parens(val), n):
            issues.append(_issue("allowed_test_ads", "critical", f"izin verilen test reklamı sayısı kayıtlı planla ({n}) aynı değil"))
    dtb = bp.get("daily_test_budget")
    if dtb is not None:
        dl = row_value(a, "günlük test bütçesi")
        if dl is None or not has_number(dl, dtb):
            issues.append(_issue("daily_test_budget", "critical", f"günlük test bütçesi kayıtlı planla ({_fmt(dtb)}) aynı değil"))
    td, cd = cy.get("test_days"), cy.get("cycle_days")
    if td and cd:
        tl = row_value(a, "test günü")
        if tl is None or not (has_number(tl, td) and has_number(tl, cd)):
            issues.append(_issue("calendar", "critical", f"test günü / tur süresi kayıtla ({td} / {cd}) aynı değil"))
    rl = ctx.get("risk_limits") or {}
    per = rl.get("per_ad") or {}
    rline = row_value(a, "zarar-risk sınırı")
    if not per.get("amount"):
        issues.append(_issue("risk_limit", "critical", "onaylı reklam başı zarar-risk sınırı kaydı yok (kullanıcıya sorulup onaylanmalı)"))
    elif rline is None or not has_number(rline, per["amount"]):
        issues.append(_issue("risk_limit", "critical", f"zarar-risk sınırı kayıtlı onayla ({_fmt(per['amount'])}) aynı değil"))
    tline = row_value(a, "toplam harcama planı")
    fits = bp.get("fits_total_budget")
    if tline is None and "fits_total_budget" in bp:
        issues.append(_issue("fits_total", "critical", "'Toplam harcama planı' satırı yok: plan toplam sınıra sığıyor mu yazılmalı"))
    elif tline is not None and "fits_total_budget" in bp:
        f = fold(tline)
        f = f.split("sığıyor mu", 1)[1] if "sığıyor mu" in f else f
        if fits is True and not re.search(r"\bevet\b|\bsığıyor\b", f):
            issues.append(_issue("fits_total", "critical", "plan toplam sınıra sığıyor ama satır 'evet' demiyor"))
        if fits is True and re.search(r"\bhayır\b|sığmıyor|aşıyor", f):
            issues.append(_issue("fits_total", "critical", "plan toplam sınıra sığıyor ama satır 'hayır/aşıyor' diyor"))
        if fits is False and not re.search(r"\bhayır\b|sığmıyor|aşıyor|doğrulanmadı|doğrulanamadı", f):
            issues.append(_issue("fits_total", "critical", "plan toplam sınıra SIĞMIYOR (ya da doğrulanmadı) ama satır bunu söylemiyor"))
        if fits is None and not any(w in f for w in NULL_WORDS):
            issues.append(_issue("fits_total", "critical", "toplam harcama sınırı tanımlanmadı; satır bunu söylemeli"))
    if bp.get("production_blocked") and not _mentions_any(text, ("bekler", "bekliyor", "durur", "üretime geçmez", "yetmiyor")):
        issues.append(_issue("blocked", "critical", "plan üretimi durduruyor (production_blocked) ama belge kullanıcıya bunu söylemiyor"))
    if (ctx.get("economics") or {}).get("status") == "non_positive" and (ctx.get("campaign") or {}).get("result_type") in ("purchase", "lead"):
        if not mentions_loss(text):
            issues.append(_issue("economics_loss", "critical", "ürünün katkısı ≤ 0 (her satış zarar): strateji bunu ve kullanıcının kararını açıkça yazmalı"))
    if ctx.get("round_mode") == "funnel" and "huni" not in fold(text):
        issues.append(_issue("round_mode", "critical", "tur modu huni turu ama belgede yazılmamış"))
    if "tahmin" not in fold(a):
        issues.append(_issue("estimate_label", "warn", "bütçe hesabının tahmin olduğu yazılmamış"))
    return issues


def check_s03(text: str, ctx: dict) -> list[dict]:
    issues = []
    def present(c: str) -> bool:
        e = re.escape(c)
        if len(c) >= 3:
            return re.search(rf"(?<![\w-]){e}(?![\w-])", text) is not None
        # tek/iki harfli kod (A, B…) yalnızca kod olarak yazıldığı yerde sayılır: "Konsept A", "| A |", "**A**", "- A:" / "A —"
        pats = (rf"(?i:konsept|concept)\s*[«\"']?{e}(?![\w-])", rf"\|\s*\**{e}\**\s*\|", rf"\*\*{e}\*\*",
                rf"(?m)^\s*(?:[-*•]|\d+[.)])?\s*{e}\s*[:—–)-]")
        return any(re.search(p, text) for p in pats)
    missing = [c for c in ctx.get("accepted_concepts") or [] if not present(c)]
    if missing:
        issues.append(_issue("concepts", "critical", "seçilen konseptler görüşme özetinde yok: " + ", ".join(missing[:8])))
    return issues


def check_s04(text: str, ctx: dict) -> list[dict]:
    issues = []
    menu = section_text(parse_sections(text), "Çekim menüsü") or ""
    rows = table_rows(menu)
    need = int(ctx.get("accepted_test_hooks") or 0)
    if rows and need and len(rows) < need:
        issues.append(_issue("shoot_menu", "critical", f"çekim menüsünde {len(rows)} satır var, seçilen test hook'u {need} (her hook ayrı satır)"))
    if not _mentions_any(text, ("izin",)):
        issues.append(_issue("consent", "warn", "tanınabilir kişi için izin hatırlatması yok"))
    return issues


def check_s14(text: str, ctx: dict) -> list[dict]:
    issues: list[dict] = []
    secs = parse_sections(text)
    up = section_text(secs, "Yüklenecek dosyalar") or ""
    test_keys = ctx.get("test_keys") or []
    reserve_only = ctx.get("reserve_only_keys") or []
    def has_key(t: str, k: str) -> bool:
        return re.search(rf"(?<![\w-]){re.escape(k)}(?![\w-])", t) is not None
    miss = [k for k in test_keys if not has_key(up, k)]
    if miss:
        issues.append(_issue("upload_list", "critical", "yükleme listesinde olmayan test kreatifi: " + ", ".join(miss[:8])))
    extra = [k for k in reserve_only if has_key(up, k)]
    if extra:
        issues.append(_issue("reserve_in_upload", "critical", "yedek kreatif yükleme listesinde (yedekler yayına sessizce eklenmez): " + ", ".join(extra[:8])))
    notqc = ctx.get("test_keys_not_passed") or []
    if notqc:
        issues.append(_issue("qc", "critical", "QC'den geçmemiş test kreatifi: " + ", ".join(notqc[:8])))
    mapping = (ctx.get("risk_limits") or {}).get("mapping") or {}
    for row in table_rows(up):
        joined = " | ".join(row)
        for k in test_keys:
            if has_key(joined, k) and (mapping.get(k) or {}).get("amount") is not None and not has_number(joined, mapping[k]["amount"]):
                issues.append(_issue("risk_mapping", "warn", f"{k} satırındaki risk sınırı eşlemeyle ({_fmt(mapping[k]['amount'])}) aynı değil"))
    if ctx.get("has_ai"):
        ai = section_text(secs, "AI açıklaması") or ""
        if not _meaningful(ai) or re.fullmatch(r"\s*(yok|gerekmez|-)\s*\.?\s*", fold(ai)):
            issues.append(_issue("ai_disclosure", "critical", "AI içeren kreatif var: AI açıklaması talimatı boş bırakılamaz"))
    if ctx.get("structure") in ("creative_test", "ab_test"):
        adv = section_text(secs, "Advantage+ kreatif iyileştirmeleri") or ""
        if "kapat" not in fold(adv):
            issues.append(_issue("enhancements", "critical", "test turunda kreatifi değiştiren Advantage+ iyileştirmelerinin KAPATILMASI talimatı yok"))
    camp = ctx.get("campaign") or {}
    sp = section_text(secs, "Harcama ve bitiş sınırları")
    issues += _money_or_null(sp, camp.get("budget_total"), "kampanya toplam harcama sınırı", "budget_total", "Harcama ve bitiş sınırları")
    per = ((ctx.get("risk_limits") or {}).get("per_ad") or {}).get("amount")
    if sp is not None and per is not None and not has_number(sp, per):
        issues.append(_issue("risk_limit", "critical", f"reklam başı zarar-risk sınırı ({_fmt(per)}) harcama bölümünde yok ya da farklı", "Harcama ve bitiş sınırları"))
    if camp.get("result_type") == "lead" and "gizlilik" not in fold(text):
        issues.append(_issue("privacy_policy", "critical", "müşteri adayı kampanyası: formda gizlilik politikası bağlantısı talimatı yok"))
    copy = section_text(secs, "Metinler") or ""
    price = (ctx.get("product") or {}).get("price")
    if price:
        for amt in CURRENCY_AMOUNT.findall(copy):
            if not has_number(amt, price) and not _mentions_any(copy, ("indirim", "yerine", "önceki fiyat", "referans")):
                issues.append(_issue("price", "warn", f"metindeki tutar ({amt.strip()}) ürünün kayıtlı fiyatıyla ({_fmt(price)}) aynı değil: satış sayfasıyla birebir olmalı"))
                break
    for w in ctx.get("meta_text_warnings") or []:
        issues.append(_issue("meta_text", "warn", f"{w.get('rule')}: {w.get('why')} — «{(w.get('text') or '')[:80]}»", "Metinler"))
    return issues


STAGE_CHECKS = {"S01": check_s01, "S01b": check_s01b, "S02": check_s02, "S03": check_s03, "S04": check_s04, "S14": check_s14}


def template_for(stage: str, path: str) -> str | None:
    t = TEMPLATES.get(stage)
    if not t:
        return None
    return t[0] if re.search(t[1], str(path).replace("\\", "/")) else None


def check_document(text: str, stage: str, ctx: dict | None = None, template_md: str | None = None) -> dict:
    """Belgeyi denetler. ctx None ise yalnızca genel ve şablon denetimi. verdict: pass (kritik yok) | fail."""
    ctx = ctx or {}
    issues = generic_checks(text)
    if template_md:
        issues += template_checks(text, template_md, stage)
        issues += _title_cycle_check(text, ctx.get("cycle_no"))
        fn = STAGE_CHECKS.get(stage)
        if fn and ctx:
            issues += fn(text, ctx)
    elif stage == "S03" and ctx:
        issues += check_s03(text, ctx)
    crit = [i for i in issues if i["severity"] == "critical"]
    return {"verdict": "fail" if crit else "pass", "critical": len(crit), "warnings": len(issues) - len(crit), "issues": issues}
