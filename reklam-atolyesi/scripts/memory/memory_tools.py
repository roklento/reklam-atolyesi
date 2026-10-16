"""Hafıza yardımcıları (spec 8.7) — SALT OKUMA önizlemeleri. Yazmalar (birleştirme, katlama, dışa aktarım) ad-memory araçlarıyla
yapılır (memory_merge, journal_fold, export_markdown); script'ler veritabanına yazmaz (7.4).

Alt komutlar:
  consolidation-preview --data-dir D [--profile-id N]   aday grupları (aynı katman/kapsam, etiket örtüşmesi, trigram benzerliği)
  usage-report          --data-dir D [--profile-id N]   en çok yer kaplayan ama en az kullanılan öğeler (8.7, "Sistem ve hesap durumu")
  fold-preview          --data-dir D [--profile-id N]   90 günden eski katlanmamış günlük kaydı sayısı
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit  # noqa: E402
from admem.util import trigram_similarity  # noqa: E402


def ro(data_dir: str) -> sqlite3.Connection:
    p = Path(data_dir) / "db" / "ad-memory.sqlite"
    con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def consolidation_preview(data_dir: str, pid: int | None, sim: float = 0.45) -> dict:
    con = ro(data_dir)
    rows = [dict(r) for r in con.execute("SELECT * FROM memory_items WHERE profile_id IS ? AND status IN ('proposed','active','due_revalidation')", (pid,))]
    groups, seen = [], set()
    for i, a in enumerate(rows):
        if a["id"] in seen:
            continue
        g = [a] + [b for b in rows[i + 1:] if b["id"] not in seen and b["layer"] == a["layer"] and trigram_similarity(a["content"], b["content"]) >= sim]
        if len(g) > 1:
            seen |= {x["id"] for x in g}
            groups.append([{"id": x["id"], "content": x["content"]} for x in g])
    return {"groups": groups[:10]}


def usage_report(data_dir: str, pid: int | None) -> dict:
    con = ro(data_dir)
    rows = [dict(r) for r in con.execute("SELECT id, layer, length(content) AS size, use_count, last_used_at, status FROM memory_items WHERE profile_id IS ? ORDER BY size DESC", (pid,))]
    heavy_unused = [r for r in rows if (r["use_count"] or 0) == 0][:10]
    return {"items": len(rows), "largest_unused": heavy_unused}


def fold_preview(data_dir: str, pid: int | None) -> dict:
    con = ro(data_dir)
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    n = con.execute("SELECT COUNT(*) FROM journal WHERE profile_id IS ? AND rolled=0 AND ts<?", (pid, cutoff)).fetchone()[0]
    return {"foldable": n, "cutoff": cutoff}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["consolidation-preview", "usage-report", "fold-preview"])
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--profile-id", type=int)
    a = ap.parse_args()
    fn = {"consolidation-preview": consolidation_preview, "usage-report": usage_report, "fold-preview": fold_preview}[a.cmd]
    emit(fn(a.data_dir, a.profile_id))


if __name__ == "__main__":
    main()
