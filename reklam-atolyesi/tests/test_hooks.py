"""Hook birim testleri (spec 13.6, 9.3, 12.10): gerçek yorumlayıcıyla çalıştırma, hata durumunda engelleme, kapsam testi."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import ROOT, make_active_profile, run_hook

SID = "test-session-0001"


def deny_of(out):
    return out and out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def ctx_of(out):
    return (out or {}).get("hookSpecificOutput", {}).get("additionalContext", "")


@pytest.fixture
def ddir(store, data_dir):
    return data_dir


def enter_mode(ddir, sid=SID):
    return run_hook("navigator.py", {"session_id": sid, "hook_event_name": "UserPromptSubmit", "prompt": "Reklam Atölyesi", "prompt_id": "p1"}, ddir)


# --- navigator ----------------------------------------------------------------------
def test_navigator_scope_and_trigger(ddir):
    assert run_hook("navigator.py", {"session_id": SID, "hook_event_name": "UserPromptSubmit", "prompt": "merhaba"}, ddir) is None
    out = enter_mode(ddir)
    c = ctx_of(out)
    assert "plugin modu: açık" in c and "profil sayısı: 0" in c and SID in c
    s = json.loads((ddir / ".sessions" / f"{SID}.json").read_text(encoding="utf-8"))
    assert s["plugin_mode"]


def test_navigator_command_turkish_i_and_exit(ddir):
    out = run_hook("navigator.py", {"session_id": "s-cmd-0002", "hook_event_name": "UserPromptSubmit", "prompt": "/reklam-atolyesi:durum"}, ddir)
    assert "Komut: /reklam-atolyesi:durum" in ctx_of(out)
    out = run_hook("navigator.py", {"session_id": "s-cmd-0003", "hook_event_name": "UserPromptSubmit", "prompt": "REKLAM ATÖLYESİ"}, ddir)
    assert "plugin modu" in ctx_of(out)
    out = run_hook("navigator.py", {"session_id": "s-cmd-0003", "hook_event_name": "UserPromptSubmit", "prompt": "Menüden çık"}, ddir)
    assert "kapatıldı" in ctx_of(out)
    assert run_hook("navigator.py", {"session_id": "s-cmd-0003", "hook_event_name": "UserPromptSubmit", "prompt": "selam"}, ddir) is None


def test_navigator_number_resolves_last_menu(ddir, store):
    enter_mode(ddir)
    store.session_menu_set(SID, ["Yeni video reklam oluştur", "Neler yaptık"])
    out = run_hook("navigator.py", {"session_id": SID, "hook_event_name": "UserPromptSubmit", "prompt": "2", "prompt_id": "p2"}, ddir)
    assert "«Neler yaptık»" in ctx_of(out)


def test_navigator_expansion_dedupe(ddir):
    run_hook("navigator.py", {"session_id": SID, "hook_event_name": "UserPromptSubmit", "prompt": "/reklam-atolyesi:basla", "prompt_id": "px"}, ddir)
    assert run_hook("navigator.py", {"session_id": SID, "hook_event_name": "UserPromptExpansion", "command_name": "reklam-atolyesi:basla",
                                     "prompt": "/reklam-atolyesi:basla", "prompt_id": "px"}, ddir) is None
    out = run_hook("navigator.py", {"session_id": "s-exp-0009", "hook_event_name": "UserPromptExpansion", "command_name": "reklam-atolyesi:sonraki",
                                    "prompt": "/reklam-atolyesi:sonraki", "prompt_id": "py"}, ddir)
    assert "plugin modu" in ctx_of(out)


def test_navigator_config_error_never_blocks(tmp_path):
    out = run_hook("navigator.py", {"session_id": SID, "hook_event_name": "UserPromptSubmit", "prompt": "reklam-atolyesi"}, None)
    assert "Yapılandırma hatası" in ctx_of(out)


# --- meta_guard -------------------------------------------------------------------
OWN = "mcp__plugin_reklam-atolyesi_meta-ads__"
OTHER = "mcp__f2f76932__"


def test_meta_own_server_always_allowlist(ddir):
    assert run_hook("meta_guard.py", {"session_id": SID, "tool_name": OWN + "ads_get_ad_accounts", "tool_input": {}}, ddir) is None
    out = run_hook("meta_guard.py", {"session_id": SID, "tool_name": OWN + "ads_update_entity", "tool_input": {}}, ddir)
    assert deny_of(out)
    out = run_hook("meta_guard.py", {"session_id": SID, "tool_name": OWN + "ads_get_ad_account_custom_audiences", "tool_input": {}}, ddir)
    assert deny_of(out)  # izin listesinde olmayan zararsız okuma aracı da reddedilir (canlı test aracı)


def test_meta_other_server_only_in_plugin_mode(ddir):
    assert run_hook("meta_guard.py", {"session_id": "x-other-01", "tool_name": OTHER + "ads_activate_entity", "tool_input": {}}, ddir) is None
    enter_mode(ddir, "x-other-02")
    assert deny_of(run_hook("meta_guard.py", {"session_id": "x-other-02", "tool_name": OTHER + "ads_activate_entity", "tool_input": {}}, ddir))


def test_meta_fail_closed(ddir, tmp_path):
    assert deny_of(run_hook("meta_guard.py", {"session_id": SID, "tool_name": OWN + "ads_get_ad_accounts"}, None))  # data_dir yok
    assert deny_of(run_hook("meta_guard.py", {"session_id": SID, "tool_name": OWN + "ads_get_ad_accounts"}, tmp_path / "yok"))
    bad = ddir / ".sessions"
    bad.mkdir(exist_ok=True)
    (bad / "bozuk-oturum-01.json").write_text("{bozuk", encoding="utf-8")
    assert deny_of(run_hook("meta_guard.py", {"session_id": "bozuk-oturum-01", "tool_name": OWN + "ads_get_ad_accounts"}, ddir))
    import subprocess, sys
    r = subprocess.run([sys.executable, str(ROOT / "hooks" / "meta_guard.py"), "--data-dir", str(ddir)], input=b"not json", capture_output=True)
    assert json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"  # okunamayan girdi


def test_meta_library_budget(ddir):
    enter_mode(ddir)
    s = json.loads((ddir / ".sessions" / f"{SID}.json").read_text(encoding="utf-8"))
    s["library_query_limit"] = 2
    (ddir / ".sessions" / f"{SID}.json").write_text(json.dumps(s), encoding="utf-8")
    p = {"session_id": SID, "tool_name": OWN + "ads_library_search", "tool_input": {}}
    assert run_hook("meta_guard.py", p, ddir) is None
    assert run_hook("meta_guard.py", p, ddir) is None
    assert deny_of(run_hook("meta_guard.py", p, ddir))


# --- cost_guard -------------------------------------------------------------------
EL = "mcp__plugin_reklam-atolyesi_ElevenLabs__"
P = {"prompt": "Örnek", "model_id": "eleven_v4", "voice_id": "v1", "flow_id": "f1"}


def test_cost_scope_outside_plugin_mode(ddir):
    assert run_hook("cost_guard.py", {"session_id": "no-mode-01", "tool_name": EL + "creative_generate_speech", "tool_input": P}, ddir) is None


def test_cost_free_unclassified_and_upload(ddir, store):
    enter_mode(ddir)
    assert run_hook("cost_guard.py", {"session_id": SID, "tool_name": EL + "creative_list_voices", "tool_input": {}}, ddir) is None
    assert deny_of(run_hook("cost_guard.py", {"session_id": SID, "tool_name": EL + "agents_create", "tool_input": {}}, ddir))
    assert deny_of(run_hook("cost_guard.py", {"session_id": SID, "tool_name": EL + "creative_attach_reference_file", "tool_input": {}}, ddir))
    pid = make_active_profile(store)["profile"]["id"]
    store.session_bind(SID, profile_id=pid)
    store.brand_upsert(pid, processing_permissions_json={"providers": {"elevenlabs": {"basis": "açık rıza", "evidence": "belge.pdf"}}})
    store.processing_permission_check(pid, "elevenlabs", "seslendirme", False, session_id=SID)
    assert run_hook("cost_guard.py", {"session_id": SID, "tool_name": EL + "creative_attach_reference_file", "tool_input": {}}, ddir) is None


def test_cost_estimate_requires_verified_schema(ddir, store):
    enter_mode(ddir)
    est = {"session_id": SID, "tool_name": EL + "creative_generate_speech", "tool_input": {**P, "estimate_only": True}}
    assert deny_of(run_hook("cost_guard.py", est, ddir))
    store.plugin_root = ddir / "plug"
    store.plugin_root.mkdir()
    (store.plugin_root / "system_manifest.json").write_text(json.dumps({"live_checks": [{"id": "el_estimate_schema"}]}), encoding="utf-8")
    store.runtime_record("el_estimate_schema", "passed", component_hashes={"tools_with_estimate_only": ["creative_generate_speech"]})
    assert run_hook("cost_guard.py", est, ddir) is None


def test_cost_paid_requires_single_use_reservation(ddir, store):
    enter_mode(ddir)
    a = make_active_profile(store)
    pid = a["profile"]["id"]
    c = store.campaign_create(pid, a["product"]["id"], "K")
    cid, cyid = c["campaign"]["id"], c["cycle"]["id"]
    call = {"session_id": SID, "tool_name": EL + "creative_generate_speech", "tool_input": {**P, "context": "x"}, "tool_use_id": "tu1"}
    assert deny_of(run_hook("cost_guard.py", call, ddir))  # oturuma bağlı kampanya yok
    store.session_bind(SID, profile_id=pid, campaign_id=cid, cycle_id=cyid)
    assert deny_of(run_hook("cost_guard.py", call, ddir))  # tahmin/onay yok
    g = store.generation_log(pid, cid, cyid, "creative_generate_speech", P, 120)
    store.generation_approve(pid, g["id"], 120, 4, "onaylıyorum", {"license": {"source": "s", "checked_at": "t", "scope": "reklam"}})
    assert run_hook("cost_guard.py", call, ddir) is None  # rezervasyon alındı
    assert store.q1("SELECT status FROM generations WHERE id=?", (g["id"],))["status"] == "running"
    assert deny_of(run_hook("cost_guard.py", call, ddir))  # ikinci çağrı: süren talep, otomatik tekrar yok


def test_cost_fail_closed_on_corrupt_session(ddir):
    (ddir / ".sessions").mkdir(exist_ok=True)
    (ddir / ".sessions" / "bozuk-oturum-02.json").write_text("{", encoding="utf-8")
    assert deny_of(run_hook("cost_guard.py", {"session_id": "bozuk-oturum-02", "tool_name": EL + "creative_generate_speech", "tool_input": P}, ddir))


# --- diğer hook'lar ---------------------------------------------------------------------
def test_session_start_only_resume_compact(ddir):
    enter_mode(ddir)
    assert run_hook("session_start.py", {"session_id": SID, "source": "startup"}, ddir) is None
    assert "plugin modunda sürüyor" in ctx_of(run_hook("session_start.py", {"session_id": SID, "source": "compact"}, ddir))
    assert run_hook("session_start.py", {"session_id": "baska-oturum-1", "source": "resume"}, ddir) is None


def test_render_qc_scope(ddir):
    assert run_hook("render_qc.py", {"session_id": SID, "tool_name": "Bash", "tool_input": {"command": "python scripts/render/render.py plan --out x.mp4"}}, ddir) is None
    enter_mode(ddir)
    out = run_hook("render_qc.py", {"session_id": SID, "tool_name": "Bash", "tool_input": {"command": "python scripts/render/render.py plan --out yok.mp4"}}, ddir)
    assert "mini-QC" in ctx_of(out)
    assert run_hook("render_qc.py", {"session_id": SID, "tool_name": "Bash", "tool_input": {"command": "ls"}}, ddir) is None


def test_stop_check_scope(ddir):
    assert run_hook("stop_check.py", {"session_id": "yok-oturum-1", "stop_hook_active": False}, ddir) is None
    enter_mode(ddir)
    assert run_hook("stop_check.py", {"session_id": SID, "stop_hook_active": True}, ddir) is None


def test_hooks_json_exec_form_no_hardcoded_paths():
    h = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    for ev, groups in h["hooks"].items():
        for g in groups:
            for hk in g["hooks"]:
                assert hk["type"] == "command" and isinstance(hk.get("args"), list)
                assert hk["command"].startswith("${user_config.data_dir}/.venv/")
                assert "--data-dir" in hk["args"] and "${user_config.data_dir}" in hk["args"]
                assert hk["timeout"] <= 10
    for f in (ROOT / "hooks").glob("*.py"):
        t = f.read_text(encoding="utf-8")
        assert ":\\\\" not in t and "D:/" not in t and "C:/" not in t and "/Users/" not in t, f
