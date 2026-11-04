"""2.9.0: kullanıcıya görünen her yerde sade ve net dil (KURALLAR K16, skills/ref-sade-dil).

Kodun ürettiği müşteri metinleri (aşama adları, ana menü, hata sorusu, hata defteri özeti, ses kurulumu, kurulum ve güncelleme
mesajları, kullanım kılavuzu, komut açıklamaları, belge şablonları, koçluk raporu) ve skill'lerin onay/geçiş mesajı kalıpları
`scripts/lib/sade_dil.py` taramasından bulgusuz geçmeli. Modelin serbest cevabını değerlendirme seti sınar (evals/rubrik.md R3).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from admem import feedback as FB
from admem import stages as ST
from conftest import ROOT, make_active_profile

sys.path.insert(0, str(ROOT / "scripts" / "lib"))
sys.path.insert(0, str(ROOT / "hooks"))
import sade_dil as SD  # noqa: E402

PKG = ROOT.parent / "musteri-paketi"


def _clean(text: str) -> list[dict]:
    """HTML yorumları (yazım notu), satır içi kod ve {{…}} doldurma talimatlarının içi dışında kalan metin taranır."""
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", " ", text)
    return SD.scan_text(text)


def _assert_plain(where: str, text: str, allow: set[str] | None = None):
    found = [f for f in _clean(text) if f["match"].lower() not in {a.lower() for a in (allow or set())}]
    assert not found, f"{where}: " + "; ".join(f"«{f['match']}» ({f['hint']})" for f in found[:8])


def test_scanner_catches_jargon_and_respects_explanations():
    kinds = {f["kind"] for f in SD.scan_text("S03'te kalmıştık; hook'lar bekliyor → devam")}
    assert kinds == {"iç_ad", "terim", "dizi"}
    assert SD.scan_text("Bir satışın reklam maliyeti (CPA) 120 TL.") == []
    assert SD.scan_text("Çekim S01 ve S02 çekimi hazır.") == []
    assert SD.scan_text("onayın gerekiyor") == [] and SD.scan_text("kapıda bekliyor")
    assert SD.scan_text("a · b · c · d")[0]["kind"] == "dizi"
    assert SD.scan_text("gate_approve(...) çağır")


def test_customer_facing_texts_are_plain(store, tmp_path):
    # aşama adları ve onay konuları (menüde, belge başlığında ve durum satırında görünür)
    for code, name in {**ST.STAGE_NAMES, **{f"gate:{k}": v for k, v in ST.GATES.items()}}.items():
        _assert_plain(f"aşama adı {code}", name)
    # ana menü: sabit maddeler ve koddan üretilen üst satır
    menu = json.loads((ROOT / "hooks" / "menu.json").read_text(encoding="utf-8"))
    for it in menu["items"]:
        _assert_plain(f"menü {it['no']}", it["label"])
    _assert_plain("menü alt satırı", menu["footer"])
    make_active_profile(store)
    r = store.menu_render("plain-session-0001")
    assert r["kind"] == "menu"
    _assert_plain("menü metni", r["text"])
    assert "→" not in r["text"] and r["text"].splitlines()[0].endswith(".")
    # hata sorusu: tek, sade soru; "sen" diliyle
    import error_notify as EN
    import plugin_mode as PM
    sid = "plain-err-0001"
    PM.update_session(tmp_path, sid, lambda st: {**st, "plugin_mode": True})
    out = EN.notify(tmp_path, {"tool_name": PM.OWN_SERVER_PREFIX + "stage_complete", "error": "x", "session_id": sid})
    msg = out["systemMessage"]
    _assert_plain("hata sorusu", msg)
    assert "hata defterine" in msg and "geliştiriciye" in msg and "İstersen" in msg and "nız" not in msg
    # hata defteri özeti: aşama kodu yerine adı
    rep = {"period_days": 30, "plugin_version": "2.9.0", "stages": {"S01": {"completed": 1}}, "stuck": [], "errors": {"count": 1},
           "imzalar": [{"asama": "S13", "sinyal": "kreatif_red", "kod": "-", "hucre": "P1-3.U1", "n": 2},
                       {"asama": "-", "sinyal": "arac_hatasi", "kod": "x", "hucre": "-", "n": 1}]}
    lines = FB.summary_lines(rep)
    _assert_plain("hata defteri özeti", "\n".join(lines))
    assert any("Son kontrol adımında" in ln for ln in lines)
    # ses kurulumu önerileri
    import tts_local as TL
    say = TL.install_offer(tmp_path)["say"]
    _assert_plain("ses kurulumu", say)
    # komut açıklamaları (/ menüsünde görünür)
    for f in sorted((ROOT / "commands").glob("*.md")):
        desc = re.search(r'^description:\s*"(.*)"\s*$', f.read_text(encoding="utf-8-sig"), re.M).group(1)
        _assert_plain(f"komut {f.stem}", desc)


def _ps_messages(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig")
    pat = r"(?:Write-Host|Write-Adim|Write-Tamam|Write-Uyari|Stop-Kurulum|throw|Read-EvetHayir)\s*\(?\s*(['\"])(.+?)\1"
    return [m.group(2) for m in re.finditer(pat, text)]


@pytest.mark.parametrize("rel", ["musteri-paketi/kur.ps1", "musteri-paketi/guncelle.ps1", "kur.ps1",
                                 "reklam-atolyesi/scripts/setup/windows/kurulum.ps1"])
def test_installer_messages_are_plain(rel):
    path = ROOT.parent / rel
    if not path.exists():
        pytest.skip(f"{rel} bu kopyada yok")
    msgs = _ps_messages(path)
    assert msgs
    for m in msgs:
        _assert_plain(f"{rel}", m)
        assert "sağlayıcı" not in m and "bağımlılık" not in m.lower(), m


def test_usage_guide_is_plain():
    path = PKG / "KULLANIM.txt"
    if not path.exists():
        pytest.skip("müşteri paketi bu kopyada yok")
    text = path.read_text(encoding="utf-8-sig")
    _assert_plain("KULLANIM.txt", text)
    for word in ("bağımlılık", "veritabanı geçiş", "render", "doctor", "galeri", "sağlayıcı"):
        assert word not in text.lower(), word


def test_document_templates_are_plain():
    for f in sorted((ROOT / "templates" / "reports").glob("*.md")):
        body = f.read_text(encoding="utf-8")
        # Meta ekranındaki resmi ad ("Advantage+ kreatif iyileştirmeleri") parantez dışında kalabilir: kullanıcı Meta'da bu adı arar
        # çekim menüsündeki çekim numaraları (S01…) aşama kodu değildir; dosya adlarında da aynen kullanılır
        allow = {"yayin-paketi.md": {"kreatif"}, "cekim-rehberi.md": {"S01"}}.get(f.name)
        _assert_plain(f"şablon {f.name}", body, allow=allow)
        assert "<!--" in body, f"{f.name}: yazım notu HTML yorumu olmalı (belgeye kopyalanmaz)"


def test_coach_report_is_plain(store):
    import coach as CO
    import report as RP
    from test_analytics import build_campaign

    pid, cid, cyid = build_campaign(store)
    snap = store.decision_input_snapshot(pid, cid, cyid)
    an = CO.analyze(snap["path"])
    md = RP.build(an, json.load(open(snap["path"], encoding="utf-8")), {}, None, None, None)
    body = md.split("\n## ", 1)[1]  # başlık satırı kampanya adını taşır
    _assert_plain("koçluk raporu", body, allow={"kreatif"})  # yalnızca "Advantage+ kreatif iyileştirmeleri" (Meta'daki resmi ad)
    for sec in RP.SECTIONS:
        assert f"## {sec}" in md


def _kapi(md: str) -> str:
    md = md.replace("\r\n", "\n")
    m = re.search(r"^## Kapı mesajı\n(.*?)(?=^## |\Z)", md, re.S | re.M)
    return m.group(1) if m else ""


def test_gate_messages_are_plain():
    """Her aşama skill'inin onay/geçiş mesajı kalıbı: tırnak içindeki kullanıcı cümleleri sade; onay isteyen aşamada soru var."""
    gated_skills = {ST.SKILLS[s] for s in ST.GATES}
    seen = 0
    for f in sorted((ROOT / "skills").glob("*/SKILL.md")):
        kapi = _kapi(f.read_text(encoding="utf-8"))
        if not kapi:
            continue
        quotes = SD.quoted_user_text(kapi)
        for q in quotes:
            _assert_plain(f"{f.parent.name} kapı mesajı", q)
            seen += 1
        if f.parent.name in gated_skills:
            assert any("?" in q for q in quotes), f"{f.parent.name}: onay isteyen mesajda soru yok"
    assert seen >= 25


def test_plain_language_rule_reaches_every_session():
    import plugin_mode as PM
    block = PM.rules_block(ROOT / "KURALLAR.md")
    assert "K16" in block and "ref-sade-dil" in block
    sk = (ROOT / "skills" / "ref-sade-dil" / "SKILL.md").read_text(encoding="utf-8")
    for part in ("## 1. Temel kurallar", "## 3. Sözlük", "## 4. Örnekler"):
        assert part in sk, part
    nav = (ROOT / "skills" / "navigator" / "SKILL.md").read_text(encoding="utf-8")
    assert "K16" in nav and "ref-sade-dil" in nav
