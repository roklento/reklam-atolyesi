"""Ücretli üretim çağrısı için tek kanonik params_hash (9.1).

Hem `generation_hash`/`generation_log` (ad-memory) hem `cost_guard` hook'u bu kodu kullanır; yalnızca standart kütüphane.
Hash yalnızca maliyeti ve çıktıyı belirleyen alanlardan hesaplanır. Hash'e GİRMEYENLER: estimate_only, context,
view_state_id ve benzeri arayüz alanları. Aracın varsayılanları (ör. generations_count=4) açıkça doldurulur ki
tahminde alanı yazmayıp gerçek çağrıda yazmak farklı hash üretmesin.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

EXCLUDED_KEYS = frozenset({"estimate_only", "context", "view_state_id", "ui_state", "view_id", "advertiser_job"})
TOOLS_FILE = Path(__file__).resolve().parents[3] / "hooks" / "elevenlabs_tools.json"


def load_tool_classes(path: Path | None = None) -> dict[str, Any]:
    p = path or TOOLS_FILE
    return json.loads(p.read_text(encoding="utf-8"))


def bare_tool_name(tool_name: str) -> str:
    """`mcp__<sunucu>__creative_generate_speech` → `creative_generate_speech`."""
    return tool_name.rsplit("__", 1)[-1] if "__" in tool_name else tool_name


def canonical_params(tool_name: str, params: dict[str, Any], classes: dict[str, Any] | None = None,
                     input_file_hashes: dict[str, str] | None = None) -> dict[str, Any]:
    classes = classes if classes is not None else load_tool_classes()
    name = bare_tool_name(tool_name)
    spec = classes.get("paid", {}).get(name, {})
    out: dict[str, Any] = {}
    for k, v in (params or {}).items():
        if k in EXCLUDED_KEYS:
            continue
        out[k] = v
    for k, v in spec.get("defaults", {}).items():
        out.setdefault(k, v)
    if isinstance(out.get("connect_from"), list):
        out["connect_from"] = sorted(out["connect_from"])
    if isinstance(out.get("node_ids"), list):
        out["node_ids"] = sorted(out["node_ids"])
    if input_file_hashes:
        out["__input_files"] = dict(sorted(input_file_hashes.items()))
    return {"tool": name, "params": out}


def params_hash(tool_name: str, params: dict[str, Any], classes: dict[str, Any] | None = None,
                input_file_hashes: dict[str, str] | None = None) -> str:
    c = canonical_params(tool_name, params, classes, input_file_hashes)
    raw = json.dumps(c, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generation_count(tool_name: str, params: dict[str, Any], classes: dict[str, Any] | None = None) -> int:
    c = canonical_params(tool_name, params, classes)
    try:
        return int(c["params"].get("generations_count", 1))
    except (TypeError, ValueError):
        return 1
