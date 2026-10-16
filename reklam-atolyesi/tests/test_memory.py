"""Hafıza (spec bölüm 8, 12.10 hafıza testleri, 12.12 adım 6). Örnek kelimeler nötrdür ("paket/paketleme" örnek)."""
from __future__ import annotations

import pytest

from admem.util import AdMemoryError, fts_query, tr_fold, tr_lower
from conftest import make_active_profile, out_file


def test_turkish_normalization():
    assert tr_lower("İÇERİK") == "içerik" and tr_lower("IŞIK") == "ışık"
    assert tr_fold("Işık Çiçeği") == "isik cicegi"
    assert fts_query("ab") is None
    assert "paket" in fts_query("PAKET")


def test_search_substring_and_folding(store):
    pid = make_active_profile(store)["profile"]["id"]
    store.memory_add("semantic", "note", "Paketleme sade tutulmalı (örnek)", "user", profile_id=pid, force_new=True)
    store.memory_add("semantic", "note", "IŞIK pencereden gelsin (örnek)", "user", profile_id=pid, force_new=True)
    assert store.memory_search("paket", profile_id=pid)["results"]               # alt dize: paket → paketleme
    assert store.memory_search("isik", profile_id=pid)["results"]                # aksansız sorgu
    assert store.memory_search("ışık", profile_id=pid)["results"]                # İ/ı duyarlı
    assert not store.memory_search("zzzqqq", profile_id=pid)["results"]          # eşleşmeme sınırı
    assert store.memory_search("pa", profile_id=pid)["results"]                  # < 3 harf: LIKE


def test_add_returns_candidates_and_observe_counts_unique(store):
    pid = make_active_profile(store)["profile"]["id"]
    r = store.memory_add("preference", "style", "Kullanıcı sade yazı tipini seviyor", "claude", profile_id=pid, tags=["stil"], evidence_id="m1")
    item = r["created"]
    assert item["status"] == "proposed"
    r2 = store.memory_add("preference", "style", "Sade yazı tipi tercih ediliyor", "claude", profile_id=pid, tags=["stil"])
    assert r2["created"] is None and r2["candidates"]  # yeni kayıt açılmaz, adaylar döner
    assert store.memory_observe(item["id"], "m1", profile_id=pid)["counted"] is False  # aynı kanıt tekrar sayılmaz
    store.memory_observe(item["id"], "m2", profile_id=pid)
    out = store.memory_observe(item["id"], "m3", profile_id=pid)
    assert out["item"]["observations"] == 3 and out["item"]["status"] == "active"  # üç tutarlı gözlem


def test_user_remember_is_active_and_forget_cleans(store, data_dir):
    pid = make_active_profile(store)["profile"]["id"]
    it = store.memory_add("preference", "note", "Örnek tercih unutulacak", "user", profile_id=pid, force_new=True)["created"]
    assert it["status"] == "active"
    store.journal_log("Örnek tercih unutulacak diye not edildi", profile_id=pid)
    store.export_markdown(pid)
    store.backup("test")
    res = store.memory_forget(it["id"], "bunu unut", profile_id=pid)
    assert res["backups_removed"] and res["new_backup"]
    assert not store.memory_search("unutulacak", profile_id=pid)["results"]
    assert not store.q1("SELECT 1 FROM memory_fts WHERE body LIKE '%unutulacak%'")
    assert store.q1("SELECT 1 FROM journal WHERE type='forget'")
    assert "unutulacak" not in (store.profile_dir(pid) / "memory" / "memory.md").read_text(encoding="utf-8")


def test_profile_isolation(store):
    a = make_active_profile(store, "Marka A", "act_a", "Ürün A")["profile"]["id"]
    b = make_active_profile(store, "Marka B", "act_b", "Ürün B")["profile"]["id"]
    store.memory_add("semantic", "note", "Gizli bilgi alfa", "user", profile_id=a, force_new=True)
    assert not store.memory_search("alfa", profile_id=b)["results"]
    it = store.q1("SELECT id FROM memory_items WHERE profile_id=?", (a,))
    with pytest.raises(AdMemoryError):
        store.memory_update(it["id"], profile_id=b, content="x")


def test_card_budget_keeps_critical(store):
    a = make_active_profile(store)
    pid = a["profile"]["id"]
    c = store.campaign_create(pid, a["product"]["id"], "Kampanya Kart")
    cid, cyid = c["campaign"]["id"], c["cycle"]["id"]
    for i in range(30):
        store.memory_add("preference", "x", f"Uzun tercih metni numara {i} " + "kelime " * 40, "user", profile_id=pid, force_new=True)
    store.stage_start(pid, "S01", cid, cyid)
    r = store.stage_complete(pid, "S01", [{"path": out_file(store, pid, cid, "b.md")}], "brief", cid, cyid)
    card = store.memory_card(pid, budget=200)
    assert any("Kampanya" in c_ for c_ in card["critical"])
    assert card["omitted_sections"]


def test_context_package_budget_and_usage(store):
    a = make_active_profile(store)
    pid = a["profile"]["id"]
    c = store.campaign_create(pid, a["product"]["id"], "K")
    for i in range(12):
        it = store.memory_add("preference", "x", f"Tercih {i} " + "uzun " * 60, "user", profile_id=pid, force_new=True)["created"]
    pkg = store.memory_context(pid, "S03", c["campaign"]["id"], budget=300)
    assert pkg["tokens"] <= 300 and pkg["omitted"]
    assert store.q1("SELECT COUNT(*) AS n FROM memory_usage WHERE profile_id=? AND via='context'", (pid,))["n"] >= 1


def test_lifecycle_decay_and_archive(store, clock):
    a = make_active_profile(store)
    pid = a["profile"]["id"]
    it = store.memory_add("semantic", "x", "Eski bilgi", "user", profile_id=pid, force_new=True)["created"]
    clock.advance(days=400)
    r = store.memory_lifecycle_tick(pid)
    assert it["id"] in r["due_revalidation"]
    # arşiv: son 3 turda kullanılmayan aktif öğe
    it2 = store.memory_add("semantic", "x", "Kullanılmayan bilgi", "user", profile_id=pid, force_new=True)["created"]
    c = store.campaign_create(pid, a["product"]["id"], "K")
    for n in (2, 3, 4):
        clock.advance(days=20)
        store.ex("INSERT INTO cycles(campaign_id, cycle, status, created_at) VALUES(?,?, 'closed', ?)", (c["campaign"]["id"], n, clock.now.strftime("%Y-%m-%dT%H:%M:%SZ")))
    r2 = store.memory_lifecycle_tick(pid, half_life_days=10000)
    assert it2["id"] in r2["archived"]


def test_consolidation_groups_and_merge(store):
    pid = make_active_profile(store)["profile"]["id"]
    ids = [store.memory_add("procedural", "p", t, "claude", profile_id=pid, tags=["render"], force_new=True)["created"]["id"]
           for t in ("Render önce önizleme ölçeğinde yapılır", "Render önce önizleme ölçeğinde yapılmalı", "Ses -14 LUFS")]
    g = store.memory_consolidate(pid)["groups"]
    assert g and {x["id"] for x in g[0]} >= {ids[0], ids[1]}
    m = store.memory_merge(ids[0], [ids[1]], profile_id=pid)
    assert store.q1("SELECT status FROM memory_items WHERE id=?", (ids[1],))["status"] == "superseded"
    assert m["id"] == ids[0]


def test_journal_fold_and_summary(store, clock):
    pid = make_active_profile(store)["profile"]["id"]
    store.journal_log("Eski not", profile_id=pid)
    clock.advance(days=120)
    r = store.journal_fold(pid)
    assert r["folded"] >= 1
    s = store.journal_summary(pid, days=365)
    assert s["rollups"]


def test_system_memory_null_profile(store):
    store.memory_add("procedural", "render_time", "Final render 15 sn ~ ölçüldü (sistem)", "system", force_new=True)
    assert store.memory_search("render", profile_id=None)["results"]
    store.export_markdown(None)
