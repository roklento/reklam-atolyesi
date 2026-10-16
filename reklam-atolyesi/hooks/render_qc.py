"""PostToolUse — Bash/PowerShell; yalnızca plugin modunda ve komut scripts/render/ içeriyorsa mini-QC (spec 13.6, 5.15).

Süre, çözünürlük, fps, ses seviyesi (kısa ölçüm) ve kontak sayfası. Eşleşme araç adına göre, dosya yolu süzgeci bu koddadır.
Bulgular Claude'a ek bağlam olarak verilir; tam öz denetimin (5.15) yerine geçmez.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

import plugin_mode as pm

OUT_RE = re.compile(r"--(?:out|output|o)\s+(\"[^\"]+\"|'[^']+'|\S+)")


def probe(ffprobe: str, path: Path) -> dict:
    r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "stream=codec_type,width,height,r_frame_rate,codec_name:format=duration",
                        "-of", "json", str(path)], capture_output=True, text=True, timeout=2)
    return json.loads(r.stdout or "{}")


def loudness(ffmpeg: str, path: Path) -> dict | None:
    r = subprocess.run([ffmpeg, "-hide_banner", "-nostats", "-t", "20", "-i", str(path), "-af", "loudnorm=I=-14:TP=-1:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True, timeout=3)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    return json.loads(m.group(0)) if m else None


def main() -> int:
    data = pm.read_input()
    tool = data.get("tool_name") or ""
    if tool not in ("Bash", "PowerShell"):
        return 0
    cmd = str((data.get("tool_input") or {}).get("command") or "")
    if "scripts/render/" not in cmd.replace("\\", "/"):
        return 0
    try:
        data_dir = pm.data_dir_from_argv()
        if not pm.plugin_mode(data_dir, data.get("session_id")):
            return 0
    except pm.ConfigError:
        return 0
    m = OUT_RE.search(cmd)
    if not m:
        pm.context("PostToolUse", "[reklam-atolyesi mini-QC] render komutunda --out bulunamadı; öz denetim (5.15) elle yapılmalı.")
        return 0
    out = Path(m.group(1).strip("\"'"))
    ffprobe, ffmpeg = shutil.which("ffprobe"), shutil.which("ffmpeg")
    lines = [f"[reklam-atolyesi mini-QC] {out.name}"]
    if not out.exists():
        lines.append("çıktı dosyası yok — render başarısız olabilir.")
    elif not ffprobe:
        lines.append("ffprobe PATH'te bulunamadı; mini-QC atlandı.")
    else:
        info = probe(ffprobe, out)
        v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
        a = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
        dur = float((info.get("format") or {}).get("duration") or 0)
        lines.append(f"süre {dur:.2f} sn · {v.get('width')}×{v.get('height')} · fps {v.get('r_frame_rate')} · video {v.get('codec_name')} · "
                     f"ses {'var (' + a.get('codec_name', '') + ')' if a else 'yok'}")
        if out.suffix.lower() in (".mp4", ".mov") and a and ffmpeg:
            ld = loudness(ffmpeg, out)
            if ld:
                lines.append(f"ses (ilk 20 sn ölçümü): {ld.get('input_i')} LUFS, tepe {ld.get('input_tp')} dBTP (hedef -14 LUFS, ≤ -1 dBTP)")
        sheet = out.with_suffix(".contact.jpg")
        if out.suffix.lower() in (".mp4", ".mov") and ffmpeg and dur > 0:
            fps = max(0.5, min(4.0, 24.0 / dur))
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(out), "-vf",
                            f"fps={fps:.3f},scale=270:-2,tile=6x4", "-frames:v", "1", str(sheet)], timeout=3, capture_output=True)
            if sheet.exists():
                lines.append(f"kontak sayfası: {sheet} — kullanıcıya göstermeden önce bak (5.15).")
    pm.context("PostToolUse", "\n".join(lines))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(0)
