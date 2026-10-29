"""Kurulu öteki Claude Code plugin'lerinin taraması (1.6.0): kurulum denetimi (doctor, kurulum_dogrula) ve navigator uyarısı.

1.5.x'e kadar yalnızca ~/.claude/skills altındaki aynı adlı klasörlere bakılıyordu; marketplace'ten kurulan, claude.ai'dan senkronlanan ve
proje kapsamındaki plugin'ler görünmüyordu. Burada her etkin plugin'in skill'leri, kancaları ve MCP sunucuları OKUNUR (hiçbir dosya
çalıştırılmaz) ve hooks/plugin_clash.json tablosuyla sınıflandırılır:
  video          skill adı/açıklaması video üretimi ya da kurgu işini üstlenebilir (plan → render → QC kapılarını atlatma riski)
  paid_or_write  MCP sunucusu ücretli üretim ya da yayın sağlayıcısı (meta_guard/cost_guard yalnızca ads_* ve creative_* adlarını korur)
  hooks          araç kullanımına giren kanca olayları (bilgi; çakışma sayılmaz)
Envanter önce `claude plugin list --json` (resmi alanlar: id, scope, enabled, installPath, mcpServers;
https://code.claude.com/docs/en/plugins/cli-reference.md), yoksa diskteki kayıtlar: <kök>/installed_plugins.json, <kök>/synced/,
~/.claude/skills/*/.claude-plugin (kök: CLAUDE_CODE_PLUGIN_CACHE_DIR ya da ~/.claude/plugins; https://code.claude.com/docs/en/plugins/loading.md).
Yalnızca standart kütüphane: hook'lar da içe aktarır.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

SELF = "reklam-atolyesi"
RULES_PATH = Path(__file__).resolve().parents[2] / "hooks" / "plugin_clash.json"
CLASHING = ("video", "paid_or_write")


def rules() -> dict:
    r = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    r["_video_re"] = [re.compile(p) for p in r["video_patterns"]]
    return r


def plugins_root() -> Path:
    env = os.environ.get("CLAUDE_CODE_PLUGIN_CACHE_DIR")
    return Path(env) if env else Path.home() / ".claude" / "plugins"


def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def parse_list_json(text: str) -> list[dict] | None:
    """`claude plugin list --json` çıktısı: birden çok satırlı JSON dizisi; öncesinde bilgi satırı olabilir ('[' ile başlayan ilk satırdan)."""
    lines = (text or "").splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.lstrip().startswith("[")), None)
    if start is None:
        return None
    try:
        rows = json.loads("\n".join(lines[start:]))
    except json.JSONDecodeError:
        return None
    return rows if isinstance(rows, list) else None


def rows_from_cli(claude: str | None, timeout: int = 20) -> list[dict] | None:
    if not claude:
        return None
    try:
        cp = subprocess.run([claude, "plugin", "list", "--json"], capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if cp.returncode != 0:
        return None
    return parse_list_json(cp.stdout.decode("utf-8", "replace"))


def _enabled_map(paths: list[Path]) -> dict:
    out: dict = {}
    for p in paths:  # düşükten yükseğe; sonraki üstün gelir
        d = _read_json(p)
        if isinstance(d, dict) and isinstance(d.get("enabledPlugins"), dict):
            out.update(d["enabledPlugins"])
    return out


def rows_from_disk() -> list[dict]:
    """CLI yokken: kurulum kaydı + senkron + skills-dir plugin'leri. `enabled` ayar dosyalarından; kayıt yoksa True (defaultEnabled)."""
    root = plugins_root()
    home = Path.home()
    user_en = _enabled_map([home / ".claude" / "settings.json"])
    rows: list[dict] = []
    rec = _read_json(root / "installed_plugins.json") or {}
    plugins = rec.get("plugins", rec) if isinstance(rec, dict) else {}
    for pid, inst in (plugins.items() if isinstance(plugins, dict) else []):
        if not isinstance(pid, str) or "@" not in pid:
            continue
        for i in (inst if isinstance(inst, list) else [inst]):
            if not isinstance(i, dict) or not i.get("installPath"):
                continue
            scope = i.get("scope", "user")
            en = dict(user_en)
            if scope in ("project", "local") and i.get("projectPath"):
                pp = Path(i["projectPath"]) / ".claude"
                en.update(_enabled_map([pp / "settings.json", pp / "settings.local.json"]))
            rows.append({"id": pid, "scope": scope, "enabled": en.get(pid, True) is not False, "installPath": i["installPath"],
                         "version": i.get("version")})
    for acct in sorted((root / "synced").glob("*")) if (root / "synced").is_dir() else []:
        for meta in sorted(acct.glob("*.meta.json")):
            name = meta.name[: -len(".meta.json")]
            m = _read_json(meta) or {}
            pid = f"{name}@synced"
            rows.append({"id": pid, "scope": "synced", "enabled": user_en.get(pid, True) is not False, "installPath": str(acct / name),
                         "required_by_org": m.get("installation_preference") == "required"})
    sk = home / ".claude" / "skills"
    for d in sorted(sk.glob("*/.claude-plugin/plugin.json")) if sk.is_dir() else []:
        man = _read_json(d) or {}
        name = man.get("name") or d.parent.parent.name
        pid = f"{name}@skills-dir"
        rows.append({"id": pid, "scope": "user", "enabled": user_en.get(pid, man.get("defaultEnabled", True)) is not False,
                     "installPath": str(d.parent.parent)})
    return rows


def _frontmatter(p: Path) -> dict:
    try:
        t = p.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return {}
    m = re.match(r"\s*---\s*\n(.*?)\n---", t, re.S)
    out = {}
    for ln in (m.group(1).splitlines() if m else []):
        k, sep, v = ln.partition(":")
        if sep and k.strip() in ("name", "description") and not k.startswith(" "):
            out[k.strip()] = v.strip().strip("'\"")
    return out


def _as_list(v) -> list:
    return v if isinstance(v, list) else [v] if v else []


def inspect(install_path: str) -> dict:
    """Plugin klasörünü okur: skill'ler (ad + açıklama), kanca olayları, MCP sunucu adları ve komut/adresleri, manifest adı."""
    base = Path(install_path)
    man = _read_json(base / ".claude-plugin" / "plugin.json") or {}
    skill_dirs = [base / "skills"] + [base / s for s in _as_list(man.get("skills")) if isinstance(s, str)]
    files: list[Path] = []
    if (base / "SKILL.md").is_file() and not (base / "skills").is_dir() and not man.get("skills"):
        files.append(base / "SKILL.md")
    for d in skill_dirs:
        if (d / "SKILL.md").is_file():
            files.append(d / "SKILL.md")
        elif d.is_dir():
            files += sorted(d.glob("*/SKILL.md"))
    skills, seen = [], set()
    for f in files:
        fm = _frontmatter(f)
        nm = fm.get("name") or f.parent.name
        if nm not in seen:
            seen.add(nm)
            skills.append({"name": nm, "description": fm.get("description", "")[:400]})
    events: set[str] = set()
    hook_sources = [base / "hooks" / "hooks.json"] + [base / h for h in _as_list(man.get("hooks")) if isinstance(h, str)]
    for h in hook_sources:
        d = _read_json(h) if h.is_file() else None
        if isinstance(d, dict):
            events |= set((d.get("hooks") or {}).keys())
    for h in _as_list(man.get("hooks")):
        if isinstance(h, dict):
            events |= set(h.keys())
    servers: dict[str, str] = {}

    def add_servers(d) -> None:
        if not isinstance(d, dict):
            return
        d = d.get("mcpServers", d) if isinstance(d.get("mcpServers"), dict) else d
        for k, v in d.items():
            if isinstance(v, dict):
                servers[k] = " ".join(str(v.get(x, "")) for x in ("command", "url")) + " " + " ".join(map(str, v.get("args") or []))
    add_servers(_read_json(base / ".mcp.json") if (base / ".mcp.json").is_file() else None)
    for m in _as_list(man.get("mcpServers")):
        if isinstance(m, dict):
            add_servers(m)
        elif isinstance(m, str) and m.endswith(".json") and (base / m).is_file():
            add_servers(_read_json(base / m))
    return {"manifest_name": man.get("name"), "skills": skills, "hook_events": sorted(events), "mcp_servers": servers}


def _tokens(s: str) -> set[str]:
    return set(t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if t)


def classify(info: dict, extra_servers: dict | None = None, r: dict | None = None) -> dict:
    r = r or rules()
    video = []
    for s in info.get("skills", []):
        text = f"{s['name']} {s.get('description', '')}".lower()
        hit = next((p.pattern for p in r["_video_re"] if p.search(text)), None)
        if hit:
            video.append(s["name"])
    servers = dict(info.get("mcp_servers") or {})
    for k, v in (extra_servers or {}).items():
        servers.setdefault(k, " ".join(str(v.get(x, "")) for x in ("command", "url")) if isinstance(v, dict) else "")
    prov = set(r["paid_or_write_providers"])
    paid = sorted(k for k, v in servers.items() if _tokens(k) & prov or _tokens(v) & prov)
    hooks = [e for e in info.get("hook_events", []) if e in r["hook_events"]]
    return {"video": video, "paid_or_write": paid, "hooks": hooks}


def is_self(row: dict, info: dict | None = None) -> bool:
    return str(row.get("id", "")).split("@", 1)[0] == SELF or bool(info and info.get("manifest_name") == SELF)


def scan(claude: str | None = None, use_cli: bool = True) -> dict:
    """Bütün etkin öteki plugin'ler. Dönüş: {source, plugins: [...], clash: [çakışan id'ler], notes}. Hiçbir zaman istisna fırlatmaz."""
    notes: list[str] = []
    rows = rows_from_cli(claude) if use_cli else None
    source = "cli"
    if rows is None:
        source = "disk"
        if use_cli:
            notes.append("claude plugin list --json okunamadı; diskteki kayıtlar kullanıldı")
        try:
            rows = rows_from_disk()
        except Exception as e:  # tarama kurulumu hiçbir zaman düşürmez
            return {"source": "none", "plugins": [], "clash": [], "notes": notes + [f"disk taraması başarısız: {type(e).__name__}: {e}"]}
    try:
        r = rules()
    except Exception as e:
        return {"source": source, "plugins": [], "clash": [], "notes": notes + [f"plugin_clash.json okunamadı: {e}"]}
    out = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("installPath"):
            continue
        try:
            info = inspect(row["installPath"])
        except Exception as e:
            info = {"skills": [], "hook_events": [], "mcp_servers": {}, "error": f"{type(e).__name__}: {e}"}
        if is_self(row, info):
            continue
        cat = classify(info, row.get("mcpServers") if isinstance(row.get("mcpServers"), dict) else None, r)
        out.append({"id": row.get("id"), "scope": row.get("scope"), "enabled": row.get("enabled") is not False,
                    "required_by_org": bool(row.get("required_by_org")) or "required by your org" in " ".join(map(str, row.get("notes") or [])),
                    "installPath": row.get("installPath"), "skills": len(info.get("skills", [])), "categories": cat})
    clash = sorted({p["id"] for p in out if p["enabled"] and any(p["categories"][c] for c in CLASHING)})
    return {"source": source, "plugins": out, "clash": clash, "notes": notes}


def disable(claude: str, plugin: dict, timeout: int = 60) -> dict:
    """Geri alınabilir: `claude plugin disable <id> [--scope]`. Kaldırma yapılmaz. Kuruma zorunlu senkron plugin kapatılamaz."""
    if plugin.get("required_by_org"):
        return {"id": plugin["id"], "ok": False, "reason": "required_by_org"}
    args = [claude, "plugin", "disable", plugin["id"]]
    if plugin.get("scope") in ("user", "project", "local"):
        args += ["--scope", plugin["scope"]]
    try:
        cp = subprocess.run(args, capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return {"id": plugin["id"], "ok": False, "reason": f"{type(e).__name__}: {e}"}
    msg = (cp.stdout + cp.stderr).decode("utf-8", "replace").strip()
    return {"id": plugin["id"], "ok": cp.returncode == 0 or "already disabled" in msg, "output": msg[-300:]}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Kurulu öteki plugin'leri tara (yalnızca okur)")
    ap.add_argument("--claude", default=None)
    ap.add_argument("--disk", action="store_true", help="CLI yerine yalnızca disk kayıtları")
    a = ap.parse_args()
    print(json.dumps(scan(a.claude, use_cli=not a.disk), ensure_ascii=False, indent=1))
