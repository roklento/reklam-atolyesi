"""PreToolUse — Meta Ads araçları (`mcp__.*__ads_.*`) için İZİN LİSTESİ koruması (spec 9.3, 13.6).

- Plugin'in kendi meta-ads sunucusunda HER ZAMAN ve HATA DURUMUNDA DA REDDEDEREK çalışır.
- Başka Meta bağlantılarında yalnızca plugin modunda.
- Plugin modunda ads_library_search için görüntü başına sorgu bütçesi oturum dosyasındaki sayaçla uygulanır.
Claude Code'da yalnızca açık 'deny' (ya da çıkış kodu 2) engeller; bu yüzden bütün gövde tek try içinde ve
beklenmeyen istisnada kapsamdaki çağrı için 'deny' döner. Ağ çağrısı yapılmaz.
"""
from __future__ import annotations

import datetime as dt
import json
import sys

import plugin_mode as pm


def load_allowlist() -> dict:
    data = json.loads((pm.HOOKS_DIR / "meta_allowlist.json").read_text(encoding="utf-8"))
    allow = data.get("allow")
    if not isinstance(allow, list) or not allow or any("*" in a for a in allow):
        raise pm.ConfigError("izin listesi geçersiz (joker kullanılmaz)")
    return data


def decide(data: dict, argv: list[str] | None = None) -> tuple[str, str | None]:
    """('allow'|'deny'|'pass', gerekçe). 'pass' = bu hook karışmaz (çıktı yok)."""
    tool = data.get("tool_name") or ""
    own = tool.startswith(pm.OWN_META_PREFIX) or data.get("mcp_server") == "plugin:reklam-atolyesi:meta-ads"
    bare = pm.bare_tool(tool)
    try:
        data_dir = pm.data_dir_from_argv(argv)
    except pm.ConfigError as e:
        return ("deny", f"Meta koruması yapılandırılamadı ({e}); plugin'in Meta sunucusu kapalı tutulur. {pm.setup_hint()}") if own else ("pass", None)
    sid = data.get("session_id")
    try:
        mode = pm.plugin_mode(data_dir, sid)
    except pm.ConfigError as e:
        if own:
            return "deny", f"oturum durumu çözülemedi ({e}); plugin'e ait korunan çağrı reddedildi"
        return "deny", f"oturum durumu bozuk ({e}); plugin modu belirlenemediği için Meta çağrısı reddedildi"
    if not own and not mode:
        return "pass", None
    lst = load_allowlist()
    if bare not in set(lst["allow"]):
        return "deny", (f"'{bare}' Meta izin listesinde yok. Plugin yalnızca salt okuma araçlarını kullanır (9.3); "
                        "yazma/harcama başlatan araçlar asla çağrılmaz. Listeye ekleme insan onayıyla yapılır.")
    if mode and bare == lst.get("library_tool"):
        sess = pm.load_session(data_dir, sid) or {}
        limit = int(sess.get("library_query_limit") or lst.get("library_query_budget_default", 20))
        key = f"{sess.get('profile_id') or 'p0'}:{dt.date.today().isoformat()}"
        b = sess.get("library_budget") or {}
        if b.get("window") != key:
            b = {"window": key, "used": 0, "limit": limit}
        if b["used"] >= limit:
            return "deny", (f"Reklam Kütüphanesi sorgu bütçesi doldu ({b['used']}/{limit}, görüntü başına). Toplu çekim yapılmaz (9.2); "
                            "görüntüyü mevcut sonuçlarla kaydedin ya da kullanıcı bütçeyi açıkça değiştirsin.")
        b["used"] += 1
        sess["library_budget"] = b
        pm.save_session(data_dir, sid, sess)
    return "allow", None


def main() -> int:
    try:
        data = pm.read_input()
        verdict, reason = decide(data)
        if verdict == "deny":
            pm.deny(reason or "reddedildi")
        return 0
    except Exception as e:  # hata durumunda engelle (9.3)
        pm.deny(f"Meta koruması beklenmeyen hata verdi ({type(e).__name__}); güvenlik için çağrı reddedildi. {pm.setup_hint()}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
