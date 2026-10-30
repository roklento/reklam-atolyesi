"""Huni aşamasına göre içerik planlama (1.9.0).

- Aşama (`stage`: tofu | mofu | bofu) bir KİTLE değil, reklamın seslendiği karar anıdır (mesaj hipotezi). Plugin tek geniş set kurar,
  yeniden hedefleme kitlesi kurmaz; Advantage+ kitlede reklamı kimin göreceğini Meta seçer (resmi, ref-legal-tr-meta §7). Reklamı kimin
  gördüğü, tanımlıysa Meta'nın kitle segmenti dökümüyle (yeni / etkileşime geçmiş / mevcut müşteri) sonradan okunur.
- Mesaj kartı (S03): her konsept "Kime, hangi düşünceyi değiştirmek için, hangi kanıtla konuşuyoruz?" sorusunu yanıtlar. Aşamanın dayanağı
  yazılır (`data` | `user` | `assumption`); veri yoksa bu açıkça söylenir.
- Satın alma engelleri (S00c, `products.objections_json`): BOFU yalnızca kanıtı olan tereddüde cevap verir; uydurma yorum, istatistik,
  stok azlığı ya da kampanya süresi yoktur.
"""
from __future__ import annotations

from typing import Any

from .util import AdMemoryError, jload

STAGES = ("tofu", "mofu", "bofu")
STAGE_BASIS = ("data", "user", "assumption")
FOCUS = ("need", "desire", "objection")
EVIDENCE_KINDS = ("claim", "review", "asset", "page_info", "none")
OBJECTION_SOURCES = ("user", "dm_lost_reason", "page_check", "review", "competitor")
ROUND_MODES = ("explore", "funnel")


def _text(v: Any) -> str:
    return v.strip() if isinstance(v, str) else ""


def validate_objections(raw: Any) -> list[dict]:
    """[{code, text, source, answer?, evidence?: {kind, ref}}]. Kodlar tekil; cevap yalnızca kanıtıyla `answerable` sayılır."""
    data = jload(raw, None) if isinstance(raw, str) else raw
    if data is None:
        return []
    if not isinstance(data, list):
        raise AdMemoryError("objections_json bir liste olmalı: [{code, text, source, answer?, evidence?}]")
    seen, out = set(), []
    for i, o in enumerate(data):
        if not isinstance(o, dict):
            raise AdMemoryError(f"objections_json[{i}] bir nesne olmalı")
        code, text = _text(o.get("code")), _text(o.get("text"))
        if not code or not text:
            raise AdMemoryError(f"objections_json[{i}]: code ve text zorunlu (alıcının tereddüdü kendi cümlesiyle)")
        if code in seen:
            raise AdMemoryError(f"objections_json: '{code}' kodu iki kez")
        seen.add(code)
        if o.get("source") not in OBJECTION_SOURCES:
            raise AdMemoryError(f"objections_json[{code}].source: {' | '.join(OBJECTION_SOURCES)}")
        ev = o.get("evidence")
        if ev is not None:
            if not isinstance(ev, dict) or ev.get("kind") not in EVIDENCE_KINDS or not _text(str(ev.get("ref") or "")):
                raise AdMemoryError(f"objections_json[{code}].evidence: {{kind: {' | '.join(EVIDENCE_KINDS)}, ref}}")
        if _text(o.get("answer")) and not ev:
            raise AdMemoryError(f"objections_json[{code}]: cevap kanıtıyla yazılır (evidence); kanıtı yoksa cevap boş kalır")
        out.append({**o, "code": code, "text": text})
    return out


def validate_message(msg: Any, objections: list[dict]) -> dict:
    """Mesaj kartının biçim denetimi. Kanıtların kayıtla eşleşmesi (yorum, iddia) çağıran tarafta yapılır."""
    data = jload(msg, None) if isinstance(msg, str) else msg
    if not isinstance(data, dict):
        raise AdMemoryError("mesaj kartı bir nesne olmalı: {stage, stage_basis, belief, focus, evidence, expected_action}")
    stage = data.get("stage")
    if stage not in STAGES:
        raise AdMemoryError(f"mesaj kartı stage: {' | '.join(STAGES)} (aşama kitle değildir, mesajın seslendiği karar anıdır)")
    if data.get("stage_basis") not in STAGE_BASIS:
        raise AdMemoryError(f"mesaj kartı stage_basis: {' | '.join(STAGE_BASIS)} (veri yoksa 'assumption' yazılır)")
    if data["stage_basis"] != "assumption" and not _text(data.get("stage_basis_note")):
        raise AdMemoryError("stage_basis data/user ise dayanak notu (stage_basis_note) yazılır; yoksa 'assumption'")
    if not _text(data.get("belief")):
        raise AdMemoryError("mesaj kartı belief: reklam sonunda değişmesini istediğimiz düşünce, tek cümle")
    if data.get("focus") not in FOCUS:
        raise AdMemoryError(f"mesaj kartı focus: {' | '.join(FOCUS)} (ihtiyaç · istek · satın alma engeli)")
    if data["focus"] == "objection":
        codes = {o["code"] for o in objections}
        if data.get("objection_code") not in codes:
            raise AdMemoryError("odak engel ise objection_code ürün kartındaki bir engel olmalı (S00c objections_json)"
                                + (f"; kayıtlı: {', '.join(sorted(codes))}" if codes else "; üründe kayıtlı engel yok"))
    if not _text(data.get("expected_action")):
        raise AdMemoryError("mesaj kartı expected_action: izleyicinin reklamdan sonra yapmasını beklediğimiz tek şey")
    ev = data.get("evidence")
    if not isinstance(ev, list) or not ev:
        raise AdMemoryError("mesaj kartı evidence: en az bir öğe ([{kind: 'none'}] dahil); kanıt uydurulmaz")
    for i, e in enumerate(ev):
        if not isinstance(e, dict) or e.get("kind") not in EVIDENCE_KINDS:
            raise AdMemoryError(f"evidence[{i}].kind: {' | '.join(EVIDENCE_KINDS)}")
        if e["kind"] != "none" and not _text(str(e.get("ref") or "")):
            raise AdMemoryError(f"evidence[{i}]: ref zorunlu (yorum kimliği, iddia metni, klip kimliği ya da okunan sayfa bilgisi)")
        if e["kind"] == "page_info" and not _text(e.get("checked_at")):
            raise AdMemoryError(f"evidence[{i}]: sayfa bilgisi okunduğu tarihle yazılır (checked_at)")
    return data


def bofu_evidence_ok(msg: dict, kinds: list[str]) -> bool:
    return any(e.get("kind") in kinds for e in (msg.get("evidence") or []))


def claim_usable(claim_text: str, provable_claims: list[dict]) -> bool:
    """İddia ürün kartında kayıtlı (S00c biçimi {claim, needs_document, verified} ya da {code, text, documented}) ve belgesi gerekmiyor
    ya da belgesi doğrulanmış olmalı."""
    t = _text(claim_text).casefold()
    for c in provable_claims or []:
        if not isinstance(c, dict):
            continue
        if t in {_text(c.get("claim")).casefold(), _text(c.get("text")).casefold(), _text(c.get("code")).casefold()} - {""}:
            return bool(c.get("verified") or c.get("documented")) or not c.get("needs_document", False)
    return False
