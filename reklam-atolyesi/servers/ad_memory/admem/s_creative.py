"""Konsept, hook, hipotez, kurgu planı, sahne önbelleği, malzeme, kreatif ve ücretli üretim kayıtları."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from . import editplan, hashing, naming
from .util import AdMemoryError, atomic_write, jdump, jload, now_iso, parse_iso, sha256_file, utcnow

CONCEPT_SOURCES = ("evidence", "direction", "general", "product", "brand_doc", "competitor")
DECISIONS = ("accepted", "merged", "rejected", "deferred")
ROLES = ("proven", "gap", "counter", "free")


def _known(v: Any) -> set[str]:
    """Sözlük değer(ler)inin bilinen kısmı: boş ve 'unknown' fark sayılmaz (4.7, bölüm 10 ile aynı ilke)."""
    vals = v if isinstance(v, (list, tuple, set)) else [v]
    return {str(x).strip() for x in vals if x is not None and str(x).strip() and str(x).strip() != "unknown"}


class CreativeMixin:
    # --- sözlük doğrulaması (4.7) ------------------------------------------------
    def _validate_features(self, profile_id: int, features: dict | None) -> dict:
        if not features:
            return {}
        tax = self._taxonomy()
        fixed = tax["fixed_axes"]
        prof_axes = tax["profile_axes"]
        out = {}
        for axis, val in features.items():
            vals = val if isinstance(val, list) else [val]
            for v in vals:
                if v == "unknown":
                    continue
                if axis in fixed:
                    if v not in fixed[axis]["values"]:
                        raise AdMemoryError(f"sözlük: {axis}={v!r} sabit eksende yok (değer eklemek sözlük sürümü ister; 4.7)")
                elif axis in prof_axes:
                    if isinstance(v, str) and v.startswith("other:"):
                        continue
                    if not self.q1("SELECT 1 FROM taxonomy_values WHERE profile_id=? AND axis=? AND code=? AND status!='retired'",
                                   (profile_id, axis, v)):
                        raise AdMemoryError(f"sözlük: profil ekseni {axis}={v!r} bu profilde tanımlı değil; önce taxonomy_value_add (kullanıcıyla) ya da 'other:<kısa ad>'")
                else:
                    raise AdMemoryError(f"sözlük: bilinmeyen eksen {axis!r}")
            out[axis] = val
        return out

    # --- konsept ve hook (4.3) ------------------------------------------------------
    def concept_upsert(self, profile_id: int, campaign_id: int, cycle_id: int, code: str, name: str, source: str,
                       angle: str | None = None, decision: str | None = None, user_said: str | None = None,
                       rationale: str | None = None, competitive_role: str | None = None,
                       source_competitor_ad_ids: list[int] | None = None, features: dict | None = None,
                       sound_intent: str | None = None, hypothesis_id: int | None = None,
                       checkpoint: dict | None = None) -> dict:
        """Yeni konsept ya da güncelleme. Güncellemede verilmeyen (None) alanlar korunur; features eksen bazında birleşir (bir ekseni
        boşaltmak için 'unknown'). Ses niyeti ya da hipotez bağı gibi tek alanlı bir güncelleme kararı, alıcıyı ve sözlük özelliklerini
        silmez (1.4.5; S03 kapısı bu alanlara dayanır)."""
        c = self._campaign(profile_id, campaign_id)
        cy = self._cycle(profile_id, cycle_id, campaign_id)
        if c["stage"] != "S03":
            raise AdMemoryError(f"konsept kayıtları S03 konsept görüşmesinde yapılır (kampanya: {c['stage']})")
        if source not in CONCEPT_SOURCES:
            raise AdMemoryError(f"kaynak: {', '.join(CONCEPT_SOURCES)}")
        if decision is not None and decision not in DECISIONS:
            raise AdMemoryError(f"karar: {', '.join(DECISIONS)}")
        if decision is not None and not (user_said and user_said.strip()):
            raise AdMemoryError("konsept kararı kullanıcının ifadesiyle kaydedilir (user_said); Claude tek başına 'approved' yazamaz (4.3)")
        if competitive_role is not None and competitive_role not in ROLES:
            raise AdMemoryError(f"portföy rolü: {', '.join(ROLES)}")
        if source_competitor_ad_ids:
            for aid in source_competitor_ad_ids:
                r = self.q1("SELECT profile_id FROM competitor_ads WHERE id=?", (int(aid),))
                if not r or r["profile_id"] != int(profile_id):
                    raise AdMemoryError(f"rakip reklamı {aid} bu profile ait değil")
        feats = self._validate_features(profile_id, features)
        tv = self._taxonomy()["taxonomy_version"]
        with self.tx():
            ex = self.q1("SELECT * FROM concepts WHERE cycle_id=? AND code=?", (cy["id"], code))
            old = ex or {}

            def keep(new: Any, col: str) -> Any:
                return old.get(col) if new is None else new

            role = keep(competitive_role, "competitive_role")
            src_ids = source_competitor_ad_ids if source_competitor_ad_ids is not None else old.get("source_competitor_ad_ids_json")
            if source == "competitor" and role not in ("proven", "gap", "counter"):
                raise AdMemoryError("rakipten türeyen öneri proven | gap | counter rolü taşır (4.3)")
            if role in ("proven", "counter") and not src_ids:
                raise AdMemoryError("proven/counter konsept kaynak rakip reklam kimliklerini taşır (uzaklık kuralı için)")
            if ex:
                old_feats = old.get("features_json") if isinstance(old.get("features_json"), dict) else {}
                feats = {**old_feats, **feats} if features is not None else old_feats
            dec = keep(decision, "decision")
            status = "selected" if dec in ("accepted", "merged") else ("dropped" if dec == "rejected" else "proposed")
            vals = dict(campaign_id=c["id"], cycle_id=cy["id"], code=code, name=name, angle=keep(angle, "angle"), source=source,
                        decision=dec, status=status, rationale=keep(rationale, "rationale"), competitive_role=role,
                        source_competitor_ad_ids_json=jdump(src_ids) if src_ids else None,
                        features_json=jdump(feats) if feats else None, taxonomy_version=tv,
                        sound_intent=keep(sound_intent, "sound_intent"), hypothesis_id=keep(hypothesis_id, "hypothesis_id"),
                        updated_at=now_iso())
            if ex:
                if ex["distance_check_json"] and (features is not None or source_competitor_ad_ids is not None):
                    vals["distance_check_json"] = None  # içerik değişti: uzaklık kontrolü yeniden
                self.ex(f"UPDATE concepts SET {', '.join(f'{k}=?' for k in vals)} WHERE id=?", (*vals.values(), ex["id"]))
                kid = ex["id"]
            else:
                vals["created_at"] = now_iso()
                kid = self.ex(f"INSERT INTO concepts({', '.join(vals)}) VALUES({', '.join('?' * len(vals))})", tuple(vals.values())).lastrowid
            if decision:
                self._decision_insert(profile_id, c["id"], cy["id"], None, None, "S03", None, f"concept:{code}:{decision}",
                                      f"kullanıcı: «{user_said.strip()}»" + (f" — {rationale}" if rationale else ""), "user")
            if checkpoint:
                self._checkpoint_in_tx(profile_id, "S03", checkpoint, c["id"], cy["id"])
        return self.q1("SELECT * FROM concepts WHERE id=?", (kid,))

    def hook_upsert(self, profile_id: int, concept_id: int, code: str, first_frame_type: str, first_frame_desc: str,
                    first_motion: str, first_sound: str, text: str, vo: str | None = None, duration_s: float = 1.5,
                    decision: str | None = None, user_said: str | None = None, reserve: bool | None = None,
                    checkpoint: dict | None = None) -> dict:
        """Hook = dört parça + metin. Güncellemede verilmeyen karar ve yedek (reserve) işareti korunur (1.4.5); yeni hook'ta reserve
        verilmezse test hook'udur."""
        k = self.q1("SELECT * FROM concepts WHERE id=?", (int(concept_id),))
        if not k:
            raise AdMemoryError("konsept yok")
        c = self._campaign(profile_id, k["campaign_id"])
        if c["stage"] != "S03":
            raise AdMemoryError("hook kayıtları S03'te yapılır")
        for name, v in (("first_frame_desc", first_frame_desc), ("first_motion", first_motion), ("first_sound", first_sound)):
            if not v or not str(v).strip():
                raise AdMemoryError(f"hook dört parçadan oluşur; {name} boş olamaz (4.3)")
        if text is None:
            raise AdMemoryError("hook metni (ekran yazısı) alanı belirtilmeli; yoksa boş metin")
        self._validate_features(profile_id, {"first_frame": first_frame_type})
        if not (0.5 <= float(duration_s) <= 3.0):
            raise AdMemoryError("hook ilk 1–2 saniyedir; süre 0,5–3 sn aralığında olmalı")
        if decision is not None and decision not in DECISIONS:
            raise AdMemoryError(f"karar: {', '.join(DECISIONS)}")
        if decision is not None and not (user_said and user_said.strip()):
            raise AdMemoryError("hook kararı kullanıcının ifadesiyle kaydedilir (user_said)")
        with self.tx():
            ex = self.q1("SELECT * FROM hooks WHERE concept_id=? AND code=?", (k["id"], code))
            dec = decision if decision is not None or not ex else ex["decision"]
            res = (1 if reserve else 0) if reserve is not None or not ex else ex["reserve"]
            vals = dict(concept_id=k["id"], code=code, first_frame_type=first_frame_type, first_frame_desc=first_frame_desc,
                        first_motion=first_motion, first_sound=first_sound, text=text, vo=vo, duration_s=float(duration_s),
                        decision=dec, reserve=res)
            if ex:
                self.ex(f"UPDATE hooks SET {', '.join(f'{x}=?' for x in vals)} WHERE id=?", (*vals.values(), ex["id"]))
                hid = ex["id"]
            else:
                vals["created_at"] = now_iso()
                hid = self.ex(f"INSERT INTO hooks({', '.join(vals)}) VALUES({', '.join('?' * len(vals))})", tuple(vals.values())).lastrowid
            if decision:
                self._decision_insert(profile_id, c["id"], k["cycle_id"], None, None, "S03", None, f"hook:{k['code']}/{code}:{decision}",
                                      f"kullanıcı: «{user_said.strip()}»", "user")
            if checkpoint:
                self._checkpoint_in_tx(profile_id, "S03", checkpoint, c["id"], k["cycle_id"])
        h = self.q1("SELECT * FROM hooks WHERE id=?", (hid,))
        sibling = self.qa("SELECT code, first_frame_type, first_motion, first_sound FROM hooks WHERE concept_id=? AND id!=?", (k["id"], hid))
        same = [s["code"] for s in sibling if s["first_frame_type"] == first_frame_type and s["first_motion"] == first_motion
                and s["first_sound"] == first_sound]
        if same:
            h["andromeda_note"] = (f"{', '.join(same)} ile açılış karesi/ilk hareket/ilk ses aynı: yalnızca metin farkı aynı varlık "
                                   "sayılır (4.3); yedek (reserve) işaretlenmesi önerilir")
        return h

    def hooks_export_csv(self, profile_id: int, campaign_id: int, cycle_id: int) -> dict:
        c = self._campaign(profile_id, campaign_id)
        cy = self._cycle(profile_id, cycle_id, campaign_id)
        rows = self.qa("""SELECT k.code AS concept, h.code AS hook, h.duration_s, h.vo, h.first_frame_type, h.first_frame_desc,
                                 h.first_motion, h.first_sound, h.text, h.reserve, h.decision
                          FROM hooks h JOIN concepts k ON k.id=h.concept_id
                          WHERE k.cycle_id=? AND k.decision IN ('accepted','merged') AND h.decision IN ('accepted','merged')
                          ORDER BY k.code, h.code""", (cy["id"],))
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["konsept", "hook", "sure_s", "format", "vo", "acilis_karesi_turu", "acilis_karesi", "ilk_hareket", "ilk_ses",
                    "metin", "rol"])
        for r in rows:
            for fmt in ("9x16", "4x5"):
                w.writerow([r["concept"], r["hook"], r["duration_s"], fmt, "var" if r["vo"] else "yok", r["first_frame_type"],
                            r["first_frame_desc"], r["first_motion"], r["first_sound"], r["text"], "yedek" if r["reserve"] else "test"])
        path = self.campaign_dir(profile_id, campaign_id) / f"c{cy['cycle']}-hooks.csv"
        if path.exists():
            raise AdMemoryError(f"{path.name} zaten var; önceki dosyanın üzerine yazılmaz (sürüm adıyla yeniden üretin)")
        sha = atomic_write(path, buf.getvalue(), overwrite=False)
        return {"path": str(path), "sha256": sha, "rows": len(rows)}

    # --- S03 test portföyü: farklı alıcı, tek açılış (4.3, 4.7; 1.4.5) --------------------------
    def concept_diversity_check(self, profile_id: int, campaign_id: int, cycle_id: int) -> dict:
        """S03 kapısının çeşitlilik denetimi; görüşme sırasında da çağrılır, hiçbir şey yazmaz."""
        self._campaign(profile_id, campaign_id)
        cy = self._cycle(profile_id, cycle_id, campaign_id)
        return self._s03_portfolio_check(cy["id"])

    def _s03_portfolio_check(self, cycle_id: int) -> dict:
        """Keşif konsepti: seçilmiş (accepted|merged), birincil doğrulama hipotezine bağlı olmayan ve en az bir test (yedek olmayan) hook'u
        olan konsept. Her keşif konseptinin tek test hook'u ve tek alıcısı (buyer) olur; keşif konseptleri ikişer ikişer farklı alıcıya
        konuşur ve diversity_axes'ten en az diversity_min_axes kadarında farklıdır. Açılış karesi test hook'undan okunur. Bilinmeyen
        (unknown) ya da boş değer fark sayılmaz. Doğrulama çifti (birincil hipotez) muaftır; tümüyle yedek konsept bu turda test edilmez."""
        tax = self._taxonomy()
        axes = list(tax["diversity_axes"])
        distinct = tax.get("diversity_distinct_axis") or "buyer"
        min_axes = int(tax.get("diversity_min_axes", 2))
        prim = self.q1("SELECT id FROM hypotheses WHERE cycle_id=? AND is_primary=1", (cycle_id,))
        sel = self.qa("SELECT * FROM concepts WHERE cycle_id=? AND decision IN ('accepted','merged') ORDER BY code", (cycle_id,))
        explore: list[dict] = []
        validation, reserve_only, issues = [], [], []
        for k in sel:
            if prim and k["hypothesis_id"] == prim["id"]:
                validation.append(k["code"])
                continue
            tests = self.qa("""SELECT code, first_frame_type FROM hooks WHERE concept_id=? AND decision IN ('accepted','merged')
                               AND reserve=0 ORDER BY code""", (k["id"],))
            if not tests:
                reserve_only.append(k["code"])
                continue
            feats = k["features_json"] if isinstance(k["features_json"], dict) else {}
            vals = {ax: _known(feats.get(ax)) for ax in axes}
            if "first_frame" in vals and len(tests) == 1 and _known(tests[0]["first_frame_type"]):
                vals["first_frame"] = _known(tests[0]["first_frame_type"])
            buyer = _known(feats.get(distinct))
            if len(tests) > 1:
                issues.append(f"konsept {k['code']}: keşifte tek test açılışı olur, {len(tests)} test hook'u var "
                              f"({', '.join(t['code'] for t in tests)}); birini seçin, diğerleri yedek (reserve) kalsın. "
                              "Aynı konseptin açılış karşılaştırması yalnızca birincil doğrulama çiftiyle yapılır (6.6)")
            if not buyer:
                issues.append(f"konsept {k['code']}: kime konuştuğu ({distinct}) kayıtlı değil; görüşmede kullanıcıyla seçilir")
            elif len(buyer) > 1:
                issues.append(f"konsept {k['code']}: tek bir alıcıya konuşur ({distinct}: {', '.join(sorted(buyer))})")
            explore.append({"code": k["code"], "buyer": buyer, "vals": vals, "tests": [t["code"] for t in tests]})
        pairs = []
        for i, a in enumerate(explore):
            for b in explore[i + 1:]:
                same_buyer = sorted(a["buyer"] & b["buyer"])
                differing = [ax for ax in axes if a["vals"][ax] and b["vals"][ax] and not (a["vals"][ax] & b["vals"][ax])]
                pairs.append({"concepts": [a["code"], b["code"]], "same_buyer": same_buyer, "differing_axes": differing})
                if same_buyer:
                    issues.append(f"konsept {a['code']} ve {b['code']} aynı alıcıya konuşuyor ({distinct}: {', '.join(same_buyer)}); "
                                  "keşifte her konsept farklı bir alıcıya konuşur")
                if len(differing) < min_axes:
                    issues.append(f"konsept {a['code']} ve {b['code']} yalnızca {len(differing)} eksende farklı "
                                  f"({', '.join(differing) or 'hiçbiri'}); {', '.join(axes)} eksenlerinden en az {min_axes} gerekir, "
                                  "bilinmeyen eksen fark sayılmaz")
        return {"passed": not issues, "issues": issues,
                "exploration": [{"code": e["code"], "buyer": sorted(e["buyer"]), "test_hooks": e["tests"],
                                 "axes": {ax: sorted(v) for ax, v in e["vals"].items()}} for e in explore],
                "pairs": pairs, "validation": validation, "reserve_only": reserve_only,
                "rule": {"distinct_axis": distinct, "diversity_axes": axes, "min_axes": min_axes, "test_hooks_per_concept": 1}}

    # --- hipotezler (4.3, 6.6, 6.14) ---------------------------------------------------
    def hypothesis_add(self, profile_id: int, statement: str, metric: str, campaign_id: int | None = None,
                       cycle_id: int | None = None, feature: str | None = None, concept_id: int | None = None,
                       is_primary: bool = False, pre_registration: dict | None = None, status: str = "open") -> dict:
        self._profile(profile_id)
        if campaign_id is not None:
            self._campaign(profile_id, campaign_id)
        if cycle_id is not None:
            cy = self._cycle(profile_id, cycle_id, campaign_id)
        if status not in ("open", "testing"):
            raise AdMemoryError("yeni hipotez open ya da testing olarak doğar")
        ev: dict[str, Any] = {}
        if is_primary:
            if cycle_id is None:
                raise AdMemoryError("birincil doğrulama hipotezi bir tura bağlı olmalı")
            if self.q1("SELECT 1 FROM hypotheses WHERE cycle_id=? AND is_primary=1", (cycle_id,)):
                raise AdMemoryError("bu turda zaten bir birincil doğrulama hipotezi var (tur başına en fazla bir; 6.6)")
            need = ("arm_a", "arm_b", "metric", "direction")
            if not pre_registration or any(k not in pre_registration for k in need):
                raise AdMemoryError("birincil hipotez test öncesi sabitlenir: pre_registration {arm_a, arm_b, metric, direction, comparison_ids}")
            if cy["test_start"] and parse_iso(cy["test_start"]) <= utcnow():
                raise AdMemoryError("test başladıktan sonra birincil hipotez sabitlenemez (6.6)")
            ev["pre_registration"] = {**pre_registration, "registered_at": now_iso()}
        with self.tx():
            hid = self.ex("""INSERT INTO hypotheses(campaign_id,cycle_id,profile_id,statement,metric,feature,status,is_primary,evidence_json,created_at,updated_at)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                          (campaign_id, cycle_id, profile_id, statement, metric, feature, status, 1 if is_primary else 0,
                           jdump(ev), now_iso(), now_iso())).lastrowid
            if concept_id:
                k = self.q1("SELECT * FROM concepts WHERE id=?", (int(concept_id),))
                if not k or k["campaign_id"] != campaign_id:
                    raise AdMemoryError("konsept bu kampanyada değil")
                self.ex("UPDATE concepts SET hypothesis_id=? WHERE id=?", (hid, k["id"]))
        return self.q1("SELECT * FROM hypotheses WHERE id=?", (hid,))

    def hypothesis_update(self, profile_id: int, hypothesis_id: int, status: str | None = None,
                          evidence: dict | None = None, note: str | None = None) -> dict:
        h = self.q1("SELECT * FROM hypotheses WHERE id=?", (int(hypothesis_id),))
        if not h or h["profile_id"] != int(profile_id):
            raise AdMemoryError("hipotez bu profile ait değil")
        if status and status not in ("open", "testing", "supported", "rejected", "inconclusive"):
            raise AdMemoryError("durum: open | testing | supported | rejected | inconclusive")
        ev = jload(h["evidence_json"], {}) if isinstance(h["evidence_json"], str) else (h["evidence_json"] or {})
        if "pre_registration" in (evidence or {}):
            raise AdMemoryError("ön kayıt değiştirilemez (test öncesi sabitlenir)")
        if evidence:
            ev.setdefault("updates", []).append({**evidence, "at": now_iso(), "note": note})
        with self.tx():
            self.ex("UPDATE hypotheses SET status=COALESCE(?, status), evidence_json=?, updated_at=? WHERE id=?",
                    (status, jdump(ev), now_iso(), h["id"]))
        return self.q1("SELECT * FROM hypotheses WHERE id=?", (h["id"],))

    def hypothesis_list(self, profile_id: int, campaign_id: int | None = None, status: str | None = None) -> dict:
        self._profile(profile_id, allow_archived=True)
        sql = "SELECT * FROM hypotheses WHERE profile_id=?"
        args: list[Any] = [profile_id]
        if campaign_id is not None:
            sql += " AND campaign_id=?"
            args.append(campaign_id)
        if status:
            sql += " AND status=?"
            args.append(status)
        return {"hypotheses": self.qa(sql + " ORDER BY id", tuple(args))}

    # --- kurgu planı (5.2) --------------------------------------------------------
    def _plan_context(self, profile_id: int, campaign_id: int, plan: dict) -> tuple[dict | None, dict]:
        style = None
        sp = plan.get("style")
        if sp:
            p = Path(sp)
            if not p.is_absolute():
                cand = [self.campaign_dir(profile_id, campaign_id) / p, self.profile_dir(profile_id) / p, self.data_dir / p]
                p = next((x for x in cand if x.exists()), cand[0])
            if p.exists():
                style = json.loads(p.read_text(encoding="utf-8"))
                style["__path"] = str(p)
                style["__sha256"] = sha256_file(p)
        index: dict[str, dict] = {}
        for s in plan.get("scenes", []):
            for l in s.get("layers", []):
                a = (l.get("source") or {}).get("asset")
                if a and a not in index:
                    aid = a[1:] if a.startswith("a") and a[1:].isdigit() else (a if a.isdigit() else None)
                    row = self.q1("SELECT * FROM assets WHERE id=? AND profile_id=?", (int(aid), profile_id)) if aid else \
                        self.q1("SELECT * FROM assets WHERE profile_id=? AND (shot_no=? OR path LIKE ?)", (profile_id, a, f"%{a}%"))
                    if row:
                        audio = row["audio_json"] if isinstance(row["audio_json"], dict) else jload(row["audio_json"], {}) or {}
                        index[a] = {"id": row["id"], "kind": row["kind"], "path": row["path"],
                                    "speaking_person": bool(audio.get("speech_detected") and audio.get("person_on_camera"))}
                    else:
                        index[a] = {"missing": True}
        return style, index

    def edit_plan_validate(self, profile_id: int, campaign_id: int, plan: dict | None = None, plan_id: int | None = None,
                           beats: list[float] | None = None) -> dict:
        self._campaign(profile_id, campaign_id)
        if plan is None:
            if plan_id is None:
                raise AdMemoryError("plan ya da plan_id")
            row = self._plan_row(profile_id, plan_id)
            plan = jload(row["plan_json"], {}) if isinstance(row["plan_json"], str) else row["plan_json"]
        style, index = self._plan_context(profile_id, campaign_id, plan)
        rep = editplan.validate(plan, style=style, beats=beats, asset_index=index)
        if style is None and plan.get("style"):
            rep["warnings"].append(f"stil dosyası bulunamadı: {plan.get('style')} (efekt bütçesi varsayılanla denetlendi)")
        if plan.get("status") == "ready" and style is not None and plan.get("style_snapshot_sha256") and plan["style_snapshot_sha256"] != style["__sha256"]:
            rep["errors"].append("style_snapshot_sha256 bağlanan stil kopyasının hash'iyle uyuşmuyor (5.6)")
        missing_assets = [k for k, v in index.items() if v.get("missing")]
        if missing_assets and plan.get("status") == "ready":
            rep["errors"].append("kayıtlı olmayan varlıklar: " + ", ".join(missing_assets))
        for s in plan.get("scenes", []):
            for l in s.get("layers", []):
                if l.get("component") == "ReviewCard" and l.get("review_id"):
                    r = self.q1("""SELECT r.* FROM reviews r JOIN profiles p ON p.brand_id=r.brand_id WHERE r.id=? AND p.id=?""",
                                (int(l["review_id"]), profile_id))
                    if not r:
                        rep["errors"].append(f"ReviewCard yorumu {l['review_id']} bu profilde yok")
                    elif r["withdrawn_at"] or not r["consent_evidence_path"]:
                        rep["errors"].append(f"ReviewCard yorumu {l['review_id']}: izin kanıtı yok ya da geri çekilmiş (bölüm 10)")
        rep["valid"] = not rep["errors"]
        return rep

    def _plan_row(self, profile_id: int, plan_id: int) -> dict:
        row = self.q1("SELECT * FROM edit_plans WHERE id=?", (int(plan_id),))
        if not row:
            raise AdMemoryError(f"kurgu planı yok: {plan_id}")
        self._campaign(profile_id, row["campaign_id"])
        return row

    def edit_plan_save(self, profile_id: int, campaign_id: int, cycle_id: int, plan: dict, parent_id: int | None = None) -> dict:
        c = self._campaign(profile_id, campaign_id)
        cy = self._cycle(profile_id, cycle_id, campaign_id)
        rep = self.edit_plan_validate(profile_id, campaign_id, plan=plan)
        schema_errors = [e for e in rep["errors"] if e.startswith("şema:")]
        if schema_errors or (plan.get("status") == "ready" and rep["errors"]):
            raise AdMemoryError("kurgu planı doğrulanamadı: " + " | ".join(rep["errors"][:12]))
        concept = self.q1("SELECT id FROM concepts WHERE cycle_id=? AND code=?", (cy["id"], plan.get("concept")))
        hook = self.q1("SELECT id FROM hooks WHERE concept_id=? AND code=?", (concept["id"], plan.get("hook"))) if concept else None
        if plan.get("purpose") == "production" and not concept:
            raise AdMemoryError(f"plan konsepti ({plan.get('concept')}) bu turda yok")
        ver = int(plan["version"])
        prev = self.q1("""SELECT MAX(version) AS v FROM edit_plans WHERE cycle_id=? AND COALESCE(concept_id,0)=? AND COALESCE(hook_id,0)=?
                          AND format=? AND purpose=?""", (cy["id"], concept["id"] if concept else 0, hook["id"] if hook else 0,
                                                          plan["format"], plan["purpose"]))
        if prev and prev["v"] and ver <= prev["v"]:
            ver = prev["v"] + 1
            plan = {**plan, "version": ver}
        if rep["computed"].get("ai_share") is not None:
            plan.setdefault("provenance", {})
            plan["provenance"]["ai_share"] = rep["computed"]["ai_share"]
            plan["provenance"]["ai_layers"] = rep["computed"]["ai_layers"]
        name = f"c{cy['cycle']}_{plan.get('concept')}_{plan.get('hook')}_{plan['format']}_{plan['purpose']}_v{ver}.json"
        path = self.campaign_dir(profile_id, campaign_id) / "edit_plans" / name
        text = json.dumps(plan, ensure_ascii=False, indent=1)
        sha = atomic_write(path, text, overwrite=False)
        with self.tx():
            pid = self.ex("""INSERT INTO edit_plans(campaign_id,cycle_id,concept_id,hook_id,format,purpose,status,version,plan_json,sha256,parent_id,path,created_at)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (c["id"], cy["id"], concept["id"] if concept else None, hook["id"] if hook else None, plan["format"],
                           plan["purpose"], plan["status"], ver, text, sha, parent_id, str(path), now_iso())).lastrowid
        return {"plan_id": pid, "path": str(path), "sha256": sha, "version": ver, "validation": rep}

    def edit_plan_get(self, profile_id: int, plan_id: int) -> dict:
        row = self._plan_row(profile_id, plan_id)
        row["plan"] = jload(row.pop("plan_json"), {})
        return row

    def edit_plan_patch(self, profile_id: int, plan_id: int, ops: list[dict]) -> dict:
        row = self._plan_row(profile_id, plan_id)
        plan = jload(row["plan_json"], {})
        try:
            new = editplan.apply_patch(plan, ops)
        except (KeyError, IndexError, ValueError) as e:
            raise AdMemoryError(f"yama uygulanamadı: {e}")
        new["variant_of"] = row["id"]
        return self.edit_plan_save(profile_id, row["campaign_id"], row["cycle_id"], new, parent_id=row["id"])

    # --- sahne önbelleği (5.21) ---------------------------------------------------
    def scene_cache_get(self, profile_id: int, key: str) -> dict:
        self._profile(profile_id)
        r = self.q1("SELECT * FROM scene_cache WHERE key=? AND profile_id=?", (key, profile_id))
        if not r:
            return {"hit": False}
        p = Path(r["path"])
        if not p.exists() or sha256_file(p) != r["sha256"]:
            with self.tx():
                self.ex("DELETE FROM scene_cache WHERE key=?", (key,))
            return {"hit": False, "note": "önbellek dosyası yok ya da hash uyuşmuyor; kısmi dosya kullanılmaz"}
        return {"hit": True, "path": r["path"], "sha256": r["sha256"], "meta": r["meta_json"]}

    def scene_cache_put(self, profile_id: int, key: str, path: str, campaign_id: int | None = None, meta: dict | None = None) -> dict:
        self._profile(profile_id)
        p = Path(path)
        if not p.exists() or p.stat().st_size == 0:
            raise AdMemoryError("yalnızca bitmiş ve doğrulanmış dosya önbelleğe alınır")
        sha = sha256_file(p)
        with self.tx():
            self.ex("""INSERT INTO scene_cache(key,profile_id,campaign_id,path,sha256,meta_json,created_at) VALUES(?,?,?,?,?,?,?)
                       ON CONFLICT(key) DO UPDATE SET path=excluded.path, sha256=excluded.sha256, meta_json=excluded.meta_json, created_at=excluded.created_at""",
                    (key, profile_id, campaign_id, str(p), sha, jdump(meta), now_iso()))
        return {"key": key, "sha256": sha}

    # --- malzeme ve çekim kütüphanesi (5.4, 5.5) ------------------------------------
    def asset_register(self, profile_id: int, kind: str, path: str, campaign_id: int | None = None,
                       product_id: int | None = None, source: str | None = None, shot_no: str | None = None,
                       score: dict | None = None, best_ranges: list | None = None, tags: list[str] | None = None,
                       audio: dict | None = None, people: list | None = None, meta: dict | None = None,
                       notes: str | None = None) -> dict:
        self._profile(profile_id)
        if campaign_id is not None:
            self._campaign(profile_id, campaign_id)
        if product_id is not None:
            self._product(profile_id, product_id)
        p = Path(path)
        if not p.is_absolute():
            p = self.data_dir / p
        if not p.exists():
            raise AdMemoryError(f"varlık dosyası yok: {p}")
        sha = sha256_file(p)
        with self.tx():
            ex = self.q1("SELECT * FROM assets WHERE profile_id=? AND sha256=?", (profile_id, sha))
            vals = {"kind": kind, "path": str(p), "source": source, "shot_no": shot_no, "score_json": jdump(score),
                    "best_ranges_json": jdump(best_ranges), "tags": ",".join(tags) if tags else None, "audio_json": jdump(audio),
                    "people_json": jdump(people), "meta_json": jdump(meta), "notes": notes,
                    "campaign_id": campaign_id, "product_id": product_id}
            if ex:
                upd = {k: v for k, v in vals.items() if v is not None}
                if upd:
                    self.ex(f"UPDATE assets SET {', '.join(f'{k}=?' for k in upd)} WHERE id=?", (*upd.values(), ex["id"]))
                aid = ex["id"]
            else:
                cols = ["profile_id", "sha256", "created_at", *vals.keys()]
                aid = self.ex(f"INSERT INTO assets({', '.join(cols)}) VALUES({', '.join('?' * len(cols))})",
                              (profile_id, sha, now_iso(), *vals.values())).lastrowid
        return self.q1("SELECT * FROM assets WHERE id=?", (aid,))

    def asset_query(self, profile_id: int, scope: str = "campaign", campaign_id: int | None = None, kind: str | None = None,
                    tag: str | None = None, shot_no: str | None = None, min_score: float | None = None, limit: int = 200) -> dict:
        self._profile(profile_id, allow_archived=True)
        if scope not in ("campaign", "profile"):
            raise AdMemoryError("scope: campaign | profile (profile = çekim kütüphanesi, 5.5)")
        sql = "SELECT * FROM assets WHERE profile_id=?"
        args: list[Any] = [profile_id]
        if scope == "campaign":
            if campaign_id is None:
                raise AdMemoryError("scope=campaign için campaign_id")
            self._campaign(profile_id, campaign_id)
            sql += " AND campaign_id=?"
            args.append(campaign_id)
        if kind:
            sql += " AND kind=?"
            args.append(kind)
        if tag:
            sql += " AND (','||tags||',') LIKE ?"
            args.append(f"%,{tag},%")
        if shot_no:
            sql += " AND shot_no=?"
            args.append(shot_no)
        rows = self.qa(sql + " ORDER BY id LIMIT ?", (*args, int(limit)))
        if min_score is not None:
            rows = [r for r in rows if (r["score_json"] or {}).get("overall", 0) >= min_score]
        for r in rows:
            used = r["used_in_json"] or []
            r["used_as_opening"] = [u for u in used if u.get("role") == "opening"]
        return {"assets": rows, "count": len(rows)}

    def asset_mark_used(self, profile_id: int, asset_id: int, creative_key: str, role: str = "body") -> dict:
        a = self.q1("SELECT * FROM assets WHERE id=? AND profile_id=?", (int(asset_id), profile_id))
        if not a:
            raise AdMemoryError("varlık bu profile ait değil")
        used = a["used_in_json"] or []
        if not any(u.get("creative_key") == creative_key and u.get("role") == role for u in used):
            used.append({"creative_key": creative_key, "role": role, "at": now_iso()})
        with self.tx():
            self.ex("UPDATE assets SET used_in_json=? WHERE id=?", (jdump(used), a["id"]))
        return {"asset_id": a["id"], "used_in": used}

    # --- kreatifler (5.16, 5.18) ------------------------------------------------------
    def creative_register(self, profile_id: int, campaign_id: int, cycle_id: int, file_path: str, delivery_role: str,
                          edit_plan_id: int | None = None, style_direction: str | None = None, music_bpm: float | None = None,
                          ai_share: float = 0.0, features: dict | None = None, duration_s: float | None = None) -> dict:
        c = self._campaign(profile_id, campaign_id)
        cy = self._cycle(profile_id, cycle_id, campaign_id)
        p = Path(file_path)
        if not p.is_absolute():
            p = self.data_dir / p
        if not p.exists():
            raise AdMemoryError(f"dosya yok: {p}")
        parsed = naming.parse_file_name(p.name)
        if not parsed:
            raise AdMemoryError(f"dosya adı adlandırma kuralına uymuyor (5.18): {p.name}")
        if parsed["cycle"] != f"c{cy['cycle']}":
            raise AdMemoryError(f"dosya adı turu ({parsed['cycle']}) bu tur (c{cy['cycle']}) değil")
        if delivery_role not in ("test", "reserve"):
            raise AdMemoryError("delivery_role: test | reserve")
        concept = self.q1("SELECT * FROM concepts WHERE cycle_id=? AND code=?", (cy["id"], parsed["concept"]))
        hook = self.q1("SELECT * FROM hooks WHERE concept_id=? AND code=?", (concept["id"], parsed["hook"])) if concept else None
        feats = self._validate_features(profile_id, features)
        if concept and concept["competitive_role"]:
            feats = {**feats, "competitive_role": concept["competitive_role"]}
        sha = sha256_file(p)
        key = parsed["creative_key"]
        with self.tx():
            ex = self.q1("SELECT * FROM creatives WHERE campaign_id=? AND creative_key=? AND format=? AND card_index=?",
                         (c["id"], key, parsed["format"], parsed["card_index"]))
            if ex:
                if ex["sha256"] != sha:
                    raise AdMemoryError(f"{key}/{parsed['format']} farklı içerikle zaten kayıtlı; üzerine yazılmaz, yeni revizyon (r{int(parsed['rev'][1:]) + 1}) açın (5.18)")
                return {**ex, "idempotent": True}
            if delivery_role == "test":
                if hook and hook["reserve"]:
                    raise AdMemoryError(f"hook {parsed['concept']}/{parsed['hook']} S03'te yedek seçildi: keşifte konsept başına tek test "
                                        "açılışı olur (4.3); bu çıktı 'reserve' olarak kaydedilmeli ya da hook rolü S03'te değiştirilmeli")
                keys = {r["creative_key"] for r in self.qa("SELECT DISTINCT creative_key FROM creatives WHERE cycle_id=? AND delivery_role='test'", (cy["id"],))}
                keys.add(key)
                bp = jload(cy["budget_plan_json"], {}) or {}
                cap = bp.get("allowed_test_ads")
                if cap is not None and len(keys) > int(cap):
                    raise AdMemoryError(f"test reklamı tavanı aşılıyor ({len(keys)} > {cap}); bu çıktı 'reserve' olarak kaydedilmeli (5.16, 6.3)")
            cid = self.ex("""INSERT INTO creatives(campaign_id,cycle_id,concept_id,hook_id,edit_plan_id,creative_key,file_path,file_name,sha256,
                             media_type,source_variant,card_index,delivery_role,duration_s,format,style_direction,music_bpm,has_vo,ai_share,
                             features_json,taxonomy_version,revision,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (c["id"], cy["id"], concept["id"] if concept else None, hook["id"] if hook else None, edit_plan_id, key,
                           str(p), p.name, sha, parsed["media"], parsed["source"], parsed["card_index"], delivery_role,
                           duration_s if duration_s is not None else (None if parsed["duration"] == "na" else float(parsed["duration"])),
                           parsed["format"], style_direction, music_bpm, 1 if parsed["vo"] == "vo" else 0, float(ai_share),
                           jdump(feats), self._taxonomy()["taxonomy_version"], int(parsed["rev"][1:]), now_iso())).lastrowid
        return self.q1("SELECT * FROM creatives WHERE id=?", (cid,))

    def creative_list(self, profile_id: int, campaign_id: int, cycle_id: int | None = None) -> dict:
        self._campaign(profile_id, campaign_id)
        sql = "SELECT * FROM creatives WHERE campaign_id=?"
        args: list[Any] = [campaign_id]
        if cycle_id is not None:
            sql += " AND cycle_id=?"
            args.append(cycle_id)
        return {"creatives": self.qa(sql + " ORDER BY creative_key, format, card_index", tuple(args))}

    def creative_set_qc(self, profile_id: int, campaign_id: int, creative_ids: list[int], status: str, report_path: str | None = None) -> dict:
        self._campaign(profile_id, campaign_id)
        if status not in ("passed", "failed", "pending"):
            raise AdMemoryError("status: passed | failed | pending")
        if status == "passed" and not report_path:
            raise AdMemoryError("QC 'passed' kaydı QC raporu yolunu ister")
        with self.tx():
            n = 0
            for cid in creative_ids:
                n += self.ex("UPDATE creatives SET qc_status=? WHERE id=? AND campaign_id=?", (status, int(cid), campaign_id)).rowcount
        return {"updated": n, "status": status, "report": report_path}

    # --- ücretli üretim (9.1) --------------------------------------------------------
    def generation_hash(self, tool_name: str, params: dict, input_file_hashes: dict | None = None) -> dict:
        return {"params_hash": hashing.params_hash(tool_name, params, None, input_file_hashes),
                "canonical": hashing.canonical_params(tool_name, params, None, input_file_hashes),
                "count": hashing.generation_count(tool_name, params)}

    def generation_log(self, profile_id: int, campaign_id: int, cycle_id: int | None, tool_name: str, params: dict,
                       estimate_credits: float | None, provider: str = "elevenlabs", model: str | None = None,
                       kind: str | None = None, input_file_hashes: dict | None = None, new_take: bool = False,
                       flow_snapshot_sha256: str | None = None) -> dict:
        self._campaign(profile_id, campaign_id)
        if cycle_id is not None:
            self._cycle(profile_id, cycle_id, campaign_id)
        classes = hashing.load_tool_classes()
        bare = hashing.bare_tool_name(tool_name)
        if bare not in classes["paid"]:
            raise AdMemoryError(f"{bare} ücretli araç listesinde değil; generations kaydı ücretli çağrılar içindir")
        if estimate_credits is None:
            raise AdMemoryError("önce estimate_only ile fiyat alınır; tahmin olmadan kayıt açılmaz (9.1)")
        if bare == "creative_run_flow_nodes" and not flow_snapshot_sha256:
            raise AdMemoryError("flow düğümü çalıştırma için creative_get_flow ile alınan flow görüntüsünün hash'i (flow_snapshot_sha256) gerekir")
        h = hashing.params_hash(tool_name, params, classes, input_file_hashes)
        with self.tx():
            rows = self.qa("SELECT * FROM generations WHERE campaign_id=? AND params_hash=? ORDER BY request_no", (campaign_id, h))
            open_rows = [r for r in rows if r["status"] in ("running", "unknown")]
            if open_rows:
                return {**open_rows[-1], "blocked": True,
                        "note": "aynı talep sürüyor ya da sonucu belirsiz; otomatik yeniden çağrı yok, önce uzlaştırma (9.1)"}
            last = rows[-1] if rows else None
            if last and last["status"] == "estimated":
                self.ex("UPDATE generations SET estimate_credits=?, estimate_approved=0, approved_at=NULL, updated_at=? WHERE id=?",
                        (float(estimate_credits), now_iso(), last["id"]))
                return {**self.q1("SELECT * FROM generations WHERE id=?", (last["id"],)), "note": "tahmin güncellendi; önceki onay geçersiz"}
            if last and last["status"] == "completed" and not new_take:
                return {**last, "blocked": True, "note": "bu talep tamamlanmış; dosya yeniden indirilebilir. Gerçekten yeni alım için new_take=true, yeni tahmin ve yeni onay"}
            req = (last["request_no"] + 1) if last else 1
            params_store = dict(params)
            if flow_snapshot_sha256:
                params_store["__flow_snapshot_sha256"] = flow_snapshot_sha256
            call_h = hashing.params_hash(tool_name, params, classes)  # hook'un gördüğü gerçek çağrı (dosya hash'leri hariç)
            gid = self.ex("""INSERT INTO generations(profile_id,campaign_id,cycle_id,provider,model,kind,tool_name,prompt,params_json,params_hash,
                             call_hash,input_files_json,request_no,estimate_credits,status,updated_at,created_at)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'estimated', ?, ?)""",
                          (profile_id, campaign_id, cycle_id, provider, model or params.get("model_id"), kind or classes["paid"][bare]["kind"],
                           bare, params.get("prompt"), jdump(params_store), h, call_h, jdump(input_file_hashes) if input_file_hashes else None,
                           req, float(estimate_credits), now_iso(), now_iso())).lastrowid
        return self.q1("SELECT * FROM generations WHERE id=?", (gid,))

    def generation_approve(self, profile_id: int, generation_id: int, approved_max_credits: float, count: int,
                           approval_text: str, approval_scope: dict) -> dict:
        g = self.q1("SELECT * FROM generations WHERE id=?", (int(generation_id),))
        if not g or g["profile_id"] != int(profile_id):
            raise AdMemoryError("üretim kaydı bu profile ait değil")
        if g["status"] != "estimated":
            raise AdMemoryError(f"yalnızca tahmin aşamasındaki kayıt onaylanır (durum: {g['status']})")
        if not approval_text or not approval_text.strip():
            raise AdMemoryError("maliyet onayı kullanıcının açık ifadesini ister")
        params = jload(g["params_json"], {}) if isinstance(g["params_json"], str) else g["params_json"]
        n = hashing.generation_count(g["tool_name"], {k: v for k, v in params.items() if not k.startswith("__")})
        if int(count) != n:
            raise AdMemoryError(f"onaylanan adet ({count}) çağrının adediyle ({n}) aynı olmalı")
        if float(approved_max_credits) < float(g["estimate_credits"] or 0):
            raise AdMemoryError("onaylanan azami kredi tahminin altında")
        lic = (approval_scope or {}).get("license") or {}
        if not (lic.get("source") and lic.get("checked_at") and lic.get("scope")):
            raise AdMemoryError("ticari kullanım hakkı kontrolü (kaynak, tarih, kapsam) onay kapsamına yazılmalı (bölüm 10)")
        if (approval_scope or {}).get("contains_personal_data") and not (approval_scope or {}).get("processing_permission_ref"):
            raise AdMemoryError("kişisel veri içeren girdi için işleme/aktarım dayanağı referansı gerekir (yükleme öncesi izin kapısı, bölüm 10)")
        scope = {**approval_scope, "approved_max_credits": float(approved_max_credits), "count": int(count),
                 "approval_text": approval_text.strip(), "params_hash": g["params_hash"], "request_no": g["request_no"]}
        with self.tx():
            self.ex("UPDATE generations SET estimate_approved=1, approved_at=?, approval_scope_json=?, updated_at=? WHERE id=?",
                    (now_iso(), jdump(scope), now_iso(), g["id"]))
        return {**self.q1("SELECT * FROM generations WHERE id=?", (g["id"],)),
                "note": "Onay tek kullanımlıktır; gerçek çağrıdan hemen önce cost_guard rezervasyonu alır."}

    def generation_reserve(self, campaign_id: int, call_hash: str, tool_use_id: str | None) -> dict:
        """cost_guard'ın kullandığı tek yazma: estimated → running, onay tüketilir (7.4 istisnası). MCP aracı değildir.
        Eşleşme gerçek çağrının kanonik hash'iyle (call_hash; girdi dosyası hash'leri hook'ta bilinemez)."""
        with self.tx():
            rows = self.qa("SELECT * FROM generations WHERE campaign_id=? AND COALESCE(call_hash, params_hash)=? ORDER BY id DESC",
                           (int(campaign_id), call_hash))
            if not rows:
                return {"ok": False, "reason": "bu çağrı için tahmin/onay kaydı yok (estimate_only → generation_log → onay)"}
            g = rows[0]
            if g["status"] in ("running", "unknown"):
                return {"ok": False, "reason": f"aynı talep {g['status']}: otomatik tekrar yok, önce uzlaştırma"}
            if g["status"] == "completed":
                return {"ok": False, "reason": "aynı talep tamamlanmış; yeni alım için yeni tahmin ve onay"}
            if g["status"] != "estimated" or not g["estimate_approved"]:
                return {"ok": False, "reason": "onay yok ya da tüketilmiş"}
            cur = self.ex("UPDATE generations SET status='running', estimate_approved=0, tool_use_id=?, updated_at=? WHERE id=? AND status='estimated' AND estimate_approved=1",
                          (tool_use_id, now_iso(), g["id"]))
            if cur.rowcount != 1:
                return {"ok": False, "reason": "eşzamanlı çağrı rezervasyonu aldı"}
        return {"ok": True, "generation_id": g["id"]}

    TRANSITIONS = {"estimated": {"failed"}, "running": {"completed", "failed", "unknown"}, "unknown": {"completed", "failed"},
                   "completed": set(), "failed": set()}

    def generation_update(self, profile_id: int, generation_id: int, status: str | None = None,
                          provider_request_id: str | None = None, flow_id: str | None = None, session_ids: list | None = None,
                          cost_credits: float | None = None, output_path: str | None = None, error: dict | None = None,
                          accepted: bool | None = None, evidence: str | None = None) -> dict:
        g = self.q1("SELECT * FROM generations WHERE id=?", (int(generation_id),))
        if not g or g["profile_id"] != int(profile_id):
            raise AdMemoryError("üretim kaydı bu profile ait değil")
        if status and status != g["status"]:
            if status not in self.TRANSITIONS.get(g["status"], set()):
                raise AdMemoryError(f"geçersiz durum geçişi {g['status']} → {status}")
            if g["status"] == "unknown" and not evidence:
                raise AdMemoryError("belirsiz kaydın çözümü sağlayıcı kaydına dayalı kanıt ister (9.1)")
            if status == "failed" and g["status"] == "running" and (error or {}).get("kind") in ("timeout", "disconnect", "session_closed"):
                raise AdMemoryError("bağlantı kesilmesi/zaman aşımı sağlayıcının işi kabul etmediğini kanıtlamaz: kayıt 'unknown' olur (9.1)")
        if output_path:
            op = Path(output_path)
            if not op.is_absolute():
                op = self.data_dir / op
            if not op.exists():
                raise AdMemoryError(f"çıktı dosyası yok: {op}")
            output_path = str(op)
        sets = {"status": status, "provider_request_id": provider_request_id, "flow_id": flow_id,
                "session_ids_json": jdump(session_ids) if session_ids is not None else None, "cost_credits": cost_credits,
                "output_path": output_path, "error_json": jdump({**(error or {}), "evidence": evidence}) if (error or evidence) else None,
                "accepted": (1 if accepted else 0) if accepted is not None else None}
        sets = {k: v for k, v in sets.items() if v is not None}
        if not sets:
            return g
        sets["updated_at"] = now_iso()
        with self.tx():
            self.ex(f"UPDATE generations SET {', '.join(f'{k}=?' for k in sets)} WHERE id=?", (*sets.values(), g["id"]))
        return self.q1("SELECT * FROM generations WHERE id=?", (g["id"],))

    def generation_find(self, profile_id: int, campaign_id: int | None = None, params_hash: str | None = None,
                        status: str | None = None, kind: str | None = None) -> dict:
        self._profile(profile_id, allow_archived=True)
        sql = "SELECT * FROM generations WHERE profile_id=?"
        args: list[Any] = [profile_id]
        for col, v in (("campaign_id", campaign_id), ("params_hash", params_hash), ("status", status), ("kind", kind)):
            if v is not None:
                sql += f" AND {col}=?"
                args.append(v)
        return {"generations": self.qa(sql + " ORDER BY id DESC LIMIT 200", tuple(args))}

    def generations_reconcile_due(self, profile_id: int, older_than_min: int = 30) -> dict:
        rows = self.qa("SELECT * FROM generations WHERE profile_id=? AND status IN ('running','unknown') ORDER BY id", (profile_id,))
        due = []
        for r in rows:
            age = (utcnow() - parse_iso(r["updated_at"])).total_seconds() / 60
            if r["status"] == "unknown" or age >= older_than_min:
                due.append({**r, "age_min": round(age, 1),
                            "how": "creative_get_flow_run_status / creative_get_flow ile salt okuma; tamamlanmışsa dosyayı bağla, sürüyorsa bekle, "
                                   "sağlayıcı kabul etmediyse 'failed' + kanıt; işlem kimliği yoksa kullanıcı sağlayıcı panelinden kontrol eder"})
        return {"due": due}

    def cost_summary(self, profile_id: int, campaign_id: int | None = None, cycle_id: int | None = None) -> dict:
        self._profile(profile_id, allow_archived=True)
        sql = """SELECT kind, model, status, COUNT(*) AS n, SUM(estimate_credits) AS est, SUM(cost_credits) AS cost
                 FROM generations WHERE profile_id=?"""
        args: list[Any] = [profile_id]
        if campaign_id is not None:
            sql += " AND campaign_id=?"
            args.append(campaign_id)
        if cycle_id is not None:
            sql += " AND cycle_id=?"
            args.append(cycle_id)
        rows = self.qa(sql + " GROUP BY kind, model, status ORDER BY kind", tuple(args))
        spent = sum((r["cost"] or 0) for r in rows if r["status"] == "completed")
        return {"rows": rows, "spent_credits": spent,
                "note": "Yerel render ve kod efektleri sağlayıcı kredisi harcamaz; tahmin ile gerçekleşen sapması üretim hafızasına yazılır (8.5)."}
