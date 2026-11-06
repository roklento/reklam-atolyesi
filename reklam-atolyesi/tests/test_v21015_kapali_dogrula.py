"""2.10.15: kapalı vaka doğrulayıcısı (evals/kapali_dogrula.py). Sentetik vakalar; ağ ve ücretli çağrı yok.

Doğrulayıcı vaka metnini yazdırmadan biçimi ve çalışırlığı denetler. Buradaki vakalar yalnızca biçim örneğidir; gerçek kapalı vakalar
değildir ve hiçbir senaryoyu önermez.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from conftest import ROOT

sys.path.insert(0, str(ROOT / "evals"))
import kapali_dogrula as KD  # noqa: E402

MATRIX = json.loads((ROOT / "evals" / "senaryo-matrisi.json").read_text(encoding="utf-8"))
GIRIS = ("Sen reklam-atolyesi plugin'i açık bir oturumdasın (plugin modu açık). Bu bir değerlendirme senaryosudur: ad-memory ya da Meta\n"
         "araçlarını ÇAĞIRMA ve kayıt yapma; gerekirse plugin'in skill'lerini ve `KURALLAR.md` dosyasını oku. Senaryodaki durumu araç\n"
         "sonuçlarıyla öğrenmiş gibi kabul et ve yalnızca kullanıcıya vereceğin cevabı Türkçe yaz.\n")
GIZLI = "zxqv"  # sentetik vakalarda gizli kalması gereken bir sözcük; hiçbir çıktıda görünmemeli


def _hucreler(n: int) -> list[tuple[str, str]]:
    acik = {(c["product"], c["user"]) for c in MATRIX["eval_cases"].values()}
    acik_u = {c["user"] for c in MATRIX["eval_cases"].values()}
    yeni_u = sorted(set(MATRIX["users"]) - acik_u)
    out: list[tuple[str, str]] = []
    for p in sorted(MATRIX["products"]):
        for u in yeni_u + sorted(MATRIX["users"]):
            if (p, u) not in acik and u not in {x[1] for x in out} and p not in {x[0] for x in out}:
                out.append((p, u))
                break
    assert len(out) >= n and (not yeni_u or out[0][1] in yeni_u)
    return out[:n]


def _yaz(dizin: Path, n: int = 5) -> dict:
    kayit = {}
    for i, (p, u) in enumerate(_hucreler(n), 1):
        ad = f"sentetik-ornek-{i}"
        d = dizin / ad
        (d / "graders").mkdir(parents=True)
        pa, ua = MATRIX["products"][p]["ad"], MATRIX["users"][u]["ad"]
        (d / "prompt.md").write_text(
            "---\nmax_turns: 12\nallowed_tools: [Read, Glob, Grep, Skill]\n---\n\n" + GIRIS
            + f"\nSenaryo: {p} ({pa}) × {u} ({ua}).\n\nDurum: {GIZLI} örnek {i} durumu, sayı {i * 7}.\n\n"
            f"Kullanıcı: \"{GIZLI} örnek {i} sorusu nedir?\"\n", encoding="utf-8")
        for kod, dosya in (("R1", "r1-kural-uyumu.md"), ("R4", "r4-durustluk.md")):
            (d / "graders" / dosya).write_text(
                f"---\ntype: llm\nweight: 1\n---\n\n{kod} ölçüt başlığı (evals/rubrik.md).\n\n"
                f"Geçer: {GIZLI} ölçütü {i} karşılanıyor. Kalır: {GIZLI} ölçütü {i} karşılanmıyor.\n", encoding="utf-8")
        kayit[ad] = {"product": p, "user": u, "rubric": ["R1", "R4"]}
    (dizin / KD.KAYIT).write_text(json.dumps({"kapali_cases": kayit}, ensure_ascii=False, indent=2), encoding="utf-8")
    return kayit


def _calistir(dizin: Path, capsys, *ek: str) -> tuple[int, str]:
    kod = KD.main(["--dizin", str(dizin), *ek])
    return kod, capsys.readouterr().out


def test_valid_set_passes_and_prints_no_content(tmp_path, capsys):
    _yaz(tmp_path)
    kod, out = _calistir(tmp_path, capsys)
    assert kod == 0, out
    assert "GEÇERLİ: 5 vaka, 10 ölçüt dosyası" in out
    assert GIZLI not in out and "sentetik-ornek" not in out


def test_missing_field_names_file_and_field_without_content(tmp_path, capsys):
    kayit = _yaz(tmp_path)
    ad = sorted(kayit)[1]
    pf = tmp_path / ad / "prompt.md"
    pf.write_text(pf.read_text(encoding="utf-8").replace("Durum:", "Anlatım:"), encoding="utf-8")
    g = tmp_path / ad / "graders" / "r4-durustluk.md"
    g.write_text(g.read_text(encoding="utf-8").replace("weight: 1\n", "").replace("Kalır:", "Olmaz:"), encoding="utf-8")
    kod, out = _calistir(tmp_path, capsys)
    assert kod == 1
    assert "vaka 2 · prompt.md: \"Durum:\" ile başlayan satır yok" in out
    assert "vaka 2 · 2. ölçüt dosyası: ön bilgide alan eksik: weight" in out
    assert "\"Kalır:\" tarifi yok" in out
    assert GIZLI not in out and ad not in out
    kod, out = _calistir(tmp_path, capsys, "--adlarla")
    assert f"{ad} · r4-durustluk.md: ön bilgide alan eksik: weight" in out and GIZLI not in out


def test_registry_rules(tmp_path, capsys):
    kayit = _yaz(tmp_path)
    acik_ad, acik = next(iter(MATRIX["eval_cases"].items()))
    a, b = sorted(kayit)[:2]
    kayit[a] = {"product": acik["product"], "user": acik["user"], "rubric": ["R1", "R4"]}  # açık vakayla aynı hücre
    kayit[b] = dict(kayit[b], rubric=["R1"], alinti=["x"])
    (tmp_path / KD.KAYIT).write_text(json.dumps({"kapali_cases": kayit}), encoding="utf-8")
    (tmp_path / "fazla-klasor").mkdir()
    kod, out = _calistir(tmp_path, capsys)
    assert kod == 1
    assert "hücresi bir açık vakada zaten var" in out
    assert "beklenmeyen alan: alinti" in out and "2 ya da 3 ölçüt" in out
    assert "kayıtta olmayan bir ölçüt dosyası var (R4)" in out
    assert "kayıtta olmayan bir vaka klasörü var (adı gizli)" in out
    assert "Senaryo:\" satırı kayıttaki hücreyle tutmuyor" in out


def test_needs_three_cases_and_a_new_user(tmp_path, capsys):
    kayit = _yaz(tmp_path, 2)
    kod, out = _calistir(tmp_path, capsys)
    assert kod == 1 and "en az 3 olmalı" in out
    acik_u = {c["user"] for c in MATRIX["eval_cases"].values()}
    if set(MATRIX["users"]) - acik_u:
        t = tmp_path / "ikinci"
        k2 = _yaz(t, 5)
        for ad, v in k2.items():
            if v["user"] not in acik_u:
                del k2[ad]
                import shutil
                shutil.rmtree(t / ad)
                break
        (t / KD.KAYIT).write_text(json.dumps({"kapali_cases": k2}), encoding="utf-8")
        kod, out = _calistir(t, capsys)
        assert kod == 1 and "hiçbir açık vakada olmayan bir kullanıcı" in out


def test_tools_extra_keys_bom_and_nested_prompt(tmp_path, capsys):
    kayit = _yaz(tmp_path)
    a, b, c = sorted(kayit)[:3]
    pf = tmp_path / a / "prompt.md"
    pf.write_text(pf.read_text(encoding="utf-8").replace("Skill]", "Skill, Bash]").replace("max_turns: 12", "max_turns: 12\nruns: 5"),
                  encoding="utf-8")
    pb = tmp_path / b / "prompt.md"
    pb.write_bytes(b"\xef\xbb\xbf" + pb.read_bytes())
    (tmp_path / c / "graders" / "prompt.md").write_text("x", encoding="utf-8")
    kod, out = _calistir(tmp_path, capsys)
    assert kod == 1
    assert "allowed_tools yalnızca Read, Glob, Grep, Skill" in out and "beklenmeyen alan: runs" in out
    assert "BOM ile başlıyor" in out and "ikinci bir prompt.md" in out


def test_memorization_checks(tmp_path, capsys):
    kayit = _yaz(tmp_path)
    a, b, c = sorted(kayit)[:3]
    # plugin metninden 6+ kelimelik bir satır (ezber denetiminin izlediği dosyalardan)
    satir = next(t for _, _, t in KD.EZ.all_lines() if len(KD.EZ.words(t)) >= 10)
    pa = tmp_path / a / "prompt.md"
    pa.write_text(pa.read_text(encoding="utf-8") + "\n" + satir + "\n", encoding="utf-8")
    # yalnızca bir açık vakada geçen bir cümle
    acik_ad = sorted(MATRIX["eval_cases"])[0]
    acik_metin = (ROOT / "evals" / "vakalar" / acik_ad / "prompt.md").read_text(encoding="utf-8")
    durum = next(ln for ln in acik_metin.splitlines() if ln.startswith("Durum:"))
    pb = tmp_path / b / "prompt.md"
    pb.write_text(pb.read_text(encoding="utf-8") + "\n" + durum + "\n", encoding="utf-8")
    kod, out = _calistir(tmp_path, capsys)
    assert kod == 1
    assert "vaka 1: plugin metniyle" in out and "6 kelimelik ortak parça" in out
    assert "vaka 2: açık vakalardan" in out
    assert satir.strip()[:30] not in out and durum[:30] not in out


def test_unreadable_registry_exits_2(tmp_path, capsys):
    kod, out = _calistir(tmp_path, capsys)
    assert kod == 2 and "kapali-matris.json yok" in out
    (tmp_path / KD.KAYIT).write_text("{bozuk", encoding="utf-8")
    kod, out = _calistir(tmp_path, capsys)
    assert kod == 2 and "geçerli JSON değil" in out


def test_open_cases_would_not_pass_as_closed(tmp_path, capsys):
    """Açık vakaları kapalı diye kopyalamak doğrulayıcıdan geçmez (ad ve hücre çakışır)."""
    import shutil
    kayit = {}
    for ad, c in list(MATRIX["eval_cases"].items())[:3]:
        shutil.copytree(ROOT / "evals" / "vakalar" / ad, tmp_path / ad)
        kayit[ad] = {k: c[k] for k in ("product", "user", "rubric")}
    (tmp_path / KD.KAYIT).write_text(json.dumps({"kapali_cases": kayit}), encoding="utf-8")
    kod, out = _calistir(tmp_path, capsys)
    assert kod == 1 and "bu ad açık vakalarda da var" in out


@pytest.mark.skipif(not (ROOT / "evals" / "kapali" / KD.KAYIT).exists(), reason="kapalı vaka kopyası yok (CI)")
def test_local_closed_copy_is_valid(capsys):
    """Yayın öncesi kopya yerindeyse doğrulayıcıdan geçer (içerik yazdırılmaz)."""
    kod, out = _calistir(ROOT / "evals" / "kapali", capsys)
    assert kod == 0, out


def test_acceptance_refused_when_closed_set_invalid(tmp_path, monkeypatch, capsys):
    """kor_kiyas.py kabul, doğrulayıcıdan geçmeyen kapalı vakalarla kabul kaydı yazmaz ve içeriği yazdırmaz."""
    import hashlib
    import kor_kiyas as KK
    kdir = tmp_path / "kapali"
    kdir.mkdir()
    kayit = _yaz(kdir)
    monkeypatch.setattr(KK, "KAPALI", kdir)
    acik = set(MATRIX["eval_cases"])
    cases = [{"name": n, "runs": [{"score": 1.0, "costUsd": 0.1}] * 3} for n in sorted(acik | set(kayit))]
    p = tmp_path / "yeni.json"
    p.write_text(json.dumps({"schemaVersion": 1, "claudeVersion": "9.9.9", "costUsd": 1.0, "cases": cases}), encoding="utf-8")
    k = {"plugin_surumu": "0.0.1", "commit": "c" * 40, "vaka_parmak_izi": "x", "vaka_sayisi": 1,
         "ham_sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "claudeVersion": "9.9.9", "kosu": 3}
    KK.kayit_yolu(p).write_text(json.dumps(k), encoding="utf-8")
    assert KK.kabul_kaydi(str(p), "kabul", "m", None)["kapali"]["sayi"] == 5  # geçerli set: kayıt kurulur
    g = kdir / sorted(kayit)[0] / "graders" / "r1-kural-uyumu.md"
    g.write_text(g.read_text(encoding="utf-8").replace("type: llm", "type: kod"), encoding="utf-8")
    with pytest.raises(SystemExit, match="doğrulayıcıdan geçmedi") as e:
        KK.kabul_kaydi(str(p), "kabul", "m", None)
    assert GIZLI not in str(e.value)


def test_local_closed_copy_does_not_change_manifest_hash(tmp_path):
    """Yayın öncesi evals/kapali/ kopyası yerindeyken manifestin evals bileşen özeti değişmez (kopya plugin'in parçası değildir)."""
    import shutil
    sys.path.insert(0, str(ROOT / "scripts" / "setup"))
    import manifest as MF
    kok = tmp_path / "eklenti"
    shutil.copytree(ROOT / "evals", kok / "evals", ignore=shutil.ignore_patterns("results", "kapali", "__pycache__"))
    once = MF.tree_hash(kok / "evals", ("*.md", "*.json", "*.yaml", "*.py"), frozenset({"results", "kapali"}))
    _yaz(kok / "evals" / "kapali")
    assert MF.tree_hash(kok / "evals", ("*.md", "*.json", "*.yaml", "*.py"), frozenset({"results", "kapali"})) == once
    src = (ROOT / "scripts" / "setup" / "manifest.py").read_text(encoding="utf-8")
    assert 'frozenset({"results", "kapali"})' in src
