-- 010 (2.10.3): sahne önbelleği anahtarı profil kapsamında tekildir (profil yalıtımı, 2.3). Önceden anahtar bütün veritabanında
-- tekildi: iki profil aynı anahtarı yazınca kayıt ilk profilde kalıyor, dosya yolu ikinci profilinki oluyordu. Mevcut satırlar aynen
-- taşınır; önbellek kaybolsa bile sahne yeniden üretilir (önbellek yalnızca hız içindir).
CREATE TABLE scene_cache_new (
  key          TEXT NOT NULL,
  profile_id   INTEGER NOT NULL REFERENCES profiles(id),
  campaign_id  INTEGER REFERENCES campaigns(id),
  path         TEXT NOT NULL,
  sha256       TEXT NOT NULL,
  meta_json    TEXT,
  created_at   TEXT NOT NULL,
  PRIMARY KEY (profile_id, key)
);
INSERT INTO scene_cache_new(key, profile_id, campaign_id, path, sha256, meta_json, created_at)
  SELECT key, profile_id, campaign_id, path, sha256, meta_json, created_at FROM scene_cache;
DROP TABLE scene_cache;
ALTER TABLE scene_cache_new RENAME TO scene_cache;
