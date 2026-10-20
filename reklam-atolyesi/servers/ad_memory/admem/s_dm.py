"""Mesajla satış (DM / WhatsApp / Messenger / telefon) kaydı ve hunisi (1.4.8).

İlkeler:
- Plugin mesaj okumaz ve göndermez; kayıt kullanıcıdan gelir (tek tek konuşma ya da günlük toplam). Taslakları kullanıcı gönderir.
- Kişisel veri tutulmaz: konuşma takma kodla (M-0001) izlenir; not/kanıt alanlarında telefon, e-posta, IBAN, kimlik numarası ya da
  @kullanıcı adı reddedilir.
- Kampanya/reklam bağı yalnızca kanıtla kurulur (source='ad' → source_evidence zorunlu); kanıtsız bağ kurulmaz.
- Günlük toplamlar markanın o gün ve kanaldaki BÜTÜN konuşmalarıdır; tek tek kaydedilen konuşmalar bu toplamın içindedir.
- Satış defteriyle çift sayım yok: mağaza bağlantısıyla ödenen DM satışı (paid_via='store_link') mağaza siparişlerinde zaten vardır;
  satış toplamına ayrıca eklenmez, yalnızca DM dönüşümünde sayılır.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any
from zoneinfo import ZoneInfo

from .util import AdMemoryError, now_iso, parse_iso, utcnow

DM_CHANNELS = ("instagram_dm", "messenger", "whatsapp", "phone", "web_chat", "email", "other")
DM_SOURCES = ("ad", "organic", "referral", "repeat", "unknown")
DM_SEGMENTS = ("individual", "corporate", "reseller", "unknown")
DM_INTENTS = ("price", "shipping", "personalization", "bulk", "stock", "payment", "return", "product_info", "other")
LOST_REASONS = ("price", "shipping_time", "shipping_cost", "no_reply", "stock", "personalization", "payment", "trust", "competitor", "other")
PAID_VIA = ("store_link", "bank_transfer", "cash_on_delivery", "card_link", "in_person", "other")
OPEN_STATES = ("open", "qualified", "quoted", "stale")
# Durum makinesi: olay → (izinli kaynak durumlar, hedef durum). responded/follow_up/note durumu değiştirmez.
TRANSITIONS = {
    "qualified": ({"open"}, "qualified"),
    "quoted": ({"open", "qualified", "quoted", "stale"}, "quoted"),
    "won": ({"open", "qualified", "quoted", "stale"}, "won"),
    "lost": ({"open", "qualified", "quoted", "stale"}, "lost"),
    "stale": ({"open", "qualified", "quoted"}, "stale"),
    "reopened": ({"lost", "stale", "won"}, "open"),  # won → open: yanlış girilmiş satışın düzeltilmesi (satış alanları silinir)
}
STATELESS_EVENTS = ("responded", "follow_up", "note")
STALE_AFTER_DAYS = 3  # yerel: son olaydan bu yana 3 gün sessiz açık konuşma takip listesine girer (Meta kuralı değil)

_PII = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "e-posta"),
    (re.compile(r"(?<!\w)@[A-Za-z0-9_.]{2,}"), "@kullanıcı adı"),
    (re.compile(r"\bTR\s?\d{2}(?:[\s.-]?\d{4}){5}[\s.-]?\d{2}\b", re.I), "IBAN"),
    (re.compile(r"(?<!\d)(?:\d[\s.-]?){21,25}\d(?!\d)"), "IBAN/hesap numarası"),
    # cep ve sabit hat, ayırıcı boşluk/nokta/tire/parantez (0532.123.45.67, (0216) 444 55 66, +90 212 …, 532 123 45 67). Başında 0 ya da
    # +90 olmayan grup yalnızca 5xx (cep) sayılır: "450 500 75 80 TL" gibi fiyat/adet dizileri telefon değildir.
    (re.compile(r"(?<!\d)(?:(?:\+|00)?90[\s.-]?\(?[2-5]\d{2}\)?|\(?0[2-5]\d{2}\)?|\(?5\d{2}\)?)[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2}(?!\d)"),
     "telefon"),
    (re.compile(r"(?<!\d)(?:\d{11}|5\d{9})(?!\d)"), "telefon/kimlik numarası"),  # 11 hane (TC kimlik, 05xx…) ya da 5 ile başlayan 10 hane
]


def pii_check(text: str | None, field: str) -> None:
    """Not ve kanıt alanlarında kişisel veri reddedilir (KVKK: plugin müşteri iletişim bilgisi tutmaz)."""
    if not text:
        return
    for rx, kind in _PII:
        if rx.search(text):
            raise AdMemoryError(f"{field} alanında {kind} görünüyor: kişisel veri kaydedilmez. Konuşma takma koduyla (M-0001) izlenir; "
                                "müşteri bilgisi kullanıcının kendi mesaj uygulamasında kalır.")


def is_date_only(v: str | None) -> bool:
    return bool(v) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(v).strip()))


def _ts(v: str | None, field: str, *, default_now: bool = False, tz: str | None = None) -> str | None:
    """Zamanı UTC'ye çevirir. Yalnızca tarih → markanın saat diliminde günün başı; saat dilimi yazılmamış zaman (2026-10-20T23:30)
    markanın yerel saati sayılır (kullanıcı saati kendi saatine göre söyler)."""
    if v is None or v == "":
        return now_iso() if default_now else None
    s = str(v).strip()
    try:
        zone = ZoneInfo(tz or "Europe/Istanbul")
    except Exception:
        zone = dt.timezone.utc
    try:
        if is_date_only(s):
            d = dt.datetime.fromisoformat(s).replace(tzinfo=zone)
        else:
            d = dt.datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T", 1))
            if d.tzinfo is None:
                d = d.replace(tzinfo=zone)
    except ValueError:
        raise AdMemoryError(f"{field} zamanı okunamadı: {v!r} (ISO biçimi: 2026-10-20 ya da 2026-10-20T14:30:00+03:00)")
    if d > utcnow() + dt.timedelta(minutes=10):  # saat dilimi doğru çevrildiği için yalnızca küçük saat kayması payı
        raise AdMemoryError(f"{field} gelecekte olamaz: {v!r}")
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _enum(v: Any, allowed: tuple, field: str) -> Any:
    if v is not None and v not in allowed:
        raise AdMemoryError(f"{field}: {' | '.join(allowed)}")
    return v


def _pos_int(v: Any, field: str) -> int | None:
    if v is None:
        return None
    if isinstance(v, bool) or int(v) != v or int(v) < 0:
        raise AdMemoryError(f"{field} sıfır ya da pozitif tam sayı olmalı")
    return int(v)


def _pos_num(v: Any, field: str) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise AdMemoryError(f"{field} sayı olmalı")
    if f < 0:
        raise AdMemoryError(f"{field} negatif olamaz")
    return f


def local_date(iso_utc: str, tzname: str | None) -> str:
    d = parse_iso(iso_utc)
    try:
        return d.astimezone(ZoneInfo(tzname or "Europe/Istanbul")).date().isoformat()
    except Exception:
        return d.date().isoformat()


def currency_code(v: str | None) -> str | None:
    from .s_conn import currency_code as cc
    return cc(v)


class DMMixin:
    # --- konuşma kaydı -------------------------------------------------------------
    def _brand_tz(self, brand_id: int) -> str | None:
        b = self.q1("SELECT timezone FROM brands WHERE id=?", (brand_id,))
        return b["timezone"] if b else None

    def _dm_thread(self, profile_id: int, ref: str) -> dict:
        bid = self._brand_id(profile_id)
        t = self.q1("SELECT * FROM dm_threads WHERE brand_id=? AND ref=?", (bid, ref))
        if not t:
            raise AdMemoryError(f"konuşma yok: {ref}")
        return t

    def _dm_daily_guard(self, brand_id: int, date: str, channel: str, extra_threads: int = 0) -> None:
        d = self.q1("SELECT conversations FROM dm_daily WHERE brand_id=? AND date=? AND channel=?", (brand_id, date, channel))
        if not d:
            return
        n = self.q1("SELECT COUNT(*) AS n FROM dm_threads WHERE brand_id=? AND channel=? AND opened_date=?",
                    (brand_id, channel, date))["n"] + extra_threads
        if n > d["conversations"]:
            raise AdMemoryError(f"{date} {channel} günlük toplamı {d['conversations']} konuşma; tek tek kayıtlar ({n}) toplamı aşamaz. "
                                "Önce dm_daily_set ile günlük toplamı güncelleyin (günlük toplam bütün konuşmalardır).")

    def dm_thread_open(self, profile_id: int, channel: str, opened_at: str | None = None, campaign_id: int | None = None,
                       source: str = "unknown", source_evidence: str | None = None, meta_ad_id: str | None = None,
                       creative_key: str | None = None, segment: str = "unknown", intent: str = "other",
                       quantity: int | None = None, note: str | None = None) -> dict:
        bid = self._brand_id(profile_id)
        _enum(channel, DM_CHANNELS, "channel")
        _enum(source, DM_SOURCES, "source")
        _enum(segment, DM_SEGMENTS, "segment")
        _enum(intent, DM_INTENTS, "intent")
        pii_check(note, "not")
        pii_check(source_evidence, "kaynak kanıtı")
        pii_check(meta_ad_id, "reklam kimliği")
        tz = self._brand_tz(bid)
        opened = _ts(opened_at, "opened_at", default_now=True, tz=tz)
        if campaign_id is not None:
            self._campaign(profile_id, campaign_id)
        if (meta_ad_id or creative_key) and source != "ad":
            raise AdMemoryError("reklam/kreatif bağı yalnızca source='ad' ile kurulur")
        if source == "ad":
            if not (source_evidence and source_evidence.strip()):
                raise AdMemoryError("source='ad' kanıt ister (source_evidence: ör. 'mesajda reklam etiketi görünüyor', 'reklamın mesaj "
                                    "butonundan geldi', 'müşteri reklamı gördüğünü söyledi'); kanıt yoksa source='unknown'")
            if campaign_id is None:
                raise AdMemoryError("reklam kaynaklı konuşma bir kampanyaya bağlanır (campaign_id)")
        if creative_key:
            if not self.q1("SELECT 1 FROM creatives WHERE campaign_id=? AND creative_key=?", (campaign_id, creative_key)):
                raise AdMemoryError(f"creative_key bu kampanyada yok: {creative_key}")
        q = _pos_int(quantity, "quantity")
        opened_day = local_date(opened, tz)
        self._dm_daily_guard(bid, opened_day, channel, extra_threads=1)
        last = self.q1("SELECT ref FROM dm_threads WHERE brand_id=? ORDER BY id DESC LIMIT 1", (bid,))
        n = (int(last["ref"].split("-")[1]) + 1) if last else 1
        ref = f"M-{n:04d}"
        now = now_iso()
        with self.tx():
            tid = self.ex("""INSERT INTO dm_threads(brand_id,campaign_id,ref,channel,source,source_evidence,meta_ad_id,creative_key,segment,
                             intent,status,quantity,opened_at,opened_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?, 'open', ?,?,?,?,?)""",
                          (bid, campaign_id, ref, channel, source, (source_evidence or "").strip() or None, meta_ad_id, creative_key,
                           segment, intent, q, opened, opened_day, now, now)).lastrowid
            self.ex("INSERT INTO dm_events(thread_id,at,kind,note,created_at) VALUES(?,?, 'opened', ?, ?)", (tid, opened, note, now))
        return self.q1("SELECT * FROM dm_threads WHERE id=?", (tid,))

    def dm_thread_event(self, profile_id: int, ref: str, event: str, at: str | None = None, amount: float | None = None,
                        quantity: int | None = None, currency: str | None = None, lost_reason: str | None = None,
                        paid_via: str | None = None, next_follow_up_at: str | None = None, segment: str | None = None,
                        intent: str | None = None, note: str | None = None) -> dict:
        t = self._dm_thread(profile_id, ref)
        if event not in TRANSITIONS and event not in STATELESS_EVENTS:
            raise AdMemoryError(f"olay: {' | '.join(list(TRANSITIONS) + list(STATELESS_EVENTS))}")
        pii_check(note, "not")
        _enum(segment, DM_SEGMENTS, "segment")
        _enum(intent, DM_INTENTS, "intent")
        tz = self._brand_tz(t["brand_id"])
        when = _ts(at, "at", default_now=True, tz=tz)
        if when < t["opened_at"] and is_date_only(at) and local_date(t["opened_at"], tz) == str(at).strip():
            when = t["opened_at"]  # açılış günüyle aynı gün, saatsiz: olay açılıştan sonra sayılır (gece yarısı değil)
        if when < t["opened_at"]:
            raise AdMemoryError("olay zamanı konuşmanın açılışından önce olamaz")
        fu = _ts(next_follow_up_at, "next_follow_up_at", tz=tz) if next_follow_up_at else None
        if fu and fu < when and is_date_only(next_follow_up_at) and local_date(when, tz) == str(next_follow_up_at).strip():
            fu = when  # aynı gün, saatsiz takip: hemen takip listesine girer
        if fu and fu < when:
            raise AdMemoryError("sonraki takip zamanı olaydan önce olamaz")
        cur = currency_code(currency)
        amt = _pos_num(amount, "amount")
        qty = _pos_int(quantity, "quantity")
        sets: dict[str, Any] = {}
        if event in TRANSITIONS:
            allowed, target = TRANSITIONS[event]
            if t["status"] not in allowed:
                raise AdMemoryError(f"{t['status']} durumundaki konuşmada '{event}' olmaz (izinli: {', '.join(sorted(allowed))})")
            sets["status"] = target
            if event == "won":
                _enum(paid_via, PAID_VIA, "paid_via")
                if not paid_via:
                    raise AdMemoryError("satış (won) ödeme yolunu ister (paid_via): mağaza bağlantısıyla ödenen satış mağaza siparişlerinde "
                                        "zaten sayılır, çift sayılmaması için gerekli")
                sets.update(paid_via=paid_via, won_amount=amt, closed_at=when, next_follow_up_at=None)
                if amt is not None and not (cur or t["currency"]):
                    raise AdMemoryError("tutar verildiyse para birimi (currency) gerekli")
            elif event == "lost":
                _enum(lost_reason, LOST_REASONS, "lost_reason")
                if not lost_reason:
                    raise AdMemoryError(f"kayıp nedeni gerekli (lost_reason: {' | '.join(LOST_REASONS)}); bilinmiyorsa 'other' ya da 'no_reply'")
                sets.update(lost_reason=lost_reason, closed_at=when, next_follow_up_at=None)
            elif event == "quoted":
                if amt is not None:
                    sets["quote_amount"] = amt
                    if not (cur or t["currency"]):
                        raise AdMemoryError("teklif tutarı verildiyse para birimi (currency) gerekli")
            elif event == "reopened":
                if t["status"] == "won" and not (note and note.strip()):
                    raise AdMemoryError("satışı geri açmak bir düzeltmedir: nedenini not olarak yazın (ör. 'yanlışlıkla satış girildi')")
                sets.update(closed_at=None, lost_reason=None, paid_via=None, won_amount=None)
        elif event == "responded":
            if t["first_response_at"] is None:
                sets["first_response_at"] = when
        if fu is not None:
            if sets.get("status", t["status"]) in ("won", "lost"):
                raise AdMemoryError("kapanmış konuşmaya takip zamanı verilmez")
            sets["next_follow_up_at"] = fu
        if qty is not None:
            sets["quantity"] = qty
        if cur:
            sets["currency"] = cur
        if segment:
            sets["segment"] = segment
        if intent:
            sets["intent"] = intent
        sets["updated_at"] = now_iso()
        with self.tx():
            self.ex(f"UPDATE dm_threads SET {', '.join(f'{k}=?' for k in sets)} WHERE id=?", (*sets.values(), t["id"]))
            self.ex("INSERT INTO dm_events(thread_id,at,kind,amount,note,created_at) VALUES(?,?,?,?,?,?)",
                    (t["id"], when, event, amt, note, now_iso()))
        return self.q1("SELECT * FROM dm_threads WHERE id=?", (t["id"],))

    # --- günlük toplam ---------------------------------------------------------------
    def dm_daily_set(self, profile_id: int, date: str, channel: str, conversations: int, from_ads: int | None = None,
                     qualified: int | None = None, quoted: int | None = None, won: int | None = None, note: str | None = None) -> dict:
        """Bir günün ve kanalın TOPLAM sayıları (tek tek kaydedilen konuşmalar dahil). Aynı gün/kanal için yeniden yazılır."""
        bid = self._brand_id(profile_id)
        _enum(channel, DM_CHANNELS, "channel")
        pii_check(note, "not")
        from .s_meta import _date
        d = _date(date)
        try:
            zone = ZoneInfo(self._brand_tz(bid) or "Europe/Istanbul")
        except Exception:
            zone = dt.timezone.utc
        if dt.date.fromisoformat(d) > utcnow().astimezone(zone).date():  # markanın bugünü
            raise AdMemoryError("gelecek gün için kayıt olmaz")
        c = _pos_int(conversations, "conversations")
        vals = {k: _pos_int(v, k) for k, v in (("from_ads", from_ads), ("qualified", qualified), ("quoted", quoted), ("won", won))}
        for k, v in vals.items():
            if v is not None and v > c:
                raise AdMemoryError(f"{k} ({v}) toplam konuşmayı ({c}) aşamaz")
        if vals["quoted"] is not None and vals["qualified"] is not None and vals["quoted"] > vals["qualified"]:
            raise AdMemoryError("teklif verilen konuşma, nitelikli (gerçek ilgi gösteren) konuşmadan fazla olamaz")
        n_threads = self.q1("SELECT COUNT(*) AS n FROM dm_threads WHERE brand_id=? AND channel=? AND opened_date=?",
                            (bid, channel, d))["n"]
        if n_threads > c:
            raise AdMemoryError(f"bu gün/kanal için tek tek kaydedilmiş {n_threads} konuşma var; toplam ({c}) bundan az olamaz")
        now = now_iso()
        with self.tx():
            ex = self.q1("SELECT id FROM dm_daily WHERE brand_id=? AND date=? AND channel=?", (bid, d, channel))
            if ex:
                self.ex("""UPDATE dm_daily SET conversations=?, from_ads=?, qualified=?, quoted=?, won=?, note=?, updated_at=? WHERE id=?""",
                        (c, vals["from_ads"], vals["qualified"], vals["quoted"], vals["won"], note, now, ex["id"]))
            else:
                self.ex("""INSERT INTO dm_daily(brand_id,date,channel,conversations,from_ads,qualified,quoted,won,note,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (bid, d, channel, c, vals["from_ads"], vals["qualified"], vals["quoted"],
                                                              vals["won"], note, now, now))
        return self.q1("SELECT * FROM dm_daily WHERE brand_id=? AND date=? AND channel=?", (bid, d, channel))

    # --- özet ve takip --------------------------------------------------------------------
    def dm_summary(self, profile_id: int, date_from: str | None = None, date_to: str | None = None,
                   campaign_id: int | None = None) -> dict:
        """Mesajla satış hunisi. Gün/kanal başına sayılar: günlük toplam varsa o, yoksa tek tek kayıtlar (ikisinden büyüğü).
        campaign_id verilirse kampanyaya kanıtla bağlı konuşmaların ayrıntısı ayrıca verilir; toplamlar markanın tüm DM'leridir."""
        bid = self._brand_id(profile_id)
        from .s_meta import _date
        lo = _date(date_from) if date_from else "0000-01-01"
        hi = _date(date_to) if date_to else "9999-12-31"
        if campaign_id is not None:
            self._campaign(profile_id, campaign_id)
        threads = self.dm_threads_rows(bid, lo, hi)
        daily = self.qa("SELECT date, channel, conversations, from_ads, qualified, quoted, won FROM dm_daily WHERE brand_id=? AND date BETWEEN ? AND ?",
                        (bid, lo, hi))
        return {"profile_id": int(profile_id), "period": [lo, hi], **dm_funnel(threads, daily, campaign_id)}

    def dm_threads_rows(self, brand_id: int, lo: str, hi: str) -> list[dict]:
        """Kişisel veri ve not içermeyen konuşma satırları; ulaşılan aşamalar olaylardan (kaybedilen konuşma da nitelikli olmuş olabilir)."""
        return self.qa("""SELECT t.ref, t.campaign_id, t.channel, t.source, t.meta_ad_id, t.creative_key, t.segment, t.intent, t.status,
                                  t.lost_reason, t.quantity, t.quote_amount, t.won_amount, t.currency, t.paid_via, t.opened_at, t.opened_date,
                                  t.first_response_at, t.closed_at, t.next_follow_up_at,
                                  EXISTS(SELECT 1 FROM dm_events e WHERE e.thread_id=t.id AND e.kind IN ('qualified','quoted')) AS r_qualified,
                                  EXISTS(SELECT 1 FROM dm_events e WHERE e.thread_id=t.id AND e.kind IN ('quoted')) AS r_quoted
                           FROM dm_threads t WHERE t.brand_id=? AND t.opened_date BETWEEN ? AND ? ORDER BY t.opened_at""", (brand_id, lo, hi))

    def dm_follow_ups(self, profile_id: int, now: str | None = None) -> dict:
        """Takip bekleyen açık konuşmalar: zamanı gelmiş takip ya da son olaydan bu yana STALE_AFTER_DAYS gün sessizlik (yerel)."""
        bid = self._brand_id(profile_id)
        ref_now = parse_iso(now) if now else utcnow()
        out = []
        for t in self.qa("SELECT * FROM dm_threads WHERE brand_id=? AND status IN ('open','qualified','quoted','stale') ORDER BY opened_at",
                         (bid,)):
            last = self.q1("SELECT MAX(at) AS at FROM dm_events WHERE thread_id=?", (t["id"],))["at"] or t["opened_at"]
            due = bool(t["next_follow_up_at"]) and parse_iso(t["next_follow_up_at"]) <= ref_now
            # sessizlik yalnızca açık konuşmada; 'stale' işaretlenmiş konuşma yalnızca verilen takip zamanı gelince listeye girer
            silent = t["status"] != "stale" and (ref_now - parse_iso(last)).days >= STALE_AFTER_DAYS
            if due or silent:
                out.append({"ref": t["ref"], "channel": t["channel"], "status": t["status"], "segment": t["segment"],
                            "intent": t["intent"], "quote_amount": t["quote_amount"], "currency": t["currency"],
                            "last_event_at": last, "reason": "takip zamanı geldi" if due else f"{STALE_AFTER_DAYS}+ gündür ses yok"})
        return {"profile_id": int(profile_id), "due": out, "rule": f"yerel: {STALE_AFTER_DAYS} gün sessizlik ya da verilen takip zamanı"}


def dm_funnel(threads: list[dict], daily: list[dict], campaign_id: int | None = None) -> dict:
    """Saf hesap (koçluk kopyasında da aynı kod kullanılır)."""
    by_key: dict[tuple, dict] = {}
    for t in threads:
        k = (t.get("opened_date") or t["opened_at"][:10], t["channel"])
        b = by_key.setdefault(k, {"conversations": 0, "from_ads": 0, "qualified": 0, "quoted": 0, "won": 0})
        b["conversations"] += 1
        b["from_ads"] += 1 if t["source"] == "ad" else 0
        b["qualified"] += 1 if (t.get("r_qualified") or t["status"] in ("qualified", "quoted", "won")) else 0
        b["quoted"] += 1 if (t.get("r_quoted") or t["status"] in ("quoted", "won")) else 0
        b["won"] += 1 if t["status"] == "won" else 0
    for d in daily:
        k = (d["date"], d["channel"])
        b = by_key.setdefault(k, {"conversations": 0, "from_ads": 0, "qualified": 0, "quoted": 0, "won": 0})
        for f in ("conversations", "from_ads", "qualified", "quoted", "won"):
            if d.get(f) is not None:
                b[f] = max(b[f], int(d[f]))
    tot = {f: sum(b[f] for b in by_key.values()) for f in ("conversations", "from_ads", "qualified", "quoted", "won")}
    by_channel: dict[str, dict] = {}
    for (day, ch), b in by_key.items():
        c = by_channel.setdefault(ch, {f: 0 for f in tot})
        for f in tot:
            c[f] += b[f]
    resp = sorted((parse_iso(t["first_response_at"]) - parse_iso(t["opened_at"])).total_seconds() / 60
                  for t in threads if t.get("first_response_at"))
    lost = {}
    for t in threads:
        if t["status"] == "lost":
            lost[t["lost_reason"] or "other"] = lost.get(t["lost_reason"] or "other", 0) + 1
    won_threads = [t for t in threads if t["status"] == "won"]
    off_store = [t for t in won_threads if t.get("paid_via") and t["paid_via"] != "store_link"]
    rev_off = {}
    for t in off_store:
        if t.get("won_amount") is not None:
            rev_off[t.get("currency") or "?"] = rev_off.get(t.get("currency") or "?", 0.0) + float(t["won_amount"])
    pipeline = {}
    for t in threads:
        if t["status"] in OPEN_STATES and t.get("quote_amount") is not None:
            pipeline[t.get("currency") or "?"] = pipeline.get(t.get("currency") or "?", 0.0) + float(t["quote_amount"])
    out = {"totals": tot, "by_channel": by_channel,
           "rates": {"won_per_conversation": round(tot["won"] / tot["conversations"], 4) if tot["conversations"] else None,
                     "won_per_qualified": round(tot["won"] / tot["qualified"], 4) if tot["qualified"] else None},
           "logged_threads": len(threads),
           "median_first_response_min": round(resp[len(resp) // 2], 1) if resp else None,
           "lost_reasons": dict(sorted(lost.items(), key=lambda kv: -kv[1])),
           "segments": {s: sum(1 for t in threads if t["segment"] == s) for s in DM_SEGMENTS if any(t["segment"] == s for t in threads)},
           "won_off_store": {"count": len(off_store), "revenue": {k: round(v, 2) for k, v in rev_off.items()}},
           "won_via_store_link": sum(1 for t in won_threads if t.get("paid_via") == "store_link"),
           "open_quote_pipeline": {k: round(v, 2) for k, v in pipeline.items()},
           "note": "Günlük toplam varsa o gün/kanal için o sayılır (tek tek kayıtlar içindedir). Mağaza bağlantısıyla ödenen DM satışı mağaza "
                   "siparişlerinde sayılır; satış toplamına ayrıca eklenmez. Kişisel veri yoktur."}
    if campaign_id is not None:
        ct = [t for t in threads if t.get("campaign_id") == campaign_id]
        out["campaign_attributed"] = {"threads": len(ct), "won": sum(1 for t in ct if t["status"] == "won"),
                                      "from_ad_evidence": sum(1 for t in ct if t["source"] == "ad"),
                                      "note": "yalnızca kanıtla kampanyaya bağlanan konuşmalar; günlük toplamlar kampanyaya bölünmez"}
    return out
