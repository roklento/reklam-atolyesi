"""UserPromptSubmit / UserPromptExpansion hook'u: navigator ve plugin modu (spec 13.6, 17.1).

- Mesajın tamamı plugin adıysa ya da mesaj bir /reklam-atolyesi: komutuyla başlıyorsa oturumu plugin moduna alır.
- Plugin adı ya da (plugin modunda) "menü" yazılınca sabit ana menüyü hooks/menu.py ile üretir; model metni aynen gösterir.
- Mesaj yalnızca bir sayıysa ve son ekran ana menüyse sabit menünün N. maddesi diye çözer; aşama içindeyken sayıya dokunmaz.
- Plugin modundaki oturumda her mesaja kısa durum ekler (bağlı profil, kampanya/aşama, bekleyen kapı). "çık"/"menüden çık" modu kapatır.
- Plugin modu dışındaki oturumlarda hiçbir şey yapmaz. Bu hook hiçbir zaman mesajı engellemez.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
import traceback

import menu as mn
import plugin_mode as pm

DECISION_HINTS = ("onay", "evet", "tamam", "seç", "sec", "olsun", "istemiyorum", "hayır", "hayir", "reddet", "kabul", "birleştir",
                  "birlestir", "değiştir", "degistir", "ertele", "kaydet", "bunu yapalım", "devam")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def status_lines(data_dir, sess: dict) -> list[str]:
    lines: list[str] = []
    con = pm.ro_db(data_dir)
    if con is None:
        return ["Veritabanı henüz yok (doctor/kurulum kontrolü gerekli)."]
    try:
        n = con.execute("SELECT COUNT(*) FROM profiles WHERE status!='archived' AND synthetic=0").fetchone()[0]
        sv = con.execute("SELECT value FROM settings WHERE key='setup_verified_at'").fetchone()
        st = con.execute("SELECT value FROM settings WHERE key='setup_static_ok_at'").fetchone()
        lines.append(f"profil sayısı: {n} · statik kurulum: {'tamam' if st and st[0] else 'EKSİK — kur.cmd yeniden çalıştırılmalı'} · "
                     f"canlı doğrulama: {'var (' + sv[0] + ')' if sv and sv[0] else 'YOK — önce kurulum-kontrol'}")
        pid = sess.get("profile_id")
        if pid:
            p = con.execute("SELECT id, name, status FROM profiles WHERE id=?", (pid,)).fetchone()
            if p:
                lines.append(f"oturumun profili: #{p['id']} {p['name']} ({p['status']})")
        else:
            a = con.execute("SELECT value FROM settings WHERE key='active_profile_id'").fetchone()
            if a and a[0]:
                p = con.execute("SELECT id, name, status FROM profiles WHERE id=?", (int(a[0]),)).fetchone()
                if p:
                    lines.append(f"oturuma profil bağlı değil; yeni oturum varsayılanı: #{p['id']} {p['name']} ({p['status']}) — iş başlarken session_bind")
        cid = sess.get("campaign_id")
        if cid:
            c = con.execute("SELECT id, name, stage, cycle FROM campaigns WHERE id=?", (cid,)).fetchone()
            if c:
                lines.append(f"kampanya: #{c['id']} {c['name']} · tur {c['cycle']} · aşama {c['stage']}")
                for g in con.execute("SELECT id, stage, output_version, cycle_id FROM stage_runs WHERE campaign_id=? AND status='awaiting_gate' AND stale=0",
                                     (cid,)).fetchall():
                    lines.append(f"BEKLEYEN KAPI: {g['stage']} (stage_run {g['id']}, sürüm {g['output_version']}, tur {g['cycle_id']})")
        if pid:
            k = con.execute("SELECT COUNT(*) FROM resume_state WHERE profile_id=? AND closed_at IS NULL", (pid,)).fetchone()[0]
            if k:
                lines.append(f"açık devam notu: {k} (stage_resume ile doğrula)")
    finally:
        con.close()
    if sess.get("screen") == "menu":
        lines.append("son ekran: ana menü (tek sayı sabit menü maddesidir)")
    return lines


MENU_RULE = ("Menüyü SEN yazma, madde ekleme/çıkarma/yeniden adlandırma: aşağıdaki MENÜ bloğunu (işaretler hariç) olduğu gibi göster. "
             "Bakım ya da 'kaldığımız yer' notu varsa menünün üstünde en fazla 2 kısa satır olabilir.")


def menu_context(data_dir, sess: dict, lead: str) -> list[str]:
    r = mn.render(data_dir, sess)
    if r["kind"] == "no_db":
        return ["Veritabanı yok: menü gösterilemez; kurulum eksik (reklam-atolyesi:kurulum-kontrol)."]
    if r["kind"] == "no_profile":
        return ["Henüz profil yok: menü gösterme; kısa karşılama ile doğrudan marka tanışması (reklam-atolyesi:brand-onboarding)."]
    if r["kind"] == "choose_profile":
        return ["Oturuma profil bağlı değil ve birden çok profil var: önce profile_list ile seçtir (ad, durum, son iş), "
                "session_bind ile bağla, sonra menu_render(session_id) sonucunu aynen göster."]
    mn.mark_shown(sess, r, _now())
    return [lead, MENU_RULE, "<<<MENÜ", r["text"], "MENÜ>>>"]


def main() -> int:
    try:
        data = pm.read_input()
    except Exception:
        return 0
    event = data.get("hook_event_name") or "UserPromptSubmit"
    sid = data.get("session_id")
    try:
        data_dir = pm.data_dir_from_argv()
    except pm.ConfigError as e:
        prompt = data.get("prompt") or ""
        if pm.is_trigger(prompt) or pm.is_command(prompt) or (data.get("command_name") or "").startswith("reklam-atolyesi:"):
            pm.context(event, f"[reklam-atolyesi] Yapılandırma hatası: {e}. {pm.setup_hint()}")
        return 0
    if not pm.valid_sid(sid):
        return 0
    prompt = data.get("prompt") or ""
    cmd = None
    if event == "UserPromptExpansion":
        name = data.get("command_name") or ""
        if name.startswith("reklam-atolyesi:"):
            cmd = name.split(":", 1)[1]
    else:
        cmd = pm.is_command(prompt)
    trig = pm.is_trigger(prompt) if event != "UserPromptExpansion" else False
    try:
        sess = pm.load_session(data_dir, sid) or {}
    except pm.ConfigError:
        sess = {}
    was_on = bool(sess.get("plugin_mode"))
    if not (was_on or trig or cmd):
        return 0  # kapsam kuralı: plugin modu dışında hiçbir şey yapma
    pid = data.get("prompt_id")
    if event == "UserPromptExpansion" and pid and sess.get("last_prompt_id") == pid:
        return 0  # aynı istem UserPromptSubmit'te işlendi
    out: list[str] = []
    if was_on and not (trig or cmd) and pm.is_exit(prompt):
        sess["plugin_mode"] = False
        sess["exited_at"] = _now()
        pm.save_session(data_dir, sid, sess)
        pm.context(event, "[reklam-atolyesi] Plugin modu kapatıldı (yalnızca bu oturum). Kullanıcıya kısaca söyle; navigator'ü tekrar açmak için 'reklam-atolyesi' yazılabilir.")
        return 0
    if not was_on:
        sess.update({"plugin_mode": True, "entered_at": _now(), "entered_by": "command" if cmd else "name"})
    sess["last_prompt_id"] = pid
    sess["last_prompt_at"] = _now()
    low = pm.fold(prompt)
    if any(pm.fold(h) in low for h in DECISION_HINTS) or re.fullmatch(r"\s*\d{1,2}\s*", prompt or ""):
        turns = sess.get("decision_turns") or []
        turns.append(_now())
        sess["decision_turns"] = turns[-20:]
    head = f"[reklam-atolyesi] plugin modu: açık · session_id: {sid} · plugin: {pm.PLUGIN_ROOT.as_posix()} · data_dir: {data_dir.as_posix()}"
    out.append(head)
    was_menu = sess.get("screen") == "menu"
    sess["screen"] = "work"  # menü gösterilirse aşağıda yeniden 'menu' olur
    try:
        if trig:
            out += menu_context(data_dir, sess,
                                "Kullanıcı plugin adını yazdı: navigator skill'ini (reklam-atolyesi:navigator) çalıştır — açılış sırası (canlı doğrulama, "
                                "profil, açık devam notu varsa 'kaldığımız yer', açılış bakımı), sonra ana menü. customer_update_without_tests true ise toplu doğrulamayı tekrarlama; navigator istisnasını uygula.")
        elif cmd:
            out.append(f"Komut: /reklam-atolyesi:{cmd} — oturum plugin modunda; korumalar (maliyet, Meta izin listesi) geçerli.")
        elif mn.is_home(prompt):
            out += menu_context(data_dir, sess,
                                "Kullanıcı ana menüye döndü (home). Yarım kalan bir aşama ya da soru varsa önce checkpoint_save ile devam notunu kaydet "
                                "(tek çağrı, kullanıcıya sorma), sonra ana menüyü göster.")
        else:
            n = mn.selected_number(prompt)
            if n is not None and was_menu:
                it = mn.item(n)
                if it:
                    labels = sess.get("last_menu") or []
                    lab = labels[n - 1] if n <= len(labels) else it["label"]
                    out.append(f"Kullanıcı ana menünün {n}. maddesini seçti: «{lab}». Yapılacak: {it['action']}")
                else:
                    out.append(f"Kullanıcı '{n}' yazdı ama ana menüde {len(mn.load()['items'])} madde var; ne istediğini sor.")
    except Exception as e:  # menü üretilemese bile mod çalışır
        out.append(f"menü üretilemedi ({type(e).__name__}: {e}); menu_render(session_id) aracını dene, o da olmazsa kullanıcıya söyle.")
    try:
        out.extend(status_lines(data_dir, sess))
    except Exception as e:  # durum satırı okunamasa bile mod çalışır
        out.append(f"durum okunamadı: {e}")
    pm.save_session(data_dir, sid, sess)
    pm.context(event, "\n".join(out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(0)  # navigator hiçbir zaman mesajı engellemez
