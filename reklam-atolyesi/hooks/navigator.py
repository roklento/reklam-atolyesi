"""UserPromptSubmit / UserPromptExpansion hook'u: navigator ve plugin modu (spec 13.6, 17.1).

- Mesajın tamamı plugin adıysa ya da mesaj bir /reklam-atolyesi: komutuyla başlıyorsa oturumu plugin moduna alır.
- Plugin modundaki oturumda her mesaja kısa durum ekler (bağlı profil, kampanya/aşama, bekleyen kapı, son menü).
- Mesaj yalnızca bir sayıysa "son menünün N. maddesi" diye çözer. "çık"/"menüden çık" modu kapatır.
- Plugin modu dışındaki oturumlarda hiçbir şey yapmaz. Bu hook hiçbir zaman mesajı engellemez.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
import traceback

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
        lines.append(f"profil sayısı: {n} · canlı doğrulama: {'var (' + sv[0] + ')' if sv and sv[0] else 'YOK — önce kurulum-kontrol'}")
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
    menu = sess.get("last_menu") or []
    if menu:
        lines.append("son menü: " + " | ".join(f"{i + 1}. {m}" for i, m in enumerate(menu[:8])))
    return lines


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
    if trig:
        out.append("Kullanıcı plugin adını yazdı: navigator skill'ini (reklam-atolyesi:navigator) çalıştır — önce canlı doğrulama durumu, "
                   "profil 0 ise tanışma, açık devam notu varsa 'kaldığımız yer', sonra numaralı menü (17.1–17.2). Menüyü session_menu_set ile kaydet.")
    if cmd:
        out.append(f"Komut: /reklam-atolyesi:{cmd} — oturum plugin modunda; korumalar (maliyet, Meta izin listesi) geçerli.")
    m = re.fullmatch(r"\s*(\d{1,2})\s*", prompt or "")
    if m and not cmd and not trig:
        n = int(m.group(1))
        menu = sess.get("last_menu") or []
        if 1 <= n <= len(menu):
            out.append(f"Kullanıcı son menünün {n}. maddesini seçti: «{menu[n - 1]}».")
        else:
            out.append(f"Kullanıcı '{n}' yazdı ama son menüde {len(menu)} madde var; ne istediğini sor.")
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
