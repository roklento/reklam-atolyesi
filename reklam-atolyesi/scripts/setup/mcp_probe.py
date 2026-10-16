"""ad-memory MCP sunucusunu gerçek stdio üzerinden başlatıp araç listesini döndürür (doctor ve testler kullanır)."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def probe(plugin_root: Path, data_dir: Path, call: str | None, args_json: str | None,
                command: str | None = None, server_args: list[str] | None = None) -> dict:
    env = dict(os.environ)
    env.update({"AD_MEMORY_DB": str(data_dir / "db" / "ad-memory.sqlite"), "AD_MEMORY_DATA_DIR": str(data_dir),
                "PYTHONIOENCODING": "utf-8"})
    data_dir.mkdir(parents=True, exist_ok=True)
    # Varsayılan: bu yorumlayıcı + server.py. doctor .mcp.json'daki çözülmüş komutu verir (kurulu tanım gerçekten denenir).
    # Çalışma klasörü plugin dışıdır: sunucu kodu klasöre değil betik yoluna dayanmalı (Claude Code da oturum klasöründen başlatır).
    params = StdioServerParameters(command=command or sys.executable,
                                   args=server_args or [str(plugin_root / "servers" / "ad_memory" / "server.py")], env=env,
                                   cwd=str(data_dir))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            tools = await s.list_tools()
            out = {"server": init.serverInfo.name, "tools": sorted(t.name for t in tools.tools)}
            if call:
                res = await s.call_tool(call, json.loads(args_json or "{}"))
                out["call"] = {"isError": res.isError, "content": [c.text for c in res.content if hasattr(c, "text")]}
            return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plugin-root", required=True)
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--call")
    ap.add_argument("--args")
    ap.add_argument("--command", help="sunucu yorumlayıcısı (varsayılan: bu Python)")
    ap.add_argument("--server-args", help="sunucu argümanları, JSON dizi (varsayılan: [<plugin>/servers/ad_memory/server.py])")
    a = ap.parse_args()
    res = asyncio.run(probe(Path(a.plugin_root), Path(a.data_dir), a.call, a.args, a.command,
                            json.loads(a.server_args) if a.server_args else None))
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
