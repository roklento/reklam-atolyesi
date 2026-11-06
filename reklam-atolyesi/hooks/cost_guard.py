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


NO_FILE_STEP = {"creative_finalize_asset_upload"}  # yüklemeyi tamamlama adımı dosya adı taşımaz; başlatan adımın kaydına bağlanır
UPLOAD_TTL_S = 30 * 60  # başlatılan yüklemenin tamamlanabileceği süre


def _sha256(path: Path) -> str | None:
    import hashlib
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _file_changed(f: dict) -> str | None:
    """2.10.7: izin anındaki içerik özeti karar anında yeniden hesaplanır (aynı ad ve boyutta başka içerik geçmez)."""
    if not f.get("path"):
        return "izin kaydında dosya yolu yok (2.10.7 öncesi izin); processing_permission_check yeniden çalıştırılmalı"
    if _sha256(Path(f["path"])) != f.get("sha256"):
        return f"{f.get('name')} izin verildikten sonra değişmiş ya da silinmiş; yeni içerik için izin yeniden alınmalı"
    return None


def _now_s() -> float:
    import time
    return time.time()


def upload_decision(perms: list[dict], tin: dict, data_dir: Path, bare: str = "", sid: str | None = None) -> tuple[str, str | None]:
    """2.10.3: izin dosyaya bağlıysa gönderilen dosyanın adı ve boyutu izindeki dosyalardan biriyle eşleşmeli ve verilen kişi/yorum
    izinleri hâlâ geçerli olmalı. 2.10.7: ad ve boyut birlikte eşleşmeli, dosyanın içerik özeti izin anındakiyle aynı olmalı; başlatılan
    her yükleme oturuma yazılır ve tamamlama adımı yalnızca böyle bir kayıtla, izin ve dosya hâlâ geçerliyse geçer. Kişisel veri içeren
    izin her zaman dosyaya bağlıdır. Dosyasız eski tip izin yalnızca kişisel veri içermeyen gönderim içindir."""
    if bare in NO_FILE_STEP:
        return _finalize_decision(data_dir, sid)
    strs: set = set()
    nums: set = set()
    _input_values(tin, strs, nums)
    for i, perm in enumerate(perms):
        files = perm.get("files") or []
        if not files:
            if not perm.get("personal"):
                _record_upload(data_dir, sid, None, None)
                return "allow", None
            continue
        for f in files:
            if f.get("name") in strs and f.get("size") in nums:
                gone = _withdrawn(perm, data_dir)
                if gone:
                    return "deny", ("bu dosya için alınan izin artık geçerli değil (geri çekilmiş ya da bulunamadı: " + ", ".join(gone)
                                    + "); dosya gönderilmez (bölüm 10)")
                changed = _file_changed(f)
                if changed:
                    return "deny", changed + " (bölüm 10)"
                _record_upload(data_dir, sid, perm, f)
                return "allow", None
    return "deny", ("bu dosya için yükleme izni alınmadı: izin başka dosya(lar) için verildi ya da ad ve boyut eşleşmedi. Gönderilecek "
                    "dosyayla processing_permission_check(..., files=[dosya]) yeniden çalıştırılmalı (bölüm 10)")


def _record_upload(data_dir: Path, sid: str | None, perm: dict | None, f: dict | None) -> None:
    if not sid:
        return

    def add(s: dict) -> None:
        pend = [u for u in (s.get("pending_uploads") or []) if _now_s() - float(u.get("t") or 0) < UPLOAD_TTL_S]
        pend.append({"t": _now_s(), "perm_at": (perm or {}).get("at"), "file": f})
        s["pending_uploads"] = pend[-20:]
    pm.update_session(data_dir, sid, add)


def _finalize_decision(data_dir: Path, sid: str | None) -> tuple[str, str | None]:
    """Tamamlama adımı: süresi geçmemiş, izinle başlatılmış bir yükleme olmalı; izin ve dosya hâlâ geçerli olmalı (2.10.7)."""
    if not sid:
        return "deny", "yükleme tamamlama adımı oturum kaydı ister"
    out: dict = {}

    def take(s: dict) -> None:
        pend = [u for u in (s.get("pending_uploads") or []) if _now_s() - float(u.get("t") or 0) < UPLOAD_TTL_S]
        if not pend:
            out["err"] = "bu oturumda izinle başlatılmış ve süresi geçmemiş bir yükleme yok; tamamlama adımı engellendi (bölüm 10)"
            s["pending_uploads"] = pend
            return
        u = pend.pop(0)
        s["pending_uploads"] = pend
        out["u"] = u
        perms = {p.get("at"): p for p in (s.get("upload_permissions") or [])}
        out["perm"] = perms.get(u.get("perm_at")) if u.get("perm_at") else None
    pm.update_session(data_dir, sid, take)
    if "err" in out:
        return "deny", out["err"]
    u, perm = out["u"], out.get("perm")
    if u.get("perm_at") and perm is None:
        return "deny", "yüklemeyi başlatan izin artık oturumda yok; dosya tamamlanmaz (bölüm 10)"
    if perm:
        gone = _withdrawn(perm, data_dir)
        if gone:
            return "deny", "izin yükleme sırasında geri çekildi (" + ", ".join(gone) + "); dosya tamamlanmaz (bölüm 10)"
    if u.get("file"):
        changed = _file_changed(u["file"])
        if changed:
            return "deny", changed + " (bölüm 10)"
    return "allow", None


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
        return upload_decision(perms, data.get("tool_input") or {}, data_dir, bare, sid)
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
