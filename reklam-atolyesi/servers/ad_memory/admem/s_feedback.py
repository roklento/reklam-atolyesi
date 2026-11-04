"""Admin ekibine anonim geri bildirim paketi (2.5.0; KURALLAR K15): önizleme → kullanıcının açık onayı → yerel dosya.

Müşteriye "hata defteri" diye anlatılır (2.8.0). Dosya <data_dir>/logs/hata-defteri/ altına yazılır (2.5.0'da logs/geri-bildirim/);
plugin onu hiçbir yere göndermez, kullanıcı isterse geliştiriciye kendisi gönderir. 2.8.0'dan itibaren defter "imzalar" taşır:
aşama · sinyal · kod · senaryo hücresi (ürün × kullanıcı); admin tarafında evals/defter_oku.py bunları toplu okur.
"""
from __future__ import annotations

import datetime as dt
import json
import platform
import sys
from pathlib import Path

from . import drafts as DR
from . import feedback as FB
from .util import AdMemoryError, atomic_write, jload, parse_iso, sha256_file, utcnow


class FeedbackMixin:
    def _plugin_version(self) -> str:
        try:
            return json.loads((Path(self.plugin_root) / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
        except Exception:
            return "unknown"

    def _feedback_cells(self) -> tuple[dict, dict]:
        """Kampanya ve profil başına senaryo hücresi kodu (2.8.0): ürün ekseni × kullanıcı ekseni; yalnızca sabit kod döner."""
        n_prof = self.q1("SELECT COUNT(*) AS n FROM profiles WHERE synthetic=0 AND status!='archived'")["n"] or 0
        by_camp: dict = {}
        by_prof: dict = {}
        rows = self.qa("""SELECT c.id AS cid, c.result_type AS rt, c.lead_method AS lm, c.season AS season, c.cycle AS cycle,
                                 pr.kind AS kind, pr.currency AS cur, pr.economics_json AS eco, pr.price AS price, pr.aov AS aov,
                                 pr.safety_factor AS sf, p.id AS pid, p.meta_data_mode AS dm
                          FROM campaigns c JOIN profiles p ON p.brand_id=c.brand_id LEFT JOIN products pr ON pr.id=c.product_id
                          WHERE p.synthetic=0 ORDER BY c.id""")
        for r in rows:
            eco = None
            if r["kind"] is not None:
                try:
                    eco = self.economics({"economics_json": r["eco"], "price": r["price"], "aov": r["aov"],
                                          "safety_factor": r["sf"]}).get("status")
                except Exception:
                    eco = None
            cell = FB.product_cell(r["kind"], eco, r["season"], r["rt"], r["lm"]) + "." + FB.user_cell(n_prof, r["dm"], r["cur"], r["cycle"])
            by_camp[r["cid"]] = cell
            by_prof[r["pid"]] = cell  # profilin en son kampanyası
        for r in self.qa("SELECT id, meta_data_mode AS dm FROM profiles WHERE synthetic=0"):
            by_prof.setdefault(r["id"], "Px." + FB.user_cell(n_prof, r["dm"], None, None))
        return by_camp, by_prof

    def _feedback_build(self, period_days: int) -> dict:
        if not (1 <= int(period_days) <= 365):
            raise AdMemoryError("period_days 1–365")
        now = utcnow()
        since = (now - dt.timedelta(days=int(period_days))).strftime("%Y-%m-%dT%H:%M:%SZ")
        from .db import current_version
        rep: dict = {"schema": FB.SCHEMA, "plugin_version": self._plugin_version(), "db_schema": current_version(self.conn),
                     "created_on": now.date().isoformat(), "period_days": int(period_days),
                     "platform": {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux" if sys.platform.startswith("linux") else "other"),
                     "python": ".".join(platform.python_version_tuple()[:2])}
        # profiller: yalnızca sayılar; sentetik (duman testi/canlı kabul) profiller sayılmaz
        prof = {"active": 0, "onboarding": 0, "archived": 0}
        for r in self.qa("SELECT status, COUNT(*) AS n FROM profiles WHERE synthetic=0 GROUP BY status"):
            prof[r["status"]] = r["n"]
        rep["profiles"] = prof
        real = "(SELECT id FROM profiles WHERE synthetic=0)"
        camps: dict = {"result_type": {}, "mode": {}, "cycles": 0, "launched_cycles": 0}
        for r in self.qa(f"""SELECT COALESCE(c.result_type,'unset') AS rt, c.mode AS mode FROM campaigns c JOIN profiles p ON p.brand_id=c.brand_id
                             WHERE p.synthetic=0 AND c.created_at>=?""", (since,)):
            camps["result_type"][r["rt"]] = camps["result_type"].get(r["rt"], 0) + 1
            camps["mode"][r["mode"]] = camps["mode"].get(r["mode"], 0) + 1
        cyc = self.q1(f"""SELECT COUNT(*) AS n, SUM(CASE WHEN cy.launched_at IS NOT NULL THEN 1 ELSE 0 END) AS l FROM cycles cy
                          JOIN campaigns c ON c.id=cy.campaign_id JOIN profiles p ON p.brand_id=c.brand_id
                          WHERE p.synthetic=0 AND cy.created_at>=?""", (since,))
        camps["cycles"], camps["launched_cycles"] = cyc["n"] or 0, cyc["l"] or 0
        rep["campaigns"] = camps
        # aşamalar: tamamlanma, sürüm sayısı (değişiklik isteği), geri dönüş, kapıda bekleme süresi
        stages: dict = {}
        runs = self.qa(f"SELECT stage, scope_key, output_version, status, started_at, finished_at, stale FROM stage_runs "
                       f"WHERE profile_id IN {real} AND started_at>=?", (since,))
        versions: dict = {}
        for r in runs:
            s = stages.setdefault(r["stage"], {"completed": 0, "skipped": 0, "back_to": 0, "max_versions": 0})
            if r["status"] == "done":
                s["completed"] += 1
            if r["status"] == "skipped":
                s["skipped"] += 1
            versions.setdefault((r["stage"], r["scope_key"]), []).append(r["output_version"])
        for (stg, _), vs in versions.items():
            stages[stg]["max_versions"] = max(stages[stg]["max_versions"], max(vs))
        for st, sv in stages.items():
            vs = [max(v) for (s2, _), v in versions.items() if s2 == st]
            sv["median_versions"] = FB.median(vs)
        for r in self.qa(f"SELECT stage, decision, COUNT(*) AS n FROM decisions WHERE profile_id IN {real} AND created_at>=? "
                         f"AND decision IN ('back','approved','skipped','correction') GROUP BY stage, decision", (since,)):
            if r["stage"] is None:
                continue
            s = stages.setdefault(r["stage"], {"completed": 0, "skipped": 0, "back_to": 0, "max_versions": 0})
            if r["decision"] == "back":
                s["back_to"] += r["n"]
            elif r["decision"] == "approved":
                s["approved"] = s.get("approved", 0) + r["n"]
            elif r["decision"] == "correction":
                s["corrections"] = s.get("corrections", 0) + r["n"]
        rep["stages"] = {k: stages[k] for k in sorted(stages)}
        # takılı: 3 günden uzun süredir running ya da kapıda bekleyen (güncel, eskimemiş) aşama kayıtları
        stuck: dict = {}
        for r in self.qa(f"SELECT stage, status, started_at, finished_at FROM stage_runs WHERE profile_id IN {real} AND stale=0 "
                         f"AND status IN ('running','awaiting_gate')"):
            t = parse_iso(r["finished_at"] or r["started_at"])
            if t is None:
                continue
            days = (now - t).total_seconds() / 86400
            if days < 3:
                continue
            k = (r["stage"], r["status"])
            e = stuck.setdefault(k, {"stage": r["stage"], "status": r["status"], "open_runs": 0, "oldest": "0-3", "_d": 0})
            e["open_runs"] += 1
            if days > e["_d"]:
                e["_d"], e["oldest"] = days, FB.days_bucket(days)
        rep["stuck"] = [{k: v for k, v in e.items() if k != "_d"} for e in sorted(stuck.values(), key=lambda x: -x["open_runs"])]
        # onaylanırken kalan taslak sorunu (kapıda kullanıcıya gösterilip onaylanan)
        rep["gates"] = {"approved_with_remaining_draft_issues": self.q1(
            f"SELECT COUNT(*) AS n FROM decisions WHERE profile_id IN {real} AND created_at>=? AND decision='approved' "
            f"AND note LIKE '%kalan taslak sorunu:%'", (since,))["n"]}
        # taslak denetimleri: sorun kodu sıklığı ve ilk turda geçme oranı
        dc = self.qa(f"SELECT stage, scope_key, round, verdict, issues_json, consumed_by_run_id FROM draft_checks "
                     f"WHERE profile_id IN {real} AND created_at>=?", (since,))
        codes: dict = {}
        by_stage: dict = {}
        first: dict = {}
        for r in dc:
            for i in jload(r["issues_json"], []) or []:
                c = f"{r['stage']}:{i.get('code')}:{i.get('severity')}"
                if FB.SAFE_TOKEN.match(c):
                    codes[c] = codes.get(c, 0) + 1
            b = by_stage.setdefault(r["stage"], {"checks": 0, "final_round_fail": 0})
            b["checks"] += 1
            if r["verdict"] == "fail" and r["round"] >= DR.MAX_DRAFT_ROUNDS:
                b["final_round_fail"] += 1
            if r["round"] == 1:
                key = (r["stage"], r["scope_key"], r["consumed_by_run_id"])
                first[key] = first.get(key) or r["verdict"] == "pass"
        rate = round(sum(1 for v in first.values() if v) / len(first), 2) if first else None
        rep["draft_checks"] = {"total": len(dc), "pass_first_round_rate": rate, "by_stage": by_stage,
                               "issue_codes": dict(sorted(codes.items(), key=lambda kv: -kv[1])[:40])}
        # QC: kreatif durumları
        qc = {"pending": 0, "passed": 0, "failed": 0, "stale": 0}
        for r in self.qa(f"""SELECT cr.qc_status AS s, COUNT(*) AS n FROM creatives cr JOIN campaigns c ON c.id=cr.campaign_id
                             JOIN profiles p ON p.brand_id=c.brand_id WHERE p.synthetic=0 AND cr.created_at>=? GROUP BY cr.qc_status""", (since,)):
            qc[r["s"]] = r["n"]
        rep["qc"] = qc
        # zamanlanmış işler: son durum sayıları
        jobs: dict = {}
        for p in self.qa("SELECT jobs_json FROM profiles WHERE synthetic=0"):
            for j in jload(p["jobs_json"], []) or []:
                t = str(j.get("job_type") or "other")
                t = t if FB.SAFE_TOKEN.match(t) else "other"
                s = str(j.get("last_status") or "never")
                s = s if s in ("ok", "failed", "skipped", "reconciled", "never") else "other"
                jobs.setdefault(t, {}).setdefault(s, 0)
                jobs[t][s] += 1
        rep["jobs"] = jobs
        # araç hataları (PostToolUseFailure kayıtları): yalnızca araç grubu ve hata türü; hata metni pakete girmez
        errs = {"count": 0, "by_tool": {}, "by_kind": {}}
        errs_detail: list = []
        logs = self.data_dir / "logs"
        for f in sorted(logs.glob("kullanim-hatasi-*.json")) if logs.exists() else []:
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            try:
                t = parse_iso(str(rec.get("time") or ""))
            except ValueError:
                t = None
            if t is None or (now - t).days > int(period_days):
                continue
            errs["count"] += 1
            tb, ek = FB.tool_bucket(rec.get("tool")), FB.error_kind(str(rec.get("error") or ""))
            errs["by_tool"][tb] = errs["by_tool"].get(tb, 0) + 1
            errs["by_kind"][ek] = errs["by_kind"].get(ek, 0) + 1
            errs_detail.append((tb, ek))
        rep["errors"] = errs
        rep["imzalar"] = self._feedback_signatures(since, real, errs_detail)
        FB.assert_anonymous(rep)
        return rep

    def _feedback_signatures(self, since: str, real: str, errs_detail: list) -> list[dict]:
        """Hata defterinin imzaları (2.8.0): aşama · sinyal · kod · senaryo hücresi → kaç kez. Admin tarafındaki okuyucu
        (evals/defter_oku.py) bunlarla eval vakası ve sürüm karşılaştırması çıkarır. Serbest metin yok; kodlar SAFE_TOKEN'dan geçer."""
        by_camp, by_prof = self._feedback_cells()
        agg: dict = {}

        def add(stage, signal, code, cell, n=1):
            stage = str(stage or "-")
            code = str(code or "-")
            if not (FB.SAFE_TOKEN.match(stage) and FB.SAFE_TOKEN.match(code)):
                code = "other"
            k = (stage, signal, code, cell or "Px.Ux")
            agg[k] = agg.get(k, 0) + int(n)

        def cell_of(r):
            return by_camp.get(r["campaign_id"]) or by_prof.get(r["profile_id"]) or "Px.Ux"

        for r in self.qa(f"SELECT stage, decision, campaign_id, profile_id FROM decisions WHERE profile_id IN {real} AND created_at>=? "
                         f"AND decision IN ('back','correction')", (since,)):
            if r["stage"]:
                add(r["stage"], "geri_donuldu" if r["decision"] == "back" else "duzeltme_istendi", "-", cell_of(r))
        for r in self.qa(f"SELECT stage, campaign_id, profile_id FROM decisions WHERE profile_id IN {real} AND created_at>=? "
                         f"AND decision='approved' AND note LIKE '%kalan taslak sorunu:%'", (since,)):
            add(r["stage"], "sorunla_onaylandi", "-", cell_of(r))
        now = utcnow()
        for r in self.qa(f"SELECT stage, status, started_at, finished_at, campaign_id, profile_id FROM stage_runs WHERE profile_id IN {real} "
                         f"AND stale=0 AND status IN ('running','awaiting_gate')"):
            t = parse_iso(r["finished_at"] or r["started_at"])
            if t is not None and (now - t).total_seconds() / 86400 >= 3:
                add(r["stage"], "takildi", r["status"], cell_of(r))
        for r in self.qa(f"SELECT stage, round, verdict, issues_json, campaign_id, profile_id FROM draft_checks WHERE profile_id IN {real} "
                         f"AND created_at>=? AND verdict='fail' AND round>=?", (since, DR.MAX_DRAFT_ROUNDS)):
            for i in jload(r["issues_json"], []) or []:
                if i.get("severity") == "critical":
                    add(r["stage"], "taslak_son_tur_kaldi", f"{i.get('code')}", cell_of(r))
        for r in self.qa(f"""SELECT cr.campaign_id AS campaign_id, p.id AS profile_id FROM creatives cr JOIN campaigns c ON c.id=cr.campaign_id
                             JOIN profiles p ON p.brand_id=c.brand_id WHERE p.synthetic=0 AND cr.created_at>=? AND cr.qc_status='failed'""", (since,)):
            add("QC", "kreatif_red", "-", cell_of(r))
        for tb, ek in errs_detail:
            add("-", "arac_hatasi", f"{tb}:{ek}", "-")
        out = [{"asama": k[0], "sinyal": k[1], "kod": k[2], "hucre": k[3], "n": n} for k, n in agg.items()]
        out.sort(key=lambda x: (-x["n"], x["asama"], x["sinyal"], x["kod"], x["hucre"]))
        return out[:80]

    def feedback_preview(self, period_days: int = 90) -> dict:
        """Paketin tam içeriği ve sade özeti; kullanıcıya gösterilir. Hiçbir şey yazılmaz."""
        rep = self._feedback_build(period_days)
        return {"report": rep, "summary": FB.summary_lines(rep),
                "next": "Kullanıcıya sade dille sor: \"Bunu hata defterine yazıp geliştiriciye gönderelim mi? Defterde adın, markan, "
                        "ürünlerin ya da tutarların yer almaz.\" Özeti madde madde göster; isterse defterin tamamını da göster. "
                        "\"Evet\" derse feedback_export(approval_text=<kullanıcının sözü>). \"Hayır\" derse hiçbir şey yazma ve işe devam et. "
                        "'Paket', 'önizleme', 'dışa aktarma' gibi terimler kullanma."}

    def feedback_export(self, approval_text: str, period_days: int = 90) -> dict:
        """Kullanıcının açık onayıyla paketi <data_dir>/logs/geri-bildirim/ altına yazar (atomik). Gönderim yapılmaz."""
        if not approval_text or not approval_text.strip():
            raise AdMemoryError("geri bildirim paketi yalnızca kullanıcının açık onayıyla yazılır (approval_text boş olamaz)")
        rep = self._feedback_build(period_days)
        out_dir = self.data_dir / "logs" / "hata-defteri"  # 2.8.0: müşterinin göreceği ad ("hata defteri"); eski klasör okunur kalır
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"hata-defteri-{rep['created_on']}.json"
        atomic_write(path, json.dumps(rep, ensure_ascii=False, indent=2))
        with self.tx():
            self._journal_insert(None, None, "feedback_export", f"Hata defteri yazıldı (son {rep['period_days']} gün); kullanıcı onayıyla.",
                                 {"sha256": sha256_file(path), "approval": approval_text.strip()[:200]}, None, None)
        return {"path": str(path), "sha256": sha256_file(path), "summary": FB.summary_lines(rep),
                "next": "Kullanıcıya şöyle söyle: \"Hata defterine yazdım. Dosya burada: <yol>. Bu dosyayı bize e-postayla ya da "
                        "WhatsApp'tan göndermen yeterli.\" Dosyayı plugin kendisi göndermez; bunu da açıkça söyle."}
