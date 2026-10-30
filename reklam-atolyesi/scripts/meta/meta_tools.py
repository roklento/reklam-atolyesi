"""Meta yardımcıları (spec 9.2, 5.18, 6.6, 17.6). Veritabanına yazmaz; içe alma ad-memory metrics_import_csv ile yapılır.

Alt komutlar:
  csv-check   --csv export.csv                      sütun eşlemesi (TR/EN başlıklar), zorunlu sütunlar, ondalık ayırıcı, tarih aralığı
  naming      --names names.json|--name "<ad adı>"  reklam adı → creative_key (adlandırma kuralı)
  priors      --rows rows.json --cutoff 2026-01-01 [--n-cap 30]   geçmişten Beta önsel (ad-memory ile aynı formül; doğrulama için)
  synth-csv   --out x.csv --ads 3 --days 10 [--seed 1729] [--start 2026-01-05]   nötr sentetik dışa aktarım (testler)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import PLUGIN_ROOT, atomic_write, emit, read_json  # noqa: E402
from admem import naming  # noqa: E402
from admem.s_meta import _date_ordered, detect_date_order, detect_decimal  # noqa: E402
from admem.util import AdMemoryError  # noqa: E402

FIELDS = json.loads((PLUGIN_ROOT / "servers" / "ad_memory" / "meta_fields.json").read_text(encoding="utf-8"))["fields"]


def csv_check(path: str) -> dict:
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-16", "cp1254", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    delim = ";" if text[:4096].count(";") > text[:4096].count(",") else ","
    rd = csv.DictReader(io.StringIO(text), delimiter=delim)
    heads = rd.fieldnames or []
    cmap = {}
    for k, spec in FIELDS.items():
        for h in spec.get("csv_headers", []):
            for real in heads:
                if real and real.strip().lower() == h.lower():
                    cmap.setdefault(k, real)
    rows = list(rd)
    need = ["date", "ad_id", "impressions", "spend"]
    video = ["thruplay", "p25", "p50", "p75", "p95", "p100"]
    raw = [r.get(cmap.get("date", ""), "") for r in rows if r.get(cmap.get("date", ""))]
    try:  # 2.0.0: tarih sırası (gün/ay) ve ISO aralık; ham metin sıralaması "10.03"ü "02.04"ten önce koyuyordu
        order = detect_date_order(raw)
        dates = sorted({_date_ordered(v, order) for v in raw}) if order else sorted(set(raw))
    except AdMemoryError as e:
        order, dates = f"hata: {e}", sorted(set(raw))
    return {"columns": cmap, "missing_required": [k for k in need if k not in cmap], "missing_video": [k for k in video if k not in cmap],
            "has_3s_or_cost_per_view": ("video_3s" in cmap) or ("cost_per_video_view" in cmap), "rows": len(rows),
            "decimal": detect_decimal([r.get(cmap.get("spend", ""), "") for r in rows][:200]), "date_range": [dates[0], dates[-1]] if dates else None,
            "date_order": order or "belirsiz: kullanıcıya rapor aralığı sorulur, measurement_context.csv_date_order ile verilir",
            "note": "Reklam düzeyi, günlük (time increment 1 gün), video sütunlu dışa aktarım gerekir; ölçüm bağlamı (hesap, saat dilimi, para birimi, sonuç tanımı, atıf penceresi, action_report_time) ayrıca verilir."}


def priors_from_rows(rows: list[dict], cutoff: str, n_cap: float = 30, min_impr: int = 1000) -> dict:
    by_ad: dict[str, dict] = {}
    for r in rows:
        if r["date"] >= cutoff[:10]:
            continue
        a = by_ad.setdefault(r["meta_ad_id"], {"impressions": 0, "video_3s": 0, "thruplay": 0, "link_clicks": 0, "purchases": 0})
        for k in a:
            a[k] += float(r.get(k) or 0)
    out = {}
    for metric, (num, den) in {"hook_rate": ("video_3s", "impressions"), "ctr_link": ("link_clicks", "impressions"),
                               "hold_rate": ("thruplay", "video_3s"), "cvr": ("purchases", "link_clicks")}.items():
        ratios = [a[num] / a[den] for a in by_ad.values() if a["impressions"] >= min_impr and a[den] and a[num] <= a[den]]
        if not ratios:
            out[metric] = {"a": 1.0, "b": 1.0, "n_source": 0}
            continue
        m = sum(ratios) / len(ratios)
        n_eff = min(len(ratios), n_cap)
        a_, b_ = max(0.001, m * n_eff), max(0.001, (1 - m) * n_eff)
        if a_ + b_ > n_cap:
            s = n_cap / (a_ + b_)
            a_, b_ = a_ * s, b_ * s
        out[metric] = {"a": round(a_, 6), "b": round(b_, 6), "n_source": len(ratios), "mean": round(m, 6)}
    return out


def synth_csv(out: str, n_ads: int, days: int, seed: int, start: str, decimal: str = ",") -> dict:
    """Nötr sentetik Ads Manager dışa aktarımı ("Reklam A1" … ; gerçek ürün/marka yok)."""
    rng = np.random.default_rng(seed)
    d0 = dt.date.fromisoformat(start)
    heads = ["Gün", "Reklam Kimliği", "Reklam adı", "Gösterimler", "Erişim", "Sıklık", "Harcanan Tutar (TRY)", "3 saniyelik video oynatmaları",
             "ThruPlay'ler", "Videonun %25'ine kadar oynatılması", "Videonun %50'sine kadar oynatılması", "Videonun %75'ine kadar oynatılması",
             "Videonun %95'ine kadar oynatılması", "Videonun %100'üne kadar oynatılması", "Bağlantı Tıklamaları", "Sonuçlar", "Satın Almalar"]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(heads)
    fmt = (lambda v: f"{v:.2f}".replace(".", ",")) if decimal == "," else (lambda v: f"{v:.2f}")
    for a in range(n_ads):
        hook = 0.18 + 0.06 * a
        for i in range(days):
            imp = int(rng.integers(800, 1600))
            v3 = int(rng.binomial(imp, hook))
            tp = int(rng.binomial(v3, 0.4))
            clicks = int(rng.binomial(imp, 0.012))
            purch = int(rng.binomial(clicks, 0.05))
            spend = imp * 0.05
            w.writerow([(d0 + dt.timedelta(days=i)).isoformat(), f"9000{a}", f"Reklam A{a}", imp, int(imp * 0.8), fmt(1.25), fmt(spend), v3, tp,
                        int(v3 * 0.8), int(v3 * 0.6), int(v3 * 0.45), int(v3 * 0.35), int(v3 * 0.3), clicks, purch, purch])
    sha = atomic_write(out, buf.getvalue())
    return {"out": out, "sha256": sha, "ads": n_ads, "days": days}


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("csv-check")
    p.add_argument("--csv", required=True)
    p = sp.add_parser("naming")
    p.add_argument("--names")
    p.add_argument("--name")
    p = sp.add_parser("priors")
    p.add_argument("--rows", required=True)
    p.add_argument("--cutoff", required=True)
    p.add_argument("--n-cap", type=float, default=30)
    p = sp.add_parser("synth-csv")
    p.add_argument("--out", required=True)
    p.add_argument("--ads", type=int, default=3)
    p.add_argument("--days", type=int, default=10)
    p.add_argument("--seed", type=int, default=1729)
    p.add_argument("--start", default="2026-01-05")
    p.add_argument("--decimal", default=",")
    a = ap.parse_args()
    if a.cmd == "csv-check":
        emit(csv_check(a.csv))
    elif a.cmd == "naming":
        names = read_json(a.names) if a.names else [a.name]
        emit({n: naming.match_ad_name(n) for n in names})
    elif a.cmd == "priors":
        emit(priors_from_rows(read_json(a.rows), a.cutoff, a.n_cap))
    else:
        emit(synth_csv(a.out, a.ads, a.days, a.seed, a.start, a.decimal))


if __name__ == "__main__":
    main()
