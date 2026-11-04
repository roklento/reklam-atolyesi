"""Admin ekibine anonim geri bildirim paketi (2.5.0; KURALLAR K15) — saf fonksiyonlar.

Paket yalnızca sayılar ve plugin'in kendi sabit kodlarından (aşama kodu, sonuç türü, denetim sorun kodu, araç adı) oluşur. Serbest metin,
ad, yol, kimlik, tarih-saat (yalnızca gün) ve tutar YOKTUR. build_report çıktısı assert_anonymous'tan geçmeden yazılmaz.
Plugin paketi hiçbir yere göndermez: dosyayı kullanıcı kendisi sağlayıcısına iletir.
"""
from __future__ import annotations

import re
import statistics

SCHEMA = "reklam-atolyesi-geri-bildirim/2"  # 2.8.0: hata defteri — imzalar (aşama · sinyal · kod · senaryo hücresi)
SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_.:+\-/]{0,64}$")
OWN_TOOL = re.compile(r"^mcp__plugin_reklam-atolyesi_[A-Za-z0-9_-]+__[a-z0-9_]+$")
BUILTIN_TOOLS = {"Bash", "PowerShell", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch", "Agent", "Task", "Skill",
                 "NotebookEdit", "TodoWrite", "AskUserQuestion"}
ERROR_KINDS = (
    ("timeout", re.compile(r"timeout|timed out|zaman aşımı", re.I)),
    ("permission", re.compile(r"permission|(?<!\w)iz(?:in|ni)|denied|reddedildi|EACCES|EPERM", re.I)),
    ("not_found", re.compile(r"not found|bulunamadı|no such file|yok:|ENOENT", re.I)),
    ("network", re.compile(r"network|connection|bağlantı|ECONN|SSL|TLS|proxy|DNS", re.I)),
    ("encoding", re.compile(r"unicode|encoding|codec|charmap", re.I)),
    ("auth", re.compile(r"oauth|token|401|403|unauthori", re.I)),
    ("validation", re.compile(r"AdMemoryError|geçersiz|olmalı|zorunlu|invalid|must be", re.I)),
)


def tool_bucket(name: str) -> str:
    """Araç adı: plugin'in kendi araçları ve yerleşik araçlar adıyla, diğer MCP sunucuları tek grupta (kullanıcının başka hizmetleri
    pakete girmez)."""
    name = str(name or "")
    if OWN_TOOL.match(name):
        return name.split("__", 2)[-1] if name.count("__") >= 2 else "own"
    if name in BUILTIN_TOOLS:
        return name
    if name.startswith("mcp__"):
        return "other_mcp"
    return "other"


def error_kind(text: str) -> str:
    for kind, rx in ERROR_KINDS:
        if rx.search(text or ""):
            return kind
    return "other"


def median(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def days_bucket(days: float) -> str:
    if days < 3:
        return "0-3"
    if days < 7:
        return "3-7"
    if days < 30:
        return "7-30"
    return "30+"


def assert_anonymous(obj, path: str = "$") -> None:
    """Paket yalnızca güvenli anahtar/değerlerden oluşur: sayı, bool, None ya da SAFE_TOKEN'a uyan kısa kod. Aksi halde ValueError."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str) or not SAFE_TOKEN.match(k):
                raise ValueError(f"{path}: güvensiz anahtar {k!r}")
            assert_anonymous(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            assert_anonymous(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        if not SAFE_TOKEN.match(obj):
            raise ValueError(f"{path}: serbest metin pakete giremez ({obj[:20]!r}…)")
    elif obj is not None and not isinstance(obj, (int, float, bool)):
        raise ValueError(f"{path}: desteklenmeyen tür {type(obj).__name__}")


def product_cell(kind: str | None, eco_status: str | None, season: str | None, result_type: str | None, lead_method: str | None) -> str:
    """Senaryo matrisinin ürün ekseni (evals/senaryo-matrisi.json): kayıttan güvenle ayrılabilen en belirgin tür. P1–P3 (düşük/yüksek
    fiyatlı fiziksel, dijital) kayıttan ayrılamaz → "P1-3"; ürün yoksa "Px". Tahmin yok."""
    if kind is None and eco_status is None:
        return "Px"
    if eco_status == "non_positive":
        return "P8"
    if kind == "service" or result_type == "lead" or lead_method:
        return "P4"
    if eco_status == "range":
        return "P7"
    if eco_status == "unknown":
        return "P6"
    if season:
        return "P5"
    return "P1-3"


def user_cell(n_profiles: int, data_mode: str | None, currency: str | None, cycle: int | None) -> str:
    """Kullanıcı ekseni: U4 ajans (birden çok profil) · U5 CSV modu · U6 TRY dışı para birimi · U3 ikinci ve sonraki tur. U1/U2/U7/U8
    bütçeye göreli olduğundan kayıttan ayrılmaz → "Ux"."""
    if n_profiles > 1:
        return "U4"
    if data_mode == "csv":
        return "U5"
    if currency and str(currency).upper() not in ("TRY", "TL"):
        return "U6"
    if cycle and int(cycle) >= 2:
        return "U3"
    return "Ux"


SIGNAL_TEXT = {  # müşteriye ve admin'e sade anlatım (pakete girmez)
    "duzeltme_istendi": "kullanıcı taslakta değişiklik istedi",
    "geri_donuldu": "kullanıcı önceki bir adıma geri döndü",
    "takildi": "adım 3 günden uzun süredir bekliyor",
    "taslak_son_tur_kaldi": "taslak, son düzeltme turunda da denetimi geçemedi",
    "sorunla_onaylandi": "adım, denetimde kalan bir sorunla onaylandı",
    "kreatif_red": "bir reklam son kontrolden geçemedi",
    "arac_hatasi": "sistemde bir hata oldu",
}


def _stage_name(code: str) -> str:
    """Kullanıcı özetinde aşama kodu değil adı görünür (2.9.0, K16); defterin kendisi kodu taşır."""
    from . import stages as ST
    return ST.STAGE_NAMES.get(code, "Bir")


def summary_lines(rep: dict) -> list[str]:
    """Kullanıcıya gösterilecek sade özet (pakete girmez). Teknik terim yok; ilk kez gören biri anlamalı."""
    st = rep.get("stages") or {}
    stuck = rep.get("stuck") or []
    er = rep.get("errors") or {}
    sig = rep.get("imzalar") or []
    lines = [f"Son {rep['period_days']} günün kaydı (Reklam Atölyesi {rep['plugin_version']}).",
             f"Tamamlanan adım: {sum(v.get('completed', 0) for v in st.values())}. Geri dönülen adım: "
             f"{sum(v.get('back_to', 0) for v in st.values())}. Bekleyen adım: {len(stuck)}.",
             f"Kaydedilen hata: {er.get('count', 0)}."]
    if sig:
        lines.append("En sık görülenler:")
        for s in sig[:5]:
            where = f"{_stage_name(s['asama'])} adımında " if s["asama"] not in ("-", None, "") else ""
            lines.append(f"- {where}{SIGNAL_TEXT.get(s['sinyal'], s['sinyal'])} ({s['n']} kez)")
    lines.append("Defterde adın, markan, ürünlerin, tutarların, dosyalarının yeri ya da yazdığın bir metin yer almaz. "
                 "Yalnızca hangi adımda ne tür bir sorun olduğu ve kaç kez olduğu yazılır.")
    return lines
