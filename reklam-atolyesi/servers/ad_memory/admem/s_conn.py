"""Veri bağlantısı planı ve mağaza sipariş içe aktarma (1.4.8).

- Veri bağlantısı planı: markanın nerede sattığı, ayarlara erişimi, müşteri verisini Meta'ya gönderme tercihi, seçilen yol(lar) ve her yolun
  dayandığı RESMİ kaynak (bağlantı + kontrol tarihi + durum). Platforma özgü adım kaynağı okunmadan "doğrulandı" sayılmaz.
- Sipariş içe aktarma: her mağaza platformunun dışa aktardığı CSV; yalnızca eşlenen sütunlar okunur (tarih, sipariş no, tutar, adet,
  durum, para birimi). Sipariş numarası saklanmaz, SHA-256 özeti saklanır; ad, adres, telefon, e-posta okunmaz.
"""
from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path
from typing import Any

from .util import AdMemoryError, jdump, jload, now_iso, sha256_file

CONNECTION_PATHS = ("platform_integration", "pixel_code", "events_upload", "order_import", "manual_entry", "messaging_only")
SALES_PLACES = ("site", "shopier", "pazaryeri", "instagram_dm", "messenger", "whatsapp", "telefon", "kurumsal", "magaza", "diger")
SOURCE_STATUS = ("verified", "not_found", "unverified")
ORDER_STATUSES = ("paid", "pending", "cancelled", "refunded", "unknown")
MAX_IMPORT_BYTES = 50 * 1024 * 1024


def _read_csv(path: Path) -> tuple[list[dict], str, str]:
    raw = path.read_bytes()
    if len(raw) > MAX_IMPORT_BYTES:
        raise AdMemoryError("dosya 50 MB'tan büyük: tarih aralığını daraltıp yeniden dışa aktarın")
    if raw[:4] == b"PK\x03\x04":
        raise AdMemoryError("dosya Excel (xlsx) görünüyor: platformdan CSV olarak dışa aktarın ya da Excel'de 'CSV UTF-8' olarak kaydedin")
    text, enc = None, None
    for e in ("utf-8-sig", "cp1254", "latin-1"):
        try:
            text, enc = raw.decode(e), e
            break
        except UnicodeDecodeError:
            continue
    sample = text[:20000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delim = dialect.delimiter
    except csv.Error:
        delim = ";" if sample.count(";") > sample.count(",") else ","
    rows = list(csv.DictReader(io.StringIO(text), delimiter=delim))
    return rows, enc, delim


def _order_date(raw: str, fmt: str | None, fallback) -> str:
    import datetime as dt
    if fmt:
        for cand in (raw, raw[:10], raw[:16], raw[:19]):
            try:
                return dt.datetime.strptime(cand, fmt).date().isoformat()
            except ValueError:
                continue
        raise AdMemoryError(f"tarih '{fmt}' biçimiyle okunamadı: {raw!r}")
    try:
        return fallback(raw)
    except AdMemoryError:
        raise AdMemoryError(f"tarih okunamadı: {raw!r}; date_format verin (ör. '%d.%m.%Y' ya da '%m/%d/%Y')")


class ConnMixin:
    # --- veri bağlantısı planı ---------------------------------------------------------
    def data_connection_set(self, profile_id: int, plan: dict) -> dict:
        p = self._profile(profile_id)
        if not isinstance(plan, dict):
            raise AdMemoryError("plan bir nesne olmalı")
        places = plan.get("sales_places") or []
        if not places:
            raise AdMemoryError("en az bir satış yeri (sales_places) gerekli: nerede satıyorsunuz?")
        for pl in places:
            if pl.get("kind") not in SALES_PLACES:
                raise AdMemoryError(f"sales_places.kind: {' | '.join(SALES_PLACES)}")
        paths = plan.get("chosen_paths") or []
        for c in paths:
            if c not in CONNECTION_PATHS:
                raise AdMemoryError(f"chosen_paths: {' | '.join(CONNECTION_PATHS)}")
        for s in plan.get("sources") or []:
            if s.get("status") not in SOURCE_STATUS:
                raise AdMemoryError(f"sources.status: {' | '.join(SOURCE_STATUS)}")
            url = str(s.get("url") or "")
            if s["status"] == "verified" and not (url.startswith("https://") and s.get("checked_at") and s.get("path") in CONNECTION_PATHS):
                raise AdMemoryError("'verified' kaynak, okunan resmi sayfanın https bağlantısını, kontrol tarihini ve hangi yol için olduğunu ister")
        pref = (plan.get("preference") or {}).get("customer_data_to_meta", "undecided")
        if pref not in ("allowed", "not_allowed", "undecided"):
            raise AdMemoryError("preference.customer_data_to_meta: allowed | not_allowed | undecided")
        if "events_upload" in paths and pref != "allowed":
            raise AdMemoryError("satış yükleme (events_upload) müşteri e-posta/telefonunun Meta'ya gitmesi demektir: kullanıcı bunu açıkça "
                                "kabul etmeden (preference.customer_data_to_meta='allowed') ve KVKK dayanağı olmadan seçilemez")
        status = plan.get("status", "planned")
        if status not in ("planned", "in_progress", "done", "blocked"):
            raise AdMemoryError("status: planned | in_progress | done | blocked")
        if status == "done":
            meta_paths = {"platform_integration", "pixel_code", "events_upload"} & set(paths)
            sig = self.meta_signal_get(profile_id)["meta_signal"]
            if meta_paths and sig.get("status") != "purchase_seen":
                raise AdMemoryError("Meta'ya satış gönderen yol 'tamam' sayılmaz: S00b 6b kontrolü Purchase olayını görmeli (meta_signal purchase_seen)")
            if "order_import" in paths and not self.q1("SELECT 1 FROM sales_imports WHERE brand_id=?", (p["brand_id"],)):
                raise AdMemoryError("sipariş içe aktarma 'tamam' sayılmaz: henüz hiç içe aktarma yok")
        rec = {**plan, "status": status, "updated_at": now_iso()}
        with self.tx():
            self.ex("UPDATE profiles SET data_connection_json=? WHERE id=?", (jdump(rec), p["id"]))
        return {"profile_id": p["id"], "data_connection": rec}

    def data_connection_get(self, profile_id: int) -> dict:
        p = self._profile(profile_id)
        v = p.get("data_connection_json")
        rec = jload(v, None) if isinstance(v, str) else v
        last_import = self.q1("SELECT platform, date_from, date_to, created_at FROM sales_imports WHERE brand_id=? ORDER BY id DESC LIMIT 1",
                              (p["brand_id"],)) if p["brand_id"] else None
        return {"profile_id": p["id"], "data_connection": rec, "meta_signal": self.meta_signal_get(profile_id)["meta_signal"],
                "last_order_import": last_import}

    # --- sipariş içe aktarma -----------------------------------------------------------------
    def sales_import_csv(self, profile_id: int, path: str, platform: str, mapping: dict, channel: str = "site",
                         status_map: dict | None = None, status_default: str | None = None, currency: str | None = None,
                         decimal: str | None = None, date_format: str | None = None) -> dict:
        """Mağaza sipariş dışa aktarımını okur. mapping: {date, order_id, amount?, units?, status?, currency?} → CSV sütun adları.
        Aynı sipariş birden çok satırdaysa (ürün satırları) tutar ilk dolu değer, adet satırların toplamıdır. Aynı dosya ikinci kez
        okunmaz; yeni dışa aktarımda durumu değişen sipariş (ör. bekliyor → ödendi) güncellenir."""
        import datetime as dt
        from .s_meta import SALES_CHANNELS, _date, _num, detect_decimal
        bid = self._brand_id(profile_id)
        if channel not in SALES_CHANNELS:
            raise AdMemoryError(f"kanal: {' | '.join(SALES_CHANNELS)}")
        plat = (platform or "").strip()
        if not plat:
            raise AdMemoryError("platform adı gerekli (ör. Shopify, İkas, Ticimax, Shopier, WooCommerce, Trendyol)")
        for k in ("date", "order_id"):
            if not mapping.get(k):
                raise AdMemoryError(f"mapping.{k} gerekli (CSV'deki sütun adı)")
        if not mapping.get("status") and status_default not in ORDER_STATUSES:
            raise AdMemoryError("durum sütunu yoksa status_default verin (ör. dosyada yalnızca tamamlanan siparişler varsa 'paid')")
        if status_default is not None and status_default not in ORDER_STATUSES:
            raise AdMemoryError(f"status_default: {' | '.join(ORDER_STATUSES)}")
        smap = {str(k).strip().casefold(): v for k, v in (status_map or {}).items()}
        for v in smap.values():
            if v not in ORDER_STATUSES:
                raise AdMemoryError(f"status_map değerleri: {' | '.join(ORDER_STATUSES)}")
        p = Path(path)
        if not p.is_file():
            raise AdMemoryError(f"dosya yok: {path}")
        sha = sha256_file(p)
        ex = self.q1("SELECT * FROM sales_imports WHERE brand_id=? AND file_sha256=?", (bid, sha))
        if ex:
            return {"import": ex, "reused": True, "note": "Bu dosya daha önce içe aktarıldı; yeniden sayılmadı."}
        rows, enc, delim = _read_csv(p)
        if not rows:
            raise AdMemoryError("dosyada satır yok")
        cols = set(rows[0].keys())
        missing = [f"{k}→{v}" for k, v in mapping.items() if v and v not in cols]
        if missing:
            raise AdMemoryError(f"CSV'de olmayan sütun: {', '.join(missing)}. Dosyadaki sütunlar: {', '.join(sorted(c for c in cols if c))}")
        dec = decimal or (detect_decimal([r.get(mapping["amount"]) for r in rows if r.get(mapping["amount"])][:200]) if mapping.get("amount") else ".")
        orders: dict[str, dict] = {}
        skipped: dict[str, int] = {}
        unmapped: dict[str, int] = {}
        for r in rows:
            oid = (r.get(mapping["order_id"]) or "").strip()
            if not oid:
                skipped["sipariş no boş"] = skipped.get("sipariş no boş", 0) + 1
                continue
            if "@" in oid:
                raise AdMemoryError("sipariş no sütunu e-posta içeriyor: yanlış sütun eşlendi (kişisel veri okunmaz)")
            o = orders.setdefault(oid, {"date": None, "amount": None, "units": 0, "status": None, "currency": None, "units_seen": False})
            if o["date"] is None and (r.get(mapping["date"]) or "").strip():
                raw_d = r[mapping["date"]].strip()
                o["date"] = _order_date(raw_d, date_format, _date)
            if mapping.get("amount") and o["amount"] is None and (r.get(mapping["amount"]) or "").strip():
                o["amount"] = _num(r[mapping["amount"]], dec)
            if mapping.get("units") and (r.get(mapping["units"]) or "").strip():
                u = _num(r[mapping["units"]], dec)
                if u is not None:
                    o["units"] += int(round(u))
                    o["units_seen"] = True
            if o["status"] is None:
                if mapping.get("status") and (r.get(mapping["status"]) or "").strip():
                    raw_s = r[mapping["status"]].strip()
                    st = smap.get(raw_s.casefold())
                    if st is None:
                        unmapped[raw_s] = unmapped.get(raw_s, 0) + 1
                        st = "unknown"
                    o["status"] = st
            if o["currency"] is None:
                o["currency"] = ((r.get(mapping["currency"]) or "").strip().upper() if mapping.get("currency") else None) or \
                    (currency.upper() if currency else None)
        for oid, o in orders.items():
            if o["status"] is None:
                o["status"] = status_default or "unknown"
        valid = {k: v for k, v in orders.items() if v["date"]}
        if len(valid) < len(orders):
            skipped["tarih yok"] = skipped.get("tarih yok", 0) + len(orders) - len(valid)
        now = now_iso()
        new = upd = dup = 0
        with self.tx():
            iid = self.ex("""INSERT INTO sales_imports(brand_id,campaign_id,platform,file_name,file_sha256,mapping_json,rows_total,rows_new,rows_dup,
                             rows_skipped,date_from,date_to,created_at) VALUES(?,?,?,?,?,?,?,0,0,?,?,?,?)""",
                          (bid, None, plat, p.name, sha, jdump({"mapping": mapping, "status_map": status_map, "status_default": status_default,
                                                               "channel": channel, "encoding": enc, "delimiter": delim, "decimal": dec}),
                           len(rows), sum(skipped.values()), min((v["date"] for v in valid.values()), default=None),
                           max((v["date"] for v in valid.values()), default=None), now)).lastrowid
            for oid, o in valid.items():
                h = hashlib.sha256(f"{bid}|{plat.casefold()}|{oid}".encode("utf-8")).hexdigest()
                cur = self.q1("SELECT * FROM sales_orders WHERE brand_id=? AND order_hash=?", (bid, h))
                units = o["units"] if o["units_seen"] else None
                if cur is None:
                    self.ex("""INSERT INTO sales_orders(brand_id,campaign_id,import_id,order_hash,date,amount,units,currency,status,channel,created_at)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (bid, None, iid, h, o["date"], o["amount"], units, o["currency"], o["status"],
                                                                 channel, now))
                    new += 1
                elif (cur["status"], cur["amount"]) != (o["status"], o["amount"]):
                    self.ex("UPDATE sales_orders SET status=?, amount=COALESCE(?, amount), units=COALESCE(?, units), import_id=? WHERE id=?",
                            (o["status"], o["amount"], units, iid, cur["id"]))
                    upd += 1
                else:
                    dup += 1
            self.ex("UPDATE sales_imports SET rows_new=?, rows_dup=? WHERE id=?", (new, dup, iid))
        counts = {s: sum(1 for v in valid.values() if v["status"] == s) for s in ORDER_STATUSES}
        return {"import": self.q1("SELECT * FROM sales_imports WHERE id=?", (iid,)), "orders": len(valid), "new": new, "updated": upd,
                "duplicates": dup, "skipped": skipped, "status_counts": counts, "unmapped_statuses": unmapped, "encoding": enc,
                "delimiter": delim, "decimal": dec,
                "note": ("Eşlenmeyen durumlar 'unknown' sayıldı ve satışa katılmadı; status_map ile eşleyip yeni dışa aktarımı okuyun. "
                         if unmapped else "") + "Ad, adres, telefon, e-posta okunmadı; sipariş numarası yalnızca özet (hash) olarak saklandı."}

    def sales_orders_summary(self, profile_id: int, date_from: str | None = None, date_to: str | None = None) -> dict:
        from .s_meta import _date
        bid = self._brand_id(profile_id)
        lo = _date(date_from) if date_from else "0000-01-01"
        hi = _date(date_to) if date_to else "9999-12-31"
        rows = self.qa("""SELECT date, channel, status, currency, COUNT(*) AS orders, SUM(COALESCE(units,0)) AS units, SUM(COALESCE(amount,0)) AS amount,
                                 SUM(CASE WHEN units IS NULL THEN 1 ELSE 0 END) AS units_unknown
                          FROM sales_orders WHERE brand_id=? AND date BETWEEN ? AND ? GROUP BY date, channel, status, currency ORDER BY date""",
                       (bid, lo, hi))
        return {"profile_id": int(profile_id), "period": [lo, hi], "daily": rows}
