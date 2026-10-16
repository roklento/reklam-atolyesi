"""SessionStart hook'u (spec 13.6, 8.2): yeni oturumda hiçbir şey eklemez. Devam ettirilen ya da bağlamı sıkıştırılmış
(resume, compact) bir plugin modu oturumunda profil kartının kritik kısmını ve açık devam notunu ekler."""
from __future__ import annotations

import json
import sys
import traceback

import plugin_mode as pm


def main() -> int:
    data = pm.read_input()
    if data.get("source") not in ("resume", "compact"):
        return 0
    sid = data.get("session_id")
    try:
        data_dir = pm.data_dir_from_argv()
        sess = pm.load_session(data_dir, sid)
    except pm.ConfigError:
        return 0
    if not sess or not sess.get("plugin_mode"):
        return 0
    lines = [f"[reklam-atolyesi] Oturum {data.get('source')} sonrası plugin modunda sürüyor · session_id: {sid} · "
             f"plugin: {pm.PLUGIN_ROOT.as_posix()} · data_dir: {data_dir.as_posix()}"]
    con = pm.ro_db(data_dir)
    if con is not None:
        try:
            pid = sess.get("profile_id")
            if pid:
                p = con.execute("SELECT name, status FROM profiles WHERE id=?", (pid,)).fetchone()
                if p:
                    lines.append(f"Profil: #{pid} {p['name']} ({p['status']}) — tam kart için memory_card({pid}).")
                for r in con.execute("""SELECT stage, scope_key, state_json, updated_at FROM resume_state WHERE profile_id=? AND closed_at IS NULL
                                        ORDER BY updated_at DESC LIMIT 3""", (pid,)).fetchall():
                    st = json.loads(r["state_json"] or "{}")
                    lines.append(f"Açık devam notu {r['stage']} ({r['scope_key']}, {r['updated_at']}): sıradaki → {st.get('next_step')}; "
                                 f"kararlar → {st.get('decisions')}")
                cid = sess.get("campaign_id")
                if cid:
                    c = con.execute("SELECT name, stage, cycle FROM campaigns WHERE id=?", (cid,)).fetchone()
                    if c:
                        lines.append(f"Kampanya #{cid} {c['name']} · tur {c['cycle']} · aşama {c['stage']}")
            lines.append("Kalıcı kaydedilmemiş bir yanıtın saklandığı varsayılmaz; stage_resume ile doğrula ve gerekirse tekrar teyit et (8.1).")
        finally:
            con.close()
    pm.context("SessionStart", "\n".join(lines))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(0)
