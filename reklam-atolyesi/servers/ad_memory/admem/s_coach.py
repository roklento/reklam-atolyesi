"""Koçluk boru hattı kayıtları: değişmez girdi kopyası, uygulama listesi, tahmin/kalibrasyon, playbook (spec 6.4–6.14, 8.6)."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from .util import AdMemoryError, atomic_write, canonical_json, jdump, jload, now_iso, parse_iso, sha256_file, sha256_text, utcnow

MODEL_VERSION = "1.4.0"
DEFAULT_PARAMS = {"n_cap": 30, "seed": 1729, "draws": 10000, "interval": 0.90,
                  "thresholds": {"hook_impressions": 1000, "ctr_impressions": 3000, "cost_results": 10},
                  "max_budget_increase": 0.20, "upper_funnel": ["hook_rate", "hold_rate", "thruplay_rate"]}
UPPER_FUNNEL = set(DEFAULT_PARAMS["upper_funnel"])
# Ölçekleme katmanı (1.4.6): günlük bütçe ≥ 7 × hedef maliyet. Öğrenme aşaması için 7 günde ~50 optimizasyon olayından türetilmiş
# YEREL eşik; sayının resmi metni bu kurulumda okunmadı (ref-legal-tr-meta §7).
SCALE_MIN_DAILY_MULT = 7
SCALE_ITEM_KINDS = ("scale_open", "scale_move", "scale_pause_source")
LOWER_FUNNEL = {"ctr_link", "link_clicks", "profile_visit", "messaging", "lead", "cost_per_lead", "add_to_cart", "cost_per_result", "purchase", "results", "cvr"}


class CoachMixin:
    def _campaign_objective(self, rows: list[dict], pri: list[dict]) -> tuple[str | None, str]:
        """Turun reklamlarının bağlı olduğu Meta kampanyalarının amacı. Tek amaç okunursa o; okunamazsa ve markada tek amaçlı önsel
        varsa o; birden çok amaç varsa ya da hiç bilgi yoksa None (Beta(1,1), rastgele bir amacın önseli kullanılmaz)."""
        ids = sorted({str(r["meta_ad_id"]) for r in rows if r.get("meta_ad_id")})
        objs: set[str] = set()
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            got = self.qa(f"""SELECT DISTINCT cmp.objective FROM meta_entities e
                               JOIN meta_entities s ON s.level='adset' AND s.meta_id=e.parent_meta_id
                               JOIN meta_entities cmp ON cmp.level='campaign' AND cmp.meta_id=s.parent_meta_id
                               WHERE e.level='ad' AND e.meta_id IN ({','.join('?' * len(chunk))}) AND cmp.objective IS NOT NULL""", chunk)
            objs |= {g["objective"] for g in got}
        have = sorted({p["objective"] for p in pri})
        if len(objs) == 1:
            return next(iter(objs)), "turun reklamlarının Meta kampanya amacı"
        if len(objs) > 1:
            return None, f"turun reklamları birden çok amaçta ({', '.join(sorted(objs))}): önsel kullanılmadı, Beta(1,1)"
        if len(have) == 1:
            return have[0], "reklamların amacı okunamadı; markada tek amaçlı önsel var"
        return None, ("reklamların amacı okunamadı ve markada birden çok amaçlı önsel var: önsel kullanılmadı, Beta(1,1)" if have
                      else "önsel yok: Beta(1,1)")

    # --- değişmez karar girdisi (6.4) ----------------------------------------------
    def decision_input_snapshot(self, profile_id: int, campaign_id: int, cycle_id: int, kind: str = "coach_report",
                                extra: dict | None = None) -> dict:
        """Hesaplamadan ÖNCE bütün girdileri tek JSON kopyasında sabitler; hesap ve rapor bu kopyayı okur."""
        if kind not in ("coach_report", "coach_draft", "budget_alert", "prediction_outcome", "daily_track"):
            raise AdMemoryError("kind: coach_report | coach_draft | budget_alert | prediction_outcome | daily_track")
        c = self._campaign(profile_id, campaign_id)
        cy = self._cycle(profile_id, cycle_id, campaign_id)
        brand = self.q1("SELECT * FROM brands WHERE id=?", (c["brand_id"],))
        prod = self.q1("SELECT * FROM products WHERE id=?", (c["product_id"],)) if c["product_id"] else None
        rows = self.metrics_daily_rows(profile_id, campaign_id)["rows"]
        window = None
        if cy["test_start"] and cy["test_end"]:
            window = self.test_window_days(cy["test_start"], cy["test_end"], brand["timezone"])
        priors = cy["priors_snapshot_json"]
        if not priors:
            pri = self.qa("SELECT objective, metric, a, b, n_source, n_cap, source, source_cutoff_at FROM priors WHERE brand_id=?", (c["brand_id"],))
            if cy["test_start"]:
                ts = cy["test_start"][:10]
                pri = [p for p in pri if not p["source_cutoff_at"] or p["source_cutoff_at"] < ts or p["source"] == "uniform"]
            # 2.0.0: önsel yalnızca kampanyanın Meta amacından (6.6 "aynı profil + objective"). Önceden markanın bütün amaçlarının
            # önselleri birlikte alınıyor, koçluk metrik başına sıradaki son satırı (rastgele bir amacı) kullanıyordu.
            objective, why = self._campaign_objective(rows, pri)
            pri = [p for p in pri if p["objective"] == objective] if objective else []
            if objective and not pri:
                why += "; bu amaç için önsel yok: Beta(1,1)"
            priors = {"frozen_at": now_iso(), "objective": objective, "objective_basis": why, "priors": pri}
            with self.tx():
                self.ex("UPDATE cycles SET priors_snapshot_json=? WHERE id=? AND priors_snapshot_json IS NULL", (jdump(priors), cy["id"]))
        comp = self.q1("SELECT id, sha256, fetched_at FROM competitor_snapshots WHERE profile_id=? ORDER BY fetched_at DESC, id DESC LIMIT 1", (profile_id,))
        creatives = self.qa("""SELECT cr.creative_key, cr.format, cr.media_type, cr.delivery_role, cr.duration_s, cr.features_json, cr.edit_plan_id,
                                      cr.cycle_id, k.code AS concept, k.competitive_role, cr.ai_share,
                                      k.features_json AS concept_features, k.message_json AS concept_message
                               FROM creatives cr LEFT JOIN concepts k ON k.id=cr.concept_id WHERE cr.campaign_id=?""", (c["id"],))
        plans = {}
        for cr in creatives:
            if cr["edit_plan_id"] and cr["edit_plan_id"] not in plans:
                pr = self.q1("SELECT id, sha256, plan_json FROM edit_plans WHERE id=?", (cr["edit_plan_id"],))
                if pr:
                    pj = jload(pr["plan_json"], {})
                    plans[pr["id"]] = {"sha256": pr["sha256"], "duration_s": pj.get("duration_s"),
                                       "scenes": [{"id": s["id"], "role": s["role"], "start_s": s["start_s"], "dur_s": s["dur_s"]} for s in pj.get("scenes", [])]}
        payload = {
            "model_version": MODEL_VERSION, "params": {**DEFAULT_PARAMS, **((extra or {}).get("params") or {})},
            "kind": kind, "profile_id": int(profile_id),
            "campaign": {k: c[k] for k in ("id", "name", "result_type", "lead_method", "budget_total", "mode", "test_structure")},
            "product_kind": (prod or {}).get("kind") or "product",
            "cycle": {k: cy[k] for k in ("id", "cycle", "adset_budget_daily", "test_budget", "test_days", "cycle_days", "launch_at", "launched_at",
                                          "test_start", "test_end", "structure_detected", "structure_evidence_json", "measurement_json",
                                          "budget_plan_json", "risk_limits_json", "strategy_json", "meta_test_id")},
            "timezone": brand["timezone"], "currency": (prod or {}).get("currency"),
            "economics": self.economics(prod) if prod else None,
            "test_window": window, "rows": rows, "sales_manual": self.qa("SELECT * FROM sales_manual WHERE campaign_id=?", (c["id"],)),
            "priors": priors, "creatives": creatives, "edit_plans": plans,
            "hypotheses": self.qa("SELECT id, statement, metric, feature, status, is_primary, evidence_json FROM hypotheses WHERE campaign_id=?", (c["id"],)),
            "competitor_snapshot": comp, "extra": {k: v for k, v in (extra or {}).items() if k != "params"},
            "data_cutoff": max((r["fetched_at"] for r in rows), default=None),
        }
        # 1.4.8: mesajla satış ve içe aktarılan mağaza siparişleri (kişisel veri ve not yok; siparişler gün/kanal/durum toplamı)
        lo = min([c["created_at"][:10]] + [r["date"] for r in rows])
        hi = "9999-12-31"  # kopya içeriği bugünün tarihine değil yalnızca kayıtlı veriye bağlı kalsın (aynı veri → aynı kopya)
        from .s_dm import local_date
        tz = self._brand_tz(c["brand_id"])
        payload["dm"] = {"threads": [{**t, "closed_date": local_date(t["closed_at"], tz) if t["closed_at"] else None}
                                     for t in self.dm_threads_rows(c["brand_id"], lo, hi)],
                         "daily": self.qa("SELECT date, channel, conversations, from_ads, qualified, quoted, won FROM dm_daily "
                                          "WHERE brand_id=? AND date BETWEEN ? AND ? ORDER BY date, channel", (c["brand_id"], lo, hi))}
        payload["sales_orders"] = self.qa("""SELECT date, channel, status, currency, COUNT(*) AS orders, SUM(COALESCE(units,0)) AS units,
                                                SUM(CASE WHEN units IS NULL THEN 1 ELSE 0 END) AS units_unknown, SUM(COALESCE(amount,0)) AS amount
                                         FROM sales_orders WHERE brand_id=? AND date BETWEEN ? AND ? GROUP BY date, channel, status, currency
                                         ORDER BY date, channel, status""", (c["brand_id"], lo, hi))
        payload["lead_outcomes"] = self.qa("""SELECT period_start, period_end, leads, reached, qualified, won, revenue, currency, source
                                              FROM lead_outcomes WHERE campaign_id=? ORDER BY period_start""", (c["id"],))
        payload["sales_imports"] = []  # dışa aktarımın kapsadığı dönem: elle girişle kıyasta mağaza kaydının esas olduğu aralık
        for im in self.qa("SELECT date_from, date_to, mapping_json FROM sales_imports WHERE brand_id=? ORDER BY id", (c["brand_id"],)):
            mj = jload(im["mapping_json"]) or {}
            per = mj.get("period")  # yalnızca kullanıcının verdiği dışa aktarım aralığı (sipariş tarihlerinin yayılımı eksik dosyayı gizler)
            if per and per[1] >= lo:
                payload["sales_imports"].append({"channel": mj.get("channel"), "from": per[0], "to": per[1]})
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1, default=str)
        sha = sha256_text(text)
        ex = self.q1("SELECT * FROM input_snapshots WHERE cycle_id=? AND kind=? AND sha256=?", (cy["id"], kind, sha))
        if ex and Path(ex["path"]).exists() and sha256_file(ex["path"]) == sha:
            return {**ex, "reused": True, "note": "Aynı girdi ve kurallar aynı rapor sürümünü kullanır (6.4)."}
        ver = ((self.q1("SELECT MAX(version) AS v FROM input_snapshots WHERE cycle_id=? AND kind=?", (cy["id"], kind)) or {}).get("v") or 0) + 1
        path = self.campaign_dir(profile_id, campaign_id) / "reports" / f"c{cy['cycle']}-{kind}-input-v{ver}.json"
        try:
            got = atomic_write(path, text, overwrite=False)
        except Exception as e:
            raise AdMemoryError(f"karar girdisi saklanamadı; rapor/uyarı tamamlanmış sayılmaz: {e}")
        if got != sha:
            raise AdMemoryError("karar girdisi doğrulanamadı")
        with self.tx():
            sid = self.ex("INSERT INTO input_snapshots(profile_id,campaign_id,cycle_id,kind,version,path,sha256,created_at) VALUES(?,?,?,?,?,?,?,?)",
                          (profile_id, c["id"], cy["id"], kind, ver, str(path), sha, now_iso())).lastrowid
        return {**self.q1("SELECT * FROM input_snapshots WHERE id=?", (sid,)), "reused": False}

    def _snapshot_ref_ok(self, profile_id: int, ref: dict | None) -> dict:
        if not ref or not ref.get("path") or not ref.get("sha256"):
            raise AdMemoryError("karar girdisi kopyası referansı (path, sha256) zorunlu (6.4)")
        p = Path(ref["path"])
        if not p.exists() or sha256_file(p) != ref["sha256"]:
            raise AdMemoryError("karar girdisi kopyası bulunamadı ya da hash uyuşmuyor; kayıt tamamlanmaz")
        row = self.q1("SELECT * FROM input_snapshots WHERE sha256=? AND profile_id=?", (ref["sha256"], profile_id))
        if not row:
            raise AdMemoryError("karar girdisi kopyası bu profile kayıtlı değil")
        return row

    # --- uygulama listesi (6.10, 6.11) -------------------------------------------------
    def action_items_set(self, profile_id: int, campaign_id: int, items: list[dict], cycle_id: int | None = None,
                         decision_id: int | None = None) -> dict:
        c = self._campaign(profile_id, campaign_id)
        if cycle_id is not None:
            self._cycle(profile_id, cycle_id, campaign_id)
        created, refreshed = [], []
        per_adset_day: dict[tuple, int] = {}
        today = utcnow().date().isoformat()
        for it in items:
            if not it.get("action"):
                raise AdMemoryError("her madde somut bir Ads Manager adımı (action) taşır")
            rk = it.get("reason_kind", "performance")
            if rk not in ("performance", "limit", "consent", "structure"):
                raise AdMemoryError("reason_kind: performance | limit | consent | structure")
            before, after = it.get("before") or {}, it.get("after") or {}
            ev = it.get("evidence") or {}
            if rk in ("performance", "limit"):
                self._snapshot_ref_ok(profile_id, ev.get("input_snapshot"))
            if before.get("daily_budget") and after.get("daily_budget"):
                inc = (float(after["daily_budget"]) - float(before["daily_budget"])) / float(before["daily_budget"])
                if inc > DEFAULT_PARAMS["max_budget_increase"] + 1e-9:
                    raise AdMemoryError(f"günlük bütçe artışı en fazla %20 (öneri: %{inc*100:.0f}) (6.10)")
            if it.get("kind") == "pause" and rk == "performance" and not ev.get("threshold_met"):
                raise AdMemoryError("eşik altındaki kreatif için istatistiksel kaybeden hükmüne dayanan 'kapat' önerilmez (6.10)")
            if it.get("kind") in SCALE_ITEM_KINDS:
                self._scale_item_ok(it, rk, after, ev)
            adset = it.get("adset_id") or it.get("target_meta_id")
            if it.get("major", True) and adset:
                k = (adset, today)
                per_adset_day[k] = per_adset_day.get(k, 0) + 1
                if per_adset_day[k] > 1:
                    raise AdMemoryError("aynı reklam setinde aynı gün birden fazla büyük değişiklik yok (6.10)")
        with self.tx():
            for it in items:
                dk = it.get("dedupe_key")
                if dk:
                    ex = self.q1("SELECT * FROM action_items WHERE campaign_id=? AND dedupe_key=? AND status IN ('proposed','approved')", (c["id"], dk))
                    if ex:
                        evs = ex["evidence_json"] if isinstance(ex["evidence_json"], list) else jload(ex["evidence_json"], []) or []
                        evs.append({**(it.get("evidence") or {}), "at": now_iso()})
                        self.ex("UPDATE action_items SET evidence_json=?, after_json=? WHERE id=?", (jdump(evs), jdump(it.get("after")), ex["id"]))
                        refreshed.append(ex["id"])
                        continue
                aid = self.ex("""INSERT INTO action_items(campaign_id,cycle_id,decision_id,action,target_meta_id,reason_kind,before_json,after_json,status,
                                 dedupe_key,evidence_json,created_at) VALUES(?,?,?,?,?,?,?,?, 'proposed', ?,?,?)""",
                              (c["id"], cycle_id, decision_id, it["action"], it.get("target_meta_id"), it.get("reason_kind", "performance"),
                               jdump(it.get("before")), jdump(it.get("after")), dk, jdump([{**(it.get("evidence") or {}), "at": now_iso()}]),
                               now_iso())).lastrowid
                created.append(aid)
        return {"created": created, "refreshed": refreshed,
                "note": "Zamanlanmış iş onay vermez; uyarının görülmesi/onaylanması reklamın durduğu anlamına gelmez (6.10)."}

    @staticmethod
    def _scale_item_ok(it: dict, rk: str, after: dict, ev: dict) -> None:
        """Ölçekleme maddeleri (coach 6a): taşıma yalnızca dört koşulla ve gönderi kimliğiyle; katman açma yapısal maddedir."""
        kind = it["kind"]
        if kind == "scale_move":
            if rk != "performance":
                raise AdMemoryError("ölçeklemeye taşıma performans gerekçeli maddedir (reason_kind='performance')")
            if not str(after.get("post_id") or "").strip():
                raise AdMemoryError("ölçeklemeye taşıma gönderi kimliği (after.post_id) ister; yeni reklam olarak kopyalamak beğeni ve yorumları taşımaz")
            checks = ev.get("scale_checks") or {}
            missing = [k for k in ("structure", "cost", "min_daily", "fits_total") if checks.get(k) is not True]
            if missing:
                raise AdMemoryError(f"ölçekleme koşulları sağlanmadı ({', '.join(missing)}); kazanan ana sette bütçe artışıyla büyür (coach 6a)")
        elif kind == "scale_open":
            if rk != "structure":
                raise AdMemoryError("ölçekleme kampanyası açma yapısal maddedir (reason_kind='structure')")
            if not after.get("daily_budget") or float(after["daily_budget"]) <= 0:
                raise AdMemoryError("ölçekleme kampanyası açma maddesi pozitif günlük bütçe (after.daily_budget) taşır")
        elif kind == "scale_pause_source":
            if rk != "structure":
                raise AdMemoryError("aynı gönderinin test setinde duraklatılması yapısal maddedir (reason_kind='structure')")
            if not str(after.get("post_id") or "").strip():
                raise AdMemoryError("test setinde duraklatılacak gönderi kimliği (after.post_id) gerekli")

    # --- ölçekleme katmanı (1.4.6; coach 6a) ------------------------------------------
    def scale_layer_get(self, profile_id: int, campaign_id: int, cycle_id: int | None = None) -> dict:
        c = self._campaign(profile_id, campaign_id)
        cy = self._cycle(profile_id, cycle_id, campaign_id) if cycle_id is not None else \
            self.q1("SELECT * FROM cycles WHERE campaign_id=? AND cycle=?", (c["id"], c["cycle"]))
        layer = (jload(cy["budget_plan_json"], {}) or {}).get("scale_layer") if cy else None
        return {"campaign_id": c["id"], "cycle_id": cy["id"] if cy else None, "scale_layer": layer,
                "min_daily_rule": f"günlük bütçe ≥ {SCALE_MIN_DAILY_MULT} × doğrulanmış hedef maliyet (yerel eşik, §7)"}

    def scale_layer_set(self, profile_id: int, campaign_id: int, cycle_id: int, layer: dict,
                        learning_warning_ack: str | None = None) -> dict:
        """Ölçekleme katmanı kaydı: ayrı Meta kampanyası, tek reklam seti; üyeler mevcut gönderiyle taşınmış reklamlar.
        Üyeler aynı creative_key'e ölçekleme setinin adset_id'siyle bağlanır (ad_link), böylece test hesabından ayrılır."""
        c = self._campaign(profile_id, campaign_id)
        cy = self._cycle(profile_id, cycle_id, campaign_id)
        if not isinstance(layer, dict):
            raise AdMemoryError("layer bir nesne olmalı")
        for k in ("campaign_meta_id", "adset_id"):
            if not str(layer.get(k) or "").strip():
                raise AdMemoryError(f"ölçekleme katmanı {k} ister (Ads Manager'dan okunan kimlik)")
        status = layer.get("status", "active")
        if status not in ("active", "paused", "closed"):
            raise AdMemoryError("status: active | paused | closed")
        try:
            daily = float(layer.get("daily_budget"))
        except (TypeError, ValueError):
            raise AdMemoryError("ölçekleme katmanı pozitif günlük bütçe (daily_budget) ister")
        if daily <= 0:
            raise AdMemoryError("ölçekleme katmanı pozitif günlük bütçe (daily_budget) ister")
        prod = self.q1("SELECT * FROM products WHERE id=?", (c["product_id"],)) if c["product_id"] else None
        eco = self.economics(prod) if prod else {"status": "unknown"}
        from .s_lead import target_for
        tgt, tgt_exact = target_for(c["result_type"], eco)
        if not (tgt and tgt_exact):
            raise AdMemoryError("ölçekleme katmanı doğrulanmış hedef maliyet ister (satışta hedef CPA, adayda hedef aday maliyeti 'exact' "
                                "değil; coach 6a)")
        min_daily = round(SCALE_MIN_DAILY_MULT * float(tgt), 2)
        warning = None
        if daily + 1e-9 < min_daily and status == "active":
            if not (learning_warning_ack and learning_warning_ack.strip()):
                raise AdMemoryError(f"günlük bütçe {daily:.2f} < {min_daily:.2f} (= {SCALE_MIN_DAILY_MULT} × hedef maliyet): öğrenme sınırlı kalabilir. "
                                    "Kullanıcı yine de isterse açık ifadesi learning_warning_ack ile kaydedilir")
            warning = f"öğrenme sınırlı kalabilir (günlük {daily:.2f} < {min_daily:.2f}); kullanıcı: «{learning_warning_ack.strip()}»"
        members = layer.get("members") or []
        if not isinstance(members, list):
            raise AdMemoryError("members bir liste olmalı")
        seen = set()
        clean = []
        for m in members:
            ck, ad, post = m.get("creative_key"), str(m.get("meta_ad_id") or "").strip(), str(m.get("post_id") or "").strip()
            if not ck or not ad:
                raise AdMemoryError("her üye creative_key ve meta_ad_id taşır")
            if not post:
                raise AdMemoryError(f"üye {ck}: gönderi kimliği (post_id) yok; ölçeklemeye yalnızca mevcut gönderiyle taşınır")
            if not self.q1("SELECT 1 FROM creatives WHERE campaign_id=? AND creative_key=? AND delivery_role='test'", (c["id"], ck)):
                raise AdMemoryError(f"üye {ck}: bu kampanyada test edilmiş kreatif değil; ölçekleme setine yeni konsept doğrudan eklenmez")
            if ad in seen:
                raise AdMemoryError(f"aynı reklam iki kez üye: {ad}")
            seen.add(ad)
            clean.append({"creative_key": ck, "meta_ad_id": ad, "post_id": post, "source_meta_ad_id": m.get("source_meta_ad_id"),
                          "moved_at": m.get("moved_at") or now_iso()})
        rec = {"campaign_meta_id": str(layer["campaign_meta_id"]), "adset_id": str(layer["adset_id"]), "daily_budget": daily,
               "status": status, "opened_at": layer.get("opened_at") or now_iso(), "members": clean,
               "min_daily": min_daily, "learning_warning": warning, "updated_at": now_iso()}
        bp = jload(cy["budget_plan_json"], {}) or {}
        bp["scale_layer"] = rec
        with self.tx():
            self.ex("UPDATE cycles SET budget_plan_json=? WHERE id=?", (jdump(bp), cy["id"]))
            if warning:
                self._decision_insert(profile_id, c["id"], cy["id"], None, None, None, None, "scale_learning_warning", warning, "user")
        for m in clean:
            self.ad_link(profile_id, c["id"], cy["id"], m["creative_key"], m["meta_ad_id"], adset_id=rec["adset_id"])
        return {"scale_layer": rec, "linked": [m["meta_ad_id"] for m in clean]}

    def action_item_set_status(self, profile_id: int, item_id: int, status: str, approval_text: str | None = None,
                               decision_id: int | None = None) -> dict:
        it = self.q1("SELECT * FROM action_items WHERE id=?", (int(item_id),))
        if not it:
            raise AdMemoryError("madde yok")
        self._campaign(profile_id, it["campaign_id"])
        if status not in ("approved", "applied", "not_applied", "proposed"):
            raise AdMemoryError("status: proposed | approved | applied | not_applied")
        if status == "approved":
            if it["status"] != "proposed":
                raise AdMemoryError("yalnızca önerilen madde onaylanır")
            if not (approval_text and approval_text.strip()):
                raise AdMemoryError("onay kullanıcının açık ifadesini ister")
            with self.tx():
                did = decision_id or self._decision_insert(profile_id, it["campaign_id"], it["cycle_id"], None, None, None, None,
                                                           f"action:{it['id']}:approved", f"kullanıcı: «{approval_text.strip()}»", "user")
                self.ex("UPDATE action_items SET status='approved', decision_id=? WHERE id=?", (did, it["id"]))
        elif status in ("applied", "not_applied"):
            raise AdMemoryError("uygulanma yalnızca action_items_verify ile, okunan kanıtla kaydedilir (6.11)")
        else:
            with self.tx():
                self.ex("UPDATE action_items SET status='proposed' WHERE id=?", (it["id"],))
        return self.q1("SELECT * FROM action_items WHERE id=?", (it["id"],))

    def action_items_verify(self, profile_id: int, campaign_id: int, readings: list[dict]) -> dict:
        """Onaylı maddeler Meta'dan salt okuma (ya da kullanıcı kanıtı) ile karşılaştırılır (6.11)."""
        self._campaign(profile_id, campaign_id)
        res = []
        with self.tx():
            for r in readings:
                it = self.q1("SELECT * FROM action_items WHERE id=? AND campaign_id=?", (int(r["item_id"]), campaign_id))
                if not it:
                    raise AdMemoryError(f"madde {r['item_id']} bu kampanyada yok")
                if it["status"] not in ("approved", "not_applied"):
                    res.append({"item_id": it["id"], "skipped": f"durum {it['status']}"})
                    continue
                src = r.get("source")
                if src not in ("meta_mcp", "user_evidence"):
                    res.append({"item_id": it["id"], "status": it["status"], "note": "kanıt yok: uygulanma doğrulanmış sayılmaz"})
                    continue
                after = it["after_json"] or {}
                obs = r.get("observed") or {}
                matched = all(str(obs.get(k)) == str(v) for k, v in after.items() if k in obs) and any(k in obs for k in after)
                new = "applied" if matched else "not_applied"
                evs = it["evidence_json"] if isinstance(it["evidence_json"], list) else jload(it["evidence_json"], []) or []
                evs.append({"verify": {"source": src, "observed": obs, "at": now_iso(), "ref": r.get("evidence_ref")}})
                self.ex("UPDATE action_items SET status=?, verified_at=?, evidence_json=? WHERE id=?", (new, now_iso(), jdump(evs), it["id"]))
                res.append({"item_id": it["id"], "status": new})
        counts = {r["status"]: r["n"] for r in self.qa("SELECT status, COUNT(*) AS n FROM action_items WHERE campaign_id=? GROUP BY status", (campaign_id,))}
        return {"results": res, "counts": counts}

    def action_items_list(self, profile_id: int, campaign_id: int, status: str | None = None) -> dict:
        self._campaign(profile_id, campaign_id)
        sql = "SELECT * FROM action_items WHERE campaign_id=?"
        args: list[Any] = [campaign_id]
        if status:
            sql += " AND status=?"
            args.append(status)
        return {"items": self.qa(sql + " ORDER BY id", tuple(args))}

    # --- tahminler ve kalibrasyon (6.13) -----------------------------------------------
    def prediction_log(self, profile_id: int, campaign_id: int, cycle_id: int, subject: str, metric: str,
                       input_snapshot: dict, p_win: float | None = None, interval: dict | None = None) -> dict:
        self._campaign(profile_id, campaign_id)
        self._cycle(profile_id, cycle_id, campaign_id)
        snap = self._snapshot_ref_ok(profile_id, input_snapshot)
        if p_win is not None and not (0 <= float(p_win) <= 1):
            raise AdMemoryError("p_win 0–1 arası")
        ref = canonical_json({"path": snap["path"], "sha256": snap["sha256"], "version": snap["version"]})
        with self.tx():
            ex = self.q1("SELECT * FROM coaching_predictions WHERE cycle_id=? AND subject=? AND metric=? AND input_snapshot_json=?",
                         (cycle_id, subject, metric, ref))
            if ex:
                return {**ex, "idempotent": True}
            prev = self.q1("SELECT * FROM coaching_predictions WHERE cycle_id=? AND subject=? AND metric=? ORDER BY id DESC LIMIT 1",
                           (cycle_id, subject, metric))
            pid = self.ex("""INSERT INTO coaching_predictions(campaign_id,cycle_id,subject,metric,p_win,interval_json,input_snapshot_json,made_at,supersedes_id)
                             VALUES(?,?,?,?,?,?,?,?,?)""",
                          (campaign_id, cycle_id, subject, metric, p_win, jdump(interval), ref, now_iso(), prev["id"] if prev else None)).lastrowid
        return self.q1("SELECT * FROM coaching_predictions WHERE id=?", (pid,))

    def prediction_resolve(self, profile_id: int, prediction_id: int, outcome: dict, outcome_snapshot: dict) -> dict:
        pr = self.q1("SELECT * FROM coaching_predictions WHERE id=?", (int(prediction_id),))
        if not pr:
            raise AdMemoryError("tahmin yok")
        self._campaign(profile_id, pr["campaign_id"])
        snap = self._snapshot_ref_ok(profile_id, outcome_snapshot)
        if "won" not in outcome and "value" not in outcome:
            raise AdMemoryError("outcome {won: bool} ya da {value: sayı} içerir")
        prev = pr["outcome_json"] or {}
        revs = prev.get("revisions", []) if isinstance(prev, dict) else []
        revs.append({**outcome, "snapshot": {"path": snap["path"], "sha256": snap["sha256"]}, "at": now_iso()})
        with self.tx():
            self.ex("UPDATE coaching_predictions SET outcome_json=?, resolved_at=? WHERE id=?",
                    (jdump({"latest": revs[-1], "revisions": revs}), now_iso(), pr["id"]))
        return self.q1("SELECT * FROM coaching_predictions WHERE id=?", (pr["id"],))

    def calibration_get(self, profile_id: int, min_resolved: int = 30) -> dict:
        bid = self._brand_id(profile_id)
        rows = self.qa("""SELECT p.* FROM coaching_predictions p JOIN campaigns c ON c.id=p.campaign_id
                          WHERE c.brand_id=? AND p.supersedes_id IS NULL ORDER BY p.id""", (bid,))
        resolved = []
        for r in rows:
            chain_last = self.q1("""WITH RECURSIVE ch(id) AS (SELECT ? UNION ALL SELECT p.id FROM coaching_predictions p JOIN ch ON p.supersedes_id=ch.id)
                                    SELECT cp.* FROM coaching_predictions cp WHERE cp.id IN (SELECT id FROM ch) AND cp.resolved_at IS NOT NULL
                                    ORDER BY cp.resolved_at DESC LIMIT 1""", (r["id"],))
            if not chain_last or r["p_win"] is None:
                continue
            latest = (chain_last["outcome_json"] or {}).get("latest") or {}
            if "won" not in latest:
                continue
            resolved.append((float(r["p_win"]), bool(latest["won"])))
        n = len(resolved)
        hits = sum(1 for p, w in resolved if (p >= 0.5) == w)
        out: dict[str, Any] = {"resolved": n, "hits": hits, "summary": f"{n} tahminden {hits}'i tuttu"}
        if n < min_resolved:
            out["note"] = f"Kalibrasyon için en az {min_resolved} çözülmüş tahmin gerekir; eşik önerilmez (6.13)."
            return out
        bins = []
        for i in range(5):  # tamsayı yüzdeyle: 0.7 + 0.1 kayan noktada 0.7999… olup etiketi "%70–79" yapıyordu
            lo, hi = 50 + 10 * i, 60 + 10 * i
            # 2.0.0: isabet = tahminin söylediği taraf gerçekleşti mi; p < 0.5 "kaybeder" demektir (önceden ham 'won' sayılıyordu)
            sel = [(w if p >= 0.5 else not w) for p, w in resolved
                   if lo <= round(max(p, 1 - p) * 100, 9) < hi or (hi == 100 and max(p, 1 - p) >= 1.0)]
            if sel:
                bins.append({"claimed": f"%{lo}–{hi}", "n": len(sel), "realized": round(sum(sel) / len(sel), 3)})
        out["bins"] = bins
        out["note"] = "Eşik ve n_cap önerileri kullanıcı onayıyla değişir (6.13)."
        return out

    # --- playbook (6.6, 6.14, 8.6) -------------------------------------------------------
    def playbook_get(self, profile_id: int, status: str | None = None, season: str | None = None) -> dict:
        self._profile(profile_id, allow_archived=True)
        sql = "SELECT * FROM playbook_rules WHERE profile_id=?"
        args: list[Any] = [profile_id]
        if status:
            sql += " AND status=?"
            args.append(status)
        rows = self.qa(sql + " ORDER BY id", tuple(args))
        if season:
            rows = [r for r in rows if not r["season"] or r["season"] == season]
        return {"rules": rows}

    def playbook_propose(self, profile_id: int, rule: str, evidence: dict, scope: dict | None = None,
                         season: str | None = None, confidence: float | None = None) -> dict:
        """Bağımsız doğrulama koşulu (6.6) ve alt huni teyidi (6.14) sağlanmadan aday bile olmaz."""
        self._profile(profile_id)
        hid = evidence.get("hypothesis_id")
        h = self.q1("SELECT * FROM hypotheses WHERE id=? AND profile_id=?", (hid, profile_id)) if hid else None
        if not h or not h["is_primary"]:
            raise AdMemoryError("playbook önerisi önceden sabitlenmiş birincil doğrulama hipotezine dayanır (6.6)")
        pre = (h["evidence_json"] or {}).get("pre_registration") if isinstance(h["evidence_json"], dict) else None
        if not pre:
            raise AdMemoryError("hipotezin test öncesi ön kaydı yok")
        disc, val = evidence.get("discovery_cycle_id"), evidence.get("validation_cycle_id")
        if not disc or not val or disc == val:
            raise AdMemoryError("ilk yeterli tur (keşif) ve ayrı bir doğrulama turu gerekir; keşif verisi tekrar kullanılamaz (6.6)")
        if h["cycle_id"] != val:
            raise AdMemoryError("birincil hipotez doğrulama turuna sabitlenmiş olmalı")
        if not evidence.get("discovery_same_direction"):
            raise AdMemoryError("keşif turunda aynı yönde bulgu gerekir")
        p = float(evidence.get("p_superiority_validation_only", 0))
        if p < 0.95:
            raise AdMemoryError(f"doğrulama turunun tek başına verisinde üstünlük olasılığı ≥ 0,95 gerekir (bulunan {p:.3f})")
        if not evidence.get("sufficient_data"):
            raise AdMemoryError("doğrulama verisi eşiklerin altında")
        metric = pre.get("metric") or h["metric"]
        if metric in UPPER_FUNNEL:
            lf = evidence.get("lower_funnel") or {}
            if not (lf.get("metric") in LOWER_FUNNEL and lf.get("same_direction") and lf.get("sufficient") and lf.get("preselected")):
                raise AdMemoryError("üst huni bulgusu, önceden seçilmiş alt huni metriğiyle aynı yönde ve yeterli veriyle desteklenmeden playbook'a girmez; 'dikkat bulgusu' olarak hipotez defterinde kalır (6.14)")
        if evidence.get("structure_verified") is False or evidence.get("bootstrap"):
            raise AdMemoryError("bootstrap/doğrulanmamış yapı turu kontrollü doğrulama sayılmaz (6.6)")
        with self.tx():
            rid = self.ex("""INSERT INTO playbook_rules(profile_id,rule,scope_json,season,evidence_json,confidence,status,created_at)
                             VALUES(?,?,?,?,?,?, 'proposed', ?)""",
                          (profile_id, rule, jdump(scope), season, jdump(evidence), confidence, now_iso())).lastrowid
        return self.q1("SELECT * FROM playbook_rules WHERE id=?", (rid,))

    def _rule(self, profile_id: int, rule_id: int) -> dict:
        r = self.q1("SELECT * FROM playbook_rules WHERE id=?", (int(rule_id),))
        if not r or r["profile_id"] != int(profile_id):
            raise AdMemoryError("kural bu profile ait değil")
        return r

    def playbook_activate(self, profile_id: int, rule_id: int, approval_text: str) -> dict:
        r = self._rule(profile_id, rule_id)
        if r["status"] not in ("proposed", "due_revalidation"):
            raise AdMemoryError(f"kural {r['status']} durumunda")
        if not (approval_text and approval_text.strip()):
            raise AdMemoryError("playbook kuralı kullanıcı onayıyla aktifleşir (S17 kapısı, 8.6)")
        with self.tx():
            self.ex("UPDATE playbook_rules SET status='active', last_validated_at=?, rounds_since_validation=0 WHERE id=?", (now_iso(), r["id"]))
            self._decision_insert(profile_id, None, None, None, None, "S17", "playbook", f"playbook:{r['id']}:active",
                                  f"kullanıcı: «{approval_text.strip()}»", "user")
        return self._rule(profile_id, rule_id)

    def playbook_revalidate(self, profile_id: int, rule_id: int, outcome: str, evidence: dict | None = None) -> dict:
        r = self._rule(profile_id, rule_id)
        if outcome not in ("consistent", "contradicted", "inconclusive"):
            raise AdMemoryError("outcome: consistent | contradicted | inconclusive")
        ev = r["evidence_json"] or {}
        ev.setdefault("revalidations", []).append({"outcome": outcome, "evidence": evidence, "at": now_iso()})
        with self.tx():
            if outcome == "consistent":
                self.ex("""UPDATE playbook_rules SET consistent_rounds=consistent_rounds+1, contradicted_rounds=0, status='active',
                           last_validated_at=?, rounds_since_validation=0, evidence_json=? WHERE id=?""", (now_iso(), jdump(ev), r["id"]))
            elif outcome == "contradicted":
                cr = r["contradicted_rounds"] + 1
                if cr >= 2:
                    self.ex("""UPDATE playbook_rules SET contradicted_rounds=?, status='retired', retired_reason=?, evidence_json=? WHERE id=?""",
                            (cr, "art arda iki turda çelişti (8.6)", jdump(ev), r["id"]))
                else:
                    self.ex("UPDATE playbook_rules SET contradicted_rounds=?, status='due_revalidation', evidence_json=? WHERE id=?",
                            (cr, jdump(ev), r["id"]))
            else:
                self.ex("UPDATE playbook_rules SET evidence_json=? WHERE id=?", (jdump(ev), r["id"]))
        return self._rule(profile_id, rule_id)

    def playbook_retire(self, profile_id: int, rule_id: int, reason: str) -> dict:
        r = self._rule(profile_id, rule_id)
        if not reason:
            raise AdMemoryError("emeklilik gerekçesi zorunlu (silinmez, gerekçesiyle saklanır)")
        with self.tx():
            self.ex("UPDATE playbook_rules SET status='retired', retired_reason=? WHERE id=?", (reason, r["id"]))
        return self._rule(profile_id, rule_id)

    def playbook_round_tick(self, profile_id: int) -> dict:
        """Her tur sonunda: aktif kurallar her 3 turda ya da 90 günde bir yeniden doğrulamaya düşer (8.6)."""
        self._profile(profile_id)
        due = []
        with self.tx():
            for r in self.qa("SELECT * FROM playbook_rules WHERE profile_id=? AND status='active'", (profile_id,)):
                n = r["rounds_since_validation"] + 1
                last = parse_iso(r["last_validated_at"] or r["created_at"])
                old = (utcnow() - last).days >= 90
                status = "due_revalidation" if (n >= 3 or old) else "active"
                self.ex("UPDATE playbook_rules SET rounds_since_validation=?, status=? WHERE id=?", (n, status, r["id"]))
                if status == "due_revalidation":
                    due.append(r["id"])
        return {"due_revalidation": due}
