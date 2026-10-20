"""Teknik QC kontrolleri (spec bölüm 10, 5.15, 5.19): siyah kare/donma tespiti, güvenli alan, teknik özellikler.

Alt komutlar:
  black   --video v.mp4                       blackdetect + freezedetect (bütün video; örnek karelerden karar verilmez)
  safe    --plan plan.json                    yazı katmanlarının güvenli alanda ve ≥ 1,5 sn ekranda olup olmadığı
  meta-text --plan plan.json | --text metin.txt   Meta reklam standartları (ref-legal-tr-meta §8) için Türkçe metin taraması (uyarı)
  copy    --texts metin.json [--plan plan.json] [--promise "kelime,kelime"] [--targets hedef.json]
          reklam metni uzunluğu: birincil 125 / başlık 40 / açıklama 30 görünür karakter (Meta önerisi) + videonun yapısına göre kurallar
  tech    --video v.mp4 [--plan plan.json] [--expect-duration 15] [--format 9x16]
          süre, çözünürlük, fps, codec/profil, yuv420p, AAC 48 kHz, faststart, -14 LUFS ±1, ≤ -1 dBTP, siyah/donma, güvenli alan
Teknik geçer kararı görsel/işitsel insan kontrolünün yerine geçmez (5.15 sınırı).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "audio"))
from common import emit, ffmpeg, ffprobe_json, read_json  # noqa: E402

FORMAT_SIZE = {"9x16": (1080, 1920), "4x5": (1080, 1350), "1x1": (1080, 1080)}
SAFE = {"9x16": {"top": 0.14, "bottom": 0.35, "side": 0.06}, "4x5": {"top": 250 / 1350, "bottom": 250 / 1350, "side": 100 / 1080},
        "1x1": {"top": 0.08, "bottom": 0.08, "side": 0.08}}
# Meta: açıklama metni (disclaimer) içeren 9:16 reklamda alttaki %40 boş bırakılır (resmi: facebook.com/business/help/980593475366490,
# kontrol 2026-10-17; ref-legal-tr-meta §7). Plan açıklama taşıyorsa (disclaimer.on) ya da AI içeriyorsa (ai_share > 0) uygulanır.
DISCLAIMER_BOTTOM_9X16 = 0.40


def has_disclaimer(plan: dict) -> bool:
    d = plan.get("disclaimer") or {}
    ai = float((plan.get("provenance") or {}).get("ai_share") or 0)
    return bool(d.get("on")) or ai > 0


def safe_box(plan: dict) -> dict:
    fmt = plan["format"]
    z = dict(SAFE[fmt])
    if fmt == "9x16" and has_disclaimer(plan):
        z["bottom"] = max(z["bottom"], DISCLAIMER_BOTTOM_9X16)
        z["reason"] = "açıklama/AI içeren 9:16: alt %40 (Meta)"
    return z


def black_freeze(video: str, black_min: float = 0.12, freeze_min: float = 0.5) -> dict:
    r = ffmpeg(["-i", video, "-vf", f"blackdetect=d={black_min}:pix_th=0.06,freezedetect=n=0.002:d={freeze_min}", "-an", "-f", "null", "-"], check=False)
    blacks = [{"start": float(a), "end": float(b), "dur": float(c)} for a, b, c in
              re.findall(r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)", r.stderr)]
    fstarts = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", r.stderr)]
    fdurs = [float(x) for x in re.findall(r"freeze_duration: ([\d.]+)", r.stderr)]
    freezes = [{"start": s, "dur": d} for s, d in zip(fstarts, fdurs)]
    return {"black_segments": blacks, "freeze_segments": freezes, "ok": not blacks and not freezes}


def _text_y(layer: dict, scene_role: str, fmt: str, title_y: float) -> float:
    anchor = layer.get("anchor")
    if anchor == "safe_top":
        return title_y + 0.02
    if anchor == "safe_bottom":
        return 0.58 if fmt == "9x16" else 0.72
    if anchor == "center":
        return 0.42
    y = (layer.get("props") or {}).get("y")
    return float(y) if y is not None else title_y + 0.02


def safe_zone(plan: dict, style: dict | None = None) -> dict:
    fmt = plan["format"]
    z = safe_box(plan)
    title_y = ((style or {}).get("layout") or {}).get(fmt, {}).get("titleY", 0.12)
    issues, checked = [], 0
    for s in plan["scenes"]:
        for i, l in enumerate(s["layers"]):
            is_text = l.get("type") == "text" or l.get("component") in ("TextReveal", "KineticWords", "SoftType", "LowerThird", "PriceTag", "CaptionTrack", "CTAPulse")
            if not is_text:
                continue
            checked += 1
            y = _text_y(l, s["role"], fmt, title_y)
            if y < z["top"] - 1e-6 or y > 1 - z["bottom"] + 1e-6:
                issues.append({"scene": s["id"], "layer": i, "y": round(y, 3), "issue": f"yazı güvenli alan dışında ({fmt}: üst %{z['top']*100:.0f}, alt %{z['bottom']*100:.0f}"
                               + (f"; {z['reason']}" if z.get("reason") else "") + ")"})
            dur = float(l.get("dur_s", s["dur_s"] - float(l.get("start_s", 0))))
            if dur < 1.5:
                issues.append({"scene": s["id"], "layer": i, "issue": f"yazı {dur:.2f} sn ekranda (< 1,5 sn)"})
    return {"checked_text_layers": checked, "zone": z, "issues": issues, "ok": not issues}


# --- Meta reklam standartları metin taraması (ref-legal-tr-meta §8, 1.4.3) ----------------------------------------------------
# Kelime/kalıp tabanlı UYARI üretir, karar vermez: her uyarı QC'de gözle "sorun yok" ya da "düzelt" diye kayda geçer. Kurallar Meta'nın
# resmi yardım merkezi metinlerinden (kontrol 2026-10-17); Türkçe kalıplar plugin'in uyarlamasıdır.
META_SRC = {"8a": "https://www.facebook.com/business/help/2557868957763449", "8b": "https://www.facebook.com/business/help/304110064285796",
            "8c": "https://www.facebook.com/business/help/2489235377779939", "8d": "https://www.facebook.com/business/help/2489235377779939"}
ATTR = {  # kişisel özellik kökleri (8a); yalnızca ikinci şahıs/soru ile aynı cümlede uyarı
    "yaş": r"\b\d{2}\s*'?\s*(ın|in|un|ün|ını|ini|unu|ünü)\b|\byaş(ın|ınız|ında|ındaysan|ındaysanız)\b|\bemekli",
    "sağlık": r"\b(diyabet|şeker hastas|tansiyon|kanser|depresyon|anksiyete|panik atak|obez|hastalığın|ağrın|migren|sivilce|akne|egzama"
              r"|sedef|uçuk|tiroid|alzheimer|parkinson|otizm)",
    "beden ve görünüm": r"\b(kilo|şişman|göbe[kğ]|selülit|sarkm|kırışık|yağlan|zayıfla|incel(me|di|ir|ecek|t)|duble çene)",
    "maddi durum": r"\b(borç|borc|iflas|haciz|icra|kredi notu|fakir|geçinem)",
    "aile ve medeni durum": r"\b(bekar|bekâr|boşan|evlen|hamile|bebeğin|yalnız yaşı|dul\b)",
    "din, köken, yönelim, kimlik": r"\b(müslüman|hristiyan|yahudi|alevi|ateist|dindar|kürt|lgbt|gey\b|gay\b|lezbiyen|trans\b)",
    "engellilik": r"\b(engelli|özürlü|sakat)",
    "sabıka": r"\b(sabıka|hapis|cezaevi)",
}
SECOND = (r"\?|\b(sen|siz|senin|sizin|sana|size|seni|sizi)\b|\b(mı|mi|mu|mü|mısın|misin|musun|müsün|mısınız|misiniz|musunuz|müsünüz)\b"
          r"|\w+(sın|sin|sun|sün|sınız|siniz|sunuz|sünüz|san|sen|sanız|seniz)\b|\w+(ın|in|un|ün|n)\s*(mı|mi|mu|mü)\b")
SENSATIONAL = r"\b(şok|şoke|dehşet|korkunç|iğrenç|ölüm|öldü|ölecek|kan\b|kanlı|kaza|yangın|felaket|tehlike|kimse bilmiyor|bunu görmeden)"
HEALTH_PROMISE = (r"\b(garanti(li)?|mucize|kesin sonuç|anında sonuç|kalıcı çözüm|tedavi eder|iyileştirir|tamamen geçer)"
                  r"|\b\d+\s*(gün|hafta|ay)\w*\s.*\b(kilo|zayıf|incel|iyileş|kurtul|geçer)")
CURE = r"\b(diyabet|herpes|uçuk|tiroid|sedef|kanser|otizm|alzheimer|parkinson|als\b|hiv)\w*\b.*\b(iyileş|tedavi|geçir|kurtar|yok eder|bitir)"
BEFORE_AFTER = r"\b(önce(si)?\s*/\s*sonra(sı)?|öncesi ve sonrası|before\s*/?\s*after)"
_SKIP_PROP = {"src", "asset", "path", "color", "colors", "font", "fontfamily", "logo", "image", "video", "audio", "id", "preset", "anchor"}


def _fold_tr(s: str) -> str:
    return (s or "").replace("I", "ı").replace("İ", "i").lower()


def _plan_texts(plan: dict) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []

    def walk(where: str, v, key: str = "") -> None:
        if isinstance(v, str):
            if key.lower() in _SKIP_PROP or re.fullmatch(r"#?[0-9a-fA-F]{3,8}", v) or re.search(r"[\\/].*\.\w{2,4}$", v):
                return
            out.append((where, v))
        elif isinstance(v, dict):
            for k, x in v.items():
                if k.lower() not in _SKIP_PROP:
                    walk(where, x, k)
        elif isinstance(v, list):
            for x in v:
                walk(where, x, key)
    for s in plan.get("scenes", []):
        for i, l in enumerate(s.get("layers", [])):
            if l.get("type") == "text" and l.get("text"):
                out.append((f"{s.get('id')}/{i}", str(l["text"])))
            walk(f"{s.get('id')}/{i}", l.get("props") or {})
    d = plan.get("disclaimer") or {}
    if d.get("text"):
        out.append(("disclaimer", str(d["text"])))
    return out


# Reklam metni uzunluğu (1.4.8). Meta'nın önerdiği uzunluklar küçük ekranda görünen kısımdır; metin cihaza ve yerleşime göre daha erken
# kesilebilir (resmi: lead ads tasarım önerileri, Audience Network özellikleri; kontrol 2026-10-20). Reels/Stories için ayrı sayı yayımlanmamış.
COPY_OFFICIAL = {"primary": 125, "headline": 40, "description": 30, "display_url": 25}
COPY_SRC = {"primary": "https://www.facebook.com/business/help/908491205873167",
            "headline": "https://www.facebook.com/business/help/908491205873167",
            "description": "https://www.facebook.com/business/help/908491205873167",
            "display_url": "https://www.facebook.com/business/help/152143699744690"}
_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\U0001F000-\U0001F2FF]")
_INVISIBLE = re.compile("[\u200d\ufe0e\ufe0f\u0300-\u036f\U0001F3FB-\U0001F3FF]")


def graphemes(s: str) -> list[str]:
    """Görünen karakterler: birleşen işaret, varyasyon seçici, ten rengi, ZWJ ile bağlı emoji (👨‍👩‍👧) ve bayrak çifti (🇹🇷) tek karakter."""
    import unicodedata
    out: list[str] = []
    for ch in unicodedata.normalize("NFC", s or ""):
        cp = ord(ch)
        if out and (_INVISIBLE.match(ch) or unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me")
                    or 0xE0020 <= cp <= 0xE007F or out[-1].endswith("\u200d")):
            out[-1] += ch
        elif out and 0x1F1E6 <= cp <= 0x1F1FF and len(out[-1]) == 1 and 0x1F1E6 <= ord(out[-1]) <= 0x1F1FF:
            out[-1] += ch  # bölgesel gösterge çifti = bayrak
        else:
            out.append(ch)
    return out


def visible_len(s: str) -> int:
    """Görünen karakter sayısı (grafem): Türkçe harf, bileşik emoji ve bayrak 1 karakter."""
    return len(graphemes(s))


def _first_sentence(s: str) -> str:
    m = re.search(r"[.!?…\n]", s or "")
    return (s[:m.end()] if m else s or "").strip()


def _plan_structure(plan: dict | None) -> dict:
    if not plan:
        return {"known": False}
    scenes = plan.get("scenes") or []
    on_screen = []
    for s in scenes:
        for l in s.get("layers", []):
            if l.get("type") == "text" and l.get("text"):
                on_screen.append(str(l["text"]))
            if l.get("component") == "PriceTag":
                on_screen.append(str((l.get("props") or {}).get("price") or "fiyat"))
    speech = any((s.get("audio") or {}).get("mode") in ("user_vo", "generated") or s.get("speaking_person")
                 or any(l.get("speaking_person") for l in s.get("layers", [])) for s in scenes)
    return {"known": True, "format": plan.get("format"), "on_screen_text": on_screen, "speech_or_vo": speech,
            "captions": bool((plan.get("captions") or {}).get("on")),
            "price_on_screen": any(l.get("component") == "PriceTag" for s in scenes for l in s.get("layers", []))}


def copy_length(texts: dict, plan: dict | None = None, promise_terms: list[str] | None = None, targets: dict | None = None) -> dict:
    """Reklam metni uzunluğu ve görünen kısmın içeriği. Resmi öneri sınırları + videonun yapısına göre kurallar. Uyarıdır, karar değildir.
    targets: profil ya da stil kitabından DAHA SIKI hedefler (ör. {"primary": 90}); resmi önerilerden gevşek hedef kabul edilmez."""
    lim = dict(COPY_OFFICIAL)
    for k, v in (targets or {}).items():
        if k in lim and v is not None:
            if int(v) > lim[k]:
                raise SystemExit(f"{k} hedefi ({v}) Meta önerisinden ({lim[k]}) gevşek olamaz")
            lim[k] = int(v)
    st = _plan_structure(plan)
    items, warnings, info = {}, [], []
    for k in ("primary", "headline", "description", "display_url"):
        t = (texts or {}).get(k)
        if t is None:
            continue
        n = visible_len(t)
        items[k] = {"chars": n, "limit": lim[k], "source": COPY_SRC[k], "over": n > lim[k]}
        if n > lim[k]:
            kind = "görünür kısım" if k == "primary" else "alan"
            warnings.append({"field": k, "rule": "uzunluk", "why": f"{n} karakter > {lim[k]}: {kind} küçük ekranda kesilir (Meta önerisi)",
                             "source": COPY_SRC[k]})
    p = (texts or {}).get("primary") or ""
    if p:
        visible = p[:lim["primary"]]
        first = _first_sentence(p)
        if promise_terms:
            found = [w for w in promise_terms if _fold_tr(w) in _fold_tr(visible)]
            if not found:
                warnings.append({"field": "primary", "rule": "görünür mesaj",
                                 "why": "ana vaat/teklif sözcükleri ilk " + str(lim["primary"]) + " karakterde yok: kesilen kısımda kalıyor"})
        n_emoji = sum(1 for g in graphemes(visible) if _EMOJI.search(g) or 0x1F1E6 <= ord(g[0]) <= 0x1F1FF)
        n_tag = len(re.findall(r"(?<!\w)#\w+", visible))
        if n_emoji > 3 or n_tag > 2:
            warnings.append({"field": "primary", "rule": "görünür alan",
                             "why": f"görünür kısımda {n_emoji} emoji, {n_tag} etiket: mesaja yer kalmıyor (yerel kural: ≤ 3 emoji, ≤ 2 etiket)"})
        if st.get("known"):
            vertical = st["format"] == "9x16"
            if vertical and visible_len(first) > lim["primary"]:
                warnings.append({"field": "primary", "rule": "dikey yerleşim",
                                 "why": "9:16'da metin videonun üstünde ve cihaza göre daha erken kesilebilir (Meta: kesilme yerleşime ve "
                                        "cihaza bağlı); ilk cümle görünür sınırı aşıyor"})
            if not st["on_screen_text"] and not st["speech_or_vo"] and not st["captions"]:
                info.append("Videoda yazı, konuşma ya da altyazı yok: mesajı yalnızca reklam metni taşıyor; ilk cümle ne olduğunu ve neden "
                            "alınacağını söylemeli.")
            elif st["price_on_screen"] and re.search(r"\d[\d.,]*\s*(tl|₺|try)\b", _fold_tr(visible)):
                info.append("Fiyat videoda zaten var; görünür metinde tekrarı yer harcıyor (birebirlik kuralı geçerli: tutar aynı olmalı).")
            if vertical:
                info.append("Reels/Stories için Meta ayrı karakter sayısı yayımlamamış: görünür kısım 125 öneriyle sınırlandı; ana mesaj ilk "
                            "cümlede.")
    return {"items": items, "warnings": warnings, "info": info, "structure": st, "limits": lim, "ok": not warnings,
            "note": "Meta'nın önerdiği uzunluk küçük ekranda görünen kısımdır; daha uzun metin 'daha fazla' arkasında kalır, yasak değildir."}


def meta_text(items: list[tuple[str, str]]) -> dict:
    """Meta reklam standartları (§8) için Türkçe metin taraması. Uyarıdır; ok=False yalnızca 'incelenmeli' demektir."""
    warnings = []
    for where, text in items:
        for sent in [x for x in re.split(r"(?<=[.!?…])\s+|\n+", text) if x.strip()]:
            f = _fold_tr(sent)
            hits = []
            second = re.search(SECOND, f)
            for cat, rx in ATTR.items():
                # özellik ikinci şahısla aynı cümlede ya da ikinci şahıs iyelik ekiyle ("diyabetin", "kilon", "borcun")
                if re.search(rx, f) and (second or re.search(rf"(?:{rx})\w*?(ın|in|un|ün|n|ınız|iniz|unuz|ünüz)\b", f)):
                    hits.append(("8a", f"kişisel özellik ({cat}) ikinci şahısla ima ediliyor olabilir"))
            if re.search(SENSATIONAL, f):
                hits.append(("8b", "şok/korku dili olabilir (sansasyonel içerik)"))
            health_ctx = re.search(ATTR["sağlık"], f) or re.search(ATTR["beden ve görünüm"], f)
            if re.search(CURE, f):
                hits.append(("8c", "tedavisi olmayan hastalık için iyileştirme iddiası olabilir"))
            elif health_ctx and re.search(HEALTH_PROMISE, f):  # Meta'nın tıklama tuzağı kuralı sağlık/kilo bağlamı içindir
                hits.append(("8c", "kesinlik ya da süreli sonuç vaadi olabilir (sağlık/kilo bağlamında tıklama tuzağı)"))
            if re.search(BEFORE_AFTER, f):
                hits.append(("8d", "önce/sonra: ürün kategorisine göre kural (8d) ve 18+ hedefleme kontrol edilmeli"))
            for rule, why in hits:
                warnings.append({"where": where, "text": sent.strip(), "rule": f"ref-legal-tr-meta §{rule}", "why": why, "source": META_SRC[rule]})
    return {"scanned": len(items), "warnings": warnings, "ok": not warnings,
            "note": "Kelime/kalıp taraması uyarıdır, karar değildir; her uyarı gözle 'sorun yok' ya da 'düzelt' diye kayda geçer (§8e)."}


def tech(video: str, plan: dict | None, expect_duration: float | None, fmt: str | None) -> dict:
    import loudness as LN
    info = ffprobe_json(video)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), {})
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur = float(info["format"].get("duration") or 0)
    fmt = fmt or (plan or {}).get("format")
    res: dict = {"file": video, "checks": []}
    def check(name, ok, detail):
        res["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
    if fmt:
        w, h = FORMAT_SIZE[fmt]
        check("çözünürlük", v.get("width") == w and v.get("height") == h, f"{v.get('width')}×{v.get('height')} (beklenen {w}×{h})")
    fps_ok = v.get("r_frame_rate") in ("30/1", "30000/1000") and v.get("avg_frame_rate") in ("30/1", "30000/1000")
    check("fps 30 CFR", fps_ok, f"r={v.get('r_frame_rate')} avg={v.get('avg_frame_rate')}")
    check("codec H.264 High", v.get("codec_name") == "h264" and (v.get("profile") or "").lower().startswith("high"), f"{v.get('codec_name')} {v.get('profile')}")
    check("yuv420p", v.get("pix_fmt") == "yuv420p", v.get("pix_fmt"))
    exp = expect_duration or (plan or {}).get("duration_s")
    if exp:
        check("süre", abs(dur - float(exp)) <= 1 / 30 + 0.05, f"{dur:.3f} sn (beklenen {exp})")
    if a:
        check("ses AAC 48 kHz", a.get("codec_name") == "aac" and str(a.get("sample_rate")) == "48000", f"{a.get('codec_name')} {a.get('sample_rate')}")
        m = LN.measure(video)
        check("loudness -14 LUFS ±1", abs(m["lufs"] + 14) <= 1.0, f"{m['lufs']} LUFS")
        check("tepe ≤ -1 dBTP", m["true_peak_dbtp"] <= -1.0 + 0.05, f"{m['true_peak_dbtp']} dBTP")
    else:
        check("ses", False, "ses akışı yok")
    with open(video, "rb") as f:
        head = f.read(1 << 16)
    moov, mdat = head.find(b"moov"), head.find(b"mdat")
    check("+faststart", moov != -1 and (mdat == -1 or moov < mdat), "moov başta" if moov != -1 else "moov baştaki 64 KB'da yok")
    bf = black_freeze(video)
    check("siyah kare/donma yok", bf["ok"], {"black": bf["black_segments"], "freeze": bf["freeze_segments"]})
    if plan:
        sz = safe_zone(plan)
        check("yazılar güvenli alanda ve ≥ 1,5 sn", sz["ok"], sz["issues"])
    res["ok"] = all(c["ok"] for c in res["checks"])
    res["note"] = "Teknik QC; görsel ve işitsel insan kontrolünün yerine geçmez (5.15)."
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("black")
    p.add_argument("--video", required=True)
    p = sp.add_parser("safe")
    p.add_argument("--plan", required=True)
    p.add_argument("--style")
    p = sp.add_parser("meta-text")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan")
    g.add_argument("--text", help="reklam metni dosyası (birincil metin, başlık, açıklama; düz metin)")
    p = sp.add_parser("copy")
    p.add_argument("--texts", required=True, help='JSON: {"primary": "...", "headline": "...", "description": "..."}')
    p.add_argument("--plan")
    p.add_argument("--promise", help="görünür kısımda olması gereken ana vaat/teklif sözcükleri, virgülle")
    p.add_argument("--targets", help="profil/stil kitabından daha sıkı hedefler (JSON)")
    p = sp.add_parser("tech")
    p.add_argument("--video", required=True)
    p.add_argument("--plan")
    p.add_argument("--expect-duration", type=float)
    p.add_argument("--format")
    a = ap.parse_args()
    if a.cmd == "black":
        emit(black_freeze(a.video))
    elif a.cmd == "safe":
        emit(safe_zone(read_json(a.plan), read_json(a.style) if a.style else None))
    elif a.cmd == "copy":
        emit(copy_length(read_json(a.texts), read_json(a.plan) if a.plan else None,
                         [w.strip() for w in a.promise.split(",") if w.strip()] if a.promise else None,
                         read_json(a.targets) if a.targets else None))
    elif a.cmd == "meta-text":
        items = _plan_texts(read_json(a.plan)) if a.plan else [(Path(a.text).name, Path(a.text).read_text(encoding="utf-8"))]
        emit(meta_text(items))
    else:
        r = tech(a.video, read_json(a.plan) if a.plan else None, a.expect_duration, a.format)
        emit(r)
        sys.exit(0 if r["ok"] else 1)


if __name__ == "__main__":
    main()
