"""Canlı ilerleme panosu (2.10.18): kampanyanın nerede olduğunu kullanıcının tarayıcıda izleyebileceği yerel bir sayfa.

Sohbette ne olduğunu ancak sorarak öğrenen kullanıcı (özellikle yeni başlayan) için: aşamalar sırayla yanar, onay bekleyen konu öne çıkar,
kurgu planının sahneleri kart olarak görünür, ücretli üretimler ve harcanan kredi listelenir. Sayfa yalnızca okur: veritabanı salt okuma
kipinde açılır, hiçbir kayıt değişmez, dışarıya istek gitmez (tek dosya, dış kaynak yok). Sayfa kendini birkaç saniyede bir yeniler;
`--izle` verilirse betik dosyayı da aynı aralıkla yeniden yazar (Claude arka planda çalıştırır, en çok `--sure` dakika).

Kullanım:
  pano.py --data-dir DD --profile-id N [--campaign-id M] [--out yol.html] [--izle] [--aralik 5] [--sure 180]
  Varsayılan çıktı: DD/profiles/<profil>/pano/kampanya-<M>.html
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "servers" / "ad_memory"))
from common import atomic_write, emit  # noqa: E402
from admem import stages as ST  # noqa: E402

ROLE_TR = {"hook": "açılış", "problem": "sorun", "reveal": "ürünün görünüşü", "product": "ürün", "demo": "kullanım", "proof": "kanıt",
           "offer": "teklif", "endcard": "kapanış", "context": "ortam", "benefit": "fayda", "cta": "çağrı"}
SOURCE_TR = {"footage": "çekim", "still": "fotoğraf", "ai_clip": "AI klip", "ai_image": "AI görsel"}
GEN_STATUS_TR = {"estimated": "fiyatı soruldu", "running": "hazırlanıyor", "completed": "hazır", "failed": "olmadı", "unknown": "durumu belirsiz"}
STAGE_STATE_TR = {"done": "tamam", "awaiting_gate": "onayını bekliyor", "running": "sürüyor", "skipped": "atlandı", "todo": "sırada"}


def _ro(data_dir: Path) -> sqlite3.Connection:
    db = Path(data_dir) / "db" / "ad-memory.sqlite"
    if not db.exists():
        raise SystemExit(json.dumps({"error": "veritabanı bulunamadı", "path": str(db)}, ensure_ascii=False))
    con = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    return con


def _rows(con, sql, args=()) -> list[dict]:
    return [dict(r) for r in con.execute(sql, args).fetchall()]


def collect(data_dir: Path, profile_id: int, campaign_id: int | None = None) -> dict:
    """Panonun gösterdiği veri (salt okuma). Kampanya verilmezse profilin son etkin kampanyası."""
    con = _ro(data_dir)
    try:
        prof = _rows(con, "SELECT id, slug, name, brand_id FROM profiles WHERE id=?", (profile_id,))
        if not prof:
            raise SystemExit(json.dumps({"error": "profil bulunamadı", "profile_id": profile_id}, ensure_ascii=False))
        p = prof[0]
        if campaign_id is None:
            c = _rows(con, "SELECT * FROM campaigns WHERE brand_id=? AND status='active' ORDER BY id DESC LIMIT 1", (p["brand_id"],))
        else:
            c = _rows(con, "SELECT * FROM campaigns WHERE id=? AND brand_id=?", (campaign_id, p["brand_id"]))
        if not c:
            return {"profile": p, "campaign": None}
        c = c[0]
        cy = _rows(con, "SELECT * FROM cycles WHERE campaign_id=? AND cycle=?", (c["id"], c["cycle"]))
        cycle_id = cy[0]["id"] if cy else None
        runs = _rows(con, """SELECT stage, status, output_version FROM stage_runs WHERE campaign_id=? AND stale=0
                             AND (cycle_id=? OR cycle_id IS NULL) ORDER BY id""", (c["id"], cycle_id))
        last: dict[str, dict] = {}
        for r in runs:
            last[r["stage"]] = r
        stages = []
        order = [s for s in ST.CAMPAIGN_STAGES if not (c.get("mode") == "quick" and s in ST.QUICK_SKIPPED)]
        for s in order:
            st = (last.get(s) or {}).get("status") or ("running" if s == c["stage"] else "todo")
            stages.append({"stage": s, "name": ST.STAGE_NAMES.get(s, s), "state": st, "gate": ST.GATES.get(s) if st == "awaiting_gate" else None})
        plan = _rows(con, """SELECT plan_json, version, status FROM edit_plans WHERE campaign_id=? AND cycle_id=? AND purpose='production'
                             ORDER BY id DESC LIMIT 1""", (c["id"], cycle_id)) if cycle_id else []
        scenes = []
        if plan:
            try:
                pj = json.loads(plan[0]["plan_json"])
            except ValueError:
                pj = {}
            for s in pj.get("scenes") or []:
                kinds = [SOURCE_TR.get((l.get("source") or {}).get("kind"), "") for l in s.get("layers") or []]
                text = next((l.get("text") or (l.get("props") or {}).get("text") or (l.get("props") or {}).get("title")
                             for l in s.get("layers") or [] if l.get("text") or (l.get("props") or {}).get("text")
                             or (l.get("props") or {}).get("title")), "")
                scenes.append({"id": s.get("id"), "role": ROLE_TR.get(s.get("role"), s.get("role") or ""), "dur_s": s.get("dur_s"),
                               "kaynak": ", ".join(k for k in dict.fromkeys(kinds) if k), "yazi": str(text)[:80]})
        gens = _rows(con, """SELECT id, kind, model, status, estimate_credits, cost_credits, accepted FROM generations
                             WHERE campaign_id=? ORDER BY id DESC LIMIT 30""", (c["id"],))
        spent = sum((g["cost_credits"] or 0) for g in gens if g["status"] == "completed")
        return {"profile": p, "campaign": {k: c.get(k) for k in ("id", "name", "stage", "cycle", "mode")},
                "stage_name": ST.STAGE_NAMES.get(c["stage"], c["stage"]), "stages": stages, "scenes": scenes,
                "plan_version": plan[0]["version"] if plan else None, "generations": gens, "spent_credits": round(spent, 2),
                "pending": [s for s in stages if s["state"] == "awaiting_gate"]}
    finally:
        con.close()


CSS = """
:root{--bg:#f7f6f3;--fg:#1f1f1f;--mut:#6b6b6b;--card:#fff;--line:#e3e1dc;--ok:#2f7d4f;--wait:#b26a00;--run:#2456a6;--todo:#b9b6ae}
@media (prefers-color-scheme:dark){:root{--bg:#161616;--fg:#eee;--mut:#a3a3a3;--card:#202020;--line:#333;--todo:#555}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:980px;margin:0 auto;padding:20px 16px 40px}h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 10px}
.mut{color:var(--mut)}.ask{background:var(--card);border:2px solid var(--wait);border-radius:10px;padding:12px 14px;margin:16px 0}
.strip{display:flex;flex-wrap:wrap;gap:6px}.st{padding:6px 10px;border-radius:8px;border:1px solid var(--line);background:var(--card);font-size:13px}
.st b{display:block;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.03em}
.done b{color:var(--ok)}.awaiting_gate{border-color:var(--wait)}.awaiting_gate b{color:var(--wait)}.running{border-color:var(--run)}
.running b{color:var(--run)}.todo{opacity:.6}.todo b,.skipped b{color:var(--mut)}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}.card .r{font-weight:600}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
td,th{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;font-size:14px}th{color:var(--mut);font-weight:600}
td.n{text-align:right;font-variant-numeric:tabular-nums}
"""


def render_html(d: dict, refresh_s: int = 5, now: str | None = None) -> str:
    e = html.escape
    now = now or dt.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    head = (f'<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta http-equiv="refresh" content="{int(refresh_s)}"><title>Reklam Atölyesi · İlerleme</title><style>{CSS}</style></head><body><main>')
    if not d.get("campaign"):
        return head + f'<h1>{e(d["profile"]["name"])}</h1><p class="mut">Henüz etkin bir kampanya yok. Kampanya başlayınca bu sayfa dolacak.</p></main></body></html>'
    c = d["campaign"]
    out = [head, f'<h1>{e(c["name"])}</h1>',
           f'<p class="mut">{e(d["profile"]["name"])} · {e(str(c["cycle"]))}. tur · şu an: <b>{e(d["stage_name"])}</b> · son yenileme {e(now)}</p>']
    for g in d["pending"]:
        out.append(f'<div class="ask"><b>Senin onayını bekliyor:</b> {e(g["gate"] or g["name"])}. Sohbete dönüp onaylayabilir ya da değişiklik isteyebilirsin.</div>')
    out.append('<h2>Aşamalar</h2><div class="strip">')
    for s in d["stages"]:
        out.append(f'<div class="st {e(s["state"])}"><b>{e(STAGE_STATE_TR.get(s["state"], s["state"]))}</b>{e(s["name"])}</div>')
    out.append("</div>")
    if d["scenes"]:
        out.append(f'<h2>Videonun sahneleri <span class="mut">(kurgu planı, sürüm {e(str(d["plan_version"]))})</span></h2><div class="cards">')
        for i, s in enumerate(d["scenes"], 1):
            dur = f'{float(s["dur_s"]):.1f}'.replace(".", ",") if s.get("dur_s") is not None else "?"
            out.append(f'<div class="card"><div class="r">{i}. {e(s["role"])}</div><div class="mut">{dur} sn'
                       f'{(" · " + e(s["kaynak"])) if s["kaynak"] else ""}</div>{("<div>“" + e(s["yazi"]) + "”</div>") if s["yazi"] else ""}</div>')
        out.append("</div>")
    out.append("<h2>Ücretli üretimler</h2>")
    if d["generations"]:
        out.append('<table><tr><th>Ne</th><th>Durum</th><th class="n">Tahmini kredi</th><th class="n">Harcanan</th></tr>')
        for g in d["generations"]:
            est = "" if g["estimate_credits"] is None else f'{g["estimate_credits"]:g}'
            cost = "" if g["cost_credits"] is None else f'{g["cost_credits"]:g}'
            what = f'{g["kind"]}' + (f' ({g["model"]})' if g.get("model") else "")
            st = GEN_STATUS_TR.get(g["status"], g["status"]) + (" · kabul edildi" if g.get("accepted") == 1 else " · kullanılmadı" if g.get("accepted") == 0 else "")
            out.append(f'<tr><td>{e(what)}</td><td>{e(st)}</td><td class="n">{e(est)}</td><td class="n">{e(cost)}</td></tr>')
        out.append(f'</table><p class="mut">Bu kampanyada harcanan toplam: <b>{d["spent_credits"]:g}</b> kredi. Bilgisayarda yapılan işler kredi harcamaz.</p>')
    else:
        out.append('<p class="mut">Henüz ücretli bir üretim yok. Her ücretli üretimden önce fiyatı sana sorulur.</p>')
    out.append("</main></body></html>")
    return "".join(out)


def default_out(data_dir: Path, d: dict) -> Path:
    cid = (d.get("campaign") or {}).get("id") or "yok"
    return Path(data_dir) / "profiles" / d["profile"]["slug"] / "pano" / f"kampanya-{cid}.html"


def write_once(data_dir: Path, profile_id: int, campaign_id: int | None, out: str | None, refresh_s: int) -> Path:
    d = collect(data_dir, profile_id, campaign_id)
    path = Path(out) if out else default_out(data_dir, d)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, render_html(d, refresh_s))
    return path


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Canlı ilerleme panosu (yalnızca okur)")
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--profile-id", type=int, required=True)
    ap.add_argument("--campaign-id", type=int)
    ap.add_argument("--out")
    ap.add_argument("--izle", action="store_true")
    ap.add_argument("--aralik", type=int, default=5)
    ap.add_argument("--sure", type=int, default=180)
    a = ap.parse_args()
    dd = Path(a.data_dir)
    path = write_once(dd, a.profile_id, a.campaign_id, a.out, a.aralik)
    emit({"pano": str(path), "kullaniciya": f"İlerlemeyi bu sayfadan izleyebilirsin; sayfa kendini yeniler: {path}"})
    if a.izle:
        end = time.monotonic() + a.sure * 60
        while time.monotonic() < end:
            time.sleep(max(2, a.aralik))
            try:
                write_once(dd, a.profile_id, a.campaign_id, str(path), a.aralik)
            except (sqlite3.Error, OSError):  # veritabanı o an yazılıyorsa bir sonraki turda denenir
                continue


if __name__ == "__main__":
    main()
