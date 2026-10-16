"""Malzeme haritası (spec 5.5): çekim menüsü numarası → en iyi klip ve aralık, eksik çekimler, AI ile tamamlanabilecekler,
gerçek çekimli eş kontrolü (5.3) ve daha önce açılış karesi olarak kullanılmış klip uyarısı.

Kullanım: material_map.py --menu shoot_menu.json --clips clips.json [--photos photos.json] --out analysis/material-map.md [--json-out ...]
  shoot_menu.json: [{"no": "S01", "concept": "A", "what": "...", "hook": "h1"|null, "ai_ok": bool, "real_twin_for": "S05"|null}]
  clips.json: [{"asset": "a12", "shot_no": "S01", "score": {...}, "best_ranges": [...], "used_in": [...], "path": "..."}]
Hızlı turda clips.json profil çekim kütüphanesinden (asset_query scope=profile) gelir.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import atomic_write, emit, read_json, write_json  # noqa: E402

MIN_SCORE = 0.45


def build(menu: list[dict], clips: list[dict], photos: list[dict] | None = None) -> dict:
    by_shot: dict[str, list[dict]] = {}
    for c in clips:
        if c.get("shot_no"):
            by_shot.setdefault(str(c["shot_no"]), []).append(c)
    rows, missing, ai_fill, twin_problems, reused_openings = [], [], [], [], []
    for m in menu:
        no = str(m["no"])
        cands = sorted(by_shot.get(no, []), key=lambda c: (c.get("score") or {}).get("overall", 0), reverse=True)
        best = cands[0] if cands else None
        ok = bool(best) and (best.get("score") or {}).get("overall", 0) >= MIN_SCORE
        rng = (best.get("best_ranges") or [None])[0] if best else None
        rows.append({"no": no, "concept": m.get("concept"), "what": m.get("what"), "hook": m.get("hook"),
                     "best": best.get("asset") if best else None, "range": rng, "score": (best.get("score") or {}).get("overall") if best else None,
                     "status": "ok" if ok else ("zayıf" if best else "eksik"), "alternatives": [c.get("asset") for c in cands[1:3]]})
        if not ok:
            (ai_fill if m.get("ai_ok") else missing).append(no)
        if m.get("real_twin_for"):
            twin_ok = ok
            if not twin_ok:
                twin_problems.append({"ai_scene_shot": m["real_twin_for"], "twin_shot": no,
                                      "note": "AI klibin gerçek çekimli eşi kullanılamıyor: ücretli AI üretiminden önce ek çekim ya da konsept uyarlaması (5.3)"})
        if best and m.get("hook"):
            for u in best.get("used_in") or []:
                if u.get("role") == "opening":
                    reused_openings.append({"shot": no, "asset": best.get("asset"), "creative_key": u.get("creative_key"),
                                            "note": "daha önce yayınlanmış kreatifte açılış karesiydi: Meta'nın gözünde aynı varlığa yakınlaşır (5.5)"})
    return {"rows": rows, "missing": missing, "ai_completable": ai_fill, "real_twin_problems": twin_problems,
            "reused_openings": reused_openings, "photos": len(photos or [])}


def to_md(m: dict, title: str = "Malzeme haritası") -> str:
    lines = [f"# {title}", "", "| Çekim | Konsept | Ne | En iyi klip | Aralık (sn) | Puan | Durum |", "|---|---|---|---|---|---|---|"]
    for r in m["rows"]:
        rng = f"{r['range']['in_s']}–{r['range']['out_s']}" if r.get("range") else "—"
        lines.append(f"| {r['no']}{' (hook ' + r['hook'] + ')' if r.get('hook') else ''} | {r.get('concept') or '—'} | {r.get('what') or '—'} | "
                     f"{r.get('best') or '—'} | {rng} | {r.get('score') if r.get('score') is not None else '—'} | {r['status']} |")
    lines += ["", f"**Eksik çekimler:** {', '.join(m['missing']) or 'yok'}",
              f"**AI ile tamamlanabilecekler:** {', '.join(m['ai_completable']) or 'yok'}",
              f"**Fotoğraf sayısı (statik/carousel için):** {m['photos']}"]
    if m["real_twin_problems"]:
        lines += ["", "**Gerçek çekimli eş sorunları:**"] + [f"- {p['ai_scene_shot']} ↔ {p['twin_shot']}: {p['note']}" for p in m["real_twin_problems"]]
    if m["reused_openings"]:
        lines += ["", "**Açılış karesi tekrarı uyarısı:**"] + [f"- {p['shot']} ({p['asset']}, {p['creative_key']}): {p['note']}" for p in m["reused_openings"]]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--menu", required=True)
    ap.add_argument("--clips", required=True)
    ap.add_argument("--photos")
    ap.add_argument("--out", required=True)
    ap.add_argument("--json-out")
    a = ap.parse_args()
    m = build(read_json(a.menu), read_json(a.clips), read_json(a.photos) if a.photos else None)
    sha = atomic_write(a.out, to_md(m))
    if a.json_out:
        write_json(a.json_out, m)
    emit({"out": a.out, "sha256": sha, **{k: m[k] for k in ("missing", "ai_completable", "real_twin_problems", "reused_openings")}})


if __name__ == "__main__":
    main()
