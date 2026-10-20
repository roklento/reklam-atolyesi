---
name: variants
description: "reklam-atolyesi S12 varyasyon ve export — plan yamaları, 9:16 + 4:5 final render (workflow ya da editor yedek yolu), statik/carousel, AI'sız eş, adlandırma ve kreatif kaydı."
---

# variants — S12 · Varyasyon ve export (spec 5.16–5.19, 5.21, 6.3)

## Amaç
Onaylı taslaktan bütün teslim dosyalarını üretmek: varyasyonlar **plan yamalarıdır**, formatlar aynı reklamın yerleşim varyantlarıdır,
her dosya adlandırma kuralıyla çıkar ve `creative_register` ile kaydedilir. S02 tavanı **ayrı ölçülecek reklam sayısına** uygulanır.

## Ön koşul
S11 taslak kapısı geçilmiş (onaylı `ready` plan ve miks).

## Girdiler ve bağlam paketi
`memory_context(profile_id, "S12", campaign_id, cycle_id)`: kurgu prosedürleri, kreatif tavanı, güncel planlar. `cycles.budget_plan_json`
(`allowed_test_ads`), `c<tur>-hooks.csv`, `photos/` (fotoğraf listesi), `analysis/material-map.json`, `strategy_get` (rol), `taxonomy_get`.

## Kullanılan hazır skill'ler ve OVERRIDES
- **ad-creative-video**: `PR/vendor-skills/ad-creative-video/OVERRIDES.md` → `SKILL.md` ("1 şablon × CSV = N varyasyon", çoklu en-boy
  export mantığı; şablon bizim Remotion projemiz, tablo `hooks.csv`) ve `references/platform-specs.md` (yalnızca bilgi; güvenli alan 5.19).
- **testimonial-video**: `PR/vendor-skills/testimonial-video/OVERRIDES.md` → `SKILL.md`, `references/quote-card.md` (alıntı kartı yöntemi;
  yalnızca izinli gerçek yorum, metin birebir, yıldız yalnızca gerçek puan).
- **remotion render (resmi bilgi)**: vendor kopyası yok; `ref-vendor-map` → renderMedia/renderStill belge bölümleri.
- **ffmpeg**: `PR/vendor-skills/ffmpeg/OVERRIDES.md` (export kuralları plugin'indir).

## Adımlar
1. `stage_start(profile_id, "S12", campaign_id, cycle_id)`.
2. **Varyasyon listesi:** varsayılan ilk tur = konsept × S03'te seçilen test hook'u × 15 sn. Keşifte konsept başına tek test açılışı
   olur; S03'te yedek seçilen hook'ların çıktıları `reserve` kalır (sunucu yedek hook'la `test` kaydını reddeder). Birincil doğrulama
   çiftinde iki kol iki test hook'u olabilir. VO'lu/VO'suz ve 6 sn sürümleri yalnızca bütçe izin veriyorsa ya da kazanan konseptlerde.
   20 sn uzun kesim marka filmidir; test matrisine girmez. Her çıktıya `delivery_role`: `test` (ayrı reklam,
   ayrı ölçülür) ya da `reserve` (yükleme listesi dışında). Test sayısı **tavanı aşamaz**; aşarsa fazlası `reserve` (sessizce yayına eklenmez).
   Statik, carousel, hook/VO/süre farkı ve AI'sız eş ayrı reklam olarak yayınlanacaksa tavandan yer alır.
3. **Yamalar:** `edit_plan_patch(profile_id, plan_id, ops)` — hook değişimi, süre kesimi (15 → 6), format yeniden kadrajlama (yazılar
   format başına `style.layout`'tan yeniden yerleşir; video formatın en-boy oranına göre kadrajlanır), VO aç/kapa, **AI'sız eş** (AI
   katmanları gerçek çekimle değiştirilir). Her yama planın yeni sürümü (`parent_id` zinciri) → `edit_plan_validate`.
4. **AI'sız eş:** AI klibi içeren her varyasyonun yanında tamamen gerçek çekimli eşi hazırlanır (varsayılan `reserve`; teste alınırsa
   ayrı reklam). Gerekli gerçek malzeme yoksa bu madde **tamamlandı sayılmaz** ve kullanıcıya söylenir.
5. **Final sahne ara dosyaları:** `PY PR/scripts/ingest/scenes.py --plan <plan> --assets <asset_files.json> --out-dir footage/scenes
   --quality final --style <style> --map-out footage/scenes/map_final.json` (4K kaynaktan, sahnenin yaklaşma payını taşıyan en küçük çözünürlük).
6. **Render (paralel):** workflow `render-variants` — `PR/workflows/render-variants.js`, args: `{profile_id, campaign_id, cycle_id,
   data_dir, plugin_root, py, project, cpu_count, parallel_jobs, now_iso, jobs:[{key, plan_path, format, out, style, scene_map, captions,
   quality:"final"}]}`.
   Toplam işçi bütçesi `max(1, floor(CPU/2))`; `J` paralel render için her birinin concurrency'si `floor(bütçe/J)`, `J ≤ bütçe`.
   **Yedek yol (13.2):** workflow yoksa/hata verirse `editor` ajanını format/varyasyon başına alt ajan olarak çağır (aynı paralellik
   sınırıyla); tamamlanmış ve hash'i doğrulanmış çıktılar tekrar render edilmez. Hangi yol kullanıldı → `journal_log`.
   Tek render komutu: `PY PR/scripts/render/render.py plan --data-dir DD --project <src> --plan <plan> --out <mp4> --style <style>
   --scene-map footage/scenes/map_final.json --captions <words.json> --quality final --parallel-jobs <J>` (sahne önbelleği değişmeyen
   sahneyi yeniden render etmez).
7. **Export ve adlandırma:** anahtar `PY PR/scripts/render/export.py key --brand <MRK> --campaign <K1> --concept A --media video
   --duration 15 --hook h1 --vo|--no-vo --source real|ai --cycle <n> --rev <r>`; dosya
   `PY PR/scripts/render/export.py video --video <render.mp4> --audio audio/stems/mix_final.wav --out-dir out/ --key <creative_key> --format 9x16`
   (H.264 High, yuv420p, 30 fps CFR, CRF 16–18, AAC 48 kHz 256 kbps, `+faststart`). Adlandırma:
   `<MARKA>_<KAMPANYA>_<KONSEPT>_<MEDYA>_<SÜRE>_<HOOK>_<VO>_<KAYNAK>_<TUR>_<REV>_<FORMAT>[_k<KART>]`; `creative_key` = format ve kart
   numarası çıkarılmış hali (Meta reklam adı).
   **Aç kalan konseptin yeniden testi (S16 `carry_over`):** yeni render yok; önceki turun final dosyası yeni tur anahtarıyla yeniden dışa
   aktarılır: `export.py video --video <eski final.mp4> --audio <eski final.mp4> --out-dir out/ --key <c<tur> anahtarı> --format <f>`
   (görüntü kopyalanır, ses aynı dosyadan alınıp -1 dBTP kontrolünden geçer; `--audio` verilmezse ses düşer). Kayıt `creative_register`
   ile bu turda; QC (S13) yeniden yapılır.
8. **Statik ve carousel (5.17):** her konsept için önce aynı oturumun **fotoğraflarından** en güçlü kare(ler); yoksa/yetersizse plan
   video karelerine düşülür ve raporda belirtilir. Öz denetim → format başına yazı → gerekirse AI görsel desteği (`materials` protokolü
   ve AI etiketi) → statik 1080×1350 (istenirse 1080×1080) ve 3–5 kartlık carousel (hook → ürün → kanıt → CTA):
   `render.py plan … --still <kare>` (Master-45 / Master-11) + `export.py name --key … --format 4x5 [--card n] --ext jpg`.
9. **Öz denetim** her final çıktıda (`self_review.py`) ve teknik ön kontrol (`PY PR/scripts/qc/checks.py tech --video <mp4> --plan <plan>
   --expect-duration 15 --format 9x16`). Uzun render'lar arka planda; her final render süresi sistem hafızasına.
10. **Kayıt:** her dosya `creative_register(profile_id, campaign_id, cycle_id, file_path, delivery_role, edit_plan_id, style_direction,
    music_bpm, ai_share, features={ortak sözlük eksenleri + taxonomy_version + competitive_role}, duration_s)`. Aynı anahtar/format/kart
    farklı içerikle üzerine yazılmaz; yeni revizyon açılır. Kullanılan varlıklar `asset_mark_used(profile_id, asset_id, creative_key, role)`
    (açılış karesi rolü dahil).
11. `stage_complete(profile_id, "S12", outputs=[{path: out/ teslim listesi md}, …], summary, campaign_id, cycle_id)` → S13.

## Çıktılar
`out/*.mp4|jpg` (adlandırılmış), `creatives` kayıtları (hash, rol, özellikler), plan yama zinciri, sahne önbelleği, teslim listesi
(`out/c<tur>-teslim-listesi.md`), devam notu.

## Kontroller
- Test reklamı sayısı ≤ tavan; yedekler ayrı; 9:16 + 4:5 her test reklamında var (1:1 yalnızca istendiyse).
- AI içeren her varyasyonun gerçek eşi var ya da eksikliği açıkça raporlandı.
- Export parametreleri doğru; adlar kurala uygun; `creative_register` hash'leri dosyalarla aynı.

## Kapı mesajı
Kapı yoktur (QC kapısı S13'te). Geçiş özeti: "N test reklamı (M dosya: 9:16/4:5), K yedek, S statik, C carousel hazır; AI'sız eşler: ….
Bağımsız kalite kontrole gönderiyorum."
