---
name: ingest
description: "reklam-atolyesi S06 ingest — telefon çekimlerini güvenli kurgu girdisine çevirir: SHA-256, VFR→CFR, HLG/PQ→SDR, proxy, sarsıntı ölçümü ve sabitleme, ses, HEIC/EXIF fotoğraflar."
---

# ingest — S06 · Ingest (spec 5.4, 5.1, bölüm 10)

## Amaç
`footage/raw/` ve `photos/raw/` dosyalarını kurguya güvenli girdiye çevirmek. **Ham çekime dokunulmaz;** bütün işlemler kopyalar
üzerinde yapılır. Kayıtlar `asset_register` ile `ad-memory`'ye işlenir (script veritabanına yazmaz).

## Ön koşul
- Kampanya S06'da (`shoot_mark_done` sonrası) ya da gece üretimi işi bu kampanya/tur için çalışıyor.
- Yükleme öncesi izin kapısı: tanınabilir kişi içeren klipler için `consent_query` ile izin; ingest yerel çalışır (dışarı gönderim yok).

## Girdiler ve bağlam paketi
`memory_context(profile_id, "S06", campaign_id, cycle_id)` (ingest prosedürleri, kampanyanın varlık özeti). Kampanya klasörü
`DD/profiles/<slug>/campaigns/<k>/`.

## Kullanılan hazır skill'ler ve OVERRIDES
- **ffmpeg**: önce `PR/vendor-skills/ffmpeg/OVERRIDES.md`, sonra `PR/vendor-skills/ffmpeg/SKILL.md` ve `reference.md` — yalnızca yöntem
  referansı (kesme, ölçekleme, ses çıkarma). Teslim parametreleri ve upstream sıkıştırma ayarları kullanılmaz; uygulama plugin script'idir.

## Adımlar
1. `stage_start(profile_id, "S06", campaign_id, cycle_id)` (yarım kalmış koşuda `stage_resume` ile doğrulanmış çıktılar korunur).
2. Çalıştır (uzun sürebilir; arka planda, kullanıcıya süre tahminiyle):
   `PY PR/scripts/ingest/convert.py ingest --campaign-dir <kampanya_klasörü> --fps 30`
   (yavaş çekim için 4K 60 çekilmiş kliplerde `--fps 60`; `--only <dosya…>` yalnızca eksikleri işler). Her klip için:
   ffprobe (çözünürlük, fps, VFR, döndürme, HLG/PQ, ses) → VFR→CFR + HDR→Rec.709 SDR (`zscale`+`tonemap`; 4K korunur) →
   proxy (1080 kısa kenar, H.264) → `vidstabdetect` sarsıntı ölçümü (‰; eşik 4,0) → eşiği aşanda `vidstabtransform` ile **ayrı**
   sabitlenmiş kopya (ham ve sabit ikisi de saklanır; hangisinin kullanılacağına S07 karar verir) → gömülü ses `audio/raw/<ad>.wav`.
   Fotoğraflar: EXIF yönü uygulanır, HEIC → JPEG (`pillow-heif`), `photos/`.
   Çıktı: `analysis/ingest_manifest.json` (kaynak ve türev SHA-256'ları, notlar: "VFR → CFR", "HLG → SDR"). Tek klip hatası bütün
   ingest'i durdurmaz; `errors` listesinde kullanıcıya söylenir.
3. Her video için `asset_register(profile_id, kind="footage", path=<cfr_sdr>, campaign_id, product_id, source="shoot",
   shot_no=<dosya adındaki çekim numarası ya da null>, audio={has_audio, wav}, meta={probe, proxy, proxy_sha256, stabilized,
   shake_permille, raw_path, raw_sha256}, tags)`; her fotoğraf için `kind="photo"`. Aynı SHA-256 profilde tekrar kayıt açmaz
   (çekim kütüphanesi, 5.5).
4. `stage_complete(profile_id, "S06", outputs=[{path: "…/analysis/ingest_manifest.json"}], summary, campaign_id, cycle_id)` → S07.
   (Kapı yok.)

## Çıktılar
`footage/graded/*_cfr.mov`, `footage/proxy/*_proxy.mp4`, `footage/stab/*_stab.mov` (gerekirse), `analysis/trf/*.trf`, `audio/raw/*.wav`,
`photos/*.jpg`, `analysis/ingest_manifest.json`, `assets` kayıtları, devam notu.

## Kontroller
- Ham dosyaların SHA-256'sı ingest öncesi/sonrası aynı (dokunulmadı).
- HDR işaretli her klip SDR'ye, VFR her klip CFR'ye çevrildi; proxy var; sarsıntı ölçüldü.
- Hatalı klipler kullanıcıya listelendi; eksik dosya "tamamlandı" sayılmadı.

## Kapı mesajı
Kapı yoktur. Geçiş özeti: "N klip, M fotoğraf işlendi (VFR→CFR: …, HDR→SDR: …, sabitlenen: …). Hata: <yok|…>. Analize geçiyorum."
