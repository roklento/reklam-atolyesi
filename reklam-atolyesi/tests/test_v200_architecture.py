"""2.0.0 mimari denetimi: iki oturum (iki süreç, iki bağlantı) aynı kampanyada; migration ayrıştırıcısının sınırları."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from admem import db
from admem.store import Store
from admem.util import AdMemoryError
from conftest import out_file
from test_store_stage import advance_to, new_campaign


def test_concurrent_gate_approve_advances_once(store, data_dir):
    pid, cid, cyid = new_campaign(store)
    advance_to(store, pid, cid, cyid, "S08")
    store.stage_start(pid, "S08", cid, cyid)
    r = store.stage_complete(pid, "S08", [{"path": out_file(store, pid, cid, "stil.md")}], "stil", cid, cyid)
    other = Store(data_dir / "db" / "ad-memory.sqlite", data_dir)  # ikinci oturumun MCP sunucusu
    try:
        run = r["stage_run"]
        real = other._gate_blockers

        def race(p, rr):  # ikinci oturum denetimlerini geçtiği anda ilk oturum aynı kapıyı onaylar
            store.gate_approve(pid, run["id"], run["output_version"], "onaylıyorum", cycle_id=cyid)
            return real(p, rr)
        other._gate_blockers = race
        with pytest.raises(AdMemoryError, match="başka bir oturumda"):
            other.gate_approve(pid, run["id"], run["output_version"], "evet", cycle_id=cyid)
    finally:
        other.close()
    assert store.q1("SELECT stage FROM campaigns WHERE id=?", (cid,))["stage"] == "S09"
    assert store.q1("SELECT COUNT(*) AS n FROM decisions WHERE stage='S08' AND decision='approved'")["n"] == 1


def test_stage_complete_rechecks_stage_inside_transaction(store, data_dir):
    pid, cid, cyid = new_campaign(store)
    advance_to(store, pid, cid, cyid, "S07")
    store.stage_start(pid, "S07", cid, cyid)
    f = out_file(store, pid, cid, "analiz.md")
    real = store._scope_key

    def moved(*a):  # aşama denetiminden sonra, işlemden önce başka oturum aşamayı geri aldı
        store.ex("UPDATE campaigns SET stage='S06' WHERE id=?", (cid,))
        return real(*a)
    store._scope_key = moved
    with pytest.raises(AdMemoryError, match="başka aşamaya geçti"):
        store.stage_complete(pid, "S07", [{"path": f}], "analiz", cid, cyid)
    assert store.q1("SELECT stage FROM campaigns WHERE id=?", (cid,))["stage"] == "S06"


def test_migrations_safe_for_simple_splitter():
    # db._split_sql satır yorumunu "--"dan keser ve ";"de böler: dize içinde "--" ya da ";" olan ya da tetikleyici gövdeli migration
    # sessizce bozulurdu. Yeni migration bu sınırlara uymalı.
    for f in sorted(db.MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql")):
        sql = f.read_text(encoding="utf-8")
        assert "CREATE TRIGGER" not in sql.upper(), f.name
        for ln in sql.splitlines():
            code = ln.split("--")[0]
            assert code.count("'") % 2 == 0, (f.name, ln)
            assert not any(";" in q for q in re.findall(r"'[^']*'", code)), (f.name, ln)


def test_parallel_hooks_and_server_do_not_lose_session_writes(store, data_dir):
    import json
    import subprocess
    import sys
    from concurrent.futures import ThreadPoolExecutor
    from conftest import ROOT, make_active_profile, run_hook
    sid = "paralel-oturum-01"
    run_hook("navigator.py", {"session_id": sid, "hook_event_name": "UserPromptSubmit", "prompt": "Reklam Atölyesi", "prompt_id": "p1"}, data_dir)
    sp = data_dir / ".sessions" / f"{sid}.json"
    s = json.loads(sp.read_text(encoding="utf-8"))
    s["library_query_limit"] = 6
    sp.write_text(json.dumps(s), encoding="utf-8")
    pid = make_active_profile(store)["profile"]["id"]
    payload = json.dumps({"session_id": sid, "tool_name": "mcp__plugin_reklam-atolyesi_meta-ads__ads_library_search", "tool_input": {}}).encode()

    def hook(_):
        r = subprocess.run([sys.executable, str(ROOT / "hooks" / "meta_guard.py"), "--data-dir", str(data_dir)], input=payload, capture_output=True)
        return b"deny" in r.stdout

    with ThreadPoolExecutor(8) as ex:  # Claude'un paralel Reklam Kütüphanesi sorguları + aynı anda oturum bağlama
        fut = ex.submit(lambda: [store.session_bind(sid, pid) for _ in range(5)])
        denied = list(ex.map(hook, range(8)))
        fut.result()
    final = json.loads(sp.read_text(encoding="utf-8"))
    assert sum(denied) == 2 and final["library_budget"]["used"] == 6  # bütçe tam: kayıp artış yok
    assert final["profile_id"] == pid and final["plugin_mode"]  # sunucunun bağlaması hook yazımında kaybolmadı
    assert not list((data_dir / ".sessions").glob("*.lock"))


def test_backup_is_verified_and_restore_keeps_previous(store, data_dir):
    import json
    import subprocess
    import sys
    from conftest import ROOT, make_active_profile
    make_active_profile(store, "Önce")
    b = store.backup(reason="deneme")
    assert not list((data_dir / "backups").glob("*.part"))
    make_active_profile(store, "Sonra", "act_B", "Ürün B")
    tool = [sys.executable, str(ROOT / "scripts" / "setup" / "db_restore.py")]
    chk = json.loads(subprocess.run(tool + ["check", "--data-dir", str(data_dir)], capture_output=True, check=True).stdout)
    assert [x["path"] for x in chk["backups"]] == [b["path"]]  # yeni kurulumda boş veritabanının migration yedekleri alınmaz
    assert chk["db"]["check"] == "ok" and chk["backups"][0]["check"] == "ok" and chk["backups"][0]["schema_version"] == db.SCHEMA_VERSION
    dry = json.loads(subprocess.run(tool + ["restore", "--data-dir", str(data_dir), "--backup", b["path"]], capture_output=True, check=True).stdout)
    assert dry["dry_run"]
    store.close()
    out = json.loads(subprocess.run(tool + ["restore", "--data-dir", str(data_dir), "--backup", b["path"], "--confirm"],
                                    capture_output=True, check=True).stdout)
    assert out["restored"] and out["check"] == "ok"
    s2 = Store(data_dir / "db" / "ad-memory.sqlite", data_dir)
    try:
        assert [p["name"] for p in s2.profile_list()["profiles"]] == ["Önce"]
    finally:
        s2.close()
    assert (Path(out["previous_kept_in"]) / "ad-memory.sqlite").exists()  # geri dönüş öncesi veritabanı silinmedi
    bad = data_dir / "backups" / "ad-memory-20990101T000000Z-bozuk.sqlite"
    bad.write_bytes(b"SQLite format 3\x00" + b"\x00" * 200)
    r = subprocess.run(tool + ["restore", "--data-dir", str(data_dir), "--backup", str(bad), "--confirm"], capture_output=True)
    assert r.returncode != 0 and "bütünlük" in r.stderr.decode("utf-8")
