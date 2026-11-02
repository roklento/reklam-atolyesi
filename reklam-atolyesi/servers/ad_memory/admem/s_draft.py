"""Taslak denetimi (2.5.0): metin aşamasının belgesi kullanıcıya gösterilmeden önce ölçütten geçer; tur sayısını sunucu tutar.

Akış (KURALLAR.md K10): belge yazılır → draft_check → kritik sorun varsa düzelt → draft_check (en fazla MAX_DRAFT_ROUNDS tur) →
stage_complete. stage_complete, metin aşamasının her .md çıktısı için aynı içerikli (sha256) bir denetim ister; denetim geçmediyse ve
tur sınırı dolmadıysa aşamayı tamamlamaz. Tur sınırı dolduysa tamamlar ama kalan sorunları döndürür; bunlar kullanıcıya söylenir.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from . import drafts as DR
from . import stages as ST
from .util import AdMemoryError, jdump, jload, now_iso


class DraftMixin:
    # ------------------------------------------------------------------ bağlam
    def _draft_ctx(self, profile_id: int, stage: str, campaign_id: int | None, cycle_id: int | None) -> dict:
        if stage not in ST.CAMPAIGN_STAGES or campaign_id is None or cycle_id is None:
            return {}
        c = self._campaign(profile_id, campaign_id)
        cy = self._cycle(profile_id, cycle_id, campaign_id)
        prod = self.q1("SELECT * FROM products WHERE id=?", (c["product_id"],)) if c["product_id"] else None
        bp = jload(cy["budget_plan_json"], {}) or {}
        rl = jload(cy["risk_limits_json"], {}) or {}
        ctx: dict = {
            "cycle_no": cy["cycle"],
            "campaign": {k: c[k] for k in ("result_type", "lead_method", "budget_total", "budget_total_confirmed", "trial", "mode", "season")
                         if k in c.keys()},
            "cycle": {k: cy[k] for k in ("adset_budget_daily", "test_days", "cycle_days")},
            "product": {"price": prod["price"], "currency": prod["currency"]} if prod else {},
            "economics": self.economics(prod) if prod else {},
            "budget_plan": bp,
            "risk_limits": rl,
            "round_mode": bp.get("round_mode"),
        }
        ts = c["test_structure"] if c["test_structure"] in ("bootstrap", "creative_test", "ab_test") else None
        ctx["structure"] = ts or bp.get("structure") or ("bootstrap" if cy["cycle"] <= 1 else "creative_test")
        snap = None
        if cy["competitor_snapshot_id"]:
            snap = self.q1("SELECT * FROM competitor_snapshots WHERE id=?", (cy["competitor_snapshot_id"],))
        if snap is None:
            snap = self.q1("SELECT * FROM competitor_snapshots WHERE cycle_id=? ORDER BY id DESC LIMIT 1", (cy["id"],))
        if snap:
            cov = jload(snap["coverage_json"], {}) or {}
            ctx["snapshot"] = {"id": snap["id"], "sha256": snap["sha256"], "n_concepts": cov.get("n_concepts"),
                               "weak": bool(cov.get("weak_coverage"))}
        concepts = self.qa("SELECT id, code FROM concepts WHERE cycle_id=? AND decision IN ('accepted','merged')", (cy["id"],))
        ctx["accepted_concepts"] = [k["code"] for k in concepts]
        ctx["accepted_test_hooks"] = sum(
            len(self.qa("SELECT 1 FROM hooks WHERE concept_id=? AND decision IN ('accepted','merged') AND reserve=0", (k["id"],)))
            for k in concepts)
        cr = self.qa("SELECT creative_key, delivery_role, qc_status, source_variant, ai_share FROM creatives WHERE cycle_id=?", (cy["id"],))
        test_keys = sorted({r["creative_key"] for r in cr if r["delivery_role"] == "test"})
        ctx["test_keys"] = test_keys
        ctx["reserve_only_keys"] = sorted({r["creative_key"] for r in cr if r["delivery_role"] == "reserve"} - set(test_keys))
        ctx["test_keys_not_passed"] = sorted({r["creative_key"] for r in cr if r["delivery_role"] == "test" and r["qc_status"] != "passed"})
        ctx["has_ai"] = any(r["delivery_role"] == "test" and (r["source_variant"] == "ai" or (r["ai_share"] or 0) > 0) for r in cr)
        return ctx

    def _meta_text_warnings(self, text: str) -> list[dict] | None:
        """S14 metinleri için scripts/qc/checks.py meta_text taraması (aynı kod). Yüklenemezse None (uyarı olarak bildirilir)."""
        try:
            root = Path(self.plugin_root) / "scripts"
            for sub in ("lib", "audio", "qc"):
                p = str(root / sub)
                if p not in sys.path:
                    sys.path.insert(0, p)
            spec = importlib.util.spec_from_file_location("ra_qc_checks", root / "qc" / "checks.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            secs = DR.parse_sections(text)
            copy = DR.section_text(secs, "Metinler") or ""
            return mod.meta_text([("Metinler", copy)])["warnings"] if copy else []
        except Exception:  # denetim aracı yüklenemese de taslak denetimi çalışır
            return None

    def _draft_scope(self, profile_id: int, stage: str, campaign_id: int | None, cycle_id: int | None, scope_key: str | None) -> str:
        if stage not in DR.DRAFT_STAGES:
            raise AdMemoryError(f"taslak denetimi metin aşamaları içindir: {', '.join(DR.DRAFT_STAGES)}")
        if stage in ST.CAMPAIGN_STAGES:
            if campaign_id is None or cycle_id is None:
                raise AdMemoryError("kampanya aşaması için campaign_id ve cycle_id gerekir")
            c = self._campaign(profile_id, campaign_id)
            self._cycle(profile_id, cycle_id, campaign_id)
            if c["stage"] != stage:
                raise AdMemoryError(f"kampanya {c['stage']} aşamasında; {stage} belgesi denetlenmez (önce o aşamaya dönülmeli)")
        if stage == "S00c" and not (scope_key or "").startswith("product:"):
            raise AdMemoryError("S00c taslak denetimi scope_key='product:<id>' ister")
        return self._scope_key(profile_id, campaign_id, cycle_id, scope_key)

    # ------------------------------------------------------------------ araçlar
    def draft_check(self, profile_id: int, stage: str, path: str, campaign_id: int | None = None, cycle_id: int | None = None,
                    scope_key: str | None = None) -> dict:
        """Metin aşaması belgesini denetler ve kaydeder. Tur sunucuda sayılır; değişmemiş içerik yeni tur değildir."""
        self._profile(profile_id)
        sk = self._draft_scope(profile_id, stage, campaign_id, cycle_id, scope_key)
        out = self._resolve_output(profile_id, {"path": path})
        p = Path(out["path"])
        if p.suffix.lower() not in DR.DRAFT_SUFFIXES:
            raise AdMemoryError("taslak denetimi .md belgeler içindir (tablo/veri dosyaları kendi araçlarıyla denetlenir)")
        text = p.read_bytes().decode("utf-8", errors="replace")
        tname = DR.template_for(stage, str(p))
        tmd = None
        if tname:
            tp = Path(self.plugin_root) / "templates" / "reports" / tname
            tmd = tp.read_text(encoding="utf-8") if tp.exists() else None
        ctx = self._draft_ctx(profile_id, stage, campaign_id, cycle_id)
        if stage == "S14" and tmd:
            w = self._meta_text_warnings(text)
            ctx["meta_text_warnings"] = w or []
        res = DR.check_document(text, stage, ctx, tmd)
        if stage == "S14" and tmd and ctx.get("meta_text_warnings") is None:
            res["issues"].append({"code": "meta_text", "severity": "warn", "message": "Meta reklam standartları metin taraması yüklenemedi; "
                                  "checks.py meta-text elle çalıştırılmalı"})
        with self.tx():
            prev = self.qa("SELECT id, sha256, round FROM draft_checks WHERE scope_key=? AND stage=? AND consumed_by_run_id IS NULL "
                           "ORDER BY id", (sk, stage))
            same = [r for r in prev if r["sha256"] == out["sha256"]]
            rnd = same[-1]["round"] if same else (max((r["round"] for r in prev), default=0) + 1)
            did = self.ex("""INSERT INTO draft_checks(profile_id,campaign_id,cycle_id,scope_key,stage,path,sha256,template,round,verdict,
                             critical,warnings,issues_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (profile_id, campaign_id, cycle_id, sk, stage, out["path"], out["sha256"], tname, rnd, res["verdict"],
                           res["critical"], res["warnings"], jdump(res["issues"]), now_iso())).lastrowid
        final = rnd >= DR.MAX_DRAFT_ROUNDS
        if res["verdict"] == "pass":
            nxt = ("Belge geçti. Uyarılar varsa kullanıcıya kısaca söyle (düzeltmek istersen düzelt ve yeniden denetle); "
                   "sonra stage_complete.")
        elif not final:
            nxt = (f"Kritik sorunlar var (tur {rnd}/{DR.MAX_DRAFT_ROUNDS}). Belgeyi KULLANICIYA GÖSTERMEDEN düzelt: veri eksikse önce kaydı "
                   "düzelt ya da kullanıcıya sor, sonra dosyayı yeniden yaz ve draft_check'i tekrar çağır. Değişmemiş dosya yeni tur sayılmaz.")
        else:
            nxt = (f"Tur sınırı ({DR.MAX_DRAFT_ROUNDS}) doldu ve kritik sorun kaldı. stage_complete'e izin var; kalan sorunları kullanıcıya "
                   "sade dille, tek tek ve belgeyle birlikte söyle. Karar kullanıcınındır; sorun gizlenmez, 'sorun yok' denmez.")
        return {"draft_check_id": did, "stage": stage, "path": out["path"], "sha256": out["sha256"], "template": tname,
                "round": rnd, "max_rounds": DR.MAX_DRAFT_ROUNDS, "verdict": res["verdict"], "final_round": final,
                "critical": res["critical"], "warnings": res["warnings"], "issues": res["issues"], "next": nxt}

    def draft_status(self, profile_id: int, stage: str, campaign_id: int | None = None, cycle_id: int | None = None,
                     scope_key: str | None = None) -> dict:
        self._profile(profile_id)
        if stage not in DR.DRAFT_STAGES:
            raise AdMemoryError(f"taslak denetimi metin aşamaları içindir: {', '.join(DR.DRAFT_STAGES)}")
        sk = self._scope_key(profile_id, campaign_id, cycle_id, scope_key)
        rows = self.qa("SELECT id, path, sha256, round, verdict, critical, warnings, created_at FROM draft_checks "
                       "WHERE scope_key=? AND stage=? AND consumed_by_run_id IS NULL ORDER BY id", (sk, stage))
        return {"stage": stage, "max_rounds": DR.MAX_DRAFT_ROUNDS, "open_checks": rows,
                "round": max((r["round"] for r in rows), default=0)}

    # ------------------------------------------------------------------ stage_complete kapısı
    def _draft_gate(self, profile_id: int, stage: str, sk: str, resolved: list[dict]) -> dict | None:
        """stage_complete içinde (işlem öncesi) çağrılır. Metin aşaması değilse None. Geçmezse AdMemoryError."""
        if stage not in DR.DRAFT_STAGES:
            return None
        docs = [r for r in resolved if Path(r["path"]).suffix.lower() in DR.DRAFT_SUFFIXES]
        if stage in DR.TEMPLATES and not any(DR.template_for(stage, r["path"]) for r in docs):
            pat = DR.TEMPLATES[stage][1].split("c\\d+-", 1)[-1].replace("\\.", ".").rstrip("$")
            raise AdMemoryError(f"{stage} belgesi (c<tur>-{pat}) çıktılarda yok: aşama belgesi şablondan yazılıp çıktıya eklenmeli")
        used, remaining = [], []
        for r in docs:
            chk = self.q1("SELECT * FROM draft_checks WHERE scope_key=? AND stage=? AND sha256=? AND consumed_by_run_id IS NULL "
                          "ORDER BY id DESC LIMIT 1", (sk, stage, r["sha256"]))
            if not chk:
                raise AdMemoryError(f"taslak denetimi yapılmadı ya da belge denetimden sonra değişti: draft_check(profile_id, '{stage}', "
                                    f"path='{r['path']}', …) çağrılmalı (KURALLAR K10)")
            issues = jload(chk["issues_json"], []) or []
            crit = [i for i in issues if i.get("severity") == "critical"]
            if chk["verdict"] == "fail" and chk["round"] < DR.MAX_DRAFT_ROUNDS:
                raise AdMemoryError(f"taslak denetimi geçmedi (tur {chk['round']}/{DR.MAX_DRAFT_ROUNDS}): "
                                    + "; ".join(i["message"] for i in crit[:6])
                                    + " — düzeltip draft_check'i yeniden çağır; kullanıcıya henüz gösterme")
            used.append(chk["id"])
            if crit:
                remaining.append({"path": r["path"], "round": chk["round"], "issues": crit})
        return {"check_ids": used, "remaining": remaining}

    def _draft_consume_in_tx(self, sk: str, stage: str, run_id: int) -> None:
        """Bu aşama kapsamındaki bütün açık denetimler aşama kaydına bağlanır: sonraki sürümün turları sıfırdan sayılır."""
        self.ex("UPDATE draft_checks SET consumed_by_run_id=? WHERE scope_key=? AND stage=? AND consumed_by_run_id IS NULL",
                (run_id, sk, stage))
