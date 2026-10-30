-- 008 (2.3.0): Advantage+ kreatif iyileştirmeleri. Yalnızca sütun ekler.
-- Turun yayınında iyileştirme durumu (S14 launch_confirm): {checked, source, on: [{name, kind, creative_keys?}], off: [name]}.
-- Meta bazı iyileştirmeleri varsayılan açar ve medya/metni ayarlayabilir (help/1082295769403815), açık kalan iyileştirme kreatif
-- testinde ikinci bir değişkendir, hüküm diline kayıt olarak girer.
ALTER TABLE cycles ADD COLUMN enhancements_json TEXT;
