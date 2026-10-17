"""Müşteri güncellemesi: SQLite yedeği ve gerekli migration; test/doğrulama çalıştırmaz."""
import argparse
import datetime as dt
import hashlib
import json
import sqlite3
import sys
from pathlib import Path


def backup(data_dir):
    db = data_dir / 'db' / 'ad-memory.sqlite'
    if not db.is_file():
        raise RuntimeError('Mevcut veritabanı yok; ilk kurulum için kur.cmd kullanın.')
    dest = data_dir / 'backups' / ('guncelleme-' + dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite')
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    print('Veritabanı yedeği: ' + str(dest))
    return dest


def finish(data_dir, root, from_version):
    # Store açılışı, gerekiyorsa numaralı migration'ları kendi yedekleriyle uygular.
    sys.path.insert(0, str(root / 'servers' / 'ad_memory'))
    from admem.store import Store
    store = Store(data_dir / 'db' / 'ad-memory.sqlite', data_dir, plugin_root=root)
    try:
        manifest = root / 'system_manifest.json'
        rec = {'version': json.loads((root / '.claude-plugin' / 'plugin.json').read_text(encoding='utf-8'))['version'],
               'from_version': from_version, 'updated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
               'manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
               'tests_run': False}
        store.journal_log('Müşteri güncellemesi alındı; test çalıştırılmadı', None, type='setup', detail=rec)
        path = data_dir / '.musteri-guncelleme.json'
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(path)
    finally:
        store.close()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['backup', 'finish'])
    ap.add_argument('--data-dir', required=True, type=Path)
    ap.add_argument('--plugin-root', type=Path)
    ap.add_argument('--from-version', default='')
    a = ap.parse_args()
    if a.action == 'backup':
        backup(a.data_dir.resolve())
    else:
        if not a.plugin_root:
            ap.error('--plugin-root gerekli')
        finish(a.data_dir.resolve(), a.plugin_root.resolve(), a.from_version)
