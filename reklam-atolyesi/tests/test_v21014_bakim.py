"""2.10.14: bakım ve yayın araçları (dış bağımsız denetim 2.10.10 B9, B13, B14, B15, B16, B17, B18, B19). Sentetik veri; ağ ve
ücretli çağrı yok."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import ROOT
from admem.util import AdMemoryError

sys.path.insert(0, str(ROOT / "scripts" / "setup"))
sys.path.insert(0, str(ROOT / "evals"))
import bagimlilik_denetimi as BD  # noqa: E402
import db_restore as DBR  # noqa: E402
import kor_kiyas as KK  # noqa: E402


# ----------------------------------------------------------------------------- B9: güvenlik taraması
def _proc(stdout, code=1):
    return SimpleNamespace(stdout=stdout, returncode=code)


def test_npm_error_response_is_not_zero_findings(monkeypatch):
    monkeypatch.setattr(BD.shutil, "which", lambda n: "/x/" + n)
    monkeypatch.setattr(BD, "_run", lambda *a, **k: _proc(json.dumps({"error": {"code": "E503", "summary": "Service Unavailable"}})))
    r = BD.npm_report()
    assert r["checked"] is False and "E503" in r["why"]
    monkeypatch.setattr(BD, "_run", lambda *a, **k: _proc(json.dumps({"auditReportVersion": 2})))
    assert BD.npm_report()["checked"] is False  # açık sayısı yoksa denetlendi sayılmaz


def test_high_finding_exits_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(BD, "python_report", lambda: {"checked": True, "count": 0, "high": 0, "items": []})
    monkeypatch.setattr(BD, "npm_report", lambda: {"checked": True, "count": 2, "high": 1, "by_severity": {}})
    assert BD.main() == 1 and "yüksek/kritik" in capsys.readouterr().out
    monkeypatch.setattr(BD, "npm_report", lambda: {"checked": False, "why": "npm yok"})
    assert BD.main() == 0


def test_pip_audit_unreadable_report(monkeypatch):
    monkeypatch.setattr(BD.shutil, "which", lambda n: "/x/" + n)
    monkeypatch.setattr(BD, "_run", lambda *a, **k: _proc("{bozuk", 0))
    assert BD.python_report()["checked"] is False


# ----------------------------------------------------------------------------- B13: hakem
def _fake_claude(tmp_path, body, code):
    exe = tmp_path / "bin" / "claude"
    exe.parent.mkdir()
    exe.write_text(f"#!/bin/sh\ncat >/dev/null\nprintf '%s' '{body}'\nexit {code}\n", encoding="utf-8")
    exe.chmod(0o755)
    return exe


@pytest.mark.skipif(sys.platform.startswith("win"), reason="sahte claude komutu sh betiği")
@pytest.mark.parametrize("body,code", [("", 37), ("karar yazmadım", 0)])
def test_failed_judge_writes_nothing_and_retries(tmp_path, monkeypatch, body, code):
    exe = _fake_claude(tmp_path, body, code)
    monkeypatch.setattr(KK.shutil, "which", lambda n: str(exe))
    pair = tmp_path / "k" / "vaka-1"
    pair.mkdir(parents=True)
    (pair / "hakem.md").write_text("sentetik hakem metni", encoding="utf-8")
    a = SimpleNamespace(dir=str(tmp_path / "k"), model="m", yeniden=False)
    assert KK.cmd_hakem(a) == 1
    assert not (pair / "karar.md").exists()
    exe.write_text("#!/bin/sh\ncat >/dev/null\nprintf '```secim\\nA\\n```'\nexit 0\n", encoding="utf-8")
    assert KK.cmd_hakem(a) == 0  # ikinci çalıştırma atlamaz, yeniden dener
    assert KK.CHOICE.findall((pair / "karar.md").read_text(encoding="utf-8")) == ["A"]


# ----------------------------------------------------------------------------- B14: profil ve dosya adresi
def test_profile_folder_error_rolls_back(store, data_dir, monkeypatch):
    real = Path.mkdir

    def boom(self, *a, **k):
        if "profiles" in self.parts and "sentetik-marka" in self.parts:
            raise PermissionError("erişim reddedildi")
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "mkdir", boom)
    with pytest.raises(AdMemoryError, match="profil kaydedilmedi"):
        store.profile_create("Sentetik Marka")
    assert store.q1("SELECT 1 FROM profiles WHERE slug LIKE 'sentetik-marka%'") is None
    monkeypatch.setattr(Path, "mkdir", real)
    assert store.profile_create("Sentetik Marka")["slug"] == "sentetik-marka"  # "-2" kopyası oluşmaz


@pytest.mark.parametrize("folder", ["veri #1", "a b%20c", "yüzde%"])
def test_readonly_db_paths_with_special_characters(tmp_path, folder):
    d = tmp_path / folder
    d.mkdir()
    db = d / "ad-memory.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE schema_meta(version INTEGER)")
    con.execute("INSERT INTO schema_meta VALUES(7)")
    con.commit()
    con.close()
    assert DBR.quick_check(db) == "ok"
    assert DBR.schema_version(db) == 7


def test_no_handwritten_file_uris_left():
    for base in ("scripts", "hooks", "servers/ad_memory/admem"):
        for f in (ROOT / base).rglob("*.py"):
            assert 'f"file:{' not in f.read_text(encoding="utf-8"), f


# ----------------------------------------------------------------------------- B15, B19: Windows betikleri
def test_updater_only_claims_backup_when_taken():
    t = (ROOT.parent / "musteri-paketi" / "guncelle.ps1").read_text(encoding="utf-8-sig")
    catch = t.split("GÜNCELLEME TAMAMLANAMADI", 1)[1].split("} finally {", 1)[0]
    assert "verileriniz yedeklendi" not in catch
    assert "if ($yedek)" in catch and "$($yedek.FullName)" in catch
    assert "yedeği alınamadı" in catch


def test_root_installer_delegates_to_customer_package():
    root = (ROOT.parent / "kur.ps1").read_text(encoding="utf-8-sig")
    assert 'musteri-paketi\\kur.ps1' in root and "@PSBoundParameters" in root
    assert "Get-KuruluPlugin" not in root  # kurulum mantığının ikinci kopyası yok
    pkg = (ROOT.parent / "musteri-paketi" / "kur.ps1").read_text(encoding="utf-8-sig")
    for p in ("DepoUrl", "PazarAdi", "VeriKlasoru", "DogrulamaYok"):
        assert f"${p}" in root and f"${p}" in pkg


# ----------------------------------------------------------------------------- B16: kabul kaydı
def _eval(tmp_path, scores, closed):
    cases = [{"name": f"vakalar/{n}", "runs": [{"score": s, "costUsd": 0.1} for s in sc]} for n, sc in scores.items()]
    p = tmp_path / "yeni.json"
    p.write_text(json.dumps({"schemaVersion": 1, "claudeVersion": "9.9.9", "costUsd": 1.0, "cases": cases}), encoding="utf-8")
    k = {"plugin_surumu": "0.0.1", "commit": "c" * 40, "vaka_parmak_izi": "x", "vaka_sayisi": len(scores),
         "ham_sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "claudeVersion": "9.9.9", "kosu": 3}
    KK.kayit_yolu(p).write_text(json.dumps(k), encoding="utf-8")
    return str(p)


def test_acceptance_record_hides_closed_names(tmp_path, monkeypatch):
    monkeypatch.setattr(KK, "closed_cases", lambda: {"kapali-x"})
    monkeypatch.setattr(KK, "expected_cases", lambda: {"a", "kapali-x"})
    p = _eval(tmp_path, {"a": [1, 1, 1], "kapali-x": [1, 0.9, 1]}, {"kapali-x"})
    rec = KK.kabul_kaydi(p, "kabul", "sentetik-model", 42)
    assert rec["acik"] == {"a": 1.0} and rec["kapali"]["sayi"] == 1 and "kapali-x" not in json.dumps(rec)
    assert KK.kabul_sorunlari(rec) == []
    assert set(KK.KABUL_ALANLARI) <= set(rec)


def test_acceptance_refused_without_closed_or_below_threshold(tmp_path, monkeypatch):
    monkeypatch.setattr(KK, "expected_cases", lambda: {"a"})
    monkeypatch.setattr(KK, "closed_cases", lambda: set())
    p = _eval(tmp_path, {"a": [1, 1, 1]}, set())
    with pytest.raises(SystemExit, match="kapalı vakalar bulunamadı"):
        KK.kabul_kaydi(p, "kabul", "m", None)
    rec = {a: None for a in KK.KABUL_ALANLARI} | {"karar": "kabul", "esik_alti": 2, "kapali": {"sayi": 3}, "commit": "c",
                                                    "claudeVersion": "v"}
    assert any("eşik altında" in s for s in KK.kabul_sorunlari(rec))


def test_existing_acceptance_records_are_valid():
    for f in sorted((ROOT / "evals" / "kabul").glob("*.json")) if (ROOT / "evals" / "kabul").exists() else []:
        assert KK.kabul_sorunlari(json.loads(f.read_text(encoding="utf-8"))) == [], f


# ----------------------------------------------------------------------------- B17: kapalı vakalar plugin dışında
def test_closed_matrix_read_from_private_clone(tmp_path):
    k = tmp_path / "evals" / "kapali"
    k.mkdir(parents=True)
    (tmp_path / "evals" / "senaryo-matrisi.json").write_text("{}", encoding="utf-8")
    (k / "kapali-matris.json").write_text(json.dumps({"kapali_cases": {"v1": {"product": "P1", "user": "U1", "rubric": []}}}),
                                          encoding="utf-8")
    (k / ".git").mkdir()
    assert set(KK.kapali_matrix(k)) == {"v1"}
    iz1, n = KK.parmak_izi(tmp_path)
    (k / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    assert KK.parmak_izi(tmp_path) == (iz1, n) and n == 0  # gizli klasör vaka ya da parmak izi değil


def test_claude_md_points_to_private_repo():
    t = (ROOT.parent / "CLAUDE.md").read_text(encoding="utf-8")
    assert "kapali-vakalar/" in t and "evals/kapali/" in t


# ----------------------------------------------------------------------------- B18: paketteki sesler
def test_no_mixkit_files_in_package():
    out = subprocess.run(["git", "ls-files", "vendor-skills"], cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
    audio = [p for p in out if p.lower().endswith((".mp3", ".wav", ".ogg", ".flac"))]
    assert audio and all(p.startswith(("vendor-skills/sfx-cc0/", "vendor-skills/sfx-earshot/")) for p in audio)
    lock = json.loads((ROOT / "vendor-skills" / "vendor.lock.json").read_text(encoding="utf-8"))
    apv = next(e for e in lock if e["repo"] == "dlazy-ai/ai-product-video")
    assert "assets/audio" not in apv["parts"]
