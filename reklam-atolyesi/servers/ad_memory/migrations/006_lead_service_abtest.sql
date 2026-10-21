-- pragma: foreign_keys=off
-- 006 (1.5.0): form ile müşteri adayı sonucu, hizmet işletmesi ve Meta A/B testi yapısı.
-- SQLite CHECK kısıtını değiştiremez: campaigns ve cycles aynı sütunlar ve kimliklerle yeniden kurulur (satırlar korunur).
-- Bu iki tabloya başka tablolar yabancı anahtarla bağlıdır: çalıştırıcı bu dosyayı yabancı anahtar denetimi kapalıyken tek işlemde
-- uygular, sonunda PRAGMA foreign_key_check boş değilse geri alır (SQLite'ın önerdiği yeniden kurma yolu). Store açılışı öncesinde
-- yedek alır.

CREATE TABLE campaigns_new (
  id              INTEGER PRIMARY KEY,
  brand_id        INTEGER NOT NULL REFERENCES brands(id),
  product_id      INTEGER REFERENCES products(id),
  name            TEXT NOT NULL,
  slug            TEXT NOT NULL,
  goal            TEXT,
  result_type     TEXT CHECK (result_type IN ('purchase','lead','messaging','profile_visit','link_click','engagement')),
  lead_method     TEXT CHECK (lead_method IS NULL OR lead_method IN ('instant_form','website','call')),
  season          TEXT,
  budget_total    REAL,
  budget_total_confirmed INTEGER NOT NULL DEFAULT 0,
  test_structure  TEXT CHECK (test_structure IN ('bootstrap','creative_test','ab_test','deviated','unverified')),
  mode            TEXT NOT NULL DEFAULT 'full' CHECK (mode IN ('full','quick')),
  stage           TEXT NOT NULL DEFAULT 'S01',
  cycle           INTEGER NOT NULL DEFAULT 1,
  trial           INTEGER NOT NULL DEFAULT 0,
  status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','closed','archived')),
  created_at      TEXT NOT NULL,
  UNIQUE (brand_id, slug)
);
INSERT INTO campaigns_new(id, brand_id, product_id, name, slug, goal, result_type, lead_method, season, budget_total, budget_total_confirmed,
                          test_structure, mode, stage, cycle, trial, status, created_at)
  SELECT id, brand_id, product_id, name, slug, goal, result_type, NULL, season, budget_total, budget_total_confirmed,
         test_structure, mode, stage, cycle, trial, status, created_at FROM campaigns;
DROP TABLE campaigns;
ALTER TABLE campaigns_new RENAME TO campaigns;

CREATE TABLE cycles_new (
  id                       INTEGER PRIMARY KEY,
  campaign_id              INTEGER NOT NULL REFERENCES campaigns(id),
  cycle                    INTEGER NOT NULL,
  adset_budget_daily       REAL,
  test_budget              REAL,
  test_days                INTEGER,
  cycle_days               INTEGER,
  plan_day                 TEXT,
  shoot_start              TEXT,
  launch_at                TEXT,
  launched_at              TEXT,
  test_start               TEXT,
  test_end                 TEXT,
  decision_due_at          TEXT,
  decision_at              TEXT,
  meta_test_id             TEXT,
  structure_detected       TEXT CHECK (structure_detected IN ('bootstrap','creative_test','ab_test','deviated','unverified')),
  structure_evidence_json  TEXT,
  measurement_json         TEXT,
  priors_snapshot_json     TEXT,
  budget_plan_json         TEXT,
  risk_limits_json         TEXT,
  jobs_json                TEXT NOT NULL DEFAULT '[]',
  strategy_json            TEXT,
  competitor_snapshot_id   INTEGER REFERENCES competitor_snapshots(id),
  calendar_json            TEXT,
  status                   TEXT NOT NULL DEFAULT 'production' CHECK (status IN ('production','measuring','closed')),
  created_at               TEXT NOT NULL,
  UNIQUE (campaign_id, cycle)
);
INSERT INTO cycles_new(id, campaign_id, cycle, adset_budget_daily, test_budget, test_days, cycle_days, plan_day, shoot_start, launch_at,
                       launched_at, test_start, test_end, decision_due_at, decision_at, meta_test_id, structure_detected,
                       structure_evidence_json, measurement_json, priors_snapshot_json, budget_plan_json, risk_limits_json, jobs_json,
                       strategy_json, competitor_snapshot_id, calendar_json, status, created_at)
  SELECT id, campaign_id, cycle, adset_budget_daily, test_budget, test_days, cycle_days, plan_day, shoot_start, launch_at,
         launched_at, test_start, test_end, decision_due_at, decision_at, meta_test_id, structure_detected,
         structure_evidence_json, measurement_json, priors_snapshot_json, budget_plan_json, risk_limits_json, jobs_json,
         strategy_json, competitor_snapshot_id, calendar_json, status, created_at FROM cycles;
DROP TABLE cycles;
ALTER TABLE cycles_new RENAME TO cycles;

-- Hizmet işletmesi: ürün kaydı hizmet de olabilir (süre, kapasite, bölge, düzenlenen sektör service_json'da).
ALTER TABLE products ADD COLUMN kind TEXT NOT NULL DEFAULT 'product' CHECK (kind IN ('product','service'));
ALTER TABLE products ADD COLUMN service_json TEXT;

-- Müşteri adayı sonrası huni (dönem toplamı; kişisel veri yok): adaylar → ulaşılan → nitelikli → satış.
CREATE TABLE lead_outcomes (
  id            INTEGER PRIMARY KEY,
  campaign_id   INTEGER NOT NULL REFERENCES campaigns(id),
  period_start  TEXT NOT NULL,
  period_end    TEXT NOT NULL,
  leads         INTEGER NOT NULL CHECK (leads >= 0),
  reached       INTEGER CHECK (reached IS NULL OR reached >= 0),
  qualified     INTEGER CHECK (qualified IS NULL OR qualified >= 0),
  won           INTEGER CHECK (won IS NULL OR won >= 0),
  revenue       REAL CHECK (revenue IS NULL OR revenue >= 0),
  currency      TEXT,
  source        TEXT NOT NULL CHECK (source IN ('crm_export','meta_leads_center','manual')),
  note          TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  UNIQUE (campaign_id, period_start, period_end)
);
CREATE INDEX idx_lead_outcomes_campaign ON lead_outcomes(campaign_id, period_start);
