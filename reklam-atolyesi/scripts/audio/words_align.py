"""Kelime zamanları ve altyazı (spec 5.7 adım 5, 5.14).

- Scribe transkript JSON'u (creative_transcribe_audio sonucu: words[] start/end) → *.words.json
- Altyazı parçaları: en fazla 2 satır, satır başına ~32 karakter, parça ≥ 0,8 sn; metin VO metniyle BİREBİR aynı olmalı.
Kullanım: words_align.py --transcript t.json --script vo.txt --out vo.words.json
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


def chunks(words: list[dict]) -> list[dict]:
    res, cur = [], []
    def flush():
        if cur:
            text = " ".join(w["text"] for w in cur)
            res.append({"text": text, "start": cur[0]["start"], "end": max(cur[-1]["end"], cur[0]["start"] + MIN_CHUNK_S),
                        "lines": wrap(text)})
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
    a = ap.parse_args()
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
    res = {"words": words, "captions": chunks(words), "matches_script": match,
           "note": None if match in (True, None) else "Transkript VO metniyle birebir değil: okunuş hatası olabilir; altyazı VO metninden kurulmalı ya da alım yeniden üretilmeli (5.7, 5.14)."}
    sha = write_json(a.out, res)
    emit({"out": a.out, "sha256": sha, "words": len(words), "captions": len(res["captions"]), "matches_script": match})


if __name__ == "__main__":
    main()
