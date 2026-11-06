"""İzinli dosya yüklemesi (2.10.12, bölüm 10).

creative_create_asset_upload çağrısından sonra baytları sağlayıcıya bu betik gönderir. Dosyaya bağlı (kişisel veri içeren) izinde
gönderilecek dosyayı komut satırından almaz: izin kaydındaki yolu açar, içerik özetini izin anındakiyle karşılaştırır, kişi/yorum
izninin geri çekilmediğine bakar ve yalnızca o baytları başlatma adımında dönen adrese PUT ile yollar. Başarılı gönderim oturuma
yazılır; creative_finalize_asset_upload ancak bundan sonra geçer.

Kullanım:
  python izinli_yukleme.py --data-dir <data_dir> --session <session_id> --asset-id <kimlik> [--file <yol>]
  --file yalnızca kişisel veri içermeyen (dosyaya bağlı olmayan) izinde gerekir.
Çıkış kodu 0 = gönderildi; 2 = reddedildi (neden JSON'da).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hooks"))
import plugin_mode as pm  # noqa: E402
import cost_guard as CG  # noqa: E402


def _put(url: str, body: bytes, mime: str, timeout: int = 300) -> int:
    req = urllib.request.Request(url, data=body, method="PUT", headers={"Content-Type": mime, "Content-Length": str(len(body))})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — adres sağlayıcının başlatma yanıtından gelir
        return r.status


def run(data_dir: Path, sid: str, asset_id: str, file: str | None, put=_put) -> dict:
    sess = pm.load_session(data_dir, sid) or {}
    pend = CG.pending_uploads(sess)
    u = next((x for x in pend if x.get("asset_id") == asset_id), None)
    if u is None:
        return {"ok": False, "why": "bu kimlikle izinle başlatılmış ve süresi geçmemiş bir yükleme yok (başlatma adımını yeniden çalıştır)"}
    if not u.get("url"):
        return {"ok": False, "why": "başlatma adımında sağlayıcının yükleme adresi okunamadı"}
    if u.get("uploaded"):
        return {"ok": False, "why": "bu yüklemenin dosyası zaten gönderildi"}
    f = u.get("file")
    if f:
        if file and Path(file).resolve() != Path(f["path"]).resolve():
            return {"ok": False, "why": "verilen dosya, izin alınan dosya değil; izin kaydındaki dosya gönderilir"}
        changed = CG._file_changed(f)
        if changed:
            return {"ok": False, "why": changed}
        perms = {p.get("at"): p for p in (sess.get("upload_permissions") or [])}
        perm = perms.get(u.get("perm_at"))
        if perm is None:
            return {"ok": False, "why": "yüklemeyi başlatan izin artık oturumda yok"}
        gone = CG._withdrawn(perm, data_dir)
        if gone:
            return {"ok": False, "why": "izin geri çekildi: " + ", ".join(gone)}
        path = Path(f["path"])
    else:
        if not file:
            return {"ok": False, "why": "--file gerekli (dosyaya bağlı olmayan izin)"}
        path = Path(file)
    body = path.read_bytes()
    sha = hashlib.sha256(body).hexdigest()
    if f and sha != f.get("sha256"):
        return {"ok": False, "why": "dosya okunurken değişti"}
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    status = put(u["url"], body, mime)
    if not 200 <= int(status) < 300:
        return {"ok": False, "why": f"sağlayıcı yüklemeyi kabul etmedi (HTTP {status})"}

    def mark(s: dict) -> None:
        for x in s.get("pending_uploads") or []:
            if x.get("asset_id") == asset_id:
                x["uploaded"], x["sent_sha256"] = True, sha
    pm.update_session(data_dir, sid, mark)
    return {"ok": True, "asset_id": asset_id, "file": path.name, "bytes": len(body), "sha256": sha}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--session", required=True)
    ap.add_argument("--asset-id", required=True)
    ap.add_argument("--file")
    a = ap.parse_args()
    try:
        out = run(Path(a.data_dir), a.session, a.asset_id, a.file)
    except (OSError, ValueError, pm.ConfigError) as e:
        out = {"ok": False, "why": f"{type(e).__name__}: {e}"}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
