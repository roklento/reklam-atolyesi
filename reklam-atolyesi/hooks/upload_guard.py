"""2.10.12: dış sağlayıcıya dosya yüklemesinin bayt adımı (bölüm 10).

ElevenLabs'ta yerel dosya üç adımda gider: creative_create_asset_upload (ad, tür, boyut) → dönen upload_url'ye baytların PUT ile
gönderilmesi → creative_finalize_asset_upload(asset_id). Araç çağrıları baytları taşımadığı için izin denetimi (cost_guard) tek başına
gönderilen dosyanın izinli dosya olduğunu bilemez. Bu hook iki yerde çalışır:

- PostToolUse (creative_create_asset_upload): sağlayıcının verdiği asset_id ve upload_url, başlatma kaydına (pending_uploads) yazılır.
- PreToolUse (Bash, PowerShell, Write, Edit, NotebookEdit): bekleyen bir yükleme adresi komutta ya da yazılan dosyada geçiyorsa ve komut
  plugin'in yükleme betiği (scripts/ingest/izinli_yukleme.py) değilse reddedilir. Betik izin kaydındaki dosyayı kendisi açar.

Plugin modu dışında ve bekleyen yükleme yokken hiçbir şey yapmaz. Ağ çağrısı yapılmaz.
"""
from __future__ import annotations

import json
import re
import sys

import plugin_mode as pm
import cost_guard as CG

UPLOAD_START = "creative_create_asset_upload"
SCRIPT = "izinli_yukleme.py"
BYTE_TOOLS = {"Bash", "PowerShell", "Write", "Edit", "NotebookEdit"}


def find_ids(obj, depth: int = 0) -> dict:
    """Araç yanıtında asset_id ve upload_url (iç içe sözlük, liste ya da JSON metni)."""
    out: dict = {}
    if depth > 6 or obj is None:
        return out
    if isinstance(obj, dict):
        for k in ("asset_id", "upload_url"):
            if isinstance(obj.get(k), str) and obj[k].strip():
                out.setdefault(k, obj[k].strip())
        for v in obj.values():
            for k, val in find_ids(v, depth + 1).items():
                out.setdefault(k, val)
    elif isinstance(obj, list):
        for v in obj:
            for k, val in find_ids(v, depth + 1).items():
                out.setdefault(k, val)
    elif isinstance(obj, str):
        s = obj.strip()
        if s.startswith(("{", "[")):
            try:
                return find_ids(json.loads(s), depth + 1)
            except ValueError:
                pass
        for k in ("asset_id", "upload_url"):
            m = re.search(r'"%s"\s*:\s*"([^"]+)"' % k, s)
            if m:
                out.setdefault(k, m.group(1))
    return out


def record_start(data: dict, data_dir) -> None:
    sid = data.get("session_id")
    if not sid:
        return
    ids = find_ids(data.get("tool_response"))

    def put(s: dict) -> None:
        pend = CG.pending_uploads(s)
        cand = [u for u in pend if not u.get("asset_id") and not u.get("unverifiable")]
        if not cand:
            return
        u = max(cand, key=lambda x: float(x.get("t") or 0))
        if ids.get("asset_id") and ids.get("upload_url"):
            u["asset_id"], u["url"] = ids["asset_id"], ids["upload_url"]
        else:
            u["unverifiable"] = True  # dosyaya bağlı izinde tamamlama reddedilir
        s["pending_uploads"] = pend
    pm.update_session(data_dir, sid, put)


def guard_bytes(data: dict, data_dir) -> tuple[str, str | None]:
    tool = data.get("tool_name") or ""
    if tool not in BYTE_TOOLS:
        return "pass", None
    sid = data.get("session_id")
    sess = pm.load_session(data_dir, sid) if sid else None
    if not sess or not sess.get("plugin_mode"):
        return "pass", None
    keys = [k for k in (CG.url_key(u.get("url")) for u in CG.pending_uploads(sess)) if k]
    if not keys:
        return "pass", None
    text = json.dumps(data.get("tool_input") or {}, ensure_ascii=False).replace("\\/", "/")
    if not any(k in text for k in keys):
        return "pass", None
    cmd = str((data.get("tool_input") or {}).get("command") or "")
    if tool in ("Bash", "PowerShell") and SCRIPT in cmd.replace("\\", "/"):
        return "pass", None
    return "deny", ("dosya baytları dış sağlayıcıya yalnızca plugin'in yükleme betiğiyle gönderilir; betik izin kaydındaki dosyayı kendisi "
                    "açar: <python> <plugin_root>/scripts/ingest/izinli_yukleme.py --data-dir <data_dir> --session <session_id> "
                    "--asset-id <kimlik> (bölüm 10)")


def main() -> int:
    try:
        data = pm.read_input()
        data_dir = pm.data_dir_from_argv()
        event = data.get("hook_event_name") or ""
        if event == "PostToolUse":
            if pm.bare_tool(data.get("tool_name") or "") == UPLOAD_START:
                record_start(data, data_dir)
            return 0
        verdict, reason = guard_bytes(data, data_dir)
        if verdict == "deny":
            pm.deny(reason or "reddedildi")
        return 0
    except Exception:  # noqa: BLE001 — bu hook her Bash çağrısında çalışır; kendi hatası komutları durdurmaz
        return 0


if __name__ == "__main__":
    sys.exit(main())
