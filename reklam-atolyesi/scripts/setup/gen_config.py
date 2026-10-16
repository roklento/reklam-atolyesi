"""hooks/hooks.json ve .mcp.json üreticisi (spec 12.7, 13.6).

Hook'lar exec biçiminde yazılır: `command` yalnızca data_dir'deki sanal ortamın Python'u, `args` ayrı dizi. Windows'ta
`${user_config.data_dir}/.venv/Scripts/python.exe`, macOS/Linux'ta `${user_config.data_dir}/.venv/bin/python`.
`ad-memory` MCP sunucusu da aynı yorumlayıcıyla `${CLAUDE_PLUGIN_ROOT}/servers/ad_memory/server.py` olarak başlar: sanal ortamda
yalnızca bağımlılıklar vardır (proje kurulmaz), kod her zaman yüklü plugin sürümünün klasöründen okunur. Böylece güncellemede
sürüm klasörü değişse de sunucu eski sürüme bağlı kalmaz ve PATH'te `uv` gerekmez.
Hiçbir yerde makineye özgü gömülü yol yoktur; değerler Claude Code tarafından çözülür.
Kullanım: python gen_config.py <plugin-kökü> [--os windows|posix]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ELEVEN_MATCHER = r"^mcp__plugin_reklam-atolyesi_ElevenLabs__.*$|^mcp__.*__(creative_[a-z0-9_]+|agents_[a-z0-9_]+|get_more_tools)$"
META_MATCHER = r"^mcp__.*__ads_[a-z0-9_]+$"
TIMEOUT = 10


def py_command(target_os: str) -> str:
    return "${user_config.data_dir}/.venv/Scripts/python.exe" if target_os == "windows" else "${user_config.data_dir}/.venv/bin/python"


def hook(script: str, target_os: str) -> dict:
    return {"type": "command", "command": py_command(target_os),
            "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/" + script, "--data-dir", "${user_config.data_dir}"], "timeout": TIMEOUT}


def hooks_json(target_os: str) -> dict:
    return {
        "description": "reklam-atolyesi: plugin modu ve navigator, Meta izin listesi (hata durumunda engelleme), ElevenLabs maliyet koruması, "
                       "render mini-QC, kaydedilmemiş çıktı/devam notu uyarısı (spec 13.6). Plugin modu dışında yalnızca kendi Meta sunucusunun "
                       "izin listesi çalışır.",
        "hooks": {
            "UserPromptSubmit": [{"hooks": [hook("navigator.py", target_os)]}],
            "UserPromptExpansion": [{"matcher": "^reklam-atolyesi:.*$", "hooks": [hook("navigator.py", target_os)]}],
            "SessionStart": [{"matcher": "resume|compact", "hooks": [hook("session_start.py", target_os)]}],
            "PreToolUse": [
                {"matcher": META_MATCHER, "hooks": [hook("meta_guard.py", target_os)]},
                {"matcher": ELEVEN_MATCHER, "hooks": [hook("cost_guard.py", target_os)]},
            ],
            "PostToolUse": [{"matcher": "Bash|PowerShell", "hooks": [hook("render_qc.py", target_os)]}],
            "Stop": [{"hooks": [hook("stop_check.py", target_os)]}],
        },
    }


def mcp_json(target_os: str) -> dict:
    return {
        "mcpServers": {
            "ad-memory": {
                "type": "stdio",
                "command": py_command(target_os),
                "args": ["${CLAUDE_PLUGIN_ROOT}/servers/ad_memory/server.py"],
                "env": {
                    "AD_MEMORY_DB": "${user_config.data_dir}/db/ad-memory.sqlite",
                    "AD_MEMORY_DATA_DIR": "${user_config.data_dir}",
                    "PYTHONIOENCODING": "utf-8",
                },
            },
            "meta-ads": {"type": "http", "url": "https://mcp.facebook.com/ads"},
            "ElevenLabs": {"type": "http", "url": "https://api.us.elevenlabs.io/v1/mcp"},
        }
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("plugin_root")
    ap.add_argument("--os", choices=["windows", "posix"], default="windows" if os.name == "nt" else "posix")
    a = ap.parse_args()
    root = Path(a.plugin_root)
    (root / "hooks").mkdir(exist_ok=True)
    (root / "hooks" / "hooks.json").write_text(json.dumps(hooks_json(a.os), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (root / ".mcp.json").write_text(json.dumps(mcp_json(a.os), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"os": a.os, "hooks": str(root / "hooks" / "hooks.json"), "mcp": str(root / ".mcp.json")}))


if __name__ == "__main__":
    main()
