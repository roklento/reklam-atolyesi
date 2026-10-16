"""Koçluk grafikleri (spec 6.12) — matplotlib; her grafiğin altında tek cümlelik yorum (rapor yazar).

Kullanım: charts.py --analysis analysis.json --snapshot input.json --out-dir reports/c1-charts-v1
Renkler nötr; marka paleti kullanılmaz (rapor iç belgedir).
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit, read_json  # noqa: E402

GRAY = ["#3B3B3B", "#6E6E6E", "#9C9C9C", "#C4C4C4", "#555555", "#808080"]


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    return plt


def funnel(an: dict, out: Path) -> str:
    plt = _plt()
    keys = sorted(an["concepts"])
    fig, ax = plt.subplots(figsize=(7, 3.2))
    w = 0.25
    for j, m in enumerate(("hook_rate", "ctr_link", "cvr")):
        vals = [(an["concepts"][k]["rates"].get(m) or {}).get("mean") or 0 for k in keys]
        ax.bar([i + j * w for i in range(len(keys))], vals, w, label=m, color=GRAY[j])
    ax.set_xticks([i + w for i in range(len(keys))], keys)
    ax.set_title("Huni göstergeleri (her oran kendi paydasıyla)")
    ax.legend(frameon=False)
    p = out / "funnel.png"
    fig.tight_layout()
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return str(p)


def intervals(an: dict, out: Path, metric: str = "hook_rate") -> str:
    plt = _plt()
    items = [(k, v["rates"].get(metric)) for k, v in sorted(an["creatives"].items()) if v["rates"].get(metric)]
    fig, ax = plt.subplots(figsize=(7, max(2.2, 0.35 * len(items) + 1)))
    for i, (k, r) in enumerate(items):
        ax.plot([r["lo"], r["hi"]], [i, i], color=GRAY[1], lw=3)
        ax.plot(r["mean"], i, "o", color=GRAY[0] if r["threshold_met"] else "#BBBBBB")
    ax.set_yticks(range(len(items)), [k[-28:] for k, _ in items])
    ax.set_title(f"{metric}: %90 aralıklar (açık renk = eşik altı, yön)")
    p = out / f"intervals_{metric}.png"
    fig.tight_layout()
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return str(p)


def spend(an: dict, out: Path) -> str:
    plt = _plt()
    d = an["spend_distribution"]
    keys = sorted(d)
    fig, ax = plt.subplots(figsize=(6, 2.8))
    ax.bar(keys, [d[k]["share"] for k in keys], color=[("#BBBBBB" if d[k]["starved"] else GRAY[0]) for k in keys])
    ax.axhline(0.10, color="#999", ls="--", lw=1)
    ax.set_title("Harcama dağılımı (açık renk: %10 altı, aç kalan)")
    p = out / "spend.png"
    fig.tight_layout()
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return str(p)


def timeseries(snap: dict, out: Path) -> str:
    plt = _plt()
    g = defaultdict(list)
    for r in snap["rows"]:
        g[r.get("creative_key") or r["meta_ad_id"]].append(r)
    fig, ax = plt.subplots(figsize=(7, 3))
    for i, (k, rows) in enumerate(sorted(g.items())):
        rows.sort(key=lambda r: r["date"])
        ys = [(float(r["video_3s"] or 0) / float(r["impressions"])) if r.get("impressions") else None for r in rows]
        ax.plot([r["date"][5:] for r in rows], ys, color=GRAY[i % len(GRAY)], label=k[-20:])
    ax.set_title("Günlük hook oranı (kreatif başına)")
    ax.tick_params(axis="x", rotation=60)
    if len(g) <= 6:
        ax.legend(frameon=False, fontsize=7)
    p = out / "timeseries.png"
    fig.tight_layout()
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return str(p)


def retention_chart(an: dict, out: Path) -> str | None:
    if not an.get("retention"):
        return None
    plt = _plt()
    fig, ax = plt.subplots(figsize=(6, 2.8))
    for i, r in enumerate(an["retention"]):
        ax.axvspan(r["interval_s"][0], r["interval_s"][1], color=GRAY[3], alpha=0.5)
        ax.text(r["interval_s"][0], 0.9 - i * 0.1, f"{r['creative'][-18:]} {r['scene'] or ''}", fontsize=7)
    ax.set_ylim(0, 1)
    ax.set_title("Beklenenden hızlı kayıp aralıkları (olasılık)")
    p = out / "retention.png"
    fig.tight_layout()
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return str(p)


def make_all(an: dict, snap: dict, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    charts = {"funnel": funnel(an, out), "intervals_hook": intervals(an, out, "hook_rate"), "intervals_ctr": intervals(an, out, "ctr_link"),
              "spend": spend(an, out), "timeseries": timeseries(snap, out)}
    r = retention_chart(an, out)
    if r:
        charts["retention"] = r
    return charts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--analysis", required=True)
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    emit(make_all(read_json(a.analysis), read_json(a.snapshot), Path(a.out_dir)))


if __name__ == "__main__":
    main()
