#!/usr/bin/env python3
"""Ezber denetimi (2.10.0, admin tarafı; CI her push ve PR'da çalıştırır).

Neden: sahadan gelen bir hatayı düzeltirken vakanın cümlesini ya da adını plugin'in kendi metnine yazmak kolaydır. Böyle bir
düzeltme vakayı geçer ama yeni müşteride işe yaramaz: plugin vakayı ezberlemiş olur. Bu betik, plugin metnine bu sürümde EKLENEN
satırlarda bir vakadan birebir alınmış KELIME_ESIGI kelimelik bir parça ya da bir vaka klasörünün adı var mı diye bakar.

Yalnızca eklenen satırlara bakılır: bir vaka plugin'in mevcut bir cümlesini durum olarak alıntılayabilir (ör. hata defteri sorusu).
O zaman alıntı yapan vakadır, plugin değil. Vaka plugin'den bilerek alıntı yapıyorsa senaryo-matrisi.json'daki kaydına
`"alinti": [...]` ile alıntılanan plugin cümleleri tek tek yazılır (vaka dosyalarının biçimine dokunulmaz). Yalnızca bu
cümlelerin içinde kalan eşleşmeler raporda gösterilir ama denetimi kırmızıya çevirmez; aynı vakadan gelen başka her eşleşme ve
vaka adının kendisi yine engeller (2.10.1; önceki `"alinti": true` vakanın bütün eşleşmelerini serbest bırakıyordu).

Sınırı: yalnızca kelime kopyasını yakalar. "Fiyat 100 TL ise şunu yap" gibi vakaya özgü mantığı yakalayamaz; onun için
etki-defteri.md'deki "Gerekçe" sütunu kullanılır.

Kullanım:
    python evals/ezber_denetimi.py                  # fark: origin/main ile ortak atadan bu yana (main'in kendisinde: son commit)
    python evals/ezber_denetimi.py --taban <commit> # fark: verilen commit'ten bu yana
    python evals/ezber_denetimi.py --hepsi          # bütün mevcut metin (bilgi amaçlı; çıkış kodu her zaman 0)
Çıkış kodu: 0 = temiz, 1 = ezber şüphesi var, 2 = git farkı alınamadı.

Yöntem: RRSI (arXiv 2609.24972) "eleştirmen" fikri; metin ve kod bu depoya özgüdür, dışarıdan kopyalanmadı.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = ROOT.parent
KELIME_ESIGI = 6
CASE_DIRS = ("vakalar", "kapali")
# Plugin'in davranışını belirleyen metinler (müşteri oturumunda modele ya da kullanıcıya giden).
WATCHED = ("KURALLAR.md", "skills/*.md", "skills/**/*.md", "agents/*.md", "commands/*.md", "hooks/*.py", "hooks/*.json",
           "templates/reports/*.md", "workflows/*")
WORD = re.compile(r"[0-9a-zçğıöşüâîû]+")


def tr_lower(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower().replace("i̇", "i")


def words(s: str) -> list[str]:
    return WORD.findall(tr_lower(s))


def _front(text: str) -> tuple[str, str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.S)
    return (m.group(1), text[m.end():]) if m else ("", text)


def load_cases(root: Path = ROOT) -> dict[str, dict]:
    """{vaka adı: {"grams": {6-kelime: dosya}, "alinti": {onaylı 6-kelime}}} — açık (vakalar/) ve kapalı (kapali/) vakalar."""
    out: dict[str, dict] = {}
    mf = root / "evals" / "senaryo-matrisi.json"
    matrix = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
    quoting: dict[str, set] = {}
    for key in ("eval_cases", "kapali_cases"):
        for n, c in (matrix.get(key) or {}).items():
            q = c.get("alinti")
            if isinstance(q, list):  # yalnızca cümle listesi geçerli; true gibi toptan izin yok sayılır
                quoting[n] = {tuple(w[i:i + KELIME_ESIGI]) for t in q if isinstance(t, str)
                              for w in [words(t)] for i in range(len(w) - KELIME_ESIGI + 1)}
    for sub in CASE_DIRS:
        base = root / "evals" / sub
        if not base.is_dir():
            continue
        for case in sorted(p for p in base.iterdir() if p.is_dir()):
            info = {"grams": {}, "alinti": quoting.get(case.name, set()), "grup": "kapalı" if sub == "kapali" else "açık"}
            files = [case / "prompt.md"] + sorted((case / "graders").glob("*.md"))
            for f in files:
                if not f.exists():
                    continue
                _, body = _front(f.read_text(encoding="utf-8"))
                w = words(body)
                for i in range(len(w) - KELIME_ESIGI + 1):
                    info["grams"].setdefault(tuple(w[i:i + KELIME_ESIGI]), f.relative_to(root).as_posix())
            out[case.name] = info
    return out


def watched(rel: str) -> bool:
    return any(fnmatch.fnmatch(rel, pat) for pat in WATCHED)


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, check=True).stdout


def default_base() -> str:
    head = _git("rev-parse", "HEAD").strip()
    for ref in ("origin/main", "main"):
        try:
            mb = _git("merge-base", "HEAD", ref).strip()
        except subprocess.CalledProcessError:
            continue
        return mb if mb != head else _git("rev-parse", "HEAD~1").strip()
    raise RuntimeError("origin/main bulunamadı; --taban verin")


def added_lines(base: str) -> list[tuple[str, int, str]]:
    """[(plugin köküne göre yol, satır no, satır)] — base'den bu yana eklenen satırlar (çalışma kopyası dahil)."""
    prefix = ROOT.relative_to(REPO).as_posix() + "/"
    diff = _git("diff", "--unified=0", "--no-color", "--no-renames", base, "--", ROOT.relative_to(REPO).as_posix())
    out, path, ln = [], None, 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            p = line[4:]
            path = p[2 + len(prefix):] if p.startswith("b/" + prefix) else None
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            ln = int(m.group(1)) if m else 0
        elif line.startswith("+") and path and watched(path):
            out.append((path, ln, line[1:]))
            ln += 1
        elif line.startswith("+"):
            ln += 1
    return out


def all_lines(root: Path = ROOT) -> list[tuple[str, int, str]]:
    out = []
    for f in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = f.relative_to(root).as_posix()
        if not watched(rel):
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            out.append((rel, i, line))
    return out


def find(lines: list[tuple[str, int, str]], cases: dict[str, dict]) -> list[dict]:
    """Satırlarda vaka parçası ya da vaka adı. Ardışık satırlar birlikte taranır (cümle satır sonunda bölünmüş olabilir)."""
    gram_owner: dict[tuple, tuple[str, str]] = {}
    for name, info in cases.items():
        for g, src in info["grams"].items():
            gram_owner.setdefault(g, (name, src))
    hits: dict[tuple, dict] = {}
    by_file: dict[str, list[tuple[int, str]]] = {}
    for path, ln, text in lines:
        by_file.setdefault(path, []).append((ln, text))
    names = {n: re.compile(r"(?<![\w-])" + re.escape(n) + r"(?![\w-])", re.I) for n in cases}
    for path, rows in by_file.items():
        for idx, (ln, text) in enumerate(rows):
            for n, rx in names.items():
                if rx.search(text):
                    hits.setdefault((path, ln, n), {"dosya": path, "satir": ln, "vaka": n, "tur": "vaka adı",
                                                   "parca": n, "alinti": False, "grup": cases[n]["grup"]})
            nxt = rows[idx + 1] if idx + 1 < len(rows) and rows[idx + 1][0] == ln + 1 else None
            w = words(text)
            span = w + (words(nxt[1]) if nxt else [])
            for i in range(min(len(w), max(0, len(span) - KELIME_ESIGI + 1))):
                g = tuple(span[i:i + KELIME_ESIGI])
                if g in gram_owner:
                    n, src = gram_owner[g]
                    key = (path, ln, n)
                    if key not in hits:
                        hits[key] = {"dosya": path, "satir": ln, "vaka": n, "tur": "birebir parça", "parca": " ".join(g),
                                     "kaynak": src, "alinti": g in cases[n]["alinti"], "grup": cases[n]["grup"]}
    return sorted(hits.values(), key=lambda h: (h["dosya"], h["satir"], h["vaka"]))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plugin metnine vakadan kopya girdi mi? (admin, CI)")
    ap.add_argument("--taban", help="farkın başlangıç commit'i (varsayılan: origin/main ile ortak ata)")
    ap.add_argument("--hepsi", action="store_true", help="bütün mevcut metni tara (bilgi amaçlı)")
    a = ap.parse_args(argv)
    cases = load_cases()
    if a.hepsi:
        lines = all_lines()
    else:
        try:
            base = a.taban or default_base()
            lines = added_lines(base)
        except (subprocess.CalledProcessError, RuntimeError, FileNotFoundError) as e:
            print(f"Git farkı alınamadı: {e}. CI'da checkout tüm geçmişi almalı (fetch-depth: 0).", file=sys.stderr)
            return 2
    hits = find(lines, cases)
    blocking = [h for h in hits if not h["alinti"]]
    scope = "bütün metin" if a.hepsi else f"eklenen {len(lines)} satır"
    if not hits:
        print(f"Ezber denetimi temiz ({scope}, {len(cases)} vaka).")
        return 0
    print(f"Ezber denetimi ({scope}, {len(cases)} vaka): {len(hits)} eşleşme, {len(blocking)} tanesi engelleyici.\n")
    for h in hits:
        etiket = "alıntı vakası, engellemez" if h["alinti"] else "ENGELLER"
        print(f"- {h['dosya']}:{h['satir']} · {h['grup']} vaka {h['vaka']} · {h['tur']}: \"{h['parca']}\" ({etiket})")
    if blocking and not a.hepsi:
        print("\nNe yapılır: düzeltmeyi vakanın kelimeleriyle değil, genel bir kural olarak yeniden yazın. Vaka plugin'in bu cümlesini "
              "bilerek alıntılıyorsa senaryo-matrisi.json'daki kaydına \"alinti\" listesine o plugin cümlesini ekleyin.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
