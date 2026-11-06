"""Kullanıcı onayının biçimi ve kaynağı (2.10.7).

Onay, kullanıcının KENDİ mesajından alınır: navigator hook'u (UserPromptSubmit) plugin modundaki her kullanıcı mesajını oturum
dosyasına yazar; onay isteyen araçlar session_id ile çağrılır ve modelin yazdığı metin yerine bu kayıttaki son mesaj kullanılır.

Mesajın onay sayılması için yalnızca onay ve dolgu kelimelerinden oluşması gerekir (izin listesi). Olumsuz kelime listesi
kullanılmaz: listede olmayan tek bir kelime (ret, şart, değişiklik isteği) mesajı onay olmaktan çıkarır ve soru yeniden sorulur.
Mesajda sayı varsa, onaylanan sayıyla aynı olmalıdır (ör. azami kredi).
"""
from __future__ import annotations

import re
import unicodedata

# Mesajda en az biri bulunmalı
CORE = frozenset({"evet", "onay", "onayla", "onayliyorum", "onayliyoruz", "onayladim", "onayladik", "onaylarim", "onaylariz",
                  "onayli", "onaylandi", "tamam", "tamamdir", "kabul", "uygun", "olur", "okey", "ok", "aynen", "elbette",
                  "kesinlikle", "tabii", "tabi"})
# Tek başına onay değildir, onayın yanında durabilir
FILLER = frozenset({"ediyorum", "ederim", "ediyoruz", "et", "bunu", "bu", "su", "haliyle", "sekilde", "ile", "icin", "kredi",
                    "kredilik", "lutfen", "peki", "de", "da", "devam", "yap", "basla", "uret", "ilerle", "gec", "harca",
                    "harcayabilirsin", "secenek", "secenegi", "surum", "surumu", "olsun", "gibi", "boyle", "ve", "hepsi",
                    "hepsini", "plan", "plani", "belge", "belgeyi", "taslak", "taslagi", "adim", "adimi", "reklam", "atolyesi",
                    "tl", "try", "usd", "kaydet", "guzel", "iyi", "super", "harika", "dogru", "paket", "paketi",
                    # onaylanan işi kullanıcının kendi ağzından söyleyen fiiller (ör. "evet, hazırla"); tek başına onay değildir
                    "hazirla", "hazirlayabilirsin", "yaz", "yazalim", "yazabilirsin", "yapalim", "yapabilirsin", "baslayalim",
                    "ilerleyelim", "gecelim", "uygula", "uygulayalim", "uygulayacagim", "durduracagim", "durdurdum"})


# Silme onayında "evet"in yanında "sil / unut" da onay kelimesidir (ör. "evet, sil", "bunu unut"). "silme", "unutma" listede yoktur.
FORGET_CORE = frozenset({"sil", "silebilirsin", "silelim", "unut", "unutabilirsin", "unutalim"})
# Başka dilde onay: kabul edilmez, kullanıcıya Türkçe kısa cevap yazması söylenir (2.10.11)
FOREIGN_YES = frozenset({"yes", "yeah", "yep", "sure", "approve", "approved", "confirm", "confirmed", "si", "oui", "ja", "da"})
# Mesajda bulunabilecek karakterler (Türkçe harfler katlandıktan sonra). Emoji, başka alfabe ya da soru işareti varsa mesaj onay sayılmaz.
_ALLOWED = re.compile(r"[a-z0-9\s.,!;:'\"()\-/₺%]*")
MAX_APPROVAL_CHARS = 300  # onay kısa bir cevaptır; daha uzun mesajda şart ya da istek olabilir, yeniden sorulur

APPROVAL_TTL_MIN = 30  # tahmin ya da belge kullanıcıya gösterildikten sonra onayın geçerli kaldığı süre (dakika)
ONAYLA_COMMAND = "/reklam-atolyesi:onayla"

_TR = str.maketrans({"I": "ı", "İ": "i"})
_FOLD = str.maketrans({"ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c", "â": "a", "î": "i", "û": "u"})


def fold(s: str) -> str:
    t = (s or "").translate(_TR).lower().translate(_FOLD)
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))


_COMMAND = re.compile(r"^/(?:reklam-atolyesi:)?onayla(?=\s|$)")


def check(text: str | None, number: float | None = None, core: frozenset | None = None) -> tuple[bool, str | None]:
    """(onay mı, değilse nedeni). number verilirse mesajdaki her sayı ona eşit olmalı. core: bu onayda ayrıca geçerli onay kelimeleri
    (ör. silmede FORGET_CORE). 2.10.11: /onayla yalnızca tam komut olarak geçer ve arkasındaki metin de aynı denetimden geçer
    ("/onaylama", "/onayla ama 10 krediyi aşma" onay değildir); emoji, başka alfabe, soru işareti ya da çok uzun mesaj onay değildir."""
    raw = (text or "").strip()
    if not raw:
        return False, "onay ifadesi boş"
    if len(raw) > MAX_APPROVAL_CHARS:
        return False, "mesaj bir onay cevabı için çok uzun; içinde şart ya da istek olabilir"
    low = fold(raw)
    cmd = _COMMAND.match(low)
    if low.startswith("/") and not cmd:
        return False, "mesaj onay komutu değil"
    body = low[cmd.end():] if cmd else low
    if not _ALLOWED.fullmatch(body):
        return False, "mesajda harf ve rakam dışında işaret (emoji, soru işareti) ya da başka alfabe var; kullanıcıdan kelimeyle cevap iste"
    nums = [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", body)]
    words = re.findall(r"[a-z]+", body)
    okw = CORE | (core or frozenset())
    if not cmd and not any(w in okw for w in words):
        if any(w in FOREIGN_YES for w in words):
            return False, "onay Türkçe kısa bir cevapla verilir; kullanıcıya \"Onaylıyorsan evet yazman yeterli\" de"
        return False, "mesajda açık bir onay kelimesi yok"
    extra = sorted({w for w in words if w not in okw and w not in FILLER})
    if extra:
        return False, ("mesaj yalnızca onaydan oluşmuyor (" + ", ".join(extra[:5]) + "); şart, ret ya da değişiklik isteği "
                       "onay sayılmaz: kullanıcıya açıkça sor")
    if nums and number is not None and any(abs(n - float(number)) > 1e-9 for n in nums):
        return False, f"mesajdaki sayı onaylanan değerle ({number:g}) aynı değil"
    return True, None


def require(text: str | None, number: float | None = None, core: frozenset | None = None) -> str:
    from .util import AdMemoryError
    ok, why = check(text, number, core)
    if not ok:
        raise AdMemoryError(f"bu ifade onay sayılmaz: {why}. Kullanıcıya ne onayladığını gösterip açık onayını iste")
    return (text or "").strip()
