"""Hafıza (spec bölüm 8): günlük, katmanlar, arama, profil kartı, bağlam paketi, konsolidasyon, yaşam döngüsü, unutma."""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import sqlite3
from pathlib import Path
from typing import Any

from .util import (AdMemoryError, atomic_write, est_tokens, fts_body, fts_query, jdump, jload, now_iso, parse_iso,
                   tr_fold, trigram_similarity, utcnow)

SERVER_DIR = Path(__file__).resolve().parents[1]
LAYERS = ("semantic", "preference", "procedural")
MAX_ITEM_CHARS = 500
MAX_JOURNAL_CHARS = 600
HOT_DAYS = 90


def _recipes() -> dict:
    return json.loads((SERVER_DIR / "memory_recipes.json").read_text(encoding="utf-8"))


class MemoryMixin:
    # --- FTS ------------------------------------------------------------------
    def _fts_put(self, kind: str, ref_id: int, profile_id: int | None, text: str) -> None:
        self.ex("DELETE FROM memory_fts WHERE kind=? AND ref_id=?", (kind, ref_id))
        self.ex("INSERT INTO memory_fts(body, kind, ref_id, profile_id) VALUES(?,?,?,?)", (fts_body(text), kind, ref_id, profile_id))

    def _fts_del(self, kind: str, ref_id: int) -> None:
        self.ex("DELETE FROM memory_fts WHERE kind=? AND ref_id=?", (kind, ref_id))

    # --- günlük (epizodik) --------------------------------------------------------
    def _journal_insert(self, profile_id, campaign_id, type_, summary, detail, links, cost) -> int:
        jid = self.ex("""INSERT INTO journal(profile_id,campaign_id,ts,type,summary,detail_json,links_json,cost_credits)
                         VALUES(?,?,?,?,?,?,?,?)""", (profile_id, campaign_id, now_iso(), type_, summary, jdump(detail), jdump(links), cost)).lastrowid
        self._fts_put("journal", jid, profile_id, summary)
        return jid

    def journal_log(self, summary: str, profile_id: int | None = None, type: str = "note", campaign_id: int | None = None,
                    detail: dict | None = None, links: dict | None = None) -> dict:
        """Tablolardan çıkarılamayan anlatı (gerekçe, istek, düzeltme, ret nedeni) — 1–3 satır (8.3). profile_id NULL: sistem hafızası."""
        if profile_id is not None:
            self._profile(profile_id)
        if campaign_id is not None:
            self._campaign(profile_id, campaign_id)
        if not summary or len(summary) > MAX_JOURNAL_CHARS or summary.count("\n") > 3:
            raise AdMemoryError(f"günlük kaydı 1–3 satır ve en fazla {MAX_JOURNAL_CHARS} karakter")
        with self.tx():
            jid = self._journal_insert(profile_id, campaign_id, type, summary.strip(), detail, links, None)
        return self.q1("SELECT * FROM journal WHERE id=?", (jid,))

    def journal_summary(self, profile_id: int, days: int = 30, campaign_id: int | None = None) -> dict:
        """'Neler yaptık': tablolar + günlük birleşik görünüm (sunucu durum için ayrıca günlük üretmez; 8.3)."""
        p = self._profile(profile_id, allow_archived=True)
        since = (utcnow() - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        cfilter, cargs = ("", ())
        if campaign_id is not None:
            self._campaign(profile_id, campaign_id)
            cfilter, cargs = (" AND campaign_id=?", (campaign_id,))
        events = []
        for r in self.qa(f"SELECT stage, status, output_version, finished_at AS ts, campaign_id FROM stage_runs WHERE profile_id=? AND finished_at>=?{cfilter}",
                         (profile_id, since, *cargs)):
            events.append({"ts": r["ts"], "what": f"{r['stage']} {r['status']} (sürüm {r['output_version']})", "source": "stage_runs"})
        for r in self.qa(f"SELECT stage, decision, note, created_at AS ts FROM decisions WHERE profile_id=? AND created_at>=?{cfilter}",
                         (profile_id, since, *cargs)):
            events.append({"ts": r["ts"], "what": f"karar {r['stage'] or ''} {r['decision']}: {(r['note'] or '')[:120]}", "source": "decisions"})
        for r in self.qa(f"SELECT kind, status, cost_credits, updated_at AS ts FROM generations WHERE profile_id=? AND updated_at>=?{cfilter}",
                         (profile_id, since, *cargs)):
            events.append({"ts": r["ts"], "what": f"üretim {r['kind']} {r['status']} ({r['cost_credits'] or 0} kredi)", "source": "generations"})
        jsql = "SELECT ts, type, summary FROM journal WHERE profile_id=? AND ts>=? AND rolled=0" + (" AND campaign_id=?" if campaign_id else "")
        for r in self.qa(jsql, (profile_id, since, *cargs)):
            events.append({"ts": r["ts"], "what": r["summary"], "source": f"journal:{r['type']}"})
        events.sort(key=lambda e: e["ts"] or "", reverse=True)
        rollups = self.qa("SELECT period, period_start, summary FROM journal_rollups WHERE profile_id=? ORDER BY period_start DESC LIMIT 8", (profile_id,))
        return {"profile": p["name"], "days": days, "events": events[:80], "rollups": rollups,
                "open_checkpoints": self.checkpoint_get(profile_id)["open"],
                "active_rules": self.qa("SELECT id, rule, season FROM playbook_rules WHERE profile_id=? AND status='active'", (profile_id,)),
                "preferences": self.qa("SELECT id, content, observations, status FROM memory_items WHERE profile_id=? AND layer='preference' AND status IN ('active','proposed') ORDER BY observations DESC LIMIT 15", (profile_id,)),
                "pending_validation": self.qa("SELECT id, content, layer FROM memory_items WHERE profile_id=? AND (status='due_revalidation' OR conflict_json IS NOT NULL)", (profile_id,))}

    def journal_fold(self, profile_id: int | None = None) -> dict:
        """Özet katlama: 90 günden eski ham kayıtlar gün → hafta → ay özetine katlanır, ham kayıt arşive iner (8.7)."""
        cutoff = (utcnow() - dt.timedelta(days=HOT_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        if profile_id is not None:
            self._profile(profile_id, allow_archived=True)
        rows = self.qa("SELECT * FROM journal WHERE rolled=0 AND ts<? AND " + ("profile_id=?" if profile_id is not None else "profile_id IS NULL"),
                       (cutoff, profile_id) if profile_id is not None else (cutoff,))
        buckets: dict[tuple[str, str], list[str]] = {}
        for r in rows:
            d = parse_iso(r["ts"]).date()
            age = (utcnow().date() - d).days
            if age > 365:
                key = ("month", d.replace(day=1).isoformat())
            elif age > 180:
                key = ("week", (d - dt.timedelta(days=d.weekday())).isoformat())
            else:
                key = ("day", d.isoformat())
            buckets.setdefault(key, []).append(r["summary"])
        with self.tx():
            for (period, start), sums in buckets.items():
                ex = self.q1("SELECT * FROM journal_rollups WHERE profile_id IS ? AND period=? AND period_start=?", (profile_id, period, start))
                text = " · ".join(dict.fromkeys(sums))
                if ex:
                    text = (ex["summary"] + " · " + text)
                text = text[:900]
                if ex:
                    self.ex("UPDATE journal_rollups SET summary=?, created_at=? WHERE id=?", (text, now_iso(), ex["id"]))
                else:
                    self.ex("INSERT INTO journal_rollups(profile_id,period,period_start,summary,created_at) VALUES(?,?,?,?,?)",
                            (profile_id, period, start, text, now_iso()))
            for r in rows:
                self.ex("UPDATE journal SET rolled=1 WHERE id=?", (r["id"],))
        return {"folded": len(rows), "rollups": len(buckets)}

    # --- hafıza öğeleri ------------------------------------------------------------
    def _item(self, profile_id: int | None, item_id: int) -> dict:
        it = self.q1("SELECT * FROM memory_items WHERE id=?", (int(item_id),))
        if not it or it["profile_id"] != (int(profile_id) if profile_id is not None else None):
            raise AdMemoryError("hafıza öğesi bu kapsamda değil (profil yalıtımı)")
        return it

    def memory_add(self, layer: str, kind: str, content: str, source: str, profile_id: int | None = None,
                   scope: dict | None = None, tags: list[str] | None = None, confidence: float | None = None,
                   evidence_id: str | None = None, force_new: bool = False) -> dict:
        """Önce eşleştirme: aynı katman/kapsam/etiket adayları + metin aramasının en yakın 5 öğesi döner (8.3)."""
        if profile_id is not None:
            self._profile(profile_id)
        if layer not in LAYERS:
            raise AdMemoryError(f"katman: {', '.join(LAYERS)}")
        if not content or len(content) > MAX_ITEM_CHARS:
            raise AdMemoryError(f"öğe içeriği 1–{MAX_ITEM_CHARS} karakter")
        if source not in ("user", "claude", "data", "system"):
            raise AdMemoryError("kaynak: user | claude | data | system")
        if not force_new:
            cands = self._match_candidates(profile_id, layer, scope, tags, content)
            if cands:
                return {"created": None, "candidates": cands,
                        "next": "Aynı şeyi söylüyorsa memory_observe(id, kanıt); çelişiyorsa memory_update(conflict=...); gerçekten yeniyse force_new=true ile tekrar çağır. "
                                "Otomatik anlam eşleştirme garantisi yoktur; eşleştirmeyi Claude adayları okuyarak yapar."}
        status = "active" if source == "user" else "proposed"
        conf = confidence if confidence is not None else (0.9 if source == "user" else 0.5)
        ev = [{"id": evidence_id, "at": now_iso()}] if evidence_id else []
        with self.tx():
            iid = self.ex("""INSERT INTO memory_items(profile_id,layer,kind,content,scope_json,tags,confidence,evidence_json,source,status,observations,created_at,last_validated_at)
                             VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?)""",
                          (profile_id, layer, kind, content.strip(), jdump(scope), ",".join(tags) if tags else None, conf, jdump(ev), source,
                           status, now_iso(), now_iso())).lastrowid
            self._fts_put("memory", iid, profile_id, content + " " + " ".join(tags or []))
        return {"created": self.q1("SELECT * FROM memory_items WHERE id=?", (iid,)), "candidates": []}

    def _match_candidates(self, profile_id, layer, scope, tags, content) -> list[dict]:
        out: dict[int, dict] = {}
        rows = self.qa("SELECT * FROM memory_items WHERE profile_id IS ? AND layer=? AND status NOT IN ('retired','superseded')", (profile_id, layer))
        tagset = set(tags or [])
        for r in rows:
            rt = set((r["tags"] or "").split(",")) - {""}
            same_scope = (r["scope_json"] or None) == (scope or None)
            if (tagset and rt & tagset) or (same_scope and trigram_similarity(r["content"], content) >= 0.35):
                out[r["id"]] = {"id": r["id"], "content": r["content"], "status": r["status"], "observations": r["observations"], "why": "katman/kapsam/etiket"}
        for r in self._fts_hits(profile_id, content, limit=5, kinds=("memory",)):
            it = self.q1("SELECT * FROM memory_items WHERE id=?", (r["ref_id"],))
            if it and it["layer"] == layer and it["status"] not in ("retired", "superseded"):
                out.setdefault(it["id"], {"id": it["id"], "content": it["content"], "status": it["status"],
                                          "observations": it["observations"], "why": "metin araması"})
        return list(out.values())[:10]

    def memory_observe(self, item_id: int, evidence_id: str, profile_id: int | None = None, note: str | None = None) -> dict:
        """Aynı öğeye yeni bağımsız kanıt; aynı kanıt kimliği tekrar sayılmaz (8.3). Tercih 3 gözlemle aktifleşir (8.6)."""
        it = self._item(profile_id, item_id)
        if not evidence_id:
            raise AdMemoryError("kanıt kimliği zorunlu (aynı kullanıcı mesajı/karar tekrar gözlem sayılmaz)")
        ev = it["evidence_json"] if isinstance(it["evidence_json"], list) else jload(it["evidence_json"], []) or []
        if any(e.get("id") == evidence_id for e in ev):
            return {"item": it, "counted": False, "note": "bu kanıt zaten sayılmış"}
        ev.append({"id": evidence_id, "at": now_iso(), "note": note})
        obs = it["observations"] + 1
        status = it["status"]
        if it["layer"] == "preference" and obs >= 3 and status == "proposed":
            status = "active"
        conf = min(0.95, (it["confidence"] or 0.5) + 0.1)
        with self.tx():
            self.ex("UPDATE memory_items SET evidence_json=?, observations=?, status=?, confidence=?, last_validated_at=? WHERE id=?",
                    (jdump(ev), obs, status, conf, now_iso(), it["id"]))
        return {"item": self.q1("SELECT * FROM memory_items WHERE id=?", (it["id"],)), "counted": True}

    def memory_update(self, item_id: int, profile_id: int | None = None, content: str | None = None, status: str | None = None,
                      conflict: dict | None = None, scope: dict | None = None, tags: list[str] | None = None,
                      confidence: float | None = None, by_user: bool = False) -> dict:
        it = self._item(profile_id, item_id)
        if status and status not in ("proposed", "active", "due_revalidation", "retired", "superseded", "archived"):
            raise AdMemoryError("geçersiz durum")
        if status == "active" and it["layer"] == "preference" and it["observations"] < 3 and not by_user:
            raise AdMemoryError("tercih üç tutarlı gözlemle ya da kullanıcının açık ifadesiyle aktifleşir (8.6)")
        if content and len(content) > MAX_ITEM_CHARS:
            raise AdMemoryError(f"öğe en fazla {MAX_ITEM_CHARS} karakter")
        sets: dict[str, Any] = {}
        if content:
            sets["content"] = content.strip()
        if status:
            sets["status"] = status
        if conflict:
            sets["conflict_json"] = jdump({**conflict, "at": now_iso()})
        elif conflict is not None:
            sets["conflict_json"] = None
        if scope is not None:
            sets["scope_json"] = jdump(scope)
        if tags is not None:
            sets["tags"] = ",".join(tags)
        if confidence is not None:
            sets["confidence"] = float(confidence)
        if by_user:
            sets["source"] = "user"
            sets["last_validated_at"] = now_iso()
        if not sets:
            return it
        with self.tx():
            self.ex(f"UPDATE memory_items SET {', '.join(f'{k}=?' for k in sets)} WHERE id=?", (*sets.values(), it["id"]))
            new = self.q1("SELECT * FROM memory_items WHERE id=?", (it["id"],))
            self._fts_put("memory", it["id"], profile_id, new["content"] + " " + (new["tags"] or "").replace(",", " "))
        return new

    def memory_merge(self, keep_id: int, merge_ids: list[int], profile_id: int | None = None, merged_content: str | None = None) -> dict:
        """Claude'un konsolidasyon kararı: grup tek öğede birleşir; kanıtlar tekilleşerek toplanır (8.7)."""
        keep = self._item(profile_id, keep_id)
        others = [self._item(profile_id, i) for i in merge_ids if int(i) != int(keep_id)]
        if any(o["layer"] != keep["layer"] for o in others):
            raise AdMemoryError("farklı katmanlar birleştirilmez")
        ev = {e.get("id"): e for e in (keep["evidence_json"] or [])}
        for o in others:
            for e in o["evidence_json"] or []:
                ev.setdefault(e.get("id"), e)
        evl = [e for e in ev.values()]
        obs = max(keep["observations"], len([e for e in evl if e.get("id")]) or 1)
        status = keep["status"]
        if keep["layer"] == "preference" and obs >= 3 and status == "proposed":
            status = "active"
        with self.tx():
            self.ex("UPDATE memory_items SET content=COALESCE(?, content), evidence_json=?, observations=?, status=?, last_validated_at=? WHERE id=?",
                    (merged_content, jdump(evl), obs, status, now_iso(), keep["id"]))
            for o in others:
                self.ex("UPDATE memory_items SET status='superseded', superseded_by=? WHERE id=?", (keep["id"], o["id"]))
                self._fts_del("memory", o["id"])
            new = self.q1("SELECT * FROM memory_items WHERE id=?", (keep["id"],))
            self._fts_put("memory", keep["id"], profile_id, new["content"] + " " + (new["tags"] or "").replace(",", " "))
            self._journal_insert(profile_id, None, "consolidation", f"hafıza birleştirildi: {len(others)} öğe → #{keep['id']}", None, None, None)
        return new

    # --- arama (8.4) ------------------------------------------------------------
    def _fts_hits(self, profile_id, query: str, limit: int = 20, kinds=("memory", "journal")) -> list[dict]:
        q = fts_query(query)
        if not q:
            return []
        try:
            rows = self.qa(f"""SELECT ref_id, kind, bm25(memory_fts) AS score FROM memory_fts
                               WHERE memory_fts MATCH ? AND profile_id IS ? AND kind IN ({','.join('?' * len(kinds))})
                               ORDER BY score LIMIT ?""", (q, profile_id, *kinds, int(limit)))
        except sqlite3.OperationalError:
            return []
        return rows

    def memory_search(self, query: str, profile_id: int | None = None, layer: str | None = None, include_journal: bool = True,
                      limit: int = 10, stage: str | None = None, scope: dict | None = None) -> dict:
        """FTS5 trigram; Türkçe normalleştirme; kök bulma yok. <3 harf: etiket ve LIKE. Sıra: kapsam, bm25, güven, tazelik, kullanım."""
        if profile_id is not None:
            self._profile(profile_id, allow_archived=True)
        results: list[dict] = []
        if len(tr_fold(query).strip()) < 3:
            like = f"%{query.strip()}%"
            rows = self.qa("SELECT * FROM memory_items WHERE profile_id IS ? AND (content LIKE ? OR tags LIKE ?) AND status NOT IN ('superseded')",
                           (profile_id, like, like))
            for r in rows:
                results.append({"kind": "memory", "item": r, "score": 0.0})
        else:
            kinds = ("memory", "journal") if include_journal else ("memory",)
            for h in self._fts_hits(profile_id, query, limit=60, kinds=kinds):
                if h["kind"] == "memory":
                    r = self.q1("SELECT * FROM memory_items WHERE id=?", (h["ref_id"],))
                    if r and r["status"] != "superseded" and (layer is None or r["layer"] == layer):
                        results.append({"kind": "memory", "item": r, "score": h["score"]})
                else:
                    r = self.q1("SELECT id, ts, type, summary, campaign_id FROM journal WHERE id=?", (h["ref_id"],))
                    if r:
                        results.append({"kind": "journal", "item": r, "score": h["score"]})

        def rank(x):
            it = x["item"]
            if x["kind"] != "memory":
                return (0, x["score"], 0, 0, 0)
            sc = 1 if scope and (it.get("scope_json") or {}) and all((it["scope_json"] or {}).get(k) == v for k, v in scope.items()) else 0
            fresh = parse_iso(it["last_validated_at"] or it["created_at"]).timestamp()
            return (-sc, x["score"], -(it["confidence"] or 0), -fresh, -(it["use_count"] or 0))
        results.sort(key=rank)
        results = results[:limit]
        with self.tx():
            for r in results:
                if r["kind"] == "memory":
                    self._use(r["item"]["id"], profile_id, stage, "search")
        return {"query": query, "results": results,
                "note": "Çekim ekli biçimler yalnızca ortak alt dizelerle eşleşir; kök bulma yoktur (ör. 'paket' 'paketleme'yi bulabilir, 'paketi' sorgusunun onu bulması garanti değildir)."}

    def _use(self, item_id: int, profile_id, stage, via) -> None:
        self.ex("INSERT INTO memory_usage(item_id,profile_id,stage,via,ts) VALUES(?,?,?,?,?)", (item_id, profile_id, stage, via, now_iso()))
        self.ex("UPDATE memory_items SET use_count=use_count+1, last_used_at=? WHERE id=?", (now_iso(), item_id))

    # --- profil kartı (8.4) -------------------------------------------------------
    def memory_card(self, profile_id: int, budget: int | None = None) -> dict:
        budget = budget or _recipes()["card_budget_tokens"]
        p = self._profile(profile_id, allow_archived=True)
        brand = self.q1("SELECT * FROM brands WHERE id=?", (p["brand_id"],)) if p["brand_id"] else None
        critical: list[str] = []
        st = self.campaign_status(profile_id)
        for c in st["campaigns"]:
            line = f"Kampanya #{c['campaign']['id']} {c['campaign']['name']}: {c['campaign']['stage']} ({c['stage_name']})"
            if c["calendar"].get("line"):
                line += f" · {c['calendar']['line']}"
            critical.append(line)
            for g in c["pending_gates"]:
                critical.append(f"BEKLEYEN KAPI: {g['stage']} {g['gate']} (stage_run {g['id']}, sürüm {g['output_version']}, tur {g['cycle_id']})")
            for w in c["warnings"]:
                critical.append(f"UYARI: {w}")
            if c["unresolved_generations"]:
                critical.append(f"BELİRSİZ/SÜREN ÜCRETLİ ÜRETİM: {c['unresolved_generations']}")
        cps = self.checkpoint_get(profile_id)["open"]
        for cp in cps[:3]:
            stj = cp["state_json"] if isinstance(cp["state_json"], dict) else jload(cp["state_json"], {})
            critical.append(f"DEVAM NOTU {cp['stage']} ({cp['scope_key']}): sıradaki → {stj.get('next_step')}")
        if p["status"] == "onboarding":
            for b in self._activation_blockers(p):
                critical.append(f"TANIŞMA EKSİĞİ: {b}")
        sections: list[tuple[str, str]] = []
        if brand:
            sections.append(("Marka", f"{brand['name']} · ton: {brand['tone'] or '—'} · CTA: {brand['cta_url'] or '—'} · saat dilimi: {brand['timezone'] or 'doğrulanmadı'}"
                                      + (f" · kaçınılacaklar: {brand['avoid_list']}" if brand['avoid_list'] else "")))
        prefs = self.qa("SELECT id, content FROM memory_items WHERE profile_id=? AND layer='preference' AND status='active' ORDER BY confidence DESC, observations DESC LIMIT 8", (profile_id,))
        if prefs:
            sections.append(("Tercihler", " | ".join(f"#{x['id']} {x['content']}" for x in prefs)))
        rules = self.qa("SELECT id, rule, season FROM playbook_rules WHERE profile_id=? AND status='active' ORDER BY confidence DESC LIMIT 6", (profile_id,))
        if rules:
            sections.append(("Playbook", " | ".join(f"#{r['id']} {r['rule']}" + (f" ({r['season']})" if r['season'] else "") for r in rules)))
        jr = self.qa("SELECT ts, summary FROM journal WHERE profile_id=? AND rolled=0 ORDER BY ts DESC LIMIT 5", (profile_id,))
        if jr:
            sections.append(("Son günlük", " | ".join(f"{r['ts'][:10]} {r['summary']}" for r in jr)))
        text = "\n".join(critical)
        used = est_tokens(text)
        included, omitted = [], []
        for title, body in sections:
            t = est_tokens(body) + 3
            if used + t <= budget:
                included.append(f"## {title}\n{body}")
                used += t
            else:
                omitted.append(title)
        with self.tx():
            for x in prefs:
                self._use(x["id"], profile_id, "card", "context")
        return {"profile": {"id": p["id"], "name": p["name"], "status": p["status"], "meta_data_mode": p["meta_data_mode"]},
                "critical": critical, "card": "\n\n".join(included), "tokens": used, "budget": budget, "omitted_sections": omitted,
                "note": "Kart canlı üretilir; bütçe kritik kimlik, kapı ve engelleri kırpmaz."}

    # --- aşama bağlam paketi (8.4) -----------------------------------------------
    def memory_context(self, profile_id: int, stage: str, campaign_id: int | None = None, cycle_id: int | None = None,
                       budget: int | None = None) -> dict:
        rec = _recipes()
        if stage not in rec["stages"]:
            raise AdMemoryError(f"reçetesi olmayan aşama: {stage}")
        budget = budget or rec["default_budget_tokens"]
        p = self._profile(profile_id, allow_archived=True)
        c = self._campaign(profile_id, campaign_id) if campaign_id else None
        cy = self._cycle(profile_id, cycle_id, campaign_id) if cycle_id else (self._current_cycle(c) if c else None)
        parts: list[dict] = []
        used_items: list[int] = []
        for src in rec["stages"][stage]["sources"]:
            parts.extend(self._ctx_source(src, p, c, cy, used_items))
        used, out, refs = 0, [], []
        for part in parts:
            t = est_tokens(part["text"]) + 4
            if used + t <= budget:
                out.append(part)
                used += t
            else:
                refs.append({"title": part["title"], "ref": part.get("ref")})
        with self.tx():
            for iid in used_items:
                if any(o.get("ref") == f"memory:{iid}" for o in out):
                    self._use(iid, profile_id, stage, "context")
        return {"stage": stage, "budget": budget, "tokens": used, "items": out, "omitted": refs,
                "note": "Bütçeye sığmayanların yalnızca başlığı ve kimliği verildi; gerekirse memory_search ile açılır."}

    def _ctx_source(self, src: str, p: dict, c: dict | None, cy: dict | None, used_items: list[int]) -> list[dict]:
        name, _, arg = src.partition(":")
        pid = p["id"]
        out: list[dict] = []

        def add(title, text, ref=None):
            if text:
                out.append({"title": title, "text": text if isinstance(text, str) else json.dumps(text, ensure_ascii=False, default=str)[:1500], "ref": ref})

        brand = self.q1("SELECT * FROM brands WHERE id=?", (p["brand_id"],)) if p["brand_id"] else None
        prod = self.q1("SELECT * FROM products WHERE id=?", (c["product_id"],)) if c and c["product_id"] else None
        if name == "profile_summary":
            add("Profil", f"{p['name']} · durum {p['status']} · Meta veri yolu {p['meta_data_mode'] or '—'} · geçmiş {p['history_status']}", f"profile:{pid}")
        elif name == "brand" and brand:
            add("Marka", {k: brand[k] for k in ("name", "tone", "avoid_list", "cta_url", "timezone", "elevenlabs_voice_id")}, f"brand:{brand['id']}")
        elif name in ("product", "products"):
            if name == "product" and prod:
                add("Ürün", {k: prod[k] for k in ("name", "price", "currency", "occasions_json", "provable_claims_json", "observation_json")}, f"product:{prod['id']}")
            elif brand:
                for r in self.qa("SELECT id, name, onboarding_status FROM products WHERE brand_id=?", (brand["id"],)):
                    add(f"Ürün {r['name']}", f"tanışma: {r['onboarding_status']}", f"product:{r['id']}")
        elif name == "product_shoot_profile" and prod:
            add("Ürüne özgü çekim tarifi", prod["shoot_profile_json"] or "kart yok: genel kurallar", f"product:{prod['id']}")
        elif name == "economics" and prod:
            add("Ekonomi", self.economics(prod), f"product:{prod['id']}")
        elif name == "onboarding_answers" and brand:
            rows = self.qa("SELECT question_key, answer, source, confirmed FROM onboarding_answers WHERE scope='brand' AND scope_id=? ORDER BY id DESC LIMIT 20", (brand["id"],))
            add("Tanışma cevapları", rows)
        elif name == "campaign" and c:
            add("Kampanya", {k: c[k] for k in ("name", "goal", "result_type", "season", "budget_total", "mode", "stage", "cycle")}, f"campaign:{c['id']}")
        elif name in ("preferences",):
            q = "SELECT id, content, observations FROM memory_items WHERE profile_id=? AND layer='preference' AND status='active'"
            args: tuple = (pid,)
            if arg:
                q += " AND (','||COALESCE(tags,'')||',') LIKE ?"
                args = (pid, f"%,{arg},%")
            for r in self.qa(q + " ORDER BY confidence DESC LIMIT 10", args):
                add("Tercih", r["content"], f"memory:{r['id']}")
                used_items.append(r["id"])
        elif name == "procedural":
            for r in self.qa("""SELECT id, content FROM memory_items WHERE (profile_id=? OR profile_id IS NULL) AND layer='procedural' AND status='active'
                                AND (','||COALESCE(tags,'')||',') LIKE ? ORDER BY confidence DESC LIMIT 8""", (pid, f"%,{arg},%")):
                add("Üretim bilgisi", r["content"], f"memory:{r['id']}")
                used_items.append(r["id"])
        elif name == "semantic":
            for r in self.qa("""SELECT id, content FROM memory_items WHERE profile_id=? AND layer='semantic' AND status='active'
                                AND (','||COALESCE(tags,'')||',') LIKE ? LIMIT 8""", (pid, f"%,{arg},%")):
                add("Bilgi", r["content"], f"memory:{r['id']}")
                used_items.append(r["id"])
        elif name == "playbook":
            q = "SELECT id, rule, season, scope_json FROM playbook_rules WHERE profile_id=?"
            q += " AND status='active'" if arg in ("active", "scoped") else ""
            for r in self.qa(q, (pid,)):
                add("Playbook", r["rule"] + (f" [sezon: {r['season']}]" if r["season"] else ""), f"playbook:{r['id']}")
        elif name == "hypotheses":
            q = "SELECT id, statement, metric, status, is_primary FROM hypotheses WHERE profile_id=?"
            args2: tuple = (pid,)
            if arg == "open":
                q += " AND status IN ('open','testing')"
            elif arg == "all_cycle" and cy:
                q += " AND cycle_id=?"
                args2 = (pid, cy["id"])
            elif arg == "candidate_primary":
                q += " AND status IN ('open','testing') AND is_primary=0"
            for r in self.qa(q + " ORDER BY id DESC LIMIT 12", args2):
                add("Hipotez", f"#{r['id']} {r['statement']} ({r['metric']}, {r['status']}{', birincil' if r['is_primary'] else ''})", f"hypothesis:{r['id']}")
        elif name == "competitor_set":
            add("Rakip seti", self.competitor_list(pid)["competitors"])
        elif name == "competitor_last_snapshot":
            s = self.q1("SELECT id, mode, fetched_at, n_ads, coverage_json, sha256 FROM competitor_snapshots WHERE profile_id=? ORDER BY fetched_at DESC, id DESC LIMIT 1", (pid,))
            if s:
                add("Son rakip görüntüsü", s, f"snapshot:{s['id']}")
        elif name == "competitive_insights":
            for r in self.qa("SELECT id, kind, statement, label FROM competitive_insights WHERE profile_id=? ORDER BY id DESC LIMIT 12", (pid,)):
                add(f"Rekabet bulgusu ({r['kind']}, {r['label']})", r["statement"], f"insight:{r['id']}")
        elif name == "competitive_map_summary":
            rows = self.qa("SELECT kind, statement, label FROM competitive_insights WHERE profile_id=? AND (cycle_id IS ? OR cycle_id IS NULL) ORDER BY id DESC LIMIT 10",
                           (pid, cy["id"] if cy else None))
            if rows:
                add("Rekabet haritası özeti", " | ".join(f"[{r['kind']}/{r['label']}] {r['statement']}" for r in rows))
        elif name == "brand_docs" or name == "brand_docs_competitors":
            d = self.profile_dir(pid) / "brand" / "docs"
            files = [f.name for f in d.glob("*") if f.is_file()] if d.exists() else []
            if files:
                add("Marka belgeleri", f"profiles/<profil>/brand/docs: {', '.join(files[:12])} (brand_doc kaynağı; öneridir, hazır karar değildir)")
        elif name == "strategy" and cy:
            add("Onaylı strateji", cy["strategy_json"] or "henüz yok", f"cycle:{cy['id']}")
        elif name == "budget_state" and cy:
            add("Bütçe planı", cy["budget_plan_json"] or "hesaplanmadı", f"cycle:{cy['id']}")
        elif name == "risk_limits" and cy:
            add("Zarar-risk sınırı", cy["risk_limits_json"] or "onaylanmadı", f"cycle:{cy['id']}")
        elif name == "calendar" and cy:
            add("Takvim", {k: cy[k] for k in ("test_days", "cycle_days", "launch_at", "launched_at", "plan_day", "calendar_json")}, f"cycle:{cy['id']}")
        elif name == "concepts" and cy:
            if arg == "selected":
                rows = self.qa("SELECT id, code, name, competitive_role, sound_intent FROM concepts WHERE cycle_id=? AND decision IN ('accepted','merged')", (cy["id"],))
            elif arg == "rejected_deferred":
                rows = self.qa("""SELECT k.id, k.code, k.name, k.decision, k.rationale FROM concepts k JOIN campaigns c ON c.id=k.campaign_id
                                  WHERE c.brand_id=? AND k.decision IN ('rejected','deferred') ORDER BY k.id DESC LIMIT 10""", (p["brand_id"],))
            else:
                rows = self.qa("SELECT id, code, distance_check_json FROM concepts WHERE cycle_id=? AND competitive_role IN ('proven','counter')", (cy["id"],))
            for r in rows:
                add(f"Konsept {r['code']}", r, f"concept:{r['id']}")
        elif name == "coaching_summary":
            for r in self.qa("SELECT ts, summary FROM journal WHERE profile_id=? AND type IN ('coaching','stage_summary') AND summary LIKE 'S16%' ORDER BY ts DESC LIMIT 2", (pid,)):
                add("Koçluk özeti", f"{r['ts'][:10]} {r['summary']}")
        elif name == "portfolio_results":
            for r in self.qa("SELECT ts, summary FROM journal WHERE profile_id=? AND type='portfolio_result' ORDER BY ts DESC LIMIT 3", (pid,)):
                add("Portföy sonucu", r["summary"])
        elif name == "calibration" and brand:
            add("Kalibrasyon", self.calibration_get(pid))
        elif name == "action_items" and c:
            add("Uygulama listesi", self.action_items_list(pid, c["id"], None)["items"][-10:])
        elif name == "model_acceptance":
            rows = self.qa("""SELECT model, COUNT(*) AS n, SUM(CASE WHEN accepted=1 THEN 1 ELSE 0 END) AS acc FROM generations
                              WHERE profile_id=? AND status='completed' GROUP BY model""", (pid,))
            add("Model kabul oranları", rows)
        elif name == "cost_summary" and c:
            add("Maliyet", self.cost_summary(pid, c["id"]))
        elif name == "style" and brand:
            add("Stil kitabı", brand["style_json_path"] or "henüz yok")
        elif name == "shoot_library_summary":
            r = self.q1("SELECT COUNT(*) AS n, COUNT(DISTINCT campaign_id) AS camps FROM assets WHERE profile_id=? AND kind IN ('footage','photo')", (pid,))
            add("Çekim kütüphanesi", f"{r['n']} klip/fotoğraf, {r['camps']} kampanyadan (asset_query scope=profile)")
        elif name == "edit_plans" and cy:
            rows = self.qa("SELECT id, format, purpose, status, version FROM edit_plans WHERE cycle_id=? ORDER BY id DESC LIMIT 8", (cy["id"],))
            add("Kurgu planları", rows)
        elif name == "consolidation_state":
            add("Konsolidasyon", self.consolidation_due(pid))
        elif name == "meta_sync_state":
            add("Meta senkronu", {"last_meta_sync_at": p["last_meta_sync_at"], "history_status": p["history_status"]})
        elif name in ("benchmarks", "priors") and brand:
            add("Kıyaslar" if name == "benchmarks" else "Önseller",
                self.qa("SELECT kind, metric, value FROM account_benchmarks WHERE brand_id=?", (brand["id"],)) if name == "benchmarks"
                else self.qa("SELECT objective, metric, a, b, n_source FROM priors WHERE brand_id=?", (brand["id"],)))
        # tanımlı olmayan ya da veri olmayan kaynaklar sessizce boş döner (reçete genişleyebilir)
        return out

    # --- konsolidasyon ve yaşam döngüsü (8.6, 8.7) --------------------------------------
    def consolidation_due(self, profile_id: int | None = None, threshold: int = 50) -> dict:
        last = self.q1("SELECT MAX(ts) AS ts FROM journal WHERE profile_id IS ? AND type='consolidation_run'", (profile_id,))["ts"] or "1970-01-01T00:00:00Z"
        n_items = self.q1("SELECT COUNT(*) AS n FROM memory_items WHERE profile_id IS ? AND created_at>?", (profile_id, last))["n"]
        n_j = self.q1("SELECT COUNT(*) AS n FROM journal WHERE profile_id IS ? AND ts>?", (profile_id, last))["n"]
        return {"due": (n_items + n_j) >= threshold, "new_items": n_items, "new_journal": n_j, "threshold": threshold, "since": last}

    def memory_consolidate(self, profile_id: int | None = None, max_groups: int = 10, similarity: float = 0.45) -> dict:
        """Python aday grupları çıkarır (aynı katman+kapsam, etiket örtüşmesi, trigram benzerliği); birleştirme Claude'undur."""
        rows = self.qa("SELECT * FROM memory_items WHERE profile_id IS ? AND status IN ('proposed','active','due_revalidation') ORDER BY id", (profile_id,))
        groups: list[list[dict]] = []
        seen: set[int] = set()
        for i, a in enumerate(rows):
            if a["id"] in seen:
                continue
            grp = [a]
            for b in rows[i + 1:]:
                if b["id"] in seen or b["layer"] != a["layer"] or (a["scope_json"] or None) != (b["scope_json"] or None):
                    continue
                ta = set((a["tags"] or "").split(",")) - {""}
                tb = set((b["tags"] or "").split(",")) - {""}
                if (ta & tb and trigram_similarity(a["content"], b["content"]) >= similarity * 0.6) or trigram_similarity(a["content"], b["content"]) >= similarity:
                    grp.append(b)
            if len(grp) > 1:
                for g in grp:
                    seen.add(g["id"])
                groups.append([{"id": g["id"], "content": g["content"], "observations": g["observations"], "status": g["status"]} for g in grp])
            if len(groups) >= max_groups:
                break
        with self.tx():
            self._journal_insert(profile_id, None, "consolidation_run", f"konsolidasyon adayları çıkarıldı: {len(groups)} grup", None, None, None)
        return {"groups": groups, "instructions": "Her grubu oku: birleştir (memory_merge), ayır (değişiklik yok) ya da çelişki işaretle (memory_update conflict). En fazla 10 grup."}

    def memory_lifecycle_tick(self, profile_id: int | None = None, half_life_days: float = 180.0, threshold: float = 0.3) -> dict:
        """Güven yarı ömürle azalır; eşik altı yeniden doğrulamaya düşer; son 3 turda kullanılmayan aktif öğe arşive iner (8.6)."""
        rows = self.qa("SELECT * FROM memory_items WHERE profile_id IS ? AND status IN ('active','proposed')", (profile_id,))
        cutoff = None
        if profile_id is not None:
            cyc = self.qa("""SELECT cy.created_at FROM cycles cy JOIN campaigns c ON c.id=cy.campaign_id JOIN profiles p ON p.brand_id=c.brand_id
                             WHERE p.id=? ORDER BY cy.created_at DESC LIMIT 3""", (profile_id,))
            if len(cyc) == 3:
                cutoff = cyc[-1]["created_at"]
        decayed, revalid, archived = 0, [], []
        with self.tx():
            for r in rows:
                last = parse_iso(r["last_validated_at"] or r["created_at"])
                days = (utcnow() - last).total_seconds() / 86400
                base = r["confidence"] or 0.5
                conf = base * math.pow(0.5, days / half_life_days) if days > 0 else base
                if r["status"] == "active" and conf < threshold:
                    self.ex("UPDATE memory_items SET status='due_revalidation' WHERE id=?", (r["id"],))
                    revalid.append(r["id"])
                elif cutoff and r["status"] == "active" and (r["last_used_at"] or r["created_at"]) < cutoff:
                    self.ex("UPDATE memory_items SET status='archived' WHERE id=?", (r["id"],))
                    archived.append(r["id"])
                decayed += 1
        return {"checked": decayed, "due_revalidation": revalid, "archived": archived, "effective_confidence_note": "yarı ömür varsayılan 180 gün"}

    # --- unutma (8.8) --------------------------------------------------------------
    def memory_forget(self, item_id: int, confirm_text: str, profile_id: int | None = None) -> dict:
        """Öğe + FTS + kullanım/kanıt kopyaları + türeyen özetler/dışa aktarımlar + öğeyi içeren yerel yedekler temizlenir."""
        it = self._item(profile_id, item_id)
        if not confirm_text or not confirm_text.strip():
            raise AdMemoryError("unutma kullanıcının açık isteğiyle yapılır")
        content = it["content"]
        frag = content[:60]
        with self.tx():
            self.ex("DELETE FROM memory_usage WHERE item_id=?", (it["id"],))
            self.ex("UPDATE memory_items SET superseded_by=NULL WHERE superseded_by=?", (it["id"],))
            self._fts_del("memory", it["id"])
            self.ex("DELETE FROM memory_items WHERE id=?", (it["id"],))
            touched = self.qa("SELECT id, summary FROM journal WHERE profile_id IS ? AND summary LIKE ?", (profile_id, f"%{frag}%"))
            for j in touched:
                self.ex("UPDATE journal SET summary='[unutma isteğiyle kaldırıldı]', detail_json=NULL WHERE id=?", (j["id"],))
                self._fts_del("journal", j["id"])
            self.ex("DELETE FROM journal_rollups WHERE profile_id IS ? AND summary LIKE ?", (profile_id, f"%{frag}%"))
            self.ex("""INSERT INTO journal(profile_id,campaign_id,ts,type,summary,rolled) VALUES(?,NULL,?, 'forget', 'bir hafıza öğesi kullanıcı isteğiyle silindi', 0)""",
                    (profile_id, now_iso()))
        exports_removed = []
        for d in self._export_dirs(profile_id):
            for f in d.glob("*.md"):
                try:
                    if frag in f.read_text(encoding="utf-8"):
                        f.unlink()
                        exports_removed.append(f.name)
                except OSError:
                    continue
        backups_removed = []
        bdir = self.data_dir / "backups"
        for b in sorted(bdir.glob("ad-memory-*.sqlite")) if bdir.exists() else []:
            try:
                con = sqlite3.connect(f"file:{b}?mode=ro", uri=True)
                hit = con.execute("SELECT 1 FROM memory_items WHERE id=? OR content=? LIMIT 1", (it["id"], content)).fetchone()
                con.close()
            except sqlite3.Error:
                hit = None
            if hit:
                b.unlink()
                backups_removed.append(b.name)
        new_backup = self.backup(reason="forget") if backups_removed else None
        if exports_removed:
            self.export_markdown(profile_id)
        return {"forgotten": item_id, "journal_scrubbed": len(touched), "exports_removed": exports_removed,
                "backups_removed": backups_removed, "new_backup": new_backup["path"] if new_backup else None,
                "pending_outside": "Meta'da yayınlanmış içerik, kullanıcının haricî kopyaları ve sağlayıcı kayıtları yerel silmeyle yok olmuş sayılmaz."}

    def _export_dirs(self, profile_id: int | None) -> list[Path]:
        if profile_id is None:
            return [self.data_dir / "memory" / "system"]
        base = self.profile_dir(profile_id)
        return [base, base / "memory"]

    def export_markdown(self, profile_id: int | None = None) -> dict:
        """playbook.md, hypotheses.md, günlük ve hafıza dışa aktarımı (yalnızca okunabilirlik; kaynak SQLite, geri okunmaz)."""
        written = []
        header = "<!-- reklam-atolyesi dışa aktarımı: kaynak SQLite'tır; bu dosya okunmaz ve geri yazılmaz (8.1) -->\n"
        if profile_id is None:
            d = self.data_dir / "memory" / "system"
            items = self.qa("SELECT * FROM memory_items WHERE profile_id IS NULL AND status NOT IN ('superseded') ORDER BY layer, id")
            text = header + "# Sistem hafızası\n\n" + "\n".join(f"- [{i['layer']}/{i['status']}] #{i['id']} {i['content']}" for i in items) + "\n"
            atomic_write(d / "memory.md", text)
            written.append(str(d / "memory.md"))
            return {"written": written}
        self._profile(profile_id, allow_archived=True)
        base = self.profile_dir(profile_id)
        rules = self.qa("SELECT * FROM playbook_rules WHERE profile_id=? ORDER BY status, id", (profile_id,))
        atomic_write(base / "playbook.md", header + "# Playbook\n\n" + "\n".join(
            f"- [{r['status']}] #{r['id']} {r['rule']}" + (f" (sezon: {r['season']})" if r["season"] else "") +
            (f" — emekli: {r['retired_reason']}" if r["retired_reason"] else "") for r in rules) + "\n")
        hyps = self.qa("SELECT * FROM hypotheses WHERE profile_id=? ORDER BY id", (profile_id,))
        atomic_write(base / "hypotheses.md", header + "# Hipotez defteri\n\n" + "\n".join(
            f"- [{h['status']}] #{h['id']} {h['statement']} ({h['metric']})" + (" · birincil" if h["is_primary"] else "") for h in hyps) + "\n")
        js = self.qa("SELECT ts, type, summary FROM journal WHERE profile_id=? ORDER BY ts DESC LIMIT 500", (profile_id,))
        atomic_write(base / "memory" / "journal.md", header + "# Günlük\n\n" + "\n".join(f"- {j['ts'][:16]} [{j['type']}] {j['summary']}" for j in js) + "\n")
        items = self.qa("SELECT * FROM memory_items WHERE profile_id=? AND status NOT IN ('superseded') ORDER BY layer, id", (profile_id,))
        atomic_write(base / "memory" / "memory.md", header + "# Hafıza öğeleri\n\n" + "\n".join(
            f"- [{i['layer']}/{i['status']}] #{i['id']} {i['content']} (gözlem {i['observations']})" for i in items) + "\n")
        written += [str(base / "playbook.md"), str(base / "hypotheses.md"), str(base / "memory" / "journal.md"), str(base / "memory" / "memory.md")]
        return {"written": written}
