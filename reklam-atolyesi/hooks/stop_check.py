"""Stop — yalnızca plugin modunda (spec 13.6, 8.3):
- aşama sürerken üretilmiş ama ad-memory'ye kaydedilmemiş çıktı varsa uyarı;
- son devam notundan bu yana kullanıcı kararı içeren 3 tur geçmişse devam notu hatırlatması.
Bu hatırlatma dayanıklılık mekanizması değildir. Aynı durum için bir kez hatırlatır (stop_hook_active ise susar).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import traceback
from pathlib import Path

import plugin_mode as pm


def _ts(s: str | None) -> float:
    if not s:
        return 0.0
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def main() -> int:
    data = pm.read_input()
    if data.get("stop_hook_active"):
        return 0
    sid = data.get("session_id")
    try:
        data_dir = pm.data_dir_from_argv()
        sess = pm.load_session(data_dir, sid)
    except pm.ConfigError:
        return 0
    if not sess or not sess.get("plugin_mode") or not sess.get("profile_id"):
        return 0
    con = pm.ro_db(data_dir)
    if con is None:
        return 0
    msgs: list[str] = []
    try:
        pid, cid = sess.get("profile_id"), sess.get("campaign_id")
        run = None
        if cid:
            run = con.execute("""SELECT sr.*, c.slug, p.slug AS pslug FROM stage_runs sr JOIN campaigns c ON c.id=sr.campaign_id
                                 JOIN brands b ON b.id=c.brand_id JOIN profiles p ON p.brand_id=b.id
                                 WHERE sr.campaign_id=? AND sr.status='running' AND sr.stale=0 ORDER BY sr.id DESC LIMIT 1""", (cid,)).fetchone()
        if run:
            cdir = data_dir / "profiles" / run["pslug"] / "campaigns" / run["slug"]
            since = _ts(run["started_at"])
            known = {r[0] for r in con.execute("SELECT path FROM assets WHERE profile_id=?", (pid,)).fetchall()}
            known |= {r[0] for r in con.execute("SELECT path FROM edit_plans WHERE campaign_id=?", (cid,)).fetchall()}
            known |= {r[0] for r in con.execute("SELECT file_path FROM creatives WHERE campaign_id=?", (cid,)).fetchall()}
            fresh = []
            for sub in ("out", "edit_plans", "analysis", "reports", "competitive"):
                d = cdir / sub
                if d.exists():
                    for f in d.rglob("*"):
                        if f.is_file() and f.stat().st_mtime > since and str(f) not in known and not f.name.startswith("."):
                            fresh.append(f.name)
            if fresh and sess.get("reminded_unsaved") != f"{run['id']}:{len(fresh)}":
                msgs.append(f"{run['stage']} sürüyor ve kaydedilmemiş görünen {len(fresh)} çıktı var (ör. {', '.join(fresh[:3])}). "
                            "Aşama çıktıları ad-memory'ye (asset_register / creative_register / stage_complete) işlenmeden tamamlandı sayılmaz (4.2).")
                sess["reminded_unsaved"] = f"{run['id']}:{len(fresh)}"
        last_cp = con.execute("SELECT MAX(updated_at) FROM resume_state WHERE profile_id=? AND closed_at IS NULL", (pid,)).fetchone()[0]
        turns = [t for t in (sess.get("decision_turns") or []) if _ts(t) > _ts(last_cp)]
        if (run or last_cp) and len(turns) >= 3 and sess.get("reminded_checkpoint") != turns[-1]:
            msgs.append(f"Son devam notundan bu yana kullanıcı kararı içeren {len(turns)} tur geçti: devam notunu güncelle (checkpoint_save; "
                        "karar mutasyonlarında checkpoint yükünü aynı çağrıda ver) (8.3).")
            sess["reminded_checkpoint"] = turns[-1]
    finally:
        con.close()
    if msgs:
        pm.save_session(data_dir, sid, sess)
        pm.emit({"decision": "block", "reason": "[reklam-atolyesi] " + " ".join(msgs)})
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(0)
