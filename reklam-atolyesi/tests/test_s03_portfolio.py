"""S03 test portföyü (1.4.5): alıcı ekseni, keşifte konsept başına tek test hook'u, farklı alıcı ve çeşitlilik eksenleri kapıda."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from admem import db as DB
from admem.store import Store
from admem.util import AdMemoryError
from conftest import ROOT, out_file
from test_store_stage import advance_to, new_campaign


def at_s03(s):
    pid, cid, cyid = new_campaign(s)
    advance_to(s, pid, cid, cyid, "S03")  # S02'de allowed_test_ads = 3
    for axis, code in (("buyer", "alici-a"), ("buyer", "alici-b"), ("buyer", "alici-c"), ("emotion", "duygu-a"),
                       ("emotion", "duygu-b"), ("moment", "an-a"), ("moment", "an-b")):
        s.taxonomy_value_add(pid, axis, code, f"Örnek {code}", status="active", user_said="evet")
    return pid, cid, cyid


MSG = {"stage": "tofu", "stage_basis": "assumption", "belief": "bu ürün hediye için uygun", "focus": "need",
       "evidence": [{"kind": "none"}], "expected_action": "profile bakmak"}


def concept(s, pid, cid, cyid, code, features, hooks=(("h1", "product", False),), hypothesis_id=None, message=MSG):
    k = s.concept_upsert(pid, cid, cyid, code, f"Konsept {code}", "general", decision="accepted", user_said=f"{code} olsun",
                         features=features, hypothesis_id=hypothesis_id, message=message)
    if hypothesis_id is None:
        s.hypothesis_add(pid, f"{code} konsepti hook oranında öndedir", "hook_rate", cid, cyid, concept_id=k["id"])
    for hcode, frame, reserve in hooks:
        s.hook_upsert(pid, k["id"], hcode, frame, f"{frame} açılışı", f"{hcode} hareketi", f"{hcode} sesi", "Örnek metin",
                      decision="accepted", user_said="bu hook", reserve=reserve)
    return k


def gate(s, pid, cid, cyid):
    s.stage_start(pid, "S03", cid, cyid)
    r = s.stage_complete(pid, "S03", [{"path": out_file(s, pid, cid, "ozet.md")}], "özet", cid, cyid)
    return lambda: s.gate_approve(pid, r["stage_run"]["id"], r["stage_run"]["output_version"], "onaylıyorum", cycle_id=cyid)


def test_buyer_axis_in_taxonomy_and_product(store):
    pid, cid, cyid = at_s03(store)
    t = store.taxonomy_get(pid)
    assert "buyer" in t["profile_axes"] and t["diversity_distinct_axis"] == "buyer" and t["diversity_min_axes"] == 2
    assert {"axis": "buyer", "code": "alici-a", "label": "Örnek alici-a", "status": "active"} in t["profile_values"]
    prod = store.q1("SELECT product_id FROM campaigns WHERE id=?", (cid,))["product_id"]
    p = store.product_upsert(pid, "Ürün A", prod, buyers_json=[{"code": "alici-b", "label": "Örnek alıcı B"}])
    assert p["buyers_json"] == [{"code": "alici-b", "label": "Örnek alıcı B"}]
    ctx = store.memory_context(pid, "S03", cid, budget=4000)
    assert "alici-b" in str(ctx)  # ürün özeti alıcıları taşır
    with pytest.raises(AdMemoryError):  # profilde tanımlı olmayan alıcı yazılamaz
        store.concept_upsert(pid, cid, cyid, "X", "X", "general", features={"buyer": "tanimsiz"})


def test_gate_passes_distinct_buyers_and_two_axes(store):
    pid, cid, cyid = at_s03(store)
    concept(store, pid, cid, cyid, "A", {"buyer": "alici-a", "emotion": "duygu-a", "moment": "an-a"}, (("h1", "product", False),))
    concept(store, pid, cid, cyid, "B", {"buyer": "alici-b", "emotion": "duygu-b", "moment": "an-a"}, (("h1", "person", False),))
    r = store.concept_diversity_check(pid, cid, cyid)
    assert r["passed"], r["issues"]
    pair = r["pairs"][0]
    assert pair["concepts"] == ["A", "B"] and set(pair["differing_axes"]) == {"emotion", "first_frame"}  # açılış karesi hook'tan
    gate(store, pid, cid, cyid)()
    assert store.q1("SELECT stage FROM campaigns WHERE id=?", (cid,))["stage"] == "S04"


def test_one_test_hook_per_exploration_concept(store):
    pid, cid, cyid = at_s03(store)
    concept(store, pid, cid, cyid, "A", {"buyer": "alici-a", "emotion": "duygu-a", "moment": "an-a"},
            (("h1", "product", False), ("h2", "person", False)))
    concept(store, pid, cid, cyid, "B", {"buyer": "alici-b", "emotion": "duygu-b", "moment": "an-b", "first_frame": "context"},
            (("h1", "context", False),))
    approve = gate(store, pid, cid, cyid)
    with pytest.raises(AdMemoryError, match="tek test açılışı"):
        approve()
    k = store.q1("SELECT id FROM concepts WHERE cycle_id=? AND code='A'", (cyid,))
    store.hook_upsert(pid, k["id"], "h2", "person", "person açılışı", "h2 hareketi", "h2 sesi", "Örnek metin",
                      decision="accepted", user_said="h2 yedek kalsın", reserve=True)
    approve()  # yedek hook çekilir ama teste girmez
    rows = store.qa("SELECT h.code, h.reserve FROM hooks h JOIN concepts k ON k.id=h.concept_id WHERE k.cycle_id=? AND k.code='A'", (cyid,))
    assert {(r["code"], r["reserve"]) for r in rows} == {("h1", 0), ("h2", 1)}


def test_same_buyer_or_too_similar_blocks_gate(store):
    pid, cid, cyid = at_s03(store)
    concept(store, pid, cid, cyid, "A", {"buyer": "alici-a", "emotion": "duygu-a", "moment": "an-a"}, (("h1", "product", False),))
    concept(store, pid, cid, cyid, "B", {"buyer": "alici-a", "emotion": "duygu-a", "moment": "unknown"}, (("h1", "person", False),))
    approve = gate(store, pid, cid, cyid)
    with pytest.raises(AdMemoryError) as e:
        approve()
    msg = str(e.value)
    assert "aynı alıcıya" in msg and "yalnızca 1 eksende" in msg  # unknown an fark sayılmaz
    store.concept_upsert(pid, cid, cyid, "B", "Konsept B", "general", decision="accepted", user_said="B olsun",
                         features={"buyer": "alici-b", "emotion": "duygu-a", "moment": "an-b"})
    approve()


def test_buyer_required_single_and_unknown_is_not_enough(store):
    pid, cid, cyid = at_s03(store)
    concept(store, pid, cid, cyid, "A", {"buyer": "unknown", "emotion": "duygu-a", "moment": "an-a"})
    concept(store, pid, cid, cyid, "B", {"buyer": ["alici-b", "alici-c"], "emotion": "duygu-b", "moment": "an-b"},
            (("h1", "person", False),))
    issues = store.concept_diversity_check(pid, cid, cyid)["issues"]
    assert any("konsept A: kime konuştuğu" in i for i in issues)
    assert any("konsept B: tek bir alıcıya" in i for i in issues)
    with pytest.raises(AdMemoryError, match="kime konuştuğu"):
        gate(store, pid, cid, cyid)()


def test_validation_pair_and_reserve_only_concepts_are_exempt(store, clock):
    pid, cid, cyid = at_s03(store)
    h = store.hypothesis_add(pid, "Kişili açılış ürünlü açılıştan öndedir", "hook_rate", cid, cyid, feature="first_frame",
                             is_primary=True, pre_registration={"arm_a": "V/h1", "arm_b": "V/h2", "metric": "hook_rate",
                                                                "direction": "a>b", "comparison_ids": []})
    concept(store, pid, cid, cyid, "V", {"emotion": "duygu-a"}, (("h1", "person", False), ("h2", "product", False)),
            hypothesis_id=h["id"])
    concept(store, pid, cid, cyid, "A", {"buyer": "alici-a", "emotion": "duygu-a", "moment": "an-a"}, (("h1", "product", False),))
    concept(store, pid, cid, cyid, "Y", {"emotion": "duygu-a"}, (("h1", "product", True),))  # tümüyle yedek: bu tur test edilmez
    r = store.concept_diversity_check(pid, cid, cyid)
    assert r["passed"], r["issues"]
    assert r["validation"] == ["V"] and r["reserve_only"] == ["Y"] and [e["code"] for e in r["exploration"]] == ["A"]
    gate(store, pid, cid, cyid)()  # 2 + 1 test reklamı = tavan 3


def test_partial_update_keeps_decision_buyer_hypothesis_and_reserve(store):
    """Ses niyeti gibi tek alanlı güncelleme kararı, alıcıyı, hipotez bağını ve yedek işaretini silmez (1.4.5)."""
    pid, cid, cyid = at_s03(store)
    k = concept(store, pid, cid, cyid, "A", {"buyer": "alici-a", "emotion": "duygu-a"},
                (("h1", "product", False), ("h2", "person", True)))
    hyp = store.q1("SELECT hypothesis_id FROM concepts WHERE id=?", (k["id"],))["hypothesis_id"]
    r = store.concept_upsert(pid, cid, cyid, "A", "Konsept A", "general", sound_intent="çekimdeki ses")
    assert (r["decision"], r["status"], r["hypothesis_id"], r["sound_intent"]) == ("accepted", "selected", hyp, "çekimdeki ses")
    assert r["features_json"] == {"buyer": "alici-a", "emotion": "duygu-a", "stage": "tofu"}  # aşama mesaj kartından (1.9.0)
    assert r["message_json"]["stage"] == "tofu"
    r = store.concept_upsert(pid, cid, cyid, "A", "Konsept A", "general", features={"moment": "an-a", "emotion": "duygu-b"})
    assert r["features_json"] == {"buyer": "alici-a", "emotion": "duygu-b", "moment": "an-a", "stage": "tofu"}  # eksen bazında birleşir
    h = store.hook_upsert(pid, k["id"], "h2", "person", "person açılışı", "yeni hareket", "h2 sesi", "Yeni metin")
    assert (h["decision"], h["reserve"]) == ("accepted", 1)
    h = store.hook_upsert(pid, k["id"], "h3", "context", "bağlam", "hareket", "ses", "Metin")  # yeni hook: varsayılan test
    assert h["reserve"] == 0 and h["decision"] is None


def test_reserve_hook_cannot_be_registered_as_test_creative(store):
    """S12'de yedek hook'tan üretilen çıktı test reklamı olarak kaydedilemez; aynı dosya yedek olarak kaydolur (1.4.5)."""
    from admem import naming
    pid, cid, cyid = at_s03(store)
    concept(store, pid, cid, cyid, "A", {"buyer": "alici-a", "emotion": "duygu-a", "moment": "an-a"},
            (("h1", "product", False), ("h2", "person", True)))

    def render(hook):
        key = naming.build_key("MRK", "K1", "A", "video", 15, hook, False, "real", 1, 1)
        f = store.campaign_dir(pid, cid) / "out" / naming.build_file_name(key, "9x16")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(hook.encode() * 16)
        return str(f)

    with pytest.raises(AdMemoryError, match="yedek seçildi"):
        store.creative_register(pid, cid, cyid, render("h2"), "test")
    assert store.creative_register(pid, cid, cyid, render("h2"), "reserve")["delivery_role"] == "reserve"
    assert store.creative_register(pid, cid, cyid, render("h1"), "test")["delivery_role"] == "test"


def test_diversity_check_is_read_only_and_profile_scoped(store):
    pid, cid, cyid = at_s03(store)
    concept(store, pid, cid, cyid, "A", {"buyer": "alici-a", "emotion": "duygu-a", "moment": "an-a"})
    before = store.q1("SELECT COUNT(*) AS n FROM decisions")["n"]
    store.concept_diversity_check(pid, cid, cyid)
    assert store.q1("SELECT COUNT(*) AS n FROM decisions")["n"] == before
    other = store.profile_create("Marka B")
    with pytest.raises(AdMemoryError):
        store.concept_diversity_check(other["id"], cid, cyid)


def test_migration_003_rebuilds_taxonomy_values_and_keeps_rows(tmp_path, monkeypatch):
    path = tmp_path / "db" / "ad-memory.sqlite"
    conn = DB.connect(path)
    first_two = sorted(DB.MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))[:2]
    monkeypatch.setattr(DB, "pending_migrations", lambda c: [f for f in first_two if int(f.name[:3]) > DB.current_version(c)])
    DB.migrate(conn)
    monkeypatch.undo()
    assert DB.current_version(conn) == 2
    now = "2026-01-01T00:00:00Z"
    conn.execute("INSERT INTO brands(id, name, created_at) VALUES(1, 'Marka A', ?)", (now,))
    conn.execute("INSERT INTO profiles(id, slug, name, brand_id, created_at) VALUES(1, 'marka-a', 'Marka A', 1, ?)", (now,))
    conn.execute("INSERT INTO products(id, brand_id, name, created_at) VALUES(1, 1, 'Ürün A', ?)", (now,))
    conn.execute("""INSERT INTO taxonomy_values(id, profile_id, axis, code, label, status, taxonomy_version, created_at)
                    VALUES(7, 1, 'moment', 'an-a', 'Örnek an', 'active', '1.4.0', ?)""", (now,))
    with pytest.raises(sqlite3.IntegrityError):  # eski kısıt alıcı eksenini tanımıyor
        conn.execute("""INSERT INTO taxonomy_values(profile_id, axis, code, label, status, taxonomy_version, created_at)
                        VALUES(1, 'buyer', 'alici-a', 'Örnek alıcı', 'active', '1.4.0', ?)""", (now,))
    conn.close()
    s = Store(path, tmp_path)  # açılış bekleyen migration'ı yedek alarak uygular
    try:
        assert DB.current_version(s.conn) == DB.SCHEMA_VERSION >= 3
        row = s.q1("SELECT * FROM taxonomy_values WHERE id=7")
        assert (row["axis"], row["code"], row["status"], row["taxonomy_version"]) == ("moment", "an-a", "active", "1.4.0")
        v = s.taxonomy_value_add(1, "buyer", "alici-a", "Örnek alıcı", status="active", user_said="evet")
        assert v["axis"] == "buyer" and v["taxonomy_version"] == s.taxonomy_get()["taxonomy_version"]
        with pytest.raises(sqlite3.IntegrityError):  # kısıt hâlâ kapalı liste
            s.ex("""INSERT INTO taxonomy_values(profile_id, axis, code, label, status, taxonomy_version, created_at)
                    VALUES(1, 'yok', 'x', 'x', 'active', '1.5.0', ?)""", (now,))
        with pytest.raises(sqlite3.IntegrityError):  # benzersizlik korundu
            s.ex("""INSERT INTO taxonomy_values(profile_id, axis, code, label, status, taxonomy_version, created_at)
                    VALUES(1, 'moment', 'an-a', 'kopya', 'active', '1.5.0', ?)""", (now,))
        p = s.product_upsert(1, "Ürün A", 1, buyers_json=[{"code": "alici-a", "label": "Örnek alıcı"}])
        assert p["buyers_json"] == [{"code": "alici-a", "label": "Örnek alıcı"}]
        assert list((tmp_path / "backups").glob("*003*")), "migration öncesi yedek alınmalı"
        assert s.conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        s.close()


def test_skills_wired_to_buyer_and_diversity_gate():
    """Tanışma, konsept görüşmesi, sözlük, stratejist ve strateji aynı kuralı anlatır; Meta dayanağı §7'de durumuyla (1.4.5)."""
    read = lambda f: (ROOT / f).read_text(encoding="utf-8")
    onboarding = read("skills/product-onboarding/SKILL.md")
    assert "buyers_json" in onboarding and 'axis="buyer"' in onboarding and "§8a" in onboarding
    concepts = read("skills/concepts/SKILL.md")
    for k in ("concept_diversity_check", "tek test hook'u", "farklı alıcıya", "§8a", "reserve=True"):
        assert k in concepts, k
    taxonomy = read("skills/ref-creative-taxonomy/SKILL.md")
    assert "`buyer`" in taxonomy and "concept_diversity_check" in taxonomy and "yerel koruma kuralı" in taxonomy
    assert "concept_diversity_check" in read("agents/creative-strategist.md")
    assert "ayrı bir alıcıya" in read("skills/strategy/SKILL.md")
    legal = read("skills/ref-legal-tr-meta/SKILL.md").split("## 7. Meta platform kuralları", 1)[1].split("## 8.", 1)[0]
    for url in ("273363992030035", "1346816142327858", "112167992830700"):
        assert url in legal, url
    assert "Andromeda" in legal and "Teyit edilmedi" in legal
    assert "concept_diversity_check" in read("servers/ad_memory/server.py")
    sql = read("servers/ad_memory/migrations/003_buyer_axis.sql")
    assert "'buyer'" in sql and "buyers_json" in sql and ";" not in "".join(l.split("--", 1)[1] for l in sql.splitlines() if "--" in l)
