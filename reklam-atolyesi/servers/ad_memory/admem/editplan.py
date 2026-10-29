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
    "text": ["TextReveal", "KineticWords", "SoftType", "LowerThird", "PriceTag", "CaptionTrack", "TextMark"],
    "transition": ["Crossfade", "DipToColor", "LightLeak", "WhipPan", "MaskReveal", "MatchZoom", "SlideBlur", "FilmBurn"],
    "light": ["LightSheen", "SoftGlow", "Bokeh", "Particles", "GradeOverlay", "LensFlareSoft"],
    "camera": ["KenBurns", "Parallax25D", "FakeRackFocus", "HandheldDrift"],
    "product": ["BehindSubjectText", "Spotlight", "OutlineGlow", "StillTurn", "PictureInPicture", "PhoneScreen"],
    "proof": ["ReviewCard", "StarRating", "EndCard", "CTAPulse", "BeforeAfter", "NumberRoll"],
    "signature": ["LightRays", "ParticleSwirl", "HeatShimmer"],
    "helper": ["SafeZoneGuide", "BeatMarker"],
}
ALL_COMPONENTS = sorted({c for v in COMPONENTS.values() for c in v})
SIGNATURE = set(COMPONENTS["signature"])
ATMOSPHERE = {"SoftGlow", "Bokeh", "Particles", "LensFlareSoft"}
PREVIEW_ONLY = set(COMPONENTS["helper"])
TRANSITION_TYPES = ["cut", "crossfade"] + [c[0].lower() + c[1:] for c in COMPONENTS["transition"] if c != "Crossfade"]
# Kaynak alan prop'lar (1.8.0): planda kaynak nesnesi ({kind, asset|path, in_s, out_s, audio?, speaking_person?}); scenes.py ara dosyayı
# "<katman>.<prop>" anahtarıyla üretir. Şablondaki components/index.ts SOURCE_PROPS ile aynı tablo.
SOURCE_PROPS = {"BeforeAfter": ["before", "after"], "PictureInPicture": ["inset"], "PhoneScreen": ["screen"]}
# Önce/sonra ürün kategorisi (ref-legal-tr-meta §8d)
BEFORE_AFTER_CATEGORIES = ["general", "cosmetic", "weight", "health_claim", "skin_whitening"]
TEXT_MARK_MAX_PER_15S = 2
# Rakip analizi ve referans video klasörleri üretime girmez (4.5, 5.2; referans videolar 1.4.6): yalnızca fikir/ritim girdisidir.
FORBIDDEN_PATH_PARTS = ("/competitors/", "/competitive/", "/references/")

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
        "captions": {"type": ["object", "null"], "properties": {"on": {"type": "boolean"},
                                                                 "preset": {"enum": ["plain", "keyword", "keyword_upper", "karaoke"]}}},
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
# Ses efekti yoğunluğu (1.5.0; yerel kural, kurgu ritmi): herhangi 1 saniyede en fazla 2 efekt, aynı efekt 2 saniye içinde tekrar edilmez.
# Stil kitabı (effects.sfxMaxPerSec / effects.sfxRepeatGapS) yalnızca daha sıkı yapabilir.
SFX_MAX_PER_SEC = 2
SFX_REPEAT_GAP_S = 2.0


def sfx_density(scenes: list[dict], effects: dict | None = None) -> list[str]:
    """Plan genelinde efekt yoğunluğu ihlalleri (mutlak zamanla)."""
    eff = effects or {}
    per_sec = min(SFX_MAX_PER_SEC, int(eff.get("sfxMaxPerSec", SFX_MAX_PER_SEC)))
    gap = max(SFX_REPEAT_GAP_S, float(eff.get("sfxRepeatGapS", SFX_REPEAT_GAP_S)))
    cues = sorted((float(s["start_s"]) + float(c["at_s"]), c.get("sfx") or "?", s["id"]) for s in scenes for c in (s.get("audio_cues") or []))
    out = []
    j = 0
    flagged_until = -1.0
    for i, (t, _, sid) in enumerate(cues):
        while cues[j][0] <= t - 1.0 + 1e-9:
            j += 1
        if i - j + 1 > per_sec and t > flagged_until:
            out.append(f"ses efekti yoğunluğu: {cues[j][0]:.2f}–{t:.2f} sn arasında {i - j + 1} efekt (1 saniyede en fazla {per_sec})")
            flagged_until = cues[j][0] + 1.0
    last: dict[str, float] = {}
    for t, name, sid in cues:
        if name == "?":  # adı verilmemiş efekt: tekrar denetimine girmez (yoğunluğa girer)
            continue
        if name in last and t - last[name] < gap - 1e-9:
            out.append(f"ses efekti tekrarı: '{name}' {last[name]:.2f} ve {t:.2f} sn'de ({gap:.0f} sn içinde aynı efekt tekrar edilmez)")
        last[name] = t
    return out


def _norm_path(p: str) -> str:
    return "/" + p.replace("\\", "/").strip("/").lower() + "/"


def _layer_span(scene: dict, layer: dict) -> tuple[float, float]:
    st = scene["start_s"] + float(layer.get("start_s", 0.0))
    du = float(layer.get("dur_s", scene["dur_s"] - float(layer.get("start_s", 0.0))))
    return st, du


def source_props(layer: dict) -> list[tuple[str, Any]]:
    """Bileşen katmanının kaynak alan prop'ları: [(prop, değer)] (değer kaynak nesnesi olmalı)."""
    props = layer.get("props") or {}
    return [(k, props.get(k)) for k in SOURCE_PROPS.get(layer.get("component") or "", []) if props.get(k) is not None]


def _component_rules(plan: dict, s: dict, li: int, layer: dict, context: dict | None, errors: list[str], warnings: list[str]) -> None:
    """1.8.0 bileşen kuralları: önce/sonra (gerçek çekim, konsept, kategori, sektör), kanıtlı sayı, kişisel veri, vurgu metni."""
    comp = layer.get("component")
    props = layer.get("props") or {}
    where = f"sahne {s['id']} katman {li}"
    ready = plan["status"] == "ready"
    for k, v in source_props(layer):
        if not isinstance(v, dict) or v.get("kind") not in SOURCE_KINDS:
            errors.append(f"{where}: {comp}.{k} kaynak nesnesi olmalı ({{kind, asset|path, in_s, out_s}})")
            continue
        if v["kind"] in ("ai_clip", "ai_image"):
            errors.append(f"{where}: {comp}.{k} AI kaynak olamaz (bileşen kaynakları gerçek çekim ya da görseldir; AI payı katmanlardan hesaplanır)")
        for key in ("path", "asset"):
            if any(part in _norm_path(str(v.get(key) or "")) for part in FORBIDDEN_PATH_PARTS):
                errors.append(f"{where}: {comp}.{k} rakip ya da referans klasörünü gösteriyor ({v.get(key)})")
        if v["kind"] == "footage" and "in_s" in v and "out_s" in v and v["out_s"] <= v["in_s"]:
            errors.append(f"{where}: {comp}.{k} out_s ≤ in_s")
        if ready and not (v.get("asset") or v.get("path")):
            errors.append(f"{where}: {comp}.{k} hazır planda varlık bağlı değil")
    if comp == "BeforeAfter":
        for k in ("before", "after"):
            v = props.get(k)
            if not isinstance(v, dict) or v.get("kind") != "footage":
                errors.append(f"{where}: BeforeAfter.{k} gerçek çekim olmalı (kind: footage); önce/sonra sahnesi gerçekten çekilir (ref-legal-tr-meta §3)")
        cat = props.get("category")
        if cat not in BEFORE_AFTER_CATEGORIES:
            errors.append(f"{where}: BeforeAfter.category ürün kategorisini işaretlemeli ({' | '.join(BEFORE_AFTER_CATEGORIES)}; ref-legal-tr-meta §8d)")
        elif cat == "skin_whitening":
            errors.append(f"{where}: kalıcı cilt beyazlatma önce/sonra ile tanıtılamaz (Meta, ref-legal-tr-meta §8d)")
        elif cat in ("cosmetic", "weight"):
            warnings.append(f"{where}: önce/sonra {cat} kategorisinde yalnızca 18+ hedeflemeyle; not S14 yayın paketine taşınır (§8d)")
        elif cat == "health_claim":
            warnings.append(f"{where}: sağlık iddialı üründe önce/sonra: hastalık ve tıklama tuzağı kuralları (§8c), sağlık beyanı belgesi (§3)")
        if context is None:
            warnings.append(f"{where}: konseptin kanıt türü ve işletme sektörü bu yolda denetlenmedi (edit_plan_validate denetler)")
        else:
            if context.get("concept_proof") != "before_after":
                errors.append(f"{where}: BeforeAfter yalnızca kanıt türü before_after seçilmiş konseptte kullanılır "
                              f"(konsept: {context.get('concept_proof') or 'belirtilmemiş'})")
            if context.get("regulated_sector") == "health":
                errors.append(f"{where}: sağlık hizmetinde önce/sonra görseli kullanılmaz (ref-legal-tr-meta, sağlık hizmetleri güvenli varsayılanı)")
    elif comp == "NumberRoll":
        kind = props.get("kind")
        val = props.get("value")
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            errors.append(f"{where}: NumberRoll.value sayı olmalı")
        if kind == "price":
            if not props.get("currency"):
                errors.append(f"{where}: NumberRoll fiyat gösteriyorsa para birimi zorunlu (PriceTag kuralı, bölüm 10)")
            price = (context or {}).get("product_price")
            if price is not None and isinstance(val, (int, float)) and abs(float(val) - float(price)) > 0.005:
                warnings.append(f"{where}: NumberRoll fiyatı ({val}) ürün kaydındaki fiyattan ({price}) farklı; satış sayfasıyla aynı olmalı")
        elif kind == "claim":
            ci, ref = props.get("claimIndex"), props.get("claimRef")
            if not ((isinstance(ci, int) and not isinstance(ci, bool)) or (isinstance(ref, str) and ref.strip())):
                errors.append(f"{where}: NumberRoll iddia sayısı claimIndex (provable_claims_json sırası) ya da claimRef (iddianın code'u) ister")
            elif context is None:
                warnings.append(f"{where}: NumberRoll iddiası kanıtlanabilir iddia listesiyle bu yolda denetlenmedi (edit_plan_validate denetler)")
            else:
                claims = [c if isinstance(c, dict) else {"claim": str(c)} for c in context.get("claims") or []]
                if isinstance(ci, int) and not isinstance(ci, bool):
                    c = claims[ci] if 0 <= ci < len(claims) else None
                else:
                    c = next((x for x in claims if ref in (x.get("code"), x.get("claim"), x.get("text"))), None)
                text = str((c or {}).get("claim") or (c or {}).get("text") or "")
                if c is None:
                    errors.append(f"{where}: NumberRoll iddiası ({ci if ref is None else ref}) kanıtlanabilir iddia listesinde yok ({len(claims)} iddia)")
                elif c.get("documented") is False or (c.get("needs_document") and not (c.get("verified") or c.get("document_path"))):
                    errors.append(f"{where}: NumberRoll iddiası belge istiyor ama belge/doğrulama yok: «{text[:80]}»")
                else:
                    digits = re.sub(r"\D", "", f"{val:g}" if isinstance(val, (int, float)) else "")
                    if digits and digits not in re.sub(r"\D", "", text):
                        warnings.append(f"{where}: NumberRoll değeri ({val}) iddia metninde geçmiyor: «{text[:80]}»")
        else:
            errors.append(f"{where}: NumberRoll değeri ya fiyat (kind: price + currency) ya da kanıtlı iddia (kind: claim + claimIndex/claimRef) olmalı")
    elif comp == "PhoneScreen":
        pdm = props.get("personalData", "unknown")
        if pdm == "blurred" and not props.get("blurRegions"):
            errors.append(f"{where}: PhoneScreen kişisel veri bulanıklaştırılacak ama blurRegions boş")
        elif pdm not in ("none", "blurred"):
            (errors if ready else warnings).append(
                f"{where}: PhoneScreen kaydında başka kişinin adı/numarası/fotoğrafı var mı kapıda sorulmadı (personalData: none | blurred)")
    elif comp == "PictureInPicture":
        if not isinstance(props.get("inset"), dict):
            errors.append(f"{where}: PictureInPicture.inset kaynağı yok")
    elif comp == "TextMark":
        if not str(props.get("text") or "").strip() or not str(props.get("mark") or "").strip():
            errors.append(f"{where}: TextMark text ve mark ister")
        elif _fold(str(props["mark"])) not in _fold(str(props["text"])) and not all(
                w in _fold(str(props["text"])) for w in _fold(str(props["mark"])).split()):
            errors.append(f"{where}: TextMark vurgusu («{props['mark']}») metinde yok")


def _fold(s: str) -> str:
    from .util import tr_fold
    return tr_fold(s)


def validate(plan: dict, *, style: dict | None = None, beats: list[float] | None = None,
             asset_index: dict[str, dict] | None = None, context: dict | None = None) -> dict[str, Any]:
    """Planı doğrular. style: planın bağlandığı stil kopyası (efekt bütçesi için); beats: vuruş zamanları (sn);
    asset_index: asset anahtarı → {kind, speaking_person, path}; context (1.8.0, edit_plan_validate verir): {concept_proof,
    regulated_sector, claims, product_price} — yoksa konsept/sektör/iddia denetimleri uyarıya düşer. Dönüş: {valid, errors, warnings, computed}."""
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
                    errors.append(f"sahne {s['id']} katman {li}: kaynak rakip analizi ya da referans video klasörünü gösteriyor ({val}); rakip/referans varlığı üretime girmez (4.5, 5.2)")
            props = layer.get("props") or {}
            for pv in props.values():
                if isinstance(pv, str) and any(part in _norm_path(pv) for part in FORBIDDEN_PATH_PARTS):
                    errors.append(f"sahne {s['id']} katman {li}: bileşen prop'u rakip ya da referans klasörünü gösteriyor ({pv})")
            if layer["type"] in ("video", "image") and not src:
                errors.append(f"sahne {s['id']} katman {li}: görüntü katmanının kaynağı yok")
            if src.get("kind") == "footage":
                if "in_s" in src and "out_s" in src and src["out_s"] <= src["in_s"]:
                    errors.append(f"sahne {s['id']} katman {li}: out_s ≤ in_s")
            cam = layer.get("camera") or {}
            try:
                zoom = float(cam.get("zoom") if cam.get("zoom") is not None else 1.0)
            except (TypeError, ValueError):
                zoom = -1.0
            if cam.get("preset") == "punch_in" and not 1.0 <= zoom <= 1.2:
                errors.append(f"sahne {s['id']} katman {li}: punch_in yakınlaştırması 1,0–1,2 olmalı (fazlası görüntüyü bozar)")
            if layer["type"] in ("video", "image"):
                st, du = _layer_span(s, layer)
                video_dur += du
                if src.get("kind") in ("ai_clip", "ai_image"):
                    ai_dur += du
                    ai_layers.append(f"{s['id']}:{li}")
                    if src.get("kind") == "ai_clip" and not src.get("real_twin") and plan["status"] == "ready":
                        warnings.append(f"sahne {s['id']} katman {li}: AI klibin gerçek çekimli eşi (real_twin) belirtilmemiş (5.3, 5.16)")
            comp = layer.get("component")
            if comp in ("BeforeAfter", "NumberRoll", "PhoneScreen", "PictureInPicture", "TextMark"):
                _component_rules(plan, s, li, layer, context, errors, warnings)
            if comp == "ReviewCard" and not layer.get("review_id"):
                errors.append(f"sahne {s['id']} katman {li}: ReviewCard izin kaydı (review_id) olmadan kullanılamaz (bölüm 10)")
            if comp in PREVIEW_ONLY and plan["purpose"] == "production" and plan["status"] == "ready":
                errors.append(f"sahne {s['id']}: {comp} yalnızca önizleme bileşenidir; hazır üretim planında olamaz")
            if comp in SIGNATURE and s["role"] not in ("reveal", "endcard"):
                errors.append(f"sahne {s['id']}: imza anı bileşeni {comp} yalnızca reveal ve son kartta kullanılabilir (5.12)")
            if layer["type"] == "text" or comp in ("TextReveal", "KineticWords", "SoftType", "LowerThird", "PriceTag", "TextMark"):
                st, du = _layer_span(s, layer)
                if du < 1.5:
                    warnings.append(f"sahne {s['id']} katman {li}: yazı {du:.2f} sn ekranda; okunurluk için ≥ 1,5 sn önerilir (bölüm 10)")

    # Ses kuralları
    for s in scenes:
        mode = s["audio"]["mode"]
        speaking = bool(s.get("speaking_person")) or any(bool(l.get("speaking_person")) for l in s["layers"])
        # 1.8.0: köşedeki konuşan kişi (PictureInPicture.inset) de konuşmalı sahne sayılır
        speaking = speaking or any(isinstance(v, dict) and v.get("speaking_person") for l in s["layers"] for _, v in source_props(l))
        if asset_index:
            for l in s["layers"]:
                srcs = [l.get("source") or {}] + [v for _, v in source_props(l) if isinstance(v, dict)]
                if any(src.get("asset") and asset_index.get(src["asset"], {}).get("speaking_person") for src in srcs):
                    speaking = True
        if speaking and mode not in ("original", "original_clean"):
            errors.append(f"sahne {s['id']}: kamerada konuşan kişi var; ses yalnızca 'original' ya da 'original_clean' olabilir (dudak senkronu, 5.2)")
        if plan["purpose"] == "style_preview" and mode != "none":
            errors.append(f"sahne {s['id']}: stil önizlemesi yalnızca audio.mode=none ile gösterilir (5.2)")
        if plan["status"] == "ready" and plan["purpose"] == "production" and not s["audio"].get("decision_id"):
            errors.append(f"sahne {s['id']}: hazır üretim planında sahne başına kullanıcı ses kararı (decision_id) zorunlu (5.2, 5.13)")
        if mode == "user_vo" and not (s["audio"].get("user_vo_asset") or (plan.get("vo") or {}).get("asset")):
            errors.append(f"sahne {s['id']}: user_vo seçilmiş ama kullanıcı kaydı belirtilmemiş")

    # Ses efekti yoğunluğu ve sahne içinde kalma (1.5.0)
    for s in scenes:
        for c in s.get("audio_cues") or []:
            if float(c["at_s"]) > float(s["dur_s"]) + frame:
                errors.append(f"sahne {s['id']}: ses efekti {c.get('sfx')} sahne süresinin dışında (at_s {c['at_s']} > {s['dur_s']})")
    errors.extend(sfx_density(scenes, effects))

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
    marks = sum(1 for s in scenes for l in s["layers"] if l.get("component") == "TextMark")
    marks_allowed = TEXT_MARK_MAX_PER_15S * max(1, math.ceil(plan["duration_s"] / 15.0 - 1e-9))
    if marks > marks_allowed:
        errors.append(f"efekt bütçesi: {marks} sözcük vurgusu (TextMark) var, izin verilen {marks_allowed} (15 sn'de en fazla {TEXT_MARK_MAX_PER_15S})")
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
