"""Font glif kapsamı (1.5.1; spec 5.6, 5.15): plandaki yazıların her karakteri, o yazıyı çizecek fontun projede gerçekten yüklenen
yüzlerinde var mı. Eksik karakter tarayıcıda başka bir fonta düşer; küçük yazıda kontak sayfasında görülmez (kare 1080'den 270 px'e iner).

Kaynak: kampanya projesinin src/ dosyalarındaki `@fontsource/<paket>/...` içe aktarmaları → <data_dir>/.node/node_modules altındaki CSS
@font-face blokları (font-family, font-weight, font-style, unicode-range). Alt küme CSS'inde (ör. latin-ext-700.css) unicode-range yazmaz;
o yüz bütün karakterleri üstlenir ama dosyada yalnızca o alt kümenin glifleri vardır — kapsam paketin unicode.json'undan alınır.
Hangi yazı hangi fontla çizilir (templates/remotion/src): text katmanı → style.fonts.display (ağırlık displayWeight); bileşen katmanı →
props.fontFamily, yoksa bileşenin varsayılanı (Inter); altyazı → style.fonts.body, 700. Her kullanılan fonttan ayrıca Türkçe alfabe beklenir.

Sonuç: `missing` (fontun hiçbir yüzünde yok → yedek fonta düşer; öz denetimde düzeltilecek bulgu), `weight_gaps` (font var ama istenen
ağırlıkta o karakter yok → başka ağırlıkla çizilir; uyarı), `unresolved` (içe aktarılan paket/CSS bulunamadı ya da font hiç yüklenmiyor;
bulgu). Proje ya da node_modules verilmezse kontrol yapılmaz ve bu açıkça döner (`checked: false`).

Kullanım: font_coverage.py --plan plan.json --project <kampanya>/src --data-dir DD [--style s.json] [--captions words.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import emit, read_json  # noqa: E402

TR_ALPHABET = "abcçdefgğhıijklmnoöprsştuüvyzABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZ0123456789.,:;!?%-'\"()₺"
DEFAULT_FAMILY = "Inter"  # bileşen şemalarının varsayılanı (components/*.tsx: fontFamily default "Inter")
NEUTRAL_FONTS = {"display": "Inter", "displayWeight": 700, "body": "Inter", "brand": "Inter"}  # style.ts NEUTRAL_STYLE
GENERIC = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "ui-sans-serif", "ui-serif", "ui-monospace", "emoji",
           "math", "fangsong", "inherit", "initial"}
# Bileşen → yazı ağırlıkları (templates/remotion/src/components; bileşen props.fontWeight verirse o da eklenir)
COMPONENT_WEIGHTS = {"LowerThird": (700, 400), "PriceTag": (400, 700), "ReviewCard": (400, 700), "EndCard": (700,), "CTAPulse": (700,),
                     "CaptionTrack": (700,), "TextReveal": (700,), "KineticWords": (700,), "SoftType": (700,), "BehindSubjectText": (700,)}
TEXT_KEYS = ("text", "title", "subtitle", "label", "quote", "displayName", "brand", "cta", "url")  # profil bileşenleri için de yazı alanları
_NOT_TEXT = re.compile(r"^\s*(#[0-9a-fA-F]{3,8}|rgba?\(.*\)|hsla?\(.*\)|-?[\d.]+(em|px|%)?|[\w.-]+\.(png|jpe?g|webp|svg|mp4|mov|wav))\s*$")
_IMPORT = re.compile(r"""(?:\bimport\s+|\bfrom\s+|@import\s+(?:url\()?\s*)["'](@fontsource(?:-variable)?/[^"']+)["']""")
_FACE = re.compile(r"@font-face\s*\{([^}]*)\}", re.S)
_SKIP_CAT = ("Z", "C", "M")  # boşluk, denetim, birleşen işaret
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿︎️‍]")


def _family(s: str | None) -> str:
    return (s or "").split(",")[0].strip().strip("'\"").strip()


def _ranges(spec: str) -> list[tuple[int, int]]:
    out = []
    for part in spec.split(","):
        part = part.strip().upper().removeprefix("U+")
        if not part:
            continue
        if "?" in part:
            out.append((int(part.replace("?", "0"), 16), int(part.replace("?", "F"), 16)))
        elif "-" in part:
            a, b = part.split("-", 1)
            out.append((int(a, 16), int(b.removeprefix("U+"), 16)))
        else:
            out.append((int(part, 16), int(part, 16)))
    return out


def _weights(spec: str) -> tuple[int, int]:
    nums = [int(x) for x in re.findall(r"\d+", spec or "")]
    if not nums:
        return (400, 400) if (spec or "").strip() != "bold" else (700, 700)
    return (nums[0], nums[-1])


def _resolve_css(spec: str, node_modules: Path) -> Path | None:
    p = node_modules / spec
    for cand in (p, p.with_name(p.name + ".css"), p / "index.css"):
        if cand.is_file():
            return cand
    return None


def _subset_of(src: str, unicode_map: dict) -> str | None:
    m = re.search(r"files/([^)'\"\s]+)", src)
    name = m.group(1) if m else src
    hits = [k for k in unicode_map if f"-{k}-" in name]
    return max(hits, key=len) if hits else None


def load_faces(project: Path, node_modules: Path) -> dict:
    """Projede içe aktarılan fontsource CSS'lerinden yüz listesi: [{family, weights, style, ranges, css}]."""
    faces, unresolved, imports = [], [], []
    for f in sorted(project.rglob("*")):
        if f.suffix not in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".css") or not f.is_file() or "node_modules" in f.parts:
            continue
        for spec in _IMPORT.findall(f.read_text(encoding="utf-8", errors="replace")):
            if spec not in imports:
                imports.append(spec)
    for spec in imports:
        css = _resolve_css(spec, node_modules)
        if css is None:
            unresolved.append({"import": spec, "issue": "içe aktarılan font CSS'i node_modules'ta yok (paket kurulmamış ya da yol yanlış)"})
            continue
        pkg_dir = node_modules / "/".join(spec.split("/")[:2])
        try:
            umap = json.loads((pkg_dir / "unicode.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            umap = {}
        for body in _FACE.findall(css.read_text(encoding="utf-8", errors="replace")):
            props = {k.strip().lower(): v.strip() for k, v in re.findall(r"([\w-]+)\s*:\s*([^;]+);?", body)}
            src = props.get("src", "")
            if "unicode-range" in props:
                rng = _ranges(props["unicode-range"])
            else:
                sub = _subset_of(src, umap)
                rng = _ranges(umap[sub]) if sub else [(0, 0x10FFFF)]
            faces.append({"family": _family(props.get("font-family")), "weights": _weights(props.get("font-weight", "400")),
                          "style": props.get("font-style", "normal"), "ranges": rng, "css": f"{spec}"})
    return {"faces": faces, "imports": imports, "unresolved": unresolved}


def _needed(plan: dict, style: dict | None, captions: list | None) -> dict[tuple[str, int], dict[str, set[str]]]:
    """(font, ağırlık) → {karakter: {nerede}}."""
    fonts = {**NEUTRAL_FONTS, **((style or {}).get("fonts") or {})}
    need: dict[tuple[str, int], dict[str, set[str]]] = {}

    def add(fam: str, weights, text: str, where: str) -> None:
        fam = _family(fam) or DEFAULT_FAMILY
        if fam.lower() in GENERIC:
            return
        for w in weights:
            bucket = need.setdefault((fam, int(w)), {})
            for ch in text:
                bucket.setdefault(ch, set()).add(where)

    used: set[str] = set()
    for s in plan.get("scenes", []):
        for i, l in enumerate(s.get("layers", [])):
            props = l.get("props") or {}
            where = f"{s.get('id')}/{i}"
            if l.get("type") == "text":
                fam = props.get("fontFamily") or fonts["display"]
                w = props.get("fontWeight") or fonts.get("displayWeight", 700)
                add(fam, (w,), str(l.get("text") or props.get("text") or props.get("title") or ""), where)
                used.add(_family(fam))
            elif l.get("type") == "component" and (l.get("component") in COMPONENT_WEIGHTS or any(props.get(k) for k in TEXT_KEYS)):
                fam = props.get("fontFamily") or DEFAULT_FAMILY
                ws = set(COMPONENT_WEIGHTS.get(l["component"], (400, 700))) | ({int(props["fontWeight"])} if props.get("fontWeight") else set())
                texts = [v for k, v in props.items() if isinstance(v, str) and not _NOT_TEXT.match(v) and k.lower() not in
                         ("fontfamily", "preset", "align", "locale", "logo", "background", "cutout", "src", "brandtracking")]
                if props.get("price") is not None:
                    texts.append("0123456789.,")
                if props.get("currency"):
                    texts.append(str(props["currency"]))
                add(fam, sorted(ws), " ".join(texts), where)
                used.add(_family(fam))
    if (plan.get("captions") or {}).get("on"):
        body = fonts["body"]
        words = " ".join(str(c.get("text", "")) for c in (captions or []))
        upper = (plan.get("captions") or {}).get("preset") == "keyword_upper"
        add(body, (700,), (words + " " + words.replace("i", "İ").replace("ı", "I").upper()) if upper else words, "altyazı")
        used.add(_family(body))
    for fam in used:
        if fam and fam.lower() not in GENERIC:
            for (f2, w) in [k for k in need if k[0] == fam]:
                for ch in TR_ALPHABET:
                    need[(f2, w)].setdefault(ch, set()).add("Türkçe alfabe")
    return need


def _covers(face: dict, cp: int) -> bool:
    return any(a <= cp <= b for a, b in face["ranges"])


def coverage(plan: dict, style: dict | None, project: str | Path | None, node_modules: str | Path | None, captions: list | None = None) -> dict:
    if not project or not node_modules or not Path(project).is_dir() or not Path(node_modules).is_dir():
        return {"checked": False, "ok": False, "missing": [], "weight_gaps": [], "unresolved": [],
                "reason": "proje (src) ya da node_modules bulunamadı: font glif kapsamı denetlenemedi"}
    fx = load_faces(Path(project), Path(node_modules))
    faces = fx["faces"]
    need = _needed(plan, style, captions)
    missing, gaps, unresolved = [], [], list(fx["unresolved"])
    fam_faces = {}
    for f in faces:
        fam_faces.setdefault(f["family"].lower(), []).append(f)
    lack_by_fam: dict[str, dict] = {}
    for (fam, w), chars in sorted(need.items()):
        ff = fam_faces.get(fam.lower(), [])
        if not ff:
            if not any(u.get("family") == fam for u in unresolved):
                unresolved.append({"family": fam, "issue": f"'{fam}' fontu projede hiç yüklenmiyor (@fontsource içe aktarması yok): "
                                                         "bütün yazı yedek fonta düşer"})
            continue
        loaded_w = sorted({x for f in ff for x in f["weights"]})
        if not any(f["weights"][0] <= w <= f["weights"][1] for f in ff):
            gaps.append({"family": fam, "weight": w, "chars": "", "where": sorted({x for v in chars.values() for x in v} - {"Türkçe alfabe"}),
                         "issue": f"'{fam}' {w} ağırlığı yüklenmiyor (yüklü: {', '.join(map(str, loaded_w))}) → tarayıcı başka ağırlıkla çizer"})
            weight_ok = False
        else:
            weight_ok = True
        wlack = {}
        for ch, wheres in chars.items():
            cp = ord(ch)
            if unicodedata.category(ch)[0] in _SKIP_CAT or _EMOJI.match(ch):
                continue
            if not any(_covers(f, cp) for f in ff):
                e = lack_by_fam.setdefault(fam, {"chars": set(), "where": set(), "weights": set()})
                e["chars"].add(ch)
                e["where"] |= set(wheres)
                e["weights"].add(w)
            elif weight_ok and not any(_covers(f, cp) and f["weights"][0] <= w <= f["weights"][1] for f in ff):
                wlack[ch] = sorted(wheres)
        if wlack:
            gaps.append({"family": fam, "weight": w, "chars": "".join(sorted(wlack)), "where": sorted({x for v in wlack.values() for x in v}),
                         "issue": f"'{fam}' {w} ağırlığında {''.join(sorted(wlack))} yok → başka ağırlıkla çizilir"})
    for fam, e in sorted(lack_by_fam.items()):
        chars = "".join(sorted(e["chars"]))
        missing.append({"family": fam, "weights": sorted(e["weights"]), "chars": chars, "where": sorted(e["where"]),
                        "issue": f"'{fam}': {chars} yüklenen yüzlerde yok → yedek fonta düşer (latin-ext alt kümesi içe aktarılmamış olabilir; "
                                 f"yer: {', '.join(sorted(e['where']))})"})
    return {"checked": True, "ok": not missing and not unresolved, "missing": missing, "weight_gaps": gaps, "unresolved": unresolved,
            "families": sorted({k[0] for k in need}), "imports": fx["imports"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--project", required=True, help="kampanyanın Remotion projesi (<kampanya>/src)")
    ap.add_argument("--data-dir", required=True, help="DD; node_modules = DD/.node/node_modules")
    ap.add_argument("--style")
    ap.add_argument("--captions", help="altyazı parçaları (captions.words.json)")
    a = ap.parse_args()
    caps = read_json(a.captions) if a.captions else None
    if isinstance(caps, dict):
        caps = caps.get("captions") or caps.get("segments") or []
    r = coverage(read_json(a.plan), read_json(a.style) if a.style else None, a.project, Path(a.data_dir) / ".node" / "node_modules", caps)
    emit(r)
    sys.exit(0 if r["ok"] else 1)


if __name__ == "__main__":
    main()
