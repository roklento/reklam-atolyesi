"""Yayın aracı (2.0.0): templates/remotion/src dosyalarının yayımlanmış her sürümünün SHA-256'sını templates/remotion/template_history.json'a yazar.

`render.py upgrade` eski bir kampanya projesindeki dosyanın elle değiştirilip değiştirilmediğini bu listeyle anlar: dosya yayımlanmış bir
şablon sürümüyle bayt bayt aynıysa değiştirilmemiştir ve güvenle güncellenir; listede yoksa özelleştirilmiş sayılır ve dokunulmaz.
Depo .gitattributes "* -text" olduğundan kurulu plugin'deki dosya baytları git'tekiyle aynıdır.

Kullanım (depo kökünde, git geçmişiyle): template_history.py --plugin-root <plugin-kökü> [--check]
--check: güncel şablonun her dosyası listede mi (yayından önce; test de aynı şeyi denetler).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

SRC = "templates/remotion/src"
OUT = "templates/remotion/template_history.json"


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, check=True).stdout


def current(plugin_root: Path) -> dict[str, str]:
    base = plugin_root / SRC
    return {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(base.rglob("*")) if p.is_file()}


def collect(plugin_root: Path) -> dict[str, list[str]]:
    top = Path(_git(plugin_root, "rev-parse", "--show-toplevel").decode().strip())
    prefix = plugin_root.resolve().relative_to(top.resolve()).as_posix()
    rel_src = f"{prefix}/{SRC}" if prefix != "." else SRC
    seen: dict[str, set[str]] = {}
    for commit in _git(top, "log", "--format=%H", "--", rel_src).decode().split():
        for line in _git(top, "ls-tree", "-r", commit, "--", rel_src).decode("utf-8").splitlines():
            meta, path = line.split("\t", 1)
            blob = meta.split()[2]
            data = _git(top, "cat-file", "blob", blob)
            seen.setdefault(path[len(rel_src) + 1:], set()).add(hashlib.sha256(data).hexdigest())
    for rel, h in current(plugin_root).items():  # henüz commit edilmemiş güncel şablon da yayımlanacak sürümdür
        seen.setdefault(rel, set()).add(h)
    return {k: sorted(v) for k, v in sorted(seen.items())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plugin-root", required=True)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    root = Path(a.plugin_root)
    if a.check:
        hist = json.loads((root / OUT).read_text(encoding="utf-8"))
        missing = [rel for rel, h in current(root).items() if h not in hist.get("files", {}).get(rel, [])]
        print(json.dumps({"ok": not missing, "missing": missing}, ensure_ascii=False))
        sys.exit(1 if missing else 0)
    doc = {"_comment": "Yayımlanmış şablon dosyası sürümlerinin SHA-256'sı; render.py upgrade değiştirilmemiş dosyayı bununla tanır. "
                       "Üretici: scripts/setup/template_history.py (şablon her değiştiğinde yeniden çalıştırılır).",
           "files": collect(root)}
    (root / OUT).write_bytes((json.dumps(doc, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    print(json.dumps({"files": len(doc["files"]), "hashes": sum(len(v) for v in doc["files"].values())}))


if __name__ == "__main__":
    main()
