"""Ücretli üretim: kanonik hash, tahmin → onay → tek kullanımlık atomik rezervasyon, belirsiz sonuç (spec 9.1, 7.4, 12.12 adım 7)."""
from __future__ import annotations

import threading

import pytest

from admem import hashing
from admem.store import Store
from admem.util import AdMemoryError
from conftest import make_active_profile

P = {"prompt": "Örnek metin", "model_id": "eleven_v4", "voice_id": "vx", "flow_id": "f1"}
LIC = {"license": {"source": "plan sayfası", "checked_at": "2026-03-02", "scope": "reklam"}}


def setup(store):
    a = make_active_profile(store)
    c = store.campaign_create(a["profile"]["id"], a["product"]["id"], "K")
    return a["profile"]["id"], c["campaign"]["id"], c["cycle"]["id"]


def test_hash_excludes_ui_fields_and_fills_defaults():
    h1 = hashing.params_hash("mcp__x__creative_generate_speech", {**P, "context": "a", "estimate_only": True})
    h2 = hashing.params_hash("mcp__plugin_reklam-atolyesi_ElevenLabs__creative_generate_speech", {**P, "context": "b", "generations_count": 4})
    h3 = hashing.params_hash("creative_generate_speech", {**P, "generations_count": 2})
    assert h1 == h2 != h3
    assert hashing.params_hash("creative_generate_speech", {**P, "view_state_id": "z"}) == h1


def test_single_use_approval_and_no_auto_retry(store):
    pid, cid, cyid = setup(store)
    g = store.generation_log(pid, cid, cyid, "creative_generate_speech", P, 120)
    h = g["params_hash"]
    assert not store.generation_reserve(cid, h, "t0")["ok"]  # onay yok
    with pytest.raises(AdMemoryError):
        store.generation_approve(pid, g["id"], 120, 4, "evet", {})  # lisans kontrolü yok
    with pytest.raises(AdMemoryError):
        store.generation_approve(pid, g["id"], 120, 2, "evet", LIC)  # adet uyuşmuyor
    store.generation_approve(pid, g["id"], 150, 4, "onaylıyorum", LIC)
    assert store.generation_reserve(cid, h, "t1")["ok"]
    assert not store.generation_reserve(cid, h, "t2")["ok"]  # onay tüketildi / süren talep
    with pytest.raises(AdMemoryError):  # zaman aşımı failed değil unknown'dır
        store.generation_update(pid, g["id"], status="failed", error={"kind": "timeout"})
    store.generation_update(pid, g["id"], status="unknown", error={"kind": "timeout"})
    again = store.generation_log(pid, cid, cyid, "creative_generate_speech", P, 120)
    assert again.get("blocked")  # belirsiz talep yeniden açılmaz
    with pytest.raises(AdMemoryError):
        store.generation_update(pid, g["id"], status="completed")  # kanıt yok
    store.generation_update(pid, g["id"], status="completed", evidence="flow durumu: completed", cost_credits=118)
    done = store.generation_log(pid, cid, cyid, "creative_generate_speech", P, 120)
    assert done.get("blocked")
    new = store.generation_log(pid, cid, cyid, "creative_generate_speech", P, 120, new_take=True)
    assert new["request_no"] == 2 and new["status"] == "estimated"


def test_concurrent_reservation_only_one(store, data_dir):
    pid, cid, cyid = setup(store)
    g = store.generation_log(pid, cid, cyid, "creative_generate_image", {"prompt": "doku", "model_id": "m"}, 50)
    store.generation_approve(pid, g["id"], 50, 4, "evet", LIC)
    results = []

    def worker(i):
        s = Store(data_dir / "db" / "ad-memory.sqlite", data_dir)
        try:
            results.append(s.generation_reserve(cid, g["params_hash"], f"tu{i}")["ok"])
        finally:
            s.close()
    ts = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert results.count(True) == 1


def test_run_flow_requires_snapshot_hash(store):
    pid, cid, cyid = setup(store)
    with pytest.raises(AdMemoryError):
        store.generation_log(pid, cid, cyid, "creative_run_flow_nodes", {"flow_id": "f", "node_ids": ["n1"]}, 10)
    g = store.generation_log(pid, cid, cyid, "creative_run_flow_nodes", {"flow_id": "f", "node_ids": ["n2", "n1"]}, 10, flow_snapshot_sha256="abc")
    assert g["params_hash"] == hashing.params_hash("creative_run_flow_nodes", {"flow_id": "f", "node_ids": ["n1", "n2"]})


def test_personal_data_requires_basis(store):
    pid, cid, cyid = setup(store)
    g = store.generation_log(pid, cid, cyid, "creative_transcribe_audio", {"model_id": "eleven_scribe_v1", "connect_from": ["n1"]}, 3)
    with pytest.raises(AdMemoryError):
        store.generation_approve(pid, g["id"], 3, 1, "evet", {**LIC, "contains_personal_data": True})
    store.generation_approve(pid, g["id"], 3, 1, "evet", {**LIC, "contains_personal_data": True, "processing_permission_ref": "izin#1"})


def test_input_file_hashes_bind_approval_but_hook_matches_call(store):
    """params_hash girdi dosyası hash'lerini içerir; hook yalnızca çağrı parametrelerini görür → call_hash ile eşleşir (9.1)."""
    pid, cid, cyid = setup(store)
    params = {"prompt": "Örnek hareket", "model_id": "kling-3-pro", "flow_id": "f1", "connect_from": ["n2", "n1"]}
    files = {"n1": "a" * 64}
    g = store.generation_log(pid, cid, cyid, "creative_generate_video", params, 300, input_file_hashes=files)
    assert g["params_hash"] == hashing.params_hash("creative_generate_video", params, None, files)
    hook_hash = hashing.params_hash("mcp__plugin_reklam-atolyesi_ElevenLabs__creative_generate_video",
                                    {**params, "connect_from": ["n1", "n2"], "context": "x"}, None)
    assert g["call_hash"] == hook_hash != g["params_hash"]
    assert not store.generation_reserve(cid, hook_hash, "t0")["ok"]  # onaysız
    store.generation_approve(pid, g["id"], 300, 1, "onaylıyorum", LIC)
    assert store.generation_reserve(cid, hook_hash, "t1")["ok"]
    assert not store.generation_reserve(cid, hook_hash, "t2")["ok"]
