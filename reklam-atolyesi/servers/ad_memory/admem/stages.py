"""Aşama makinesi sabitleri (spec 4.1–4.2)."""
from __future__ import annotations

ONBOARDING_STAGES = ["S00a", "S00b", "S00c"]
CAMPAIGN_STAGES = ["S01", "S01b", "S02", "S03", "S04", "S05", "W", "S06", "S07", "S08", "S09",
                   "S10", "S11", "S12", "S13", "S14", "S15", "S16", "S17"]
STAGE_NAMES = {
    "S00a": "Marka tanışması", "S00b": "Meta geçmişi", "S00c": "Ürün tanışması",
    "S01": "Brief", "S01b": "Rakip analizi", "S02": "Strateji", "S03": "Konsept görüşmesi",
    "S04": "Çekim planı", "S05": "Deneme geri bildirimi", "W": "Çekim bekleniyor", "S06": "Ingest",
    "S07": "Analiz", "S08": "Stil yönleri", "S09": "Malzeme", "S10": "Kurgu", "S11": "Ses",
    "S12": "Varyasyon ve export", "S13": "Kalite kontrol", "S14": "Yayın paketi", "S15": "Takip",
    "S16": "Analiz ve koçluk", "S17": "Öğrenme",
}
GATES = {
    "S00a": "marka tanışması", "S00c": "ürün tanışması",
    "S02": "strateji (bütçe, risk sınırı, stratejik yön)", "S03": "görüşme özeti", "S04": "çekim planı",
    "S08": "stil seçimi", "S09": "ses kararları + maliyet", "S11": "taslak", "S13": "QC",
    "S14": "yayın paketi", "S16": "kararlar", "S17": "playbook",
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
