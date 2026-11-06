"""Bağımlılık güvenlik raporu (2.10.10). Yayın öncesi ve CI'da çalışır; yayını durdurmaz, rapor verir.

Python: kilitli bağımlılıklar `uv export` ile dökülür ve `pip-audit` ile taranır.
npm: Remotion şablonunun kilidi `npm audit --omit=dev` ile taranır.
Yüksek ya da kritik bildirim çıkarsa GitHub Actions'ta uyarı satırı (`::warning::`) basılır ve betik 1 koduyla çıkar (2.10.14).
Araç ya da ağ yoksa, araç hata koduyla bitip okunabilir rapor vermezse ya da rapor bir hata nesnesiyse "denetlenemedi" yazılır;
bu durum 0 sayılmaz, ayrı gösterilir. Çıkış kodu: 0 = bildirim yok ya da denetlenemedi, 1 = yüksek/kritik bildirim var.
Kullanım (servers/ad_memory içinden): uv run python ../../scripts/setup/bagimlilik_denetimi.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(cmd: list[str], cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def python_report() -> dict:
    srv = ROOT / "servers" / "ad_memory"
    uv = shutil.which("uv")
    if not uv:
        return {"checked": False, "why": "uv yok"}
    exp = _run([uv, "export", "--frozen", "--no-hashes", "--no-emit-project", "-q"], srv)
    if not exp or exp.returncode != 0:
        return {"checked": False, "why": "uv export çalışmadı"}
    with tempfile.TemporaryDirectory() as td:
        req = Path(td) / "req.txt"
        req.write_text(exp.stdout, encoding="utf-8")
        r = _run([uv, "tool", "run", "pip-audit", "-r", str(req), "--format", "json", "--progress-spinner", "off"], srv)
    if not r or not r.stdout.strip().startswith("{"):
        return {"checked": False, "why": "pip-audit çalışmadı (ağ?)"}
    try:
        data = json.loads(r.stdout)
    except ValueError:
        return {"checked": False, "why": "pip-audit raporu okunamadı"}
    if not isinstance(data, dict) or "dependencies" not in data:
        return {"checked": False, "why": "pip-audit raporunda bağımlılık listesi yok"}
    vulns = [{"package": d["name"], "version": d["version"], "id": v["id"], "fix": v.get("fix_versions")}
             for d in data.get("dependencies", []) for v in d.get("vulns", [])]
    # pip-audit önem derecesi vermez: her bildirim ciddi sayılır
    return {"checked": True, "count": len(vulns), "high": len(vulns), "items": vulns}


def npm_report() -> dict:
    tpl = ROOT / "templates" / "remotion"
    npm = shutil.which("npm")
    if not npm:
        return {"checked": False, "why": "npm yok"}
    r = _run([npm, "audit", "--omit=dev", "--json", "--package-lock-only"], tpl)
    if not r or not r.stdout.strip().startswith("{"):
        return {"checked": False, "why": "npm audit çalışmadı (ağ?)"}
    try:
        data = json.loads(r.stdout)
    except ValueError:
        return {"checked": False, "why": "npm audit raporu okunamadı"}
    # npm, kayıt sunucusu hatasında da JSON döner ({"error": {...}}); bu "0 açık" değildir
    if not isinstance(data, dict) or data.get("error"):
        err = data.get("error") if isinstance(data, dict) else None
        code = err.get("code") if isinstance(err, dict) else None
        return {"checked": False, "why": f"npm audit hata verdi ({code or 'bilinmeyen hata'})"}
    meta = (data.get("metadata") or {}).get("vulnerabilities")
    if not isinstance(meta, dict) or "total" not in meta:
        return {"checked": False, "why": "npm audit raporunda açık sayısı yok"}
    return {"checked": True, "count": int(meta.get("total", 0)), "high": int(meta.get("high", 0)) + int(meta.get("critical", 0)),
            "by_severity": meta}


def main() -> int:
    rep = {"python": python_report(), "npm": npm_report()}
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    for k, v in rep.items():
        if not v.get("checked"):
            print(f"::warning::{k} bağımlılıkları denetlenemedi: {v.get('why')}")
        elif v.get("high"):
            print(f"::warning::{k} bağımlılıklarında {v['high']} yüksek/kritik güvenlik bildirimi var; yayından önce güncelle")
    return 1 if any(v.get("checked") and v.get("high") for v in rep.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
