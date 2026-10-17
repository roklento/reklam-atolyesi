-- 003: 'buyer' (video kime konuşuyor) profil ekseni ve ürünün alıcı listesi (sözlük 1.5.0, S00c ve S03).
-- SQLite CHECK kısıtını değiştiremez. taxonomy_values aynı sütunlarla yeniden kurulur, satırlar ve kimlikleri korunur.
-- Bu tabloya başka bir tablo yabancı anahtarla bağlanmaz.
CREATE TABLE taxonomy_values_new (
  id                INTEGER PRIMARY KEY,
  profile_id        INTEGER NOT NULL REFERENCES profiles(id),
  axis              TEXT NOT NULL CHECK (axis IN ('angle','moment','buyer','emotion','tone')),
  code              TEXT NOT NULL,
  label             TEXT NOT NULL,
  status            TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','active','retired')),
  taxonomy_version  TEXT NOT NULL,
  created_at        TEXT NOT NULL,
  UNIQUE (profile_id, axis, code)
);
INSERT INTO taxonomy_values_new(id, profile_id, axis, code, label, status, taxonomy_version, created_at)
  SELECT id, profile_id, axis, code, label, status, taxonomy_version, created_at FROM taxonomy_values;
DROP TABLE taxonomy_values;
ALTER TABLE taxonomy_values_new RENAME TO taxonomy_values;

-- Ürünü kimin aldığı: [{code, label}], her değer taxonomy_values'ta axis='buyer' (occasions_json'daki anların karşılığı).
ALTER TABLE products ADD COLUMN buyers_json TEXT;
