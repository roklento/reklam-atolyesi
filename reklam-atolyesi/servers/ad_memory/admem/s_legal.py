"""Müşteri yorumları, kişi izinleri, geri çekme etkisi ve yükleme öncesi izin kapısı (spec bölüm 10, KVKK)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .util import AdMemoryError, jdump, jload, now_iso


class LegalMixin:
    def _evidence_path(self, profile_id: int, path: str | None) -> str | None:
        if not path:
            return None
        p = Path(path)
        if not p.is_absolute():
            p = self.data_dir / p
        if not p.exists():
            raise AdMemoryError(f"izin kanıt dosyası yok: {p}")
        try:
            p.resolve().relative_to(self.profile_dir(profile_id).resolve())
        except ValueError:
            raise AdMemoryError("izin kanıtı profil klasöründe saklanmalı (profiles/<profil>/brand/...)")
        return str(p)

    # --- yorumlar -----------------------------------------------------------------
    def review_add(self, profile_id: int, text: str, name_display_mode: str, consent_type: str, consent_date: str,
                   consent_evidence_path: str, display_name: str | None = None, rating: float | None = None,
                   source: str | None = None, processing_scope: dict | None = None) -> dict:
        bid = self._brand_id(profile_id)
        self._profile(profile_id)
        if name_display_mode not in ("full", "initials", "hidden"):
            raise AdMemoryError("ad gösterimi: full | initials | hidden")
        if not text or not text.strip():
            raise AdMemoryError("yorum metni boş olamaz (birebir saklanır)")
        if rating is not None and not (0 <= float(rating) <= 5):
            raise AdMemoryError("puan 0–5")
        ev = self._evidence_path(profile_id, consent_evidence_path)
        if not ev or not consent_type or not consent_date:
            raise AdMemoryError("yalnızca izin kaydı olan gerçek yorum: izin türü, tarihi ve kanıt dosyası zorunlu (bölüm 10)")
        with self.tx():
            rid = self.ex("""INSERT INTO reviews(brand_id,text,display_name,name_display_mode,rating,source,consent_type,consent_date,consent_evidence_path,
                             processing_scope_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                          (bid, text, display_name, name_display_mode, rating, source, consent_type, consent_date, ev,
                           jdump(processing_scope), now_iso())).lastrowid
        return self.q1("SELECT * FROM reviews WHERE id=?", (rid,))

    def review_query(self, profile_id: int, include_withdrawn: bool = False) -> dict:
        bid = self._brand_id(profile_id)
        sql = "SELECT * FROM reviews WHERE brand_id=?" + ("" if include_withdrawn else " AND withdrawn_at IS NULL")
        rows = self.qa(sql + " ORDER BY id", (bid,))
        for r in rows:
            r["display"] = self._display_name(r)
        return {"reviews": rows}

    @staticmethod
    def _display_name(r: dict) -> str | None:
        n = r.get("display_name") or ""
        if r["name_display_mode"] == "hidden" or not n:
            return None
        if r["name_display_mode"] == "initials":
            return " ".join(p[0].upper() + "." for p in n.split() if p)
        return n

    def review_withdraw(self, profile_id: int, review_id: int, reason: str | None = None) -> dict:
        bid = self._brand_id(profile_id)
        r = self.q1("SELECT * FROM reviews WHERE id=? AND brand_id=?", (int(review_id), bid))
        if not r:
            raise AdMemoryError("yorum bu profile ait değil")
        with self.tx():
            self.ex("UPDATE reviews SET withdrawn_at=COALESCE(withdrawn_at, ?) WHERE id=?", (now_iso(), r["id"]))
            impact = self._withdraw_impact(profile_id, lambda plan: any(
                l.get("component") == "ReviewCard" and int(l.get("review_id") or 0) == r["id"]
                for s in plan.get("scenes", []) for l in s.get("layers", [])), f"yorum #{r['id']} izni geri çekildi")
        return {"withdrawn": r["id"], **impact}

    # --- kişi izinleri ---------------------------------------------------------------
    def consent_add(self, profile_id: int, person_label: str, scope: str, consent_type: str, consent_date: str,
                    evidence_path: str, processing_scope: dict | None = None) -> dict:
        bid = self._brand_id(profile_id)
        self._profile(profile_id)
        if scope not in ("image", "voice", "image_voice"):
            raise AdMemoryError("kapsam: image | voice | image_voice")
        ev = self._evidence_path(profile_id, evidence_path)
        if not ev or not consent_type or not consent_date:
            raise AdMemoryError("açık rıza: tür, tarih ve kanıt dosyası zorunlu (bölüm 10)")
        with self.tx():
            cid = self.ex("""INSERT INTO person_consents(brand_id,person_label,scope,consent_type,consent_date,evidence_path,processing_scope_json,created_at)
                             VALUES(?,?,?,?,?,?,?,?)""", (bid, person_label, scope, consent_type, consent_date, ev, jdump(processing_scope), now_iso())).lastrowid
        return self.q1("SELECT * FROM person_consents WHERE id=?", (cid,))

    def consent_query(self, profile_id: int, include_withdrawn: bool = False) -> dict:
        bid = self._brand_id(profile_id)
        sql = "SELECT * FROM person_consents WHERE brand_id=?" + ("" if include_withdrawn else " AND withdrawn_at IS NULL")
        consents = self.qa(sql + " ORDER BY id", (bid,))
        unmatched = []
        for a in self.qa("SELECT id, path, people_json FROM assets WHERE profile_id=? AND people_json IS NOT NULL", (profile_id,)):
            for person in a["people_json"] or []:
                cid = person.get("consent_id")
                ok = cid and any(c["id"] == cid and not c["withdrawn_at"] for c in consents)
                if not ok:
                    unmatched.append({"asset_id": a["id"], "path": a["path"], "person": person.get("label")})
        return {"consents": consents, "assets_without_valid_consent": unmatched,
                "rule": "İzni olmayan ya da geri çekilmiş kişinin klibi kreatifte kullanılamaz (bölüm 10)."}

    def consent_withdraw(self, profile_id: int, consent_id: int, reason: str | None = None) -> dict:
        bid = self._brand_id(profile_id)
        c = self.q1("SELECT * FROM person_consents WHERE id=? AND brand_id=?", (int(consent_id), bid))
        if not c:
            raise AdMemoryError("izin kaydı bu profile ait değil")
        assets = [a["id"] for a in self.qa("SELECT id, people_json FROM assets WHERE profile_id=?", (profile_id,))
                  if any((p or {}).get("consent_id") == c["id"] for p in (a["people_json"] or []))]
        keys = {f"a{x}" for x in assets} | {str(x) for x in assets}
        with self.tx():
            self.ex("UPDATE person_consents SET withdrawn_at=COALESCE(withdrawn_at, ?) WHERE id=?", (now_iso(), c["id"]))
            impact = self._withdraw_impact(profile_id, lambda plan: any(
                (l.get("source") or {}).get("asset") in keys for s in plan.get("scenes", []) for l in s.get("layers", [])),
                f"kişi izni #{c['id']} ({c['person_label']}) geri çekildi")
        return {"withdrawn": c["id"], "assets": assets, **impact}

    def _withdraw_impact(self, profile_id: int, plan_uses, why: str) -> dict:
        """Varlık → plan → kreatif → reklam bağlarını tarar: yeni kullanım engellenir, yayınlanmamış paketler eskir,
        yayındaki reklamlar için insana durdurma/değiştirme adımı oluşturulur (bölüm 10). Plugin Meta'ya yazmaz."""
        bid = self._brand_id(profile_id)
        plans = [p for p in self.qa("""SELECT ep.id, ep.plan_json, ep.campaign_id, ep.cycle_id FROM edit_plans ep JOIN campaigns c ON c.id=ep.campaign_id
                                        WHERE c.brand_id=?""", (bid,)) if plan_uses(jload(p["plan_json"], {}))]
        plan_ids = [p["id"] for p in plans]
        creatives = self.qa(f"SELECT * FROM creatives WHERE edit_plan_id IN ({','.join('?' * len(plan_ids))})", tuple(plan_ids)) if plan_ids else []
        stale, actions = [], []
        for cr in creatives:
            launched = self.qa("SELECT * FROM ads WHERE brand_id=? AND creative_key=?", (bid, cr["creative_key"]))
            if launched:
                for ad in launched:
                    dk = f"consent:{ad['meta_ad_id']}"
                    if not self.q1("SELECT 1 FROM action_items WHERE campaign_id=? AND dedupe_key=? AND status IN ('proposed','approved')", (cr["campaign_id"], dk)):
                        aid = self.ex("""INSERT INTO action_items(campaign_id,cycle_id,action,target_meta_id,reason_kind,status,dedupe_key,evidence_json,created_at)
                                         VALUES(?,?,?,?, 'consent', 'proposed', ?, ?, ?)""",
                                      (cr["campaign_id"], cr["cycle_id"], f"Reklamı durdur ya da kişiyi/yorumu içermeyen sürümle değiştir: {ad['meta_ad_name'] or ad['meta_ad_id']}",
                                       ad["meta_ad_id"], dk, jdump([{"why": why, "at": now_iso()}]), now_iso())).lastrowid
                        actions.append(aid)
            else:
                self.ex("UPDATE creatives SET qc_status='stale' WHERE id=?", (cr["id"],))
                stale.append(cr["id"])
        return {"plans_affected": plan_ids, "creatives_marked_stale": stale, "human_actions_created": actions,
                "note": "Silme istenirse yerel kaynak, türev, dışa aktarım ve yedekler 8.8'e göre temizlenir; yayındaki içerik için insan işlemi takip edilir."}

    # --- yükleme öncesi izin kapısı ---------------------------------------------------
    def processing_permission_check(self, profile_id: int, provider: str, purpose: str, contains_personal_data: bool,
                                    data_kinds: list[str] | None = None, session_id: str | None = None,
                                    consent_ids: list[int] | None = None, review_ids: list[int] | None = None) -> dict:
        """Tanınabilir görüntü/ses, yorum ya da kişisel veri dış sağlayıcıya gitmeden ÖNCE (bölüm 10)."""
        bid = self._brand_id(profile_id)
        brand = self.q1("SELECT processing_permissions_json FROM brands WHERE id=?", (bid,))
        perms = brand["processing_permissions_json"] or {}
        if isinstance(perms, str):
            perms = jload(perms, {}) or {}
        reasons: list[str] = []
        allowed = True
        if contains_personal_data:
            basis = (perms.get("providers") or {}).get(provider) or {}
            if not (basis.get("basis") and basis.get("evidence")):
                allowed = False
                reasons.append(f"işletmenin {provider} için işleme/yurt dışı aktarım dayanağı ve belgesi kayıtlı değil (brands.processing_permissions_json)")
            for cid in consent_ids or []:
                c = self.q1("SELECT * FROM person_consents WHERE id=? AND brand_id=?", (int(cid), bid))
                scope = (c or {}).get("processing_scope_json") or {}
                if isinstance(scope, str):
                    scope = jload(scope, {}) or {}
                if not c or c["withdrawn_at"] or provider not in (scope.get("providers") or []):
                    allowed = False
                    reasons.append(f"kişi izni #{cid}: {provider} sağlayıcısına aktarım kapsamı yok ya da geri çekilmiş "
                                   "(reklamda gösterim izni sağlayıcıya yükleme izniyle eş tutulmaz)")
            for rid in review_ids or []:
                r = self.q1("SELECT * FROM reviews WHERE id=? AND brand_id=?", (int(rid), bid))
                scope = (r or {}).get("processing_scope_json") or {}
                if isinstance(scope, str):
                    scope = jload(scope, {}) or {}
                if not r or r["withdrawn_at"] or provider not in (scope.get("providers") or []):
                    allowed = False
                    reasons.append(f"yorum #{rid}: {provider} aktarım kapsamı yok ya da geri çekilmiş")
        result = {"allowed": allowed, "provider": provider, "purpose": purpose, "contains_personal_data": contains_personal_data,
                  "reasons": reasons,
                  "fallback": None if allowed else "Kişisel veri dışarı aktarılmaz; yerelde kimliksizleştirilmiş malzeme ya da kişisel veri içermeyen ürün çekimi kullanılır.",
                  "note": "Bu kayıt yalnızca izin/kanıt takibi yapar; plugin hukuki uygunluğu kendiliğinden belgeleyemez."}
        if session_id and allowed:
            s = self.session_get(session_id)
            ups = s.get("upload_permissions") or []
            ups.append({"profile_id": profile_id, "provider": provider, "purpose": purpose, "personal": contains_personal_data, "at": now_iso()})
            s["upload_permissions"] = ups[-20:]
            self._session_write(session_id, s)
            result["session_recorded"] = True
        return result
