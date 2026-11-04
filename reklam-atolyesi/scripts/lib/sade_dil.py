"""Kullanıcıya giden metinlerde zor terim ve iç ad taraması (2.9.0, KURALLAR K16).

Kodun ürettiği müşteri metinleri (menü, aşama adları, hook mesajları, kurulum/güncelleme mesajları, hata defteri özeti) ve skill'lerin
kapı mesajı kalıpları bu taramadan geçer (`tests/test_v290_plain_language.py`; CI testleri çalıştırır). Modelin serbest cevabını
değerlendirme seti (`evals/rubrik.md` R3) sınar; sözlük ve kurallar `skills/ref-sade-dil/SKILL.md`'dedir.

Kural: aşağıdaki terimler kullanıcı metninde açıklamasız geçemez. Bir terim parantez içinde geçiyorsa (ör. "bir satışın reklam
maliyeti (CPA)") açıklanmış sayılır. İç adlar (aşama kodu, araç/alan adı, yazılım terimleri) parantez içinde de geçemez.
"""
from __future__ import annotations

import re

# Açıklanarak (parantez içinde) kullanılabilecek reklam ve video terimleri.
TERMS: list[tuple[str, str]] = [
    (r"\bCPA\b", "bir satışın reklam maliyeti"),
    (r"\bCPM\b", "1.000 gösterimin maliyeti"),
    (r"\bCTR\b", "görenlerin yüzde kaçının tıkladığı"),
    (r"\bROAS\b", "harcanan 1 TL'nin getirdiği satış"),
    (r"\bCPL\b", "bir müşteri adayının maliyeti"),
    (r"\bAOV\b", "ortalama sipariş tutarı"),
    (r"\bCTA\b", "harekete çağrı"),
    (r"\b[Hh]ook\w*", "videonun açılışı (ilk 3 saniye)"),
    (r"\b[Kk]reatif\w*", "reklam (video ya da görsel)"),
    (r"\b[Bb]rief\w*", "reklamın özeti"),
    (r"\bQC\b", "son kontrol"),
    (r"\b[Rr]ender\w*", "video dosyası"),
    (r"\b[Ee]xport\w*", "dosya olarak hazırlama"),
    (r"\b[Ii]ngest\w*", "çekimleri alma"),
    (r"\bVO\b", "seslendirme"),
    (r"\bLUFS\b|\bdBTP\b", "ses yüksekliği (sayı verilmez)"),
    (r"\bLUT\b", "renk ayarı"),
    (r"\bVFR\b|\bCFR\b|\bHDR\b|\bSDR\b", "görüntü düzeltme (söylenmez)"),
    (r"\bB-roll\b", "ara görüntüler"),
    (r"\bUGC\b", "müşteri videosu tarzı"),
    (r"\b[Cc]arousel\w*", "kaydırmalı çoklu görsel"),
    (r"\b[Pp]laybook\w*", "kalıcı kuralımız"),
    (r"\bproven\b|\bgap\b|\bcounter\b", "işe yaramış / boş bırakılmış / karşı fikir"),
    (r"\bTOFU\b|\bMOFU\b|\bBOFU\b", "ilk kez görenler / tanıyanlar / almaya yakın olanlar"),
    (r"\b[Pp]iksel\w*|\bCAPI\b|\b[Dd]ataset\w*", "satışları Meta'ya bildiren bağlantı"),
    (r"\b[Vv]aryasyon\w*", "farklı sürüm"),
    (r"\b[Ss]tatik\b", "tek görsel"),
    (r"\b[Öö]nsel\w*", "başlangıç beklentisi"),
]

# Kullanıcıya hiç gösterilmeyen iç adlar ve yazılım terimleri (parantez içinde de olmaz).
INTERNAL: list[tuple[str, str]] = [
    # Çekim numaraları (çekim menüsündeki "Çekim S01", "S01 çekimi") aşama kodu değildir; kullanıcıya böyle gösterilir.
    (r"(?<![Çç]ekim )\bS(?:0\d|1[0-7])b?\b(?! çekim)|\bS00[abc]\b", "aşama kodu: aşamanın adı söylenir"),
    (r"\b[a-z]+_[a-z0-9_]+\(", "araç adı"),
    (r"\b(?:gate_approve|draft_check|stage_\w+|campaign_\w+|feedback_\w+|profile_id|session_id|data_dir|budget_\w+)\b", "araç ya da alan adı"),
    (r"\bMCP\b|\bOAuth\b|\b[Tt]oken\w*\b|\bSHA-256\b|\bmanifest\w*|\bdoctor\b|\bsmoke\b|\bpytest\b|\bmigration\w*", "yazılım terimi"),
    (r"\b[Kk]apı(?:sı|da|dan|ya|yı|lar\w*)?\b", "'onayın gerekiyor' denir"),
    (r"\bplugin modu\b|\bprofil kartı\b|\bdevam notu\b", "iç kavram"),
    (r"\b[Bb]ağımlılık\w*", "yazılım terimi: 'gerekli programlar' denir"),
    (r"\b[Vv]eritabanı geçiş\w*", "yazılım terimi"),
    (r"\bsağlayıcı\w*", "'geliştirici' denir"),
]

_TERMS = [(re.compile(p), h) for p, h in TERMS]
_INTERNAL = [(re.compile(p), h) for p, h in INTERNAL]
PAREN = re.compile(r"\([^()]*\)")


def _paren_spans(text: str) -> list[tuple[int, int]]:
    spans, stack = [], []
    for i, ch in enumerate(text):
        if ch == "(":
            stack.append(i)
        elif ch == ")" and stack:
            spans.append((stack.pop(), i))
    return spans


def scan_text(text: str, *, allow: set[str] | None = None) -> list[dict]:
    """Bir kullanıcı metnindeki bulgular: [{kind: terim|iç_ad|dizi, match, hint}]. allow: bu bağlamda izinli eşleşmeler."""
    allow = {a.lower() for a in (allow or set())}
    out: list[dict] = []
    spans = _paren_spans(text or "")

    def in_paren(pos: int) -> bool:
        return any(a < pos < b for a, b in spans)

    for rx, hint in _TERMS:
        for m in rx.finditer(text or ""):
            if m.group(0).lower() in allow or in_paren(m.start()):
                continue
            out.append({"kind": "terim", "match": m.group(0), "hint": hint})
    for rx, hint in _INTERNAL:
        for m in rx.finditer(text or ""):
            if m.group(0).lower() in allow:
                continue
            out.append({"kind": "iç_ad", "match": m.group(0), "hint": hint})
    for line in (text or "").splitlines():
        if line.count(" · ") >= 3 or "→" in line:
            out.append({"kind": "dizi", "match": line.strip()[:80], "hint": "noktalı dizi ya da ok zinciri yerine tam cümle"})
    return out


QUOTE = re.compile(r"\"([^\"\n]{12,}(?:\n[^\"\n]*){0,6}?)\"|“([^”]{12,})”|«([^»]{12,})»")


def quoted_user_text(md: str) -> list[str]:
    """Skill metnindeki tırnaklı kullanıcı cümleleri (kapı mesajı kalıpları)."""
    out = []
    for m in QUOTE.finditer(md or ""):
        s = next(g for g in m.groups() if g)
        out.append(s)
    return out
