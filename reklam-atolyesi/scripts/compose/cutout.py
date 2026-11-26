"""Yerel ürün ayırma (2.10.17): ürün fotoğrafından kesik ürün, ürünün arkası doldurulmuş arka plan ve maske. Ücretsizdir, fotoğraf
bilgisayardan çıkmaz, kredi harcanmaz.

Neden: `Parallax25D`, `BehindSubjectText`, `OutlineGlow` ve `Spotlight` ürünün kesik hâlini ister. Bu iş daha önce yalnızca ücretli
bir AI servisiyle yapılabiliyordu; ürün kesildikten sonra arkada kalan boşluğu dolduran bir adım da yoktu, bu yüzden `Parallax25D`
arka planda ürünün kendisini de taşıyordu (hareket edince ürün iki kez görünür). Elinde yalnızca ürün fotoğrafı olan satıcı için
fotoğraftan hareket bu araçla ücretsizdir.

Model: BiRefNet-lite (ZhengPeng7/BiRefNet, MIT). Dosya rembg'nin (MIT) GitHub sürüm sayfasından iner; boyut ve sha256 sabittir,
tutmazsa dosya kullanılmaz. Motor kendi sanal ortamındadır (DD/.gorsel/cutout/.venv; çekirdek ortama girmez, torch yok).
Boşluk doldurma OpenCV ile yapılır (ek model yok): ürünün arkası çevresindeki renk ve dokudan tamamlanır. Büyük boşluk yumuşak
kalır; `Parallax25D`'de ön plan ürünü kapattığı için yalnızca kenarlar görünür.

Kullanım:
  cutout.py kur --data-dir DD [--yes]
      --yes olmadan yalnızca planı (indirme boyutu, hedef klasör) ve kullanıcıya sorulacak cümleyi yazar, çıkış kodu 2; hiçbir şey inmez.
  cutout.py ayir --data-dir DD --image urun.jpg [--image …] --out-dir DIR
      → DIR/<ad>.urun.png (saydam arka planlı ürün, fotoğrafla aynı boyut), DIR/<ad>.arka.png (ürünün arkası doldurulmuş arka plan),
        DIR/<ad>.maske.png (beyaz = ürün). Fotoğrafın döndürme bilgisi uygulanır; HEIC okunur. Kurulu değilse çıkış kodu 5.
  cutout.py durum --data-dir DD
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit  # noqa: E402

WORKER = Path(__file__).resolve().parent / "cutout_worker.py"
ENGINE = "cutout"
PACKAGES = ["onnxruntime==1.31.0", "numpy==2.5.5", "pillow==13.0.0"]  # sınanan sürümler (26.11.2026); onnxruntime whisper ile aynı
MODEL = {
    "name": "birefnet-lite",
    "url": "https://github.com/danielgatis/rembg/releases/download/v0.0.0/BiRefNet-general-bb_swin_v1_tiny-epoch_232.onnx",
    "file": "birefnet_lite.onnx",
    "bytes": 224005088,
    "sha256": "5600024376f572a557870a5eb0afb1e5961636bef4e1e22132025467d0f03333",
    "license": "MIT (BiRefNet, ZhengPeng7; dosya rembg sürüm sayfasından, MIT)",
}
ENV_GB = 0.1
WORKER_TIMEOUT = 1800
OFFER = ("Ürününü fotoğrafın arka planından ayırmak için bilgisayarına bir kez yaklaşık 300 MB'lık ücretsiz bir araç indirmem "
         "gerekiyor. Fotoğrafların bilgisayarından çıkmaz ve kredi harcanmaz. İndireyim mi?")
MIN_COVER, MAX_COVER = 0.01, 0.92  # ürün alanı bu aralığın dışındaysa ayırma güvenilmez: kullanıcıya gösterilir


class CutoutError(RuntimeError):
    pass


def base_dir(data_dir: Path) -> Path:
    return Path(data_dir) / ".gorsel"


def engine_python(data_dir: Path) -> Path:
    v = base_dir(data_dir) / ENGINE / ".venv"
    return v / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def model_path(data_dir: Path) -> Path:
    return base_dir(data_dir) / "models" / MODEL["file"]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _record(data_dir: Path) -> dict | None:
    p = base_dir(data_dir) / "engines.json"
    try:
        return (json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}).get(ENGINE)
    except (OSError, ValueError):
        return None


def installed(data_dir: Path) -> bool:
    """Ortam, kayıt ve doğru boyutta model dosyası birlikte varsa kurulu sayılır (sha256 kurulumda doğrulandı)."""
    mp = model_path(data_dir)
    rec = _record(data_dir)
    return (engine_python(data_dir).exists() and rec is not None and rec.get("sha256") == MODEL["sha256"]
            and mp.is_file() and mp.stat().st_size == MODEL["bytes"])


def plan(data_dir: Path) -> dict:
    return {"engine": ENGINE, "target": str(base_dir(data_dir)), "packages": PACKAGES, "model": MODEL["name"], "license": MODEL["license"],
            "download_estimate_gb": round(ENV_GB + MODEL["bytes"] / 1e9, 1), "kullaniciya": OFFER}


def download(url: str, dest: Path, size: int, digest: str) -> None:
    """Modeli .part dosyasına indirir; boyut ya da sha256 tutmazsa dosyayı siler ve durur (yarım ya da farklı dosya kullanılmaz)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(part, "wb") as f:  # noqa: S310 (sabit https adresi)
            shutil.copyfileobj(r, f, 1 << 20)
        if part.stat().st_size != size or sha256(part) != digest:
            raise CutoutError("indirilen model dosyası beklenen dosya değil (boyut ya da özet tutmuyor); dosya silindi, yeniden deneyin")
        part.replace(dest)
    finally:
        if part.exists():
            part.unlink()


def install(data_dir: Path) -> dict:
    uv = shutil.which("uv")
    if not uv:
        raise CutoutError("uv bulunamadı (kurulum gereksinimi)")
    venv = engine_python(data_dir).parent.parent
    venv.parent.mkdir(parents=True, exist_ok=True)
    if not venv.exists():
        subprocess.run([uv, "venv", "-q", "--python", "3.12", str(venv)], check=True)
    py = engine_python(data_dir)
    subprocess.run([uv, "pip", "install", "-q", "--python", str(py), *PACKAGES], check=True)
    subprocess.run([str(py), "-I", "-c", "import onnxruntime, numpy, PIL"], check=True)  # eksikse burada durur, kayıt yazılmaz
    mp = model_path(data_dir)
    if not (mp.is_file() and mp.stat().st_size == MODEL["bytes"] and sha256(mp) == MODEL["sha256"]):
        download(MODEL["url"], mp, MODEL["bytes"], MODEL["sha256"])
    rp = base_dir(data_dir) / "engines.json"
    try:
        rec = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else {}
    except (OSError, ValueError):
        rec = {}
    p = plan(data_dir)
    p.pop("kullaniciya")
    rec[ENGINE] = {**p, "sha256": MODEL["sha256"], "installed_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    rp.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec[ENGINE]


# --- çekirdek ortamdaki işler: girdi hazırlığı, kesik ürün, boşluk doldurma ------------------------------------------------------

def _open_rgb(path: Path):
    from PIL import Image, ImageOps
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:  # HEIC desteği yoksa yalnızca HEIC dosyaları açılamaz
        pass
    im = Image.open(path)
    return ImageOps.exif_transpose(im).convert("RGB")


def build_outputs(rgb, mask, out_dir: Path, stem: str) -> dict:
    """rgb: HxWx3 uint8, mask: HxW uint8 (beyaz = ürün). Kesik ürün (RGBA), doldurulmuş arka plan ve maske yazar."""
    import cv2
    import numpy as np
    from PIL import Image
    h, w = mask.shape
    out_dir.mkdir(parents=True, exist_ok=True)
    cover = float((mask >= 128).mean())
    rgba = np.dstack([rgb, mask])
    paths = {"urun": out_dir / f"{stem}.urun.png", "arka": out_dir / f"{stem}.arka.png", "maske": out_dir / f"{stem}.maske.png"}
    Image.fromarray(rgba, "RGBA").save(paths["urun"])
    Image.fromarray(mask, "L").save(paths["maske"])
    # Boşluk: yumuşak kenar dahil ürün alanı, gölge ve kenar halesi için biraz genişletilir
    hole = (mask >= 16).astype(np.uint8) * 255
    k = max(3, int(round(max(h, w) * 0.015)) | 1)
    hole = cv2.dilate(hole, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    s = min(1.0, 768 / max(h, w))  # doldurma küçük ölçekte (hız; büyük boşluk zaten yumuşak kalır), sonra yalnız boşluğa yazılır
    sw, sh = max(1, int(round(w * s))), max(1, int(round(h * s)))
    small = cv2.resize(rgb, (sw, sh), interpolation=cv2.INTER_AREA)
    shole = (cv2.resize(hole, (sw, sh), interpolation=cv2.INTER_NEAREST) > 0).astype(np.uint8) * 255
    filled = cv2.inpaint(small, shole, 7, cv2.INPAINT_TELEA) if shole.any() else small
    filled = cv2.GaussianBlur(filled, (0, 0), 1.5)
    up = cv2.resize(filled, (w, h), interpolation=cv2.INTER_CUBIC)
    a = cv2.GaussianBlur(hole.astype(np.float32) / 255.0, (0, 0), max(1.0, k / 3))[..., None]
    plate = (rgb.astype(np.float32) * (1 - a) + up.astype(np.float32) * a).round().clip(0, 255).astype(np.uint8)
    Image.fromarray(plate, "RGB").save(paths["arka"])
    warn = None
    if cover < MIN_COVER:
        warn = "Fotoğrafta ürünü bulamadım. Ürünün büyük ve net göründüğü bir fotoğrafla yeniden deneyelim."
    elif cover > MAX_COVER:
        warn = "Ürünü arka plandan ayıramadım; fotoğrafın neredeyse tamamı ürün gibi görünüyor. Ürünün etrafında boşluk olan bir fotoğraf deneyelim."
    return {**{k2: str(v) for k2, v in paths.items()}, "size": [w, h], "urun_orani": round(cover, 3), "uyari": warn}


def separate(data_dir: Path, images: list[Path], out_dir: Path) -> list[dict]:
    import numpy as np
    from PIL import Image
    if not installed(data_dir):
        raise CutoutError("kurulu değil")
    py = engine_python(data_dir)
    with tempfile.TemporaryDirectory() as td:
        items, stems = [], []
        for i, img in enumerate(images):
            src = Path(td) / f"girdi{i}.png"  # döndürme uygulanmış, HEIC çevrilmiş kopya: işçi ile çekirdek aynı pikseli görür
            _open_rgb(img).save(src)
            items.append({"image": str(src), "mask": str(Path(td) / f"maske{i}.png")})
            stems.append(img.stem)
        rq, rs = Path(td) / "req.json", Path(td) / "res.json"
        rq.write_text(json.dumps({"model": str(model_path(data_dir)), "items": items}, ensure_ascii=False), encoding="utf-8")
        try:
            r = subprocess.run([str(py), "-I", str(WORKER), str(rq), str(rs)], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=WORKER_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise CutoutError(f"ürün ayırma {WORKER_TIMEOUT // 60} dakikada bitmedi: daha az fotoğrafla çalıştırın")
        if r.returncode != 0 or not rs.exists():
            raise CutoutError(f"ürün ayırma başarısız: {(r.stderr or r.stdout)[-1500:]}")
        out = []
        for it, stem in zip(items, stems):
            rgb = np.asarray(Image.open(it["image"]).convert("RGB"))
            mask = np.asarray(Image.open(it["mask"]).convert("L"))
            out.append({"image": str(images[len(out)]), **build_outputs(rgb, mask, out_dir, stem)})
        return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Yerel ürün ayırma (ücretsiz)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("kur")
    k.add_argument("--data-dir", required=True)
    k.add_argument("--yes", action="store_true")
    s = sub.add_parser("ayir")
    s.add_argument("--data-dir", required=True)
    s.add_argument("--image", action="append", required=True)
    s.add_argument("--out-dir", required=True)
    d = sub.add_parser("durum")
    d.add_argument("--data-dir", required=True)
    a = ap.parse_args()
    dd = Path(a.data_dir)
    if a.cmd == "durum":
        emit({ENGINE: {"installed": installed(dd), "model": MODEL["name"], "license": MODEL["license"]}})
        return
    if a.cmd == "kur":
        if installed(dd):
            emit({"installed": _record(dd), "note": "zaten kurulu"})
            return
        if not a.yes:
            emit({"plan": plan(dd), "note": "Kullanıcıya 'kullaniciya' cümlesiyle sorulur; onaylarsa --yes ile yeniden çalıştırılır."})
            sys.exit(2)
        try:
            emit({"installed": install(dd)})
        except (CutoutError, subprocess.CalledProcessError, OSError) as e:
            emit({"error": str(e)[:500]})
            sys.exit(1)
        return
    if not installed(dd):
        emit({"error": "kurulu değil", "kullaniciya": OFFER, "kur": f"cutout.py kur --data-dir {dd} --yes",
              "alternatif": "kullanıcı indirmek istemezse ücretli arka plan kaldırma (ref-production-recipes; tahmin → onay)"})
        sys.exit(5)
    try:
        emit({"items": separate(dd, [Path(x) for x in a.image], Path(a.out_dir))})
    except CutoutError as e:
        emit({"error": str(e)[:1500]})
        sys.exit(1)


if __name__ == "__main__":
    main()
