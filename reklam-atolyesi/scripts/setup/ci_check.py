"""Sürekli entegrasyon denetimi (2.5.0): sürüm tutarlılığı ve manifest/nötrlük güncelliği.

Kullanım: python scripts/setup/ci_check.py   (çıkış kodu 0 = temiz, 1 = sorun)
Denetler:
  * sürüm dört yerde aynı: plugin.json, kök marketplace.json, admem/__init__.py, README başlığı (yayın kuralı);
  * system_manifest.json gerçek bileşenlerle tutarlı ve nötrlük denetimi güncel dosyaları kapsıyor (doctor.check_manifest);
  * KURALLAR.md kısa listesi var (hook'lar onu modele verir) ve her zaman bağlamda duran özeti RULES_BLOCK_MAX karakteri aşmıyor
    (2.8.0; evals/etki-defteri.md "Yeni metin nereye konur": her zaman duran metne satır eklenirse başka satır kısaltılır);
  * skill, ajan, komut ve KURALLAR.md metinlerinde adı geçen her scripts/... dosyası gerçekten var (2.8.0).
Ağ, Claude ya da Meta gerektirmez; müşteri bilgisayarında çalıştırılmaz.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT / "scripts" / "setup"))
sys.path.insert(0, str(ROOT / "hooks"))


def versions() -> dict:
    out = {"plugin.json": json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]}
    mp = REPO / ".claude-plugin" / "marketplace.json"
    if mp.exists():
        plugs = json.loads(mp.read_text(encoding="utf-8")).get("plugins") or []
        ent = next((p for p in plugs if p.get("name") == "reklam-atolyesi"), {}) or {}
        m = re.search(r"sürüm (\d+\.\d+\.\d+)", ent.get("description") or "")
        out["marketplace.json"] = ent.get("version") or (m.group(1) if m else None)
    init = (ROOT / "servers" / "ad_memory" / "admem" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r"__version__\s*=\s*[\"']([^\"']+)", init)
    out["admem/__init__.py"] = m.group(1) if m else None
    head = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()[0]
    m = re.search(r"(\d+\.\d+\.\d+)", head)
    out["README.md"] = m.group(1) if m else None
    return out


RULES_BLOCK_MAX = 3000
SCRIPT_REF = re.compile(r"scripts/[A-Za-z0-9_/.-]+\.(?:py|js|mjs|sh|ts|ps1|cmd)\b")


def missing_script_refs() -> list[str]:
    """Metinde adı geçen ama depoda olmayan betikler. PR/ öneki ve <yer tutucu> içeren yollar atlanmaz: yol olduğu gibi aranır."""
    out = []
    files = [ROOT / "KURALLAR.md"] + sorted((ROOT / "skills").glob("*/SKILL.md")) + sorted((ROOT / "agents").glob("*.md")) \
        + sorted((ROOT / "commands").glob("*.md"))
    for f in files:
        for ref in sorted(set(SCRIPT_REF.findall(f.read_text(encoding="utf-8")))):
            if not (ROOT / ref).exists():
                out.append(f"{f.relative_to(ROOT)} → {ref}")
    return out


def main() -> int:
    problems: list[str] = []
    v = versions()
    if len(set(v.values())) != 1:
        problems.append(f"sürüm tutarsız: {v}")
    import doctor  # noqa: E402

    r = doctor.Report()
    doctor.check_manifest(r, json.loads((ROOT / "system_manifest.json").read_text(encoding="utf-8")))
    for it in r.items:
        if it["key"] in ("manifest", "neutrality") and not it["ok"]:
            problems.append(f"{it['key']}: {it['title']} — {it['detail']}")
    import plugin_mode as pm  # noqa: E402

    if len(pm.rules_short(ROOT / "KURALLAR.md")) < 10:
        problems.append("KURALLAR.md kısa listesi okunamadı")
    rb = len(pm.rules_block(ROOT / "KURALLAR.md"))
    if rb > RULES_BLOCK_MAX:
        problems.append(f"her zaman bağlamda duran kurallar özeti {rb} karakter (sınır {RULES_BLOCK_MAX}): bir satır kısaltın")
    problems += [f"adı geçen betik yok: {m}" for m in missing_script_refs()]
    print(json.dumps({"versions": v, "problems": problems}, ensure_ascii=False, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
