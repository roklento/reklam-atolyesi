"""Koçluğun kendi isabeti (spec 6.13, 6.16): çözülmüş tahminlerden kalibrasyon.

- Aynı tahmin bir kez, son geçerli çözümüyle sayılır; rapor sürümleri bağımsız yeni tahmin değildir (zinciri ilk kayıt temsil eder).
- 30'dan az çözülmüş tahminde yalnızca sayı ("12 tahminden 9'u tuttu"); eşik önerisi yok.
Kullanım: calibration.py --pairs pairs.json   ([{"p": 0.8, "won": true, "chain": "c1:concept:A:hook_rate"}, ...])
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import emit, read_json  # noqa: E402

MIN_RESOLVED = 30


def calibrate(pairs: list[dict], min_resolved: int = MIN_RESOLVED) -> dict:
    seen: dict[str, dict] = {}
    for p in pairs:
        key = p.get("chain") or str(id(p))
        if key not in seen:
            seen[key] = p  # zincirin ilk tahmini kalibrasyona girer
        elif "won" in p:
            seen[key] = {**seen[key], "won": p["won"]}  # son geçerli çözüm
    rows = [(float(v["p"]), bool(v["won"])) for v in seen.values() if "won" in v and v.get("p") is not None]
    n = len(rows)
    hits = sum(1 for p, w in rows if (p >= 0.5) == w)
    out = {"resolved": n, "hits": hits, "summary": f"{n} tahminden {hits}'i tuttu"}
    if n < min_resolved:
        out["note"] = f"en az {min_resolved} çözülmüş tahmin gerekir; eşik önerilmez"
        return out
    bins = []
    for lo in (0.5, 0.6, 0.7, 0.8, 0.9):
        sel = [w if p >= 0.5 else (not w) for p, w in rows if lo <= max(p, 1 - p) < lo + 0.1 or (lo == 0.9 and max(p, 1 - p) >= 0.9)]
        if sel:
            bins.append({"claimed": f"%{int(lo*100)}–{int(lo*100)+10}", "n": len(sel), "realized": round(sum(sel) / len(sel), 3)})
    out["bins"] = bins
    claimed = sum(max(p, 1 - p) for p, _ in rows) / n
    realized = hits / n
    out["overconfidence"] = round(claimed - realized, 3)
    out["suggestion"] = ("n_cap ya da eşikler gevşetilebilir (aşırı güven)" if claimed - realized > 0.08 else
                         "kalibrasyon makul" if abs(claimed - realized) <= 0.08 else "model temkinli")
    out["note"] = "öneri kullanıcı onayıyla uygulanır"
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", required=True)
    a = ap.parse_args()
    emit(calibrate(read_json(a.pairs)))


if __name__ == "__main__":
    main()
