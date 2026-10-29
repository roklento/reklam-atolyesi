"""Dağıtılan kurulumun makinedeki doğrulaması (spec 12.9 adım 8 ve 12, 12.10, 12.12, 12.13 güncelleme sırası).

Bileşenler dağıtılan sürümde hazır gelir ve kurulum sahibinin kurulumunda üretilip denetlenmiştir (system_manifest.json: nötrlük denetimi,
deneme workflow'u, resmi kaynak kontrolleri). Bu betik aynı sürümün BU makinede çalıştığını kanıtlar:
  1. (güncellemede) veritabanı yedeği; açılışta bekleyen migration'lar kendi yedekleriyle uygulanır
  2. sentetik duman testi (12.12; data_dir/.selftest içinde, bitince silinir)
  3. final Türkçe render (2 sn, 1080×1920, ölçek 1) → 30. kare, kurulum sahibinin görsel olarak incelediği referans kareyle karşılaştırılır
  4. animasyon galerisi (37 bileşen × 4 kare) → plugin'deki incelenmiş galeriyle bileşen bileşen karşılaştırılır
  5. doctor --write-ok (testleri çalıştırır, hook ve MCP komutlarını gerçek yorumlayıcıyla dener, plugin kaydını doğrular)
Karşılaştırma eşiği aşılamazsa ve konsol etkileşimliyse kareler açılır ve kullanıcıya sorulur; kaydın `by` alanı kimin baktığını yazar.

Kullanım: <data_dir>/.venv/Scripts/python.exe kurulum_dogrula.py --data-dir <data_dir> [--claude <claude>] [--deviations-json <dosya>]
          [--guncelleme] [--etkilesimli] [--work <geçici klasör>] [--json-out <özet.json>]
Özet varsayılan olarak data_dir/logs/kurulum-dogrulama-<zaman>.json'a yazılır.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "servers" / "ad_memory"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

TR_REFERENCE = ROOT / "scripts" / "setup" / "referans" / "tr_final_kare30.png"
GALLERY_REFERENCE = ROOT / "templates" / "remotion" / "gallery.png"
GALLERY_BLOCK = (740, 350)  # render.gallery: bileşen başına 4 × 180 px + 20 px boşluk; satır 320 + 30 px
TR_MIN_PSNR = 32.0
BLOCK_MIN_PSNR = 25.0
GALLERY_MIN_MEAN_PSNR = 30.0


def say(msg: str) -> None:
    print(msg, flush=True)


def run_py(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, *args], capture_output=True, timeout=timeout, env=env, cwd=str(ROOT))


def last_json(cp: subprocess.CompletedProcess) -> dict:
    for line in reversed(cp.stdout.decode("utf-8", "replace").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {}


def psnr(a, b) -> float:
    import numpy as np
    d = (np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)) ** 2
    mse = float(d.mean())
    return float("inf") if mse == 0 else float(10 * np.log10(255.0 ** 2 / mse))  # JSON'a yazılabilir düz float


def load_rgb(p: Path):
    from PIL import Image
    return Image.open(p).convert("RGB")


def compare_turkish(still: Path) -> dict:
    a, b = load_rgb(still), load_rgb(TR_REFERENCE)
    if a.size != b.size:
        return {"ok": False, "reason": f"boyut farklı {a.size} ≠ {b.size}"}
    v = psnr(a, b)
    return {"ok": v >= TR_MIN_PSNR, "psnr_db": None if v == float("inf") else round(v, 2), "identical": v == float("inf"),
            "threshold_db": TR_MIN_PSNR}


def compare_gallery(img: Path) -> dict:
    a, b = load_rgb(img), load_rgb(GALLERY_REFERENCE)
    if a.size != b.size:
        return {"ok": False, "reason": f"boyut farklı {a.size} ≠ {b.size}"}
    bw, bh = GALLERY_BLOCK
    blocks, low = [], []
    for y in range(0, a.size[1], bh):
        for x in range(0, a.size[0], bw):
            box = (x, y, min(x + bw, a.size[0]), min(y + bh, a.size[1]))
            v = psnr(a.crop(box), b.crop(box))
            blocks.append(v)
            if v < BLOCK_MIN_PSNR:
                low.append({"block": [x // bw, y // bh], "psnr_db": round(v, 2)})
    finite = [v for v in blocks if v != float("inf")]
    mean = sum(finite) / len(finite) if finite else float("inf")
    return {"ok": not low and mean >= GALLERY_MIN_MEAN_PSNR, "identical": not finite,
            "mean_psnr_db": None if mean == float("inf") else round(mean, 2), "low_blocks": low,
            "threshold_db": {"block": BLOCK_MIN_PSNR, "mean": GALLERY_MIN_MEAN_PSNR}}


def ask_human(question: str, images: list[Path], interactive: bool) -> bool | None:
    if not interactive or not sys.stdin or not sys.stdin.isatty():
        return None
    for p in images:
        try:
            if os.name == "nt":
                os.startfile(str(p))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(p)])
        except OSError:
            say(f"  (açılamadı, elle açın: {p})")
    while True:
        ans = input(f"{question} [E/H]: ").strip().lower()
        if ans in ("e", "evet", "y", "yes"):
            return True
        if ans in ("h", "hayır", "hayir", "n", "no"):
            return False


def review_record(cmp: dict, what: str, images: list[Path], interactive: bool, question: str) -> dict:
    today = dt.date.today().isoformat()
    if cmp.get("ok"):
        return {"ok": True, "by": f"otomatik karşılaştırma: {what} kurulum sahibinin görsel olarak incelediği referansla", "at": today,
                "comparison": cmp}
    human = ask_human(question, images, interactive)
    if human is None:
        return {"ok": False, "by": "otomatik karşılaştırma (eşik geçilmedi; etkileşimli inceleme yapılmadı)", "at": today, "comparison": cmp}
    return {"ok": human, "by": "kullanıcı (görsel inceleme, eşik geçilmediği için soruldu)", "at": today, "comparison": cmp}


def accepted_deviation(data_dir: Path, check: str) -> bool:
    import doctor as DR
    return any(d.get("check") == check and d.get("decided_by") == "user" and d.get("status") == "accepted"
               for d in DR.load_install_deviations(data_dir))


def handle_global_skills(data_dir: Path, choice: str, interactive: bool) -> tuple[dict | None, dict]:
    """~/.claude/skills altında çakışan genel skill'ler (1.4.1). 'tasi': ~/.claude/skills-yedek'e taşınır (silinmez);
    'birak': kullanıcı kararı 'global_skills' sapması olarak kaydedilir; 'sor': etkileşimli konsolda sorulur, değilse karar yok
    (doctor maddeyi kırmızı gösterir ve ne yapılacağını söyler). Dönüş: (sapma kaydı ya da None, adım ayrıntısı)."""
    import doctor as DR
    clash = DR.global_skill_clash()
    if not clash:
        return None, {"clash": []}
    if accepted_deviation(data_dir, "global_skills"):
        return None, {"clash": clash, "karar": "daha önce kabul edilmiş sapma (dokunulmadı)"}
    if choice == "sor":
        if interactive and sys.stdin and sys.stdin.isatty():
            say(f"  ~/.claude/skills altında plugin'in Remotion başvurularıyla aynı adlı genel skill'ler var: {', '.join(clash)}")
            say("  Plugin bunları kullanmaz. Başka işlerde kullanıyorsanız dokunmayın; kullanmıyorsanız yedek klasörüne taşınabilir (silinmez).")
            while True:
                ans = input("  [T] yedeğe taşı  /  [D] dokunma: ").strip().lower()
                if ans in ("t", "taşı", "tasi"):
                    choice = "tasi"
                    break
                if ans in ("d", "dokunma", "b", "birak", "bırak"):
                    choice = "birak"
                    break
        else:
            return None, {"clash": clash, "karar": "verilmedi (etkileşimsiz); --global-skills tasi|birak ile yeniden çalıştırın"}
    if choice == "tasi":
        src = Path.home() / ".claude" / "skills"
        dst = Path.home() / ".claude" / "skills-yedek"
        dst.mkdir(parents=True, exist_ok=True)
        moved = []
        for name in clash:
            target = dst / name
            i = 2
            while target.exists():
                target = dst / f"{name}-{i}"
                i += 1
            shutil.move(str(src / name), str(target))
            moved.append(target.name)
        return None, {"clash": clash, "karar": "yedeğe taşındı", "yedek": "~/.claude/skills-yedek", "tasinan": moved}
    rec = {"id": "global_remotion_skills", "check": "global_skills", "spec": "12.4, 12.5",
           "deviation": (f"~/.claude/skills altında genel skill'ler var ({', '.join(clash)}); kullanıcı başka işlerde kullandığı için dokunulmamasına "
                         "karar verdi. Plugin bunları okumaz; Remotion için ref-remotion-components ve ref-vendor-map geçerlidir."),
           "decided_by": "user", "decided_at": dt.date.today().isoformat(), "status": "accepted"}
    return rec, {"clash": clash, "karar": "dokunulmadı (sapma olarak kaydedilecek)"}


def handle_plugins(data_dir: Path, choice: str, interactive: bool, claude: str | None) -> tuple[dict | None, dict]:
    """Öteki plugin'ler (1.6.0; scripts/lib/plugin_scan.py). Video üretimi skill'i ya da ücretli/yazma sağlayıcısı MCP'si olan etkin plugin:
    'devre-disi': `claude plugin disable` ile kapatılır (geri alınabilir, kaldırılmaz; kuruma zorunlu senkron plugin kapatılamaz);
    'birak': kullanıcı kararı kimlik listesiyle 'plugins' sapması olarak kaydedilir; 'sor': etkileşimli konsolda sorulur, değilse karar yok
    (doctor maddeyi kırmızı gösterir). Daha önce kabul edilmiş kimlikler yeniden sorulmaz. Dönüş: (sapma kaydı ya da None, adım ayrıntısı)."""
    import doctor as DR
    import plugin_scan as PS
    claude = DR.find_claude(claude)
    sc = PS.scan(claude)
    known = DR.accepted_plugin_ids(DR.load_install_deviations(data_dir))
    clash = [p for p in sc["plugins"] if p["id"] in sc["clash"]]
    new = [p for p in clash if p["id"] not in known]
    det = {"source": sc["source"], "clash": [{"id": p["id"], "categories": p["categories"]} for p in clash], "notes": sc["notes"]}
    if not clash:
        return None, det
    if not new:
        return None, {**det, "karar": "daha önce kabul edilmiş sapma (dokunulmadı)"}
    if choice == "sor":
        if interactive and sys.stdin and sys.stdin.isatty():
            say("  Kurulu öteki plugin'lerden bazıları video üretimi ya da ücretli/yayın işi yapabiliyor:")
            for p in new:
                c = p["categories"]
                why = "; ".join(x for x in (("video skill'leri: " + ", ".join(c["video"][:4])) if c["video"] else "",
                                             ("sağlayıcı: " + ", ".join(c["paid_or_write"][:4])) if c["paid_or_write"] else "") if x)
                say(f"   - {p['id']} ({why})")
            say("  reklam-atolyesi bunları kullanmaz; açık kalırlarsa video işinde plan, render ve QC kapılarını atlatabilirler.")
            say("  Kapatmak geri alınabilir (claude plugin enable <ad>); plugin silinmez.")
            while True:
                ans = input("  [K] kapat  /  [D] dokunma: ").strip().lower()
                if ans in ("k", "kapat", "devre-disi"):
                    choice = "devre-disi"
                    break
                if ans in ("d", "dokunma", "b", "birak", "bırak"):
                    choice = "birak"
                    break
        else:
            return None, {**det, "karar": "verilmedi (etkileşimsiz); --plugins devre-disi|birak ile yeniden çalıştırın"}
    if choice == "devre-disi" and claude:
        res = [PS.disable(claude, p) for p in new]
        left = [x["id"] for x in res if not x["ok"]]
        det = {**det, "karar": "kapatıldı" if not left else "kısmen kapatıldı", "sonuc": res}
        if not left:
            return None, det
        new = [p for p in new if p["id"] in left]  # kapatılamayan (ör. kuruma zorunlu) sapma olarak kaydedilir
    elif choice == "devre-disi":
        det = {**det, "karar": "kapatılamadı (claude yürütülebilir dosyası bulunamadı)"}
    ids = sorted(p["id"] for p in new) + sorted(known & set(sc["clash"]))
    rec = {"id": "other_plugins", "check": "plugins", "spec": "1.6.0 A", "plugin_ids": sorted(set(ids)),
           "deviation": (f"Video üretimi ya da ücretli/yazma sağlayıcısı olan öteki plugin'ler açık bırakıldı ({', '.join(sorted(set(ids)))}). "
                         "reklam-atolyesi bunların skill'lerini okumaz ve uygulamaz; Remotion için ref-remotion-components ve ref-vendor-map geçerlidir."),
           "decided_by": "user", "decided_at": dt.date.today().isoformat(), "status": "accepted"}
    return rec, {**det, "karar": det.get("karar", "dokunulmadı") + " (sapma olarak kaydedilecek)"}


def backup_before_update(data_dir: Path, version: str) -> dict:
    db = data_dir / "db" / "ad-memory.sqlite"
    if not db.exists():
        return {"skipped": "veritabanı yok"}
    from admem.store import Store  # açılışta bekleyen migration varsa önce kendi yedeğini alır (12.13)
    s = Store(db, data_dir)
    try:
        return s.backup(reason=f"guncelleme-{version}")
    finally:
        s.close()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--claude")
    ap.add_argument("--deviations-json")
    ap.add_argument("--guncelleme", action="store_true", help="kullanımdaki data_dir'de sürüm güncellemesi")
    ap.add_argument("--etkilesimli", action="store_true", help="eşik geçilmezse kareleri açıp kullanıcıya sor")
    ap.add_argument("--global-skills", choices=("sor", "tasi", "birak"), default="sor",
                    help="~/.claude/skills altında çakışan genel skill'ler: sor (etkileşimli), tasi (yedeğe taşı), birak (sapma olarak kaydet)")
    ap.add_argument("--plugins", choices=("sor", "devre-disi", "birak"), default="sor",
                    help="video üretimi ya da ücretli/yazma sağlayıcısı olan öteki plugin'ler: sor (etkileşimli), devre-disi (claude plugin disable), "
                         "birak (sapma olarak kaydet)")
    ap.add_argument("--work")
    ap.add_argument("--json-out")
    a = ap.parse_args()
    data_dir = Path(a.data_dir).resolve()
    version = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    work = Path(a.work) if a.work else Path(tempfile.mkdtemp(prefix="reklam-atolyesi-dogrulama-"))
    work.mkdir(parents=True, exist_ok=True)
    summary: dict = {"plugin_version": version, "data_dir": str(data_dir), "work": str(work), "steps": []}
    t_all = time.time()

    def step(name: str, ok: bool, detail) -> None:
        summary["steps"].append({"step": name, "ok": bool(ok), "detail": detail})
        say(f"{'✔' if ok else '✘'} {name}")

    if a.guncelleme:
        say("• Veritabanı yedeği alınıyor…")
        try:
            b = backup_before_update(data_dir, version)
            step("Güncelleme öncesi veritabanı yedeği", True, b)
        except Exception as e:  # yedek alınamazsa doğrulama sürmez: veri güvenliği önce gelir
            step("Güncelleme öncesi veritabanı yedeği", False, f"{type(e).__name__}: {e}")
            finish(summary, a, t_all, ok=False)

    say("• Sentetik duman testi (yaklaşık 5 dk)…")
    cp = run_py([str(ROOT / "scripts" / "selftest" / "smoke.py"), "--data-dir", str(data_dir), "--out", str(work / "smoke.json")], 3600)
    smoke = json.loads((work / "smoke.json").read_text(encoding="utf-8")) if (work / "smoke.json").exists() else {}
    step("Sentetik duman testi (9 adım)", cp.returncode == 0 and smoke.get("ok") is True,
         {"steps": [(s["step"], s["ok"]) for s in smoke.get("steps", [])],
          "errors": [s.get("error") for s in smoke.get("steps", []) if not s["ok"]]})

    say("• Türkçe karakterli final render…")
    tr_dir = work / "tr"
    tr_out = tr_dir / "tr_final.mp4"
    cp = run_py([str(ROOT / "scripts" / "render" / "render.py"), "turkish", "--data-dir", str(data_dir), "--work", str(tr_dir),
                 "--out", str(tr_out)], 1800)
    still = tr_out.with_suffix(".png")
    if cp.returncode == 0 and still.exists():
        cmp = compare_turkish(still)
        vr = review_record(cmp, "30. kare", [still, TR_REFERENCE], a.etkilesimli,
                           "Açılan iki görselde Türkçe harfler (ğ ş ı İ ç ö ü) aynı ve doğru çizilmiş mi?")
        (work / "turkish.json").write_text(json.dumps({"out": str(tr_out), "still": str(still), "visual_review": vr}, ensure_ascii=False,
                                                      indent=1), encoding="utf-8")
        step("Türkçe final render ve görsel karşılaştırma", vr["ok"], cmp)
    else:
        step("Türkçe final render ve görsel karşılaştırma", False, cp.stderr.decode("utf-8", "replace")[-2000:])

    say("• Animasyon galerisi (37 bileşen, yaklaşık 6 dk)…")
    g_dir = work / "galeri"
    g_out = g_dir / "gallery.png"
    cp = run_py([str(ROOT / "scripts" / "render" / "render.py"), "gallery", "--data-dir", str(data_dir), "--work", str(g_dir),
                 "--out", str(g_out)], 3600)
    g = last_json(cp)
    if cp.returncode == 0 and g_out.exists():
        cmp = compare_gallery(g_out)
        vr = review_record(cmp, "galeri", [g_out, GALLERY_REFERENCE], a.etkilesimli,
                           "Açılan iki galeride bileşenler aynı görünüyor ve hiçbiri boş/bozuk değil mi?")
        g["visual_review"] = vr
        (work / "gallery.json").write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
        step("Animasyon galerisi ve görsel karşılaştırma", vr["ok"] and not g.get("failed") and not g.get("frames_all_black"),
             {"components": g.get("components"), "failed": g.get("failed"), "comparison": cmp})
    else:
        step("Animasyon galerisi ve görsel karşılaştırma", False, cp.stderr.decode("utf-8", "replace")[-2000:])

    dev_json = a.deviations_json
    rec, gdet = handle_global_skills(data_dir, a.global_skills, a.etkilesimli)
    if gdet.get("clash"):
        step("Çakışan genel skill'ler (~/.claude/skills)", gdet.get("karar", "").startswith(("yedeğe", "dokunulmadı", "daha önce")), gdet)
    prec, pdet = handle_plugins(data_dir, a.plugins, a.etkilesimli, a.claude)
    if pdet.get("clash"):
        step("Öteki plugin'ler (video üretimi / ücretli sağlayıcı)",
             pdet.get("karar", "").startswith(("kapatıldı", "kısmen", "kapatılamadı", "dokunulmadı", "daha önce")), pdet)
    new_recs = [x for x in (rec, prec) if x]
    if new_recs:
        recs = json.loads(Path(a.deviations_json).read_text(encoding="utf-8")) if a.deviations_json else []
        dev_json = str(work / "sapmalar.json")
        Path(dev_json).write_text(json.dumps([*recs, *new_recs], ensure_ascii=False, indent=1), encoding="utf-8")

    say("• Statik kontrol (doctor; otomatik testler dahil, yaklaşık 5 dk)…")
    args = [str(ROOT / "scripts" / "setup" / "doctor.py"), "--data-dir", str(data_dir), "--results-dir", str(work),
            "--write-ok", "--json-out", str(work / "doctor.json")]
    if a.claude:
        args += ["--claude", a.claude]
    if dev_json:
        args += ["--deviations-json", dev_json]
    if a.guncelleme:
        args.append("--update")
    cp = run_py(args, 7200)
    doc = json.loads((work / "doctor.json").read_text(encoding="utf-8")) if (work / "doctor.json").exists() else {}
    red = [{"key": i["key"], "title": i["title"], "detail": i["detail"]} for i in doc.get("items", []) if not i["ok"] and not i["accepted_deviation"]]
    step("Statik kontrol (doctor) ve kurulum işareti", bool(doc.get("ok")) and (doc.get("write_ok") or {}).get("written") is True,
         {"blocking": red, "accepted_deviations": doc.get("accepted_deviations"), "write_ok": doc.get("write_ok")})
    finish(summary, a, t_all, ok=all(s["ok"] for s in summary["steps"]))


def _home_variants() -> list[str]:
    home = str(Path.home())
    homes = {home}
    if os.name == "nt":  # %TEMP% çoğu zaman 8.3 kısa adla gelir (C:\Users\ADMINI~1\...)
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(1024)
            if ctypes.windll.kernel32.GetShortPathNameW(home, buf, 1024):
                homes.add(buf.value)
        except Exception:
            pass
    out = set()
    for h in homes:
        if len(h) > 3:
            out |= {h, h.replace("\\", "/"), h.replace("\\", "\\\\")}
    return sorted(out, key=len, reverse=True)


_HOME_RES = [re.compile(re.escape(v), re.I) for v in _home_variants()]
_USER_DIR_RE = re.compile(r"(?i)((?:[A-Za-z]:)?(?:\\{1,2}|/)(?:users|home)(?:\\{1,2}|/))[^\\/\"'\s]+")


def mask_home(obj):
    """Özet destek için sağlayıcıya gönderilebilir: kullanıcı klasörü (kullanıcı adı) %USERPROFILE% olarak yazılır.
    Tam, kısa (8.3), küçük harfli ve çift ters bölülü biçimler; anahtarlar dahil. Yedek olarak Users/home altındaki ilk klasör adı da gizlenir."""
    if isinstance(obj, dict):
        return {mask_home(k): mask_home(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [mask_home(v) for v in obj]
    if isinstance(obj, str):
        for rx in _HOME_RES:
            obj = rx.sub("%USERPROFILE%", obj)
        obj = _USER_DIR_RE.sub(r"\1<kullanıcı>", obj)
    return obj


def finish(summary: dict, a, t_all: float, ok: bool) -> None:
    summary["ok"] = ok
    summary["seconds"] = round(time.time() - t_all, 1)
    text = json.dumps(mask_home(summary), ensure_ascii=False, indent=1, default=str)
    if a.json_out:
        out = Path(a.json_out)
    else:  # data_dir/logs kurulumdan sonra izin verilen klasördür (14.2); özet hassas veri içermez
        out = Path(summary["data_dir"]) / "logs" / f"kurulum-dogrulama-{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    if ok and not a.work:
        shutil.rmtree(summary["work"], ignore_errors=True)  # geçici render ve rapor dosyaları; başarısızlıkta inceleme için kalır
    say(json.dumps({"ok": ok, "seconds": summary["seconds"], "summary": str(out)}, ensure_ascii=False))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
