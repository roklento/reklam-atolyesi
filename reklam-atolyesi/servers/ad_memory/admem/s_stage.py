"""Kampanya, tur ve aşama makinesi (spec 4.1–4.4, 8.3)."""
from __future__ import annotations

import datetime as dt
import math
from pathlib import Path
from typing import Any

from . import stages as ST
from .util import AdMemoryError, est_tokens, jdump, jload, now_iso, parse_iso, sha256_file, slugify, utcnow

CYCLE_FIELDS = {"adset_budget_daily", "test_budget", "test_days", "cycle_days", "plan_day", "shoot_start", "launch_at",
                "test_start", "test_end", "decision_due_at", "decision_at", "meta_test_id", "structure_detected",
                "structure_evidence_json", "measurement_json", "priors_snapshot_json", "budget_plan_json",
                "risk_limits_json", "calendar_json", "status"}
CHECKPOINT_MAX_TOKENS = 600  # ~400 hedef; yapılandırılmış alanlarla küçük pay (8.3)


class StageMixin:
    # --- kampanya --------------------------------------------------------------
    def campaign_create(self, profile_id: int, product_id: int, name: str, goal: str | None = None,
                        result_type: str | None = None, season: str | None = None, budget_total: float | None = None,
                        budget_total_confirmed: bool = False, mode: str = "full", trial: bool = False,
                        lead_method: str | None = None) -> dict:
        p = self._profile(profile_id)
        if p["status"] != "active" and not (trial and p["status"] == "onboarding" and p["brand_id"]):
            raise AdMemoryError("kampanya açmak için profil tanışması tamamlanmış (active) olmalı (Faz 3, 17.2)")
        prod = self._product(profile_id, product_id)
        if prod["onboarding_status"] != "done" and not trial:
            raise AdMemoryError("ürün tanışması (S00c) tamamlanmamış ürünle gerçek kampanya açılamaz; yalnızca deneme kampanyasında bilerek atlanabilir (17.7)")
        if mode not in ("full", "quick"):
            raise AdMemoryError("mode: full | quick")
        if budget_total is not None and float(budget_total) <= 0:
            raise AdMemoryError("budget_total pozitif olmalı ya da açıkça NULL (sınır yok) bırakılmalı (6.3)")
        if result_type == "purchase":
            self._purchase_signal_required(profile_id)
        self._lead_rules(profile_id, result_type, lead_method)
        slug = slugify(name)
        base, n = slug, 2
        while self.q1("SELECT 1 FROM campaigns WHERE brand_id=? AND slug=?", (p["brand_id"], slug)):
            slug = f"{base}-{n}"
            n += 1
        with self.tx():
            cur = self.ex("""INSERT INTO campaigns(brand_id,product_id,name,slug,goal,result_type,lead_method,season,budget_total,
                             budget_total_confirmed,mode,stage,cycle,trial,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?, 'S01', 1, ?, ?)""",
                          (p["brand_id"], prod["id"], name, slug, goal, result_type, lead_method if result_type == "lead" else None,
                           season, budget_total, 1 if budget_total_confirmed else 0, mode, 1 if trial else 0, now_iso()))
            cid = cur.lastrowid
            cyc = self.ex("INSERT INTO cycles(campaign_id,cycle,status,created_at) VALUES(?,1,'production',?)", (cid, now_iso()))
            if trial and prod["onboarding_status"] == "pending":
                self.ex("UPDATE products SET onboarding_status='skipped_trial' WHERE id=?", (prod["id"],))
            # kampanya açılınca tanışmanın "kaldığımız yer" notları biter (1.4.1); kaldığımız yer artık kampanyadır
            self.ex("""UPDATE resume_state SET closed_at=? WHERE profile_id=? AND campaign_id IS NULL AND origin='interactive'
                       AND closed_at IS NULL""", (now_iso(), profile_id))
        cdir = self.campaign_dir(profile_id, cid)
        for sub in ("edit_plans", "competitive", "footage/raw", "footage/proxy", "footage/graded", "footage/stab",
                    "footage/scenes", "photos/raw", "photos", "analysis", "audio/raw", "audio/music", "audio/vo",
                    "audio/sfx", "audio/stems", "audio/user_vo", "ai", "src", "out", "reports"):
            (cdir / sub).mkdir(parents=True, exist_ok=True)
        return {"campaign": self.q1("SELECT * FROM campaigns WHERE id=?", (cid,)),
                "cycle": self.q1("SELECT * FROM cycles WHERE id=?", (cyc.lastrowid,)), "dir": str(cdir),
                "trial_note": "Ürün tanışması atlandı: brief'e 'ekonomi VARSAYIMSAL' yazılır (17.7)." if trial else None}

    def campaign_dir(self, profile_id: int, campaign_id: int) -> Path:
        c = self._campaign(profile_id, campaign_id)
        return self.profile_dir(profile_id) / "campaigns" / c["slug"]

    def campaign_get(self, profile_id: int, campaign_id: int) -> dict:
        c = self._campaign(profile_id, campaign_id)
        cycles = self.qa("SELECT * FROM cycles WHERE campaign_id=? ORDER BY cycle", (c["id"],))
        runs = self.qa("SELECT id,stage,cycle_id,output_version,status,stale,started_at,finished_at FROM stage_runs WHERE campaign_id=? ORDER BY id",
                       (c["id"],))
        return {"campaign": c, "cycles": cycles, "stage_runs": runs, "dir": str(self.campaign_dir(profile_id, c["id"]))}

    def campaign_list(self, profile_id: int, include_closed: bool = False) -> dict:
        bid = self._brand_id(profile_id, required=False)
        if not bid:
            return {"campaigns": []}
        sql = "SELECT * FROM campaigns WHERE brand_id=?" + ("" if include_closed else " AND status='active'")
        return {"campaigns": self.qa(sql + " ORDER BY id", (bid,))}

    def _purchase_signal_required(self, profile_id: int) -> None:
        """Satış sonuçlu kampanya için Meta'nın satışı görmesi gerekir (1.4.7): görmezse Meta tıklayanı bulur, alanı değil."""
        sig = self.meta_signal_get(profile_id)["meta_signal"]
        if sig.get("status") != "purchase_seen":
            raise AdMemoryError("satış (purchase) sonucu için Meta'nın son 7 günde Purchase olayı aldığı doğrulanmadı (meta_signal: "
                                f"{sig.get('status', 'unknown')}). Yollar: piksel kur, satışları KVKK dayanağıyla Events Manager'a yükle, ya da "
                                "bilinçli olarak messaging/link_click/profile_visit ya da anlık formla lead sonucuna optimize et; satışlar yine sales_add ile izlenir.")

    def _lead_rules(self, profile_id: int, result_type: str | None, lead_method: str | None) -> None:
        """Aday sonucu (1.5.0): yol zorunlu; sitedeki form için Meta'nın Lead olayını görmesi gerekir (satıştaki kuralın aynısı)."""
        from .s_lead import LEAD_METHODS
        if result_type != "lead":
            if lead_method is not None:
                raise AdMemoryError("lead_method yalnızca result_type='lead' ile verilir")
            return
        if lead_method not in LEAD_METHODS:
            raise AdMemoryError(f"aday sonucu yol ister (lead_method): {' | '.join(LEAD_METHODS)} — instant_form: Meta anlık form (piksel "
                                "gerekmez) · website: sitedeki form (Meta'nın Lead olayını görmesi gerekir) · call: arama")
        if lead_method == "website" and not self.meta_signal_get(profile_id)["meta_signal"].get("lead_seen"):
            raise AdMemoryError("sitedeki form için Meta'nın son 7 günde Lead olayı aldığı doğrulanmadı (meta_signal.lead_seen). Yollar: "
                                "anlık form (instant_form) kullan, Lead olayını kur (veri bağlantısı), ya da mesaj sonucuna optimize et.")

    def campaign_update(self, profile_id: int, campaign_id: int, **fields: Any) -> dict:
        c = self._campaign(profile_id, campaign_id)
        allowed = {"goal", "result_type", "lead_method", "season", "budget_total", "budget_total_confirmed", "test_structure", "mode",
                   "status", "name"}
        bad = set(fields) - allowed
        if bad:
            raise AdMemoryError(f"campaign_update alanı desteklenmiyor: {', '.join(sorted(bad))} (stage/cycle yalnızca aşama makinesiyle)")
        if "budget_total" in fields and fields["budget_total"] is not None and float(fields["budget_total"]) <= 0:
            raise AdMemoryError("budget_total pozitif ya da NULL olmalı")
        if "mode" in fields and fields["mode"] == "quick" and ST.index(c["stage"]) > ST.index("S03"):
            raise AdMemoryError("hızlı tur yolu S03 kapısından önce seçilir (4.2)")
        if fields.get("result_type") == "purchase" and c["result_type"] != "purchase":
            self._purchase_signal_required(profile_id)
        if "result_type" in fields or "lead_method" in fields:
            rt = fields.get("result_type", c["result_type"])
            lm = fields.get("lead_method", c.get("lead_method") if rt == "lead" else None)
            self._lead_rules(profile_id, rt, lm)
            if rt != "lead":
                fields["lead_method"] = None
        if fields.get("test_structure") == "ab_test":
            raise AdMemoryError("ab_test yapısı yalnızca okunmuş Meta A/B çalışmasıyla tur kaydına yazılır (cycle_set structure_detected='ab_test')")
        sets = {k: v for k, v in fields.items()}
        if "budget_total" in sets and "budget_total_confirmed" not in sets:
            sets["budget_total_confirmed"] = 1
        with self.tx():
            self.ex(f"UPDATE campaigns SET {', '.join(f'{k}=?' for k in sets)} WHERE id=?", (*sets.values(), c["id"]))
        return self.q1("SELECT * FROM campaigns WHERE id=?", (c["id"],))

    def _current_cycle(self, campaign: dict) -> dict:
        return self.q1("SELECT * FROM cycles WHERE campaign_id=? AND cycle=?", (campaign["id"], campaign["cycle"]))

    # --- tur ----------------------------------------------------------------
    def cycle_set(self, profile_id: int, cycle_id: int, correction_reason: str | None = None, **fields: Any) -> dict:
        cy = self._cycle(profile_id, cycle_id)
        bad = set(fields) - CYCLE_FIELDS
        if bad:
            raise AdMemoryError(f"cycle_set alanı desteklenmiyor: {', '.join(sorted(bad))} (launched_at yalnızca launch_confirm ile)")
        if cy["launched_at"]:
            for k in ("test_start", "launch_at"):
                if k in fields and cy[k] and fields[k] != cy[k] and not correction_reason:
                    raise AdMemoryError(f"{k} gerçekleşmiş bir tarih; geriye dönük değiştirilmez (4.4). Kaynak hatası düzeltmesiyse correction_reason verin.")
        if "priors_snapshot_json" in fields and cy["priors_snapshot_json"] and cy["status"] != "production":
            raise AdMemoryError("turun önselleri dondurulmuş; ölçüm sırasında değiştirilemez (6.6)")
        if "risk_limits_json" in fields and fields["risk_limits_json"] is not None:
            self._validate_risk_limits(fields["risk_limits_json"])
        if "structure_detected" in fields and fields["structure_detected"] not in (None, "bootstrap", "creative_test", "ab_test", "deviated", "unverified"):
            raise AdMemoryError("structure_detected: bootstrap | creative_test | ab_test | deviated | unverified")
        if fields.get("structure_detected") in ("creative_test", "bootstrap", "ab_test") and not (fields.get("structure_evidence_json") or cy["structure_evidence_json"]):
            raise AdMemoryError("yapı kaynak kanıtı olmadan doğrulanmış sayılmaz; kanıt yoksa 'unverified' (6.3)")
        if fields.get("structure_detected") == "ab_test":
            # Meta A/B testi (1.5.0): çalışma kimliği salt okuma aracıyla okunmuş olmalı (ads_experiment_abtest_get_test)
            ev = jload(fields.get("structure_evidence_json") or cy["structure_evidence_json"], {}) or {}
            if not (fields.get("meta_test_id") or cy["meta_test_id"]) or not ev.get("study_read"):
                raise AdMemoryError("ab_test için meta_test_id ve kanıtta okunmuş çalışma (study_read: hücreler, tarih, değişken) gerekli")
        if "budget_plan_json" in fields:
            # Ölçekleme katmanı kaydı yalnızca scale_layer_set ile değişir; S02'nin yeni bütçe planı onu silmez (1.4.6).
            new_bp = jload(fields["budget_plan_json"], None) if isinstance(fields["budget_plan_json"], str) else fields["budget_plan_json"]
            old_layer = (jload(cy["budget_plan_json"], {}) or {}).get("scale_layer")
            if isinstance(new_bp, dict):
                if "scale_layer" in new_bp and new_bp["scale_layer"] != old_layer:
                    raise AdMemoryError("ölçekleme katmanı (scale_layer) cycle_set ile değiştirilmez; scale_layer_set kullanın")
                if old_layer is not None:
                    new_bp = {**new_bp, "scale_layer": old_layer}
                self._validate_round_mode(new_bp, int(cy["cycle"]))
                fields["budget_plan_json"] = new_bp
            elif new_bp is None and old_layer is not None:
                fields["budget_plan_json"] = {"scale_layer": old_layer}
        for k in list(fields):
            if k.endswith("_json") and fields[k] is not None and not isinstance(fields[k], str):
                fields[k] = jdump(fields[k])
        if not fields:
            return cy
        with self.tx():
            self.ex(f"UPDATE cycles SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?", (*fields.values(), cy["id"]))
            if "structure_detected" in fields:
                self.ex("UPDATE campaigns SET test_structure=? WHERE id=?", (fields["structure_detected"], cy["campaign_id"]))
            if correction_reason:
                self._decision_insert(profile_id, cy["campaign_id"], cy["id"], None, None, None, None, "correction",
                                      f"tur alanı düzeltmesi: {', '.join(fields)} — {correction_reason}", "user")
        return self.q1("SELECT * FROM cycles WHERE id=?", (cy["id"],))

    @staticmethod
    def _validate_risk_limits(rl: Any) -> None:
        data = jload(rl, None) if isinstance(rl, str) else rl
        if not isinstance(data, dict) or not isinstance(data.get("per_ad"), dict):
            raise AdMemoryError("risk_limits_json {'per_ad': {'amount':..,'currency':..,'scope':'ad_launch_to_stop','approved_at':..,'note':..}, 'mapping': {...}} biçiminde olmalı (6.3)")
        pa = data["per_ad"]
        try:
            amt = float(pa.get("amount"))
        except (TypeError, ValueError):
            raise AdMemoryError("zarar-risk sınırı tutarı sayı olmalı")
        if not math.isfinite(amt) or amt <= 0:
            raise AdMemoryError("zarar-risk sınırı sonlu ve pozitif olmalı (6.3)")
        if pa.get("scope") != "ad_launch_to_stop":
            raise AdMemoryError("risk sınırı kapsamı 'ad_launch_to_stop' olmalı (6.3)")
        if not pa.get("currency") or not pa.get("approved_at"):
            raise AdMemoryError("risk sınırı para birimi ve onay zamanı taşımalı (açık kullanıcı onayı)")

    # --- devam notu (8.3) -------------------------------------------------------
    def _scope_key(self, profile_id: int, campaign_id: int | None, cycle_id: int | None, scope_key: str | None = None) -> str:
        if cycle_id is not None:
            return f"cycle:{int(cycle_id)}"
        if scope_key:
            if not (scope_key.startswith("profile:") or scope_key.startswith("product:")):
                raise AdMemoryError("scope_key: profile:<id> | product:<id>")
            if scope_key.startswith("product:"):
                self._product(profile_id, int(scope_key.split(":")[1]))
            elif int(scope_key.split(":")[1]) != int(profile_id):
                raise AdMemoryError("scope_key profili oturumun profiliyle aynı olmalı")
            return scope_key
        return f"profile:{int(profile_id)}"

    def _checkpoint_in_tx(self, profile_id: int, stage: str, state: dict, campaign_id: int | None = None,
                          cycle_id: int | None = None, scope_key: str | None = None, origin: str = "interactive",
                          stage_run_id: int | None = None) -> dict:
        if not isinstance(state, dict):
            raise AdMemoryError("devam notu yapılandırılmış olmalı: {completed_steps, decisions, open_questions, next_step, refs}")
        txt = jdump(state)
        if est_tokens(txt) > CHECKPOINT_MAX_TOKENS:
            raise AdMemoryError(f"devam notu ~400 token'ı aşıyor ({est_tokens(txt)}); görüşmenin tamamı değil, karar kimlikleri ve sıradaki soru yazılır (8.3)")
        sk = self._scope_key(profile_id, campaign_id, cycle_id, scope_key)
        cur = self.q1("SELECT id FROM resume_state WHERE scope_key=? AND stage=? AND origin=? AND closed_at IS NULL", (sk, stage, origin))
        if cur:
            self.ex("UPDATE resume_state SET state_json=?, updated_at=?, stage_run_id=COALESCE(?, stage_run_id) WHERE id=?",
                    (txt, now_iso(), stage_run_id, cur["id"]))
            rid = cur["id"]
        else:
            rid = self.ex("""INSERT INTO resume_state(profile_id,campaign_id,cycle_id,stage_run_id,stage,scope_key,origin,state_json,updated_at)
                             VALUES(?,?,?,?,?,?,?,?,?)""",
                          (profile_id, campaign_id, cycle_id, stage_run_id, stage, sk, origin, txt, now_iso())).lastrowid
        if campaign_id is None and origin == "interactive":
            # Profil düzeyinde (tanışma) tek "kaldığımız yer" vardır (1.4.1): yeni not öncekileri kapatır; tanışma sıralı ilerler ve
            # S00a'da kaydedilip S00b/S00c'de unutulan not "açık devam notu" olarak kalmaz.
            self.ex("""UPDATE resume_state SET closed_at=? WHERE profile_id=? AND campaign_id IS NULL AND origin='interactive'
                       AND closed_at IS NULL AND id!=?""", (now_iso(), profile_id, rid))
        return self.q1("SELECT * FROM resume_state WHERE id=?", (rid,))

    def checkpoint_save(self, profile_id: int, stage: str, state: dict, campaign_id: int | None = None,
                        cycle_id: int | None = None, scope_key: str | None = None, origin: str = "interactive") -> dict:
        self._profile(profile_id)
        if campaign_id is not None:
            self._campaign(profile_id, campaign_id)
        if cycle_id is not None:
            self._cycle(profile_id, cycle_id, campaign_id)
        if origin not in ("interactive", "job"):
            raise AdMemoryError("origin: interactive | job (otomatik takip etkileşimli notun üzerine yazmaz)")
        with self.tx():
            return self._checkpoint_in_tx(profile_id, stage, state, campaign_id, cycle_id, scope_key, origin)

    def checkpoint_get(self, profile_id: int, campaign_id: int | None = None, cycle_id: int | None = None,
                       stage: str | None = None) -> dict:
        self._profile(profile_id, allow_archived=True)
        sql = "SELECT * FROM resume_state WHERE profile_id=? AND closed_at IS NULL"
        args: list[Any] = [profile_id]
        if campaign_id is not None:
            sql += " AND campaign_id=?"
            args.append(campaign_id)
        if cycle_id is not None:
            sql += " AND cycle_id=?"
            args.append(cycle_id)
        if stage:
            sql += " AND stage=?"
            args.append(stage)
        return {"open": self.qa(sql + " ORDER BY updated_at DESC", tuple(args))}

    def checkpoint_close(self, profile_id: int, stage: str, summary: str, campaign_id: int | None = None,
                         cycle_id: int | None = None, scope_key: str | None = None, origin: str = "interactive") -> dict:
        self._profile(profile_id)
        with self.tx():
            return self._checkpoint_close_in_tx(profile_id, stage, summary, campaign_id, cycle_id, scope_key, origin)

    def _checkpoint_close_in_tx(self, profile_id, stage, summary, campaign_id, cycle_id, scope_key, origin="interactive"):
        sk = self._scope_key(profile_id, campaign_id, cycle_id, scope_key)
        cur = self.q1("SELECT * FROM resume_state WHERE scope_key=? AND stage=? AND origin=? AND closed_at IS NULL", (sk, stage, origin))
        if cur:
            self.ex("UPDATE resume_state SET closed_at=? WHERE id=?", (now_iso(), cur["id"]))
        if summary:
            self._journal_insert(profile_id, campaign_id, "stage_summary", f"{stage}: {summary}",
                                 {"stage": stage, "scope_key": sk}, None, None)
        return {"closed": bool(cur), "scope_key": sk, "stage": stage}

    # --- aşama makinesi ------------------------------------------------------
    def _resolve_output(self, profile_id: int, o: dict) -> dict:
        if not isinstance(o, dict) or not o.get("path"):
            raise AdMemoryError("her çıktı {path, sha256?, version?, kind?} olmalı")
        p = Path(o["path"])
        if not p.is_absolute():
            p = self.data_dir / p
        try:
            p.resolve().relative_to(self.data_dir.resolve())
        except ValueError:
            raise AdMemoryError(f"çıktı data_dir dışında: {p}")
        if not p.exists() or not p.is_file():
            raise AdMemoryError(f"çıktı dosyası yok: {p} (eksik dosya tamamlandı sayılmaz)")
        if p.stat().st_size == 0:
            raise AdMemoryError(f"çıktı dosyası boş: {p}")
        h = sha256_file(p)
        if o.get("sha256") and o["sha256"] != h:
            raise AdMemoryError(f"çıktı hash'i uyuşmuyor: {p}")
        return {"path": str(p), "sha256": h, "version": o.get("version"), "kind": o.get("kind")}

    def stage_start(self, profile_id: int, stage: str, campaign_id: int | None = None, cycle_id: int | None = None,
                    scope_key: str | None = None) -> dict:
        self._profile(profile_id)
        if stage in ST.CAMPAIGN_STAGES:
            c = self._campaign(profile_id, campaign_id)
            cy = self._cycle(profile_id, cycle_id, campaign_id)
            if c["stage"] != stage:
                raise AdMemoryError(f"kampanya şu anda {c['stage']} aşamasında; {stage} başlatılamaz (geri dönmek için stage_back)")
            if cy["cycle"] != c["cycle"] and stage not in ("S15", "S16", "S17"):
                raise AdMemoryError("bu tur güncel üretim turu değil")
        elif stage not in ST.ONBOARDING_STAGES:
            raise AdMemoryError(f"bilinmeyen aşama: {stage}")
        sk = self._scope_key(profile_id, campaign_id, cycle_id, scope_key)
        with self.tx():
            run = self.q1("SELECT * FROM stage_runs WHERE scope_key=? AND stage=? AND status='running' AND stale=0 ORDER BY output_version DESC LIMIT 1",
                          (sk, stage))
            if run:
                return run
            v = (self.q1("SELECT MAX(output_version) AS v FROM stage_runs WHERE scope_key=? AND stage=?", (sk, stage)) or {}).get("v") or 0
            rid = self.ex("""INSERT INTO stage_runs(profile_id,campaign_id,stage,cycle_id,scope_key,output_version,status,started_at)
                             VALUES(?,?,?,?,?,?, 'running', ?)""", (profile_id, campaign_id, stage, cycle_id, sk, v + 1, now_iso())).lastrowid
        return self.q1("SELECT * FROM stage_runs WHERE id=?", (rid,))

    def stage_complete(self, profile_id: int, stage: str, outputs: list[dict], summary: str,
                       campaign_id: int | None = None, cycle_id: int | None = None, scope_key: str | None = None,
                       skipped_reason: str | None = None, extra: dict | None = None) -> dict:
        """Çıktılar doğrulanır (dosya var, boş değil, hash), kayıt ve devam notunun kapanışı tek işlemde (4.2)."""
        p = self._profile(profile_id)
        if stage == "W":
            raise AdMemoryError("W bekleme durumudur; 'çekim tamam' için shoot_mark_done kullanılır")
        skipped = skipped_reason is not None
        if skipped:
            if stage not in ST.SKIPPABLE_ON_REQUEST and not (stage == "S00b"):
                raise AdMemoryError(f"{stage} atlanamaz (yalnızca kullanıcı açıkça isterse S01b; hızlı turda S04–S06 S03 kapısında)")
            if not skipped_reason.strip():
                raise AdMemoryError("atlama gerekçesi zorunlu")
            resolved = []
        else:
            if not outputs:
                raise AdMemoryError("aşama boş çıktıyla tamamlanmaz (4.2)")
            resolved = [self._resolve_output(profile_id, o) for o in outputs]
        c = cy = None
        if stage in ST.CAMPAIGN_STAGES:
            c = self._campaign(profile_id, campaign_id)
            cy = self._cycle(profile_id, cycle_id, campaign_id)
            if c["stage"] != stage:
                raise AdMemoryError(f"kampanya {c['stage']} aşamasında; {stage} tamamlanamaz")
            if stage == "S15" and not cy["launched_at"]:
                raise AdMemoryError("S15 yalnızca gerçek yayın kaydı (launch_confirm) sonrası")
            if stage == "S02":
                self._s02_preconditions(profile_id, c, cy)
        elif stage not in ST.ONBOARDING_STAGES:
            raise AdMemoryError(f"bilinmeyen aşama: {stage}")
        if stage == "S00c" and not (scope_key or "").startswith("product:"):
            raise AdMemoryError("S00c scope_key='product:<id>' ister (ürün başına tanışma)")
        sk = self._scope_key(profile_id, campaign_id, cycle_id, scope_key)
        gated = ST.is_gated(stage) and not skipped
        with self.tx():
            if c and (self.q1("SELECT stage FROM campaigns WHERE id=?", (c["id"],)) or {}).get("stage") != stage:
                raise AdMemoryError("kampanya bu arada başka aşamaya geçti (başka oturum); aşama tamamlanmadı")  # 2.0.0: işlem içinde yeniden
            run = self.q1("SELECT * FROM stage_runs WHERE scope_key=? AND stage=? AND status='running' AND stale=0 ORDER BY output_version DESC LIMIT 1",
                          (sk, stage))
            outputs_json = {"files": resolved, "summary": summary, "extra": extra or {}}
            if skipped:
                outputs_json["skipped_reason"] = skipped_reason
            status = "skipped" if skipped else ("awaiting_gate" if gated else "done")
            if run:
                self.ex("UPDATE stage_runs SET status=?, finished_at=?, outputs_json=? WHERE id=?",
                        (status, now_iso(), jdump(outputs_json), run["id"]))
                rid = run["id"]
            else:
                v = (self.q1("SELECT MAX(output_version) AS v FROM stage_runs WHERE scope_key=? AND stage=?", (sk, stage)) or {}).get("v") or 0
                rid = self.ex("""INSERT INTO stage_runs(profile_id,campaign_id,stage,cycle_id,scope_key,output_version,status,started_at,finished_at,outputs_json)
                                 VALUES(?,?,?,?,?,?,?,?,?,?)""",
                              (profile_id, campaign_id, stage, cycle_id, sk, v + 1, status, now_iso(), now_iso(), jdump(outputs_json))).lastrowid
            # yeni sürüm eski onayları geçersiz kılar: aynı aşamanın önceki awaiting_gate sürümleri eskir
            self.ex("UPDATE stage_runs SET stale=1 WHERE scope_key=? AND stage=? AND id!=? AND status='awaiting_gate'", (sk, stage, rid))
            if skipped:
                self._decision_insert(profile_id, campaign_id, cycle_id, rid, None, stage, None, "skipped", skipped_reason, "user")
            if not gated:
                self._advance(profile_id, stage, c, cy, sk, rid)
            self._checkpoint_close_in_tx(profile_id, stage, summary, campaign_id, cycle_id, scope_key)
        run = self.q1("SELECT * FROM stage_runs WHERE id=?", (rid,))
        out = {"stage_run": run, "status": status}
        if gated:
            out["gate"] = ST.GATES[stage]
            out["note"] = "Kapı: kullanıcının açık onayı gerekir (gate_approve). Değişiklik isteği onay değildir."
        return out

    @staticmethod
    def _validate_round_mode(bp: dict, cycle_no: int) -> None:
        """Tur modu (1.9.0): explore (varsayılan; keşif konseptleri farklı alıcıya) | funnel (huni turu: aynı alıcı, farklı aşama).
        Huni turu bilerek seçilir: alıcı ve dayanağı (kazanan konsept, kanıtlanmış alıcı ya da kullanıcının gerekçesi) yazılır. İlk turda
        açılmaz: tek sette Meta bütçeyi satışa en yakın mesaja akıtır, aşamalar adil karşılaştırılmaz; 2. turdan itibaren kreatif test
        bütçeyi test reklamlarına eşit böler (resmi, ref-legal-tr-meta §7)."""
        mode = bp.get("round_mode")
        if mode is None:
            return
        if mode not in ("explore", "funnel"):
            raise AdMemoryError("round_mode: explore | funnel")
        if mode == "funnel" and cycle_no <= 1:
            raise AdMemoryError("huni turu ilk turda açılmaz: tek sette Meta bütçeyi eşit dağıtmaz, satışa en yakın mesaj öne geçer. "
                                "2. turdan itibaren kreatif test (bütçe test reklamlarına eşit bölünür) yapısında açılır")
        if mode == "funnel":
            fu = bp.get("funnel") or {}
            if not (isinstance(fu, dict) and str(fu.get("buyer") or "").strip() and str(fu.get("basis") or "").strip()):
                raise AdMemoryError("huni turu için budget_plan_json.funnel = {buyer, basis, user_said?} gerekir: hangi alıcıya, neden "
                                    "(kazanan konsept, kanıtlanmış alıcı ya da kullanıcının gerekçesi)")

    def _s02_preconditions(self, profile_id: int, c: dict, cy: dict) -> None:
        bp = jload(cy["budget_plan_json"], None) or {}
        if not any(k != "scale_layer" for k in bp):
            raise AdMemoryError("S02 için bütçe planı (budget_plan_json) yazılmalı (6.3)")

    def _s02_blockers(self, c: dict, cy: dict) -> list[str]:
        out = []
        bp = jload(cy["budget_plan_json"], {}) or {}
        if not cy["risk_limits_json"]:
            out.append("onaylı zarar-risk sınırı (risk_limits_json) yok (6.3)")
        if bp.get("allowed_test_ads", 0) < 2:
            out.append("test bütçesi iki reklama bile yetmiyor; üretim bekler (6.3)")
        if c["budget_total"] is not None and bp.get("fits_total_budget") is not True:
            out.append("toplam harcama planı kalan bütçeyi aşıyor ya da doğrulanmadı (6.3)")
        layer = bp.get("scale_layer")
        if layer and layer.get("status", "active") == "active":
            planned = (bp.get("spend_projection") or {}).get("scale_layer_daily")
            if planned is None or float(planned) + 1e-9 < float(layer.get("daily_budget") or 0):
                out.append("ölçekleme katmanının günlük bütçesi toplam harcama planına girmedi (budget.py scale_layer_daily) (6.3)")
        if not cy["strategy_json"]:
            out.append("stratejik yön (strategy_save) kaydedilmedi (4.6)")
        cal = jload(cy["calendar_json"], {}) or {}
        if not (cy["test_days"] and cy["cycle_days"]) and not cal:
            out.append("tur takvimi (test_days, cycle_days) hesaplanmadı (4.4)")
        return out

    def _gate_blockers(self, profile_id: int, run: dict) -> list[str]:
        stage = run["stage"]
        if stage not in ST.CAMPAIGN_STAGES:
            return []
        c = self.q1("SELECT * FROM campaigns WHERE id=?", (run["campaign_id"],))
        cy = self.q1("SELECT * FROM cycles WHERE id=?", (run["cycle_id"],))
        out: list[str] = []
        if stage == "S02":
            out += self._s02_blockers(c, cy)
        elif stage == "S03":
            sel = self.qa("SELECT * FROM concepts WHERE cycle_id=? AND decision IN ('accepted','merged')", (cy["id"],))
            if not sel:
                out.append("görüşmede seçilmiş (accepted/merged) konsept yok")
            for k in sel:
                if not self.q1("SELECT 1 FROM hooks WHERE concept_id=? AND decision IN ('accepted','merged')", (k["id"],)):
                    out.append(f"konsept {k['code']} için seçilmiş hook yok")
                if k["competitive_role"] in ("proven", "counter"):
                    dc = jload(k["distance_check_json"], None)
                    if not dc or not dc.get("passed"):
                        out.append(f"konsept {k['code']} rakipten türüyor; uzaklık kuralı (concept_distance_check) geçmedi (10)")
                if k["hypothesis_id"] is None:
                    out.append(f"konsept {k['code']} için hipotez kaydı yok (4.3 adım 7)")
            bp = jload(cy["budget_plan_json"], {}) or {}
            cap = bp.get("allowed_test_ads")
            if cap is not None:
                n_test = 0
                for k in sel:
                    n_test += len(self.qa("SELECT 1 FROM hooks WHERE concept_id=? AND decision IN ('accepted','merged') AND reserve=0", (k["id"],)))
                if n_test > cap:
                    out.append(f"seçilen test reklamı sayısı {n_test} > S02 kreatif tavanı {cap} (6.3); fazlası yedek işaretlenmeli")
            # Test hakkı önce farklı alıcılara konuşan farklı fikirlere: tek test açılışı, farklı alıcı, çeşitlilik eksenleri (4.3, 4.7; 1.4.5)
            out += self._s03_portfolio_check(cy["id"])["issues"]
            # Mesaj kartı (1.9.0): her test konsepti "kime, hangi düşünceyi değiştirmek için, hangi kanıtla" sorusunu yanıtlar
            for k in sel:
                if k["message_json"] is None and self.q1("SELECT 1 FROM hooks WHERE concept_id=? AND decision IN ('accepted','merged') "
                                                         "AND reserve=0", (k["id"],)):
                    out.append(f"konsept {k['code']} için mesaj kartı (concept_upsert message: aşama, değişecek düşünce, odak, kanıt, "
                               "beklenen aksiyon) yok")
        elif stage == "S13":
            bad = self.qa("SELECT creative_key, format, qc_status FROM creatives WHERE cycle_id=? AND delivery_role='test' AND qc_status!='passed'", (cy["id"],))
            if bad:
                out.append("QC'den geçmemiş test kreatifleri: " + ", ".join(f"{b['creative_key']}/{b['format']}({b['qc_status']})" for b in bad[:6]))
        elif stage == "S14":
            out += self._s02_blockers(c, cy)
            rl = jload(cy["risk_limits_json"], {}) or {}
            mapping = rl.get("mapping") or {}
            keys = [r["creative_key"] for r in self.qa("SELECT DISTINCT creative_key FROM creatives WHERE cycle_id=? AND delivery_role='test'", (cy["id"],))]
            if not keys:
                out.append("yayınlanacak test kreatifi yok")
            missing = [k for k in keys if k not in mapping]
            if missing:
                out.append("risk sınırı eşlemesi eksik creative_key: " + ", ".join(missing[:8]))
            bp = jload(cy["budget_plan_json"], {}) or {}
            if bp.get("allowed_test_ads") is not None and len(keys) > bp["allowed_test_ads"]:
                out.append(f"test reklamı sayısı {len(keys)} > tavan {bp['allowed_test_ads']} (5.18): fazlası yedekte kalmalı")
        return out

    def gate_approve(self, profile_id: int, stage_run_id: int, output_version: int, approval_text: str,
                     cycle_id: int | None = None, note: str | None = None, checkpoint: dict | None = None) -> dict:
        """Onay stage_run_id + cycle_id + output_version'a bağlıdır (4.2); kullanıcının açık ifadesi zorunlu."""
        self._profile(profile_id)
        if not approval_text or not approval_text.strip():
            raise AdMemoryError("kapı yalnızca kullanıcının açık onayıyla geçilir; onay ifadesi (approval_text) boş olamaz")
        run = self.q1("SELECT * FROM stage_runs WHERE id=?", (int(stage_run_id),))
        if not run or run["profile_id"] != int(profile_id):
            raise AdMemoryError("aşama kaydı bu profile ait değil")
        if run["status"] != "awaiting_gate":
            raise AdMemoryError(f"bu aşama kapıda değil (durum: {run['status']})")
        if run["stale"]:
            raise AdMemoryError("bu çıktı sürümü eskimiş; güncel sürüm onaylanmalı")
        if int(output_version) != run["output_version"]:
            raise AdMemoryError(f"onay sürümü ({output_version}) güncel çıktı sürümü ({run['output_version']}) değil; eski onay kullanılamaz")
        latest = self.q1("SELECT MAX(output_version) AS v FROM stage_runs WHERE scope_key=? AND stage=?", (run["scope_key"], run["stage"]))["v"]
        if latest != run["output_version"]:
            raise AdMemoryError("daha yeni bir çıktı sürümü var; bu sürümün onayı geçersiz")
        if run["stage"] in ST.CAMPAIGN_STAGES:
            if cycle_id is None or int(cycle_id) != run["cycle_id"]:
                raise AdMemoryError("onay turu (cycle_id) aşama kaydının turuyla aynı olmalı; başka turun onayı kullanılamaz")
        blockers = self._gate_blockers(profile_id, run)
        if blockers:
            raise AdMemoryError("kapı geçilemez: " + "; ".join(blockers))
        c = self.q1("SELECT * FROM campaigns WHERE id=?", (run["campaign_id"],)) if run["campaign_id"] else None
        cy = self.q1("SELECT * FROM cycles WHERE id=?", (run["cycle_id"],)) if run["cycle_id"] else None
        with self.tx():
            # 2.0.0: denetim işlem içinde yinelenir; iki oturum aynı kapıyı aynı anda onaylarsa ikincisi aşamayı iki kez ilerletmez
            # (S17'de iki yeni tur açılırdı)
            if self.ex("UPDATE stage_runs SET status='done', finished_at=COALESCE(finished_at, ?) WHERE id=? AND status='awaiting_gate' AND stale=0",
                       (now_iso(), run["id"])).rowcount != 1:
                raise AdMemoryError("bu kapı az önce başka bir oturumda onaylandı ya da çıktı yenilendi; durum yeniden okunmalı")
            if c and (self.q1("SELECT stage FROM campaigns WHERE id=?", (c["id"],)) or {}).get("stage") != run["stage"]:
                raise AdMemoryError("kampanya bu arada başka aşamaya geçti; onay uygulanmadı")
            did = self._decision_insert(profile_id, run["campaign_id"], run["cycle_id"], run["id"], run["output_version"],
                                        run["stage"], ST.GATES.get(run["stage"]), "approved",
                                        (note + " — " if note else "") + f"onay: «{approval_text.strip()}»", "user")
            nxt = self._advance(profile_id, run["stage"], c, cy, run["scope_key"], run["id"])
            # onaylanan aşamanın kapı görüşmesi sırasında kaydedilmiş notu kapanır (1.4.1); gerekiyorsa aşağıda yeni not yazılır
            self._checkpoint_close_in_tx(profile_id, run["stage"], "", run["campaign_id"], run["cycle_id"],
                                         None if run["campaign_id"] else run["scope_key"])
            if checkpoint:
                self._checkpoint_in_tx(profile_id, nxt or run["stage"], checkpoint, run["campaign_id"],
                                       (self.q1("SELECT id FROM cycles WHERE campaign_id=? AND cycle=(SELECT cycle FROM campaigns WHERE id=?)",
                                                (run["campaign_id"], run["campaign_id"])) or {}).get("id") if run["campaign_id"] else None,
                                       None if run["campaign_id"] else run["scope_key"])
        return {"approved": True, "decision_id": did, "stage": run["stage"], "next_stage": nxt,
                "note": "S14 paket onayı yayın yapıldığı anlamına gelmez; S15 geçişi launch_confirm bekler." if run["stage"] == "S14" else None}

    def _advance(self, profile_id: int, stage: str, c: dict | None, cy: dict | None, scope_key: str, run_id: int) -> str | None:
        if stage == "S00c":
            pid = int(scope_key.split(":")[1])
            self.ex("UPDATE products SET onboarding_status='done' WHERE id=?", (pid,))
            return None
        if stage in ST.ONBOARDING_STAGES:
            return None
        c = self.q1("SELECT * FROM campaigns WHERE id=?", (c["id"],))
        nxt = ST.next_stage(stage, c["mode"])
        if stage == "S03" and c["mode"] == "quick":
            for s in ST.QUICK_SKIPPED:
                v = (self.q1("SELECT MAX(output_version) AS v FROM stage_runs WHERE scope_key=? AND stage=?", (scope_key, s)) or {}).get("v") or 0
                self.ex("""INSERT INTO stage_runs(profile_id,campaign_id,stage,cycle_id,scope_key,output_version,status,started_at,finished_at,outputs_json)
                           VALUES(?,?,?,?,?,?, 'skipped', ?, ?, ?)""",
                        (profile_id, c["id"], s, cy["id"], scope_key, v + 1, now_iso(), now_iso(),
                         jdump({"skipped_reason": "hızlı tur: malzeme profil çekim kütüphanesinden (4.2)"})))
        if stage == "S17":
            self.ex("UPDATE cycles SET status='closed', decision_at=COALESCE(decision_at, ?) WHERE id=?", (now_iso(), cy["id"]))
            new_no = c["cycle"] + 1
            # Ölçekleme katmanı turlar boyunca yaşar: kaydı yeni tura aynen taşınır (bütçe planının geri kalanı S02'de yeniden kurulur).
            layer = (jload(cy["budget_plan_json"], {}) or {}).get("scale_layer")
            self.ex("INSERT INTO cycles(campaign_id,cycle,status,created_at,budget_plan_json) VALUES(?,?, 'production', ?, ?)",
                    (c["id"], new_no, now_iso(), jdump({"scale_layer": layer}) if layer else None))
            self.ex("UPDATE campaigns SET cycle=?, stage='S01', mode='full' WHERE id=?", (new_no, c["id"]))
            return "S01"
        if nxt:
            self.ex("UPDATE campaigns SET stage=? WHERE id=?", (nxt, c["id"]))
        return nxt

    def _decision_insert(self, profile_id, campaign_id, cycle_id, stage_run_id, output_version, stage, gate, decision, note, decided_by) -> int:
        return self.ex("""INSERT INTO decisions(profile_id,campaign_id,cycle_id,stage_run_id,output_version,stage,gate,decision,note,decided_by,created_at)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                       (profile_id, campaign_id, cycle_id, stage_run_id, output_version, stage, gate, decision, note, decided_by, now_iso())).lastrowid

    def decision_log(self, profile_id: int, decision: str, note: str | None = None, campaign_id: int | None = None,
                     cycle_id: int | None = None, stage: str | None = None, stage_run_id: int | None = None,
                     decided_by: str = "user", checkpoint: dict | None = None, scope_key: str | None = None) -> dict:
        self._profile(profile_id)
        if campaign_id is not None:
            self._campaign(profile_id, campaign_id)
        if cycle_id is not None:
            self._cycle(profile_id, cycle_id, campaign_id)
        if decided_by not in ("user", "system", "job"):
            raise AdMemoryError("decided_by: user | system | job")
        with self.tx():
            did = self._decision_insert(profile_id, campaign_id, cycle_id, stage_run_id, None, stage, None, decision, note, decided_by)
            if checkpoint:
                self._checkpoint_in_tx(profile_id, stage or "general", checkpoint, campaign_id, cycle_id, scope_key)
        return self.q1("SELECT * FROM decisions WHERE id=?", (did,))

    def stage_back(self, profile_id: int, campaign_id: int, cycle_id: int, target_stage: str, reason: str) -> dict:
        c = self._campaign(profile_id, campaign_id)
        cy = self._cycle(profile_id, cycle_id, campaign_id)
        if target_stage not in ST.CAMPAIGN_STAGES:
            raise AdMemoryError(f"bilinmeyen aşama: {target_stage}")
        if cy["launched_at"] and target_stage in ST.NO_RETURN_AFTER_LAUNCH:
            raise AdMemoryError("turun reklamları yayına alındı; S14 ve öncesine dönülmez. Değişiklik bir sonraki turun konusu olur (4.2)")
        if ST.index(target_stage) >= ST.index(c["stage"]):
            raise AdMemoryError(f"hedef aşama ({target_stage}) mevcut aşamadan ({c['stage']}) önce olmalı")
        ti = ST.index(target_stage)
        later = [s for s in ST.CAMPAIGN_STAGES if ST.index(s) > ti]
        with self.tx():
            n = 0
            for s in later:
                n += self.ex("UPDATE stage_runs SET stale=1 WHERE cycle_id=? AND stage=? AND stale=0", (cy["id"], s)).rowcount
            self.ex("UPDATE campaigns SET stage=? WHERE id=?", (target_stage, c["id"]))
            g = self.ex("UPDATE generations SET reusable=1 WHERE cycle_id=? AND status='completed'", (cy["id"],)).rowcount
            if ti <= ST.index("S12"):
                self.ex("UPDATE creatives SET qc_status='stale' WHERE cycle_id=?", (cy["id"],))
            self._decision_insert(profile_id, c["id"], cy["id"], None, None, target_stage, None, "back", reason, "user")
        return {"stage": target_stage, "stale_runs": n, "reusable_generations": g,
                "note": "Sonraki aşamaların çıktıları ve onayları eski işaretlendi; ücretli üretimler silinmedi, yeniden kullanılabilir."}

    def stage_resume(self, profile_id: int, campaign_id: int | None = None, cycle_id: int | None = None) -> dict:
        """Devam notunu tablolar ve dosya hash'leriyle karşılaştırır (8.3)."""
        notes = self.checkpoint_get(profile_id, campaign_id, cycle_id)["open"]
        report = []
        for n in notes:
            st = jload(n["state_json"], {}) if isinstance(n["state_json"], str) else n["state_json"]
            files = st.get("files") or []
            ok, missing, changed = [], [], []
            for f in files:
                path = Path(f.get("path", ""))
                if not path.is_absolute():
                    path = self.data_dir / path
                if not path.exists():
                    missing.append(str(path))
                elif f.get("sha256") and sha256_file(path) != f["sha256"]:
                    changed.append(str(path))
                else:
                    ok.append(str(path))
            gens = []
            if n["cycle_id"]:
                gens = self.qa("SELECT id,tool_name,status,provider_request_id FROM generations WHERE cycle_id=? AND status IN ('running','unknown')",
                               (n["cycle_id"],))
            run = self.q1("SELECT id,stage,status,output_version,stale FROM stage_runs WHERE id=?", (n["stage_run_id"],)) if n["stage_run_id"] else None
            report.append({"checkpoint": n, "verified_files": ok, "missing_files": missing, "changed_files": changed,
                           "unresolved_generations": gens, "stage_run": run,
                           "rules": ["tamamlanan iş tekrar edilmez", "kayıtsız dosya doğrulanmadan benimsenmez",
                                     "eksik dosya tamamlandı sayılmaz", "running/unknown ücretli iş yeniden başlatılmaz"]})
        return {"resume": report}

    def shoot_mark_done(self, profile_id: int, campaign_id: int, cycle_id: int, note: str | None = None) -> dict:
        c = self._campaign(profile_id, campaign_id)
        cy = self._cycle(profile_id, cycle_id, campaign_id)
        if c["stage"] not in ("W", "S05"):
            raise AdMemoryError(f"kampanya çekim bekleme durumunda değil ({c['stage']})")
        raw = self.campaign_dir(profile_id, campaign_id) / "footage" / "raw"
        files = [p for p in raw.glob("*") if p.is_file()]
        photos = [p for p in (raw.parent.parent / "photos" / "raw").glob("*") if p.is_file()]
        import time as _time
        now = _time.time()  # dosya sistemi zamanı gerçek saatle karşılaştırılır
        busy = [p.name for p in files + photos if now - p.stat().st_mtime < 120]
        if busy:
            raise AdMemoryError("son 2 dakikada değişmiş dosyalar var (kopyalama sürüyor olabilir): " + ", ".join(busy[:5]))
        if not files and not photos:
            raise AdMemoryError("footage/raw/ ve photos/raw/ boş; çekim dosyaları gelmeden S06 başlamaz")
        sk = f"cycle:{cy['id']}"
        with self.tx():
            v = (self.q1("SELECT MAX(output_version) AS v FROM stage_runs WHERE scope_key=? AND stage='W'", (sk,)) or {}).get("v") or 0
            self.ex("""INSERT INTO stage_runs(profile_id,campaign_id,stage,cycle_id,scope_key,output_version,status,started_at,finished_at,outputs_json)
                       VALUES(?,?, 'W', ?,?,?, 'done', ?, ?, ?)""",
                    (profile_id, c["id"], cy["id"], sk, v + 1, now_iso(), now_iso(),
                     jdump({"footage": [p.name for p in files], "photos": [p.name for p in photos], "note": note})))
            if self.ex("UPDATE campaigns SET stage='S06' WHERE id=? AND stage IN ('W','S05')", (c["id"],)).rowcount != 1:
                raise AdMemoryError("çekim başka bir oturumda zaten tamam işaretlendi")  # 2.0.0: işlem içinde yeniden denetim
            self._decision_insert(profile_id, c["id"], cy["id"], None, None, "W", None, "shoot_done", note or "çekim tamam", "user")
        return {"stage": "S06", "footage": len(files), "photos": len(photos)}

    def launch_confirm(self, profile_id: int, campaign_id: int, cycle_id: int, s14_stage_run_id: int, output_version: int,
                       ads: list[dict], launched_at: str, user_confirmation: str, test_start: str | None = None,
                       readback: dict | None = None) -> dict:
        """Gerçek yayın kaydı: onaylı S14 sürümü, reklam kimlikleri, gerçek tarih ve kullanıcı teyidi birlikte (4.2)."""
        c = self._campaign(profile_id, campaign_id)
        cy = self._cycle(profile_id, cycle_id, campaign_id)
        if not user_confirmation or not user_confirmation.strip():
            raise AdMemoryError("kullanıcının yayın teyidi zorunlu")
        run = self.q1("SELECT * FROM stage_runs WHERE id=?", (int(s14_stage_run_id),))
        if not run or run["stage"] != "S14" or run["cycle_id"] != cy["id"]:
            raise AdMemoryError("S14 kaydı bu tura ait değil")
        if run["status"] != "done" or run["stale"] or run["output_version"] != int(output_version):
            raise AdMemoryError("onaylı ve güncel S14 sürümü gerekli")
        latest = self.q1("SELECT MAX(output_version) AS v FROM stage_runs WHERE scope_key=? AND stage='S14'", (run["scope_key"],))["v"]
        if latest != run["output_version"]:
            raise AdMemoryError("daha yeni bir S14 sürümü var")
        if cy["launched_at"]:
            raise AdMemoryError("bu tur zaten yayın kaydına sahip")
        if parse_iso(launched_at) is None:
            raise AdMemoryError("launched_at ISO tarih/saat olmalı")
        if not ads:
            raise AdMemoryError("yayınlanan reklam kimlikleri (ads) zorunlu")
        keys = {r["creative_key"] for r in self.qa("SELECT DISTINCT creative_key FROM creatives WHERE cycle_id=? AND delivery_role='test'", (cy["id"],))}
        rl = jload(cy["risk_limits_json"], {}) or {}
        mapping = rl.get("mapping") or {}
        if readback is not None:
            seen = {str(x) for x in (readback.get("ad_ids") or [])}
            notfound = [a["meta_ad_id"] for a in ads if str(a["meta_ad_id"]) not in seen]
            if notfound:
                raise AdMemoryError("salt okuma karşılaştırmasında bulunamayan reklam kimlikleri: " + ", ".join(notfound))
        bid = c["brand_id"]
        with self.tx():
            for a in ads:
                if not a.get("meta_ad_id"):
                    raise AdMemoryError("her reklam meta_ad_id taşımalı")
                ck = a.get("creative_key")
                if ck and ck not in keys:
                    raise AdMemoryError(f"creative_key {ck} bu turun test kreatiflerinde yok (yedekler sessizce yayına eklenmez)")
                if ck and ck not in mapping:
                    raise AdMemoryError(f"creative_key {ck} için risk sınırı eşlemesi yok")
                self.ex("""INSERT INTO ads(brand_id,campaign_id,cycle_id,creative_key,meta_ad_id,meta_ad_name,adset_id,campaign_meta_id,launched_at,status)
                           VALUES(?,?,?,?,?,?,?,?,?, 'active')
                           ON CONFLICT(brand_id, meta_ad_id) DO UPDATE SET campaign_id=excluded.campaign_id, cycle_id=excluded.cycle_id,
                             creative_key=excluded.creative_key, meta_ad_name=excluded.meta_ad_name, adset_id=excluded.adset_id,
                             campaign_meta_id=excluded.campaign_meta_id, launched_at=excluded.launched_at""",
                        (bid, c["id"], cy["id"], ck, str(a["meta_ad_id"]), a.get("meta_ad_name"), a.get("adset_id"),
                         a.get("campaign_meta_id"), launched_at))
                if ck:
                    mapping.setdefault(ck, {}).setdefault("meta_ad_ids", [])
                    if str(a["meta_ad_id"]) not in mapping[ck]["meta_ad_ids"]:
                        mapping[ck]["meta_ad_ids"].append(str(a["meta_ad_id"]))
            rl["mapping"] = mapping
            if self.ex("UPDATE cycles SET launched_at=?, test_start=COALESCE(?, test_start), risk_limits_json=?, status='measuring' "
                       "WHERE id=? AND launched_at IS NULL", (launched_at, test_start, jdump(rl), cy["id"])).rowcount != 1:
                raise AdMemoryError("bu tur başka bir oturumda az önce yayın kaydı aldı")  # 2.0.0: işlem içinde yeniden denetim
            self._decision_insert(profile_id, c["id"], cy["id"], run["id"], run["output_version"], "S14", "yayın", "launched",
                                  f"kullanıcı teyidi: «{user_confirmation.strip()}»", "user")
            self.ex("UPDATE campaigns SET stage='S15' WHERE id=?", (c["id"],))
            v = (self.q1("SELECT MAX(output_version) AS v FROM stage_runs WHERE scope_key=? AND stage='S15'", (run["scope_key"],)) or {}).get("v") or 0
            self.ex("""INSERT INTO stage_runs(profile_id,campaign_id,stage,cycle_id,scope_key,output_version,status,started_at)
                       VALUES(?,?, 'S15', ?,?,?, 'running', ?)""", (profile_id, c["id"], cy["id"], run["scope_key"], v + 1, now_iso()))
        return {"launched": True, "cycle": self.q1("SELECT * FROM cycles WHERE id=?", (cy["id"],)),
                "next": "Günlük takip işi (takip) ve plan günü karar hazırlığı işi gerçek yayın kaydına göre kurulur (4.4)."}

    # --- durum ve takvim (4.4, 17.1) --------------------------------------------
    def campaign_status(self, profile_id: int, campaign_id: int | None = None) -> dict:
        p = self._profile(profile_id, allow_archived=True)
        brand = self.q1("SELECT * FROM brands WHERE id=?", (p["brand_id"],)) if p["brand_id"] else None
        tzname = (brand or {}).get("timezone")
        camps = [self._campaign(profile_id, campaign_id)] if campaign_id else (
            self.qa("SELECT * FROM campaigns WHERE brand_id=? AND status='active' ORDER BY id", (p["brand_id"],)) if p["brand_id"] else [])
        out = []
        for c in camps:
            cy = self._current_cycle(c)
            measuring = self.qa("SELECT * FROM cycles WHERE campaign_id=? AND status='measuring' ORDER BY cycle", (c["id"],))
            pending = self.qa("""SELECT id,stage,output_version,cycle_id FROM stage_runs WHERE campaign_id=? AND status='awaiting_gate' AND stale=0
                                 ORDER BY id""", (c["id"],))
            ai = self.qa("SELECT status, COUNT(*) AS n FROM action_items WHERE campaign_id=? GROUP BY status", (c["id"],))
            gens = self.qa("SELECT status, COUNT(*) AS n FROM generations WHERE campaign_id=? AND status IN ('running','unknown') GROUP BY status", (c["id"],))
            cal = self._calendar_line(c, cy, measuring, tzname)
            warnings = []
            for m in measuring:
                if m["structure_detected"] in ("deviated", "unverified"):
                    warnings.append(f"Tur {m['cycle']}: test yapısı {m['structure_detected']} — hükümler 'doğrulanmamış yapı' kaydıyla")
            if c["result_type"] == "purchase" and self.meta_signal_get(profile_id)["meta_signal"].get("status") != "purchase_seen":
                warnings.append("Satış sonuçlu kampanya ama Meta'nın satışı gördüğü doğrulanmadı: Meta tıklayanı bulur, alanı değil (piksel/yükleme)")
            if c["result_type"] == "lead":  # 1.5.0
                if c.get("lead_method") == "website" and not self.meta_signal_get(profile_id)["meta_signal"].get("lead_seen"):
                    warnings.append("Sitedeki formla aday kampanyası ama Meta'nın Lead olayını gördüğü doğrulanmadı (S00b 6b, veri bağlantısı)")
                if measuring and not self.q1("SELECT 1 FROM lead_outcomes WHERE campaign_id=? LIMIT 1", (c["id"],)):
                    warnings.append("Aday kampanyası ölçümde ama aday sonrası kayıt yok (lead_outcome_set): nitelik ve satış görülmeden büyütme önerilmez")
            out.append({"campaign": {k: c[k] for k in ("id", "name", "stage", "cycle", "mode", "result_type", "lead_method", "budget_total")},
                        "stage_name": ST.STAGE_NAMES.get(c["stage"]), "skill": ST.SKILLS.get(c["stage"]),
                        "current_cycle_id": cy["id"] if cy else None,
                        "pending_gates": [{**g, "gate": ST.GATES.get(g["stage"])} for g in pending],
                        "action_items": {r["status"]: r["n"] for r in ai},
                        "unresolved_generations": {r["status"]: r["n"] for r in gens},
                        "calendar": cal, "warnings": warnings})
        return {"profile": {"id": p["id"], "name": p["name"], "status": p["status"]}, "campaigns": out}

    def _calendar_line(self, c: dict, cy: dict | None, measuring: list[dict], tzname: str | None) -> dict:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(tzname) if tzname else dt.timezone.utc
        today = utcnow().astimezone(tz).date()
        res: dict[str, Any] = {"today": today.isoformat(), "timezone": tzname or "UTC (marka saat dilimi doğrulanmadı)"}
        m = measuring[-1] if measuring else None
        if m and m["launched_at"]:
            g0 = parse_iso(m["launched_at"]).astimezone(tz).date()
            gday = (today - g0).days
            cd = m["cycle_days"] or 14
            td = m["test_days"] or 7
            plan_day = m["plan_day"] or (g0 + dt.timedelta(days=td + 3)).isoformat()
            phase = "test sürüyor" if gday <= td else ("atıf verisi bekleniyor" if today.isoformat() < plan_day else "plan günü")
            res.update({"cycle": m["cycle"], "g_day": gday, "cycle_days": cd, "phase": phase, "plan_day": plan_day,
                        "line": f"Tur {m['cycle']} · G{gday}/{cd} · {phase} · plan günü: {plan_day}"})
        elif cy:
            cal = jload(cy["calendar_json"], {}) or {}
            res.update({"cycle": cy["cycle"], "phase": "üretim", "targets": cal.get("targets"),
                        "line": f"Tur {cy['cycle']} · üretim ({ST.STAGE_NAMES.get(c['stage'], c['stage'])})"
                                + (f" · hedef yayın: {cy['launch_at']}" if cy.get("launch_at") else "")})
        return res
