"""Sahne önbelleği anahtarı (spec 5.21).

Anahtar: çözülmüş sahne tanımı, kaynak dosya hash'leri, stil kopyası, font/LUT hash'leri, bileşen kodu, kilit dosyasındaki render
sürümleri, format, fps, ölçek/kalite, tohum ve sahne zamanlaması; global zamana bağlı animasyonun başlangıç karesi ve komşu geçiş
girdileri; sahneyi etkileyen ses/beat değişikliği. Yalnızca bitmiş ve hash'i doğrulanmış dosya önbellekten kullanılır.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import PLUGIN_ROOT, sha256_file  # noqa: E402

COMPONENTS_DIR = PLUGIN_ROOT / "templates" / "remotion" / "src"


def tree_hash(root: Path, suffixes=(".ts", ".tsx", ".json")) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix in suffixes:
            h.update(p.relative_to(root).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def lock_versions(node_dir: Path | None) -> dict:
    if not node_dir:
        return {}
    lock = node_dir / "package-lock.json"
    if not lock.exists():
        return {}
    data = json.loads(lock.read_text(encoding="utf-8"))
    pk = data.get("packages", {})
    return {k.replace("node_modules/", ""): v.get("version") for k, v in pk.items()
            if k.startswith("node_modules/") and ("remotion" in k or k.endswith("/react") or k.endswith("/three") or k.endswith("/zod"))}


def scene_key(plan: dict, index: int, *, source_hashes: dict[str, str], style_sha: str | None, quality: str, scale: float,
              font_hashes: dict[str, str] | None = None, lut_sha: str | None = None, component_sha: str | None = None,
              render_versions: dict | None = None, audio_sha: str | None = None, beats_sha: str | None = None) -> str:
    scenes = plan["scenes"]
    s = scenes[index]
    prev_t = scenes[index - 1].get("transition_out") if index > 0 else None
    nxt = scenes[index + 1] if index + 1 < len(scenes) else None
    payload: dict[str, Any] = {
        "scene": s, "start_frame": round(s["start_s"] * plan["fps"]), "frames": round(s["dur_s"] * plan["fps"]),
        "prev_transition": prev_t, "next_scene_head": {"id": nxt["id"], "layers": nxt["layers"]} if nxt and s.get("transition_out") else None,
        "format": plan["format"], "fps": plan["fps"], "seed": plan.get("seed", 0), "quality": quality, "scale": scale,
        "captions": plan.get("captions"), "sources": {k: source_hashes.get(k) for k in sorted(_assets(s) | _assets(nxt or {}))},
        "style_sha": style_sha, "fonts": font_hashes or {}, "lut": lut_sha, "components": component_sha or tree_hash(COMPONENTS_DIR),
        "render_versions": render_versions or {}, "audio": audio_sha if _audio_affects(s) else None, "beats": beats_sha if s.get("beat_lock") not in (None, "none") else None,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _assets(scene: dict) -> set[str]:
    out = set()
    for l in scene.get("layers", []) or []:
        src = l.get("source") or {}
        if src.get("asset"):
            out.add(src["asset"])
        elif src.get("path"):
            out.add(src["path"])
    return out


def _audio_affects(scene: dict) -> bool:
    return any(l.get("component") in ("CaptionTrack", "BeatMarker") for l in scene.get("layers", []))


def cached(path: Path) -> bool:
    """Bitmiş ve hash'i doğrulanmış dosya: <dosya> + <dosya>.sha256 eşleşmeli; kısmi dosya kullanılmaz."""
    side = path.with_suffix(path.suffix + ".sha256")
    return path.exists() and side.exists() and side.read_text(encoding="utf-8").strip() == sha256_file(path)


def mark_done(path: Path) -> str:
    h = sha256_file(path)
    path.with_suffix(path.suffix + ".sha256").write_text(h, encoding="utf-8")
    return h
