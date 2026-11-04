"""Aşama makinesi sabitleri (spec 4.1–4.2)."""
from __future__ import annotations

ONBOARDING_STAGES = ["S00a", "S00b", "S00c"]
CAMPAIGN_STAGES = ["S01", "S01b", "S02", "S03", "S04", "S05", "W", "S06", "S07", "S08", "S09",
                   "S10", "S11", "S12", "S13", "S14", "S15", "S16", "S17"]
STAGE_NAMES = {  # kullanıcıya görünen adlar: sade Türkçe (2.9.0, K16)
    "S00a": "Marka tanışması", "S00b": "Geçmiş reklamlara bakış", "S00c": "Ürün tanışması",
    "S01": "Reklamın özeti", "S01b": "Rakiplere bakış", "S02": "Strateji ve bütçe", "S03": "Reklam fikirleri",
    "S04": "Çekim planı", "S05": "Deneme çekimine bakış", "W": "Çekim bekleniyor", "S06": "Çekimleri alma",
    "S07": "Çekimleri inceleme", "S08": "Görünüm seçimi", "S09": "Ses ve malzemeler", "S10": "Kurgu", "S11": "Ses ve taslak",
    "S12": "Farklı sürümler ve dosyalar", "S13": "Son kontrol", "S14": "Yayın paketi", "S15": "Sonuçları izleme",
    "S16": "Sonuçları yorumlama", "S17": "Bu turdan öğrendiklerimiz",
}
GATES = {  # onay istenen konu, kullanıcıya görünür
    "S00a": "marka tanışması", "S00c": "ürün tanışması",
    "S02": "strateji (bütçe, harcama sınırı ve yön)", "S03": "konuşmamızın özeti", "S04": "çekim planı",
    "S08": "görünüm seçimi", "S09": "ses kararları ve maliyet", "S11": "video taslağı", "S13": "son kontrol",
    "S14": "yayın paketi", "S16": "kararlar", "S17": "kalıcı kurallar",
}
SKILLS = {
    "S00a": "brand-onboarding", "S00b": "meta-history", "S00c": "product-onboarding",
    "S01": "brief", "S01b": "competitor-analysis", "S02": "strategy", "S03": "concepts", "S04": "shoot-guide",
    "S05": "shoot-feedback", "W": None, "S06": "ingest", "S07": "analyze", "S08": "style-directions",
    "S09": "materials", "S10": "compose", "S11": "sound", "S12": "variants", "S13": "qc",
    "S14": "launch-pack", "S15": "track", "S16": "coach", "S17": "learn",
}
QUICK_SKIPPED = ["S04", "S05", "W", "S06"]
SKIPPABLE_ON_REQUEST = {"S01b"}
NO_RETURN_AFTER_LAUNCH = set(CAMPAIGN_STAGES[:CAMPAIGN_STAGES.index("S14") + 1])


def is_gated(stage: str) -> bool:
    return stage in GATES


def index(stage: str) -> int:
    if stage in CAMPAIGN_STAGES:
        return CAMPAIGN_STAGES.index(stage)
    raise ValueError(f"bilinmeyen kampanya aşaması: {stage}")


def next_stage(stage: str, mode: str = "full") -> str | None:
    """Kapı/tamamlanma sonrası bir sonraki aşama. S14 → S15 yalnızca launch_confirm ile; S17 → yeni tur."""
    if stage == "S03":
        return "S07" if mode == "quick" else "S04"
    if stage == "S05":
        return "W"
    if stage == "W":
        return "S06"
    if stage in ("S14", "S17"):
        return None
    i = index(stage)
    return CAMPAIGN_STAGES[i + 1] if i + 1 < len(CAMPAIGN_STAGES) else None
