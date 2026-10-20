-- 005 (1.4.8): mesajla satış (DM/WhatsApp/Messenger/telefon), mağaza sipariş içe aktarma ve veri bağlantısı planı.
-- Yeni tablolar ve sütunlar eklenir; mevcut tablo yeniden kurulmaz, satırlar ve kimlikler değişmez.
-- Kişisel veri tutulmaz: konuşmalar takma kodla (M-0001), siparişler numaranın SHA-256 özetiyle saklanır.

ALTER TABLE profiles ADD COLUMN data_connection_json TEXT;

CREATE TABLE dm_threads (
  id                 INTEGER PRIMARY KEY,
  brand_id           INTEGER NOT NULL REFERENCES brands(id),
  campaign_id        INTEGER REFERENCES campaigns(id),
  ref                TEXT NOT NULL,
  channel            TEXT NOT NULL CHECK (channel IN ('instagram_dm','messenger','whatsapp','phone','web_chat','email','other')),
  source             TEXT NOT NULL DEFAULT 'unknown' CHECK (source IN ('ad','organic','referral','repeat','unknown')),
  source_evidence    TEXT,
  meta_ad_id         TEXT,
  creative_key       TEXT,
  segment            TEXT NOT NULL DEFAULT 'unknown' CHECK (segment IN ('individual','corporate','reseller','unknown')),
  intent             TEXT NOT NULL DEFAULT 'other' CHECK (intent IN ('price','shipping','personalization','bulk','stock','payment','return','product_info','other')),
  status             TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','qualified','quoted','won','lost','stale')),
  lost_reason        TEXT CHECK (lost_reason IS NULL OR lost_reason IN ('price','shipping_time','shipping_cost','no_reply','stock',
                                                                        'personalization','payment','trust','competitor','other')),
  quantity           INTEGER,
  quote_amount       REAL,
  won_amount         REAL,
  currency           TEXT,
  paid_via           TEXT CHECK (paid_via IS NULL OR paid_via IN ('store_link','bank_transfer','cash_on_delivery','card_link','in_person','other')),
  opened_at          TEXT NOT NULL,
  opened_date        TEXT NOT NULL,          -- markanın saat dilimindeki gün (günlük toplamlarla aynı gün tanımı)
  first_response_at  TEXT,
  closed_at          TEXT,
  next_follow_up_at  TEXT,
  created_at         TEXT NOT NULL,
  updated_at         TEXT NOT NULL,
  UNIQUE (brand_id, ref)
);
CREATE INDEX idx_dm_threads_campaign ON dm_threads(campaign_id, opened_at);
CREATE INDEX idx_dm_threads_day ON dm_threads(brand_id, opened_date, channel);

CREATE TABLE dm_events (
  id          INTEGER PRIMARY KEY,
  thread_id   INTEGER NOT NULL REFERENCES dm_threads(id),
  at          TEXT NOT NULL,
  kind        TEXT NOT NULL CHECK (kind IN ('opened','responded','qualified','quoted','won','lost','stale','reopened','follow_up','note')),
  amount      REAL,
  note        TEXT,
  created_at  TEXT NOT NULL
);
CREATE INDEX idx_dm_events_thread ON dm_events(thread_id, at);

-- Günlük toplamlar markanın o gün ve kanaldaki TÜM konuşmalarıdır (tek tek kaydedilenler dahil). Kampanyaya bölünmez: kullanıcı
-- DM'leri kampanyalara ayıramaz; kampanya bağı yalnızca tek tek kaydedilen konuşmada ve kanıtıyla kurulur.
CREATE TABLE dm_daily (
  id             INTEGER PRIMARY KEY,
  brand_id       INTEGER NOT NULL REFERENCES brands(id),
  date           TEXT NOT NULL,
  channel        TEXT NOT NULL CHECK (channel IN ('instagram_dm','messenger','whatsapp','phone','web_chat','email','other')),
  conversations  INTEGER NOT NULL,
  from_ads       INTEGER,
  qualified      INTEGER,
  quoted         INTEGER,
  won            INTEGER,
  note           TEXT,
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL
);
CREATE UNIQUE INDEX ux_dm_daily ON dm_daily(brand_id, date, channel);

CREATE TABLE sales_imports (
  id            INTEGER PRIMARY KEY,
  brand_id      INTEGER NOT NULL REFERENCES brands(id),
  campaign_id   INTEGER REFERENCES campaigns(id),
  platform      TEXT NOT NULL,
  file_name     TEXT NOT NULL,
  file_sha256   TEXT NOT NULL,
  mapping_json  TEXT NOT NULL,
  rows_total    INTEGER NOT NULL,
  rows_new      INTEGER NOT NULL,
  rows_dup      INTEGER NOT NULL,
  rows_skipped  INTEGER NOT NULL,
  date_from     TEXT,
  date_to       TEXT,
  created_at    TEXT NOT NULL,
  UNIQUE (brand_id, file_sha256)
);

CREATE TABLE sales_orders (
  id          INTEGER PRIMARY KEY,
  brand_id    INTEGER NOT NULL REFERENCES brands(id),
  campaign_id INTEGER REFERENCES campaigns(id),
  import_id   INTEGER NOT NULL REFERENCES sales_imports(id),
  order_hash  TEXT NOT NULL,
  date        TEXT NOT NULL,
  amount      REAL,
  units       INTEGER,
  currency    TEXT,
  status      TEXT NOT NULL CHECK (status IN ('paid','pending','cancelled','refunded','unknown')),
  channel     TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  UNIQUE (brand_id, order_hash)
);
CREATE INDEX idx_sales_orders_date ON sales_orders(brand_id, date);
