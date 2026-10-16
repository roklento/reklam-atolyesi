---
name: analyze
description: "reklam-atolyesi S07 analiz — klip başına ölçüm ve kontak sayfası (workflow analyze-footage ya da footage-analyst yedek yolu), puanlar, en iyi aralıklar, malzeme haritası, çekim kütüphanesi."
---

# analyze — S07 · Analiz ve malzeme haritası (spec 5.5, 5.3, 4.2 hızlı tur)

## Amaç
Her klibi ölçmek (netlik, pozlama, sarsıntı, hareket, ses, kişi), kontak sayfasına bakarak çekim menüsüne eşlemek ve puanlamak; kampanya
için **malzeme haritası** çıkarmak: çekim menüsü numarası → en iyi klip ve aralık, eksik çekimler, AI ile tamamlanabilecekler,
gerçek çekimli eşin kullanılabilirliği.

## Ön koşul
- Tam turda S06 tamam (ingest manifesti ve `assets` kayıtları). Hızlı turda (S04–S06 `skipped`) malzeme profil çekim kütüphanesinden.
- `analysis/shoot_menu.json` (tam tur) ya da S03'teki konsept → kütüphane eşleşmesi (hızlı tur).

## Girdiler ve bağlam paketi
`memory_context(profile_id, "S07", campaign_id, cycle_id)`: seçilen konseptler, çekim menüsü, kampanya varlık özeti, analiz prosedürleri.
`asset_query(profile_id, campaign_id=…, kind="footage")`; hızlı turda `asset_query(profile_id, scope="profile", …)`.

## Kullanılan hazır skill'ler ve OVERRIDES
- **motion-design**: önce `PR/vendor-skills/motion-design/OVERRIDES.md`; sonra `PR/vendor-skills/motion-design/SKILL.md` içindeki
  `## 8. Critique loop` (modelin kendi karelerine bakması → kontak sayfasıyla doğrulama). Stok indirme, AI yüz ve HTML render uygulanmaz.
- **ffmpeg**: `PR/vendor-skills/ffmpeg/OVERRIDES.md` → `SKILL.md` (kare çıkarma yöntemi; uygulama plugin script'i).

## Adımlar
1. `stage_start(profile_id, "S07", campaign_id, cycle_id)`.
2. **Klip başına analiz (paralel):** workflow `analyze-footage` — `PR/workflows/analyze-footage.js`, args: `{profile_id, campaign_id,
   cycle_id, campaign_dir, plugin_root, data_dir, py, clips:[{asset_id, proxy, wav, shake_permille, shot_hint}], shoot_menu_path, now_iso}`.
   Her klip için `footage-analyst` ajanı: `measure.py` + `contact_sheet.py` + kontak sayfasına bakış → `clip_<asset_id>.json`.
   **Yedek yol (13.2):** workflow yoksa ya da hata verirse aynı ajanı klip başına alt ajan olarak çağır (Agent aracı,
   `subagent_type: "reklam-atolyesi:footage-analyst"`, eşzamanlı en fazla `max(1, floor(CPU/2))`); `clip_<id>.json` hazır olan klipler
   tekrar işlenmez. Hangi yolun kullanıldığı `journal_log`'a yazılır.
   Ajanın tek klip komutları (referans):
   `PY PR/scripts/analyze/measure.py --clip <proxy> --shake-permille <‰> --audio <wav> --out analysis/clips/<id>_measure.json`
   `PY PR/scripts/analyze/contact_sheet.py --video <proxy> --out analysis/clips/<id>_sheet.jpg` (6×4, zaman damgalı)
3. **Kayıt:** her klip için `asset_register(profile_id, kind="footage", path, campaign_id, shot_no, score={sharpness, exposure, shake,
   motion, audio, overall}, best_ranges=[{in_s, out_s, why}], audio={usable, noise_floor_db, speech, snr_db, suggestion}, people=[{t, kind,
   speaking, consent_id?}], tags, notes)` (aynı SHA-256 → güncelleme). Sabitlenmiş kopya mı ham mı: `meta.use_stabilized`.
4. **Kişi ve izin:** kişi tespit edilen her klip `consent_query` ile eşlenir; izinsiz/geri çekilmiş kişili klip **kullanılamaz** diye
   işaretlenir (`tags` + `notes`). Kamerada konuşan kişi varsa not edilir (S09'da yalnızca `original`/`original_clean`).
5. **Malzeme haritası:** `clips.json` (`[{asset, shot_no, score, best_ranges, used_in, path}]`) hazırla →
   `PY PR/scripts/analyze/material_map.py --menu analysis/shoot_menu.json --clips analysis/clips.json [--photos analysis/photos.json]
   --out analysis/material-map.md --json-out analysis/material-map.json`.
   Harita: menü no → en iyi klip ve aralık · eksik çekimler · AI ile tamamlanabilecekler · AI planlı sahnelerde **gerçek çekimli eşin**
   bulunup bulunmadığı (yoksa ücretli AI üretiminden önce ek çekim istenir ya da konsept mevcut gerçek malzemeye uyarlanır) ·
   daha önce yayınlanmış bir kreatifte açılış karesi olmuş klip uyarısı (Meta gözünde aynı varlığa yakınlaşır).
6. **Hızlı tur:** `clips.json` profil kütüphanesinden (`asset_query(scope="profile")`); eksik çekim çıkarsa yalnızca onlar için kısa S04
   önerilir.
7. `stage_complete(profile_id, "S07", outputs=[{path: material-map.md}, {path: material-map.json}], summary, campaign_id, cycle_id)` → S08.

## Çıktılar
`analysis/clips/*` (ölçüm + kontak sayfası), `analysis/clips.json`, `analysis/material-map.{md,json}`, güncellenmiş `assets` (puan, aralık,
ses, kişi), devam notu; tekrarlayan çekim sorunları `memory_add(layer="procedural")`.

## Kontroller
- Her klip için `score_json` (0–1) ve 2–5 sn'lik en iyi aralıklar; kontak sayfasına gerçekten bakıldı (puanlar tek başına içerik eşlemesi değildir).
- Eksik çekimler ve gerçek çekimli eş durumu açık; izinsiz kişili klip kullanılabilir listesinde değil.

## Kapı mesajı
Kapı yoktur. Geçiş özeti: "N klip analiz edildi; menüden M/K çekim karşılandı. Eksik: … AI ile tamamlanabilecek: … (gerçek eşi: …).
Ses kullanılabilir klipler: …. Stil yönlerine geçiyorum."
