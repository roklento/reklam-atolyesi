"""Kurgu planı doğrulama (spec 5.2). Tek doğrulama kaynağı admem.editplan'dır (ad-memory ile aynı kod).

Kullanım: validate_plan.py <plan.json> [--style style.json] [--beats beats.json] [--assets asset_index.json]
          validate_plan.py --export-schema <hedef.json>   (JSON şemasını dışa aktarır)
Çıkış kodu: 0 geçerli, 1 geçersiz.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit, read_json, write_json  # noqa: E402
from admem import editplan  # noqa: E402


def load_beats(p: str | None) -> list[float] | None:
    if not p:
        return None
    b = read_json(p)
    if isinstance(b, dict):
        return [float(x) for x in (b.get("locks") or b.get("beats") or [])]
    return [float(x) for x in b]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("plan", nargs="?")
    ap.add_argument("--style")
    ap.add_argument("--beats")
    ap.add_argument("--assets")
    ap.add_argument("--export-schema")
    a = ap.parse_args()
    if a.export_schema:
        write_json(a.export_schema, editplan.SCHEMA)
        emit({"schema": a.export_schema})
        return
    plan = read_json(a.plan)
    rep = editplan.validate(plan, style=read_json(a.style) if a.style else None, beats=load_beats(a.beats),
                            asset_index=read_json(a.assets) if a.assets else None)
    emit(rep)
    sys.exit(0 if rep["valid"] else 1)


if __name__ == "__main__":
    main()
