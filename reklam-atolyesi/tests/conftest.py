"""Ortak test düzeni: her test geçici bir data_dir'de çalışır (nötr sentetik veri; ilke 12, spec 12.12)."""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "servers" / "ad_memory"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
for sub in ("analytics", "audio", "analyze", "compose", "competitive", "ingest", "meta", "qc", "render", "setup", "selftest"):
    sys.path.insert(0, str(ROOT / "scripts" / sub))

from admem import util  # noqa: E402
from admem.store import Store  # noqa: E402


class Clock:
    def __init__(self, start: str = "2026-03-02T09:00:00Z"):
        self.now = util.parse_iso(start)

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now = self.now + dt.timedelta(**kw)


@pytest.fixture
def clock():
    c = Clock()
    util.set_clock(c)
    yield c
    util.set_clock(None)


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "veri dizini ğüş"  # boşluk ve Türkçe karakterli data_dir (12.10)
    d.mkdir()
    return d


@pytest.fixture
def store(data_dir, clock):
    s = Store(data_dir / "db" / "ad-memory.sqlite", data_dir)
    yield s
    s.close()


def make_active_profile(s: Store, name: str = "Marka A", account: str = "act_A", product: str = "Ürün A", mode: str = "mcp") -> dict:
    p = s.profile_create(name)
    s.brand_upsert(p["id"], name=name, meta_ad_account_id=account, timezone="Europe/Istanbul", tone="nötr")
    s.profile_update(p["id"], meta_data_mode=mode, history_status="no_history")
    # Satış sonuçlu sentetik kampanyalar için Meta satış sinyali (1.4.7); sinyalsiz durum ayrıca test edilir.
    s.meta_signal_set(p["id"], "purchase_seen", "meta_mcp", "sentetik veri kümesi: Purchase son 7 gün")
    run = s.stage_start(p["id"], "S00a")
    f = s.profile_dir(p["id"]) / "brand" / "s00a.md"
    f.write_text("marka özeti", encoding="utf-8")
    r = s.stage_complete(p["id"], "S00a", [{"path": str(f)}], "marka tanışması")
    s.gate_approve(p["id"], r["stage_run"]["id"], r["stage_run"]["output_version"], "onaylıyorum")
    s.profile_update(p["id"], status="active")
    prod = s.product_upsert(p["id"], product, price=100, currency="TRY",
                            economics_json={"contribution": 40, "confirmed": True, "net_basket": 120},
                            provable_claims_json=[{"code": "c1", "text": "Örnek iddia", "proof_type": "process", "documented": True}],
                            occasions_json=[{"code": "an-a", "label": "Örnek an"}],
                            buyers_json=[{"code": "alici-a", "label": "Örnek alıcı"}])
    pf = s.profile_dir(p["id"]) / "products" / "s00c.md"
    pf.write_text("ürün tanışması", encoding="utf-8")
    r = s.stage_complete(p["id"], "S00c", [{"path": str(pf)}], "ürün tanışması", scope_key=f"product:{prod['id']}")
    s.gate_approve(p["id"], r["stage_run"]["id"], r["stage_run"]["output_version"], "evet onaylıyorum")
    return {"profile": s._profile(p["id"]), "product": s._product(p["id"], prod["id"])}


def out_file(s: Store, pid: int, cid: int, name: str, content: str = "çıktı") -> str:
    p = s.campaign_dir(pid, cid) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return str(p)


@pytest.fixture
def venv_python():
    return sys.executable


def run_hook(script: str, payload: dict, data_dir: Path | None, env: dict | None = None) -> dict | None:
    args = [sys.executable, str(ROOT / "hooks" / script)]
    if data_dir is not None:
        args += ["--data-dir", str(data_dir)]
    e = dict(os.environ)
    e.pop("CLAUDE_PLUGIN_OPTION_DATA_DIR", None)
    e.update(env or {})
    r = subprocess.run(args, input=json.dumps(payload).encode("utf-8"), capture_output=True, timeout=30, env=e)
    out = r.stdout.decode("utf-8").strip()
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    return json.loads(out) if out else None
