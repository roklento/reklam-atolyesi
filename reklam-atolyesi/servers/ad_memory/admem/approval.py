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


APPROVAL_TTL_MIN = 30  # tahmin ya da belge kullanıcıya gösterildikten sonra onayın geçerli kaldığı süre (dakika)
ONAYLA_COMMAND = "/reklam-atolyesi:onayla"

_TR = str.maketrans({"I": "ı", "İ": "i"})
_FOLD = str.maketrans({"ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c", "â": "a", "î": "i", "û": "u"})


def fold(s: str) -> str:
    t = (s or "").translate(_TR).lower().translate(_FOLD)
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))


def check(text: str | None, number: float | None = None) -> tuple[bool, str | None]:
    """(onay mı, değilse nedeni). number verilirse mesajdaki her sayı ona eşit olmalı."""
    raw = (text or "").strip()
    if not raw:
        return False, "onay ifadesi boş"
    if fold(raw).startswith((ONAYLA_COMMAND, "/onayla")):
        return True, None  # /onayla komutu kullanıcının kendi açık eylemidir
    low = fold(raw)
    nums = [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", low)]
    words = re.findall(r"[a-z]+", low)
    if not any(w in CORE for w in words):
        return False, "mesajda açık bir onay kelimesi yok"
    extra = sorted({w for w in words if w not in CORE and w not in FILLER})
    if extra:
        return False, ("mesaj yalnızca onaydan oluşmuyor (" + ", ".join(extra[:5]) + "); şart, ret ya da değişiklik isteği "
                       "onay sayılmaz: kullanıcıya açıkça sor")
    if nums and number is not None and any(abs(n - float(number)) > 1e-9 for n in nums):
        return False, f"mesajdaki sayı onaylanan değerle ({number:g}) aynı değil"
    return True, None


def require(text: str | None, number: float | None = None) -> str:
    from .util import AdMemoryError
    ok, why = check(text, number)
    if not ok:
        raise AdMemoryError(f"bu ifade onay sayılmaz: {why}. Kullanıcıya ne onayladığını gösterip açık onayını iste")
    return (text or "").strip()
