-- reklam-atolyesi ad-memory şeması, sürüm 1 (spec 7.2; 1.4 kapsamı tek migration'da kurulur)
-- Standart SQL; SQLite'a özgü kısımlar: FTS5 sanal tablosu ve partial index'ler (taşınabilirlik, ilke 8).
-- Zaman damgaları ISO-8601 metin (UTC, 'Z'); JSON alanları metin.

CREATE TABLE IF NOT EXISTS schema_meta (
  version     INTEGER PRIMARY KEY,
  applied_at  TEXT NOT NULL
);

CREATE TABLE settings (
  key         TEXT PRIMARY KEY,
  value       TEXT,
  updated_at  TEXT NOT NULL
);

-- Marka ve ürün -------------------------------------------------------------
CREATE TABLE brands (
  id                           INTEGER PRIMARY KEY,
  name                         TEXT NOT NULL,
  meta_ad_account_id           TEXT UNIQUE,            -- aynı hesap iki profile bağlanamaz (2.3)
  meta_page_id                 TEXT,
  ig_account_id                TEXT,
  tone                         TEXT,
  avoid_list                   TEXT,                   -- JSON dizi
  cta_url                      TEXT,
  style_json_path              TEXT,
  elevenlabs_voice_id          TEXT,
  timezone                     TEXT,
  processing_permissions_json  TEXT,
  created_at                   TEXT NOT NULL
);

CREATE TABLE profiles (
  id                 INTEGER PRIMARY KEY,
  slug               TEXT NOT NULL UNIQUE,
  name               TEXT NOT NULL,
  brand_id           INTEGER REFERENCES brands(id),
  status             TEXT NOT NULL DEFAULT 'onboarding' CHECK (status IN ('onboarding','active','archived')),
  meta_data_mode     TEXT CHECK (meta_data_mode IN ('mcp','csv')),
  meta_verified_at   TEXT,
  history_status     TEXT NOT NULL DEFAULT 'pending' CHECK (history_status IN ('pending','ready','no_history')),
  last_meta_sync_at  TEXT,
  jobs_json          TEXT NOT NULL DEFAULT '[]',
  synthetic          INTEGER NOT NULL DEFAULT 0,      -- canlı kabul listesi profili (16.5); sayılmaz
  created_at         TEXT NOT NULL,
  archived_at        TEXT
);
CREATE UNIQUE INDEX ux_profiles_brand ON profiles(brand_id) WHERE brand_id IS NOT NULL;

CREATE TABLE products (
  id                    INTEGER PRIMARY KEY,
  brand_id              INTEGER NOT NULL REFERENCES brands(id),
  name                  TEXT NOT NULL,
  price                 REAL,
  gross_margin          REAL,
  aov                   REAL,
  currency              TEXT,
  safety_factor         REAL NOT NULL DEFAULT 0.7,
  economics_json        TEXT,
  occasions_json        TEXT,
  provable_claims_json  TEXT,
  capacity_limit        TEXT,
  photos_json           TEXT,
  observation_json      TEXT,
  shoot_profile_json    TEXT,
  catalog_product_id    TEXT,
  onboarding_status     TEXT NOT NULL DEFAULT 'pending' CHECK (onboarding_status IN ('pending','done','skipped_trial')),
  created_at            TEXT NOT NULL,
  UNIQUE (brand_id, name)
);

CREATE TABLE onboarding_answers (
  id            INTEGER PRIMARY KEY,
  scope         TEXT NOT NULL CHECK (scope IN ('brand','product')),
  scope_id      INTEGER NOT NULL,
  question_key  TEXT NOT NULL,
  answer        TEXT,
  source        TEXT NOT NULL CHECK (source IN ('user','meta','inferred')),
  confirmed     INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL
);
CREATE INDEX ix_onboarding_scope ON onboarding_answers(scope, scope_id, question_key);

-- Meta geçmişi ve önseller --------------------------------------------------
CREATE TABLE meta_entities (
  id              INTEGER PRIMARY KEY,
  brand_id        INTEGER NOT NULL REFERENCES brands(id),
  ad_account_id   TEXT NOT NULL,
  level           TEXT NOT NULL CHECK (level IN ('campaign','adset','ad')),
  meta_id         TEXT NOT NULL,
  parent_meta_id  TEXT,
  name            TEXT,
  status          TEXT,
  objective       TEXT,
  created_time    TEXT,
  creative_id     TEXT,
  raw_json        TEXT,
  synced_at       TEXT NOT NULL,
  UNIQUE (level, meta_id)
);
CREATE INDEX ix_meta_entities_brand ON meta_entities(brand_id, level);

CREATE TABLE account_benchmarks (
  id            INTEGER PRIMARY KEY,
  brand_id      INTEGER NOT NULL REFERENCES brands(id),
  kind          TEXT NOT NULL,
  metric        TEXT NOT NULL,
  value         REAL,
  context_json  TEXT,
  fetched_at    TEXT NOT NULL,
  UNIQUE (brand_id, kind, metric)
);

CREATE TABLE priors (
  id                   INTEGER PRIMARY KEY,
  brand_id             INTEGER NOT NULL REFERENCES brands(id),
  objective            TEXT NOT NULL,
  metric               TEXT NOT NULL,
  dist                 TEXT NOT NULL DEFAULT 'beta' CHECK (dist IN ('beta')),
  a                    REAL NOT NULL,
  b                    REAL NOT NULL,
  n_source             REAL NOT NULL DEFAULT 0,
  n_cap                REAL NOT NULL DEFAULT 30,
  source               TEXT NOT NULL,
  source_cutoff_at     TEXT,
  source_summary_json  TEXT,
  updated_at           TEXT NOT NULL,
  UNIQUE (brand_id, objective, metric)
);

-- Kampanya ve tur -----------------------------------------------------------
CREATE TABLE campaigns (
  id              INTEGER PRIMARY KEY,
  brand_id        INTEGER NOT NULL REFERENCES brands(id),
  product_id      INTEGER REFERENCES products(id),
  name            TEXT NOT NULL,
  slug            TEXT NOT NULL,
  goal            TEXT,
  result_type     TEXT CHECK (result_type IN ('purchase','messaging','profile_visit','link_click','engagement')),
  season          TEXT,
  budget_total    REAL,                 -- NULL: kullanıcı sınır tanımlamadı (6.3)
  budget_total_confirmed INTEGER NOT NULL DEFAULT 0,
  test_structure  TEXT CHECK (test_structure IN ('bootstrap','creative_test','deviated','unverified')),
  mode            TEXT NOT NULL DEFAULT 'full' CHECK (mode IN ('full','quick')),
  stage           TEXT NOT NULL DEFAULT 'S01',
  cycle           INTEGER NOT NULL DEFAULT 1,
  trial           INTEGER NOT NULL DEFAULT 0,  -- ürün tanışması atlanmış deneme kampanyası (17.7)
  status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','closed','archived')),
  created_at      TEXT NOT NULL,
  UNIQUE (brand_id, slug)
);

CREATE TABLE cycles (
  id                       INTEGER PRIMARY KEY,
  campaign_id              INTEGER NOT NULL REFERENCES campaigns(id),
  cycle                    INTEGER NOT NULL,
  adset_budget_daily       REAL,
  test_budget              REAL,
  test_days                INTEGER,
  cycle_days               INTEGER,
  plan_day                 TEXT,
  shoot_start              TEXT,
  launch_at                TEXT,            -- planlanan
  launched_at              TEXT,            -- gerçekleşen yayın
  test_start               TEXT,
  test_end                 TEXT,
  decision_due_at          TEXT,
  decision_at              TEXT,
  meta_test_id             TEXT,
  structure_detected       TEXT CHECK (structure_detected IN ('bootstrap','creative_test','deviated','unverified')),
  structure_evidence_json  TEXT,
  measurement_json         TEXT,
  priors_snapshot_json     TEXT,
  budget_plan_json         TEXT,
  risk_limits_json         TEXT,
  jobs_json                TEXT NOT NULL DEFAULT '[]',
  strategy_json            TEXT,
  competitor_snapshot_id   INTEGER REFERENCES competitor_snapshots(id),
  calendar_json            TEXT,            -- hedef tarihler ve kayma geçmişi (4.4)
  status                   TEXT NOT NULL DEFAULT 'production' CHECK (status IN ('production','measuring','closed')),
  created_at               TEXT NOT NULL,
  UNIQUE (campaign_id, cycle)
);

CREATE TABLE stage_runs (
  id              INTEGER PRIMARY KEY,
  profile_id      INTEGER NOT NULL REFERENCES profiles(id),
  campaign_id     INTEGER REFERENCES campaigns(id),
  stage           TEXT NOT NULL,
  cycle_id        INTEGER REFERENCES cycles(id),
  scope_key       TEXT NOT NULL,            -- 'cycle:<id>' ya da tanışmada 'profile:<id>' / 'product:<id>'
  output_version  INTEGER NOT NULL,
  status          TEXT NOT NULL CHECK (status IN ('running','awaiting_gate','done','skipped')),
  started_at      TEXT NOT NULL,
  finished_at     TEXT,
  outputs_json    TEXT,
  stale           INTEGER NOT NULL DEFAULT 0,
  UNIQUE (scope_key, stage, output_version)
);
CREATE UNIQUE INDEX ux_stage_runs_cycle ON stage_runs(cycle_id, stage, output_version) WHERE cycle_id IS NOT NULL;
CREATE INDEX ix_stage_runs_campaign ON stage_runs(campaign_id, cycle_id, stage);

CREATE TABLE decisions (
  id              INTEGER PRIMARY KEY,
  profile_id      INTEGER NOT NULL REFERENCES profiles(id),
  campaign_id     INTEGER REFERENCES campaigns(id),
  cycle_id        INTEGER REFERENCES cycles(id),
  stage_run_id    INTEGER REFERENCES stage_runs(id),
  output_version  INTEGER,
  stage           TEXT,
  gate            TEXT,
  decision        TEXT NOT NULL,
  note            TEXT,
  decided_by      TEXT NOT NULL,
  created_at      TEXT NOT NULL
);

-- Rekabet (4.5–4.7, 6.16) ---------------------------------------------------
CREATE TABLE competitors (
  id            INTEGER PRIMARY KEY,
  profile_id    INTEGER NOT NULL REFERENCES profiles(id),
  name          TEXT NOT NULL,
  kind          TEXT NOT NULL CHECK (kind IN ('direct','indirect','aspirational')),
  meta_page_id  TEXT,
  ig_handle     TEXT,
  website       TEXT,
  notes         TEXT,
  status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','ignored')),
  added_by      TEXT NOT NULL CHECK (added_by IN ('user','discovered','brand_doc')),
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  UNIQUE (profile_id, name)
);

CREATE TABLE competitor_snapshots (
  id             INTEGER PRIMARY KEY,
  profile_id     INTEGER NOT NULL REFERENCES profiles(id),
  campaign_id    INTEGER REFERENCES campaigns(id),
  cycle_id       INTEGER REFERENCES cycles(id),
  mode           TEXT NOT NULL CHECK (mode IN ('full','diff')),
  scope_json     TEXT,
  fetched_at     TEXT NOT NULL,
  n_calls        INTEGER NOT NULL DEFAULT 0,
  n_ads          INTEGER NOT NULL DEFAULT 0,
  coverage_json  TEXT,
  source         TEXT NOT NULL DEFAULT 'ad_library' CHECK (source IN ('ad_library','manual','synthetic')),
  sha256         TEXT NOT NULL
);

CREATE TABLE competitor_ads (
  id                INTEGER PRIMARY KEY,
  profile_id        INTEGER NOT NULL REFERENCES profiles(id),
  competitor_id     INTEGER NOT NULL REFERENCES competitors(id),
  library_id        TEXT NOT NULL,
  variant_group     TEXT,
  start_date        TEXT,
  stop_date         TEXT,
  first_seen_at     TEXT,
  last_seen_at      TEXT,
  is_active         INTEGER,
  platforms_json    TEXT,
  media_type        TEXT,
  body_text         TEXT,
  title             TEXT,
  cta               TEXT,
  link_url          TEXT,
  snapshot_url      TEXT,
  features_json     TEXT,
  taxonomy_version  TEXT,
  source            TEXT NOT NULL CHECK (source IN ('ad_library','user','web')),
  raw_json          TEXT,
  instruction_flag  INTEGER NOT NULL DEFAULT 0,   -- metinde yönerge görüldü (ilke 14); yalnızca veri
  last_snapshot_id  INTEGER REFERENCES competitor_snapshots(id),
  UNIQUE (competitor_id, library_id)
);

CREATE TABLE competitor_offers (
  id             INTEGER PRIMARY KEY,
  profile_id     INTEGER NOT NULL REFERENCES profiles(id),
  competitor_id  INTEGER NOT NULL REFERENCES competitors(id),
  snapshot_id    INTEGER REFERENCES competitor_snapshots(id),
  product_ref    TEXT,
  price          REAL,
  currency       TEXT,
  offer_json     TEXT,
  claims_json    TEXT,
  url            TEXT,
  fetched_at     TEXT NOT NULL
);

CREATE TABLE competitive_insights (
  id             INTEGER PRIMARY KEY,
  profile_id     INTEGER NOT NULL REFERENCES profiles(id),
  campaign_id    INTEGER REFERENCES campaigns(id),
  cycle_id       INTEGER REFERENCES cycles(id),
  snapshot_id    INTEGER REFERENCES competitor_snapshots(id),
  kind           TEXT NOT NULL CHECK (kind IN ('norm','proven_angle','gap','offer','timing','risk','differentiator')),
  statement      TEXT NOT NULL,
  axis           TEXT,
  label          TEXT NOT NULL CHECK (label IN ('observation','proxy','user')),
  evidence_json  TEXT,
  created_at     TEXT NOT NULL
);

CREATE TABLE taxonomy_values (
  id                INTEGER PRIMARY KEY,
  profile_id        INTEGER NOT NULL REFERENCES profiles(id),
  axis              TEXT NOT NULL CHECK (axis IN ('angle','moment','emotion','tone')),
  code              TEXT NOT NULL,
  label             TEXT NOT NULL,
  status            TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','active','retired')),
  taxonomy_version  TEXT NOT NULL,
  created_at        TEXT NOT NULL,
  UNIQUE (profile_id, axis, code)
);

-- Konsept, kreatif, kurgu ---------------------------------------------------
CREATE TABLE hypotheses (
  id             INTEGER PRIMARY KEY,
  campaign_id    INTEGER REFERENCES campaigns(id),
  cycle_id       INTEGER REFERENCES cycles(id),
  profile_id     INTEGER NOT NULL REFERENCES profiles(id),
  statement      TEXT NOT NULL,
  metric         TEXT,
  feature        TEXT,
  status         TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','testing','supported','rejected','inconclusive')),
  is_primary     INTEGER NOT NULL DEFAULT 0,      -- turun birincil doğrulama hipotezi (6.6)
  evidence_json  TEXT,
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL
);

CREATE TABLE concepts (
  id                             INTEGER PRIMARY KEY,
  campaign_id                    INTEGER NOT NULL REFERENCES campaigns(id),
  cycle_id                       INTEGER NOT NULL REFERENCES cycles(id),
  code                           TEXT NOT NULL,
  name                           TEXT NOT NULL,
  angle                          TEXT,
  hypothesis_id                  INTEGER REFERENCES hypotheses(id),
  status                         TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','selected','dropped')),
  source                         TEXT NOT NULL CHECK (source IN ('evidence','direction','general','product','brand_doc','competitor')),
  decision                       TEXT CHECK (decision IN ('accepted','merged','rejected','deferred')),
  rationale                      TEXT,
  competitive_role               TEXT CHECK (competitive_role IN ('proven','gap','counter','free')),
  source_competitor_ad_ids_json  TEXT,
  features_json                  TEXT,
  taxonomy_version               TEXT,
  distance_check_json            TEXT,
  sound_intent                   TEXT,
  created_at                     TEXT NOT NULL,
  updated_at                     TEXT NOT NULL,
  UNIQUE (cycle_id, code)
);

CREATE TABLE hooks (
  id                INTEGER PRIMARY KEY,
  concept_id        INTEGER NOT NULL REFERENCES concepts(id),
  code              TEXT NOT NULL,
  first_frame_type  TEXT,
  first_frame_desc  TEXT,
  first_motion      TEXT,
  first_sound       TEXT,
  text              TEXT,
  vo                TEXT,
  duration_s        REAL,
  decision          TEXT CHECK (decision IN ('accepted','merged','rejected','deferred')),
  reserve           INTEGER NOT NULL DEFAULT 0,     -- yalnızca metin/renk farkı: aynı varlık, yedek (4.3)
  created_at        TEXT NOT NULL,
  UNIQUE (concept_id, code)
);

CREATE TABLE edit_plans (
  id           INTEGER PRIMARY KEY,
  campaign_id  INTEGER NOT NULL REFERENCES campaigns(id),
  cycle_id     INTEGER NOT NULL REFERENCES cycles(id),
  concept_id   INTEGER REFERENCES concepts(id),
  hook_id      INTEGER REFERENCES hooks(id),
  format       TEXT NOT NULL,
  purpose      TEXT NOT NULL CHECK (purpose IN ('style_preview','production')),
  status       TEXT NOT NULL CHECK (status IN ('draft','ready')),
  version      INTEGER NOT NULL,
  plan_json    TEXT NOT NULL,
  sha256       TEXT NOT NULL,
  parent_id    INTEGER REFERENCES edit_plans(id),
  path         TEXT,
  created_at   TEXT NOT NULL
);
CREATE INDEX ix_edit_plans_cycle ON edit_plans(cycle_id, concept_id, hook_id, format, version);

CREATE TABLE creatives (
  id                INTEGER PRIMARY KEY,
  campaign_id       INTEGER NOT NULL REFERENCES campaigns(id),
  cycle_id          INTEGER NOT NULL REFERENCES cycles(id),
  concept_id        INTEGER REFERENCES concepts(id),
  hook_id           INTEGER REFERENCES hooks(id),
  edit_plan_id      INTEGER REFERENCES edit_plans(id),
  creative_key      TEXT NOT NULL,
  file_path         TEXT NOT NULL,
  file_name         TEXT NOT NULL,
  sha256            TEXT NOT NULL,
  media_type        TEXT NOT NULL CHECK (media_type IN ('video','static','carousel')),
  source_variant    TEXT NOT NULL CHECK (source_variant IN ('real','ai')),
  card_index        INTEGER NOT NULL DEFAULT 0,
  delivery_role     TEXT NOT NULL CHECK (delivery_role IN ('test','reserve')),
  duration_s        REAL,
  format            TEXT NOT NULL,
  style_direction   TEXT,
  music_bpm         REAL,
  has_vo            INTEGER NOT NULL DEFAULT 0,
  ai_share          REAL NOT NULL DEFAULT 0,
  features_json     TEXT,
  taxonomy_version  TEXT,
  revision          INTEGER NOT NULL DEFAULT 1,
  qc_status         TEXT NOT NULL DEFAULT 'pending' CHECK (qc_status IN ('pending','passed','failed','stale')),
  created_at        TEXT NOT NULL,
  UNIQUE (campaign_id, creative_key, format, card_index)
);

-- Malzeme ve maliyet --------------------------------------------------------
CREATE TABLE assets (
  id                INTEGER PRIMARY KEY,
  profile_id        INTEGER NOT NULL REFERENCES profiles(id),
  product_id        INTEGER REFERENCES products(id),
  campaign_id       INTEGER REFERENCES campaigns(id),
  kind              TEXT NOT NULL,
  path              TEXT NOT NULL,
  source            TEXT,
  shot_no           TEXT,
  sha256            TEXT NOT NULL,
  score_json        TEXT,
  best_ranges_json  TEXT,
  tags              TEXT,
  audio_json        TEXT,
  people_json       TEXT,
  used_in_json      TEXT,
  meta_json         TEXT,       -- ffprobe/EXIF özeti ve türev dosyalar (proxy, stab, sdr)
  notes             TEXT,
  created_at        TEXT NOT NULL,
  UNIQUE (profile_id, sha256)
);

CREATE TABLE generations (
  id                   INTEGER PRIMARY KEY,
  profile_id           INTEGER NOT NULL REFERENCES profiles(id),
  campaign_id          INTEGER NOT NULL REFERENCES campaigns(id),
  cycle_id             INTEGER REFERENCES cycles(id),
  provider             TEXT NOT NULL,
  model                TEXT,
  kind                 TEXT NOT NULL,
  tool_name            TEXT NOT NULL,
  prompt               TEXT,
  params_json          TEXT NOT NULL,
  params_hash          TEXT NOT NULL,
  request_no           INTEGER NOT NULL DEFAULT 1,
  estimate_credits     REAL,
  estimate_approved    INTEGER NOT NULL DEFAULT 0,      -- tek kullanımlık (9.1)
  approved_at          TEXT,
  approval_scope_json  TEXT,
  cost_credits         REAL,
  flow_id              TEXT,
  session_ids_json     TEXT,
  tool_use_id          TEXT,
  provider_request_id  TEXT,
  status               TEXT NOT NULL DEFAULT 'estimated' CHECK (status IN ('estimated','running','completed','failed','unknown')),
  error_json           TEXT,
  output_path          TEXT,
  accepted             INTEGER,
  reusable             INTEGER NOT NULL DEFAULT 0,
  updated_at           TEXT NOT NULL,
  created_at           TEXT NOT NULL,
  UNIQUE (campaign_id, params_hash, request_no)
);

-- Müşteri yorumları ve izin (KVKK) ------------------------------------------
CREATE TABLE reviews (
  id                     INTEGER PRIMARY KEY,
  brand_id               INTEGER NOT NULL REFERENCES brands(id),
  text                   TEXT NOT NULL,
  display_name           TEXT,
  name_display_mode      TEXT NOT NULL CHECK (name_display_mode IN ('full','initials','hidden')),
  rating                 REAL,
  source                 TEXT,
  consent_type           TEXT,
  consent_date           TEXT,
  consent_evidence_path  TEXT,
  processing_scope_json  TEXT,
  withdrawn_at           TEXT,
  created_at             TEXT NOT NULL
);

CREATE TABLE person_consents (
  id                     INTEGER PRIMARY KEY,
  brand_id               INTEGER NOT NULL REFERENCES brands(id),
  person_label           TEXT NOT NULL,
  scope                  TEXT NOT NULL CHECK (scope IN ('image','voice','image_voice')),
  consent_type           TEXT,
  consent_date           TEXT,
  evidence_path          TEXT,
  processing_scope_json  TEXT,
  withdrawn_at           TEXT,
  created_at             TEXT NOT NULL
);

-- Yayın eşlemesi ve performans ----------------------------------------------
CREATE TABLE ads (
  id                INTEGER PRIMARY KEY,
  brand_id          INTEGER NOT NULL REFERENCES brands(id),
  campaign_id       INTEGER REFERENCES campaigns(id),
  cycle_id          INTEGER REFERENCES cycles(id),
  creative_key      TEXT,          -- Meta geçmişindeki plugin dışı reklamlarda NULL
  meta_ad_id        TEXT NOT NULL,
  meta_ad_name      TEXT,
  adset_id          TEXT,
  campaign_meta_id  TEXT,
  launched_at       TEXT,
  status            TEXT,
  UNIQUE (brand_id, meta_ad_id)
);

CREATE TABLE metrics_daily (
  ad_id                     INTEGER NOT NULL REFERENCES ads(id),
  date                      TEXT NOT NULL,
  impressions               INTEGER,
  reach                     INTEGER,
  frequency                 REAL,
  spend                     REAL,
  cpm                       REAL,
  video_3s                  REAL,
  video_3s_derived          INTEGER NOT NULL DEFAULT 0,   -- amount_spent / cost_per_video_view ile türetildi (9.2)
  thruplay                  INTEGER,
  p25                       INTEGER,
  p50                       INTEGER,
  p75                       INTEGER,
  p95                       INTEGER,
  p100                      INTEGER,
  avg_watch_s               REAL,
  link_clicks               INTEGER,
  ctr_link                  REAL,
  results                   INTEGER,
  result_type               TEXT,
  add_to_cart               INTEGER,
  purchases                 INTEGER,
  revenue                   REAL,
  source                    TEXT NOT NULL CHECK (source IN ('meta_mcp','csv','synthetic')),
  fetched_at                TEXT NOT NULL,
  measurement_context_json  TEXT NOT NULL,
  measurement_fingerprint   TEXT NOT NULL,
  PRIMARY KEY (ad_id, date)
);

-- Koçluk (6) ----------------------------------------------------------------
CREATE TABLE sales_manual (
  id            INTEGER PRIMARY KEY,
  campaign_id   INTEGER NOT NULL REFERENCES campaigns(id),
  period_start  TEXT NOT NULL,
  period_end    TEXT NOT NULL,
  units         INTEGER,
  revenue       REAL,
  source_note   TEXT,
  created_at    TEXT NOT NULL
);

CREATE TABLE input_snapshots (       -- değişmez karar girdisi kopyaları (6.4)
  id           INTEGER PRIMARY KEY,
  profile_id   INTEGER NOT NULL REFERENCES profiles(id),
  campaign_id  INTEGER REFERENCES campaigns(id),
  cycle_id     INTEGER REFERENCES cycles(id),
  kind         TEXT NOT NULL,          -- coach_report | coach_draft | budget_alert | prediction_outcome
  version      INTEGER NOT NULL,
  path         TEXT NOT NULL,
  sha256       TEXT NOT NULL,
  created_at   TEXT NOT NULL,
  UNIQUE (cycle_id, kind, sha256)
);

CREATE TABLE action_items (
  id              INTEGER PRIMARY KEY,
  campaign_id     INTEGER NOT NULL REFERENCES campaigns(id),
  cycle_id        INTEGER REFERENCES cycles(id),
  decision_id     INTEGER REFERENCES decisions(id),
  action          TEXT NOT NULL,
  target_meta_id  TEXT,
  reason_kind     TEXT NOT NULL DEFAULT 'performance' CHECK (reason_kind IN ('performance','limit','consent','structure')),
  before_json     TEXT,
  after_json      TEXT,
  status          TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','approved','applied','not_applied')),
  dedupe_key      TEXT,
  evidence_json   TEXT,
  created_at      TEXT NOT NULL,
  verified_at     TEXT
);
CREATE UNIQUE INDEX ux_action_open ON action_items(campaign_id, dedupe_key) WHERE dedupe_key IS NOT NULL AND status IN ('proposed','approved');

CREATE TABLE coaching_predictions (
  id                   INTEGER PRIMARY KEY,
  campaign_id          INTEGER NOT NULL REFERENCES campaigns(id),
  cycle_id             INTEGER REFERENCES cycles(id),
  subject              TEXT NOT NULL,
  metric               TEXT NOT NULL,
  p_win                REAL,
  interval_json        TEXT,
  input_snapshot_json  TEXT NOT NULL,
  made_at              TEXT NOT NULL,
  outcome_json         TEXT,
  resolved_at          TEXT,
  supersedes_id        INTEGER REFERENCES coaching_predictions(id),  -- aynı test/özne/metrik için rapor sürümü (6.13)
  UNIQUE (cycle_id, subject, metric, input_snapshot_json)
);

-- Öğrenme -------------------------------------------------------------------
CREATE TABLE playbook_rules (
  id                       INTEGER PRIMARY KEY,
  profile_id               INTEGER NOT NULL REFERENCES profiles(id),
  rule                     TEXT NOT NULL,
  scope_json               TEXT,
  season                   TEXT,
  evidence_json            TEXT,
  confidence               REAL,
  status                   TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','active','due_revalidation','retired')),
  consistent_rounds        INTEGER NOT NULL DEFAULT 0,
  contradicted_rounds      INTEGER NOT NULL DEFAULT 0,
  rounds_since_validation  INTEGER NOT NULL DEFAULT 0,
  created_at               TEXT NOT NULL,
  last_validated_at        TEXT,
  retired_reason           TEXT
);

-- Hafıza (8) ----------------------------------------------------------------
CREATE TABLE journal (
  id            INTEGER PRIMARY KEY,
  profile_id    INTEGER REFERENCES profiles(id),   -- NULL: sistem hafızası (8.9)
  campaign_id   INTEGER REFERENCES campaigns(id),
  ts            TEXT NOT NULL,
  type          TEXT NOT NULL,
  summary       TEXT NOT NULL,
  detail_json   TEXT,
  links_json    TEXT,
  cost_credits  REAL,
  rolled        INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX ix_journal_profile ON journal(profile_id, ts);

CREATE TABLE journal_rollups (
  id            INTEGER PRIMARY KEY,
  profile_id    INTEGER REFERENCES profiles(id),
  period        TEXT NOT NULL CHECK (period IN ('day','week','month')),
  period_start  TEXT NOT NULL,
  summary       TEXT NOT NULL,
  created_at    TEXT NOT NULL,
  UNIQUE (profile_id, period, period_start)
);

CREATE TABLE memory_items (
  id                 INTEGER PRIMARY KEY,
  profile_id         INTEGER REFERENCES profiles(id),  -- NULL: sistem hafızası
  layer              TEXT NOT NULL CHECK (layer IN ('semantic','preference','procedural')),
  kind               TEXT NOT NULL,
  content            TEXT NOT NULL,
  scope_json         TEXT,
  tags               TEXT,
  confidence         REAL NOT NULL DEFAULT 0.5,
  evidence_json      TEXT NOT NULL DEFAULT '[]',
  source             TEXT NOT NULL,
  status             TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','active','due_revalidation','retired','superseded','archived')),
  observations       INTEGER NOT NULL DEFAULT 1,
  conflict_json      TEXT,
  created_at         TEXT NOT NULL,
  last_used_at       TEXT,
  last_validated_at  TEXT,
  use_count          INTEGER NOT NULL DEFAULT 0,
  superseded_by      INTEGER REFERENCES memory_items(id)
);
CREATE INDEX ix_memory_profile ON memory_items(profile_id, layer, status);

CREATE TABLE memory_usage (
  id          INTEGER PRIMARY KEY,
  item_id     INTEGER NOT NULL REFERENCES memory_items(id) ON DELETE CASCADE,
  profile_id  INTEGER REFERENCES profiles(id),
  stage       TEXT,
  via         TEXT NOT NULL CHECK (via IN ('context','search')),
  ts          TEXT NOT NULL,
  cycle_no    INTEGER
);

CREATE TABLE resume_state (
  id            INTEGER PRIMARY KEY,
  profile_id    INTEGER NOT NULL REFERENCES profiles(id),
  campaign_id   INTEGER REFERENCES campaigns(id),
  cycle_id      INTEGER REFERENCES cycles(id),
  stage_run_id  INTEGER REFERENCES stage_runs(id),
  stage         TEXT NOT NULL,
  scope_key     TEXT NOT NULL,
  origin        TEXT NOT NULL DEFAULT 'interactive' CHECK (origin IN ('interactive','job')),
  state_json    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  closed_at     TEXT
);
CREATE UNIQUE INDEX ux_resume_open ON resume_state(scope_key, stage, origin) WHERE closed_at IS NULL;

CREATE TABLE scene_cache (
  key          TEXT PRIMARY KEY,
  profile_id   INTEGER NOT NULL REFERENCES profiles(id),
  campaign_id  INTEGER REFERENCES campaigns(id),
  path         TEXT NOT NULL,
  sha256       TEXT NOT NULL,
  meta_json    TEXT,
  created_at   TEXT NOT NULL
);

CREATE VIRTUAL TABLE memory_fts USING fts5(
  body,
  kind UNINDEXED,
  ref_id UNINDEXED,
  profile_id UNINDEXED,
  tokenize = 'trigram'
);
