"""Statik kurulum kontrolü (spec 12.9 adım 12, 12.10 statik liste, 16.4).

Her madde makine tarafından denetlenir; görsel/nötrlük incelemelerinde doctor yalnızca mevcut inceleme kaydını ve dosya hash'lerini doğrular,
yargıyı kendisi üretmez. --write-ok yalnızca bütün maddeler yeşilse (ya da kırmızı madde manifest'te kullanıcının açıkça kabul ettiği bir
sapmaysa) ve render atlanmadıysa: data_dir/.kurulum-statik-tamam, settings.setup_static_ok_at ve ilk "kurulum tamamlandı" günlük kaydını
yazar (aynı Store kodu; 7.4 kurulum istisnası).

Kullanım: doctor.py --data-dir <data_dir> [--results-dir <dizin>] [--selftest-json <smoke.json>] [--claude <claude yürütülebilir>]
                    [--skip-render] [--run-tests] [--write-ok] [--update] [--json-out <rapor.json>]
--update: kullanımdaki data_dir'de sürüm güncellemesinin doğrulaması (profil verisi beklenir; yalnızca test artığı denetlenir).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "servers" / "ad_memory"))

EXPECTED_SKILLS = ["navigator", "brand-onboarding", "meta-history", "product-onboarding", "brief", "competitor-analysis", "strategy", "concepts",
                   "shoot-guide", "shoot-feedback", "ingest", "analyze", "style-directions", "materials", "compose", "sound", "variants", "qc",
                   "launch-pack", "track", "coach", "learn", "memory", "ref-system-map", "ref-metrics-math", "ref-legal-tr-meta",
                   "ref-remotion-components", "ref-shooting-basics", "ref-production-recipes", "ref-vendor-map", "ref-creative-taxonomy"]
STAGE_SKILLS = EXPECTED_SKILLS[1:22]
STAGE_HEADINGS = ["## Amaç", "## Ön koşul", "## Girdiler ve bağlam paketi", "## Kullanılan hazır skill'ler ve OVERRIDES", "## Adımlar",
                  "## Çıktılar", "## Kontroller", "## Kapı mesajı"]
EXPECTED_AGENTS = ["meta-historian", "competitor-analyst", "creative-strategist", "cinematographer", "footage-analyst", "art-director", "editor",
                   "sound-designer", "qc-reviewer", "media-analyst", "coach"]
EXPECTED_COMMANDS = ["basla", "kurulum-kontrol", "profiller", "profil-ekle", "profil-sec", "tanis-marka", "tanis-urun", "meta-gecmis",
                     "yeni-kampanya", "durum", "sonraki", "onayla", "geri", "rapor", "rakip-analizi", "takip", "karar-hazirla", "gece-uretim", "bakim"]
EXPECTED_WORKFLOWS = ["analyze-footage", "analyze-competitors", "render-variants", "qc-review"]
EXPECTED_HOOKS = ["plugin_mode.py", "navigator.py", "session_start.py", "meta_guard.py", "cost_guard.py", "render_qc.py", "stop_check.py",
                  "meta_allowlist.json", "hooks.json"]
TOOLS_7_3 = """profile_create profile_list profile_set_active profile_get_active profile_update settings_get settings_set brand_upsert product_upsert
onboarding_save onboarding_get meta_entities_upsert benchmarks_upsert priors_set priors_get priors_from_history history_summary metrics_import_csv
metrics_ingest metrics_query metrics_export_csv campaign_create campaign_get campaign_status cycle_set launch_confirm stage_complete gate_approve
stage_resume stage_back decision_log concept_upsert hook_upsert hooks_export_csv hypothesis_add hypothesis_update competitor_upsert competitor_list
competitor_snapshot_save competitor_ads_upsert competitor_offer_upsert competitor_diff competitive_map competitive_insights_save
competitive_insights_get concept_distance_check strategy_save strategy_get taxonomy_get taxonomy_value_add edit_plan_save edit_plan_validate
edit_plan_patch scene_cache_get asset_register asset_query generation_hash generation_log generation_find generation_approve generation_update
cost_summary review_add review_withdraw review_query consent_add consent_withdraw consent_query creative_register ad_link sales_add
action_items_set action_item_set_status action_items_verify prediction_log prediction_resolve calibration_get playbook_get playbook_propose
playbook_activate playbook_revalidate playbook_retire playbook_round_tick memory_card memory_context memory_search memory_add memory_observe
memory_update memory_forget memory_consolidate consolidation_due journal_log journal_summary checkpoint_save checkpoint_get checkpoint_close
export_markdown backup system_manifest_get""".split()
DATA_ALLOWED = {".venv", ".node", "db", ".kurulum-statik-tamam", ".sessions", "logs", "backups", "memory", ".selftest"}
FFMPEG_FILTERS = ["vidstabdetect", "vidstabtransform", "zscale", "loudnorm", "lut3d", "sidechaincompress", "tonemap"]
VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


class Report:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, key: str, title: str, ok: bool, detail=None, deviation: str | None = None) -> None:
        self.items.append({"key": key, "title": title, "ok": bool(ok), "detail": detail, "accepted_deviation": deviation if not ok else None})

    def blocking(self) -> list[dict]:
        return [i for i in self.items if not i["ok"] and not i["accepted_deviation"]]


def _run(args: list[str], timeout: int = 120, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, timeout=timeout, **kw)


def _ver(text: str) -> tuple[int, ...]:
    m = VERSION_RE.search(text or "")
    return tuple(int(x or 0) for x in m.groups()) if m else (0,)


def venv_python(data_dir: Path) -> Path:
    return data_dir / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def find_claude(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    w = shutil.which("claude")
    if w:
        return w
    appdata = os.environ.get("APPDATA")
    if appdata:
        cands = sorted(Path(appdata, "Claude", "claude-code").glob("*/*/claude.exe")) + sorted(Path(appdata, "Claude", "claude-code").glob("*/claude.exe"))
        if cands:
            return str(cands[-1])
    return None


# --- kontroller ---------------------------------------------------------------------------------------------------------
def check_tools(r: Report, data_dir: Path) -> None:
    py = venv_python(data_dir)
    node = shutil.which("node")
    nv = _ver(_run([node, "-v"]).stdout.decode()) if node else (0,)
    r.add("node", "Node ≥ 22", nv >= (22,), {"path": node, "version": ".".join(map(str, nv))})
    pv = _run([str(py), "-c", "import sys,sqlite3,json;c=sqlite3.connect(':memory:');"
               "fts=1\ntry:\n c.execute('create virtual table t using fts5(x, tokenize=\"trigram\")')\nexcept Exception: fts=0\n"
               "print(json.dumps({'py':sys.version.split()[0],'sqlite':sqlite3.sqlite_version,'fts5_trigram':bool(fts)}))"]) if py.exists() else None
    info = json.loads(pv.stdout.decode()) if pv and pv.returncode == 0 else {}
    r.add("python", "Python ≥ 3.11 (data_dir sanal ortamı)", _ver(info.get("py", "")) >= (3, 11), {"python": str(py), **info})
    r.add("sqlite", "SQLite ≥ 3.40, FTS5 trigram açık", _ver(info.get("sqlite", "")) >= (3, 40) and info.get("fts5_trigram") is True, info)
    for name in ("uv", "git"):
        w = shutil.which(name)
        out = _run([w, "--version"]).stdout.decode().strip() if w else ""
        r.add(name, f"{name} kurulu", bool(w and out), {"path": w, "version": out})
    ff = shutil.which("ffmpeg")
    filt = _run([ff, "-hide_banner", "-filters"]).stdout.decode("utf-8", "replace") if ff else ""
    missing = [f for f in FFMPEG_FILTERS if not re.search(rf"\s{f}\s", filt)]
    r.add("ffmpeg_filters", "FFmpeg: vidstab, zscale, loudnorm, lut3d, sidechaincompress", bool(ff) and not missing, {"path": ff, "missing": missing})


def check_disk(r: Report, data_dir: Path, deviations: dict) -> None:
    du = shutil.disk_usage(data_dir)
    okd = du.free >= 50 * 2**30
    r.add("disk_data", "data_dir sürücüsünde ≥ 50 GB boş", okd, {"free_gb": round(du.free / 2**30, 1)},
          deviation=deviations.get("disk_data") if not okd else None)
    sysdrive = Path(os.environ.get("SystemDrive", "C:") + "\\") if os.name == "nt" else Path("/")
    ds = shutil.disk_usage(sysdrive)
    ok = ds.free >= 10 * 2**30
    r.add("disk_system", "Sistem sürücüsünde ≥ 10 GB boş (hata)", ok, {"free_gb": round(ds.free / 2**30, 1)},
          deviation=deviations.get("disk_system") if not ok else None)
    t = data_dir / ".doctor-yazma-testi"
    try:
        t.write_text("x", encoding="utf-8")
        t.unlink()
        w = True
    except OSError:
        w = False
    r.add("data_dir_writable", "data_dir yazılabilir", w, str(data_dir))


def check_data_dir_contents(r: Report, data_dir: Path, final: bool, update: bool = False) -> None:
    if update:
        # Güncellemede data_dir kullanımdadır (profiller, oturum dosyaları, hafıza): yalnızca test klasörünün kalmadığı denetlenir.
        left = [".selftest (duman testi klasörü silinmemiş)"] if final and (data_dir / ".selftest").exists() else []
        r.add("data_dir_contents", "Güncelleme: data_dir'de duman testi artığı yok (kullanıcı verisine dokunulmaz)", not left, {"unexpected": left})
        return
    extra = sorted(p.name for p in data_dir.iterdir() if p.name not in DATA_ALLOWED)
    if final:
        if (data_dir / ".selftest").exists():
            extra.append(".selftest (duman testi klasörü silinmemiş)")
        sess = list((data_dir / ".sessions").glob("*")) if (data_dir / ".sessions").exists() else []
        if sess:
            extra.append(f".sessions içinde {len(sess)} dosya")
        mem = data_dir / "memory"
        if mem.exists():
            extra += [f"memory/{p.name}" for p in mem.iterdir() if p.name != "system"]
    r.add("data_dir_contents", "data_dir'de yalnızca 12'deki liste", not extra, {"unexpected": extra})


def check_vendor(r: Report) -> None:
    vd = ROOT / "vendor-skills"
    lock = json.loads((vd / "vendor.lock.json").read_text(encoding="utf-8"))
    problems = []
    for entry in lock:
        if entry["status"] != "vendored":
            continue
        for part in entry["parts"].split(";"):
            dst = part.split("=>")[1].split("/")[0]
            d = vd / dst
            up = d / "UPSTREAM.md"
            if not d.exists():
                problems.append(f"{dst}: klasör yok")
                continue
            if not (d / "LICENSE").exists():
                problems.append(f"{dst}: LICENSE yok")
            if not (d / "OVERRIDES.md").exists():
                problems.append(f"{dst}: OVERRIDES.md yok")
            if not up.exists() or entry["commit"] not in up.read_text(encoding="utf-8"):
                problems.append(f"{dst}: UPSTREAM.md beklenen commit'i ({entry['commit'][:12]}) göstermiyor")
    pj = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    if pj.get("skills") != ["./skills/"]:
        problems.append(f"plugin.json skills alanı yalnızca ./skills/ olmalı: {pj.get('skills')}")
    vm = (ROOT / "skills" / "ref-vendor-map" / "SKILL.md").read_text(encoding="utf-8")
    if "Remotion — resmi belge yolu" not in vm or "remotion.dev/docs" not in vm:
        problems.append("ref-vendor-map: Remotion resmi belge eşlemesi yok")
    r.add("vendor", "Vendor skill'ler pinli; LICENSE/OVERRIDES yerinde; yalnızca ./skills/ kayıtlı; Remotion resmi belgeye bağlı",
          not problems, problems)


def global_skill_clash() -> list[str]:
    """~/.claude/skills altında vendor skill'leriyle ya da Remotion ile aynı adlı genel skill'ler (kullanıcının başka işler için kurduğu)."""
    vd = ROOT / "vendor-skills"
    gskills = Path.home() / ".claude" / "skills"
    globals_ = sorted(p.name for p in gskills.iterdir()) if gskills.exists() else []
    vendor_names = {p.name for p in vd.iterdir() if p.is_dir()} | {"remotion", "remotion-best-practices"}
    return [g for g in globals_ if g in vendor_names or g.startswith("remotion")]


def check_global_skills(r: Report, deviations: dict) -> None:
    # Ayrı madde (1.4.1): kullanıcı bu skill'leri başka işlerde kullanıyorsa dokunulmamasını seçebilir; karar install_deviations'a
    # 'global_skills' sapması olarak yazılır, madde kırmızı görünür ama kurulumu engellemez. Plugin bu skill'leri okumaz (ref-vendor-map).
    clash = global_skill_clash()
    r.add("global_skills", "~/.claude/skills altında plugin'inkilerle çakışan genel skill yok", not clash,
          {"clash": clash, "path": "~/.claude/skills"} if clash else None, deviation=deviations.get("global_skills") if clash else None)


def check_components(r: Report) -> None:
    probs = []
    for s in EXPECTED_SKILLS:
        f = ROOT / "skills" / s / "SKILL.md"
        if not f.exists():
            probs.append(f"skill yok: {s}")
            continue
        t = f.read_text(encoding="utf-8")
        if not re.search(rf'^name: {re.escape(s)}$', t, re.M):
            probs.append(f"{s}: name alanı")
        if "description:" not in t.split("---")[1]:
            probs.append(f"{s}: description yok")
        if s in STAGE_SKILLS:
            miss = [h for h in STAGE_HEADINGS if h not in t]
            if miss:
                probs.append(f"{s}: eksik başlık {miss}")
    extra = sorted(p.name for p in (ROOT / "skills").iterdir() if p.is_dir() and p.name not in EXPECTED_SKILLS)
    if extra:
        probs.append(f"beklenmeyen skill: {extra}")
    for a in EXPECTED_AGENTS:
        f = ROOT / "agents" / f"{a}.md"
        if not f.exists() or f"name: {a}" not in f.read_text(encoding="utf-8"):
            probs.append(f"ajan yok/hatalı: {a}")
    for c in EXPECTED_COMMANDS:
        f = ROOT / "commands" / f"{c}.md"
        if not f.exists() or "description:" not in f.read_text(encoding="utf-8"):
            probs.append(f"komut yok/hatalı: {c}")
    for w in EXPECTED_WORKFLOWS:
        f = ROOT / "workflows" / f"{w}.js"
        if not f.exists():
            probs.append(f"workflow yok: {w}")
            continue
        t = f.read_text(encoding="utf-8")
        if not t.startswith("export const meta = {"):
            probs.append(f"{w}: meta ilk ifade değil")
        if re.search(r"Date\.now|Math\.random|new Date\(\)|import\(|^import ", t, re.M):
            probs.append(f"{w}: Date.now/Math.random/import kullanılıyor")
    for h in EXPECTED_HOOKS:
        if not (ROOT / "hooks" / h).exists():
            probs.append(f"hook dosyası yok: {h}")
    for f in ("README.md", ".mcp.json", "system_manifest.json"):
        if not (ROOT / f).exists():
            probs.append(f"{f} yok")
    r.add("components", "Bölüm 16 bileşenleri: 31 skill (başlıklar), 11 ajan, 19 komut, 4 workflow, hook'lar, README", not probs, probs)


def check_scripts_map(r: Report, manifest: dict) -> None:
    missing = [f"{k} → {v}" for k, v in (manifest.get("scripts") or {}).items() if not (ROOT / v).exists()]
    r.add("scripts_map", "system_manifest script haritasındaki her işlevin dosyası var", bool(manifest.get("scripts")) and not missing, missing)


def check_hooks_exec(r: Report, data_dir: Path) -> None:
    hj = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    tmp = Path(tempfile.mkdtemp(prefix="doctor-hook-"))
    results, probs = [], []
    try:
        def build(h: dict, dd_arg: Path | None) -> list[str]:
            cmd = h["command"].replace("${user_config.data_dir}", str(data_dir)).replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT))
            args = []
            skip = False
            for a in h.get("args", []):
                if skip:
                    skip = False
                    continue
                if a == "--data-dir" and dd_arg is None:
                    skip = True
                    continue
                args.append(a.replace("${user_config.data_dir}", str(dd_arg or "")).replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT)))
            return [cmd, *args]
        sid = "doctor-" + "0" * 8 + "-0000-0000-0000-000000000000"
        payloads = {
            "UserPromptSubmit": {"hook_event_name": "UserPromptSubmit", "session_id": sid, "prompt": "merhaba"},
            "SessionStart": {"hook_event_name": "SessionStart", "session_id": sid, "source": "startup"},
            "PreToolUse": {"hook_event_name": "PreToolUse", "session_id": sid, "tool_name": "mcp__plugin_reklam-atolyesi_meta-ads__ads_create_campaign",
                           "tool_input": {}},
            "PostToolUse": {"hook_event_name": "PostToolUse", "session_id": sid, "tool_name": "Bash", "tool_input": {"command": "echo"}},
            "Stop": {"hook_event_name": "Stop", "session_id": sid},
            "UserPromptExpansion": {"hook_event_name": "UserPromptExpansion", "session_id": sid, "command_name": "x:y"},
        }
        for ev, arr in hj["hooks"].items():
            for m in arr:
                for h in m["hooks"]:
                    if "args" not in h or "shell" in h:
                        probs.append(f"{ev}: exec biçimi değil")
                    if re.search(r"[A-Za-z]:\\\\|[A-Za-z]:/|/Users/|/home/", json.dumps(h)):
                        probs.append(f"{ev}: gömülü makine yolu")
                    cmd = build(h, tmp)
                    script = Path(cmd[1]).name if len(cmd) > 1 else "?"
                    p = dict(payloads.get(ev, {"hook_event_name": ev, "session_id": sid}))
                    if ev == "PreToolUse" and "cost_guard" in script:
                        p["tool_name"] = "mcp__plugin_reklam-atolyesi_ElevenLabs__creative_list_voices"
                    pr = _run(cmd, input=json.dumps(p).encode("utf-8"), timeout=30)
                    out = pr.stdout.decode("utf-8", "replace").strip()
                    ok = pr.returncode == 0
                    if ev == "PreToolUse" and "meta_guard" in script:
                        ok = ok and '"deny"' in out  # kendi meta-ads sunucusunda yazma aracı her zaman reddedilir
                    if ev == "UserPromptSubmit":
                        ok = ok and out == ""  # plugin modu dışında hiçbir şey yapmaz
                    results.append({"event": ev, "script": script, "ok": ok, "rc": pr.returncode, "out": out[:200]})
        # data_dir verilmeden: meta_guard kendi sunucusu için deny
        mg = next(h for m in hj["hooks"]["PreToolUse"] for h in m["hooks"] if "meta_guard" in json.dumps(h))
        pr = _run(build(mg, None), input=json.dumps(payloads["PreToolUse"]).encode("utf-8"), timeout=30)
        nodd = '"deny"' in pr.stdout.decode("utf-8", "replace")
        results.append({"event": "PreToolUse (data_dir yok)", "script": "meta_guard.py", "ok": nodd})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    want = "/.venv/Scripts/python.exe" if os.name == "nt" else "/.venv/bin/python"
    for ev, arr in hj["hooks"].items():
        for m in arr:
            for h in m["hooks"]:
                if not h.get("command", "").endswith(want):
                    probs.append(f"{ev}: yorumlayıcı yolu bu işletim sistemine uymuyor ({h.get('command')}); gen_config.py yeniden çalıştırılmalı")
    bad = [x for x in results if not x["ok"]]
    r.add("hooks_exec", "hooks.json komutları gerçek yorumlayıcıyla çalışıyor; kapsam dışında iş yok; Meta yazma reddi", not bad and not probs,
          {"results": results, "problems": probs})
    src_probs = []
    for f in (ROOT / "hooks").glob("*.py"):
        t = f.read_text(encoding="utf-8")
        if re.search(r"['\"][A-Za-z]:[\\/]|['\"]/Users/|['\"]/home/", t):
            src_probs.append(f.name)
    r.add("hooks_no_hardcoded", "Hook'larda gömülü/varsayılan yol yok; data_dir yapılandırmadan; data_dir yoksa meta_guard deny", not src_probs and nodd,
          src_probs)


def check_tests(r: Report, results: dict, run_tests: bool, data_dir: Path) -> dict:
    py = venv_python(data_dir)
    pj = results.get("pytest")
    if run_tests or not pj:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        pr = _run([str(py), "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"], timeout=3600, cwd=str(ROOT), env=env)
        out = pr.stdout.decode("utf-8", "replace")
        m = re.search(r"(\d+) passed", out)
        f = re.search(r"(\d+) failed", out)
        pj = {"passed": int(m.group(1)) if m else 0, "failed": int(f.group(1)) if f else 0, "returncode": pr.returncode,
              "summary": out.strip().splitlines()[-1] if out.strip() else ""}
    ok = pj.get("returncode") == 0 and pj.get("failed", 1) == 0 and pj.get("passed", 0) > 0
    r.add("pytest", "Otomatik (O) testler: veri deposu, aşama makinesi, hook'lar, medya, analitik, hafıza, rekabet", ok, pj)
    return pj


def check_smoke(r: Report, smoke: dict | None) -> None:
    ok = bool(smoke) and smoke.get("ok") is True and not smoke.get("partial")
    steps = {s["step"]: s["ok"] for s in (smoke or {}).get("steps", [])}
    r.add("smoke", "Sentetik duman testi (12.12) 9 adımın hepsi geçti; test klasörü silindi", ok and len(steps) == 9 and smoke.get("selftest_dir_removed"),
          {"steps": steps, "seconds": (smoke or {}).get("seconds")})
    r.add("golden_production", "Üretim boru hattı altın örneği (ingest → render → ses → öz denetim → varyasyon → QC)", steps.get(3) and steps.get(4), None)
    r.add("golden_competitive", "Rekabet boru hattı (harita, fark, uzaklık, portföy, sorgu bütçesi, rakip kaynağı reddi)", bool(steps.get(8)), None)
    r.add("golden_coaching", "Koçluk sentetik gerçeklik testleri (6.15)", bool(steps.get(5)), None)
    r.add("memory_tests", "Hafıza testleri (bölüm 8)", bool(steps.get(6)), None)


def check_render(r: Report, results: dict, skip: bool, data_dir: Path) -> None:
    if skip:
        r.add("final_render", "Final render 2 sn 1080×1920 Türkçe karakter", False, "--skip-render: kurulumu bitirmez")
        return
    tr = results.get("turkish") or {}
    ok = False
    det = tr
    if tr.get("out") and Path(tr["out"]).exists():
        info = json.loads(_run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", tr["out"]]).stdout.decode())
        v = next((s for s in info["streams"] if s["codec_type"] == "video"), {})
        dur = float(info["format"]["duration"])
        ok = v.get("width") == 1080 and v.get("height") == 1920 and abs(dur - 2.0) < 0.1 and tr.get("visual_review", {}).get("ok") is True
        det = {"w": v.get("width"), "h": v.get("height"), "dur": dur, "visual_review": tr.get("visual_review")}
    elif tr.get("checked"):
        ok = tr["checked"].get("w") == 1080 and tr["checked"].get("h") == 1920 and tr.get("visual_review", {}).get("ok") is True
        det = tr
    r.add("final_render", "Final render 2 sn, 1080×1920, --quality final, ölçek 1, Türkçe karakterler doğru (görsel inceleme kaydı)", ok, det)
    g = results.get("gallery") or {}
    gok = g.get("components", 0) >= 37 and not g.get("failed") and g.get("visual_review", {}).get("ok") is True
    r.add("gallery", "Animasyon galerisi (bileşen başına 4 kare) üretildi ve görsel kontrolden geçti", gok,
          {"components": g.get("components"), "failed": g.get("failed"), "all_black": g.get("frames_all_black"), "visual_review": g.get("visual_review")})


def mcp_server_command(data_dir: Path) -> tuple[list[str], list[str]]:
    """.mcp.json'daki ad-memory tanımını Claude Code'un yapacağı gibi çözer; (komut + argümanlar, sorunlar)."""
    srv = (json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8")).get("mcpServers") or {}).get("ad-memory") or {}
    probs = []
    want = "/.venv/Scripts/python.exe" if os.name == "nt" else "/.venv/bin/python"
    cmd = str(srv.get("command", ""))
    if not cmd.startswith("${user_config.data_dir}/") or not cmd.endswith(want):
        probs.append(f"ad-memory komutu data_dir sanal ortamının bu işletim sistemine uygun Python'u değil ({cmd}); gen_config.py yeniden çalıştırılmalı")
    if re.search(r"[A-Za-z]:\\\\|[A-Za-z]:/|/Users/|/home/", json.dumps(srv)):
        probs.append("ad-memory tanımında gömülü makine yolu")
    sub = lambda v: str(v).replace("${user_config.data_dir}", str(data_dir)).replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT))  # noqa: E731
    return [sub(cmd), *[sub(a) for a in srv.get("args", [])]], probs


def check_admemory(r: Report, data_dir: Path, manifest: dict) -> None:
    py = venv_python(data_dir)
    argv, probs = mcp_server_command(data_dir)
    tmp = Path(tempfile.mkdtemp(prefix="doctor-mcp-"))
    try:
        # Sunucu .mcp.json'daki çözülmüş komutla (gerçek yorumlayıcı, plugin içindeki server.py) başlatılır.
        pr = _run([str(py), str(ROOT / "scripts" / "setup" / "mcp_probe.py"), "--plugin-root", str(ROOT), "--data-dir", str(tmp),
                   "--command", argv[0], "--server-args", json.dumps(argv[1:])], timeout=120,
                  env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        out = pr.stdout.decode("utf-8", "replace")
        try:
            tools = set(json.loads(out).get("tools", []))
        except json.JSONDecodeError:
            tools = set()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    missing = [t for t in TOOLS_7_3 if t not in tools]
    r.add("ad_memory_tools", "ad-memory .mcp.json komutuyla stdio'da başlıyor; 7.3'teki tüm araçlar listeleniyor", bool(tools) and not missing and not probs,
          {"count": len(tools), "missing": missing, "problems": probs, "command": argv[0]})
    from admem import db as DB  # noqa
    r.add("schema", "Şema migration'ları ve sürüm", DB.SCHEMA_VERSION >= 1, {"schema_version": DB.SCHEMA_VERSION})
    mt = (manifest.get("mcp_tools") or {}).get("ad-memory") or []
    r.add("manifest_tools", "Manifest araç listesi gerçek sunucuyla aynı", set(mt) == tools, {"manifest": len(mt), "server": len(tools)})


def check_taxonomy(r: Report) -> None:
    t = json.loads((ROOT / "servers" / "ad_memory" / "taxonomy.json").read_text(encoding="utf-8"))
    probs = []
    for k in ("taxonomy_version", "fixed_axes", "profile_axes", "special_values", "distance"):
        if k not in t:
            probs.append(f"alan yok: {k}")
    for ax, v in (t.get("profile_axes") or {}).items():
        if "values" in v and v["values"]:
            probs.append(f"profil ekseninde kurulumdan gelen değer: {ax}")
    r.add("taxonomy", "taxonomy.json şeması geçerli; profil eksenlerinde kurulumdan değer yok (ilke 12)", not probs, probs)


def check_manifest(r: Report, manifest: dict) -> None:
    sys.path.insert(0, str(ROOT / "scripts" / "setup"))
    import manifest as MF  # noqa
    cur = MF.build(ROOT, None)["component_hashes"]
    diff = [k for k, v in cur.items() if (manifest.get("component_hashes") or {}).get(k) != v]
    need = ["stages", "skills", "agents", "commands", "workflows", "hooks", "mcp_servers", "mcp_tools", "pipelines", "scripts", "tests",
            "deviations", "neutrality_audit", "live_checks", "component_hashes"]
    missing = [k for k in need if k not in manifest]
    r.add("manifest", "system_manifest.json tam ve gerçek bileşenlerle tutarlı (hash)", not diff and not missing and len(manifest.get("skills", [])) == 31,
          {"stale_components": diff, "missing_sections": missing})
    na = manifest.get("neutrality_audit") or {}
    covered = na.get("component_hashes") or {}
    stale = [k for k in ("skills", "agents", "commands", "workflows", "hooks", "ad_memory", "scripts", "templates") if covered.get(k) != cur.get(k)]
    r.add("neutrality", "Nötrlük denetimi temiz ve güncel dosyaları kapsıyor", na.get("status") == "clean" and not stale,
          {"status": na.get("status"), "stale": stale, "auditor": na.get("auditor")})
    wt = (manifest.get("tests") or {}).get("workflow_trial") or {}
    r.add("workflow_trial", "Deneme workflow'u çalıştı ya da yedek yol manifest'te", wt.get("path") in ("workflow", "fallback"), wt)
    ic = (manifest.get("tests") or {}).get("install_checks") or {}
    r.add("mcp_deferred", "Claude Code'un MCP araçlarını ertelemeli yüklediği doğrulandı (8.7)", ic.get("mcp_tools_deferred") is True, ic.get("mcp_tools_deferred_evidence"))
    r.add("official_sources", "Kurulumda resmi kaynaktan doğrulananlar kaydedildi (yükleme, exec+userConfig, hook olayları, FTS5, Remotion lisansı, yasal metinler)",
          bool(ic.get("official_sources")), ic.get("official_sources"))


def check_claude(r: Report, claude: str | None) -> None:
    if not claude:
        r.add("plugin_validate", "claude plugin validate hatasız", False, "claude yürütülebilir dosyası bulunamadı (--claude)")
        r.add("plugin_installed", "claude plugin list: kurulu ve etkin", False, "claude yok")
        return
    pv = _run([claude, "plugin", "validate", str(ROOT)], timeout=180)
    out = (pv.stdout + pv.stderr).decode("utf-8", "replace")
    r.add("plugin_validate", "claude plugin validate hatasız", pv.returncode == 0 and "Validation passed" in out, out.strip().splitlines()[-1:])
    # Marketplace adı kuruluma göre değişir (yerel: reklam-atolyesi-local, dağıtım: kendi adı); kimlik reklam-atolyesi@<marketplace>.
    pl = _run([claude, "plugin", "list", "--json"], timeout=180)
    rows = None
    if pl.returncode == 0:
        # Çıktı birden çok satırlı JSON dizisidir; öncesinde bilgi satırı olabilir: '[' ile başlayan ilk satırdan ayrıştırılır.
        lines = pl.stdout.decode("utf-8", "replace").splitlines()
        start = next((i for i, ln in enumerate(lines) if ln.lstrip().startswith("[")), None)
        try:
            rows = json.loads("\n".join(lines[start:])) if start is not None else None
        except json.JSONDecodeError:
            rows = None
    if isinstance(rows, list):
        mine = [x for x in rows if str(x.get("id", "")).startswith("reklam-atolyesi@")]
        enabled = any(x.get("enabled") is True and x.get("scope") == "user" for x in mine)
        det = [{k: x.get(k) for k in ("id", "version", "scope", "enabled")} for x in mine]
    else:  # --json'u desteklemeyen sürüm: metin çıktısı
        pl = _run([claude, "plugin", "list"], timeout=180)
        out = (pl.stdout + pl.stderr).decode("utf-8", "replace")
        m = re.search(r"reklam-atolyesi@[A-Za-z0-9._-]+[\s\S]{0,400}", out)
        det = m.group(0)[:300] if m else ""
        enabled = bool(m) and re.search(r"[Ee]nabled|✔", det) is not None and not re.search(r"[Dd]isabled", det.split("\n\n")[0])
    r.add("plugin_installed", "claude plugin list: reklam-atolyesi kurulu ve etkin (kullanıcı kapsamı)", enabled, det)


def load_install_deviations(data_dir: Path) -> list[dict]:
    import sqlite3
    db = data_dir / "db" / "ad-memory.sqlite"
    if not db.exists():
        return []
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        row = con.execute("SELECT value FROM settings WHERE key='install_deviations_json'").fetchone()
        con.close()
        return json.loads(row[0]) if row and row[0] else []
    except sqlite3.Error:
        return []


def merge_deviations(old: list[dict], new: list[dict]) -> list[dict]:
    by = {d.get("id"): d for d in old}
    for d in new:
        if not isinstance(d, dict) or not {"id", "check", "spec", "deviation", "decided_by", "status"} <= set(d):
            raise SystemExit(f"sapma kaydı eksik alanlı: {d}")
        by[d["id"]] = d
    return list(by.values())


def plugin_version() -> str:
    return json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]


def write_ok(data_dir: Path, manifest_sha: str, report: Report, dev_records: list[dict], update: bool = False) -> dict:
    from admem.store import Store
    from admem.util import now_iso
    ver = plugin_version()
    s = Store(data_dir / "db" / "ad-memory.sqlite", data_dir)
    try:
        ts = now_iso()
        s.settings_set("setup_static_ok_at", ts)
        if dev_records:
            s.settings_set("install_deviations_json", json.dumps(dev_records, ensure_ascii=False))
        detail = {"manifest_sha256": manifest_sha, "accepted_deviations": [i["key"] for i in report.items if i["accepted_deviation"]]}
        existing = s.qa("SELECT id FROM journal WHERE profile_id IS NULL AND type='setup' AND summary LIKE 'kurulum tamamlandı%'")
        if not existing:
            s.journal_log(f"kurulum tamamlandı · reklam-atolyesi {ver} · statik kontrol yeşil", None, type="setup", detail=detail)
        elif update:
            s.journal_log(f"güncelleme doğrulandı · reklam-atolyesi {ver} · statik kontrol yeşil", None, type="setup", detail=detail)
        s.mark_verified_if_ready()  # canlı maddeler daha önce geçtiyse kurulum şimdi doğrulanmış olur (1.4.1)
        for sub in ("logs", "backups", "memory/system", ".sessions"):
            (data_dir / sub).mkdir(parents=True, exist_ok=True)
        mark = data_dir / ".kurulum-statik-tamam"
        tmp = mark.with_suffix(".tmp")
        tmp.write_text(json.dumps({"plugin_version": ver, "manifest_sha256": manifest_sha, "setup_static_ok_at": ts,
                                   "accepted_deviations": [i["key"] for i in report.items if i["accepted_deviation"]]}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(mark)
        return {"written": True, "at": ts}
    finally:
        s.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--results-dir")
    ap.add_argument("--selftest-json")
    ap.add_argument("--claude")
    ap.add_argument("--skip-render", action="store_true")
    ap.add_argument("--run-tests", action="store_true")
    ap.add_argument("--write-ok", action="store_true")
    ap.add_argument("--json-out")
    ap.add_argument("--deviations-json", help="kurulum oturumunda kullanıcının kabul ettiği yerel sapmalar")
    ap.add_argument("--update", action="store_true",
                    help="kullanımdaki bir data_dir'de güncelleme doğrulaması: data_dir içerik listesi yerine yalnızca test artığı denetlenir")
    a = ap.parse_args()
    data_dir = Path(a.data_dir).resolve()
    rd = Path(a.results_dir) if a.results_dir else None
    results = {}
    if rd and rd.exists():
        for n in ("pytest", "smoke", "gallery", "turkish", "workflow_trial", "neutrality", "install_checks", "deviations"):
            f = rd / f"{n}.json"
            if f.exists():
                results[n] = json.loads(f.read_text(encoding="utf-8"))
    if a.selftest_json:
        results["smoke"] = json.loads(Path(a.selftest_json).read_text(encoding="utf-8"))
    mpath = ROOT / "system_manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {}
    # Kuruluma/makineye özgü, kullanıcının açıkça kabul ettiği sapmalar dağıtılan manifestte değil bu data_dir'in veritabanında
    # (settings.install_deviations_json) tutulur; kurulum oturumu --deviations-json ile verir, --write-ok başarılıysa kalıcı yazılır.
    # Kabul edilen sapma maddeyi engel olmaktan çıkarır ama madde kırmızı gösterilir. Eşleşme doctor kontrol anahtarıyla (check).
    dev_records = load_install_deviations(data_dir)
    if a.deviations_json:
        dev_records = merge_deviations(dev_records, json.loads(Path(a.deviations_json).read_text(encoding="utf-8")))
    deviations = {d.get("check"): d["deviation"] for d in dev_records
                  if d.get("decided_by") == "user" and d.get("status") == "accepted" and d.get("check")}
    r = Report()
    check_tools(r, data_dir)
    check_vendor(r)
    check_global_skills(r, deviations)
    check_components(r)
    check_scripts_map(r, manifest)
    check_hooks_exec(r, data_dir)
    check_render(r, results, a.skip_render, data_dir)
    check_tests(r, results, a.run_tests, data_dir)
    check_smoke(r, results.get("smoke"))
    check_admemory(r, data_dir, manifest)
    check_taxonomy(r)
    check_manifest(r, manifest)
    check_claude(r, find_claude(a.claude))
    check_disk(r, data_dir, deviations)
    check_data_dir_contents(r, data_dir, final=a.write_ok, update=a.update)
    blocking = r.blocking()
    out = {"ok": not blocking, "blocking": [b["key"] for b in blocking],
           "accepted_deviations": [i["key"] for i in r.items if i["accepted_deviation"]], "items": r.items}
    if a.write_ok:
        if blocking or a.skip_render:
            out["write_ok"] = {"written": False, "reason": "kırmızı madde var ya da render atlandı"}
        else:
            out["write_ok"] = write_ok(data_dir, sha(mpath), r, dev_records, update=a.update)
            r.items = [i for i in r.items if i["key"] != "data_dir_contents"]
            check_data_dir_contents(r, data_dir, final=True, update=a.update)
            out["items"] = r.items
    text = json.dumps(out, ensure_ascii=False, indent=1, default=str)
    if a.json_out:
        Path(a.json_out).write_text(text, encoding="utf-8")
    for i in r.items:
        mark = "✔" if i["ok"] else ("◐ kabul edilmiş sapma" if i["accepted_deviation"] else "✘")
        print(f"{mark} {i['title']}")
    print(json.dumps({"ok": out["ok"], "blocking": out["blocking"], "accepted_deviations": out["accepted_deviations"],
                      "write_ok": out.get("write_ok")}, ensure_ascii=False))
    sys.exit(0 if out["ok"] else 1)


if __name__ == "__main__":
    main()
