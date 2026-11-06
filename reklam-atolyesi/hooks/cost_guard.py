"""PreToolUse — plugin modunda ElevenLabs araçları için maliyet koruması (spec 9.1, 13.6).

- Sınıflandırılmamış ElevenLabs aracı reddedilir (ör. ConvAI agents_*, brand kit).
- Ücretsiz araçlar geçer. Yükleme araçları yalnızca oturuma kayıtlı işleme izniyle (yükleme öncesi izin kapısı, bölüm 10).
- Ücretli araçta estimate_only=true yalnızca canlı şemada desteği doğrulanmış araçta ücretsiz geçer.
- Gerçek ücretli çağrı: bağlı profil/kampanya + onaylı ve tek kullanımlık tahmin kaydı; aynı Store koduyla BEGIN IMMEDIATE
  içinde estimated → running rezervasyonu alınır ve onay tüketilir. Süren/tamamlanmış/belirsiz çağrı ve rezervasyon hatası reddedilir.
Bütün gövde tek try içinde; beklenmeyen istisnada kapsamdaki çağrı reddedilir. Ağ çağrısı yapılmaz.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import plugin_mode as pm

sys.path.insert(0, str(pm.PLUGIN_ROOT / "servers" / "ad_memory"))


def load_classes() -> dict:
    return json.loads((pm.HOOKS_DIR / "elevenlabs_tools.json").read_text(encoding="utf-8"))


def _input_values(obj, strs: set, nums: set, depth: int = 0) -> None:
    if depth > 4:
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _input_values(v, strs, nums, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            _input_values(v, strs, nums, depth + 1)
    elif isinstance(obj, bool):
        return
    elif isinstance(obj, int):
        nums.add(obj)
    elif isinstance(obj, str):
        strs.add(obj.replace("\\", "/").rsplit("/", 1)[-1].split("?", 1)[0])


def _withdrawn(perm: dict, data_dir: Path) -> list[str]:
    """İzin alındıktan sonra geri çekilen kişi/yorum izinleri (yükleme anında veritabanından yeniden okunur)."""
    ids = [("person_consents", "kişi izni", i) for i in perm.get("consent_ids") or []] + \
          [("reviews", "yorum", i) for i in perm.get("review_ids") or []]
    if not ids:
        return []
    if not pm.db_path(data_dir).exists():
        return ["izin kayıtları okunamadı (veritabanı yok)"]
    from admem.store import Store
    st = Store(pm.db_path(data_dir), data_dir)
    try:
        out = []
        for table, label, i in ids:
            r = st.q1(f"SELECT withdrawn_at FROM {table} WHERE id=?", (int(i),))
            if not r or r["withdrawn_at"]:
                out.append(f"{label} #{i}")
        return out
    finally:
        st.close()


NO_FILE_STEP = {"creative_finalize_asset_upload"}  # yüklemeyi tamamlama adımı dosya adı taşımaz; başlatan adım denetlenmiştir


def upload_decision(perms: list[dict], tin: dict, data_dir: Path, bare: str = "") -> tuple[str, str | None]:
    """2.10.3: izin dosyaya bağlıysa gönderilen dosyanın adı (araç boyut veriyorsa boyutu da) izindeki dosyalardan biriyle eşleşmeli ve
    verilen kişi/yorum izinleri hâlâ geçerli olmalı. Kişisel veri içeren izin her zaman dosyaya bağlıdır (processing_permission_check
    files ister). Dosyasız eski tip izin yalnızca kişisel veri içermeyen gönderim içindir."""
    if bare in NO_FILE_STEP:
        return "allow", None
    strs: set = set()
    nums: set = set()
    _input_values(tin, strs, nums)
    for perm in perms:
        files = perm.get("files") or []
        if not files:
            if not perm.get("personal"):
                return "allow", None
            continue
        if any(f.get("name") in strs and (not nums or f.get("size") in nums) for f in files):
            gone = _withdrawn(perm, data_dir)
            if gone:
                return "deny", ("bu dosya için alınan izin artık geçerli değil (geri çekilmiş ya da bulunamadı: " + ", ".join(gone)
                                + "); dosya gönderilmez (bölüm 10)")
            return "allow", None
    return "deny", ("bu dosya için yükleme izni alınmadı: izin başka dosya(lar) için verildi. Gönderilecek dosyayla "
                    "processing_permission_check(..., files=[dosya]) yeniden çalıştırılmalı (bölüm 10)")


def decide(data: dict, argv: list[str] | None = None) -> tuple[str, str | None]:
    tool = data.get("tool_name") or ""
    own = tool.startswith(pm.OWN_ELEVEN_PREFIX)
    bare = pm.bare_tool(tool)
    try:
        data_dir = pm.data_dir_from_argv(argv)
    except pm.ConfigError as e:
        return ("deny", f"maliyet koruması yapılandırılamadı ({e}). {pm.setup_hint()}") if own else ("pass", None)
    sid = data.get("session_id")
    try:
        sess = pm.load_session(data_dir, sid)
    except pm.ConfigError as e:
        return "deny", f"oturum durumu bozuk ({e}); maliyet koruması atlanmaz"
    if not sess or not sess.get("plugin_mode"):
        return "pass", None  # plugin dışı kullanım: bilinçli sınır (bölüm 11)
    classes = load_classes()
    if bare in set(classes.get("free", [])):
        return "allow", None
    if bare in set(classes.get("upload", [])):
        pid = sess.get("profile_id")
        perms = [u for u in (sess.get("upload_permissions") or []) if u.get("provider") == "elevenlabs" and u.get("profile_id") == pid]
        if not pid or not perms:
            return "deny", ("dosya dış sağlayıcıya gönderilmeden önce yükleme öncesi izin kapısı gerekir: processing_permission_check "
                            "(provider='elevenlabs', session_id ile) çalıştırılmalı (bölüm 10)")
        return upload_decision(perms, data.get("tool_input") or {}, data_dir, bare)
    paid = classes.get("paid", {})
    if bare not in paid:
        return "deny", f"'{bare}' sınıflandırılmamış ElevenLabs aracı; plugin modunda varsayılan olarak engellenir (9.1). Liste insan onayıyla güncellenir."
    tin = data.get("tool_input") or {}
    if tin.get("estimate_only") is True:
        rec = pm.runtime_item(data_dir, "el_estimate_schema")
        tools = (rec or {}).get("component_hashes", {}).get("tools_with_estimate_only") if rec else None
        if rec and rec.get("status") == "passed" and isinstance(tools, list) and bare in tools:
            return "allow", None
        return "deny", ("estimate_only desteği bu araç için canlı şemada doğrulanmadı; üretim kapalı kalır (9.1). "
                        "Kurulum kontrolünde araç şeması okunup runtime_record('el_estimate_schema') kaydedilmeli.")
    pid, cid = sess.get("profile_id"), sess.get("campaign_id")
    if not pid or not cid:
        return "deny", "ücretli çağrı oturuma bağlı profil ve kampanya ister (session_bind)"
    if not pm.db_path(data_dir).exists():
        return "deny", "ad-memory veritabanı yok; rezervasyon yapılamaz"
    from admem import hashing
    from admem.store import Store
    h = hashing.params_hash(tool, tin, None)
    st = Store(pm.db_path(data_dir), data_dir)
    try:
        camp = st.q1("SELECT c.id FROM campaigns c JOIN profiles p ON p.brand_id=c.brand_id WHERE c.id=? AND p.id=?", (cid, pid))
        if not camp:
            return "deny", "oturuma bağlı kampanya bu profile ait değil"
        res = st.generation_reserve(cid, h, data.get("tool_use_id"))
    finally:
        st.close()
    if not res.get("ok"):
        return "deny", f"ücretli çağrı reddedildi: {res.get('reason')} (call_hash {h[:12]}…). Akış: estimate_only → generation_log → kullanıcı onayı → çağrı."
    return "allow", None


def main() -> int:
    try:
        data = pm.read_input()
        verdict, reason = decide(data)
        if verdict == "deny":
            pm.deny(reason or "reddedildi")
        return 0
    except Exception as e:  # hata durumunda engelle
        pm.deny(f"maliyet koruması beklenmeyen hata verdi ({type(e).__name__}: {e}); çağrı reddedildi. Koruma onarılmadan yeniden onaylatılıp körlemesine yürütülmez.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
