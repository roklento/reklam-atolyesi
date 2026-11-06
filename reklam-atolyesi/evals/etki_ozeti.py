#!/usr/bin/env python3
"""Etki defteri özeti (2.10.0, admin tarafı): silmeye aday ve ölçülmemiş bileşenler.

Neden: plugin her revizede büyür. Bir kural ya da skill bölümü birkaç sürüm boyunca hiçbir vakada fark yaratmadıysa onu taşımak
her müşteri oturumunda boşuna yer kaplar. Bu betik etki-defteri.md'deki tabloları okur ve iki liste verir:

    Silmeye aday : en az ETKISIZ_ESIGI sürümde "etkisiz" yazılmış ve hiç "yardım etti" almamış bileşenler.
    Ölçülmemiş   : en az OLCULMEMIS_ESIGI sürümde "ölçülecek" diye kalmış ve hiç sonuç almamış bileşenler.
    Eval kanıtı yok (2.10.2): kararı yalnız birim testine ("yardım etti (test)") ya da bekleyen ölçüme dayanan bileşenler.

Betik hiçbir şeyi silmez; silme kararı admin'indir. "silindi" kararı almış bileşen listelere girmez.

Kullanım: python evals/etki_ozeti.py [--defter evals/etki-defteri.md]
Yöntem: RRSI (arXiv 2609.24972) "budama" fikri; metin ve kod bu depoya özgüdür.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ETKISIZ_ESIGI = 2
OLCULMEMIS_ESIGI = 3
SECTION = re.compile(r"^## (\d+\.\d+\.\d+)\b", re.M)


def _decision(cell: str) -> str | None:
    c = cell.lower()
    for key in ("silindi", "yardım etti", "bozdu", "karışık", "etkisiz", "ölçülecek"):
        if key in c:
            return key
    return None


def _components(cell: str) -> list[str]:
    items = re.findall(r"`([^`]+)`", cell)
    rest = re.sub(r"\([^)]*\)?", "", re.sub(r"`[^`]+`", "", cell))  # 2.10.2: parantez içi açıklama ve ok bileşen sayılmaz
    items += [x.strip(" +,→") for x in re.split(r",|\+|→", rest) if x.strip(" +,→")]
    return [i for i in items if i and i != "—" and re.search(r"\w", i)]


def parse(text: str) -> dict[str, dict]:
    """{bileşen: {"surumler": {sürüm: karar}}} — yalnızca sürüm bölümlerindeki 'Bileşen' tabloları okunur."""
    out: dict[str, dict] = {}
    marks = list(SECTION.finditer(text))
    for i, m in enumerate(marks):
        body = text[m.end():marks[i + 1].start() if i + 1 < len(marks) else len(text)]
        header = None
        for line in body.splitlines():
            if not line.startswith("|"):
                header = None if not line.strip() else header
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if cells and cells[0] == "Bileşen":
                header = [c.lower() for c in cells]
                continue
            if header is None or set(line.replace("|", "").strip()) <= {"-", " "}:
                continue
            karar = cells[header.index("karar")] if "karar" in header and len(cells) == len(header) else cells[-1]
            d = _decision(karar)
            if not d:
                continue
            for comp in _components(cells[0]):
                e = out.setdefault(comp, {"surumler": {}, "yalniz_test": set()})
                e["surumler"][m.group(1)] = d
                if d == "yardım etti" and "(test)" in karar.lower():
                    e["yalniz_test"].add(m.group(1))
    return out


def summarize(data: dict[str, dict]) -> dict[str, list[tuple[str, list[str]]]]:
    aday, olc, kanitsiz = [], [], []
    for comp, info in sorted(data.items()):
        vals = info["surumler"]
        decisions = set(vals.values())
        if "silindi" in decisions:
            continue
        # 2.10.2: eval ya da sahayla ölçülmüş karar yoksa (yalnız birim testi ya da bekleyen ölçüm) ayrı listelenir; "ölçülmemiş yok"
        # bütün bileşenlerin ölçüldüğü anlamına gelmez
        olculen = [v for v, d in vals.items() if d in ("bozdu", "etkisiz", "karışık")
                   or (d == "yardım etti" and v not in info.get("yalniz_test", set()))]
        if not olculen:
            kanitsiz.append((comp, sorted(vals)))
        etkisiz = [v for v, d in vals.items() if d == "etkisiz"]
        if len(etkisiz) >= ETKISIZ_ESIGI and "yardım etti" not in decisions:
            aday.append((comp, sorted(etkisiz)))
        bekleyen = [v for v, d in vals.items() if d == "ölçülecek"]
        if len(bekleyen) >= OLCULMEMIS_ESIGI and decisions <= {"ölçülecek"}:
            olc.append((comp, sorted(bekleyen)))
    return {"silmeye_aday": aday, "olculmemis": olc, "eval_kaniti_yok": kanitsiz}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Etki defterinden silmeye aday ve ölçülmemiş bileşenler (admin).")
    ap.add_argument("--defter", default=str(HERE / "etki-defteri.md"))
    a = ap.parse_args(argv)
    data = parse(Path(a.defter).read_text(encoding="utf-8"))
    s = summarize(data)
    print(f"Etki defterinde {len(data)} bileşen okundu.\n")
    print(f"Silmeye aday (en az {ETKISIZ_ESIGI} sürüm etkisiz, hiç yardım etmemiş):")
    print("\n".join(f"- {c} · {', '.join(v)}" for c, v in s["silmeye_aday"]) or "- yok")
    print(f"\nÖlçülmemiş (en az {OLCULMEMIS_ESIGI} sürüm 'ölçülecek'):")
    print("\n".join(f"- {c} · {', '.join(v)}" for c, v in s["olculmemis"]) or "- yok")
    print(f"\nEval ya da sahayla henüz ölçülmemiş ({len(s['eval_kaniti_yok'])} bileşen; yalnız birim testi ya da bekleyen ölçüm):")
    print("\n".join(f"- {c} · {', '.join(v)}" for c, v in s["eval_kaniti_yok"]) or "- yok")
    print("\nNot: 'yardım etti (test)' yalnız kodun beklendiği gibi çalıştığını gösterir; müşteriye faydanın kanıtı değildir.")
    print("\nBu betik hiçbir şeyi silmez. Silme kararı admin'indir; silinen parça etki defterine 'silindi' diye yazılır.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
