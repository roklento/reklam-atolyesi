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
    for i in range(5):  # tamsayı yüzdeyle: kayan noktada 0.7 + 0.1 = 0.7999… sınırdaki tahmini yanlış kutuya koyuyordu (2.0.0)
        lo, hi = 50 + 10 * i, 60 + 10 * i
        sel = [w if p >= 0.5 else (not w) for p, w in rows if lo <= round(max(p, 1 - p) * 100, 9) < hi or (hi == 100 and max(p, 1 - p) >= 1.0)]
        if sel:
            bins.append({"claimed": f"%{lo}–{hi}", "n": len(sel), "realized": round(sum(sel) / len(sel), 3)})
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
