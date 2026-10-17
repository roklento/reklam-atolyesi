"""Sabit ana menü (spec 17.1; 1.4.1). Yalnızca standart kütüphane + admem.stages (saf sabitler).

Menü maddeleri hooks/menu.json'dadır ve değişmez; burada yalnızca üst satır, 1. maddenin hedefi ve maddelere eklenen kısa not
veritabanından (salt okuma) üretilir. Aynı kod hem navigator hook'unda hem ad-memory'nin menu_render aracında çalışır: iki yol aynı
metni verir. Model menüyü kendisi yazmaz, buradan gelen metni aynen gösterir.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import plugin_mode as pm

sys.path.insert(0, str(pm.PLUGIN_ROOT / "servers" / "ad_memory"))
from admem import stages as ST  # noqa: E402

MENU_FILE = pm.HOOKS_DIR / "menu.json"
NUMBER_RE = re.compile(r"\s*(\d{1,2})\s*[.)]?\s*")


def load() -> dict:
    return json.loads(MENU_FILE.read_text(encoding="utf-8"))


def is_home(prompt: str, menu: dict | None = None) -> bool:
    words = (menu or load())["home_words"]
    return pm.fold(prompt) in {pm.fold(w) for w in words}


def item(n: int, menu: dict | None = None) -> dict | None:
    return next((i for i in (menu or load())["items"] if i["no"] == n), None)


def selected_number(prompt: str) -> int | None:
    m = NUMBER_RE.fullmatch(prompt or "")
    return int(m.group(1)) if m else None


def _setting(con, key: str):
    r = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r[0] if r and r[0] else None


def pick_profile(con, sess: dict):
    """Oturumun profili: bağlı olan, yoksa yeni oturum varsayılanı, yoksa tek profil. (satır, durum) döner;
    durum: 'bound' | 'default' | 'only' | 'none' (hiç profil yok) | 'choose' (birden çok, seçim gerekli)."""
    q = "SELECT id, name, status, brand_id FROM profiles WHERE id=? AND status!='archived'"
    if sess.get("profile_id"):
        p = con.execute(q, (sess["profile_id"],)).fetchone()
        if p:
            return p, "bound"
    a = _setting(con, "active_profile_id")
    if a:
        p = con.execute(q, (int(a),)).fetchone()
        if p:
            return p, "default"
    rows = con.execute("SELECT id, name, status, brand_id FROM profiles WHERE status!='archived' AND synthetic=0 ORDER BY id").fetchall()
    if not rows:
        return None, "none"
    if len(rows) == 1:
        return rows[0], "only"
    return None, "choose"


def _campaign(con, sess: dict, brand_id):
    if brand_id is None:
        return None
    if sess.get("campaign_id"):
        c = con.execute("SELECT * FROM campaigns WHERE id=? AND brand_id=? AND status='active'", (sess["campaign_id"], brand_id)).fetchone()
        if c:
            return c
    return con.execute("SELECT * FROM campaigns WHERE brand_id=? AND status='active' ORDER BY id DESC LIMIT 1", (brand_id,)).fetchone()


def _stage(code: str) -> str:
    return ST.STAGE_NAMES.get(code, code)


def _onboarding_next(con, p) -> str | None:
    """Tanışması bitmemiş profilde sıradaki tanışma adımı."""
    done = {r["stage"]: r["status"] for r in con.execute(
        "SELECT stage, status FROM stage_runs WHERE profile_id=? AND campaign_id IS NULL AND stale=0 ORDER BY id", (p["id"],)).fetchall()}
    for code in ST.ONBOARDING_STAGES:
        st = done.get(code)
        if st == "awaiting_gate":
            return f"onay bekliyor: {_stage(code).lower()}"
        if st not in ("done", "skipped"):
            return _stage(code).lower()
    return None


def continue_target(con, p, camp) -> str:
    if camp is not None:
        gate = con.execute("SELECT stage FROM stage_runs WHERE campaign_id=? AND status='awaiting_gate' AND stale=0 ORDER BY id LIMIT 1",
                           (camp["id"],)).fetchone()
        if gate:
            return f"onay bekliyor: {_stage(gate['stage'])} ({camp['name']})"
        return f"{camp['name']}: {_stage(camp['stage'])}"
    if p["status"] == "onboarding":
        return "tanışma: " + (_onboarding_next(con, p) or "marka tanışması")
    gate = con.execute("""SELECT stage FROM stage_runs WHERE profile_id=? AND campaign_id IS NULL AND status='awaiting_gate' AND stale=0
                          ORDER BY id LIMIT 1""", (p["id"],)).fetchone()
    if gate:
        return f"onay bekliyor: {_stage(gate['stage']).lower()}"
    if p["brand_id"] is not None:
        prod = con.execute("SELECT name FROM products WHERE brand_id=? AND onboarding_status='done' ORDER BY id DESC LIMIT 1",
                           (p["brand_id"],)).fetchone()
        if prod:
            return f"yeni kampanya brief'i: {prod['name']}"
        prod = con.execute("SELECT name FROM products WHERE brand_id=? ORDER BY id DESC LIMIT 1", (p["brand_id"],)).fetchone()
        if prod:
            return f"ürün tanışması: {prod['name']}"
    return "ilk ürünü tanıt"


def render(data_dir: Path, sess: dict) -> dict:
    """Menüyü üretir. kind: 'menu' | 'no_db' | 'no_profile' | 'choose_profile'. 'menu' dışında text yoktur."""
    menu = load()
    con = pm.ro_db(data_dir)
    if con is None:
        return {"kind": "no_db"}
    try:
        p, how = pick_profile(con, sess)
        if p is None:
            return {"kind": "no_profile" if how == "none" else "choose_profile"}
        camp = _campaign(con, sess, p["brand_id"])
        head = [f"**{p['name']}**"]
        warn: list[str] = []
        if camp is not None:
            head.append(f"aktif kampanya: {camp['name']} · Tur {camp['cycle']} · {_stage(camp['stage'])}")
            n_gate = con.execute("SELECT COUNT(*) FROM stage_runs WHERE campaign_id=? AND status='awaiting_gate' AND stale=0",
                                 (camp["id"],)).fetchone()[0]
            head.append(f"{n_gate} onay bekliyor" if n_gate else "bekleyen onay yok")
            n_ai = con.execute("SELECT COUNT(*) FROM action_items WHERE campaign_id=? AND status='approved'", (camp["id"],)).fetchone()[0]
            if n_ai:
                warn.append(f"uygulama listesinde {n_ai} adım bekliyor")
            n_gen = con.execute("SELECT COUNT(*) FROM generations WHERE campaign_id=? AND status IN ('running','unknown')",
                                (camp["id"],)).fetchone()[0]
            if n_gen:
                warn.append(f"{n_gen} ücretli üretimin sonucu belirsiz")
        else:
            head.append("aktif kampanya yok")
            if p["status"] == "onboarding":
                head.append("tanışma sürüyor")
        if not _setting(con, "setup_static_ok_at"):
            warn.append("⚠ kurulum doğrulaması tamamlanmamış: kurulum dosyasını (kur.cmd) yeniden çalıştırın")
        launched = p["brand_id"] is not None and con.execute(
            """SELECT 1 FROM cycles cy JOIN campaigns c ON c.id=cy.campaign_id WHERE c.brand_id=? AND cy.launched_at IS NOT NULL LIMIT 1""",
            (p["brand_id"],)).fetchone() is not None
        target = continue_target(con, p, camp)
    finally:
        con.close()
    labels = []
    for it in menu["items"]:
        lab = it["label"]
        if it["key"] == "devam":
            lab = f"{lab} → {target}"
        elif it["key"] == "performans" and not launched:
            lab = f"{lab} (henüz yayında reklam yok)"
        labels.append(lab)
    lines = [" · ".join(head)]
    if warn:
        lines.append(" · ".join(warn))
    lines.append("")
    lines += [f"{i + 1}. {lab}" for i, lab in enumerate(labels)]
    lines += ["", menu["footer"]]
    return {"kind": "menu", "text": "\n".join(lines), "labels": labels, "profile_id": p["id"], "profile_how": how,
            "campaign_id": camp["id"] if camp is not None else None}


def mark_shown(sess: dict, r: dict, now: str) -> dict:
    """Menü gösterildi: son ekran menüdür; sayı bu menüye göre çözülür. Profil seçilmemişse kesin tek seçenek bağlanır."""
    sess["screen"] = "menu"
    sess["last_menu"] = r["labels"]
    sess["menu_at"] = now
    if not sess.get("profile_id") and r.get("profile_id"):
        sess["profile_id"] = r["profile_id"]
    return sess
