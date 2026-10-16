"""SQLite bağlantısı, pragmalar ve numaralı migration'lar (7.4)."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from .util import now_iso

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
SCHEMA_VERSION = max(int(p.name.split("_")[0]) for p in MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))


def connect(db_path: str | Path) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=5.0, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_meta'").fetchone()
    if not row:
        return 0
    v = conn.execute("SELECT MAX(version) FROM schema_meta").fetchone()[0]
    return int(v or 0)


def pending_migrations(conn: sqlite3.Connection) -> list[Path]:
    cur = current_version(conn)
    files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))
    return [f for f in files if int(f.name.split("_")[0]) > cur]


def migrate(conn: sqlite3.Connection, backup_fn=None) -> list[str]:
    """Bekleyen migration'ları sırayla uygular. Her migration öncesi (boş olmayan veritabanında) yedek alınır."""
    applied: list[str] = []
    for f in pending_migrations(conn):
        if backup_fn is not None and current_version(conn) > 0:
            backup_fn(reason=f"migration-{f.stem}")
        sql = f.read_text(encoding="utf-8")
        version = int(f.name.split("_")[0])
        conn.execute("BEGIN IMMEDIATE")
        try:
            for stmt in _split_sql(sql):
                conn.execute(stmt)
            conn.execute("INSERT INTO schema_meta(version, applied_at) VALUES (?, ?)", (version, now_iso()))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        applied.append(f.name)
    return applied


def _split_sql(sql: str) -> list[str]:
    # Satır yorumlarını at, ';' ile böl (şemada tetikleyici gövdesi yok).
    lines = [re.sub(r"--.*$", "", ln) for ln in sql.splitlines()]
    text = "\n".join(lines)
    return [s.strip() for s in text.split(";") if s.strip()]
