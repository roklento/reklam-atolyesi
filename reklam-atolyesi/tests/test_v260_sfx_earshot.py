"""2.6.0: Earshot ses bankası (kodla üretilmiş, MIT) — dosya başına kaynak kaydı, uyarılı sesler varsayılan aramada yok,
kayıtsız/değişmiş dosya listelenmez, arama sırası profil → Kenney → Earshot (2.10.14: Mixkit arşivi çıkarıldı)."""
from __future__ import annotations

import json
import shutil

import sfx_library as SL
from conftest import ROOT

V = ROOT / "vendor-skills" / "sfx-earshot"


def test_bank_recorded_with_license_and_flags():
    allowed = SL.earshot_allowed()
    assert len(allowed) == 252 and sum(ok for _, _, ok in allowed) == 236
    assert (V / "LICENSE").read_text(encoding="utf-8").startswith("MIT License")
    assert "CC0 1.0" in (V / "CREDITS_FIT.md").read_text(encoding="utf-8")
    assert "591fa3e028032e6dce56620a20e932e35667e8d8" in (V / "UPSTREAM.md").read_text(encoding="utf-8")
    fits = [p for p, sid, _ in allowed if sid.startswith("fit/")]
    assert len(fits) == 15
    assert not list(V.rglob("*.wav")) and not list(V.rglob("*.py"))  # yalnız ses ve kayıt; Earshot kodu yok


def test_flagged_hidden_by_default():
    flagged = {sid for _, sid, ok in SL.earshot_allowed() if not ok}
    assert "pro_zip/up_hi" in flagged and len(flagged) == 16
    default = SL.search("zip", limit=100)["results"]
    assert all(r.get("earshot_id") not in flagged for r in default)
    allr = SL.search("zip", limit=100, include_flagged=True)["results"]
    assert any(r.get("flagged") and r["earshot_id"] == "pro_zip/up_hi" for r in allr)


def test_unrecorded_or_changed_file_is_not_listed(tmp_path, monkeypatch):
    d = tmp_path / "sfx-earshot"
    (d / "click").mkdir(parents=True)
    for n in ("double.ogg", "snap.ogg"):
        shutil.copy(V / "click" / n, d / "click" / n)
    (d / "click" / "kayitsiz.ogg").write_bytes(b"OggS")
    rows = [ln for ln in (V / "ATTRIBUTION.md").read_text(encoding="utf-8").splitlines()
            if "`click/double.ogg`" in ln or "`click/snap.ogg`" in ln]
    (d / "ATTRIBUTION.md").write_text("| a | b | c | d | e |\n|---|---|---|---|---|\n" + "\n".join(rows) + "\n", encoding="utf-8")
    with open(d / "click" / "snap.ogg", "ab") as f:
        f.write(b"\0")
    monkeypatch.setattr(SL, "EARSHOT_DIR", d)
    SL.earshot_allowed.cache_clear()
    try:
        assert [p.name for p, _, _ in SL.earshot_allowed()] == ["double.ogg"]
    finally:
        SL.earshot_allowed.cache_clear()


def test_turkish_queries_reach_new_families():
    assert all("logo_sting" in r["path"] for r in SL.search("logo", limit=5)["results"])
    assert any("downlifter" in r["path"] for r in SL.search("iniş", limit=10)["results"])
    assert any("pro_notify" in r["path"] for r in SL.search("bildirim", limit=10)["results"])
    assert any("glitch" in r["path"] and r["source"].startswith("vendor:sfx-earshot") for r in SL.search("bozulma", limit=5)["results"])
    # Kenney "tık" önceliği korunur (1.7.0 davranışı bozulmaz)
    assert all(r["source"].startswith("vendor:sfx-cc0") for r in SL.search("tık", limit=3)["results"])


def test_earshot_ranks_after_kenney():
    res = SL.search("glitch", limit=40)["results"]
    srcs = [r["source"].split(" ")[0] for r in res if r["score"] == res[0]["score"]]
    order = [s for i, s in enumerate(srcs) if s not in srcs[:i]]
    assert order.index("vendor:sfx-cc0") < order.index("vendor:sfx-earshot")


def test_vendor_record_generated():
    lock = {e["repo"]: e for e in json.loads((ROOT / "vendor-skills" / "vendor.lock.json").read_text(encoding="utf-8"))}
    e = lock["Leonxlnx/earshot"]
    assert e["status"] == "generated" and e["license"] == "MIT" and e["commit"].startswith(e["pin"])
    notices = (ROOT / "vendor-skills" / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "Leonxlnx/earshot" in notices and "sfx-earshot" in notices
    build = (ROOT / "scripts" / "setup" / "sfx_earshot_build.py").read_text(encoding="utf-8")
    assert e["commit"] in build
