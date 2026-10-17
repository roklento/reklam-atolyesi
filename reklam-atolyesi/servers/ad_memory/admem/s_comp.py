"""Rekabet, strateji ve ortak kreatif sözlüğü (spec 4.5–4.7, 6.16)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import competitive as CP
from .util import AdMemoryError, canonical_json, jdump, jload, now_iso, parse_iso, sha256_text, utcnow

SERVER_DIR = Path(__file__).resolve().parents[1]
CREATIVE_TEST_TOOL_MAX = 5   # Meta kreatif test aracı: 2–5 test reklamı (6.3; hesapta doğrulanır)


@lru_cache(maxsize=1)
def _taxonomy_file() -> dict:
    return json.loads((SERVER_DIR / "taxonomy.json").read_text(encoding="utf-8"))


class CompMixin:
    def _taxonomy(self) -> dict:
        return _taxonomy_file()

    # --- sözlük -----------------------------------------------------------------
    def taxonomy_get(self, profile_id: int | None = None) -> dict:
        t = self._taxonomy()
        out = {"taxonomy_version": t["taxonomy_version"], "fixed_axes": t["fixed_axes"], "profile_axes": t["profile_axes"],
               "diversity_axes": t["diversity_axes"], "diversity_distinct_axis": t.get("diversity_distinct_axis"),
               "diversity_min_axes": t.get("diversity_min_axes", 2), "distance": t["distance"]}
        if profile_id is not None:
            self._profile(profile_id, allow_archived=True)
            out["profile_values"] = self.qa("SELECT axis, code, label, status FROM taxonomy_values WHERE profile_id=? ORDER BY axis, code", (profile_id,))
        return out

    def taxonomy_value_add(self, profile_id: int, axis: str, code: str, label: str, status: str = "proposed",
                           user_said: str | None = None) -> dict:
        self._profile(profile_id)
        t = self._taxonomy()
        if axis not in t["profile_axes"]:
            raise AdMemoryError(f"profil ekseni değil: {axis} (sabit eksenlere değer eklemek plugin güncellemesi ister; öneri sistem hafızasına yazılır)")
        if status not in ("proposed", "active", "retired"):
            raise AdMemoryError("status: proposed | active | retired")
        if status == "active" and not (user_said and user_said.strip()):
            raise AdMemoryError("profil değeri kullanıcıyla doğar; aktifleştirme kullanıcının ifadesini ister (4.7)")
        code = code.strip()
        if code.startswith("other:"):
            code = code[len("other:"):].strip()
        with self.tx():
            self.ex("""INSERT INTO taxonomy_values(profile_id,axis,code,label,status,taxonomy_version,created_at) VALUES(?,?,?,?,?,?,?)
                       ON CONFLICT(profile_id,axis,code) DO UPDATE SET label=excluded.label, status=excluded.status""",
                    (profile_id, axis, code, label, status, t["taxonomy_version"], now_iso()))
        return self.q1("SELECT * FROM taxonomy_values WHERE profile_id=? AND axis=? AND code=?", (profile_id, axis, code))

    # --- rakip seti ---------------------------------------------------------------
    def competitor_upsert(self, profile_id: int, name: str, kind: str, added_by: str = "user", meta_page_id: str | None = None,
                          ig_handle: str | None = None, website: str | None = None, notes: str | None = None,
                          status: str = "active") -> dict:
        self._profile(profile_id)
        if kind not in ("direct", "indirect", "aspirational"):
            raise AdMemoryError("tür: direct | indirect | aspirational")
        if added_by not in ("user", "discovered", "brand_doc"):
            raise AdMemoryError("added_by: user | discovered | brand_doc")
        if status not in ("active", "ignored"):
            raise AdMemoryError("status: active | ignored")
        with self.tx():
            self.ex("""INSERT INTO competitors(profile_id,name,kind,meta_page_id,ig_handle,website,notes,status,added_by,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(profile_id,name) DO UPDATE SET kind=excluded.kind, meta_page_id=COALESCE(excluded.meta_page_id, competitors.meta_page_id),
                         ig_handle=COALESCE(excluded.ig_handle, competitors.ig_handle), website=COALESCE(excluded.website, competitors.website),
                         notes=COALESCE(excluded.notes, competitors.notes), status=excluded.status, updated_at=excluded.updated_at""",
                    (profile_id, name.strip(), kind, meta_page_id, ig_handle, website, notes, status, added_by, now_iso(), now_iso()))
        return self.q1("SELECT * FROM competitors WHERE profile_id=? AND name=?", (profile_id, name.strip()))

    def competitor_list(self, profile_id: int, include_ignored: bool = False) -> dict:
        self._profile(profile_id, allow_archived=True)
        sql = "SELECT * FROM competitors WHERE profile_id=?" + ("" if include_ignored else " AND status='active'")
        comps = self.qa(sql + " ORDER BY kind, name", (profile_id,))
        last = self.q1("SELECT * FROM competitor_snapshots WHERE profile_id=? ORDER BY fetched_at DESC, id DESC LIMIT 1", (profile_id,))
        fresh = None
        if last:
            age = (utcnow() - parse_iso(last["fetched_at"])).days
            fresh = {"snapshot_id": last["id"], "age_days": age, "reusable": age < 14,
                     "rule": "14 günden yeni görüntü yeniden kullanılır, yalnızca fark çekilir (4.5)"}
        return {"competitors": comps, "last_snapshot": fresh,
                "set_size_note": "3–8 rakip yeter; set ilk S01b'de kullanıcıyla kurulur, sonra yalnızca değişiklik sorulur"}

    def _competitor(self, profile_id: int, competitor_id: int) -> dict:
        c = self.q1("SELECT * FROM competitors WHERE id=?", (int(competitor_id),))
        if not c or c["profile_id"] != int(profile_id):
            raise AdMemoryError(f"rakip {competitor_id} bu profile ait değil")
        return c

    # --- görüntü (snapshot) -------------------------------------------------------
    def competitor_snapshot_save(self, profile_id: int, mode: str, ads: list[dict], n_calls: int, scope: dict,
                                 campaign_id: int | None = None, cycle_id: int | None = None, source: str = "ad_library",
                                 coverage: dict | None = None) -> dict:
        """Görüntü tek işlemde: reklam UPSERT'i (ilk/son görülme), varyant grupları, SHA-256 ve kapsam."""
        self._profile(profile_id)
        if mode not in ("full", "diff"):
            raise AdMemoryError("mode: full | diff")
        if source not in ("ad_library", "manual", "synthetic"):
            raise AdMemoryError("source: ad_library | manual | synthetic")
        if campaign_id is not None:
            self._campaign(profile_id, campaign_id)
        if cycle_id is not None:
            self._cycle(profile_id, cycle_id, campaign_id)
        budget = int((scope or {}).get("query_budget", 20))
        if n_calls > budget:
            raise AdMemoryError(f"sorgu bütçesi aşıldı ({n_calls} > {budget}); görüntü kaydedilmedi (9.2, 13.6)")
        bad = [str(a.get("library_id") or f"#{i}") for i, a in enumerate(ads or [])
               if not isinstance(a, dict) or not a.get("library_id") or isinstance(a.get("competitor_id"), bool)
               or not isinstance(a.get("competitor_id"), int) and not str(a.get("competitor_id") or "").isdigit()]
        if bad:
            raise AdMemoryError("her reklamda library_id ve sayısal competitor_id gerekli (competitor_upsert/competitor_list'ten; rakip adı değil). "
                                f"Eksik/hatalı: {', '.join(bad[:10])}" + (f" (+{len(bad) - 10})" if len(bad) > 10 else "") + "; görüntü kaydedilmedi")
        payload = canonical_json({"mode": mode, "scope": scope, "ads": sorted(ads, key=lambda a: str(a.get("library_id")))})
        sha = sha256_text(payload)
        now = now_iso()
        today = now[:10]
        flagged = 0
        with self.tx():
            prev_snap = self.q1("SELECT id FROM competitor_snapshots WHERE profile_id=? ORDER BY fetched_at DESC, id DESC LIMIT 1", (profile_id,))
            prev_active = [r["library_id"] for r in self.qa("SELECT library_id FROM competitor_ads WHERE profile_id=? AND is_active=1", (profile_id,))]
            sid = self.ex("""INSERT INTO competitor_snapshots(profile_id,campaign_id,cycle_id,mode,scope_json,fetched_at,n_calls,n_ads,coverage_json,source,sha256)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                          (profile_id, campaign_id, cycle_id, mode, jdump(scope), now, int(n_calls), len(ads), None, source, sha)).lastrowid
            seen_competitors = set()
            for a in ads:
                comp = self._competitor(profile_id, a["competitor_id"])
                seen_competitors.add(comp["id"])
                if not a.get("library_id"):
                    raise AdMemoryError("her rakip reklamı library_id taşımalı (kanıt bağlantısı)")
                vg = a.get("variant_group") or CP.variant_key({**a, "competitor_id": comp["id"]})
                instr = 1 if CP.detect_instruction((a.get("body_text") or "") + " " + (a.get("title") or "")) else 0
                flagged += instr
                feats = self._validate_features(profile_id, a.get("features")) if a.get("features") else None
                self.ex("""INSERT INTO competitor_ads(profile_id,competitor_id,library_id,variant_group,start_date,stop_date,first_seen_at,last_seen_at,
                             is_active,platforms_json,media_type,body_text,title,cta,link_url,snapshot_url,features_json,taxonomy_version,source,raw_json,
                             instruction_flag,last_snapshot_id)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(competitor_id, library_id) DO UPDATE SET variant_group=excluded.variant_group,
                             stop_date=COALESCE(excluded.stop_date, competitor_ads.stop_date), last_seen_at=excluded.last_seen_at,
                             is_active=excluded.is_active, platforms_json=excluded.platforms_json, body_text=excluded.body_text,
                             title=excluded.title, cta=excluded.cta, link_url=excluded.link_url, snapshot_url=excluded.snapshot_url,
                             features_json=COALESCE(excluded.features_json, competitor_ads.features_json),
                             taxonomy_version=COALESCE(excluded.taxonomy_version, competitor_ads.taxonomy_version),
                             raw_json=excluded.raw_json, instruction_flag=excluded.instruction_flag, last_snapshot_id=excluded.last_snapshot_id""",
                        (profile_id, comp["id"], str(a["library_id"]), vg, a.get("start_date"), a.get("stop_date"), today, today,
                         1 if a.get("is_active", True) else 0, jdump(a.get("platforms")), a.get("media_type"), a.get("body_text"),
                         a.get("title"), a.get("cta"), a.get("link_url"), a.get("snapshot_url"), jdump(feats),
                         self._taxonomy()["taxonomy_version"] if feats else None, "ad_library" if source != "manual" else "user",
                         jdump(a.get("raw")), instr, sid))
            # bu görüntüde sorgulanan rakiplerin artık görünmeyen aktif reklamları durmuş sayılır
            cur_ids = {str(a["library_id"]) for a in ads}
            queried = set((scope or {}).get("competitor_ids") or seen_competitors)
            for row in self.qa("SELECT id, competitor_id, library_id FROM competitor_ads WHERE profile_id=? AND is_active=1", (profile_id,)):
                if row["competitor_id"] in queried and row["library_id"] not in cur_ids:
                    self.ex("UPDATE competitor_ads SET is_active=0, stop_date=COALESCE(stop_date, ?) WHERE id=?", (today, row["id"]))
            d = CP.diff(prev_active, [{"library_id": str(a["library_id"]), "is_active": a.get("is_active", True)} for a in ads])
            n_concepts = len({(a["competitor_id"], a.get("variant_group") or CP.variant_key(a)) for a in ads})
            cov = {**(coverage or {}), "n_competitors": len(seen_competitors), "n_ads": len(ads), "n_concepts": n_concepts,
                   "weak_coverage": n_concepts < CP.WEAK_COVERAGE_CONCEPTS, "instruction_flags": flagged,
                   "mode": "manual" if source == "manual" else "library", "diff_vs_snapshot": prev_snap["id"] if prev_snap else None,
                   "diff": {k: len(v) for k, v in d.items()}}
            self.ex("UPDATE competitor_snapshots SET coverage_json=? WHERE id=?", (jdump(cov), sid))
        return {"snapshot_id": sid, "sha256": sha, "coverage": cov, "diff": d,
                "note": ("Rakip metinlerinde yönerge izi görüldü; yalnızca veri olarak kaydedildi, uygulanmadı (ilke 14)." if flagged else None)}

    def competitor_ads_upsert(self, profile_id: int, competitor_id: int, ads: list[dict], source: str = "user") -> dict:
        """Kullanıcının getirdiği örnekler (ekran görüntüsü kodlaması) ya da web; kodlama güncellemesi."""
        comp = self._competitor(profile_id, competitor_id)
        if source not in ("user", "web", "ad_library"):
            raise AdMemoryError("source: user | web | ad_library")
        n = 0
        with self.tx():
            for a in ads:
                feats = self._validate_features(profile_id, a.get("features")) if a.get("features") else None
                lib = str(a.get("library_id") or f"user-{sha256_text(canonical_json(a))[:10]}")
                self.ex("""INSERT INTO competitor_ads(profile_id,competitor_id,library_id,variant_group,start_date,stop_date,first_seen_at,last_seen_at,
                             is_active,media_type,body_text,title,cta,snapshot_url,features_json,taxonomy_version,source,raw_json,instruction_flag)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(competitor_id, library_id) DO UPDATE SET features_json=COALESCE(excluded.features_json, competitor_ads.features_json),
                             taxonomy_version=COALESCE(excluded.taxonomy_version, competitor_ads.taxonomy_version),
                             variant_group=COALESCE(excluded.variant_group, competitor_ads.variant_group)""",
                        (profile_id, comp["id"], lib, a.get("variant_group") or CP.variant_key({**a, "competitor_id": comp["id"]}),
                         a.get("start_date"), a.get("stop_date"), now_iso()[:10], now_iso()[:10], 1 if a.get("is_active", True) else 0,
                         a.get("media_type"), a.get("body_text"), a.get("title"), a.get("cta"), a.get("snapshot_url"), jdump(feats),
                         self._taxonomy()["taxonomy_version"] if feats else None, source, jdump(a.get("raw")),
                         1 if CP.detect_instruction(a.get("body_text")) else 0))
                n += 1
        return {"upserted": n}

    def competitor_offer_upsert(self, profile_id: int, competitor_id: int, url: str, product_ref: str | None = None,
                                price: float | None = None, currency: str | None = None, offer: dict | None = None,
                                claims: list | None = None, snapshot_id: int | None = None) -> dict:
        comp = self._competitor(profile_id, competitor_id)
        with self.tx():
            oid = self.ex("""INSERT INTO competitor_offers(profile_id,competitor_id,snapshot_id,product_ref,price,currency,offer_json,claims_json,url,fetched_at)
                             VALUES(?,?,?,?,?,?,?,?,?,?)""",
                          (profile_id, comp["id"], snapshot_id, product_ref, price, currency, jdump(offer), jdump(claims), url, now_iso())).lastrowid
        return self.q1("SELECT * FROM competitor_offers WHERE id=?", (oid,))

    def competitor_diff(self, profile_id: int, snapshot_id: int | None = None) -> dict:
        self._profile(profile_id, allow_archived=True)
        snap = self.q1("SELECT * FROM competitor_snapshots WHERE id=? AND profile_id=?", (snapshot_id, profile_id)) if snapshot_id else \
            self.q1("SELECT * FROM competitor_snapshots WHERE profile_id=? ORDER BY fetched_at DESC, id DESC LIMIT 1", (profile_id,))
        if not snap:
            return {"snapshot": None, "note": "henüz rakip görüntüsü yok"}
        ads = self.qa("""SELECT a.*, c.name AS competitor, c.kind FROM competitor_ads a JOIN competitors c ON c.id=a.competitor_id
                         WHERE a.profile_id=? ORDER BY c.name, a.start_date""", (profile_id,))
        new = [a for a in ads if a["last_snapshot_id"] == snap["id"] and a["first_seen_at"] == snap["fetched_at"][:10]]
        stopped = [a for a in ads if not a["is_active"] and a["stop_date"] == snap["fetched_at"][:10]]
        cont = [a for a in ads if a["is_active"] and a not in new]
        for a in ads:
            a["observed_run_days"] = CP.observed_run_days(a, snap["fetched_at"])
        return {"snapshot": snap, "new": new, "continuing": cont, "stopped": stopped,
                "label": "proxy", "note": "Gözlenen yayın süresi ve durdurma vekil sinyaldir; performans kanıtı değildir (4.5)."}

    def competitive_map(self, profile_id: int, axes: list[str] | None = None, product_id: int | None = None) -> dict:
        self._profile(profile_id, allow_archived=True)
        t = self._taxonomy()
        axes = axes or ["video_type", "first_frame", "proof", "offer", "price_shown", "media", "angle", "moment", "emotion"]
        ads = self.qa("SELECT * FROM competitor_ads WHERE profile_id=?", (profile_id,))
        for a in ads:
            a["features"] = a["features_json"] or {}
        kinds = {c["id"]: c["kind"] for c in self.qa("SELECT id, kind FROM competitors WHERE profile_id=? AND status='active'", (profile_id,))}
        ads = [a for a in ads if a["competitor_id"] in kinds]
        groups = CP.group_concepts(ads)
        cmap = CP.build_map(list(groups.values()), axes, kinds)
        supports: dict[str, set[str]] = {}
        if product_id is not None:
            prod = self._product(profile_id, product_id)
            claims = prod["provable_claims_json"] or []
            proofs = {c.get("proof_type") for c in claims if isinstance(c, dict) and c.get("proof_type") and c.get("documented", True)}
            supports["proof"] = {p for p in proofs if p in t["fixed_axes"]["proof"]["values"]}
            occ = prod["occasions_json"] or []
            supports["moment"] = {o.get("code") if isinstance(o, dict) else str(o) for o in occ}
        last = self.q1("SELECT id, sha256, fetched_at FROM competitor_snapshots WHERE profile_id=? ORDER BY fetched_at DESC, id DESC LIMIT 1", (profile_id,))
        ref = {"snapshot_id": last["id"], "snapshot_sha256": last["sha256"]} if last else {}
        insights = CP.derive_insights(cmap, len(kinds), supports, ref)
        n_concepts = len(groups)
        return {"map": cmap, "n_competitors": len(kinds), "n_concepts": n_concepts,
                "weak_coverage": n_concepts < CP.WEAK_COVERAGE_CONCEPTS, "candidate_insights": insights,
                "concepts": [{k: v for k, v in g.items() if k != "ads"} | {"library_ids": [a["library_id"] for a in g["ads"]]} for g in groups.values()],
                "snapshot": ref}

    def competitive_insights_save(self, profile_id: int, insights: list[dict], snapshot_id: int | None = None,
                                  campaign_id: int | None = None, cycle_id: int | None = None) -> dict:
        self._profile(profile_id)
        if campaign_id is not None:
            self._campaign(profile_id, campaign_id)
        if cycle_id is not None:
            self._cycle(profile_id, cycle_id, campaign_id)
        weak = False
        if snapshot_id:
            snap = self.q1("SELECT * FROM competitor_snapshots WHERE id=? AND profile_id=?", (snapshot_id, profile_id))
            if not snap:
                raise AdMemoryError("görüntü bu profile ait değil")
            weak = bool((snap["coverage_json"] or {}).get("weak_coverage"))
        provable = set()
        if campaign_id is not None:
            c = self._campaign(profile_id, campaign_id)
            if c["product_id"]:
                prod = self._product(profile_id, c["product_id"])
                for cl in prod["provable_claims_json"] or []:
                    provable.add((cl.get("code") or cl.get("text")) if isinstance(cl, dict) else str(cl))
        ids = []
        with self.tx():
            for ins in insights:
                kind, label = ins.get("kind"), ins.get("label")
                if kind not in ("norm", "proven_angle", "gap", "offer", "timing", "risk", "differentiator"):
                    raise AdMemoryError(f"bulgu türü geçersiz: {kind}")
                if label not in ("observation", "proxy", "user"):
                    raise AdMemoryError("etiket: observation | proxy | user")
                ev = dict(ins.get("evidence") or {})
                if label == "proxy" and not (ev.get("library_ids") or ev.get("snapshot_id")):
                    raise AdMemoryError("proxy bulgu kanıt bağlantısı (library_id/tarih ya da görüntü) taşır (4.5 kontroller)")
                if kind == "proven_angle" and label != "proxy":
                    raise AdMemoryError("kanıtlanmış açı her zaman 'proxy' etiketlidir")
                if kind == "differentiator":
                    ref = ev.get("claim_ref")
                    if not ref or (provable and ref not in provable):
                        raise AdMemoryError("ayrıştırıcı yalnızca ürünün kanıtlanabilir iddialarından (provable_claims_json) gelir")
                stmt = ins["statement"] + (" [zayıf kapsam]" if weak and "[zayıf kapsam]" not in ins["statement"] else "")
                ids.append(self.ex("""INSERT INTO competitive_insights(profile_id,campaign_id,cycle_id,snapshot_id,kind,statement,axis,label,evidence_json,created_at)
                                      VALUES(?,?,?,?,?,?,?,?,?,?)""",
                                   (profile_id, campaign_id, cycle_id, snapshot_id, kind, stmt, ins.get("axis"), label, jdump(ev), now_iso())).lastrowid)
        return {"saved": len(ids), "ids": ids, "weak_coverage": weak}

    def competitive_insights_get(self, profile_id: int, campaign_id: int | None = None, cycle_id: int | None = None,
                                 snapshot_id: int | None = None) -> dict:
        self._profile(profile_id, allow_archived=True)
        sql = "SELECT * FROM competitive_insights WHERE profile_id=?"
        args: list[Any] = [profile_id]
        for col, v in (("campaign_id", campaign_id), ("cycle_id", cycle_id), ("snapshot_id", snapshot_id)):
            if v is not None:
                sql += f" AND {col}=?"
                args.append(v)
        return {"insights": self.qa(sql + " ORDER BY id DESC LIMIT 200", tuple(args))}

    def concept_distance_check(self, profile_id: int, concept_id: int, own_texts: list[str] | None = None,
                               threshold: float | None = None) -> dict:
        k = self.q1("SELECT * FROM concepts WHERE id=?", (int(concept_id),))
        if not k:
            raise AdMemoryError("konsept yok")
        self._campaign(profile_id, k["campaign_id"])
        src_ids = k["source_competitor_ad_ids_json"] or []
        if not src_ids:
            return {"passed": True, "note": "rakipten türemeyen konsept; uzaklık kuralı uygulanmaz"}
        t = self._taxonomy()["distance"]
        src = [self.q1("SELECT * FROM competitor_ads WHERE id=? AND profile_id=?", (int(i), profile_id)) for i in src_ids]
        src = [s for s in src if s]
        hooks = self.qa("SELECT text, vo FROM hooks WHERE concept_id=?", (k["id"],))
        texts = list(own_texts or []) + [h["text"] for h in hooks if h["text"]] + [h["vo"] for h in hooks if h["vo"]] + [k["name"]]
        results = []
        for s in src:
            results.append({"library_id": s["library_id"],
                            **CP.distance(k["features_json"] or {}, s["features_json"] or {}, texts,
                                          [s["body_text"] or "", s["title"] or ""], t["min_axes_besides_angle"],
                                          threshold if threshold is not None else t["max_4gram_overlap"])})
        passed = all(r["passed"] for r in results)
        out = {"passed": passed, "per_source": results, "checked_at": now_iso()}
        with self.tx():
            self.ex("UPDATE concepts SET distance_check_json=? WHERE id=?", (jdump(out), k["id"]))
        return out

    # --- strateji (4.6) -----------------------------------------------------------
    def strategy_save(self, profile_id: int, campaign_id: int, cycle_id: int, strategy: dict,
                      competitor_snapshot_id: int | None = None, document_path: str | None = None) -> dict:
        c = self._campaign(profile_id, campaign_id)
        cy = self._cycle(profile_id, cycle_id, campaign_id)
        if c["stage"] != "S02":
            raise AdMemoryError("strateji S02'de kaydedilir")
        no_ctx = bool(strategy.get("no_competitor_context"))
        port = strategy.get("portfolio") or {}
        bp = jload(cy["budget_plan_json"], {}) or {}
        cap = bp.get("allowed_test_ads")
        total = sum(int(v) for v in port.values()) if port else 0
        if not no_ctx:
            bad = set(port) - {"proven", "gap", "counter", "free"}
            if bad:
                raise AdMemoryError(f"portföy rolleri: proven · gap · counter · free (geçersiz: {', '.join(bad)})")
        elif port and any(r in port for r in ("proven", "gap", "counter")):
            raise AdMemoryError("rakip bağlamı yokken portföy rolleri kullanılmaz; konseptler çeşitlilik ilkesiyle dağıtılır (4.6)")
        if cap is not None and total > int(cap):
            raise AdMemoryError(f"portföy {total} reklam > izin verilen test reklamı sayısı {cap} (6.3)")
        tool_cap = int(bp.get("creative_test_tool_max", CREATIVE_TEST_TOOL_MAX))
        if (cy["cycle"] > 1 or bp.get("structure") == "creative_test") and total > tool_cap:
            raise AdMemoryError(f"portföy {total} > kreatif test aracının reklam sınırı {tool_cap}")
        if not strategy.get("positioning") and not no_ctx:
            raise AdMemoryError("konumlandırma (seçilen tür ve tek cümle) yazılmalı")
        if no_ctx and "rakip bağlamı yok" not in json.dumps(strategy, ensure_ascii=False):
            strategy = {**strategy, "label": "rakip bağlamı yok"}
        prim = self.q1("SELECT * FROM hypotheses WHERE cycle_id=? AND is_primary=1", (cy["id"],))
        if prim and not strategy.get("validation_pair_first", True):
            raise AdMemoryError("birincil doğrulama hipotezinin karşılaştırma çifti portföyde önce yer alır (4.6)")
        if competitor_snapshot_id is not None:
            snap = self.q1("SELECT * FROM competitor_snapshots WHERE id=? AND profile_id=?", (competitor_snapshot_id, profile_id))
            if not snap:
                raise AdMemoryError("rakip görüntüsü bu profile ait değil")
            strategy = {**strategy, "competitor_snapshot": {"id": snap["id"], "sha256": snap["sha256"]}}
        if document_path:
            dp = Path(document_path)
            if not dp.is_absolute():
                dp = self.data_dir / dp
            if not dp.exists():
                raise AdMemoryError(f"strateji belgesi yok: {dp}")
            from .util import sha256_file
            strategy = {**strategy, "document": {"path": str(dp), "sha256": sha256_file(dp)}}
        with self.tx():
            self.ex("UPDATE cycles SET strategy_json=?, competitor_snapshot_id=COALESCE(?, competitor_snapshot_id) WHERE id=?",
                    (jdump({**strategy, "saved_at": now_iso()}), competitor_snapshot_id, cy["id"]))
        return {"cycle_id": cy["id"], "strategy": self.q1("SELECT strategy_json FROM cycles WHERE id=?", (cy["id"],))["strategy_json"]}

    def strategy_get(self, profile_id: int, campaign_id: int, cycle_id: int | None = None) -> dict:
        c = self._campaign(profile_id, campaign_id)
        cy = self._cycle(profile_id, cycle_id, campaign_id) if cycle_id else self._current_cycle(c)
        rejected = [d for d in self.qa("SELECT * FROM decisions WHERE campaign_id=? AND stage='S02' ORDER BY id", (c["id"],))
                    if (d["decision"] or "").startswith("positioning:rejected")]
        return {"cycle_id": cy["id"], "strategy": cy["strategy_json"], "competitor_snapshot_id": cy["competitor_snapshot_id"],
                "budget_plan": cy["budget_plan_json"], "risk_limits": cy["risk_limits_json"], "rejected_positionings": rejected}
