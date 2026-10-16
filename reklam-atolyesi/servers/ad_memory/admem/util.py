"""Ortak yardımcılar: zaman, JSON, hash, Türkçe normalleştirme, atomik yazma."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Callable

# Test ve sentetik senaryolar saati enjekte edebilsin diye tek bir saat kaynağı.
_clock: Callable[[], _dt.datetime] | None = None


def set_clock(fn: Callable[[], _dt.datetime] | None) -> None:
    global _clock
    _clock = fn


def utcnow() -> _dt.datetime:
    if _clock is not None:
        return _clock()
    return _dt.datetime.now(_dt.timezone.utc)


def now_iso() -> str:
    return utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str | None) -> _dt.datetime | None:
    if not s:
        return None
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    d = _dt.datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.timezone.utc)
    return d


def jdump(obj: Any) -> str | None:
    if obj is None:
        return None
    return json.dumps(obj, ensure_ascii=False, sort_keys=False)


def jload(s: Any, default: Any = None) -> Any:
    """JSON metnini çözer; zaten çözülmüş dict/list (satır okuyucusu *_json alanlarını çözer) olduğu gibi döner."""
    if s is None or s == "":
        return default
    if isinstance(s, (dict, list)):
        return s
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return default


def canonical_json(obj: Any) -> str:
    """Anahtar sırası sabit, boşluksuz JSON (hash ve parmak izi için)."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: str | os.PathLike) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write(path: str | os.PathLike, data: bytes | str, *, overwrite: bool = True) -> str:
    """Geçici ada yaz → fsync → doğrula → atomik yeniden adlandır (4.2). SHA-256 döner."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not overwrite and p.exists():
        raise FileExistsError(f"Dosya zaten var, üzerine yazılmaz: {p}")
    raw = data.encode("utf-8") if isinstance(data, str) else data
    fd, tmp = tempfile.mkstemp(prefix=f".{p.name}.", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        if sha256_file(tmp) != sha256_bytes(raw):
            raise IOError("Geçici dosya doğrulanamadı")
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return sha256_bytes(raw)


# --- Türkçe normalleştirme (8.4) -------------------------------------------------
_FOLD = str.maketrans({"ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c", "â": "a", "î": "i", "û": "u"})


def tr_lower(s: str) -> str:
    """Türkçeye duyarlı küçültme: I→ı, İ→i (Python'un lower()'ı İ'yi 'i̇' yapar)."""
    if not s:
        return ""
    s = s.replace("I", "ı").replace("İ", "i")
    s = s.lower()
    return unicodedata.normalize("NFC", s.replace("i̇", "i"))


def tr_fold(s: str) -> str:
    """Aksansız kopya: ı→i, ş→s, ğ→g, ü→u, ö→o, ç→c."""
    s = tr_lower(s).translate(_FOLD)
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def fts_body(text: str) -> str:
    """İndekslenecek metin: Türkçe küçük harfli biçim + aksansız kopya."""
    a = tr_lower(text)
    b = tr_fold(text)
    return a if a == b else f"{a}\n{b}"


def fts_query(q: str) -> str | None:
    """Kullanıcı sorgusunu FTS5 trigram ifadesine çevirir; 3 harften kısa terimler için None."""
    terms = [t for t in re.split(r"\s+", q.strip()) if t]
    parts: list[str] = []
    for t in terms:
        lo, fo = tr_lower(t), tr_fold(t)
        if len(fo) < 3:
            continue
        alts = {lo, fo}
        parts.append("(" + " OR ".join('"' + a.replace('"', '""') + '"' for a in sorted(alts)) + ")")
    if not parts:
        return None
    return " AND ".join(parts)


def est_tokens(s: str | None) -> int:
    """Kaba token tahmini (Türkçe için ~3.5 karakter/token)."""
    if not s:
        return 0
    return int(math.ceil(len(s) / 3.5))


def trigram_set(s: str) -> set[str]:
    f = re.sub(r"\s+", " ", tr_fold(s)).strip()
    return {f[i:i + 3] for i in range(max(0, len(f) - 2))}


def trigram_similarity(a: str, b: str) -> float:
    ta, tb = trigram_set(a), trigram_set(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def ngram_overlap(a: str, b: str, n: int = 4) -> float:
    """Normalize metinde kelime n-gram örtüşmesi: |A∩B| / min(|A|,|B|) (uzaklık kuralı, bölüm 10)."""
    def grams(s: str) -> set[tuple[str, ...]]:
        w = re.findall(r"[0-9a-z]+", tr_fold(s))
        if len(w) < n:
            return {tuple(w)} if w else set()
        return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}
    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / min(len(ga), len(gb))


def slugify(s: str, maxlen: int = 40) -> str:
    f = tr_fold(s)
    f = re.sub(r"[^a-z0-9]+", "-", f).strip("-")
    return (f or "x")[:maxlen].strip("-") or "x"


class AdMemoryError(Exception):
    """Kullanıcıya/Claude'a Türkçe açıklamayla dönen iş kuralı hatası."""
