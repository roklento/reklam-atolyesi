-- 009 (2.5.0): metin aşamalarının taslak denetimi (KURALLAR.md K10). Yalnızca tablo ekler; mevcut kayıtlar değişmez.
-- Her denetim çağrısı bir satırdır. Tur, aynı aşama kapsamında henüz bir aşama kaydına bağlanmamış (consumed_by_run_id NULL) ve
-- birbirinden farklı içerikli (sha256) denetimlerin sayısıdır; değişmemiş dosyanın yeniden denetimi yeni tur sayılmaz.
-- stage_complete belgeyi tamamlarken uygun denetimi aşama kaydına bağlar (consumed_by_run_id).
CREATE TABLE draft_checks (
  id                  INTEGER PRIMARY KEY,
  profile_id          INTEGER NOT NULL REFERENCES profiles(id),
  campaign_id         INTEGER REFERENCES campaigns(id),
  cycle_id            INTEGER REFERENCES cycles(id),
  scope_key           TEXT NOT NULL,
  stage               TEXT NOT NULL,
  path                TEXT NOT NULL,
  sha256              TEXT NOT NULL,
  template            TEXT,
  round               INTEGER NOT NULL,
  verdict             TEXT NOT NULL CHECK (verdict IN ('pass','fail')),
  critical            INTEGER NOT NULL DEFAULT 0,
  warnings            INTEGER NOT NULL DEFAULT 0,
  issues_json         TEXT NOT NULL DEFAULT '[]',
  consumed_by_run_id  INTEGER REFERENCES stage_runs(id),
  created_at          TEXT NOT NULL
);
CREATE INDEX ix_draft_checks_scope ON draft_checks(scope_key, stage, consumed_by_run_id);
