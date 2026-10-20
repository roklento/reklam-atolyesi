-- 004 (1.4.7): Meta'nın satışı görüp görmediği (piksel/CAPI/yükleme sinyali) ve elle satışın kanalı.
-- Yalnızca sütun eklenir; tablo yeniden kurulmaz, satırlar ve kimlikler değişmez.
-- meta_signal_json: {status: purchase_seen|no_purchase|unknown, source, evidence, checked_at, choice?} (S00b/S01; meta_signal_set).
ALTER TABLE profiles ADD COLUMN meta_signal_json TEXT;
-- channel: shopier|site|instagram_dm|whatsapp|kurumsal|magaza|diger (doğrulama kodda); kind: sale|lead (talep/teklif isteği).
ALTER TABLE sales_manual ADD COLUMN channel TEXT;
ALTER TABLE sales_manual ADD COLUMN kind TEXT NOT NULL DEFAULT 'sale';
