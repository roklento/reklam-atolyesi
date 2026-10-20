"""Yerel ses motoru kurulumu (1.4.8). Her motor kendi sanal ortamına kurulur: DD/.tts/<motor>/.venv (çekirdek ortama torch girmez).
Model dosyaları DD/.tts/hf altına iner. İndirme boyutu önce gösterilir; --yes olmadan hiçbir şey indirilmez.

  ema      ema-lightning (Apache-2.0) + CPU torch            ≈ 0,6 GB ortam + 34 MB model; her bilgisayarda çalışır
  voxcpm   voxcpm (Apache-2.0) + torch (NVIDIA varsa CUDA)  ≈ 4–5 GB ortam + ~5 GB model; NVIDIA GPU önerilir (CPU çok yavaş)
  whisper  faster-whisper (MIT) + Whisper large-v3-turbo (MIT, CTranslate2 biçimi)  ≈ 0,3 GB ortam + 1,6 GB model; torch yok,
           CPU'da int8 (yazıya dökme: kullanıcı kaydı, kamerada konuşma, yerel seslendirmenin okunuş denetimi)

Kullanım: tts_setup.py --data-dir DD --engine ema|voxcpm|whisper [--device auto|cpu|cuda] [--yes]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
from pathlib import Path

PINS = {
    # model sürümleri sabit (sınanan sürümler, 20-21.10.2026); çalışırken ağ kapalı, yalnızca kurulumda inen sürüm kullanılır
    "ema": {"packages": ["ema-lightning==1.1.2"], "model": "canberkkkkkk/ema-lightning", "revision": "7a6ba1ad216bb2f1da9863f80ac8770a6a807632",
            "env_gb": 0.6, "model_gb": 0.04},
    "voxcpm": {"packages": ["voxcpm==2.0.3", "soundfile"], "model": "openbmb/VoxCPM2", "revision": "32279effe8c19989596f05d353d1447f51d9e915",
               "env_gb": 4.5, "model_gb": 5.0},
    # faster-whisper'ın "large-v3-turbo" kısaltması mobiuslabsgmbh/… adresine gider; o depo bu ada taşındı (HF API, 21.10.2026).
    # Sürüm sabit: model dosyası değişirse kelime zamanları ve testler değişmesin. Bağımlılıklar da sabit: av 19.0.0
    # av.open(metadata_errors=) parametresini kaldırdı, faster-whisper 1.2.1 onunla ses açamıyor (21.10.2026'da ölçüldü).
    "whisper": {"packages": ["faster-whisper==1.2.1", "av==18.1.0", "ctranslate2==4.8.3", "onnxruntime==1.31.0", "tokenizers==0.23.3",
                             "huggingface-hub==2.2.0"], "model": "dropbox-dash/faster-whisper-large-v3-turbo",
                "revision": "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf", "env_gb": 0.3, "model_gb": 1.6, "torch": False},
}
TORCH_INDEX = {"cpu": "https://download.pytorch.org/whl/cpu", "cuda": "https://download.pytorch.org/whl/cu128"}


def has_nvidia() -> bool:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return False
    r = subprocess.run([exe, "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True)
    return r.returncode == 0 and bool(r.stdout.strip())


DEEPEST_REL = 140  # motor ortamındaki en uzun dosya yolu site-packages altında ~134 karakter (voxcpm 2.0.3 + bağımlılıkları, ölçüldü)
IMPORT_CHECK = {"ema": "import ema_lightning, normalizer_tr", "voxcpm": "import voxcpm, soundfile, torch",
                "whisper": "import faster_whisper, ctranslate2, av"}


def long_paths_enabled() -> bool:
    if sys.platform != "win32":
        return True
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as k:
            return winreg.QueryValueEx(k, "LongPathsEnabled")[0] == 1
    except OSError:
        return False


HF_FILE_MAX = 32  # model deposundaki en uzun dosya adı payı (preprocessor_config.json = 24)


def hf_snapshot_len(hf: Path, model: str) -> int:
    """Model önbelleğindeki en uzun dosya yolu: hf/hub/models--<kurum>--<ad>/snapshots/<40 karakter sürüm>/<dosya>."""
    return len(str(hf / "hub" / f"models--{model.replace('/', '--')}" / "snapshots")) + 1 + 40 + 1 + HF_FILE_MAX


def path_budget(venv: Path, hf: Path | None = None, model: str | None = None) -> int:
    """Windows'ta uzun yol kapalıysa 260 karakter sınırına kalan pay; negatifse paket ya da model dosyaları eksik yazılır
    (model önbelleği için ölçüldü: indirme yarıda 'yol bulunamadı' ile kesiliyordu)."""
    if long_paths_enabled():
        return 10_000
    need = len(str(venv / "Lib" / "site-packages")) + 1 + DEEPEST_REL
    if hf is not None and model:
        need = max(need, hf_snapshot_len(hf, model))
    return 259 - need


def run(cmd: list[str], env: dict | None = None) -> None:
    import os
    r = subprocess.run(cmd, env={**os.environ, **(env or {})})
    if r.returncode != 0:
        raise SystemExit(f"komut başarısız ({r.returncode}): {' '.join(cmd)[:300]}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Türkçe karakterler Windows konsol kod sayfasında bozulmasın
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--engine", required=True, choices=list(PINS))
    ap.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    dd = Path(a.data_dir)
    pin = PINS[a.engine]
    device = ("cuda" if has_nvidia() else "cpu") if a.device == "auto" else a.device
    if a.engine in ("ema", "whisper"):
        device = "cpu"  # EMA CPU'da yeterince hızlı; Whisper CPU int8 (CUDA için ayrı cuBLAS/cuDNN kütüphaneleri gerekir, kurulmaz)
    with_torch = pin.get("torch", True)
    base = dd / ".tts" / a.engine
    plan = {"engine": a.engine, "device": device, "target": str(base), "packages": pin["packages"], "model": pin["model"],
            "revision": pin.get("revision"),
            "download_estimate_gb": round(pin["env_gb"] + pin["model_gb"] + (2.5 if device == "cuda" and with_torch else 0), 1)}
    if a.engine == "voxcpm" and device == "cpu":
        plan["warning"] = "NVIDIA GPU bulunamadı: VoxCPM2 CPU'da çok yavaş çalışır; ses kütüphanesi yerine EMA varsayılan sesi önerilir"
    if path_budget(base / ".venv", (dd / ".tts" / "hf").resolve(), pin["model"]) < 0:
        print(json.dumps({"error": "veri klasörünün yolu çok uzun: Windows 260 karakter sınırı (uzun yol desteği kapalı) motor dosyalarının "
                                   "eksik kurulmasına yol açar", "target": str(base),
                          "fix": "veri klasörünü kısa bir yola alın (ör. C:\\ReklamAtolyesi\\veri) ya da Windows'ta uzun yol desteğini "
                                 "yöneticinin açması gerekir"}, ensure_ascii=False))
        sys.exit(3)
    if not a.yes:
        print(json.dumps({"plan": plan, "note": "Onaylamak için --yes ile yeniden çalıştırın."}, ensure_ascii=False))
        sys.exit(2)
    uv = shutil.which("uv")
    if not uv:
        raise SystemExit("uv bulunamadı (kurulum gereksinimi)")
    base.mkdir(parents=True, exist_ok=True)
    venv = base / ".venv"
    if not venv.exists():
        run([uv, "venv", "-q", "--python", "3.12", str(venv)])
    py = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if with_torch:
        run([uv, "pip", "install", "-q", "--python", str(py), "torch", "torchaudio", "--index-url", TORCH_INDEX[device]])
        run([uv, "pip", "install", "-q", "--python", str(py), *pin["packages"], "--extra-index-url", TORCH_INDEX[device],
             "--index-strategy", "unsafe-best-match"])
    else:
        run([uv, "pip", "install", "-q", "--python", str(py), *pin["packages"]])
    run([str(py), "-I", "-c", IMPORT_CHECK[a.engine]])  # kurulum eksikse burada durur (kayıt yazılmaz)
    hf = dd / ".tts" / "hf"
    run([str(py), "-c", f"from huggingface_hub import snapshot_download; snapshot_download({pin['model']!r}, revision={pin.get('revision')!r})"],
        env={"HF_HOME": str(hf), "HF_HUB_DISABLE_TELEMETRY": "1", "HF_HUB_DISABLE_SYMLINKS_WARNING": "1"})
    if pin.get("revision"):  # sürümle indirilen modelde önbellek 'main' göstericisi yazılmaz; adla yükleyen motor (EMA, VoxCPM) çevrimdışı bulsun
        ref = hf / "hub" / f"models--{pin['model'].replace('/', '--')}" / "refs" / "main"
        ref.parent.mkdir(parents=True, exist_ok=True)
        ref.write_text(pin["revision"], encoding="utf-8")
    rec_path = dd / ".tts" / "engines.json"
    rec = json.loads(rec_path.read_text(encoding="utf-8")) if rec_path.exists() else {}
    rec[a.engine] = {**plan, "installed_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"installed": rec[a.engine]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
