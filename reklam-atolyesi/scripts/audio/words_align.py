"""Kelime zamanları ve altyazı (spec 5.7 adım 5, 5.14).

- Scribe transkript JSON'u (creative_transcribe_audio sonucu: words[] start/end) → *.words.json
- Altyazı parçaları: en fazla 2 satır, satır başına ~32 karakter, parça ≥ 0,8 sn; metin VO metniyle BİREBİR aynı olmalı.
- Vurgu (1.5.0): her parçada EN FAZLA bir vurgu sözcüğü (`emph`, parçadaki sözcük sırası). Öncelik: verilen anahtar kelimeler (ürün,
  teklif, hook sözcüğü) → sayı/fiyat/yüzde → en uzun anlamlı sözcük (≥ 5 harf, bağlaç/edat değil). Parçada aday yoksa vurgu yok.
  Her parça sözcük zamanlarını da taşır (`words`): karaoke ön ayarı etkin sözcüğü bunlarla bulur.
Kullanım: words_align.py --transcript t.json --script vo.txt --out vo.words.json [--keywords "kargo,850 TL"]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit, read_json, write_json  # noqa: E402
from admem.util import tr_fold  # noqa: E402

MAX_LINE = 32
MAX_LINES = 2
MIN_CHUNK_S = 0.8


def norm_words(s: str) -> list[str]:
    return re.findall(r"[0-9a-z]+", tr_fold(s))


def extract_words(tr: dict | list) -> list[dict]:
    if isinstance(tr, dict):
        for k in ("words", "transcripts"):
            if k in tr:
                tr = tr[k]
                break
    if tr and isinstance(tr, list) and isinstance(tr[0], dict) and "words" in tr[0]:
        tr = [w for t in tr for w in t["words"]]
    out = []
    for w in tr:
        text = (w.get("text") or w.get("word") or "").strip()
        if not text or w.get("type") == "spacing":
            continue
        out.append({"text": text, "start": float(w["start"]), "end": float(w["end"])})
    return out


# Vurgu adayı olmayan sözcükler (bağlaç, edat, zamir, yardımcı; yerel liste)
STOP = set("""ve ile ama fakat veya ya da de da ki mi mı mu mü bu şu o bir her çok daha en gibi için kadar sonra önce
artık hem ne nasıl neden niye şimdi hemen yani ise bile diye olan olarak gibi bunu şunu onu bunlar şunlar onlar bizim sizin
senin benim kendi kendini""".split())


def _fold(s: str) -> str:
    return re.sub(r"[^0-9a-zçğıöşü]", "", s.replace("İ", "i").replace("I", "ı").lower())


def _variants(s: str) -> set[str]:
    """Türkçe ve Latin küçük harf (LINEN → linen; İSTANBUL → istanbul)."""
    return {v for v in (_fold(s), re.sub(r"[^0-9a-zçğıöşü]", "", s.lower())) if v}


def emphasis(chunk_words: list[dict], keywords: list[str] | None = None) -> int | None:
    """Parçadaki vurgu sözcüğünün sırası (en fazla bir); aday yoksa None."""
    # çok sözcüklü anahtar ("kapıda ödeme") sözcüklerine ayrılır; parçada ilk eşleşen sözcük vurgulanır
    keys = [v for x in (keywords or []) for part in str(x).split() for v in _variants(part) if len(v) >= 2]
    folded = [_fold(w["text"]) for w in chunk_words]
    for i, w in enumerate(chunk_words):  # 1) anahtar kelime: tam sözcük ya da (≥ 4 harfli anahtarda) kök başı
        if any(f == k or (len(k) >= 4 and f.startswith(k)) for f in _variants(w["text"]) for k in keys):
            return i
    for i, w in enumerate(chunk_words):  # 2) sayı, fiyat, yüzde
        if re.search(r"\d", w["text"]) or "%" in w["text"] or "₺" in w["text"]:
            return i
    best = None
    for i, f in enumerate(folded):  # 3) en uzun anlamlı sözcük
        if len(f) >= 5 and f not in STOP and (best is None or len(f) > len(folded[best])):
            best = i
    return best


def chunks(words: list[dict], keywords: list[str] | None = None) -> list[dict]:
    res, cur = [], []
    def flush():
        if cur:
            text = " ".join(w["text"] for w in cur)
            ws = [{"text": w["text"], "start": w["start"], "end": w["end"]} for w in cur]
            res.append({"text": text, "start": cur[0]["start"], "end": max(cur[-1]["end"], cur[0]["start"] + MIN_CHUNK_S),
                        "lines": wrap(text), "words": ws, "emph": emphasis(ws, keywords)})
    for w in words:
        trial = " ".join(x["text"] for x in cur + [w])
        if cur and (len(wrap(trial)) > MAX_LINES or re.search(r"[.!?]$", cur[-1]["text"])):
            flush()
            cur = []
        cur.append(w)
    flush()
    return res


def wrap(text: str) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        if len(cur) + len(word) + (1 if cur else 0) <= MAX_LINE:
            cur = f"{cur} {word}".strip()
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--script", help="VO metni (dosya); altyazı metni bununla birebir aynı olmalı")
    ap.add_argument("--out", required=True)
    ap.add_argument("--keywords", help="vurgulanacak sözcükler, virgülle (ürün, teklif, hook sözcüğü)")
    a = ap.parse_args()
    keys = [k.strip() for k in (a.keywords or "").split(",") if k.strip()]
    words = extract_words(read_json(a.transcript))
    match = None
    if a.script:
        script = Path(a.script).read_text(encoding="utf-8")
        match = norm_words(script) == norm_words(" ".join(w["text"] for w in words))
        if match:  # yazımı VO metninden al (noktalama/büyük harf birebir)
            sw = script.split()
            if len(sw) == len(words):
                for w, t in zip(words, sw):
                    w["text"] = t
    res = {"words": words, "captions": chunks(words, keys), "matches_script": match,
           "note": None if match in (True, None) else "Transkript VO metniyle birebir değil: okunuş hatası olabilir; altyazı VO metninden kurulmalı ya da alım yeniden üretilmeli (5.7, 5.14)."}
    sha = write_json(a.out, res)
    emit({"out": a.out, "sha256": sha, "words": len(words), "captions": len(res["captions"]), "matches_script": match})


if __name__ == "__main__":
    main()
