"""Meta geçmişi, kıyaslar, önseller, günlük metrikler, reklam eşlemesi, elle satış (spec 6.2, 6.4, 6.6, 9.2, 17.6)."""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from pathlib import Path
from typing import Any

from . import naming
from .util import AdMemoryError, atomic_write, canonical_json, jdump, jload, now_iso, parse_iso, sha256_text

CONTEXT_DEF_KEYS = ("account_id", "timezone", "currency", "result_definition", "metric_definitions",
                    "attribution_window", "action_report_time")
METRIC_COLS = ("impressions", "reach", "frequency", "spend", "cpm", "video_3s", "thruplay", "p25", "p50", "p75", "p95",
               "p100", "avg_watch_s", "link_clicks", "ctr_link", "results", "result_type", "add_to_cart", "purchases", "revenue")
INT_COLS = {"impressions", "reach", "thruplay", "p25", "p50", "p75", "p95", "p100", "link_clicks", "results",
            "add_to_cart", "purchases"}
SERVER_DIR = Path(__file__).resolve().parents[1]


def measurement_fingerprint(ctx: dict) -> str:
    """Ölçüm tanımlarının anahtar sırası sabit JSON'undan SHA-256 (kaynak ve çekim zamanı katılmaz; 6.4)."""
    return sha256_text(canonical_json({k: ctx.get(k) for k in CONTEXT_DEF_KEYS}))


def _num(v: Any, decimal: str | None = None) -> float | None:
    """Sayı ayrıştırma. decimal: ',' (TR dışa aktarım: 1.234,56) ya da '.' (EN: 1,234.56); None ise ikisi birlikteyse sondaki ayırıcı ondalıktır."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "").replace(" ", "")
    if s in ("", "-", "—", "N/A", "n/a"):
        return None
    s = re.sub(r"[^\d,.\-]", "", s)
    if decimal is None:
        decimal = "," if ("," in s and "." in s and s.rfind(",") > s.rfind(".")) or re.search(r"\d,\d{1,2}$", s) else "."
    if decimal == ",":
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def detect_decimal(values: list[str]) -> str:
    for v in values:
        if v and re.search(r"\d,\d{1,2}$", str(v).strip()):
            return ","
    for v in values:
        if v and re.search(r"\d\.\d{1,2}$", str(v).strip()):
            return "."
    return ","


def _date(v: Any) -> str:
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(s[:10], fmt).date().isoformat()
        except ValueError:
            continue
    raise AdMemoryError(f"tarih okunamadı: {v!r}")


SALES_CHANNELS = ("shopier", "site", "instagram_dm", "whatsapp", "kurumsal", "magaza", "diger")
META_SIGNAL_STATUSES = ("purchase_seen", "no_purchase", "unknown")
META_SIGNAL_CHOICES = ("pixel_install", "csv_upload", "optimize_other")
META_SIGNAL_RULE = ("Satış (purchase) sonuçlu kampanya yalnızca Meta son 7 günde Purchase olayı alıyorsa açılır; almıyorsa üç yol: piksel kur, "
                    "satışları KVKK dayanağıyla Events Manager'a yükle, ya da bilinçli olarak mesaj/bağlantı/sayfa görüntüleme sonucuna optimize et.")


class MetaMixin:
    # --- Meta varlıkları ----------------------------------------------------------
    def meta_entities_upsert(self, profile_id: int, ad_account_id: str, entities: list[dict]) -> dict:
        p = self._profile(profile_id)
        brand = self.q1("SELECT * FROM brands WHERE id=?", (self._brand_id(profile_id),))
        if brand["meta_ad_account_id"] and str(brand["meta_ad_account_id"]) != str(ad_account_id):
            raise AdMemoryError("varlıklar profilin reklam hesabına ait değil (profil yalıtımı, 2.3)")
        n = 0
        linked = 0
        with self.tx():
            for e in entities:
                lvl = e.get("level")
                if lvl not in ("campaign", "adset", "ad"):
                    raise AdMemoryError("level: campaign | adset | ad")
                mid = str(e.get("meta_id") or e.get("id") or "")
                if not mid:
                    raise AdMemoryError("her varlık meta_id taşımalı")
                other = self.q1("SELECT brand_id FROM meta_entities WHERE level=? AND meta_id=?", (lvl, mid))
                if other and other["brand_id"] != brand["id"]:
                    raise AdMemoryError(f"Meta varlığı {mid} başka bir profile kayıtlı; yazılmadı")
                self.ex("""INSERT INTO meta_entities(brand_id,ad_account_id,level,meta_id,parent_meta_id,name,status,objective,created_time,creative_id,raw_json,synced_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(level, meta_id) DO UPDATE SET parent_meta_id=excluded.parent_meta_id, name=excluded.name,
                             status=excluded.status, objective=excluded.objective, created_time=excluded.created_time,
                             creative_id=excluded.creative_id, raw_json=excluded.raw_json, synced_at=excluded.synced_at""",
                        (brand["id"], str(ad_account_id), lvl, mid, e.get("parent_meta_id"), e.get("name"), e.get("status"),
                         e.get("objective"), e.get("created_time"), e.get("creative_id"), jdump(e.get("raw")), now_iso()))
                n += 1
                if lvl == "ad":
                    ck = naming.match_ad_name(e.get("name") or "")
                    camp = self._campaign_for_key(brand["id"], ck) if ck else None
                    self.ex("""INSERT INTO ads(brand_id,campaign_id,cycle_id,creative_key,meta_ad_id,meta_ad_name,adset_id,campaign_meta_id,launched_at,status)
                               VALUES(?,?,?,?,?,?,?,?,?,?)
                               ON CONFLICT(brand_id, meta_ad_id) DO UPDATE SET meta_ad_name=excluded.meta_ad_name, status=excluded.status,
                                 adset_id=COALESCE(ads.adset_id, excluded.adset_id),
                                 creative_key=COALESCE(ads.creative_key, excluded.creative_key),
                                 campaign_id=COALESCE(ads.campaign_id, excluded.campaign_id),
                                 cycle_id=COALESCE(ads.cycle_id, excluded.cycle_id)""",
                            (brand["id"], camp["campaign_id"] if camp else None, camp["cycle_id"] if camp else None, ck, mid,
                             e.get("name"), e.get("parent_meta_id"), (e.get("raw") or {}).get("campaign_id"), e.get("created_time"),
                             e.get("status")))
                    linked += 1 if ck else 0
            self.ex("UPDATE profiles SET last_meta_sync_at=? WHERE id=?", (now_iso(), p["id"]))
        return {"upserted": n, "ads_matching_naming_rule": linked}

    def _campaign_for_key(self, brand_id: int, creative_key: str) -> dict | None:
        r = self.q1("""SELECT cr.campaign_id, cr.cycle_id FROM creatives cr JOIN campaigns c ON c.id=cr.campaign_id
                       WHERE c.brand_id=? AND cr.creative_key=? ORDER BY cr.id DESC LIMIT 1""", (brand_id, creative_key))
        return r

    def benchmarks_upsert(self, profile_id: int, items: list[dict]) -> dict:
        bid = self._brand_id(profile_id)
        with self.tx():
            for it in items:
                self.ex("""INSERT INTO account_benchmarks(brand_id,kind,metric,value,context_json,fetched_at) VALUES(?,?,?,?,?,?)
                           ON CONFLICT(brand_id,kind,metric) DO UPDATE SET value=excluded.value, context_json=excluded.context_json, fetched_at=excluded.fetched_at""",
                        (bid, it["kind"], it["metric"], it.get("value"), jdump(it.get("context")), now_iso()))
        return {"benchmarks": self.qa("SELECT * FROM account_benchmarks WHERE brand_id=? ORDER BY kind, metric", (bid,))}

    def benchmarks_get(self, profile_id: int) -> dict:
        bid = self._brand_id(profile_id)
        return {"benchmarks": self.qa("SELECT * FROM account_benchmarks WHERE brand_id=? ORDER BY kind, metric", (bid,))}

    # --- önseller (6.6) -----------------------------------------------------------
    def priors_set(self, profile_id: int, objective: str, metric: str, a: float, b: float, n_source: float,
                   source: str, n_cap: float = 30, source_cutoff_at: str | None = None, source_summary: dict | None = None) -> dict:
        bid = self._brand_id(profile_id)
        if a <= 0 or b <= 0:
            raise AdMemoryError("Beta parametreleri pozitif olmalı")
        with self.tx():
            self.ex("""INSERT INTO priors(brand_id,objective,metric,dist,a,b,n_source,n_cap,source,source_cutoff_at,source_summary_json,updated_at)
                       VALUES(?,?,?,'beta',?,?,?,?,?,?,?,?)
                       ON CONFLICT(brand_id,objective,metric) DO UPDATE SET a=excluded.a, b=excluded.b, n_source=excluded.n_source,
                         n_cap=excluded.n_cap, source=excluded.source, source_cutoff_at=excluded.source_cutoff_at,
                         source_summary_json=excluded.source_summary_json, updated_at=excluded.updated_at""",
                    (bid, objective, metric, float(a), float(b), float(n_source), float(n_cap), source, source_cutoff_at,
                     jdump(source_summary), now_iso()))
        return self.q1("SELECT * FROM priors WHERE brand_id=? AND objective=? AND metric=?", (bid, objective, metric))

    def priors_get(self, profile_id: int, objective: str | None = None) -> dict:
        bid = self._brand_id(profile_id)
        if objective:
            rows = self.qa("SELECT * FROM priors WHERE brand_id=? AND objective=?", (bid, objective))
        else:
            rows = self.qa("SELECT * FROM priors WHERE brand_id=?", (bid,))
        return {"priors": rows, "default": "Geçmiş yoksa Beta(1,1) (6.6)"}

    PRIOR_METRICS = {"hook_rate": ("video_3s", "impressions"), "ctr_link": ("link_clicks", "impressions"),
                     "hold_rate": ("thruplay", "video_3s"), "cvr": ("purchases", "link_clicks")}

    def priors_from_history(self, profile_id: int, objective: str, cutoff_at: str, n_cap: float = 30,
                            min_impressions: int = 1000) -> dict:
        """Aynı profil ve objective için, test başlamadan önceki uygun geçmişten Beta önselleri (6.6)."""
        bid = self._brand_id(profile_id)
        cutoff = _date(cutoff_at[:10])
        rows = self.qa("""SELECT a.id AS ad_id, SUM(m.impressions) AS impressions, SUM(m.video_3s) AS video_3s, SUM(m.thruplay) AS thruplay,
                                 SUM(m.link_clicks) AS link_clicks, SUM(m.purchases) AS purchases
                          FROM metrics_daily m JOIN ads a ON a.id=m.ad_id
                          LEFT JOIN meta_entities e ON e.level='ad' AND e.meta_id=a.meta_ad_id
                          LEFT JOIN meta_entities ad_set ON ad_set.level='adset' AND ad_set.meta_id=e.parent_meta_id
                          LEFT JOIN meta_entities cmp ON cmp.level='campaign' AND cmp.meta_id=ad_set.parent_meta_id
                          WHERE a.brand_id=? AND m.date < ? AND (cmp.objective=? OR (cmp.objective IS NULL AND ?='*'))
                          GROUP BY a.id""", (bid, cutoff, objective, objective))
        result = {}
        for metric, (num, den) in self.PRIOR_METRICS.items():
            ratios = []
            for r in rows:
                if (r["impressions"] or 0) < min_impressions:
                    continue
                n, d = r[num], r[den]
                if n is None or not d or n > d:
                    continue
                ratios.append(n / d)
            if not ratios:
                result[metric] = {"a": 1.0, "b": 1.0, "n_source": 0, "source": "uniform", "note": "uygun geçmiş yok → Beta(1,1)"}
                continue
            m = sum(ratios) / len(ratios)
            n_eff = min(len(ratios), n_cap)
            a = max(0.001, m * n_eff)
            b = max(0.001, (1 - m) * n_eff)
            if a + b > n_cap:
                s = n_cap / (a + b)
                a, b = a * s, b * s
            result[metric] = {"a": round(a, 6), "b": round(b, 6), "n_source": len(ratios), "mean": round(m, 6), "source": "history"}
        with self.tx():
            for metric, r in result.items():
                self.priors_set(profile_id, objective, metric, r["a"], r["b"], r["n_source"], r["source"], n_cap, cutoff,
                                {"n_ads": r["n_source"], "mean": r.get("mean"), "min_impressions": min_impressions})
        return {"objective": objective, "source_cutoff_at": cutoff, "priors": result}

    # --- metrikler (6.4) -------------------------------------------------------
    def _ad_row(self, brand_id: int, meta_ad_id: str, ad_name: str | None) -> dict:
        r = self.q1("SELECT * FROM ads WHERE brand_id=? AND meta_ad_id=?", (brand_id, str(meta_ad_id)))
        if r:
            return r
        ck = naming.match_ad_name(ad_name or "")
        camp = self._campaign_for_key(brand_id, ck) if ck else None
        aid = self.ex("INSERT INTO ads(brand_id,campaign_id,cycle_id,creative_key,meta_ad_id,meta_ad_name,status) VALUES(?,?,?,?,?,?,?)",
                      (brand_id, camp["campaign_id"] if camp else None, camp["cycle_id"] if camp else None, ck, str(meta_ad_id),
                       ad_name, "unknown")).lastrowid
        return self.q1("SELECT * FROM ads WHERE id=?", (aid,))

    def metrics_ingest(self, profile_id: int, rows: list[dict], source: str, measurement_context: dict,
                       completion_evidence: str | None = None, decimal: str | None = None) -> dict:
        """Günlük satırları tek işlemde UPSERT eder; tanımı uyuşmayan tek satırda bile tüm içe alma geri alınır (6.4, 7.4)."""
        self._profile(profile_id)
        bid = self._brand_id(profile_id)
        brand = self.q1("SELECT * FROM brands WHERE id=?", (bid,))
        if source not in ("meta_mcp", "csv", "synthetic"):
            raise AdMemoryError("source: meta_mcp | csv")
        ctx = dict(measurement_context or {})
        missing = [k for k in CONTEXT_DEF_KEYS if k not in ctx]
        if missing:
            raise AdMemoryError("ölçüm bağlamı zorunlu alanları eksik: " + ", ".join(missing)
                                + " (doğrulanamayan alan null ve gerekçesiyle yazılır, tahmin edilmez; 6.4)")
        nulls = [k for k in CONTEXT_DEF_KEYS if ctx.get(k) is None]
        reasons = ctx.get("null_reasons") or {}
        lacking = [k for k in nulls if k not in reasons]
        if lacking:
            raise AdMemoryError("null bağlam alanları gerekçe ister (null_reasons): " + ", ".join(lacking))
        if brand["meta_ad_account_id"] and ctx.get("account_id") and str(ctx["account_id"]) != str(brand["meta_ad_account_id"]):
            raise AdMemoryError("ölçüm bağlamındaki hesap profilin hesabı değil (profil yalıtımı)")
        fp = measurement_fingerprint(ctx)
        fetched = ctx.get("fetched_at") or now_iso()
        ctx_store = {**ctx, "source": source, "fetched_at": fetched}
        inserted = updated = 0
        with self.tx():
            for r in rows:
                mid = r.get("meta_ad_id") or r.get("ad_id")
                if not mid:
                    raise AdMemoryError("her satır meta_ad_id taşımalı")
                day = _date(r["date"])
                ad = self._ad_row(bid, str(mid), r.get("ad_name"))
                vals: dict[str, Any] = {}
                for k in METRIC_COLS:
                    if k == "result_type":
                        vals[k] = r.get(k)
                        continue
                    v = _num(r.get(k), decimal)
                    vals[k] = (int(round(v)) if (v is not None and k in INT_COLS) else v)
                derived = 0
                if vals.get("video_3s") is None:
                    cpvv = _num(r.get("cost_per_video_view"), decimal)
                    if cpvv and vals.get("spend") is not None:
                        vals["video_3s"] = round(vals["spend"] / cpvv, 3)
                        derived = 1
                if vals.get("impressions") is not None and vals.get("spend") is not None and vals.get("cpm") is None and vals["impressions"] > 0:
                    vals["cpm"] = round(vals["spend"] / vals["impressions"] * 1000, 4)
                ex = self.q1("SELECT measurement_fingerprint, measurement_context_json FROM metrics_daily WHERE ad_id=? AND date=?", (ad["id"], day))
                if ex and ex["measurement_fingerprint"] != fp:
                    old = ex["measurement_context_json"] if isinstance(ex["measurement_context_json"], dict) else jload(ex["measurement_context_json"], {})
                    if not self._completes_unknown(old, ctx) or not completion_evidence:
                        diff = [k for k in CONTEXT_DEF_KEYS if old.get(k) != ctx.get(k)]
                        raise AdMemoryError(f"ölçüm tanımı uyuşmuyor (reklam {mid}, {day}; farklı alanlar: {', '.join(diff)}). "
                                            "İçe alma tamamen geri alındı. Aynı atıf penceresi/saat dilimi/sonuç tanımıyla dışa aktarım gerekir (6.4).")
                    ctx_store["completion_evidence"] = completion_evidence
                cols = ["ad_id", "date", *METRIC_COLS, "video_3s_derived", "source", "fetched_at", "measurement_context_json", "measurement_fingerprint"]
                args = [ad["id"], day, *[vals[k] for k in METRIC_COLS], derived, source, fetched, jdump(ctx_store), fp]
                upd = ", ".join(f"{c}=excluded.{c}" for c in cols[2:])
                self.ex(f"INSERT INTO metrics_daily({', '.join(cols)}) VALUES({', '.join('?' * len(cols))}) "
                        f"ON CONFLICT(ad_id, date) DO UPDATE SET {upd}", tuple(args))
                if ex:
                    updated += 1
                else:
                    inserted += 1
        return {"inserted": inserted, "updated": updated, "fingerprint": fp, "source": source}

    @staticmethod
    def _completes_unknown(old: dict, new: dict) -> bool:
        for k in CONTEXT_DEF_KEYS:
            if old.get(k) is None:
                continue
            if old.get(k) != new.get(k):
                return False
        return any(old.get(k) is None and new.get(k) is not None for k in CONTEXT_DEF_KEYS)

    def metrics_import_csv(self, profile_id: int, path: str, measurement_context: dict,
                           column_map: dict | None = None, completion_evidence: str | None = None) -> dict:
        p = Path(path)
        if not p.is_absolute():
            p = self.data_dir / p
        if not p.exists():
            raise AdMemoryError(f"CSV bulunamadı: {p}")
        raw = p.read_bytes()
        for enc in ("utf-8-sig", "utf-16", "cp1254", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        sample = text[:4096]
        delim = ";" if sample.count(";") > sample.count(",") else ("\t" if sample.count("\t") > sample.count(",") else ",")
        reader = csv.DictReader(io.StringIO(text), delimiter=delim)
        headers = reader.fieldnames or []
        fields = json.loads((SERVER_DIR / "meta_fields.json").read_text(encoding="utf-8"))["fields"]
        cmap: dict[str, str] = {}
        for key, spec in fields.items():
            for h in spec.get("csv_headers", []):
                for real in headers:
                    if real and real.strip().lower() == h.lower():
                        cmap.setdefault(key, real)
        if column_map:
            cmap.update(column_map)
        need = ["date", "ad_id", "impressions", "spend"]
        absent = [k for k in need if k not in cmap]
        if absent:
            raise AdMemoryError("CSV'de zorunlu sütunlar bulunamadı: " + ", ".join(absent)
                                + f". Başlıklar: {headers[:20]}. Reklam düzeyi, günlük, video sütunlu dışa aktarım gerekir (9.2).")
        rows = []
        for r in reader:
            if not r.get(cmap["ad_id"]):
                continue
            row = {"meta_ad_id": r[cmap["ad_id"]].strip(), "date": r[cmap["date"]], "ad_name": r.get(cmap.get("ad_name", ""), None)}
            for k, real in cmap.items():
                if k in ("ad_id", "date", "ad_name"):
                    continue
                row[k] = r.get(real)
            rows.append(row)
        dec = (measurement_context or {}).get("csv_decimal") or detect_decimal([r.get("spend") for r in rows][:200])
        res = self.metrics_ingest(profile_id, rows, "csv", measurement_context, completion_evidence, dec)
        res["decimal"] = dec
        res.update({"rows": len(rows), "columns": cmap, "file": str(p)})
        return res

    def metrics_daily_rows(self, profile_id: int, campaign_id: int | None = None, cycle_id: int | None = None,
                           date_from: str | None = None, date_to: str | None = None, fingerprint: str | None = None) -> dict:
        bid = self._brand_id(profile_id)
        sql = """SELECT m.*, a.meta_ad_id, a.meta_ad_name, a.creative_key, a.campaign_id, a.cycle_id, a.adset_id
                 FROM metrics_daily m JOIN ads a ON a.id=m.ad_id WHERE a.brand_id=?"""
        args: list[Any] = [bid]
        if campaign_id is not None:
            self._campaign(profile_id, campaign_id)
            sql += " AND a.campaign_id=?"
            args.append(campaign_id)
        if cycle_id is not None:
            sql += " AND a.cycle_id=?"
            args.append(cycle_id)
        if date_from:
            sql += " AND m.date>=?"
            args.append(_date(date_from))
        if date_to:
            sql += " AND m.date<=?"
            args.append(_date(date_to))
        if fingerprint:
            sql += " AND m.measurement_fingerprint=?"
            args.append(fingerprint)
        return {"rows": self.qa(sql + " ORDER BY a.meta_ad_id, m.date", tuple(args))}

    @staticmethod
    def test_window_days(test_start: str, test_end: str, tzname: str | None) -> dict:
        """[test_start, test_end) aralığında bütünüyle kalan hesap-günleri (6.4). Sınır günleri dışlanır; bölünmez."""
        import zoneinfo
        tz = zoneinfo.ZoneInfo(tzname) if tzname else dt.timezone.utc
        s = parse_iso(test_start).astimezone(tz)
        e = parse_iso(test_end).astimezone(tz)
        full, excluded = [], []
        d = s.date()
        while d <= e.date():
            day_start = dt.datetime.combine(d, dt.time(0, 0), tz)
            day_end = day_start + dt.timedelta(days=1)
            if day_start >= s and day_end <= e:
                full.append(d.isoformat())
            elif day_end > s and day_start < e:
                excluded.append(d.isoformat())
            d += dt.timedelta(days=1)
        return {"full_days": full, "excluded_boundary_days": excluded, "timezone": str(tz)}

    def metrics_query(self, profile_id: int, campaign_id: int | None = None, cycle_id: int | None = None,
                      level: str = "creative", window: str = "all", date_from: str | None = None,
                      date_to: str | None = None, fingerprint: str | None = None) -> dict:
        """Kreatif (creative_key; formatlar birleşik) → konsept → kampanya toplama. Erişim reklam/gün toplanmaz (6.4)."""
        if level not in ("ad", "creative", "concept", "campaign"):
            raise AdMemoryError("level: ad | creative | concept | campaign")
        rows = self.metrics_daily_rows(profile_id, campaign_id, cycle_id, date_from, date_to, fingerprint)["rows"]
        excluded: list[str] = []
        if window == "test":
            if cycle_id is None:
                raise AdMemoryError("window=test için cycle_id gerekli")
            cy = self._cycle(profile_id, cycle_id)
            if not (cy["test_start"] and cy["test_end"]):
                raise AdMemoryError("turun test_start/test_end değerleri yok")
            tz = (self.q1("SELECT timezone FROM brands WHERE id=?", (self._brand_id(profile_id),)) or {}).get("timezone")
            w = self.test_window_days(cy["test_start"], cy["test_end"], tz)
            keep = set(w["full_days"])
            excluded = w["excluded_boundary_days"]
            rows = [r for r in rows if r["date"] in keep]
        fps = sorted({r["measurement_fingerprint"] for r in rows})
        concept_of: dict[str, str] = {}
        if level in ("concept",):
            for cr in self.qa("""SELECT cr.creative_key, k.code FROM creatives cr LEFT JOIN concepts k ON k.id=cr.concept_id
                                 WHERE cr.campaign_id IN (SELECT id FROM campaigns WHERE brand_id=?)""", (self._brand_id(profile_id),)):
                concept_of[cr["creative_key"]] = cr["code"]
        groups: dict[str, dict] = {}
        for r in rows:
            if level == "ad":
                key = r["meta_ad_id"]
            elif level == "creative":
                key = r["creative_key"] or f"(eşlenmemiş) {r['meta_ad_id']}"
            elif level == "concept":
                key = concept_of.get(r["creative_key"] or "", "(konseptsiz)")
            else:
                key = str(r["campaign_id"])
            g = groups.setdefault(key, {"key": key, "days": set(), "ads": set(), "fingerprints": set(),
                                        **{k: 0.0 for k in ("impressions", "spend", "video_3s", "thruplay", "link_clicks", "results",
                                                            "purchases", "revenue", "add_to_cart", "p25", "p50", "p75", "p95", "p100")}})
            g["days"].add(r["date"])
            g["ads"].add(r["meta_ad_id"])
            g["fingerprints"].add(r["measurement_fingerprint"])
            for k in ("impressions", "spend", "video_3s", "thruplay", "link_clicks", "results", "purchases", "revenue",
                      "add_to_cart", "p25", "p50", "p75", "p95", "p100"):
                if r.get(k) is not None:
                    g[k] += float(r[k])
        out = []
        for g in groups.values():
            imp = g["impressions"]
            out.append({**{k: v for k, v in g.items() if k not in ("days", "ads", "fingerprints")},
                        "n_days": len(g["days"]), "n_ads": len(g["ads"]), "mixed_definitions": len(g["fingerprints"]) > 1,
                        "hook_rate": (g["video_3s"] / imp) if imp else None,
                        "hold_rate": (g["thruplay"] / g["video_3s"]) if g["video_3s"] else None,
                        "ctr_link": (g["link_clicks"] / imp) if imp else None,
                        "cvr": (g["purchases"] / g["link_clicks"]) if g["link_clicks"] else None,
                        "cpm": (g["spend"] / imp * 1000) if imp else None,
                        "cost_per_result": (g["spend"] / g["results"]) if g["results"] else None,
                        "roas": (g["revenue"] / g["spend"]) if g["spend"] else None,
                        "reach_note": "erişim reklam/gün toplanmaz; dönem frekansı yalnızca Meta'nın tekilleştirilmiş erişimiyle"})
        return {"level": level, "window": window, "excluded_boundary_days": excluded, "fingerprints": fps,
                "groups": sorted(out, key=lambda x: str(x["key"]))}

    def metrics_export_csv(self, profile_id: int, path: str, campaign_id: int | None = None) -> dict:
        rows = self.metrics_daily_rows(profile_id, campaign_id)["rows"]
        p = Path(path)
        if not p.is_absolute():
            p = self.data_dir / p
        buf = io.StringIO()
        cols = ["meta_ad_id", "meta_ad_name", "creative_key", "date", *METRIC_COLS, "video_3s_derived", "source", "fetched_at",
                "measurement_fingerprint", "measurement_context_json"]
        w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            r = dict(r)
            r["measurement_context_json"] = json.dumps(r["measurement_context_json"], ensure_ascii=False) if isinstance(r["measurement_context_json"], dict) else r["measurement_context_json"]
            w.writerow(r)
        sha = atomic_write(p, buf.getvalue())
        return {"path": str(p), "rows": len(rows), "sha256": sha}

    def history_summary(self, profile_id: int) -> dict:
        bid = self._brand_id(profile_id)
        p = self._profile(profile_id, allow_archived=True)
        ent = {r["level"]: r["n"] for r in self.qa("SELECT level, COUNT(*) AS n FROM meta_entities WHERE brand_id=? GROUP BY level", (bid,))}
        objs = self.qa("SELECT objective, COUNT(*) AS n FROM meta_entities WHERE brand_id=? AND level='campaign' GROUP BY objective", (bid,))
        rng = self.q1("""SELECT MIN(m.date) AS first, MAX(m.date) AS last, SUM(m.spend) AS spend, SUM(m.impressions) AS impressions, COUNT(DISTINCT m.ad_id) AS ads
                         FROM metrics_daily m JOIN ads a ON a.id=m.ad_id WHERE a.brand_id=?""", (bid,))
        named = self.q1("SELECT COUNT(*) AS n FROM ads WHERE brand_id=? AND creative_key IS NOT NULL", (bid,))["n"]
        total = self.q1("SELECT COUNT(*) AS n FROM ads WHERE brand_id=?", (bid,))["n"]
        return {"profile": p["name"], "history_status": p["history_status"], "last_meta_sync_at": p["last_meta_sync_at"],
                "meta_data_mode": p["meta_data_mode"], "entities": ent, "objectives": objs, "metrics": rng,
                "ads_total": total, "ads_matching_naming_rule": named,
                "priors": self.qa("SELECT objective, metric, a, b, n_source, source FROM priors WHERE brand_id=?", (bid,))}

    def ad_link(self, profile_id: int, campaign_id: int, cycle_id: int, creative_key: str, meta_ad_id: str,
                adset_id: str | None = None, meta_ad_name: str | None = None) -> dict:
        c = self._campaign(profile_id, campaign_id)
        self._cycle(profile_id, cycle_id, campaign_id)
        if not self.q1("SELECT 1 FROM creatives WHERE campaign_id=? AND creative_key=?", (campaign_id, creative_key)):
            raise AdMemoryError(f"creative_key bu kampanyada yok: {creative_key}")
        with self.tx():
            self.ex("""INSERT INTO ads(brand_id,campaign_id,cycle_id,creative_key,meta_ad_id,meta_ad_name,adset_id,status) VALUES(?,?,?,?,?,?,?, 'active')
                       ON CONFLICT(brand_id, meta_ad_id) DO UPDATE SET campaign_id=excluded.campaign_id, cycle_id=excluded.cycle_id,
                         creative_key=excluded.creative_key, adset_id=COALESCE(excluded.adset_id, ads.adset_id),
                         meta_ad_name=COALESCE(excluded.meta_ad_name, ads.meta_ad_name)""",
                    (c["brand_id"], campaign_id, cycle_id, creative_key, str(meta_ad_id), meta_ad_name, adset_id))
        return self.q1("SELECT * FROM ads WHERE brand_id=? AND meta_ad_id=?", (c["brand_id"], str(meta_ad_id)))

    # --- elle satış (6.2) --------------------------------------------------------
    def sales_add(self, profile_id: int, campaign_id: int, period_start: str, period_end: str, units: int | None,
                  revenue: float | None, source_note: str | None = None, channel: str | None = None, kind: str = "sale") -> dict:
        self._campaign(profile_id, campaign_id)
        ps, pe = _date(period_start), _date(period_end)
        if pe < ps:
            raise AdMemoryError("dönem sonu başlangıçtan önce olamaz")
        if channel is not None and channel not in SALES_CHANNELS:
            raise AdMemoryError(f"kanal: {' | '.join(SALES_CHANNELS)}")
        if kind not in ("sale", "lead"):
            raise AdMemoryError("kind: sale (satış) | lead (talep/teklif isteği, ör. kurumsal DM)")
        with self.tx():
            sid = self.ex("""INSERT INTO sales_manual(campaign_id,period_start,period_end,units,revenue,source_note,channel,kind,created_at)
                             VALUES(?,?,?,?,?,?,?,?,?)""",
                          (campaign_id, ps, pe, units, revenue, source_note, channel, kind, now_iso())).lastrowid
        return {**self.q1("SELECT * FROM sales_manual WHERE id=?", (sid,)),
                "note": "Atıf varsayımı raporda açıkça yazılır; dönem satışının tamamı reklamın yarattığı satış sayılmaz; kreatiflere dağıtılmaz (6.2). "
                        "Kanal ayrı tutulur: DM/WhatsApp/kurumsal satış ve talepler Meta'da görünmez, kampanya sonucuna ayrıca eklenir (1.4.7)."}

    # --- Meta satış sinyali (1.4.7): Meta satışı görüyor mu? ---------------------------
    def meta_signal_set(self, profile_id: int, status: str, source: str, evidence: str, choice: str | None = None,
                        checked_at: str | None = None) -> dict:
        """S00b/S01: veri kümesinde son 7 günde Purchase olayı var mı. status purchase_seen yalnızca okunan kanıtla (ads_get_dataset_stats)
        ya da kullanıcının Events Manager'dan gösterdiği kanıtla yazılır; tahmin edilmez. no_purchase'ta seçilen yol choice ile kaydedilir."""
        p = self._profile(profile_id)
        if status not in META_SIGNAL_STATUSES:
            raise AdMemoryError(f"status: {' | '.join(META_SIGNAL_STATUSES)}")
        if source not in ("meta_mcp", "user_evidence", "csv"):
            raise AdMemoryError("source: meta_mcp (salt okuma araç sonucu) | user_evidence (Events Manager kanıtı) | csv")
        if not (evidence and evidence.strip()):
            raise AdMemoryError("kanıt (evidence) zorunlu: hangi veri kümesi, hangi olay, hangi tarih aralığı")
        if choice is not None and choice not in META_SIGNAL_CHOICES:
            raise AdMemoryError(f"choice: {' | '.join(META_SIGNAL_CHOICES)}")
        if status == "purchase_seen" and choice is not None:
            choice = None
        rec = {"status": status, "source": source, "evidence": evidence.strip(), "choice": choice, "checked_at": checked_at or now_iso()}
        with self.tx():
            self.ex("UPDATE profiles SET meta_signal_json=? WHERE id=?", (jdump(rec), p["id"]))
        return {"profile_id": p["id"], "meta_signal": rec, "rule": META_SIGNAL_RULE}

    def meta_signal_get(self, profile_id: int) -> dict:
        p = self._profile(profile_id)
        rec = jload(p.get("meta_signal_json"), None) if isinstance(p.get("meta_signal_json"), (str, type(None))) else p.get("meta_signal_json")
        return {"profile_id": p["id"], "meta_signal": rec or {"status": "unknown"}, "rule": META_SIGNAL_RULE}

    def sales_list(self, profile_id: int, campaign_id: int) -> dict:
        self._campaign(profile_id, campaign_id)
        return {"sales": self.qa("SELECT * FROM sales_manual WHERE campaign_id=? ORDER BY period_start", (campaign_id,))}
