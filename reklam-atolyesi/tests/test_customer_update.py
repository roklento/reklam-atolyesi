"""Yalnızca geliştiricide çalışır; müşteri güncelleyicisi bu testleri çağırmaz."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
from conftest import ROOT

PACKAGE = ROOT.parent / 'musteri-paketi'
if not PACKAGE.is_dir():
    pytest.skip('Müşteri paketi kaynak depoda sınanır; kurulu plugin yanında bulunmaz.', allow_module_level=True)
sys.path.insert(0, str(ROOT / 'hooks'))
import error_notify as EN
import plugin_mode as PM

spec = importlib.util.spec_from_file_location('customer_updater', PACKAGE / 'guncelle.py')
UP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(UP)


def test_backup_includes_wal_and_finish_preserves_verification(store):
    store.settings_set('setup_static_ok_at', '2026-01-01T00:00:00Z')
    store.settings_set('setup_verified_at', '2026-01-02T00:00:00Z')
    profile = store.profile_create('Müşteri')
    old_settings = store.settings_get()
    dest = UP.backup(store.data_dir)
    with sqlite3.connect(dest) as conn:
        assert conn.execute('SELECT name FROM profiles WHERE id=?', (profile['id'],)).fetchone()[0] == 'Müşteri'
    UP.finish(store.data_dir, ROOT, '1.4.3')
    assert store.settings_get() == old_settings
    view = store.system_manifest_get()
    assert view['customer_update_without_tests'] is True
    assert view['setup_verified_effective'] is False  # eksik canlı sonuçları geçmiş sayılmaz
    mark = store.data_dir / '.musteri-guncelleme.json'
    obj = json.loads(mark.read_text(encoding='utf-8'))
    obj['manifest_sha256'] = 'different-release'
    mark.write_text(json.dumps(obj), encoding='utf-8')
    assert store.system_manifest_get()['customer_update_without_tests'] is False
    mark.write_text('[]', encoding='utf-8')
    assert store.system_manifest_get()['customer_update_without_tests'] is False


def test_update_does_not_bypass_incomplete_first_install(store):
    UP.finish(store.data_dir, ROOT, '1.4.3')
    assert store.system_manifest_get()['customer_update_without_tests'] is False


def test_failure_notification_scope_and_redaction(data_dir):
    event = {'session_id': 'test-session', 'tool_name': 'Bash',
             'error': 'Exit code 1\nBearer secret-value access_token=hidden api_key=private'}
    assert EN.notify(data_dir, event) is None
    PM.save_session(data_dir, 'test-session', {'plugin_mode': True})
    result = EN.notify(data_dir, event)
    assert 'sağlayıcınıza' in result['systemMessage']
    files = list((data_dir / 'logs').glob('kullanim-hatasi-*.json'))
    assert len(files) == 1
    record = files[0].read_text(encoding='utf-8')
    assert 'secret-value' not in record and 'hidden' not in record and 'private' not in record
    assert EN.notify(data_dir, {**event, 'is_interrupt': True}) is None
    assert len(list((data_dir / 'logs').glob('*.json'))) == 1
    assert EN.notify(data_dir, {**event, 'session_id': 'unknown', 'tool_name': PM.OWN_SERVER_PREFIX + 'ad-memory__profile_list'})


@pytest.mark.skipif(os.name != 'nt', reason='Windows müşteri paketi')
@pytest.mark.parametrize('mode', ['same', 'changed', 'update-fails', 'deps-fail', 'missing'])
def test_windows_updater_flow(tmp_path, mode):
    """Gerçek PS 5.1 kontrol akışı; dış servis/kurulum çağrıları sahte, müşteri verisine erişim yok."""
    dd = tmp_path / 'müşteri veri'
    old = tmp_path / 'old'
    new = tmp_path / 'new'
    for folder in (old, new):
        for rel, content in {'servers/ad_memory/uv.lock': 'same', 'servers/ad_memory/pyproject.toml': 'project',
                             'templates/remotion/package-lock.json': 'node', 'templates/remotion/package.json': '{}',
                             'hooks/error_notify.py': '# present'}.items():
            p = folder / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
    (dd / '.venv/Scripts').mkdir(parents=True)
    (dd / '.venv/Scripts/python.exe').touch()
    (dd / '.node/node_modules/remotion').mkdir(parents=True)
    (dd / '.node/.kilit-sha256').write_text(hashlib.sha256(b'node').hexdigest().upper())
    if mode in ('changed', 'deps-fail'):
        (new / 'servers/ad_memory/uv.lock').write_text('new deps')
        (new / 'templates/remotion/package-lock.json').write_text('new node')
    calls = tmp_path / 'calls.jsonl'
    def quote(path):
        return "'" + str(path).replace("'", "''") + "'"
    mock = '''
$script:moved = $false
function Update-YolDegiskeni { }
function Find-Claude { return 'mock-claude' }
function Get-KayitliVeriKlasoru { return DD }
function Get-KuruluPlugin {
    if ('MODE' -eq 'missing') { return $null }
    if ($script:moved) { return [pscustomobject]@{scope='user';version='1.4.4';installPath=NEW} }
    return [pscustomobject]@{scope='user';version='1.4.3';installPath=OLD}
}
function uv { }
function npm.cmd { }
function Invoke-Adim([string]$exe, [string[]]$argv) {
    ConvertTo-Json -Compress @{exe=$exe;argv=$argv} | Add-Content -LiteralPath CALLS -Encoding UTF8
    if ($argv[0] -eq 'plugin' -and $argv[1] -eq 'update') {
        if ('MODE' -eq 'update-fails') { throw 'SIMULATED UPDATE ERROR' }
        $script:moved = $true
    }
    if ($exe -eq 'uv' -and 'MODE' -eq 'deps-fail') { throw 'SIMULATED DEPENDENCY ERROR' }
}
'''
    for key, val in {'DD': quote(dd), 'NEW': quote(new), 'OLD': quote(old), 'CALLS': quote(calls), 'MODE': mode}.items():
        mock = mock.replace(key, val)
    script = (PACKAGE / 'guncelle.ps1').read_text(encoding='utf-8-sig')
    script = script.replace('$Gunluk = Join-Path', mock + '\n$Gunluk = Join-Path', 1)
    test_script = tmp_path / 'updater.ps1'
    test_script.write_text(script, encoding='utf-8-sig')
    env = dict(os.environ)
    env.pop('PSModulePath', None)  # PS 7'nin modül yolları PS 5.1 alt sürecine taşınmasın.
    result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(test_script)],
                            capture_output=True, timeout=30, env=env)
    output = result.stdout.decode('utf-8', errors='replace') + result.stderr.decode('utf-8', errors='replace')
    assert result.returncode == (0 if mode in ('same', 'changed') else 1), output
    entries = [json.loads(s) for s in calls.read_text(encoding='utf-8-sig').splitlines()] if calls.exists() else []
    # Geçici klasör yolu (Windows'ta ".../pytest-of-<kullanıcı>/...") komut sanılmasın: yalnızca çağrılan komutlar aranır.
    tmp_json = json.dumps(str(tmp_path))[1:-1]
    called = [json.dumps(e).replace(tmp_json, '<tmp>') for e in entries]
    assert not any(any(word in s for word in ('doctor.py', 'kurulum.ps1', 'kurulum_dogrula.py', 'pytest', 'smoke.py')) for s in called)
    if mode == 'missing':
        assert not entries
        return
    assert entries[0]['argv'][1] == 'backup'
    assert entries[1]['argv'] == ['plugin', 'marketplace', 'update', 'reklam-atolyesi']
    assert entries[2]['argv'] == ['plugin', 'update', 'reklam-atolyesi@reklam-atolyesi', '--scope', 'user']
    assert any(e['exe'] == 'uv' for e in entries) == (mode in ('changed', 'deps-fail'))
    assert any(e['exe'] == 'npm.cmd' for e in entries) == (mode == 'changed')
    assert any('finish' in e['argv'] for e in entries) == (mode in ('same', 'changed'))
    assert list((dd / 'logs').glob('reklam-atolyesi-guncelleme-*.log'))
    if mode in ('update-fails', 'deps-fail'):
        assert 'sağlayıcınıza' in output
    if mode == 'deps-fail':
        stamp = (dd / '.guncelleme-python-sha256').read_text()
        assert stamp.startswith(hashlib.sha256(b'same').hexdigest().upper())
    if mode == 'changed':
        before = len(entries)
        again = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(test_script)],
                               capture_output=True, timeout=30, env=env)
        assert again.returncode == 0, again.stdout
        tail = [json.loads(s) for s in calls.read_text(encoding='utf-8-sig').splitlines()][before:]
        assert not any(e['exe'] in ('uv', 'npm.cmd') for e in tail)
