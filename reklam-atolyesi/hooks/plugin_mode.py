"""reklam-atolyesi hook'larının ortak yardımcısı (spec 13.6). Yalnızca standart kütüphane.

Kapsam kuralı: plugin kullanıcı düzeyinde kurulu olduğu için hook'lar her oturumda tetiklenir; her hook önce oturumun plugin
modunda olup olmadığına bakar (data_dir/.sessions/<session_id>.json) ve modun kapalı olduğu doğrulanmışsa hiçbir şey yapmaz.
Tek istisna: plugin'in kendi meta-ads sunucusuna gelen çağrılar her zaman izin listesinden geçer.
Bu dosyada makineye özgü gömülü/varsayılan yol yoktur; data_dir yalnızca --data-dir argümanından gelir.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

PLUGIN_NAME = "reklam-atolyesi"
OWN_SERVER_PREFIX = "mcp__plugin_reklam-atolyesi_"
OWN_META_PREFIX = "mcp__plugin_reklam-atolyesi_meta-ads__"
OWN_ELEVEN_PREFIX = "mcp__plugin_reklam-atolyesi_ElevenLabs__"
HOOKS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = HOOKS_DIR.parent
TRIGGERS = {"reklam-atolyesi", "reklam atolyesi", "reklamatolyesi", "reklam-atölyesi", "reklam atölyesi"}
EXIT_WORDS = {"çık", "cik", "menüden çık", "menuden cik", "plugin modundan çık", "plugin modundan cik"}


class ConfigError(Exception):
    pass


def read_input() -> dict:
    raw = sys.stdin.buffer.read()
    if not raw:
        raise ConfigError("boş hook girdisi")
    return json.loads(raw.decode("utf-8"))


def data_dir_from_argv(argv: list[str] | None = None) -> Path:
    argv = sys.argv[1:] if argv is None else argv
    val = None
    for i, a in enumerate(argv):
        if a == "--data-dir" and i + 1 < len(argv):
            val = argv[i + 1]
        elif a.startswith("--data-dir="):
            val = a.split("=", 1)[1]
    if not val:
        val = os.environ.get("CLAUDE_PLUGIN_OPTION_DATA_DIR") or ""
    if not val or "${" in val:
        raise ConfigError("data_dir yapılandırılmadı (userConfig.data_dir)")
    p = Path(val)
    if not p.is_dir():
        raise ConfigError(f"data_dir yok: {p}")
    return p


def tr_norm(s: str) -> str:
    s = (s or "").replace("I", "ı").replace("İ", "i").lower()
    s = unicodedata.normalize("NFC", s.replace("i̇", "i"))
    s = re.sub(r"[\s]+", " ", s).strip()
    return s.strip(" .!?…'\"`")


def fold(s: str) -> str:
    t = tr_norm(s).translate(str.maketrans({"ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c"}))
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))


def is_trigger(prompt: str) -> bool:
    p = tr_norm(prompt)
    return p in TRIGGERS or fold(p) in {fold(t) for t in TRIGGERS}


def is_command(prompt: str) -> str | None:
    m = re.match(r"^\s*/reklam-atolyesi:([a-z0-9-]+)(.*)$", prompt or "", re.S)
    return m.group(1) if m else None


def is_exit(prompt: str) -> bool:
    return tr_norm(prompt) in EXIT_WORDS or fold(prompt) in {fold(w) for w in EXIT_WORDS}


def valid_sid(sid: str | None) -> bool:
    return bool(sid) and re.fullmatch(r"[A-Za-z0-9_.-]{4,128}", sid) is not None


def session_path(data_dir: Path, sid: str) -> Path:
    if not valid_sid(sid):
        raise ConfigError("oturum kimliği çözülemedi")
    return data_dir / ".sessions" / f"{sid}.json"


def load_session(data_dir: Path, sid: str) -> dict | None:
    """None: dosya yok (mod kapalı doğrulandı). ConfigError: dosya bozuk (mod belirlenemedi)."""
    p = session_path(data_dir, sid)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise ConfigError(f"oturum dosyası okunamadı: {e}")


def save_session(data_dir: Path, sid: str, data: dict) -> None:
    p = session_path(data_dir, sid)
    p.parent.mkdir(parents=True, exist_ok=True)
    data["session_id"] = sid
    fd, tmp = tempfile.mkstemp(prefix=f".{p.name}.", suffix=".tmp", dir=str(p.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def file_lock(path: str | os.PathLike, timeout: float = 3.0, stale: float = 10.0):
    """Süreçler arası kısa kilit (oturum dosyası oku-değiştir-yaz için; hook ve MCP sunucusu aynı dosyayı yazar). O_EXCL kilit dosyası
    her işletim sisteminde aynı davranır. 10 sn'den eski kilit ölü sayılır; 3 sn içinde alınamazsa kilitsiz devam edilir (hook süresi
    sınırlı; en kötü durum 2.0.0 öncesi davranıştır)."""
    import contextlib
    import time

    @contextlib.contextmanager
    def _cm():
        lock = Path(str(path) + ".lock")
        lock.parent.mkdir(parents=True, exist_ok=True)
        fd, t0 = None, time.monotonic()
        while fd is None:
            try:
                fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    if time.time() - lock.stat().st_mtime > stale:
                        lock.unlink(missing_ok=True)
                        continue
                except OSError:
                    continue
                if time.monotonic() - t0 > timeout:
                    break
                time.sleep(0.02)
        try:
            yield fd is not None
        finally:
            if fd is not None:
                os.close(fd)
                try:
                    lock.unlink(missing_ok=True)
                except OSError:
                    pass
    return _cm()


def update_session(data_dir: Path, sid: str, fn) -> dict:
    """Kilit altında oku → fn(oturum) → yaz (2.0.0: paralel araç çağrılarında hook ile MCP sunucusu birbirinin yazdığını silmesin)."""
    with file_lock(session_path(data_dir, sid)):
        sess = load_session(data_dir, sid) or {}
        fn(sess)
        save_session(data_dir, sid, sess)
        return sess


def plugin_mode(data_dir: Path, sid: str) -> bool:
    s = load_session(data_dir, sid)
    return bool(s and s.get("plugin_mode"))


def db_path(data_dir: Path) -> Path:
    return data_dir / "db" / "ad-memory.sqlite"


def ro_db(data_dir: Path) -> sqlite3.Connection | None:
    p = db_path(data_dir)
    if not p.exists():
        return None
    con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True, timeout=3)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=3000")
    return con


def emit(obj: dict) -> None:
    # ASCII kaçışlı JSON: host hook'u PYTHONIOENCODING olmadan başlatır; Windows'ta stdout kod sayfası (cp1254) UTF-8 değildir ve
    # Türkçe karakterler bozulur. \uXXXX kaçışları her kod sayfasında aynı baytlardır, host JSON'u çözünce metin doğru gelir.
    sys.stdout.write(json.dumps(obj, ensure_ascii=True))
    sys.stdout.flush()


def deny(reason: str) -> None:
    emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                 "permissionDecisionReason": f"[reklam-atolyesi] {reason}"}})


def context(event: str, text: str) -> None:
    emit({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}})


def bare_tool(tool_name: str) -> str:
    return tool_name.rsplit("__", 1)[-1] if "__" in tool_name else tool_name


def runtime_item(data_dir: Path, item_id: str, scope: str = "common") -> dict | None:
    con = ro_db(data_dir)
    if con is None:
        return None
    try:
        r = con.execute("SELECT value FROM settings WHERE key='runtime_verification_json'").fetchone()
        if not r or not r["value"]:
            return None
        return (json.loads(r["value"]).get("items") or {}).get(f"{item_id}@{scope}")
    finally:
        con.close()


def setup_hint() -> str:
    return "Kurulumu kontrol edin: plugin ayarlarında data_dir ve <data_dir>/.venv mevcut olmalı (doctor.py)."
