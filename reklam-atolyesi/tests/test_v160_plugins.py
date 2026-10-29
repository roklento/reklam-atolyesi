"""1.6.0 A: kurulum denetimi tüm plugin'leri kapsar (marketplace, claude.ai senkronu, skills-dir); sınıflandırma, kullanıcı kararı, uyarı."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

import doctor as DR
import kurulum_dogrula as KD
import plugin_scan as PS
from conftest import ROOT

sys.path.insert(0, str(ROOT / "hooks"))


def _plugin(base: Path, name: str, skills: dict[str, str] = None, mcp: dict = None, hooks: list[str] = None) -> Path:
    (base / ".claude-plugin").mkdir(parents=True)
    (base / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": name}), encoding="utf-8")
    for sk, desc in (skills or {}).items():
        (base / "skills" / sk).mkdir(parents=True)
        (base / "skills" / sk / "SKILL.md").write_text(f"---\nname: {sk}\ndescription: {desc}\n---\n\ngövde", encoding="utf-8")
    if mcp:
        (base / ".mcp.json").write_text(json.dumps({"mcpServers": mcp}), encoding="utf-8")
    if hooks:
        (base / "hooks").mkdir()
        (base / "hooks" / "hooks.json").write_text(json.dumps({"hooks": {e: [] for e in hooks}}), encoding="utf-8")
    return base


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """Sahte ~/.claude: marketplace'ten Remotion, senkron ElevenLabs (kuruma zorunlu), zararsız bir plugin, skills-dir plugin ve kendimiz."""
    home = tmp_path / "ev"
    root = home / ".claude" / "plugins"
    cache = root / "cache"
    rem = _plugin(cache / "remotion" / "remotion" / "1.0.0", "remotion",
                  {"remotion-best-practices": "Best practices for Remotion - video creation in React"})
    self_ = _plugin(cache / "yerel" / "reklam-atolyesi" / "1.6.0", "reklam-atolyesi", {"compose": "video kurgu"})
    notes = _plugin(cache / "m" / "notlar" / "0.1.0", "notlar", {"toplanti-notu": "Toplantı notlarını özetler"}, hooks=["SessionStart"])
    (root / "installed_plugins.json").parent.mkdir(parents=True, exist_ok=True)
    (root / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
        "remotion@remotion": [{"scope": "user", "installPath": str(rem), "version": "1.0.0"}],
        "reklam-atolyesi@yerel": [{"scope": "user", "installPath": str(self_), "version": "1.6.0"}],
        "notlar@m": [{"scope": "user", "installPath": str(notes), "version": "0.1.0"}]}}), encoding="utf-8")
    acct = root / "synced" / "org_user"
    _plugin(acct / "ses", "ses", {"seslendirme": "Metni sese çevirir"},
            mcp={"ElevenLabs": {"type": "http", "url": "https://api.elevenlabs.io/mcp"}}, hooks=["PreToolUse"])
    (acct / "ses.meta.json").write_text(json.dumps({"installation_preference": "required"}), encoding="utf-8")
    _plugin(home / ".claude" / "skills" / "altyazi-araci", "altyazi-araci", {"altyazi": "Videolara altyazı ekler"})
    (home / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": {"notlar@m": True}}), encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("CLAUDE_CODE_PLUGIN_CACHE_DIR", str(root))
    return home


def test_disk_scan_covers_all_plugin_kinds_and_classifies(fake_home):
    sc = PS.scan(use_cli=False)
    assert sc["source"] == "disk"
    ids = {p["id"]: p for p in sc["plugins"]}
    assert set(ids) == {"remotion@remotion", "notlar@m", "ses@synced", "altyazi-araci@skills-dir"}  # kendimiz hariç
    assert ids["remotion@remotion"]["categories"]["video"] == ["remotion-best-practices"]
    assert ids["ses@synced"]["categories"]["paid_or_write"] == ["ElevenLabs"] and ids["ses@synced"]["required_by_org"]
    assert ids["ses@synced"]["categories"]["hooks"] == ["PreToolUse"]
    assert ids["altyazi-araci@skills-dir"]["categories"]["video"] == ["altyazi"]
    assert ids["notlar@m"]["categories"] == {"video": [], "paid_or_write": [], "hooks": []}  # SessionStart araç kullanımına girmez
    assert sc["clash"] == ["altyazi-araci@skills-dir", "remotion@remotion", "ses@synced"]


def test_disabled_plugin_is_not_a_clash(fake_home):
    (fake_home / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": {"remotion@remotion": False}}), encoding="utf-8")
    assert "remotion@remotion" not in PS.scan(use_cli=False)["clash"]


def test_cli_json_preferred_and_falls_back_to_disk(fake_home, monkeypatch):
    rem = str(next((fake_home / ".claude" / "plugins" / "cache" / "remotion").rglob("1.0.0")))
    out = "Bilgi satırı\n" + json.dumps([{"id": "remotion@remotion", "version": "1.0.0", "scope": "user", "enabled": True, "installPath": rem},
                                          {"id": "x@y", "scope": "project", "enabled": True, "installPath": rem + "-yok",
                                           "mcpServers": {"replicate": {"command": "npx", "args": ["replicate-mcp"]}}}], indent=1)
    monkeypatch.setattr(PS.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 0, out.encode(), b""))
    sc = PS.scan("claude")
    assert sc["source"] == "cli" and sc["clash"] == ["remotion@remotion", "x@y"]
    monkeypatch.setattr(PS.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 1, b"", b"hata"))
    sc = PS.scan("claude")
    assert sc["source"] == "disk" and sc["notes"] and "ses@synced" in sc["clash"]


def test_provider_match_is_token_based_not_substring():
    r = PS.rules()
    info = {"skills": [{"name": "rapor", "description": "metadata ve ölçüm raporu"}], "hook_events": [],
            "mcp_servers": {"metabase": "npx metabase-mcp", "falcon-db": "uvx falcon"}}
    assert PS.classify(info, None, r) == {"video": [], "paid_or_write": [], "hooks": []}
    assert PS.classify({"mcp_servers": {"meta-ads": "https://mcp.facebook.com/ads"}}, None, r)["paid_or_write"] == ["meta-ads"]


def test_handle_plugins_decisions(fake_home, data_dir, monkeypatch):
    monkeypatch.setattr(PS, "rows_from_cli", lambda *a, **k: None)  # tarama diskten (makinedeki gerçek claude okunmaz)
    rec, det = KD.handle_plugins(data_dir, "sor", interactive=False, claude=None)
    assert rec is None and "verilmedi" in det["karar"] and len(det["clash"]) == 3
    rec, det = KD.handle_plugins(data_dir, "birak", interactive=False, claude=None)
    assert rec["check"] == "plugins" and rec["decided_by"] == "user" and rec["status"] == "accepted"
    assert rec["plugin_ids"] == ["altyazi-araci@skills-dir", "remotion@remotion", "ses@synced"]
    calls = []

    def fake_run(args, **k):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, b"Disabled", b"")
    monkeypatch.setattr(PS.subprocess, "run", fake_run)
    monkeypatch.setattr(DR, "find_claude", lambda c=None: "claude")
    rec, det = KD.handle_plugins(data_dir, "devre-disi", interactive=False, claude="claude")
    # kuruma zorunlu senkron plugin kapatılmaz, sapma olarak kalır; ötekiler `claude plugin disable` ile (kaldırma yok)
    assert ["claude", "plugin", "disable", "remotion@remotion", "--scope", "user"] in calls
    assert not any("ses@synced" in c for c in calls) and not any("uninstall" in c for c in calls)
    assert det["karar"].startswith("kısmen kapatıldı") and rec["plugin_ids"] == ["ses@synced"]


def test_doctor_check_plugins_accepts_by_id_only(fake_home):
    monkey_rec = {"id": "other_plugins", "check": "plugins", "plugin_ids": ["altyazi-araci@skills-dir", "remotion@remotion", "ses@synced"],
                  "deviation": "açık bırakıldı", "decided_by": "user", "status": "accepted"}
    r = DR.Report()
    DR.check_plugins(r, [monkey_rec], None)
    it = r.items[0]
    assert it["key"] == "plugins" and it["ok"] is False and it["accepted_deviation"] and not r.blocking()
    r = DR.Report()
    DR.check_plugins(r, [{**monkey_rec, "plugin_ids": ["remotion@remotion"]}], None)  # sonradan gelen plugin kabulde yok
    assert r.items[0]["ok"] is False and r.blocking()


def test_navigator_warns_only_for_unaccepted(fake_home, store, data_dir):
    import navigator as NV
    line = NV.plugin_clash_line(data_dir)
    assert line.startswith("UYARI") and "remotion@remotion" in line
    con = sqlite3.connect(data_dir / "db" / "ad-memory.sqlite")
    con.execute("INSERT OR REPLACE INTO settings(key, value, updated_at) VALUES('install_deviations_json', ?, '2026-10-29T00:00:00Z')",
                (json.dumps([{"id": "other_plugins", "check": "plugins", "status": "accepted",
                              "plugin_ids": ["altyazi-araci@skills-dir", "remotion@remotion", "ses@synced"]}]),))
    con.commit()
    con.close()
    assert NV.plugin_clash_line(data_dir) is None


def test_setup_wiring_and_docs():
    ps1 = (ROOT / "scripts" / "setup" / "windows" / "kurulum.ps1").read_text(encoding="utf-8-sig")
    assert '"--plugins", $Plugins' in ps1 and '[ValidateSet("sor", "devre-disi", "birak")][string]$Plugins' in ps1
    kk = (ROOT / "commands" / "kurulum-kontrol.md").read_text(encoding="utf-8")
    assert "plugin_scan.py" in kk and "required_by_org" in kk
    assert "öteki plugin" in (ROOT / "skills" / "ref-vendor-map" / "SKILL.md").read_text(encoding="utf-8")
