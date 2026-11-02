"""Admin ekibine anonim geri bildirim paketi (2.5.0; KURALLAR K15) — saf fonksiyonlar.

Paket yalnızca sayılar ve plugin'in kendi sabit kodlarından (aşama kodu, sonuç türü, denetim sorun kodu, araç adı) oluşur. Serbest metin,
ad, yol, kimlik, tarih-saat (yalnızca gün) ve tutar YOKTUR. build_report çıktısı assert_anonymous'tan geçmeden yazılmaz.
Plugin paketi hiçbir yere göndermez: dosyayı kullanıcı kendisi sağlayıcısına iletir.
"""
from __future__ import annotations

import re
import statistics

SCHEMA = "reklam-atolyesi-geri-bildirim/1"
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


def summary_lines(rep: dict) -> list[str]:
    """Kullanıcıya önizlemede gösterilecek sade Türkçe özet (pakete girmez)."""
    st = rep.get("stages") or {}
    stuck = rep.get("stuck") or []
    dc = rep.get("draft_checks") or {}
    er = rep.get("errors") or {}
    lines = [f"Dönem: son {rep['period_days']} gün · plugin {rep['plugin_version']} · profil sayısı {sum((rep.get('profiles') or {}).values())}",
             f"Tamamlanan aşama: {sum(v.get('completed', 0) for v in st.values())} · geri dönüş: {sum(v.get('back_to', 0) for v in st.values())}",
             f"Bekleyen/takılı aşama: {len(stuck)}" + (" (" + ", ".join(f"{s['stage']} {s['open_runs']}" for s in stuck[:5]) + ")" if stuck else ""),
             f"Taslak denetimi: {dc.get('total', 0)} denetim, ilk turda geçen oran {dc.get('pass_first_round_rate')}",
             f"Kayıtlı araç hatası: {er.get('count', 0)}"]
    lines.append("Pakette marka, ürün, kampanya adı, dosya yolu, tutar, kişi bilgisi ya da serbest metin yoktur; yalnızca sayılar ve plugin kodları.")
    return lines
