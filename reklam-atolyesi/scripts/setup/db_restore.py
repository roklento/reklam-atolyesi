"""Veritabanı sağlık denetimi ve yedekten geri dönüş (2.0.0).

Haftalık ve her migration öncesi yedekler `<data_dir>/backups/ad-memory-<zaman>-<neden>.sqlite` olarak alınır (son 8). Bu araç:
  check   --data-dir DD                         veritabanının ve her yedeğin bütünlüğü (salt okuma)
  restore --data-dir DD --backup <dosya> --confirm
          seçilen yedeği geri koyar. Önce Claude Code kapatılır (açık veritabanı Windows'ta taşınamaz; araç bunu söyler ve durur).
          Mevcut veritabanı silinmez: `db/onceki-<zaman>/` altına taşınır. Yedekten sonra yapılan kayıtlar geri gelmez; kullanıcı
          hangi yedeği seçtiğini ve tarihini görerek onaylar.
"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit  # noqa: E402


def quick_check(path: Path) -> str:
    try:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=3)
        try:
            r = con.execute("PRAGMA quick_check").fetchone()[0]
            v = con.execute("SELECT MAX(version) FROM schema_meta").fetchone()[0]
        finally:
            con.close()
        return "ok" if r == "ok" and v else (r if r != "ok" else "şema sürümü okunamadı")
    except sqlite3.Error as e:
        return f"açılamadı: {e}"


def schema_version(path: Path) -> int | None:
    try:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=3)
        try:
            return int(con.execute("SELECT MAX(version) FROM schema_meta").fetchone()[0] or 0)
        finally:
            con.close()
    except sqlite3.Error:
        return None


def check(data_dir: Path) -> dict:
    db = data_dir / "db" / "ad-memory.sqlite"
    backups = sorted((data_dir / "backups").glob("ad-memory-*.sqlite"), reverse=True)
    return {"db": {"path": str(db), "exists": db.exists(), "check": quick_check(db) if db.exists() else None},
            "backups": [{"path": str(b), "taken": b.name[10:26], "bytes": b.stat().st_size, "check": quick_check(b),
                         "schema_version": schema_version(b)} for b in backups],
            "note": "Geri dönüş: restore --backup <dosya> --confirm (önce Claude Code kapatılır)."}


def restore(data_dir: Path, backup: Path, confirm: bool) -> dict:
    dbdir = data_dir / "db"
    db = dbdir / "ad-memory.sqlite"
    backup = backup.resolve()
    if not backup.is_file():
        raise SystemExit(f"yedek bulunamadı: {backup}")
    if (data_dir / "backups").resolve() not in backup.parents:
        raise SystemExit("yalnızca <data_dir>/backups altındaki yedekler geri konur")
    st = quick_check(backup)
    if st != "ok":
        raise SystemExit(f"yedek bütünlük denetiminden geçmedi ({st}); başka bir yedek seçin (check)")
    if not confirm:
        return {"dry_run": True, "backup": str(backup), "taken": backup.name[10:26],
                "note": "Bu yedekten sonra yapılan kayıtlar geri gelmez. Kullanıcı onaylarsa --confirm ile yeniden çalıştırın."}
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    keep = dbdir / f"onceki-{stamp}"
    keep.mkdir(parents=True, exist_ok=False)
    moved = []
    try:
        for suffix in ("", "-wal", "-shm"):
            f = dbdir / f"ad-memory.sqlite{suffix}"
            if f.exists():
                f.replace(keep / f.name)
                moved.append(f.name)
    except PermissionError:
        for name in moved:  # yarım taşımayı geri al
            (keep / name).replace(dbdir / name)
        keep.rmdir()
        raise SystemExit("veritabanı kullanımda: Claude Code'u (bütün pencereleri) kapatıp yeniden deneyin; hiçbir şey değiştirilmedi")
    tmp = dbdir / "ad-memory.sqlite.restore-tmp"
    shutil.copy2(backup, tmp)
    tmp.replace(db)
    return {"restored": True, "from": str(backup), "previous_kept_in": str(keep), "moved": moved, "check": quick_check(db),
            "note": "Claude Code yeniden açıldığında sunucu gerekiyorsa şemayı günceller (migration öncesi yine yedek alınır)."}


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--data-dir", required=True)
    r = sub.add_parser("restore")
    r.add_argument("--data-dir", required=True)
    r.add_argument("--backup", required=True)
    r.add_argument("--confirm", action="store_true")
    a = ap.parse_args()
    dd = Path(a.data_dir).resolve()
    out = check(dd) if a.cmd == "check" else restore(dd, Path(a.backup), a.confirm)
    emit(out)


if __name__ == "__main__":
    main()
