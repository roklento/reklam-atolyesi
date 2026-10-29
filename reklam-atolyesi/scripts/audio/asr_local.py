"""Yerel yazıya dökme ve konuşmalı kurgu (1.4.8): ücretsiz, bilgisayardan çıkmayan Türkçe konuşma → kelime zamanları.

Motor: Whisper large-v3-turbo (faster-whisper, MIT; kendi sanal ortamında: DD/.tts/whisper/.venv; kurulum
`scripts/setup/tts_setup.py --engine whisper`). Ücretli Scribe'ın yerine varsayılan yol.

Kullanım:
  asr_local.py transcribe --data-dir DD --in a.wav [--in b.mp4 …] --out-dir DIR [--script vo.txt]
      → DIR/<ad>.transcript.json (döküm: sözcük, zaman, olasılık; sınırlar enerji zarfıyla gerçek sese oturtulmuş, `words_raw` ham
        Whisper zamanı, `nonspeech` dökümde olmayan sesli bölgeler) ve DIR/<ad>.words.json (words_align biçimi).
        --script varsa altyazı yazımı metinden; okunuş farkları `diffs` (850 TL ↔ "sekiz yüz elli lira" fark sayılmaz).
        1.6.0: Whisper'ın sözcük güveni (prob) LOW_PROB altındaysa kullanıcıya gösterilen dökümde `[?sözcük]` diye işaretlenir ve
        `low_confidence` listesine girer; words.json'daki sözcük metni ve altyazı değişmez (işaret yalnızca okuma içindir).
  asr_local.py align --transcript x.transcript.json --script metin.txt --out x.words.json     (motor gerekmez)
  asr_local.py cuts --transcript x.transcript.json --out cuts.json [--script duzeltilmis.txt] [--at 0] [--fps 30]
      [--punch 1.12] [--restore r3.20,r9.74] [--keep-retakes] [--role context] [--id-prefix konusma] [--asset <varlık kimliği>]
      → kesim ÖNERİSİ: dolgu (ııı/eee; dökümde olmayan sesli bölge), uzun sessizlik, yeniden başlama (art arda tekrar edilen
        bölüm ya da başı aynı cümle; son alım tutulur);
        tutulan parçalar kurgu planı sahnesi olarak (kaynak in/out, kamerada konuşan kişi, ses `original`, kesik yerinde
        dönüşümlü yakınlaştırma) ve kurgu zamanına taşınmış altyazı (cuts.words.json). Kararı kullanıcı verir (`--restore`).
  asr_local.py captions --words vo.words.json@0 --words cuts.words.json --out altyazi.words.json [--keywords "kargo,850 TL"]
      (VO + konuşma tek altyazı; her parçada en fazla bir vurgu sözcüğü — tek dosyada da kullanılır: --words vo.words.json)
  asr_local.py status --data-dir DD
"""
from __future__ import annotations

import argparse
import difflib
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "setup"))
from common import emit, read_json, write_json  # noqa: E402
import words_align as WA  # noqa: E402
import tts_local as TL  # noqa: E402
from tts_setup import PINS  # noqa: E402

WORKER = Path(__file__).resolve().parent / "asr_worker.py"
ENGINE = "whisper"

# --- Türkçe okunuş: yazılı metin ile duyulan metni aynı biçime getirir (sayı, para, yüzde, kısaltma) ---------------------------
ONES = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
TENS = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]
SCALES = [(10 ** 12, "trilyon"), (10 ** 9, "milyar"), (10 ** 6, "milyon"), (10 ** 3, "bin")]
ABBR = {"tl": ["lira"], "kg": ["kilogram"], "gr": ["gram"], "cm": ["santimetre"], "mm": ["milimetre"], "ml": ["mililitre"],
        "lt": ["litre"], "ve": ["ve"]}
# "Türk lirası", "lirası" ve "lira" aynı sayılır: kaynak "850 TL", okunuş "sekiz yüz elli Türk lirası", döküm "850 lira" olabilir
CANON = {"lirası": "lira", "liralık": "lira"}
FILLER = re.compile(r"^(ı+|i{2,}|e{2,}|a{2,}|ö{2,}|h?m{2,}|hm+|ı+m+|e+h+|e+m+|a+h+|ı+h+|h[ıe]+)$")


def _lower(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower()


def _below_1000(n: int) -> list[str]:
    out = []
    h, r = divmod(n, 100)
    if h:
        out += ([] if h == 1 else [ONES[h]]) + ["yüz"]
    t, o = divmod(r, 10)
    if t:
        out.append(TENS[t])
    if o:
        out.append(ONES[o])
    return out


def say_int(n: int) -> list[str]:
    """Tam sayının Türkçe okunuşu: 1250 → bin iki yüz elli; 2000000 → iki milyon."""
    if n == 0:
        return ["sıfır"]
    out = []
    for v, name in SCALES:
        q, n = divmod(n, v)
        if q:
            out += ([] if (q == 1 and name == "bin") else (_below_1000(q) if q < 1000 else say_int(q))) + [name]
    return out + _below_1000(n)


MONTHS = ["ocak", "şubat", "mart", "nisan", "mayıs", "haziran", "temmuz", "ağustos", "eylül", "ekim", "kasım", "aralık"]


def _frac(sep: str, frac: str) -> list[str]:
    z = len(frac) - len(frac.lstrip("0"))
    return ["virgül" if sep == "," else "nokta"] + ["sıfır"] * z + (say_int(int(frac)) if frac.strip("0") else [])


def number_words(p: str) -> list[str]:
    """Sayının okunuşu. Okunamayan biçim çökertmez: rakamlar tek tek okunur (karşılaştırmada fark olarak görünür, alım dinlenir)."""
    try:
        return _number_words(p)
    except (ValueError, IndexError):
        return [w for d in re.findall(r"\d", p) for w in say_int(int(d))]


def _number_words(p: str) -> list[str]:
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", p)
    if m and 1 <= int(m.group(1)) <= 31 and 1 <= int(m.group(2)) <= 12:  # 21.10.2026 → yirmi bir ekim iki bin yirmi altı
        return say_int(int(m.group(1))) + [MONTHS[int(m.group(2)) - 1]] + say_int(int(m.group(3)))
    m = re.fullmatch(r"(\d{1,3}(?:\.\d{3})+),(\d+)", p)  # 1.249,90 (TR: binlik nokta, ondalık virgül)
    if m:
        return say_int(int(m.group(1).replace(".", ""))) + _frac(",", m.group(2))
    m = re.fullmatch(r"(\d{1,3}(?:,\d{3})+)(?:\.(\d+))?", p)  # 1,250 / 1,250.50 (EN)
    if m:
        return say_int(int(m.group(1).replace(",", ""))) + (_frac(",", m.group(2)) if m.group(2) else [])
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", p):  # 1.250 (binlik ayırıcı)
        return say_int(int(p.replace(".", "")))
    m = re.fullmatch(r"(\d+)([,.])(\d+)", p)
    if m:  # 2,5 → iki virgül beş; 2,05 → iki virgül sıfır beş
        frac = m.group(3)
        z = len(frac) - len(frac.lstrip("0"))
        return say_int(int(m.group(1))) + ["virgül" if m.group(2) == "," else "nokta"] + ["sıfır"] * z + (say_int(int(frac)) if frac.strip("0") else [])
    if ":" in p:  # 12:30
        return [w for part in p.split(":") if part for w in say_int(int(part))]
    return say_int(int(p))


def spoken(token: str) -> list[str]:
    """Bir yazılı ya da duyulmuş sözcüğün karşılaştırma biçimi (küçük harf, noktalamasız, sayılar okunuşla)."""
    t = re.sub(r"₺\s*(\d[\d.,]*)", r"\1 tl", _lower(token))  # ₺99 → "doksan dokuz lira" (simge önde, okunuş sonda)
    t = t.replace("₺", " tl ").replace("%", " yüzde ").replace("&", " ve ").replace("’", "'")
    out: list[str] = []
    for p in re.findall(r"\d+(?:[.,:]\d+)*(?:'[a-zçğıöşüâîû]+)?|[a-zçğıöşüâîû]+(?:'[a-zçğıöşüâîû]+)?", t):
        suffix = ""
        if "'" in p:
            p, suffix = p.split("'", 1)
        if p[0].isdigit():
            ws = number_words(p)
            if suffix:
                ws[-1] += suffix
            out += ws
        elif p in ABBR and suffix:  # TL'ye → lira (ek ses uyumuyla okunur: liraya; kök karşılaştırılır)
            out += ABBR[p]
        else:
            out += ABBR.get(p + suffix, [p + suffix]) if not suffix else [p + suffix]
    return [_canon(w) for w in out]


def _canon(w: str) -> str:
    """Para birimi sözcükleri ekinden bağımsız: lirası/liraya/liralık → lira, kuruşa → kuruş."""
    for root in ("lira", "kuruş"):
        if w.startswith(root):
            return root
    return CANON.get(w, w)


NUMWORDS = set(ONES[1:] + TENS[1:] + ["yüz", "bin", "milyon", "milyar", "trilyon", "sıfır"])


def _collapse(seq: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Sözcükler arası birleştirme: "Türk" + "lirası" (ayrı yazılmış) → "lira" (850 TL ile aynı)."""
    out: list[tuple[str, int]] = []
    for w, o in seq:
        if w == "lira" and out and out[-1][0] == "türk":
            out.pop()
        out.append((w, o))
    # "2,5" = "iki buçuk": tam sayıdan sonra yalnız "virgül beş"
    k = 0
    while k + 1 < len(out):
        if out[k][0] == "virgül" and out[k + 1][0] == "beş" and k > 0 and out[k - 1][0] in NUMWORDS \
                and (k + 2 >= len(out) or out[k + 2][0] not in NUMWORDS):
            out[k:k + 2] = [("buçuk", out[k][1])]
        k += 1
    # "99,90 TL" (doksan dokuz virgül doksan lira) = "doksan dokuz lira doksan kuruş"
    k = 0
    while k < len(out):
        if out[k][0] == "virgül":
            j = k + 1
            while j < len(out) and out[j][0] in NUMWORDS:
                j += 1
            if j > k + 1 and j < len(out) and out[j][0] == "lira":
                frac = out[k + 1:j]
                out[k:j + 1] = [out[j]] + frac + [("kuruş", out[j][1])]
                k = j + 1
                continue
        k += 1
    return out


def is_filler(text: str) -> bool:
    w = spoken(text)
    return len(w) == 1 and bool(FILLER.match(w[0]))


# --- Metin ↔ döküm hizalaması ------------------------------------------------------------------------------------------------
def align(script: str, asr_words: list[dict]) -> dict:
    """Metnin her sözcüğüne dökümden zaman verir (yazım metinden). Duyulan ile metin farklıysa `diffs` (okunuş/eksik/fazla)."""
    src = script.split()
    A = _collapse([(w, i) for i, t in enumerate(src) for w in spoken(t)])
    asr = [w for w in asr_words if not is_filler(w["text"])]
    B = _collapse([(w, j) for j, aw in enumerate(asr) for w in spoken(aw["text"])])
    sm = difflib.SequenceMatcher(a=[w for w, _ in A], b=[w for w, _ in B], autojunk=False)
    times: dict[int, list[float]] = {}
    diffs = []

    def put(i: int, s: float, e: float) -> None:
        t = times.setdefault(i, [s, e])
        t[0], t[1] = min(t[0], s), max(t[1], e)
    for op, a0, a1, b0, b1 in sm.get_opcodes():
        if op == "equal":
            for k in range(a1 - a0):
                j = B[b0 + k][1]
                put(A[a0 + k][1], asr[j]["start"], asr[j]["end"])
            continue
        a_orig = sorted({A[k][1] for k in range(a0, a1)})
        b_orig = sorted({B[k][1] for k in range(b0, b1)})
        t_at = asr[b_orig[0]]["start"] if b_orig else (asr[B[b0][1]]["start"] if b0 < len(B) else (asr[-1]["end"] if asr else 0.0))
        diffs.append({"kind": {"replace": "okunuş farkı", "delete": "metinde var, duyulmadı", "insert": "duyuldu, metinde yok"}[op],
                      "script": " ".join(src[i] for i in a_orig), "heard": " ".join(asr[j]["text"] for j in b_orig), "t": round(t_at, 3)})
        if op == "replace" and a_orig and b_orig:  # B bloğunun süresi A sözcüklerine uzunlukları oranında dağıtılır
            s, e = asr[b_orig[0]]["start"], asr[b_orig[-1]]["end"]
            total = sum(len(src[i]) for i in a_orig) or 1
            acc = s
            for i in a_orig:
                d = (e - s) * len(src[i]) / total
                put(i, acc, acc + d)
                acc += d
    words = []
    for i, tok in enumerate(src):
        if i in times:
            words.append({"text": tok, "start": round(times[i][0], 3), "end": round(times[i][1], 3)})
        else:
            words.append({"text": tok, "start": None, "end": None})
    for i, w in enumerate(words):  # duyulmayan sözcük: komşuların arasına sıfıra yakın süreyle
        if w["start"] is None:
            prev = next((x["end"] for x in reversed(words[:i]) if x["start"] is not None), 0.0)
            nxt = next((x["start"] for x in words[i + 1:] if x["start"] is not None), prev)
            w["start"], w["end"] = round(prev, 3), round(max(prev, min(nxt, prev + 0.05)), 3)
    for i in range(1, len(words)):
        words[i]["start"] = max(words[i]["start"], words[i - 1]["start"])
        words[i]["end"] = max(words[i]["end"], words[i]["start"])
    for d, (op, a0, a1, b0, b1) in zip(diffs, [o for o in sm.get_opcodes() if o[0] != "equal"]):
        a_orig = sorted({A[k][1] for k in range(a0, a1)})
        if a_orig:  # okunuş farkında metin sözcüğünün süresindeki bütün duyulanlar (850 ↔ "sekiz yüz altmış")
            s, e = words[a_orig[0]]["start"], words[a_orig[-1]]["end"]
            heard = [w["text"] for w in asr if w["start"] < e and w["end"] > s]
            if heard:
                d["heard"] = " ".join(heard)
    return {"words": words, "matches_script": not diffs, "diffs": diffs}


LOW_PROB = 0.5  # faster-whisper sözcük olasılığı; altı "emin değilim" sayılır (1.6.0)


def low_confidence(words: list[dict]) -> list[dict]:
    """Düşük güvenli sözcükler (dolgu hariç): {i, text, start, prob}. prob yoksa (eski döküm) boş."""
    return [{"i": i, "text": w["text"], "start": w.get("start"), "prob": w["prob"]} for i, w in enumerate(words)
            if isinstance(w.get("prob"), (int, float)) and w["prob"] < LOW_PROB and not is_filler(w["text"])]


def marked_text(words: list[dict]) -> str:
    """Kullanıcıya gösterilecek döküm: düşük güvenli sözcük `[?sözcük]`."""
    low = {x["i"] for x in low_confidence(words)}
    return " ".join(f"[?{w['text']}]" if i in low else w["text"] for i, w in enumerate(words))


LOW_NOTE = ("[?sözcük] işaretli yerlerden Whisper emin değil: kullanıcı o sözcükleri özellikle kontrol eder (özel ad, marka, fiyat, "
            "ürün adı sık yanlış duyulur). İşaret yalnızca okuma içindir; altyazıya girmez.")


def words_doc(script: str | None, tr: dict) -> dict:
    """words_align biçimi: words + captions + matches_script (+ diffs)."""
    if script:
        al = align(script, tr["words"])
        note = None if al["matches_script"] else ("Duyulan metinle VO metni farklı (diffs): okunuş hatası olabilir; alım dinlenip gerekirse yeniden "
                                                  "üretilmeli. Altyazı yazımı VO metninden.")
        return {"words": al["words"], "captions": WA.chunks(al["words"]), "matches_script": al["matches_script"], "diffs": al["diffs"],
                "timing": "whisper", "note": note}
    words = [{"text": w["text"], "start": w["start"], "end": w["end"]} for w in tr["words"] if not is_filler(w["text"])]
    low = low_confidence(tr["words"])
    note = "Makine dökümü: altyazıdan önce kullanıcı metni okur; düzeltilmiş metin `align --script` ile uygulanır."
    return {"words": words, "captions": WA.chunks(words), "matches_script": None, "timing": "whisper",
            "text_marked": marked_text(tr["words"]), "low_confidence": low, "note": note + (" " + LOW_NOTE if low else "")}


# --- Sözcük sınırlarını sese oturtma ---------------------------------------------------------------------------------------------
# Whisper'ın sözcük zamanı duraklamadan sonraki sözcüğün başını sessizliğe çeker (ölçülen: 0,7 sn erken) ve yazmadığı dolgu sesini
# ("eee") sonraki sözcüğün içine katar. Enerji zarfından sesli bölgeler çıkarılır; her sözcük kendi aralığındaki son sesli öbeğe
# oturtulur; hiçbir sözcüğe düşmeyen sesli bölge "dökümde olmayan ses" (çoğunlukla dolgu/nefes) olarak raporlanır.
FILL_GAP = 0.08    # sesli bölge içindeki bundan kısa sessizlik (kapantılı ünsüz) birleştirilir
MIN_RUN = 0.05     # bundan kısa sesli parça gürültü sayılır
CLUSTER_GAP = 0.25  # bir sözcüğün içindeki öbekler
MIN_NONWORD = 0.12  # dökümde olmayan ses bundan kısaysa raporlanmaz


def voiced_runs(energy_db: list[float], hop: float = 0.01) -> list[tuple[float, float]]:
    if not energy_db:
        return []
    srt = sorted(energy_db)
    floor, top = srt[int(0.10 * (len(srt) - 1))], srt[int(0.95 * (len(srt) - 1))]
    thr = floor + max(8.0, 0.3 * (top - floor))
    runs: list[list[float]] = []
    for k, e in enumerate(energy_db):
        if e >= thr:
            t0 = k * hop
            if runs and t0 - runs[-1][1] <= FILL_GAP:
                runs[-1][1] = t0 + hop
            else:
                runs.append([t0, t0 + hop])
    return [(round(a, 3), round(b, 3)) for a, b in runs if b - a >= MIN_RUN]


def refine_words(words: list[dict], energy_db: list[float], hop: float = 0.01) -> tuple[list[dict], list[dict]]:
    """Sözcük sınırlarını gerçek sese oturtur. Dönüş: (düzeltilmiş sözcükler, dökümde olmayan sesli bölgeler)."""
    runs = voiced_runs(energy_db, hop)
    if not runs or not words:
        return [dict(w) for w in words], []

    def clusters(s: float, e: float) -> list[list[float]]:
        out: list[list[float]] = []
        for a, b in runs:
            if b > s and a < e:
                if out and a - out[-1][1] <= CLUSTER_GAP:
                    out[-1][1] = b
                else:
                    out.append([a, b])
        return out
    starts, chosen = [], []
    for w in words:
        cl = clusters(w["start"], w["end"])
        c = cl[-1] if cl else None
        chosen.append(c)
        starts.append(w["start"] if (c is None or c[0] <= w["start"] <= c[1]) else c[0])
    out = []
    prev_end = 0.0
    for i, (w, c) in enumerate(zip(words, chosen)):
        s = max(starts[i], prev_end)
        if c is None:
            e = w["end"]
        elif c[0] <= w["end"] <= c[1]:  # sözcük sesli bölgenin içinde bitiyor: bölge sonraki sözcüğe kadar sürüyorsa uzat
            nxt = starts[i + 1] if i + 1 < len(words) else c[1]
            e = max(w["end"], min(c[1], nxt))
        else:
            e = min(w["end"], c[1])
        e = max(e, s + 0.02)
        out.append({**w, "start": round(s, 3), "end": round(e, 3), **({"raw": [w["start"], w["end"]]} if (s, e) != (w["start"], w["end"]) else {})})
        prev_end = e
    nonword = []
    for a, b in runs:  # hiçbir sözcüğe düşmeyen sesli bölge
        free = [(a, b)]
        for w in out:
            nxt = []
            for x, y in free:
                if w["end"] <= x or w["start"] >= y:
                    nxt.append((x, y))
                    continue
                if w["start"] > x:
                    nxt.append((x, w["start"]))
                if w["end"] < y:
                    nxt.append((w["end"], y))
            free = nxt
        for x, y in free:
            near = any(abs(x - w["end"]) <= FILL_GAP or abs(y - w["start"]) <= FILL_GAP for w in out)
            if y - x >= MIN_NONWORD and not near:
                nonword.append({"start": round(x, 3), "end": round(y, 3)})
    return out, nonword


# --- Motor ---------------------------------------------------------------------------------------------------------------------
def installed(data_dir: Path) -> bool:
    try:
        TL.engine_python(data_dir, ENGINE)
        return True
    except SystemExit:
        return False


BATCH = 4  # bir işçi çağrısındaki dosya: model yüklemesi ~2 sn; bir dosyanın hatası ya da zaman aşımı diğerlerini kaybettirmez


def transcribe_files(data_dir: Path, files: list[str], prompt: str | None = None) -> dict:
    for f in files:
        if not Path(f).exists():
            raise TL.TTSError(f"dosya yok: {f}")
    pin = PINS[ENGINE]
    out, errors, meta = [], [], {}
    paths = [str(Path(f).resolve()) for f in files]
    for k in range(0, len(paths), BATCH):
        part = paths[k:k + BATCH]
        req = {"model": pin["model"], "revision": pin.get("revision"), "language": "tr", "files": part, "initial_prompt": prompt}
        try:
            res = TL.run_worker(data_dir, ENGINE, req, worker=WORKER, offline=True)
        except TL.TTSError as e:
            if len(paths) == 1:
                raise
            errors += [{"in": p, "error": str(e)[-400:]} for p in part]
            continue
        meta = {"engine_version": res["engine_version"], "model": res["model"], "load_s": res["load_s"]}
        out += [f for f in res["files"] if "error" not in f]
        errors += [{"in": f["in"], "error": f["error"]} for f in res["files"] if "error" in f]
    if not out:
        raise TL.TTSError("hiçbir dosya dökülemedi: " + "; ".join(e["error"][-200:] for e in errors[:2]))
    return {**meta, "files": out, "errors": errors}


def verify_takes(data_dir: Path, wavs: list[str], script: str) -> list[dict]:
    """Yerel seslendirme alımlarının okunuş denetimi: alım dökülür, VO metniyle karşılaştırılır. Motor yoksa denetim yapılmadı der."""
    if not installed(data_dir):
        return [{"checked": False, "how": "Okunuş denetimi için Whisper motoru: PY PR/scripts/setup/tts_setup.py --data-dir DD --engine whisper"}
                for _ in wavs]
    try:
        res = transcribe_files(data_dir, wavs)
    except SystemExit as e:  # denetim yapılamadı: seslendirme yine teslim edilir, durum açıkça yazılır
        return [{"checked": False, "how": f"okunuş denetimi çalışmadı: {str(e)[-300:]}"} for _ in wavs]
    by_in = {f["in"]: f for f in res["files"]}
    out = []
    for w in wavs:
        f = by_in.get(str(Path(w).resolve()))
        if f is None:
            out.append({"checked": False, "how": "bu alım dökülemedi"})
            continue
        al = align(script, f["words"])
        out.append({"checked": True, "matches": al["matches_script"], "diffs": al["diffs"],
                    "heard": " ".join(x["text"] for x in f["words"]), "model": res["model"]})
    return out


# --- Konuşmalı kurgu: kesim önerisi ---------------------------------------------------------------------------------------------
MAX_GAP = 0.35    # sözcükler arası bundan uzun sessizlik kesilir
PAD_IN = 0.06     # kesimde sözcük başından önce bırakılan pay (Whisper sınırları ± ~0,1 sn)
PAD_OUT = 0.12    # sözcük sonundan sonra bırakılan pay
SENT_GAP = 0.8    # bu kadar sessizlik cümle sınırı sayılır
MIN_SEG = 0.25    # bundan kısa parça, arada yalnızca kısa sessizlik varsa komşusuyla birleşir
MAX_BRIDGE = 0.6  # birleştirirken korunabilecek en uzun sessizlik (daha uzununu korumak temposu bozar; kısa parça uyarıyla kalır)
RETAKE_MIN_HEAD = 4  # yeniden başlanan cümlede ortak baş (sözcük)


def _sentences(words: list[dict]) -> list[list[int]]:
    sents, cur = [], []
    for i, w in enumerate(words):
        if cur and w["start"] - words[cur[-1]]["end"] > SENT_GAP:
            sents.append(cur)
            cur = []
        cur.append(i)
        if not w.get("nonword") and re.search(r"[.!?…]$", w["text"]):  # dökümde olmayan ses (nefes) cümleyi bitirmez
            sents.append(cur)
            cur = []
    if cur:
        sents.append(cur)
    return sents


def plan_cuts(tr: dict, *, restore: set[str] | None = None, keep_retakes: bool = False, at: float = 0.0, fps: int = 30,
              punch: float = 1.12, role: str = "context", id_prefix: str = "konusma", clip: str | None = None,
              script: str | None = None, asset: str | None = None) -> dict:
    restore = restore or set()
    words = sorted([dict(w) for w in tr["words"]] +
                   [{"text": "…", "start": n["start"], "end": n["end"], "nonword": True} for n in tr.get("nonspeech", [])],
                   key=lambda w: w["start"])
    dur = float(tr.get("duration_s") or (words[-1]["end"] if words else 0.0))
    removed: list[dict] = []
    drop: set[int] = set()
    protected: set[int] = set()  # kullanıcının geri aldığı sözcükler başka kuralla yeniden çıkarılmaz

    def mark(idx: list[int], reason: str) -> None:
        if not idx or set(idx) & (drop | protected):
            return
        rid = f"r{words[idx[0]]['start']:.2f}"  # kimlik zamandan: geri alma (--restore) her çalıştırmada aynı kesimi bulur
        removed.append({"id": rid, "start": words[idx[0]]["start"], "end": words[idx[-1]]["end"],
                        "text": " ".join(words[i]["text"] for i in idx), "reason": reason, "restored": rid in restore})
        (protected if rid in restore else drop).update(idx)
    for i, w in enumerate(words):
        if w.get("nonword"):
            mark([i], "dökümde olmayan ses: dolgu/nefes olabilir (gerçek sözse geri alın)")
        elif is_filler(w["text"]):
            mark([i], "dolgu sesi")
    canon = {i: ([] if words[i].get("nonword") else spoken(words[i]["text"])) for i in range(len(words))}

    def toks(s: list[int]) -> list[str]:
        return [t for i in s for t in canon[i]]

    def same(a: list[str], b: list[str]) -> bool:
        """İki söz parçası aynı mı: her sözcük eşit ya da yarım bırakılmış hâli (yap… → yapımı). Bir sözcüğü farklı paralel cümle
        ("… nemlendirir. … korur.") yeniden başlama değildir."""
        if len(a) != len(b) or len(a) < 2:
            return False
        return all(x == y or (len(x) >= 2 and (y.startswith(x) or x.startswith(y))) for x, y in zip(a, b))
    if not keep_retakes:
        # 1) yeniden başlama: art arda söylenen aynı parça (2–12 sözcük); önceki çıkar, sonraki tutulur. Tek sözcük ikilemesi
        #    Türkçede doğaldır (çok çok, yavaş yavaş) ve kesilmez.
        seq = [i for i in range(len(words)) if i not in drop and canon[i]]
        j = 1
        while j < len(seq):
            hit = 0
            for n in range(min(12, j, len(seq) - j), 1, -1):
                if same(toks(seq[j - n:j]), toks(seq[j:j + n])):
                    hit = n
                    break
            if hit:
                mark(seq[j - hit:j], f"yeniden başlama: aynı bölüm tekrar söylendi, sonraki tutuldu ({words[seq[j]]['start']:.1f} sn)")
            j += 1
        # 2) yeniden başlanan cümle: başı aynı, devamı farklı (önceki yarım/kötü alım). Paralel anlatım ("Her gün kullan. Her gün
        #    yıka.") kesilmesin diye: noktayla bitmiş (tam) cümle yalnızca sonrakinin birebir başıysa; noktalanmamış (yarıda kalmış)
        #    cümlede ortak baş en az RETAKE_MIN_HEAD sözcük ve cümlenin %60'ı, ya da cümlenin tamamı (son sözcük hariç).
        sents = [[i for i in s if i not in drop and canon[i]] for s in _sentences(words)]
        sents = [s for s in sents if s]

        def head(a: list[str], b: list[str]) -> int:
            n = 0
            for x, y in zip(a, b):
                if x == y or (len(x) >= 2 and (y.startswith(x) or x.startswith(y))):
                    n += 1
                else:
                    break
            return n
        for a in range(len(sents) - 1):
            ta = toks(sents[a])
            ended = bool(re.search(r"[.!?…]$", words[sents[a][-1]]["text"]))
            for b in (a + 1, a + 2):
                if b >= len(sents):
                    break
                tb = toks(sents[b])
                h = head(ta, tb)
                if (ended and h >= len(ta) and len(tb) > len(ta)) or                         (not ended and ((h >= RETAKE_MIN_HEAD and h >= 0.6 * len(ta)) or (h >= 2 and h >= len(ta) - 1 and len(tb) > len(ta)))):
                    mark(sents[a], f"yeniden başlanan cümle: sonraki alım tutuldu ({words[sents[b][0]]['start']:.1f} sn)")
                    break
    kept = [i for i in range(len(words)) if i not in drop]
    # parçalar: tutulan sözcükler; aradaki sessizlik MAX_GAP'i aşarsa ya da arada çıkarılan sözcük varsa kesik
    segs: list[list[int]] = []
    for i in kept:
        if segs and (words[i]["start"] - words[segs[-1][-1]]["end"] <= MAX_GAP) and not any(j in drop for j in range(segs[-1][-1] + 1, i)):
            segs[-1].append(i)
        else:
            segs.append([i])

    def span(seg: list[int]) -> tuple[float, float]:
        first, last = seg[0], seg[-1]
        lo = words[first - 1]["end"] if first > 0 else 0.0
        hi = words[last + 1]["start"] if last + 1 < len(words) else dur
        return max(lo, words[first]["start"] - PAD_IN, 0.0), min(hi, words[last]["end"] + PAD_OUT, dur)
    merged: list[list[int]] = []  # kısa parça: arada yalnızca sessizlik varsa komşusuyla birleşir
    for seg in segs:
        s0, s1 = span(seg)
        if merged and (s1 - s0 < MIN_SEG or span(merged[-1])[1] - span(merged[-1])[0] < MIN_SEG) \
                and words[seg[0]]["start"] - words[merged[-1][-1]]["end"] <= MAX_BRIDGE \
                and not any(j in drop for j in range(merged[-1][-1] + 1, seg[0])):
            merged[-1] += seg
        else:
            merged.append(seg)
    warnings = []
    scenes, segments, tl_words = [], [], []
    t = at
    for n, seg in enumerate(merged):
        s0, s1 = span(seg)
        s0, s1 = math.floor(s0 * fps + 1e-6) / fps, math.ceil(s1 * fps - 1e-6) / fps  # kare ızgarası (ses-görüntü kayması olmasın)
        s1 = min(s1, dur) if dur else s1  # dosya sonu kare ızgarasında değilse son sözcük kırpılmaz
        d = round(s1 - s0, 4)
        if d < MIN_SEG:
            warnings.append(f"parça {n + 1} kısa ({d:.2f} sn): kurguda kontrol edin")
        zoom = 1.0 if n % 2 == 0 else punch
        sid = f"{id_prefix}_{n + 1:02d}"
        ref = {"asset": asset} if asset else ({"path": clip} if clip else {})
        layer = {"type": "video", "source": {"kind": "footage", **ref, "in_s": round(s0, 4), "out_s": round(s1, 4)},
                 "speaking_person": True}
        if zoom != 1.0:
            layer["camera"] = {"preset": "punch_in", "zoom": zoom}
        scenes.append({"id": sid, "role": role, "start_s": round(t, 4), "dur_s": d, "speaking_person": True, "audio": {"mode": "original"},
                       "layers": [layer], "transition_out": {"type": "cut"}})
        segments.append({"id": sid, "in_s": round(s0, 4), "out_s": round(s1, 4), "zoom": zoom, "text": " ".join(words[i]["text"] for i in seg if not words[i].get("nonword"))})
        for i in seg:
            w = words[i]
            if w.get("nonword"):
                continue
            ws = round(t + max(w["start"], s0) - s0, 3)
            tl_words.append({"text": w["text"], "start": ws, "end": max(ws, round(t + min(w["end"], s1) - s0, 3))})
        t += d
    if script:  # düzeltilmiş metin: yazım metinden, zaman dökümden; yalnızca tutulan parçalara düşen sözcükler
        al = align(script, words)
        tl_words = []
        acc = at
        for seg in segments:
            for w in al["words"]:
                mid = (w["start"] + w["end"]) / 2
                if seg["in_s"] <= mid < seg["out_s"]:
                    tl_words.append({"text": w["text"], "start": round(acc + max(w["start"], seg["in_s"]) - seg["in_s"], 3),
                                     "end": round(acc + min(w["end"], seg["out_s"]) - seg["in_s"], 3)})
            acc += seg["out_s"] - seg["in_s"]
    kept_s = round(sum(s["out_s"] - s["in_s"] for s in segments), 3)
    return {"source": clip, "duration_s": round(dur, 3), "kept_s": kept_s, "removed_s": round(dur - kept_s, 3), "at_s": at, "fps": fps,
            "removed": removed, "segments": segments, "scenes": scenes, "warnings": warnings,
            "captions": {"words": tl_words, "captions": WA.chunks(tl_words), "matches_script": None, "timing": "whisper_timeline"},
            "note": "Kesimler öneridir: kullanıcı `removed` listesini görür; geri almak istedikleri `--restore r3.20,r9.74` ile tutulur. "
                    "Sahneler kurgu planına eklenir; altyazı kurgu zamanındadır (render --captions)."}


def _part(s: str) -> tuple[Path, float]:
    """'dosya.json@2.5' → (dosya, 2.5); yolda @ geçse de yalnızca sondaki sayı başlangıç sayılır."""
    base, sep, off = s.rpartition("@")
    if sep and re.fullmatch(r"\d+(\.\d+)?", off):
        return Path(base), float(off)
    return Path(s), 0.0


def merge_captions(parts: list[tuple[Path, float]], keywords: list[str] | None = None) -> dict:
    """Birden çok kelime dosyasını (VO, tutulan konuşma) kurgu zamanında tek altyazıya birleştirir; çakışan konuşma raporlanır."""
    words = []
    for path, off in parts:
        for w in read_json(path)["words"]:
            words.append({"text": w["text"], "start": round(w["start"] + off, 3), "end": round(w["end"] + off, 3)})
    words.sort(key=lambda w: w["start"])
    overlaps = [f"{words[i]['start']:.2f} sn" for i in range(1, len(words)) if words[i]["start"] < words[i - 1]["end"] - 0.05]
    return {"words": words, "captions": WA.chunks(words, keywords), "matches_script": None, "timing": "merged", "overlaps": overlaps,
            "note": None if not overlaps else "VO ile konuşma üst üste biniyor: iki ses aynı anda anlaşılmaz; kurguda biri kaydırılmalı."}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("transcribe")
    p.add_argument("--data-dir", required=True)
    p.add_argument("--in", dest="inputs", action="append", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--script", help="VO metni (dosya): okunuş denetimi ve altyazı yazımı")
    p = sp.add_parser("align")
    p.add_argument("--transcript", required=True)
    p.add_argument("--script", required=True)
    p.add_argument("--out", required=True)
    p = sp.add_parser("cuts")
    p.add_argument("--transcript", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--script")
    p.add_argument("--at", type=float, default=0.0)
    p.add_argument("--fps", type=int, default=30, choices=[30, 60])
    p.add_argument("--punch", type=float, default=1.12)
    p.add_argument("--restore", default="")
    p.add_argument("--keep-retakes", action="store_true")
    p.add_argument("--role", default="context")
    p.add_argument("--id-prefix", default="konusma")
    p.add_argument("--asset", help="klibin varlık kimliği (kurgu planı source.asset); yoksa dökümün dosya yolu")
    p = sp.add_parser("captions")
    p.add_argument("--words", action="append", required=True, help="kelime dosyası[@başlangıç sn]: VO ve konuşma altyazısı tek dosyada")
    p.add_argument("--keywords", help="vurgulanacak sözcükler, virgülle (ürün, teklif, hook sözcüğü; 1.5.0)")
    p.add_argument("--out", required=True)
    p = sp.add_parser("status")
    p.add_argument("--data-dir", required=True)
    a = ap.parse_args()
    if a.cmd == "transcribe":
        script = Path(a.script).read_text(encoding="utf-8") if a.script else None
        res = transcribe_files(Path(a.data_dir), a.inputs)
        od = Path(a.out_dir)
        od.mkdir(parents=True, exist_ok=True)
        out = []
        used: set[str] = set()
        for f in res["files"]:
            stem = Path(f["in"]).stem
            if stem.casefold() in used:  # aynı adlı iki girdi (a.wav + a.mp4, farklı klasörler; Windows'ta büyük/küçük harf aynı)
                stem = f"{stem}_{Path(f['in']).suffix.lstrip('.')}"
                n = 2
                while stem.casefold() in used:
                    stem, n = f"{Path(f['in']).stem}_{n}", n + 1
            used.add(stem.casefold())
            words, nonspeech = refine_words(f["words"], f.pop("energy_db", []), f.get("hop_s", 0.01))
            f.update(words_raw=f["words"], words=words, nonspeech=nonspeech)
            write_json(od / f"{stem}.transcript.json", {**f, "engine": ENGINE, "engine_version": res["engine_version"], "model": res["model"]})
            doc = words_doc(script, f)
            write_json(od / f"{stem}.words.json", doc)
            out.append({"in": f["in"], "transcript": str(od / f"{stem}.transcript.json"), "words": str(od / f"{stem}.words.json"),
                        "duration_s": f["duration_s"], "asr_s": f["asr_s"], "matches_script": doc["matches_script"],
                        "diffs": doc.get("diffs"), "text": marked_text(f["words"]),
                        "low_confidence": [{k: x[k] for k in ("text", "start", "prob")} for x in low_confidence(f["words"])]})
        emit({"engine": ENGINE, "model": res.get("model"), "load_s": res.get("load_s"), "files": out, "errors": res.get("errors") or [],
              **({"note": LOW_NOTE} if any(o["low_confidence"] for o in out) else {})})
    elif a.cmd == "align":
        tr = read_json(a.transcript)
        doc = words_doc(Path(a.script).read_text(encoding="utf-8"), tr)
        write_json(a.out, doc)
        emit({"out": a.out, "matches_script": doc["matches_script"], "diffs": doc["diffs"]})
    elif a.cmd == "cuts":
        if not 1.0 <= a.punch <= 1.2:
            raise SystemExit("--punch 1,0–1,2 olmalı (fazlası görüntüyü bozar)")
        tr = read_json(a.transcript)
        res = plan_cuts(tr, restore={x.strip() for x in a.restore.split(",") if x.strip()}, keep_retakes=a.keep_retakes, at=a.at,
                        fps=a.fps, punch=a.punch, role=a.role, id_prefix=a.id_prefix, clip=tr.get("in"),
                        script=Path(a.script).read_text(encoding="utf-8") if a.script else None, asset=a.asset)
        write_json(a.out, res)
        cap = Path(a.out).with_suffix(".words.json")
        write_json(cap, res["captions"])
        emit({"out": a.out, "captions": str(cap), "duration_s": res["duration_s"], "kept_s": res["kept_s"], "segments": len(res["segments"]),
              "removed": [{k: r[k] for k in ("id", "start", "text", "reason", "restored")} for r in res["removed"]], "warnings": res["warnings"]})
    elif a.cmd == "captions":
        doc = merge_captions([_part(s) for s in a.words], [k.strip() for k in (a.keywords or "").split(",") if k.strip()])
        write_json(a.out, doc)
        emit({"out": a.out, "words": len(doc["words"]), "captions": len(doc["captions"]), "overlaps": doc["overlaps"]})
    else:
        emit({ENGINE: {"installed": installed(Path(a.data_dir)), "model": PINS[ENGINE]["model"]}})


if __name__ == "__main__":
    main()
