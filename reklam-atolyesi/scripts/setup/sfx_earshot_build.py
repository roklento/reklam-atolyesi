"""Earshot ses bankasını plugin'e üretir (2.6.0, geliştirici aracı; müşteri kurulumunda çalışmaz).

Earshot (https://github.com/Leonxlnx/earshot, MIT) ses efektlerini kayıt kullanmadan, kodla (numpy/scipy/numba DSP) üretir.
Bu betik bankadaki her sesi kendi tohumunda (yayımlanan son hali) üretir, OGG Vorbis'e çevirir ve
vendor-skills/sfx-earshot/ altına dosya başına kaynak kaydıyla (ATTRIBUTION.md: kimlik, tohum, denetim, SHA-256) yazar.

Earshot'un kendi sanal ortamında çalışır; çekirdek ortama torch girmez. Ses üretimi torch istemez:
  python -m venv .earshot && .earshot/bin/pip install numpy scipy numba soundfile soxr pyloudnorm
  git clone https://github.com/Leonxlnx/earshot && git -C earshot checkout <EARSHOT_COMMIT>
  .earshot/bin/pip install --no-deps -e earshot
  .earshot/bin/python scripts/setup/sfx_earshot_build.py --plugin-root .
Çıktı deterministiktir (aynı commit + tohum = aynı WAV); OGG kodlaması ffmpeg sürümüne göre bayt düzeyinde değişebilir,
bu yüzden SHA-256 her üretimde yeniden yazılır.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

EARSHOT_COMMIT = "591fa3e028032e6dce56620a20e932e35667e8d8"
EARSHOT_URL = "https://github.com/Leonxlnx/earshot"
HEAD = f"""# Kaynak kaydı — Earshot ses bankası (kodla üretilmiş)

Kaynak: {EARSHOT_URL}, commit `{EARSHOT_COMMIT}` (sürüm 0.4.0, banka `{{bank}}`). Earshot kodu MIT (`LICENSE`).
Sesler kayıt içermez: her biri Earshot'un DSP tarifinden kendi tohumunda üretildi (`scripts/setup/sfx_earshot_build.py`),
48 kHz'den OGG Vorbis'e (q6) çevrildi. `fit/` altındaki 15 ses, Earshot'un CC0 1.0 Freesound kayıtlarından çıkardığı
tariflerden üretildi; kaynak kayıtlar ve kaydedenler `CREDITS_FIT.md`'de (CC0: atıf zorunlu değil).
Earshot'un 0.4 tarifleri özel lisanslı örnek seslerin ölçümlerine göre ayarlanmıştır; o örnekler pakette ve burada yoktur.

`scripts/audio/sfx_library.py` yalnızca bu tabloda satırı olan ve SHA-256'sı tutan dosyaları listeler. Earshot'un kendi
denetiminde uyarı alan sesler (`Denetim` sütunu "uyarı") varsayılan aramada **listelenmez**; `--include-flagged` ile görünür.
Seslerin hiçbiri yayın öncesi insan kulağıyla dinlenmeden kullanılmaz (sound skill'indeki telefon testi kuralı).
"""


def rel_path(sound_id: str) -> str:
    """earshot kimliği → dosya yolu: whoosh_big/cape → whoosh_big/cape.ogg, fit/key.space/thock_space → fit/key-space/thock_space.ogg"""
    return sound_id.replace(".", "-") + ".ogg"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plugin-root", required=True)
    a = ap.parse_args()
    from earshot.forge import bank, sfx  # earshot ortamında

    dst = Path(a.plugin_root) / "vendor-skills" / "sfx-earshot"
    for d in dst.iterdir() if dst.exists() else []:
        if d.is_dir():
            shutil.rmtree(d)
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for r in bank.list_sounds():
            sid = r["id"]
            wav = Path(tmp) / "x.wav"
            meta = sfx.sfx_render(sid, str(wav))["meta"]
            out = dst / rel_path(sid)
            out.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav), "-map_metadata", "-1", "-c:a", "libvorbis",
                            "-q:a", "6", str(out)], check=True)
            chk = meta.get("checks") or {}
            warn = "; ".join(w.get("msg", "") for w in chk.get("warnings", []))
            rows.append({"file": rel_path(sid), "id": sid, "seed": meta.get("seed"), "type": r["type"],
                         "dur_s": round(meta["dur_s"], 3), "ok": bool(chk.get("ok")), "warn": warn,
                         "sha": hashlib.sha256(out.read_bytes()).hexdigest()})
    lic = {"forge": "MIT (Earshot, kodla üretildi)", "fit": "MIT (Earshot) + kaynak kayıt CC0 1.0"}
    lines = ["| Dosya | Lisans | Earshot kimliği (tohum) | Denetim | SHA-256 |", "|---|---|---|---|---|"]
    for x in rows:
        den = "temiz" if x["ok"] else "uyarı: " + x["warn"].replace("|", "/")
        lines.append(f"| `{x['file']}` | {lic.get(x['type'], 'MIT (Earshot)')} | `{x['id']}` ({x['seed']}) | {den} | `{x['sha']}` |")
    (dst / "ATTRIBUTION.md").write_text(HEAD.format(bank=bank.VERSION).rstrip() + "\n\n## Dosyalar\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    n_ok = sum(x["ok"] for x in rows)
    print(json.dumps({"sounds": len(rows), "clean": n_ok, "flagged": len(rows) - n_ok, "bank": bank.VERSION}, ensure_ascii=False))


if __name__ == "__main__":
    main()
