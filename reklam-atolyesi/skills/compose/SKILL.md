---
name: compose
description: "reklam-atolyesi S10 kurgu — kurgu planını kesin zamanlama, katman ve geçişlerle tamamlar, vuruşa yaslar, sahne ara dosyalarından Remotion render eder ve görsel öz denetimden geçirir."
---

# compose — S10 · Kurgu (spec 5.2, 5.12, 5.15, 5.21)

## Amaç
S08–S09 planını kesin zamanlama, katman, geçiş ve varlıklarla tamamlamak ve **öz denetimden geçmiş ilk taslağı** üretmek. Plan dışında
render yapılmaz; geçersiz plan render edilmez. Kurgu `editor` ajanının, yeni bileşen tasarımı `art-director`'ın yöntemiyle.

## Ön koşul
S09 kapısı geçilmiş: her sahnede kullanıcı ses kararı, varlıklar bağlı, stil kopyası (`styles/v<N>.json`) ve hash'i belli.

## Girdiler ve bağlam paketi
`memory_context(profile_id, "S10", campaign_id, cycle_id)`: güncel stil, kurgu prosedürleri, kurgu tercihleri, güncel planlar.
`edit_plan_get`, `analysis/material-map.json`, `audio/music/*.beats.json`, `audio/vo/*.words.json`, `ref-remotion-components`.

## Kullanılan hazır skill'ler ve OVERRIDES
- Remotion: yalnızca `ref-remotion-components` ve `ref-vendor-map` → "Remotion — resmi belge yolu". Makinede genel `remotion-*`
  skill'leri kurulu olsa bile okunmaz (sürüm ve kurallar plugin'in pinli sürümüyle uyuşmayabilir).
- **launch-video**: `PR/vendor-skills/launch-video/OVERRIDES.md` → `SKILL.md`, `references/launch-structure.md` (hook → tease → reveal →
  montaj → son kart yayı, "drop'ta reveal" vuruş kilidi; iart.ai ve 16:9 varsayımı uygulanmaz).
- **promo-video**: `PR/vendor-skills/promo-video/OVERRIDES.md` → `SKILL.md` `## Beats & music` (beat-lock) ve `## Hard-won gotchas`
  (render doğrulama, Remotion tuzakları). Web sitesi tarama akışı uygulanmaz.
- **ai-product-video**: `PR/vendor-skills/ai-product-video/OVERRIDES.md` → `references/shots/{camera,transition,typography,rhythm,
  opening,outro}/*.md` (hareket tarifleri; parametreler uyarlanır, kod kopyalanmaz).
- **motion-design**: `PR/vendor-skills/motion-design/OVERRIDES.md` → `SKILL.md` `## 6. Gotchas` (alt-kare hareket bulanıklığı).
- **remotion (resmi bilgi)**: vendor kopyası yok; `ref-remotion-components` + `ref-vendor-map`'teki resmi belge bölümleri.

## Adımlar
1. `stage_start(profile_id, "S10", campaign_id, cycle_id)`. Proje yoksa `PY PR/scripts/render/render.py init --project <k>/src`.
2. **Planı tamamla** (`purpose="production"`; `status` önce `draft`):
   - Sahne rolleri sabit sözlükten: `hook · context · reveal · product · process · demo · proof · offer · endcard` (açılar rol değildir).
   - Her katmanın kaynağı: `footage` (malzeme haritasındaki klip + saniye aralığı; sabit/ham seçimi) · `ai_clip` · `ai_image` · `still` ·
     `graphic`. **Rakip analizi klasörleri** (`profiles/<p>/competitors/`, `campaigns/<k>/competitive/`) hiçbir katmanın kaynağı olamaz.
   - Kesim ve vuruş: kesimler önce aksiyona göre (hareket üstünde, bakış/jest tamamlanınca). Aksiyon kesimi en yakın vuruşa ≤ 3 kare
     ise vuruşa yaslanır; değilse aksiyonda kalır. `beat_lock` işaretli anlar (reveal, hook'tan çıkış, son kart girişi) vuruşa kilitlenir.
   - Bileşenler `ref-remotion-components` kütüphanesinden, stil kitabına ve **efekt bütçesine** göre (imza anı yalnızca reveal ve son
     kartta). Hiçbir bileşen varsayılan değildir.
   - Altyazı (5.14): VO ya da tutulan konuşma varsa `captions.on=true`, kelime zamanlarından; metin VO ile birebir.
   - `provenance.ai_share` ve `ai_layers` katmanlardan hesaplanır.
3. **Doğrula:** `edit_plan_save(...)` → `edit_plan_validate(profile_id, campaign_id, plan_id, beats=<beats.json yolu>)` (şema, zamanlar,
   kamerada konuşan sahne ↔ `original*`, efekt bütçesi, kilitli anlar, rakip kaynağı reddi). Yerel kontrol için aynı kod:
   `PY PR/scripts/compose/validate_plan.py <plan.json> --style <style> --beats <beats.json>`.
4. **Sahne ara dosyaları (proxy):** `PY PR/scripts/ingest/scenes.py --plan <plan> --assets <asset_files.json> --out-dir footage/scenes
   --quality proxy --style <style> --map-out footage/scenes/map_proxy.json` (aralık kesimi + `lut3d` + gerekirse sabit kopya; ham 4K
   Remotion'a verilmez; çekim sesi kullanılan sahnelerde WAV parçaları).
5. **Taslak render (önizleme 0,5 ölçek):** `PY PR/scripts/render/render.py plan --data-dir DD --project <k>/src --plan <plan> --out
   out/drafts/<ad>_preview.mp4 --style <style> --scene-map footage/scenes/map_proxy.json --captions <words.json> --quality preview`
   (sahne önbelleği değişmeyen sahneyi yeniden render etmez; uzun render arka planda, süre tahminiyle).
6. **Öz denetim (5.15):** `PY PR/scripts/render/self_review.py --video <preview.mp4> --plan <plan> --out-dir analysis/review_<ad>
   --style <style> --beats <beats.json> --round <n>` → kontak sayfası ve sahne kareleri **görülür**; sayısal kontroller (yazı süresi ve
   güvenli alan, `beat_lock` ↔ vuruş, efekt bütçesi, ses seviyesi, siyah kare/donma). Sorun varsa plan düzeltilir
   (`edit_plan_patch`), yeniden render; **en fazla 3 tur**. Kalan sorun kullanıcıya açıkça söylenir. Akıcılık, kısa ürün bozulması ve
   ses için tam oynatma gerekir; araç yapamıyorsa S11 kapısında kullanıcı kontrolü beklenir.
7. **Yeni bileşen kuralı:** gereken efekt kütüphanede yoksa yazılır (deterministik, `useCurrentFrame()`'den türetilmiş, zod parametreli,
   `Math.random`/`Date.now` yok) → 3 sabit kare + 2 sn test → öz denetim → kullanıcı taslak içinde görür; onaylanırsa sürüm numarası ve
   testiyle kütüphaneye; onaylanmazsa kampanyaya özel kalır.
8. Bulgular ve tekrarlayan hatalar `memory_add(layer="procedural", kind="compose")`. Render süresi sistem hafızasına
   (`memory_add(profile_id=None, kind="render_time", content=…)`).
9. Plan `status="ready"` (bütün varlıklar, zamanlar, stil kopyası, sahne ses kararları) olarak yeni sürümle kaydedilir.
10. `stage_complete(profile_id, "S10", outputs=[{path: preview.mp4}, {path: plan.json}, {path: review kontak sayfası}], summary, campaign_id,
    cycle_id)` → S11 (kapı yok; taslak kapısı S11'de).

## Çıktılar
`edit_plans` sürümleri (`ready` üretim planı), `footage/scenes/` ara dosyaları, `out/drafts/*_preview.mp4`, `analysis/review_*`, sahne
önbelleği kayıtları (`scene_cache_*`), devam notu (render başında ve sonunda).

## Kontroller
- Plan doğrulamadan geçti; rakip kaynağı yok; efekt bütçesi aşılmadı; kilitli anlar vuruşta (≤ 3 kare).
- Render deterministik (tohumlu); final değil önizleme; öz denetim yapıldı ve tur sayısı kayıtlı.
- S10 yeni sahne eklediyse ya da onaylı ses seçimini değiştirdiyse yalnızca etkilenen sahnenin ses kararı yeniden soruldu; yeni maliyet ayrıca onaylandı.

## Kapı mesajı
Kapı yoktur (taslak kapısı S11'de). Geçiş özeti: "İlk taslak hazır (önizleme): N sahne, M sn; öz denetim <k> tur, kalan not: …. Sesi
bitirip taslağı birlikte izleyelim."
