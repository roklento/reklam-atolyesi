"""2.5.0: değişmez kurallar dosyası (KURALLAR.md) — kısa liste ile tablo aynı, her kod referansı ve test gerçekten var, hook'lar
kuralları plugin modu açılırken ve compact sonrası bağlama verir, plugin modu dışında vermez."""
from __future__ import annotations

import json
import re
import sys

from conftest import ROOT, run_hook

sys.path.insert(0, str(ROOT / "hooks"))
import plugin_mode as pm  # noqa: E402

RULES = ROOT / "KURALLAR.md"


def table_rows() -> list[dict]:
    rows = []
    for ln in RULES.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*(K\d{2})\s*\|(.*)\|\s*$", ln)
        if m:
            cells = [c.strip() for c in m.group(2).split("|")]
            rows.append({"code": m.group(1), "rule": cells[0], "why": cells[1], "code_refs": cells[2], "tests": cells[3], "source": cells[4]})
    return rows


def refs(cell: str) -> list[tuple[str, str | None]]:
    out = []
    for r in re.findall(r"`([^`]+)`", cell):
        path, _, sym = r.partition("::")
        out.append((path, sym or None))
    return out


def symbol_defined(path, sym: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return sym in json.loads(text)
    return re.search(rf"^\s*(def|class)\s+{re.escape(sym)}\b|^\s*{re.escape(sym)}\s*=", text, re.M) is not None


def test_short_list_and_table_carry_the_same_codes():
    short = [ln.split()[0] for ln in pm.rules_short(RULES)]
    rows = [r["code"] for r in table_rows()]
    assert short == rows == [f"K{i:02d}" for i in range(1, len(rows) + 1)]
    assert len(rows) >= 15


def test_every_code_reference_exists():
    for r in table_rows():
        cr = refs(r["code_refs"])
        assert cr, f"{r['code']} kodla zorlanan yer göstermiyor"
        for path, sym in cr:
            p = ROOT / path
            assert p.exists(), f"{r['code']}: {path} yok"
            if sym:
                assert symbol_defined(p, sym), f"{r['code']}: {path}::{sym} tanımlı değil"


def test_every_listed_test_exists():
    for r in table_rows():
        tr = refs(r["tests"])
        assert tr, f"{r['code']} için test yok"
        for path, name in tr:
            p = ROOT / path
            assert p.exists(), f"{r['code']}: {path} yok"
            assert name and re.search(rf"^def {re.escape(name)}\(", p.read_text(encoding="utf-8"), re.M), f"{r['code']}: {path}::{name} yok"


def test_rules_block_fallback_never_raises(tmp_path):
    assert pm.rules_short(tmp_path / "yok.md")[0].startswith("K--")
    bad = tmp_path / "bozuk.md"
    bad.write_text("başlıksız", encoding="utf-8")
    assert pm.rules_short(bad)[0].startswith("K--")


def test_navigator_injects_rules_once_on_entry_and_session_start_after_compact(store, data_dir):
    sid = "kural-oturum-01"
    first = run_hook("navigator.py", {"session_id": sid, "hook_event_name": "UserPromptSubmit", "prompt": "reklam-atolyesi", "prompt_id": "a1"}, data_dir)
    ctx = first["hookSpecificOutput"]["additionalContext"]
    assert "Değişmez kurallar" in ctx and "K10 " in ctx
    again = run_hook("navigator.py", {"session_id": sid, "hook_event_name": "UserPromptSubmit", "prompt": "devam edelim", "prompt_id": "a2"}, data_dir)
    assert "Değişmez kurallar" not in again["hookSpecificOutput"]["additionalContext"]  # her istemde tekrar edilmez
    comp = run_hook("session_start.py", {"session_id": sid, "source": "compact"}, data_dir)
    assert "K01 " in comp["hookSpecificOutput"]["additionalContext"]
    # plugin modu dışındaki oturuma hiçbir şey eklenmez
    assert run_hook("navigator.py", {"session_id": "baska-02", "hook_event_name": "UserPromptSubmit", "prompt": "merhaba"}, data_dir) is None


def test_mcp_instructions_point_to_rules():
    text = (ROOT / "servers" / "ad_memory" / "server.py").read_text(encoding="utf-8")
    assert "KURALLAR.md" in text
