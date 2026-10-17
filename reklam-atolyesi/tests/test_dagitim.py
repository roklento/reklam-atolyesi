"""Dağıtılan kurulum: MCP başlatma biçimi, manifestte makine yolu olmaması, güncelleme modu ve görsel karşılaştırma (12.7, 12.13)."""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

import doctor as DR
import gen_config as GC
import kurulum_dogrula as KD
import manifest as MF
import mcp_probe as MP
from conftest import ROOT

ABS = re.compile(r"[A-Za-z]:[\\/]|\\\\|/(Users|home)/")


def _strings(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)
    elif isinstance(obj, str):
        yield obj


def test_mcp_json_exec_form_without_uv():
    for os_name, py in (("windows", "/.venv/Scripts/python.exe"), ("posix", "/.venv/bin/python")):
        srv = GC.mcp_json(os_name)["mcpServers"]["ad-memory"]
        assert srv["command"] == "${user_config.data_dir}" + py
        assert srv["args"] == ["${CLAUDE_PLUGIN_ROOT}/servers/ad_memory/server.py"]
        assert "uv" not in json.dumps(srv).replace("${user_config", "")
        assert not any(ABS.search(s) for s in _strings(srv))
    # depodaki .mcp.json üreticinin çıktısıdır (hangi işletim sistemi için üretildiğini doctor ayrıca denetler)
    on_disk = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    assert on_disk in (GC.mcp_json("windows"), GC.mcp_json("posix"))


def test_doctor_resolves_mcp_command_with_spaces(data_dir):
    argv, probs = DR.mcp_server_command(data_dir)
    assert not probs
    assert Path(argv[0]).parent.parent == data_dir / ".venv"
    assert Path(argv[1]) == ROOT / "servers" / "ad_memory" / "server.py"


def test_server_starts_by_script_path_outside_plugin(tmp_path):
    # Claude Code sunucuyu oturum klasöründen başlatır: kod yalnızca betik yoluyla bulunmalı (sanal ortamda proje kurulu olmasa da).
    out = asyncio.run(MP.probe(ROOT, tmp_path / "probe veri", None, None))
    assert out["server"] == "ad-memory" and "system_manifest_get" in out["tools"]


def test_redact_paths():
    src = {"a": "D:\\veri\\.selftest\\profiles\\marka-a\\kare.png", "b": ["/Users/x/proj/out.mp4", "göreli/yol.png", "metin: C: değil"],
           "c": {"d": "C:/Users/Ad Soyad/AppData/x.json"}, "n": 3,
           "error": "SystemExit: render başarısız: E:\\iş klasörü\\a b\\çıktı.mp4 bulunamadı; bkz. /opt/app/log.txt",
           "trace": "File \"C:\\x\\y.py\", line 1", "C:\\anahtar\\yol.json": 1, "u": "file:///home/x/a.png ve https://example.com/tmp/x"}
    r = MF.redact_paths(src)
    assert r["a"] == "<data_dir>/.selftest/profiles/marka-a/kare.png"
    assert r["b"] == ["<yol>/out.mp4", "göreli/yol.png", "metin: C: değil"]
    assert r["c"]["d"] == "<yol>/x.json" and r["n"] == 3
    assert r["error"] == "SystemExit: render başarısız: <yol>/çıktı.mp4 bulunamadı; bkz. <yol>/log.txt"
    assert "trace" not in r and "<yol>/yol.json" in r
    assert r["u"] == "<yol>/a.png ve https://example.com/tmp/x"  # URL yolu makine yolu değildir
    assert MF.find_abs_paths(r) == []
    # klasörde biten yol (kullanıcı adı), Python repr'indeki çift ters bölü ve uzun yol öneki
    for s, want in (("izin yok: C:\\Users\\kullanici", "izin yok: <yol>"), ("/home/kullanici", "<yol>"),
                    ("No such file: 'C:\\\\Users\\\\Ad Soyad\\\\proje\\\\yok.mp4'", "No such file: '<yol>/yok.mp4'"),
                    ("\\\\?\\C:\\Users\\kullanici\\x.json okunamadı", "<yol>/x.json okunamadı")):
        assert MF.redact_paths(s) == want, s


def test_distributed_manifest_has_no_machine_paths():
    m = json.loads((ROOT / "system_manifest.json").read_text(encoding="utf-8"))
    bad = MF.find_abs_paths(m)
    assert not bad, bad[:5]


def test_data_dir_contents_update_mode(data_dir):
    (data_dir / "profiles" / "marka-a").mkdir(parents=True)
    (data_dir / ".sessions").mkdir()
    (data_dir / ".sessions" / "oturum.json").write_text("{}", encoding="utf-8")
    r = DR.Report()
    DR.check_data_dir_contents(r, data_dir, final=True)
    assert r.items[-1]["ok"] is False  # yeni kurulum: data_dir yalnızca 12'deki liste
    r = DR.Report()
    DR.check_data_dir_contents(r, data_dir, final=True, update=True)
    assert r.items[-1]["ok"] is True  # güncelleme: kullanıcı verisi beklenir
    (data_dir / ".selftest").mkdir()
    r = DR.Report()
    DR.check_data_dir_contents(r, data_dir, final=True, update=True)
    assert r.items[-1]["ok"] is False  # duman testi artığı kalmamalı


def test_visual_comparison(tmp_path):
    from PIL import Image, ImageDraw
    same = KD.compare_turkish(KD.TR_REFERENCE)
    assert same["ok"] and same["identical"]
    im = Image.open(KD.TR_REFERENCE).convert("RGB")
    ImageDraw.Draw(im).rectangle((100, 600, 980, 1300), fill=(255, 0, 0))
    bad = tmp_path / "bozuk.png"
    im.save(bad)
    assert KD.compare_turkish(bad)["ok"] is False
    g = Image.open(KD.GALLERY_REFERENCE).convert("RGB")
    ImageDraw.Draw(g).rectangle((0, 0, 739, 349), fill=(0, 0, 0))  # tek bileşen bloğu bozuk
    gb = tmp_path / "galeri.png"
    g.save(gb)
    res = KD.compare_gallery(gb)
    assert res["ok"] is False and res["low_blocks"] and res["low_blocks"][0]["block"] == [0, 0]
    assert KD.compare_gallery(KD.GALLERY_REFERENCE)["ok"] is True


def test_review_record_without_tty_does_not_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdin", None)
    rec = KD.review_record({"ok": False}, "kare", [], True, "?")
    assert rec["ok"] is False and "yapılmadı" in rec["by"]
    rec = KD.review_record({"ok": True}, "kare", [], False, "?")
    assert rec["ok"] is True and rec["by"].startswith("otomatik karşılaştırma")


def test_support_summary_masks_user_folder():
    home = str(Path.home())
    r = KD.mask_home({"work": home + "\\AppData\\Local\\Temp\\x", "l": [home.replace("\\", "/") + "/a"], "n": 1})
    assert all(home not in s and home.replace("\\", "/") not in s for s in _strings(r))
    assert r["work"].startswith("%USERPROFILE%") and r["n"] == 1


def test_plugin_version_from_manifest():
    assert DR.plugin_version() == json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]


def test_global_skills_separate_check_and_user_decision(tmp_path, monkeypatch, data_dir):
    """Çakışan genel skill'ler ayrı doctor maddesidir; 'dokunma' sapma kaydı olur, 'taşı' silmeden yedeğe taşır (1.4.1)."""
    home = tmp_path / "ev"
    (home / ".claude" / "skills" / "remotion-render").mkdir(parents=True)
    (home / ".claude" / "skills" / "baska-skill").mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    assert DR.global_skill_clash() == ["remotion-render"]
    rec, det = KD.handle_global_skills(data_dir, "sor", interactive=False)
    assert rec is None and "verilmedi" in det["karar"]
    rec, det = KD.handle_global_skills(data_dir, "birak", interactive=False)
    assert rec["check"] == "global_skills" and rec["decided_by"] == "user" and rec["status"] == "accepted"
    r = DR.Report()
    DR.check_global_skills(r, {"global_skills": rec["deviation"]})
    assert r.items[0]["ok"] is False and r.items[0]["accepted_deviation"] and not r.blocking()
    rec, det = KD.handle_global_skills(data_dir, "tasi", interactive=False)
    assert rec is None and det["tasinan"] == ["remotion-render"]
    assert (home / ".claude" / "skills-yedek" / "remotion-render").is_dir() and DR.global_skill_clash() == []


def test_kurulum_ps1_survives_inherited_strict_mode():
    """Claude Code'u kuran resmi betik Set-StrictMode -Version Latest açar ve kur.ps1 kapsamında kalır (1.4.0 ilk kurulum hatası)."""
    t = (ROOT / "scripts" / "setup" / "windows" / "kurulum.ps1").read_text(encoding="utf-8-sig")
    body = re.split(r"^\)\s*$", t, maxsplit=1, flags=re.M)[1]  # param(...) bloğundan sonrası
    first = [ln.strip() for ln in body.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert "Set-StrictMode -Off" in first[:3]
    assert "$miss = Get-EksikFfmpegFiltreleri" not in t and t.count("$miss = @(Get-EksikFfmpegFiltreleri)") == 2
