"""Store tabanı: bağlantı, işlemler, profil yalıtımı, ayarlar, profiller, marka/ürün, tanışma, oturum, işler, sistem."""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterator

from . import db
from .util import (AdMemoryError, atomic_write, canonical_json, file_lock, jdump, jload, now_iso, parse_iso, sha256_file,
                   sha256_text, slugify, utcnow)

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
SERVER_DIR = Path(__file__).resolve().parents[1]

VALID_CURRENCIES = ("TRY", "USD", "EUR")
VALID_LANGUAGES = ("tr", "en")
SETTINGS_KEYS = {"active_profile_id", "setup_verified_at", "setup_static_ok_at", "runtime_verification_json",
                 "meta_data_mode_default", "last_backup_at", "currency", "language", "exploration_share",
                 "consolidation_threshold", "render_timings_json", "mcp_deferred_loading", "env_id",
                 "install_deviations_json"}
JOB_TYPES = ("takip", "karar-hazirla", "gece-uretim", "bakim")


def _row(r: sqlite3.Row | None) -> dict | None:
    if r is None:
        return None
    d = dict(r)
    for k, v in list(d.items()):
        if k.endswith("_json") and isinstance(v, str):
            d[k] = jload(v, v)
    return d


def _rows(rs) -> list[dict]:
    return [_row(r) for r in rs]


class BaseStore:
    def __init__(self, db_path: str | os.PathLike, data_dir: str | os.PathLike, plugin_root: str | os.PathLike | None = None):
        self.db_path = Path(db_path)
        self.data_dir = Path(data_dir)
        self.plugin_root = Path(plugin_root) if plugin_root else PLUGIN_ROOT
        self.conn = db.connect(self.db_path)
        self._depth = 0
        db.migrate(self.conn, backup_fn=self._migration_backup)

    # --- işlemler -----------------------------------------------------------
    @contextlib.contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """İç içe çağrılabilen BEGIN IMMEDIATE işlemi; hata olursa tamamı geri alınır (7.4)."""
        if self._depth == 0:
            self.conn.execute("BEGIN IMMEDIATE")
        self._depth += 1
        try:
            yield self.conn
        except BaseException:
            self._depth -= 1
            if self._depth == 0:
                self.conn.execute("ROLLBACK")
            raise
        else:
            self._depth -= 1
            if self._depth == 0:
                self.conn.execute("COMMIT")

    def q1(self, sql: str, args: tuple = ()) -> dict | None:
        return _row(self.conn.execute(sql, args).fetchone())

    def qa(self, sql: str, args: tuple = ()) -> list[dict]:
        return _rows(self.conn.execute(sql, args).fetchall())

    def ex(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, args)

    def close(self) -> None:
        self.conn.close()

    # --- yalıtım kontrolleri (7.4) -----------------------------------------
    def _profile(self, profile_id: int, *, allow_archived: bool = False) -> dict:
        if profile_id is None:
            raise AdMemoryError("profile_id zorunlu: profil verisi araçları aktif profile düşmez (7.4)")
        p = self.q1("SELECT * FROM profiles WHERE id=?", (int(profile_id),))
        if not p:
            raise AdMemoryError(f"profil bulunamadı: {profile_id}")
        if p["status"] == "archived" and not allow_archived:
            raise AdMemoryError(f"profil arşivlenmiş: {p['name']} (veri silinmez, yeni yazma yapılmaz)")
        return p

    def _brand_id(self, profile_id: int, *, required: bool = True) -> int | None:
        p = self._profile(profile_id, allow_archived=True)
        if p["brand_id"] is None and required:
            raise AdMemoryError(f"profilin marka kaydı yok (S00a tamamlanmalı): {p['name']}")
        return p["brand_id"]

    def _campaign(self, profile_id: int, campaign_id: int) -> dict:
        bid = self._brand_id(profile_id)
        c = self.q1("SELECT * FROM campaigns WHERE id=?", (int(campaign_id),))
        if not c or c["brand_id"] != bid:
            raise AdMemoryError(f"kampanya {campaign_id} bu profile ait değil (profil yalıtımı, 2.3)")
        return c

    def _cycle(self, profile_id: int, cycle_id: int, campaign_id: int | None = None) -> dict:
        cy = self.q1("SELECT * FROM cycles WHERE id=?", (int(cycle_id),))
        if not cy:
            raise AdMemoryError(f"tur bulunamadı: {cycle_id}")
        self._campaign(profile_id, cy["campaign_id"])
        if campaign_id is not None and int(campaign_id) != cy["campaign_id"]:
            raise AdMemoryError(f"tur {cycle_id} kampanya {campaign_id}'e ait değil")
        return cy

    def _product(self, profile_id: int, product_id: int) -> dict:
        bid = self._brand_id(profile_id)
        p = self.q1("SELECT * FROM products WHERE id=?", (int(product_id),))
        if not p or p["brand_id"] != bid:
            raise AdMemoryError(f"ürün {product_id} bu profile ait değil")
        return p

    def profile_dir(self, profile_id: int) -> Path:
        p = self._profile(profile_id, allow_archived=True)
        return self.data_dir / "profiles" / p["slug"]

    # --- ayarlar ------------------------------------------------------------
    def settings_get(self, key: str | None = None) -> dict:
        if key:
            r = self.q1("SELECT * FROM settings WHERE key=?", (key,))
            val = r["value"] if r else None
            if key.endswith("_json"):
                val = jload(val, val)
            return {"key": key, "value": val, "updated_at": r["updated_at"] if r else None}
        rows = self.qa("SELECT * FROM settings ORDER BY key")
        return {r["key"]: (jload(r["value"], r["value"]) if r["key"].endswith("_json") else r["value"]) for r in rows}

    def settings_set(self, key: str, value: Any) -> dict:
        if key not in SETTINGS_KEYS:
            raise AdMemoryError(f"bilinmeyen ayar anahtarı: {key}")
        if key == "runtime_verification_json":
            raise AdMemoryError("runtime_verification_json yalnızca runtime_record ile madde madde güncellenir (12.13)")
        if key == "active_profile_id" and value is not None:
            self._profile(int(value))
        if key == "currency" and value not in VALID_CURRENCIES:
            raise AdMemoryError(f"geçersiz para birimi: {value} (geçerli: {', '.join(VALID_CURRENCIES)})")
        if key == "language" and value not in VALID_LANGUAGES:
            raise AdMemoryError(f"geçersiz dil: {value} (geçerli: {', '.join(VALID_LANGUAGES)})")
        if key == "exploration_share":
            v = float(value)
            if not (0.05 <= v <= 0.2):
                raise AdMemoryError("exploration_share 0,05 ile 0,2 arasında olmalı (6.3)")
        if key == "meta_data_mode_default" and value not in ("mcp", "csv"):
            raise AdMemoryError("meta_data_mode_default: mcp | csv")
        sval = value if isinstance(value, str) or value is None else json.dumps(value, ensure_ascii=False)
        with self.tx():
            self.ex("INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                    (key, sval, now_iso()))
        return self.settings_get(key)

    def _setting(self, key: str, default: Any = None) -> Any:
        r = self.q1("SELECT value FROM settings WHERE key=?", (key,))
        return r["value"] if r and r["value"] is not None else default

    # --- profiller (2.3) ----------------------------------------------------
    def profile_create(self, name: str, slug: str | None = None, synthetic: bool = False) -> dict:
        if not name or not name.strip():
            raise AdMemoryError("profil adı boş olamaz")
        base = slugify(slug or name)
        s = base
        n = 2
        while self.q1("SELECT 1 FROM profiles WHERE slug=?", (s,)):
            s = f"{base}-{n}"
            n += 1
        with self.tx():
            cur = self.ex("INSERT INTO profiles(slug,name,status,created_at,synthetic) VALUES(?,?, 'onboarding', ?, ?)",
                          (s, name.strip(), now_iso(), 1 if synthetic else 0))
            pid = cur.lastrowid
        pdir = self.data_dir / "profiles" / s
        for sub in ("brand/docs", "memory", "products", "reports", "competitors/user", "competitors/cache", "campaigns", "styles"):
            (pdir / sub).mkdir(parents=True, exist_ok=True)
        return self.q1("SELECT * FROM profiles WHERE id=?", (pid,))

    def profile_list(self, include_archived: bool = False, include_synthetic: bool = False) -> dict:
        sql = "SELECT p.*, b.name AS brand_name, b.meta_ad_account_id FROM profiles p LEFT JOIN brands b ON b.id=p.brand_id"
        conds = []
        if not include_archived:
            conds.append("p.status!='archived'")
        if not include_synthetic:
            conds.append("p.synthetic=0")
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        rows = self.qa(sql + " ORDER BY p.id")
        active = self._setting("active_profile_id")
        return {"count": len(rows), "active_profile_id": int(active) if active else None, "profiles": rows}

    def profile_get_active(self) -> dict:
        a = self._setting("active_profile_id")
        if not a:
            return {"active": None}
        p = self.q1("SELECT * FROM profiles WHERE id=?", (int(a),))
        return {"active": p}

    def profile_set_active(self, profile_id: int, session_id: str | None = None) -> dict:
        p = self._profile(profile_id)
        self.settings_set("active_profile_id", str(p["id"]))
        if session_id:
            self.session_bind(session_id, profile_id=p["id"], campaign_id=None, cycle_id=None)
        return {"active_profile_id": p["id"], "name": p["name"],
                "note": "Bu oturumun ve yeni oturumların varsayılanı değişti; başka oturumların ve görevlerin bağlı kimlikleri değişmez (2.3)."}

    def profile_update(self, profile_id: int, **fields: Any) -> dict:
        p = self._profile(profile_id, allow_archived=True)
        allowed = {"name", "status", "meta_data_mode", "meta_verified_at", "history_status", "last_meta_sync_at"}
        bad = set(fields) - allowed
        if bad:
            raise AdMemoryError(f"profile_update alanı desteklenmiyor: {', '.join(sorted(bad))}")
        st = fields.get("status")
        if st == "active":
            missing = self._activation_blockers(p)
            if missing:
                raise AdMemoryError("profil aktifleştirilemez: " + "; ".join(missing))
        sets, args = [], []
        for k, v in fields.items():
            if v is None:
                continue
            sets.append(f"{k}=?")
            args.append(v)
        if st == "archived":
            sets.append("archived_at=?")
            args.append(now_iso())
        if not sets:
            return p
        with self.tx():
            self.ex(f"UPDATE profiles SET {', '.join(sets)} WHERE id=?", (*args, p["id"]))
            if st == "archived":
                jobs = jload(p["jobs_json"], [])
                for j in jobs:
                    j["status"] = "stopped"
                self.ex("UPDATE profiles SET jobs_json=? WHERE id=?", (jdump(jobs), p["id"]))
        return self.q1("SELECT * FROM profiles WHERE id=?", (p["id"],))

    def _activation_blockers(self, p: dict) -> list[str]:
        out = []
        s00a = self.q1("SELECT * FROM stage_runs WHERE scope_key=? AND stage='S00a' AND status='done' AND stale=0 ORDER BY output_version DESC LIMIT 1",
                       (f"profile:{p['id']}",))
        if not s00a:
            out.append("S00a (marka tanışması) onaylanmadı")
        if p["history_status"] not in ("ready", "no_history"):
            out.append("S00b Meta geçmişi alınmadı ya da 'geçmiş yok' kaydedilmedi")
        if not p["meta_data_mode"]:
            out.append("profilin Meta veri yolu (mcp|csv) kayıtlı değil")
        return out

    def profile_onboarding_state(self, profile_id: int) -> dict:
        p = self._profile(profile_id, allow_archived=True)
        brand = self.q1("SELECT * FROM brands WHERE id=?", (p["brand_id"],)) if p["brand_id"] else None
        prods = self.qa("SELECT id,name,onboarding_status FROM products WHERE brand_id=?", (p["brand_id"],)) if p["brand_id"] else []
        runs = self.qa("SELECT stage,status,output_version,scope_key FROM stage_runs WHERE profile_id=? AND stage IN ('S00a','S00b','S00c') AND stale=0 ORDER BY id",
                       (p["id"],))
        return {"profile": p, "brand": brand, "products": prods, "onboarding_runs": runs,
                "activation_blockers": self._activation_blockers(p) if p["status"] == "onboarding" else []}

    # --- marka ve ürün -------------------------------------------------------
    def brand_upsert(self, profile_id: int, **fields: Any) -> dict:
        p = self._profile(profile_id)
        allowed = {"name", "meta_ad_account_id", "meta_page_id", "ig_account_id", "tone", "avoid_list", "cta_url",
                   "style_json_path", "elevenlabs_voice_id", "timezone", "processing_permissions_json"}
        bad = set(fields) - allowed
        if bad:
            raise AdMemoryError(f"brand_upsert alanı desteklenmiyor: {', '.join(sorted(bad))}")
        for k in ("avoid_list", "processing_permissions_json"):
            if k in fields and not isinstance(fields[k], (str, type(None))):
                fields[k] = jdump(fields[k])
        acct = fields.get("meta_ad_account_id")
        if acct:
            other = self.q1("SELECT b.id, p.name AS pname FROM brands b JOIN profiles p ON p.brand_id=b.id WHERE b.meta_ad_account_id=? AND p.id!=?",
                            (acct, p["id"]))
            if other:
                raise AdMemoryError(f"reklam hesabı {acct} zaten '{other['pname']}' profiline bağlı; aynı hesap iki profile bağlanamaz (2.3)")
        tz = fields.get("timezone")
        if tz:
            try:
                import zoneinfo
                zoneinfo.ZoneInfo(tz)
            except Exception:
                raise AdMemoryError(f"geçersiz saat dilimi: {tz} (IANA adı gerekir, ör. 'Europe/Istanbul', 'Europe/Berlin', 'America/New_York'; hesaptan doğrulanır)")
        with self.tx():
            if p["brand_id"] is None:
                if not fields.get("name"):
                    fields["name"] = p["name"]
                cols = list(fields)
                cur = self.ex(f"INSERT INTO brands({', '.join(cols)}, created_at) VALUES({', '.join('?' * len(cols))}, ?)",
                              (*[fields[c] for c in cols], now_iso()))
                self.ex("UPDATE profiles SET brand_id=? WHERE id=?", (cur.lastrowid, p["id"]))
                bid = cur.lastrowid
            else:
                bid = p["brand_id"]
                if fields:
                    self.ex(f"UPDATE brands SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?", (*fields.values(), bid))
        return self.q1("SELECT * FROM brands WHERE id=?", (bid,))

    def product_upsert(self, profile_id: int, name: str, product_id: int | None = None, **fields: Any) -> dict:
        bid = self._brand_id(profile_id)
        self._profile(profile_id)
        allowed = {"price", "gross_margin", "aov", "currency", "safety_factor", "economics_json", "occasions_json", "buyers_json",
                   "provable_claims_json", "capacity_limit", "photos_json", "observation_json", "shoot_profile_json",
                   "catalog_product_id", "onboarding_status", "kind", "service_json", "objections_json"}
        bad = set(fields) - allowed
        if bad:
            raise AdMemoryError(f"product_upsert alanı desteklenmiyor: {', '.join(sorted(bad))}")
        if "currency" in fields and fields["currency"] and fields["currency"] not in VALID_CURRENCIES:
            raise AdMemoryError(f"geçersiz para birimi: {fields['currency']}")
        if "shoot_profile_json" in fields and fields["shoot_profile_json"] is not None:
            self._validate_shoot_profile(fields["shoot_profile_json"])
        if "kind" in fields and fields["kind"] not in ("product", "service"):
            raise AdMemoryError("kind: product | service")
        if "service_json" in fields and fields["service_json"] is not None:
            from .s_lead import validate_service
            fields["service_json"] = validate_service(fields["service_json"])
        if "objections_json" in fields and fields["objections_json"] is not None:  # satın alma engelleri (S00c; 1.9.0)
            from .funnel import validate_objections
            fields["objections_json"] = validate_objections(fields["objections_json"])
        for k in list(fields):
            if k.endswith("_json") and fields[k] is not None and not isinstance(fields[k], str):
                fields[k] = jdump(fields[k])
        with self.tx():
            if product_id:
                prod = self._product(profile_id, product_id)
                fields["name"] = name or prod["name"]
                self.ex(f"UPDATE products SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?", (*fields.values(), prod["id"]))
                pid = prod["id"]
            else:
                existing = self.q1("SELECT id FROM products WHERE brand_id=? AND name=?", (bid, name))
                if existing:
                    if fields:
                        self.ex(f"UPDATE products SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?", (*fields.values(), existing["id"]))
                    pid = existing["id"]
                else:
                    cols = ["brand_id", "name", *fields.keys(), "created_at"]
                    vals = [bid, name, *fields.values(), now_iso()]
                    cur = self.ex(f"INSERT INTO products({', '.join(cols)}) VALUES({', '.join('?' * len(cols))})", tuple(vals))
                    pid = cur.lastrowid
        prod = self.q1("SELECT * FROM products WHERE id=?", (pid,))
        prod["economics"] = self.economics(prod)
        return prod

    @staticmethod
    def _validate_shoot_profile(sp: Any) -> None:
        data = jload(sp, None) if isinstance(sp, str) else sp
        if data is None:
            return
        cards = data.get("cards") if isinstance(data, dict) else None
        if not isinstance(cards, list):
            raise AdMemoryError("shoot_profile_json {'cards': [...]} biçiminde olmalı (5.3)")
        for i, c in enumerate(cards):
            for k in ("risk", "what", "phone", "do", "stop_when", "success_check", "overrides_rule", "why"):
                if k not in c:
                    raise AdMemoryError(f"çekim tarifi kartı {i}: '{k}' alanı eksik (kart yapısı genel kurallarla aynıdır ve hangi kuralı neden değiştirdiğini yazar; 5.3)")

    @staticmethod
    def economics(prod: dict) -> dict:
        """Başa baş CPA / ROAS ve hedef CPA (6.2). Katkı bilinmiyorsa/aralıksa sonuç da varsayım/aralıktır."""
        eco = jload(prod.get("economics_json"), {}) if isinstance(prod.get("economics_json"), str) else (prod.get("economics_json") or {})
        sf = float(prod.get("safety_factor") or 0.7)
        out: dict[str, Any] = {"basis": eco.get("basis"), "status": "unknown", "safety_factor": sf}
        contrib = eco.get("contribution")
        low, high = eco.get("contribution_low"), eco.get("contribution_high")
        basket = eco.get("net_basket") or prod.get("aov") or prod.get("price")

        def num(v) -> float | None:
            if isinstance(v, bool) or v is None:
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        vc = eco.get("variable_costs")
        # Kalemlerden katkı yalnızca açık katkı ya da aralık verilmemişse ve bütün kalemler sayıysa hesaplanır (1.4.1): bilinmeyen kalem
        # (ör. iade oranı null/metin) sıfır sayılmaz; aralık verildiyse kalemlerden çıkan tek sayı aralığı ezmez.
        if contrib is None and low is None and high is None and eco.get("net_basket") is not None and isinstance(vc, dict):
            vals = {k: num(v) for k, v in vc.items()}
            unknown = sorted(k for k, v in vals.items() if v is None)
            if unknown:
                out["unknown_costs"] = unknown
            elif num(eco["net_basket"]) is not None:
                contrib = num(eco["net_basket"]) - sum(vals.values())
        if contrib is not None:
            contrib = float(contrib)
            if contrib <= 0:
                out.update(status="non_positive", contribution=contrib,
                           note="Katkı ≤ 0: pozitif başa baş CPA üretilmez (6.2)")
                if eco.get("lead_close_rate") is not None:
                    out.update(cpl_status="unknown", cpl_note="Katkı ≤ 0: başa baş aday maliyeti de üretilmez")
                return out
            out.update(status="exact" if eco.get("confirmed") else "assumed", contribution=contrib,
                       breakeven_cpa=round(contrib, 2), target_cpa=round(contrib * sf, 2))
            if basket:
                out["breakeven_roas"] = round(float(basket) / contrib, 3)
        elif low is not None and high is not None:
            lo, hi = float(low), float(high)
            out.update(status="range", contribution_range=[lo, hi], breakeven_cpa_range=[round(lo, 2), round(hi, 2)],
                       target_cpa_range=[round(lo * sf, 2), round(hi * sf, 2)],
                       note="Katkı aralık: kesin kârlılık veya büyütme hükmü verilmez (6.2)")
        else:
            out["note"] = "Katkı bilinmiyor: ekonomi VARSAYIMSAL; kesin kârlılık hükmü verilmez (6.2)" + (
                f" · bilinmeyen kalemler: {', '.join(out['unknown_costs'])} (contribution_low/high ile aralık verilebilir)" if out.get("unknown_costs") else "")
        if eco.get("lead_close_rate") is not None:  # aday sonucu: başa baş aday maliyeti (1.5.0); satış hesabından bağımsız eklenir
            from .s_lead import lead_economics
            rng = out.get("contribution_range")
            out.update(lead_economics(eco, out.get("contribution") if out.get("status") in ("exact", "assumed") else None,
                                      out.get("status") == "exact", sf, rng))
        return out

    def product_list(self, profile_id: int) -> dict:
        bid = self._brand_id(profile_id, required=False)
        if not bid:
            return {"products": []}
        rows = self.qa("SELECT * FROM products WHERE brand_id=? ORDER BY id", (bid,))
        for r in rows:
            r["economics"] = self.economics(r)
        return {"products": rows}

    def onboarding_save(self, profile_id: int, scope: str, scope_id: int, question_key: str, answer: Any,
                        source: str = "user", confirmed: bool = False) -> dict:
        self._profile(profile_id)
        if scope == "brand":
            if int(scope_id) != self._brand_id(profile_id):
                raise AdMemoryError("marka bu profile ait değil")
        elif scope == "product":
            self._product(profile_id, scope_id)
        else:
            raise AdMemoryError("scope: brand | product")
        if source not in ("user", "meta", "inferred"):
            raise AdMemoryError("source: user | meta | inferred")
        val = answer if isinstance(answer, str) else jdump(answer)
        with self.tx():
            cur = self.ex("INSERT INTO onboarding_answers(scope,scope_id,question_key,answer,source,confirmed,created_at) VALUES(?,?,?,?,?,?,?)",
                          (scope, int(scope_id), question_key, val, source, 1 if confirmed else 0, now_iso()))
        return self.q1("SELECT * FROM onboarding_answers WHERE id=?", (cur.lastrowid,))

    def onboarding_get(self, profile_id: int, scope: str, scope_id: int) -> dict:
        self._profile(profile_id, allow_archived=True)
        if scope == "brand" and int(scope_id) != self._brand_id(profile_id):
            raise AdMemoryError("marka bu profile ait değil")
        if scope == "product":
            self._product(profile_id, scope_id)
        rows = self.qa("SELECT * FROM onboarding_answers WHERE scope=? AND scope_id=? ORDER BY id", (scope, int(scope_id)))
        latest: dict[str, dict] = {}
        for r in rows:
            latest[r["question_key"]] = r
        return {"answers": list(latest.values()), "history_count": len(rows)}

    # --- oturum durumu (.sessions, 13.6) -------------------------------------
    def _session_path(self, session_id: str) -> Path:
        if not session_id or not re.fullmatch(r"[A-Za-z0-9_.-]{4,128}", session_id):
            raise AdMemoryError("geçersiz session_id")
        return self.data_dir / ".sessions" / f"{session_id}.json"

    def session_get(self, session_id: str) -> dict:
        p = self._session_path(session_id)
        if not p.exists():
            return {"session_id": session_id, "plugin_mode": False}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {"session_id": session_id, "plugin_mode": False, "corrupt": True}

    def _session_update(self, session_id: str, fn) -> dict:
        """Kilit altında oku → fn → yaz; hook'lar (meta_guard) aynı kilidi kullanır (2.0.0: paralel çağrıda bağlama/izin kaybolmasın)."""
        with file_lock(self._session_path(session_id)):
            s = self.session_get(session_id)
            out = fn(s)
            return self._session_write(session_id, s if out is None else out)

    def _session_write(self, session_id: str, data: dict) -> dict:
        data["session_id"] = session_id
        data["updated_at"] = now_iso()
        atomic_write(self._session_path(session_id), json.dumps(data, ensure_ascii=False, indent=1))
        return data

    def session_bind(self, session_id: str, profile_id: int | None = None, campaign_id: int | None = None,
                     cycle_id: int | None = None, stage: str | None = None) -> dict:
        """Oturuma profil/kampanya/tur bağlar (2.3). Başka oturumu ve görevleri etkilemez."""
        if profile_id is not None:
            self._profile(profile_id)
            if campaign_id is not None:
                self._campaign(profile_id, campaign_id)
            if cycle_id is not None:
                self._cycle(profile_id, cycle_id, campaign_id)

        def bind(s: dict) -> None:
            s.update({"profile_id": profile_id, "campaign_id": campaign_id, "cycle_id": cycle_id})
            if stage is not None:
                s["stage"] = stage
        return self._session_update(session_id, bind)

    def menu_render(self, session_id: str) -> dict:
        """Sabit ana menünün metni (17.1; hooks/menu.py ile hook'la aynı kod). Gösterildiği oturuma 'son ekran: menü' yazılır;
        sonraki tek sayı bu menüye göre çözülür. kind 'menu' değilse metin yoktur (profil yok / seçim gerekli)."""
        import sys
        hooks_dir = str(PLUGIN_ROOT / "hooks")
        if hooks_dir not in sys.path:
            sys.path.insert(0, hooks_dir)
        import menu as MN  # noqa: E402  (yalnızca standart kütüphane)
        r = MN.render(self.data_dir, self.session_get(session_id))
        if r["kind"] == "menu":
            self._session_update(session_id, lambda s: MN.mark_shown(s, r, now_iso()))
            r["rule"] = "Bu metni olduğu gibi göster; madde ekleme, çıkarma ya da yeniden adlandırma."
        return r

    def session_menu_set(self, session_id: str, items: list[str], header: str | None = None) -> dict:
        if not isinstance(items, list) or len(items) > 12:
            raise AdMemoryError("menü en fazla 12 madde olmalı (navigator en fazla 8 gösterir)")
        return self._session_update(session_id, lambda s: s.update({"last_menu": [str(i) for i in items], "menu_header": header,
                                                                    "menu_at": now_iso()}))

    # --- zamanlanmış işler (4.4) ---------------------------------------------
    def job_upsert(self, profile_id: int, job_type: str, campaign_id: int | None = None, cycle_id: int | None = None,
                   schedule: str | None = None, task_id: str | None = None, timezone: str | None = None,
                   status: str = "planned", job_id: str | None = None) -> dict:
        p = self._profile(profile_id)
        if job_type not in JOB_TYPES:
            raise AdMemoryError(f"iş türü: {', '.join(JOB_TYPES)}")
        if job_type == "takip" and campaign_id is None:
            raise AdMemoryError("takip işi --campaign gerektirir (13.5)")
        if job_type in ("karar-hazirla", "gece-uretim") and (campaign_id is None or cycle_id is None):
            raise AdMemoryError(f"{job_type} işi --campaign ve --cycle gerektirir (13.5)")
        if campaign_id is not None:
            self._campaign(profile_id, campaign_id)
        if cycle_id is not None:
            self._cycle(profile_id, cycle_id, campaign_id)
        with self.tx():
            p = self._profile(profile_id)
            jobs = jload(p["jobs_json"], [])
            if job_type == "takip":
                same = [j for j in jobs if j["type"] == "takip" and j.get("campaign_id") == campaign_id and j.get("status") != "stopped"]
                if same and not job_id:
                    job_id = same[0]["job_id"]  # kampanya başına tek günlük takip
            if not job_id:
                job_id = f"{job_type}-{profile_id}-{campaign_id or 0}-{cycle_id or 0}-{sha256_text(now_iso() + job_type)[:6]}"
            j = next((x for x in jobs if x["job_id"] == job_id), None)
            if j is None:
                j = {"job_id": job_id, "type": job_type, "profile_id": profile_id, "created_at": now_iso()}
                jobs.append(j)
            j.update({"campaign_id": campaign_id, "cycle_id": cycle_id, "schedule": schedule, "task_id": task_id,
                      "timezone": timezone, "status": status, "updated_at": now_iso()})
            self.ex("UPDATE profiles SET jobs_json=? WHERE id=?", (jdump(jobs), profile_id))
            if cycle_id is not None:
                cy = self.q1("SELECT jobs_json FROM cycles WHERE id=?", (cycle_id,))
                refs = jload(cy["jobs_json"], [])
                if job_id not in refs:
                    refs.append(job_id)
                self.ex("UPDATE cycles SET jobs_json=? WHERE id=?", (jdump(refs), cycle_id))
        return j

    def job_claim(self, profile_id: int, job_id: str, session_id: str, stale_after_min: int = 180) -> dict:
        """Aynı işin iki oturumda başlamasını önler (atomik sahiplenme, 4.4)."""
        with self.tx():
            p = self._profile(profile_id)
            jobs = jload(p["jobs_json"], [])
            j = next((x for x in jobs if x["job_id"] == job_id), None)
            if j is None:
                raise AdMemoryError(f"iş kaydı yok: {job_id}")
            if j.get("status") == "stopped":
                raise AdMemoryError("iş durdurulmuş (profil arşivlenmiş olabilir)")
            claim = j.get("claim")
            if claim and claim.get("session_id") != session_id:
                at = parse_iso(claim.get("at"))
                if at and (utcnow() - at).total_seconds() < stale_after_min * 60:
                    return {"claimed": False, "reason": "başka oturum çalıştırıyor", "current": j}
                return {"claimed": False, "reason": "yarım kalmış sahiplenme var; önce çıktı ve işlem durumu uzlaştırılmalı (job_finish status=reconciled)", "current": j}
            j["claim"] = {"session_id": session_id, "at": now_iso()}
            j["status"] = "running"
            self.ex("UPDATE profiles SET jobs_json=? WHERE id=?", (jdump(jobs), profile_id))
        return {"claimed": True, "job": j}

    def job_finish(self, profile_id: int, job_id: str, session_id: str, status: str, data_version: str | None = None,
                   output_ref: str | None = None, note: str | None = None) -> dict:
        if status not in ("ok", "failed", "skipped", "reconciled"):
            raise AdMemoryError("status: ok | failed | skipped | reconciled (tetiklenme başarı sayılmaz)")
        with self.tx():
            p = self._profile(profile_id)
            jobs = jload(p["jobs_json"], [])
            j = next((x for x in jobs if x["job_id"] == job_id), None)
            if j is None:
                raise AdMemoryError(f"iş kaydı yok: {job_id}")
            if j.get("claim") and j["claim"].get("session_id") != session_id and status != "reconciled":
                raise AdMemoryError("bu oturum işi sahiplenmemiş")
            j.pop("claim", None)
            j["status"] = "planned"
            j["last_status"] = status
            j["last_run_at"] = now_iso()
            if status == "ok":
                j["last_ok_at"] = now_iso()
                if data_version:
                    j["last_ok_data_version"] = data_version
                if output_ref:
                    j["last_ok_output"] = output_ref
            if note:
                j["note"] = note
            self.ex("UPDATE profiles SET jobs_json=? WHERE id=?", (jdump(jobs), profile_id))
        return j

    # --- yedek (12.13) --------------------------------------------------------
    def _migration_backup(self, reason: str) -> None:
        self.backup(reason=reason)

    def backup(self, reason: str = "manual", keep: int = 8) -> dict:
        bdir = self.data_dir / "backups"
        bdir.mkdir(parents=True, exist_ok=True)
        ts = utcnow().strftime("%Y%m%dT%H%M%SZ")
        target = bdir / f"ad-memory-{ts}-{slugify(reason, 24)}.sqlite"
        # 2.0.0: geçici ada yazılır, bütünlüğü denetlenir, sonra yerine konur. Yarıda kalan yedek (kapanan bilgisayar, dolu disk) önceden
        # sağlam yedek gibi görünüyor ve 8'lik sırada iyi yedeği siliyordu.
        part = target.with_name(target.name + ".part")
        part.unlink(missing_ok=True)
        dst = sqlite3.connect(str(part))
        try:
            self.conn.backup(dst)
            ok = dst.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            dst.close()
        if ok != "ok":
            part.unlink(missing_ok=True)
            raise AdMemoryError(f"yedek bütünlük denetiminden geçmedi ({ok}); eski yedekler silinmedi")
        os.replace(part, target)
        files = sorted(bdir.glob("ad-memory-*.sqlite"))
        removed = []
        for old in files[:-keep]:
            old.unlink()
            removed.append(old.name)
        self.ex("INSERT INTO settings(key,value,updated_at) VALUES('last_backup_at',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (now_iso(), now_iso()))
        return {"path": str(target), "sha256": sha256_file(target), "kept": min(len(files), keep), "removed": removed}

    def backup_if_due(self, days: int = 7) -> dict:
        last = parse_iso(self._setting("last_backup_at"))
        if last and (utcnow() - last) < dt.timedelta(days=days):
            return {"due": False, "last_backup_at": last.strftime("%Y-%m-%dT%H:%M:%SZ")}
        return {"due": True, **self.backup(reason="weekly")}

    # --- sistem manifesti ve canlı doğrulama (12.13) --------------------------
    def _manifest(self) -> tuple[dict, str | None]:
        mp = self.plugin_root / "system_manifest.json"
        if not mp.exists():
            return {}, None
        return json.loads(mp.read_text(encoding="utf-8")), sha256_file(mp)

    def runtime_record(self, item_id: str, status: str, scope: str = "common", evidence_ref: str | None = None,
                       component_hashes: dict | None = None, not_applicable_reason: str | None = None,
                       env_id: str | None = None, note: str | None = None) -> dict:
        if status not in ("pending", "passed", "failed", "not_applicable", "stale"):
            raise AdMemoryError("status: pending | passed | failed | not_applicable | stale")
        if status == "not_applicable" and not not_applicable_reason:
            raise AdMemoryError("uygulanamaz madde gerekçe ister (12.10)")
        manifest, msha = self._manifest()
        known = {i["id"] for i in manifest.get("live_checks", [])}
        if known and item_id not in known:
            raise AdMemoryError(f"manifest'te tanımlı olmayan canlı madde: {item_id}")
        if scope != "common" and not re.fullmatch(r"(profile|account|data_path):[A-Za-z0-9_.:-]+", scope):
            raise AdMemoryError("scope: common | profile:<id> | account:<id> | data_path:<mcp|csv>")
        for k in ("token", "access_token", "secret", "password"):
            if note and k in note.lower():
                raise AdMemoryError("canlı kayıt kimlik bilgisi/token içeremez (12.13)")
        with self.tx():
            cur = self.q1("SELECT value FROM settings WHERE key='runtime_verification_json'")
            data = jload(cur["value"], {}) if cur else {}
            items = data.setdefault("items", {})
            key = f"{item_id}@{scope}"
            items[key] = {"item_id": item_id, "scope": scope, "status": status, "at": now_iso(),
                          "evidence_ref": evidence_ref, "component_hashes": component_hashes or {},
                          "not_applicable_reason": not_applicable_reason, "note": note,
                          "plugin_version": manifest.get("plugin_version"), "manifest_sha256": msha,
                          "env_id": env_id or self._setting("env_id")}
            self.ex("INSERT INTO settings(key,value,updated_at) VALUES('runtime_verification_json',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                    (jdump(data), now_iso()))
        view = self.mark_verified_if_ready()
        return {"recorded": items[key], "live": view["live"]}

    def mark_verified_if_ready(self) -> dict:
        """setup_verified_at yalnızca statik kontrol (doctor --write-ok → setup_static_ok_at) VE ortak zorunlu canlı maddeler geçince
        yazılır (1.4.1). Hangisi son gelirse onu yazan çağrı işaretler: runtime_record ya da doctor."""
        view = self.system_manifest_get()
        if view["live"]["common_required_ok"] and view["setup_static_ok_at"] and not self._setting("setup_verified_at"):
            with self.tx():
                self.ex("INSERT INTO settings(key,value,updated_at) VALUES('setup_verified_at',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                        (now_iso(), now_iso()))
            view = self.system_manifest_get()
        return view

    def system_manifest_get(self, section: str | None = None) -> dict:
        manifest, msha = self._manifest()
        rv = jload(self._setting("runtime_verification_json"), {}) or {}
        items = rv.get("items", {})
        checks = manifest.get("live_checks", [])
        live_rows = []
        req_ok = True
        mode = self._setting("meta_data_mode_default")
        for c in checks:
            recs = [v for v in items.values() if v["item_id"] == c["id"]]
            common = next((r for r in recs if r["scope"] == "common"), None)
            effective = "pending"
            if common:
                effective = common["status"]
                if common.get("manifest_sha256") != msha and effective in ("passed", "not_applicable"):
                    if not self._hashes_still_match(c, common, manifest):
                        effective = "stale"
            applies = c.get("applies_to", "both")
            if mode and applies in ("mcp", "csv") and applies != mode and effective == "pending":
                effective = "not_applicable_by_path"
            if c.get("required") and c.get("scope", "common") == "common":
                if effective not in ("passed", "not_applicable", "not_applicable_by_path"):
                    req_ok = False
            live_rows.append({"id": c["id"], "title": c.get("title"), "required": c.get("required", False),
                              "applies_to": applies, "status": effective, "record": common,
                              "scoped": [r for r in recs if r["scope"] != "common"]})
        out = {"manifest_present": bool(manifest), "manifest_sha256": msha,
               "plugin_version": manifest.get("plugin_version"),
               "setup_static_ok_at": self._setting("setup_static_ok_at"),
               "setup_verified_at": self._setting("setup_verified_at"),
               "meta_data_mode_default": mode,
               "live": {"common_required_ok": bool(checks) and req_ok, "checks": live_rows,
                        "note": "Eşleşmeyen/eski kayıt başarı sayılmaz; ilk açılışta canlı kayıt yoksa bütün uygulanabilir maddeler bekliyor görünür."}}
        # Statik kontrol geçmeden kurulum doğrulanmış sayılmaz (1.4.1; 1.4.0'da canlı maddeler tek başına yetiyordu).
        out["setup_verified_effective"] = bool(out["setup_verified_at"]) and bool(out["setup_static_ok_at"]) and out["live"]["common_required_ok"]
        # Müşteri güncellemesi test sonucu değildir. Önceki ilk kurulum tamamlandıysa açılışta test zorlamaz.
        update = {}
        try:
            update = json.loads((self.data_dir / ".musteri-guncelleme.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        out["customer_update_without_tests"] = bool(
            isinstance(update, dict) and update.get("tests_run") is False
            and update.get("version") == manifest.get("plugin_version")
            and update.get("manifest_sha256") == msha
            and out["setup_verified_at"] and out["setup_static_ok_at"])
        # Kuruluma/makineye özgü, kullanıcının kabul ettiği sapmalar dağıtılan manifestte değil bu data_dir'de tutulur (12.13).
        out["install_deviations"] = jload(self._setting("install_deviations_json"), []) or []
        if section and manifest:
            out["section"] = manifest.get(section)
        elif manifest:
            out["summary"] = {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in manifest.items()
                              if k not in ("files",)}
        return out

    def _hashes_still_match(self, check: dict, record: dict, manifest: dict) -> bool:
        comps = check.get("components") or []
        if not comps:
            return False
        rec_h = record.get("component_hashes") or {}
        cur_h = (manifest.get("component_hashes") or {})
        return all(rec_h.get(c) and rec_h.get(c) == cur_h.get(c) for c in comps)
