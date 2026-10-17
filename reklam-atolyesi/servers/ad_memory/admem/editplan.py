"""Kurgu planı (`edit_plan.json`) şeması ve doğrulaması (spec 5.2, 5.6, 5.12, 10).

Tek doğrulama kaynağı: `edit_plan_validate` aracı, `scripts/compose/validate_plan.py` ve render script'i bu modülü kullanır.
Geçersiz plan render edilmez; `draft` plan final render edilemez.
"""
from __future__ import annotations

import math
import re
from typing import Any

import jsonschema

ROLES = ["hook", "context", "reveal", "product", "process", "demo", "proof", "offer", "endcard"]
AUDIO_MODES = ["original", "original_clean", "user_vo", "generated", "none"]
FORMATS = ["9x16", "4x5", "1x1"]
SOURCE_KINDS = ["footage", "ai_clip", "ai_image", "still", "graphic"]
BEAT_LOCKS = ["none", "downbeat", "beat", "onset"]

COMPONENTS = {
    "text": ["TextReveal", "KineticWords", "SoftType", "LowerThird", "PriceTag", "CaptionTrack"],
    "transition": ["Crossfade", "DipToColor", "LightLeak", "WhipPan", "MaskReveal", "MatchZoom", "SlideBlur", "FilmBurn"],
    "light": ["LightSheen", "SoftGlow", "Bokeh", "Particles", "GradeOverlay", "LensFlareSoft"],
    "camera": ["KenBurns", "Parallax25D", "FakeRackFocus", "HandheldDrift"],
    "product": ["BehindSubjectText", "Spotlight", "OutlineGlow", "StillTurn"],
    "proof": ["ReviewCard", "StarRating", "EndCard", "CTAPulse"],
    "signature": ["LightRays", "ParticleSwirl", "HeatShimmer"],
    "helper": ["SafeZoneGuide", "BeatMarker"],
}
ALL_COMPONENTS = sorted({c for v in COMPONENTS.values() for c in v})
SIGNATURE = set(COMPONENTS["signature"])
ATMOSPHERE = {"SoftGlow", "Bokeh", "Particles", "LensFlareSoft"}
PREVIEW_ONLY = set(COMPONENTS["helper"])
TRANSITION_TYPES = ["cut", "crossfade"] + [c[0].lower() + c[1:] for c in COMPONENTS["transition"] if c != "Crossfade"]
FORBIDDEN_PATH_PARTS = ("/competitors/", "/competitive/")

_source = {
    "type": "object",
    "required": ["kind"],
    "properties": {
        "kind": {"enum": SOURCE_KINDS},
        "asset": {"type": "string"},
        "path": {"type": "string"},
        "in_s": {"type": "number", "minimum": 0},
        "out_s": {"type": "number", "minimum": 0},
        "generation_id": {"type": "integer"},
        "real_twin": {"type": "string"},
    },
}
_layer = {
    "type": "object",
    "required": ["type"],
    "properties": {
        "type": {"enum": ["video", "image", "text", "component", "graphic", "audio"]},
        "source": _source,
        "component": {"enum": ALL_COMPONENTS},
        "preset": {"type": "string"},
        "props": {"type": "object"},
        "text": {"type": "string"},
        "anchor": {"type": "string"},
        "start_s": {"type": "number", "minimum": 0},
        "dur_s": {"type": "number", "exclusiveMinimum": 0},
        "camera": {"type": "object"},
        "review_id": {"type": "integer"},
        "speaking_person": {"type": "boolean"},
    },
}
_scene = {
    "type": "object",
    "required": ["id", "role", "start_s", "dur_s", "audio", "layers"],
    "properties": {
        "id": {"type": "string", "pattern": r"^[A-Za-z0-9_-]+$"},
        "role": {"enum": ROLES},
        "start_s": {"type": "number", "minimum": 0},
        "dur_s": {"type": "number", "exclusiveMinimum": 0},
        "beat_lock": {"enum": BEAT_LOCKS},
        "audio": {
            "type": "object",
            "required": ["mode"],
            "properties": {"mode": {"enum": AUDIO_MODES}, "decision_id": {"type": ["string", "integer", "null"]},
                           "user_vo_asset": {"type": "string"}, "gain_db": {"type": "number"}},
        },
        "layers": {"type": "array", "items": _layer},
        "transition_out": {"type": "object", "properties": {"type": {"type": "string"}, "dur_s": {"type": "number", "minimum": 0}}},
        "audio_cues": {"type": "array", "items": {"type": "object", "required": ["at_s"],
                                                   "properties": {"sfx": {"type": "string"}, "at_s": {"type": "number", "minimum": 0}}}},
        "speaking_person": {"type": "boolean"},
    },
}
SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "reklam-atolyesi edit_plan",
    "type": "object",
    "required": ["campaign", "cycle_id", "concept", "hook", "format", "purpose", "status", "version", "duration_s", "fps", "style", "scenes"],
    "properties": {
        "campaign": {"type": "string"},
        "cycle_id": {"type": ["string", "integer"]},
        "concept": {"type": "string"},
        "hook": {"type": "string"},
        "format": {"enum": FORMATS},
        "purpose": {"enum": ["style_preview", "production"]},
        "status": {"enum": ["draft", "ready"]},
        "version": {"type": "integer", "minimum": 1},
        "style_snapshot_sha256": {"type": ["string", "null"]},
        "duration_s": {"type": "number", "exclusiveMinimum": 0},
        "fps": {"enum": [30, 60]},
        "style": {"type": "string"},
        "seed": {"type": "integer"},
        "music": {"type": ["object", "null"], "properties": {"asset": {"type": "string"}, "offset_s": {"type": "number"}, "beats": {"type": "string"}, "gain_db": {"type": "number"}}},
        "vo": {"type": ["object", "null"], "properties": {"asset": {"type": "string"}, "words": {"type": "string"}}},
        "captions": {"type": ["object", "null"], "properties": {"on": {"type": "boolean"}, "preset": {"type": "string"}}},
        # videoda görünen açıklama metni (AI açıklaması, yasal not); 9:16'da alt %40 boş kalır (checks.py safe; ref-legal-tr-meta §7)
        "disclaimer": {"type": ["object", "null"], "properties": {"on": {"type": "boolean"}, "text": {"type": "string"},
                                                                   "reason": {"enum": ["ai", "legal", "price", "other"]}}},
        "scenes": {"type": "array", "minItems": 1, "items": _scene},
        "missing": {"type": "array", "items": {"type": "string"}},
        "provenance": {"type": "object", "properties": {"ai_share": {"type": "number", "minimum": 0, "maximum": 1},
                                                        "ai_layers": {"type": "array"}}},
        "variant_of": {"type": ["integer", "null"]},
        "patch_ops": {"type": "array"},
    },
}

DEFAULT_EFFECTS = {"signatureMax": 1, "transitionTypesMax": 2, "persistentAtmosphere": False}


def _norm_path(p: str) -> str:
    return "/" + p.replace("\\", "/").strip("/").lower() + "/"


def _layer_span(scene: dict, layer: dict) -> tuple[float, float]:
    st = scene["start_s"] + float(layer.get("start_s", 0.0))
    du = float(layer.get("dur_s", scene["dur_s"] - float(layer.get("start_s", 0.0))))
    return st, du


def validate(plan: dict, *, style: dict | None = None, beats: list[float] | None = None,
             asset_index: dict[str, dict] | None = None) -> dict[str, Any]:
    """Planı doğrular. style: planın bağlandığı stil kopyası (efekt bütçesi için); beats: vuruş zamanları (sn);
    asset_index: asset anahtarı → {kind, speaking_person, path}. Dönüş: {valid, errors, warnings, computed}."""
    errors: list[str] = []
    warnings: list[str] = []
    v = jsonschema.Draft202012Validator(SCHEMA)
    for e in sorted(v.iter_errors(plan), key=lambda e: list(e.path)):
        loc = "/".join(str(x) for x in e.path) or "(kök)"
        errors.append(f"şema: {loc}: {e.message}")
    if errors:
        return {"valid": False, "errors": errors, "warnings": warnings, "computed": {}}

    fps = plan["fps"]
    frame = 1.0 / fps
    scenes = plan["scenes"]
    effects = dict(DEFAULT_EFFECTS)
    if style and isinstance(style.get("effects"), dict):
        effects.update({k: v for k, v in style["effects"].items() if v is not None})

    # Zamanlama: sahneler sıralı ve bitişik; toplam süre ≈ duration_s
    t = 0.0
    ids = set()
    for i, s in enumerate(scenes):
        if s["id"] in ids:
            errors.append(f"sahne {s['id']}: kimlik tekrar ediyor")
        ids.add(s["id"])
        if abs(s["start_s"] - t) > frame + 1e-6:
            errors.append(f"sahne {s['id']}: başlangıç {s['start_s']:.3f} sn, beklenen {t:.3f} sn (sahneler bitişik olmalı)")
        t = s["start_s"] + s["dur_s"]
    if abs(t - plan["duration_s"]) > frame + 1e-6:
        errors.append(f"toplam süre {t:.3f} sn ≠ duration_s {plan['duration_s']:.3f} sn")
    if scenes[0]["role"] != "hook" and plan["purpose"] == "production":
        warnings.append("ilk sahnenin rolü 'hook' değil")

    # Kaynak kuralları
    ai_dur = 0.0
    ai_layers: list[str] = []
    video_dur = 0.0
    for s in scenes:
        for li, layer in enumerate(s["layers"]):
            src = layer.get("source") or {}
            for key in ("path", "asset"):
                val = src.get(key) or ""
                if any(part in _norm_path(val) for part in FORBIDDEN_PATH_PARTS):
                    errors.append(f"sahne {s['id']} katman {li}: kaynak rakip analizi klasörünü gösteriyor ({val}); rakip varlığı üretime girmez (4.5, 5.2)")
            props = layer.get("props") or {}
            for pv in props.values():
                if isinstance(pv, str) and any(part in _norm_path(pv) for part in FORBIDDEN_PATH_PARTS):
                    errors.append(f"sahne {s['id']} katman {li}: bileşen prop'u rakip klasörünü gösteriyor ({pv})")
            if layer["type"] in ("video", "image") and not src:
                errors.append(f"sahne {s['id']} katman {li}: görüntü katmanının kaynağı yok")
            if src.get("kind") == "footage":
                if "in_s" in src and "out_s" in src and src["out_s"] <= src["in_s"]:
                    errors.append(f"sahne {s['id']} katman {li}: out_s ≤ in_s")
            if layer["type"] in ("video", "image"):
                st, du = _layer_span(s, layer)
                video_dur += du
                if src.get("kind") in ("ai_clip", "ai_image"):
                    ai_dur += du
                    ai_layers.append(f"{s['id']}:{li}")
                    if src.get("kind") == "ai_clip" and not src.get("real_twin") and plan["status"] == "ready":
                        warnings.append(f"sahne {s['id']} katman {li}: AI klibin gerçek çekimli eşi (real_twin) belirtilmemiş (5.3, 5.16)")
            comp = layer.get("component")
            if comp == "ReviewCard" and not layer.get("review_id"):
                errors.append(f"sahne {s['id']} katman {li}: ReviewCard izin kaydı (review_id) olmadan kullanılamaz (bölüm 10)")
            if comp in PREVIEW_ONLY and plan["purpose"] == "production" and plan["status"] == "ready":
                errors.append(f"sahne {s['id']}: {comp} yalnızca önizleme bileşenidir; hazır üretim planında olamaz")
            if comp in SIGNATURE and s["role"] not in ("reveal", "endcard"):
                errors.append(f"sahne {s['id']}: imza anı bileşeni {comp} yalnızca reveal ve son kartta kullanılabilir (5.12)")
            if layer["type"] == "text" or comp in ("TextReveal", "KineticWords", "SoftType", "LowerThird", "PriceTag"):
                st, du = _layer_span(s, layer)
                if du < 1.5:
                    warnings.append(f"sahne {s['id']} katman {li}: yazı {du:.2f} sn ekranda; okunurluk için ≥ 1,5 sn önerilir (bölüm 10)")

    # Ses kuralları
    for s in scenes:
        mode = s["audio"]["mode"]
        speaking = bool(s.get("speaking_person")) or any(bool(l.get("speaking_person")) for l in s["layers"])
        if asset_index:
            for l in s["layers"]:
                a = (l.get("source") or {}).get("asset")
                if a and asset_index.get(a, {}).get("speaking_person"):
                    speaking = True
        if speaking and mode not in ("original", "original_clean"):
            errors.append(f"sahne {s['id']}: kamerada konuşan kişi var; ses yalnızca 'original' ya da 'original_clean' olabilir (dudak senkronu, 5.2)")
        if plan["purpose"] == "style_preview" and mode != "none":
            errors.append(f"sahne {s['id']}: stil önizlemesi yalnızca audio.mode=none ile gösterilir (5.2)")
        if plan["status"] == "ready" and plan["purpose"] == "production" and not s["audio"].get("decision_id"):
            errors.append(f"sahne {s['id']}: hazır üretim planında sahne başına kullanıcı ses kararı (decision_id) zorunlu (5.2, 5.13)")
        if mode == "user_vo" and not (s["audio"].get("user_vo_asset") or (plan.get("vo") or {}).get("asset")):
            errors.append(f"sahne {s['id']}: user_vo seçilmiş ama kullanıcı kaydı belirtilmemiş")

    # Efekt bütçesi (5.6)
    sig = sum(1 for s in scenes for l in s["layers"] if l.get("component") in SIGNATURE)
    sig_allowed = int(effects.get("signatureMax", 1)) * max(1, math.ceil(plan["duration_s"] / 15.0 - 1e-9))
    if sig > sig_allowed:
        errors.append(f"efekt bütçesi: {sig} imza anı var, izin verilen {sig_allowed} (stil: {effects.get('signatureMax')} / 15 sn)")
    ttypes = set()
    for s in scenes[:-1]:
        tt = (s.get("transition_out") or {}).get("type", "cut")
        if tt and tt != "cut":
            ttypes.add(tt)
    for s in scenes:
        for l in s["layers"]:
            if l.get("component") in COMPONENTS["transition"] and l.get("component") != "Crossfade":
                ttypes.add(l["component"][0].lower() + l["component"][1:])
            elif l.get("component") == "Crossfade":
                ttypes.add("crossfade")
    if len(ttypes) > int(effects.get("transitionTypesMax", 2)):
        errors.append(f"efekt bütçesi: {len(ttypes)} farklı geçiş türü ({', '.join(sorted(ttypes))}), izin verilen {effects.get('transitionTypesMax')}")
    if not effects.get("persistentAtmosphere", False):
        for s in scenes:
            for l in s["layers"]:
                if l.get("component") in ATMOSPHERE:
                    st, du = _layer_span(s, l)
                    if du >= s["dur_s"] - frame:
                        errors.append(f"efekt bütçesi: sahne {s['id']} boyunca süren atmosfer efekti ({l['component']}) — stil buna izin vermiyor")

    # Vuruş kilidi (5.2): kilitli anlar en yakın vuruşa ≤ 3 kare
    if beats is not None and plan["purpose"] == "production":
        for s in scenes:
            bl = s.get("beat_lock", "none")
            if bl and bl != "none" and beats:
                nearest = min(beats, key=lambda b: abs(b - s["start_s"]))
                off = abs(nearest - s["start_s"]) * fps
                if off > 3 + 1e-6:
                    errors.append(f"sahne {s['id']}: beat_lock={bl} ama en yakın vuruşa {off:.1f} kare uzak (≤ 3 kare)")

    # Hazır plan koşulları
    if plan["status"] == "ready":
        if plan["purpose"] == "production" and not plan.get("style_snapshot_sha256"):
            errors.append("hazır üretim planı style_snapshot_sha256 taşımalı (5.2)")
        if plan.get("missing"):
            errors.append("hazır planda eksik varlık listesi olamaz: " + ", ".join(plan["missing"]))
        for s in scenes:
            for li, l in enumerate(s["layers"]):
                src = l.get("source") or {}
                if l["type"] in ("video", "image") and not (src.get("asset") or src.get("path")):
                    errors.append(f"sahne {s['id']} katman {li}: hazır planda varlık bağlı değil")
        if (plan.get("captions") or {}).get("on") and not ((plan.get("vo") or {}).get("words")
                                                         or any(s["audio"]["mode"] in ("original", "original_clean", "user_vo") for s in scenes)):
            warnings.append("altyazı açık ama kelime zamanları (vo.words) yok; VO yoksa ana mesaj ekran yazısıyla verilir (5.14)")

    ai_share = round(ai_dur / video_dur, 4) if video_dur > 0 else 0.0
    declared = (plan.get("provenance") or {}).get("ai_share")
    if declared is not None and abs(float(declared) - ai_share) > 0.01:
        errors.append(f"provenance.ai_share {declared} ≠ hesaplanan {ai_share} (katman kaynaklarından; ilke 4)")
    return {"valid": not errors, "errors": errors, "warnings": warnings,
            "computed": {"ai_share": ai_share, "ai_layers": ai_layers, "duration_s": round(t, 4),
                         "signature_count": sig, "transition_types": sorted(ttypes)}}


def apply_patch(plan: dict, ops: list[dict]) -> dict:
    """Varyasyon yaması (5.2, 5.16): basit JSON-pointer benzeri işlemler.
    op: {op: 'set'|'remove'|'trim'|'reformat'|'replace_hook'|'vo', path?, value?, ...}"""
    import copy
    p = copy.deepcopy(plan)
    for op in ops:
        kind = op.get("op")
        if kind == "set":
            _set_path(p, op["path"], op.get("value"))
        elif kind == "remove":
            _remove_path(p, op["path"])
        elif kind == "reformat":
            if op["format"] not in FORMATS:
                raise ValueError(f"geçersiz format: {op['format']}")
            p["format"] = op["format"]
        elif kind == "trim":
            target = float(op["duration_s"])
            keep_roles = op.get("keep_roles") or ["hook", "reveal", "endcard"]
            kept = [s for s in p["scenes"] if s["role"] in keep_roles] or p["scenes"][:1]
            total = sum(s["dur_s"] for s in kept)
            scale = target / total if total > 0 else 1.0
            t = 0.0
            fps = p.get("fps", 30)
            for s in kept:
                d = round(s["dur_s"] * scale * fps) / fps
                s["start_s"] = round(t, 6)
                s["dur_s"] = d
                t += d
            if kept:
                kept[-1]["dur_s"] = round(target - kept[-1]["start_s"], 6)
            p["scenes"] = kept
            p["duration_s"] = target
        elif kind == "replace_hook":
            hook_scene = next((s for s in p["scenes"] if s["role"] == "hook"), None)
            if hook_scene is None:
                raise ValueError("planda hook sahnesi yok")
            hook_scene["layers"] = op["layers"]
            p["hook"] = op.get("hook_code", p["hook"])
        elif kind == "vo":
            if op.get("on"):
                p["vo"] = op.get("vo")
            else:
                p["vo"] = None
                for s in p["scenes"]:
                    if s["audio"]["mode"] == "generated" and op.get("scene_mode"):
                        s["audio"]["mode"] = op["scene_mode"]
        else:
            raise ValueError(f"bilinmeyen yama işlemi: {kind}")
    p["version"] = int(plan.get("version", 1)) + 1
    p["patch_ops"] = list(plan.get("patch_ops") or []) + ops
    return p


def _split(path: str) -> list[str]:
    return [x for x in re.split(r"[/.]", path.strip("/")) if x]


def _walk(obj: Any, parts: list[str]) -> Any:
    for part in parts:
        obj = obj[int(part)] if isinstance(obj, list) else obj[part]
    return obj


def _set_path(obj: dict, path: str, value: Any) -> None:
    parts = _split(path)
    parent = _walk(obj, parts[:-1])
    key = parts[-1]
    if isinstance(parent, list):
        parent[int(key)] = value
    else:
        parent[key] = value


def _remove_path(obj: dict, path: str) -> None:
    parts = _split(path)
    parent = _walk(obj, parts[:-1])
    key = parts[-1]
    if isinstance(parent, list):
        parent.pop(int(key))
    else:
        parent.pop(key, None)
