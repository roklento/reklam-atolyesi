"""Script'lerin ortak yardımcıları: araç yolları, alt süreç, JSON G/Ç, data_dir ve plugin kökü, güvenli silme.

Script'ler SQLite'a doğrudan yazmaz (okuma serbest; 7.4). Bütün yollar argümanla gelir; makineye özgü gömülü yol yoktur.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLUGIN_ROOT / "servers" / "ad_memory"))

from admem.util import atomic_write, sha256_file  # noqa: E402  (aynı kod: 4.2 atomik yazma)


class ToolMissing(RuntimeError):
    pass


def tool(name: str) -> str:
    p = shutil.which(name)
    if not p:
        raise ToolMissing(f"{name} PATH'te bulunamadı (kurulum gereksinimi, 12.2)")
    return p


def run(cmd: list[str], *, timeout: float | None = None, check: bool = True, cwd: str | None = None,
        env: dict | None = None) -> subprocess.CompletedProcess:
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, cwd=cwd, env=env)
    if check and r.returncode != 0:
        raise RuntimeError(f"komut başarısız ({r.returncode}): {' '.join(map(str, cmd))[:400]}\n{r.stderr[-2000:]}")
    return r


def ffmpeg(args: list[str], **kw) -> subprocess.CompletedProcess:
    return run([tool("ffmpeg"), "-hide_banner", "-nostdin", "-y", *args], **kw)


def ffprobe_json(path: str | Path) -> dict:
    r = run([tool("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    return json.loads(r.stdout or "{}")


def read_json(p: str | Path) -> Any:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def write_json(p: str | Path, obj: Any, *, overwrite: bool = True) -> str:
    return atomic_write(p, json.dumps(obj, ensure_ascii=False, indent=1, default=str), overwrite=overwrite)


def emit(obj: Any) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, default=str))


def x264_threads() -> int:
    """Bellek baskısında x264 iş parçacığı tavanı (çok çekirdekte aşırı bellek kullanımını sınırlar)."""
    return max(1, min(8, (os.cpu_count() or 2) // 2))


def render_budget() -> int:
    """Toplam render işçisi bütçesi = max(1, floor(mantıksal_CPU / 2)) (5.21)."""
    return max(1, (os.cpu_count() or 2) // 2)


def per_render_concurrency(parallel_jobs: int) -> int:
    b = render_budget()
    j = max(1, min(int(parallel_jobs), b))
    return max(1, b // j)


def even(n: float) -> int:
    v = int(round(n))
    return v if v % 2 == 0 else v + 1


def safe_rmtree(path: str | Path) -> None:
    """Bağlantı (junction/symlink) hedeflerine inmeden siler: bağlantının kendisi kaldırılır, hedefi korunur."""
    p = Path(path)
    if not p.exists() and not p.is_symlink():
        return
    if _is_link(p):
        _unlink_link(p)
        return
    for child in p.iterdir():
        if _is_link(child):
            _unlink_link(child)
        elif child.is_dir():
            safe_rmtree(child)
        else:
            try:
                child.unlink()
            except PermissionError:
                os.chmod(child, stat.S_IWRITE)
                child.unlink()
    p.rmdir()


def _is_link(p: Path) -> bool:
    if p.is_symlink():
        return True
    if os.name == "nt":
        try:
            return bool(os.lstat(p).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
        except (OSError, AttributeError):
            return False
    return False


def _unlink_link(p: Path) -> None:
    try:
        os.rmdir(p) if p.is_dir() else os.unlink(p)
    except OSError:
        os.unlink(p)


def seconds_to_tc(s: float) -> str:
    m, sec = divmod(max(0.0, s), 60)
    return f"{int(m):02d}:{sec:05.2f}"


def finite(x: Any) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False
