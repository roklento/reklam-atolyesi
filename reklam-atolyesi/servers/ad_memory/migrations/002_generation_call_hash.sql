-- 002: ücretli üretimde hook eşleşmesi (9.1, 13.6).
-- params_hash girdi dosyası hash'lerini de içerir (onay ve tekrar koruması bu kanonik çağrıya bağlıdır).
-- cost_guard hook'u yalnızca aracın gerçek çağrı parametrelerini görür; dosya hash'lerini bilemez. Bu yüzden aynı kanonik
-- koddan, dosya hash'leri olmadan hesaplanan call_hash ayrıca saklanır ve rezervasyon onunla eşleşir.
ALTER TABLE generations ADD COLUMN call_hash TEXT;
ALTER TABLE generations ADD COLUMN input_files_json TEXT;
UPDATE generations SET call_hash = params_hash WHERE call_hash IS NULL;
CREATE INDEX IF NOT EXISTS idx_generations_call_hash ON generations(campaign_id, call_hash);
