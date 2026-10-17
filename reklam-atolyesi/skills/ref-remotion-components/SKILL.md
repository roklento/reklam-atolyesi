---
name: ref-remotion-components
description: "reklam-atolyesi Remotion bileşen kütüphanesi — kompozisyonlar, plan katmanı → bileşen eşlemesi, bileşen prop'ları, geçiş/kamera/yazı presetleri, determinizm, yeni bileşen kuralı."
---

# ref-remotion-components — bileşen kütüphanesi (spec 5.12, 5.6, 5.19, 5.21)

Kütüphane bir **araç kutusudur**: hiçbir bileşen varsayılan olarak kurgu planına girmez; seçim stil kitabına ve efekt bütçesine göre
yapılır. Bütün demo/örnek prop'lar nötr yer tutucudur ("Marka A", "Örnek başlık"); içerik varsayılanı değildir.

## Proje ve kompozisyonlar
Şablon `PR/templates/remotion/` → kampanyaya `render.py init --project <k>/src` ile kopyalanır; bağımlılıklar `DD/.node/node_modules`
(Remotion 4.0.532, zod 4.5.4, three 0.178.0, react 19.1.0).
- `src/Root.tsx`: `Master-916` (1080×1920), `Master-45` (1080×1350), `Master-11` (1080×1080; isteğe bağlı), `Gallery`. Remotion
  kimliklerinde alt çizgi geçersizdir. Sabit kareler aynı kompozisyondan `--still <kare>`.
- `src/plan.ts` (zod; yetkili doğrulama Python `edit_plan_validate`), `src/style.ts` (planın hash'le bağlandığı stil kopyası),
  `src/beats.ts` (kilitli anlar, ≤ 3 kare yaslanma), `src/scenes/` (rol başına sahne), `src/components/`, `src/assets.ts` (`staticFile()`
  proxy/final ara dosya anahtarı).

## Plan katmanı → render
| Katman `type` | Ne olur |
|---|---|
| `video` | `source.kind=footage|ai_clip` → sahne ara dosyası `<OffthreadVideo>`; `camera.preset`: `static` · `kenburns_in` · `kenburns_out` · `handheld` · `rack_focus` (+ `zoom`) |
| `image` | `source.kind=still|ai_image` (fotoğraf/AI görsel) |
| `text` | `preset`: `text_reveal` (TextReveal) · `kinetic`/`kinetic_words` (KineticWords) · `soft_type` (SoftType) · `lower_third` (LowerThird); `anchor`: `safe_top` vb.; konum `style.layout[format].titleY` ve rol |
| `component` | `component: "<Ad>"`, `props: {…}` (zod şemasıyla doğrulanır); sarmalayıcılar (`KenBurns`, `FakeRackFocus`, `HandheldDrift`, `Spotlight`, `LightRays`, `ParticleSwirl`, `HeatShimmer`, `SafeZoneGuide`) altındaki katmanı sarar |
| `graphic` | düz grafik/renk alanı |
Sahne geçişi: `transition_out: {type, dur_s}`; `type`: `cut` · `crossfade` · `dipToColor` · `lightLeak` · `whipPan` · `maskReveal` ·
`matchZoom` · `slideBlur` · `filmBurn`. Efekt bütçesi: 15 sn'de en fazla 2 farklı geçiş türü (stil daraltabilir).

## Bileşenler (kategori · ad · başlıca prop'lar)
- **Yazı:** `TextReveal`, `KineticWords`, `SoftType` (ortak: `text`, `color`, `fontFamily`, `fontWeight`, `fontSize`, `y` 0–1, `align`) ·
  `LowerThird` (`title`, `subtitle`, `color`, `bg`, `accent`, `y`) · `PriceTag` (`price`, `currency`, `referencePrice`,
  `referencePriceVerified`, `label`, `locale` — sayı biçimi profilin dilinden/para biriminden, ör. `tr-TR`, `en-US`; fiyat yoksa kırmızı uyarı kutusu
  render eder; **çizili/referans fiyat yalnızca
  `referencePriceVerified=true`** ve fiyat geçmişi kanıtıyla) · `CaptionTrack` (`captions:[{text,start,end}]`, `fontSize`, `y`,
  `offsetS`; metin VO ile birebir).
- **Geçiş (bileşen olarak test):** `Crossfade`, `DipToColor`, `LightLeak`, `WhipPan` (hareket bulanıklıklı), `MaskReveal`, `MatchZoom`,
  `SlideBlur`, `FilmBurn` (`type`, `color`, `durationFrames`, `seed`).
- **Işık/atmosfer:** `LightSheen` (`angle`, `width`, `intensity`) · `SoftGlow` (`x`,`y`,`radius`,`color`,`pulse`) · `Bokeh` (`count`,`seed`) ·
  `Particles` (`count`,`seed`; tohumlu) · `GradeOverlay` (`grain` 0–1, `vignette` 0–1; nötr varsayılan 0) · `LensFlareSoft`.
  Sahne boyu süren atmosfer efekti varsayılan bütçede yoktur.
- **Kamera:** `KenBurns` (`fromScale`,`toScale`,`fromX`,`toX`,`fromY`,`toY`; 2× üstünde netlik düşer) · `Parallax25D` (`background`,
  `foreground` maske) · `FakeRackFocus` · `HandheldDrift` (çok hafif; `amplitude ≤ 1,5`).
- **Ürün:** `BehindSubjectText` (`text`, `background`, `cutout` maske) · `Spotlight` · `OutlineGlow` (`cutout`) · `StillTurn` (fotoğraftan
  hafif dönüş hissi, `degrees ≤ 14`, `sheen` varsayılan kapalı, AI yok).
- **Kanıt/kapanış:** `ReviewCard` (`reviewId` **zorunlu** ve `reviews` kaydıyla eşleşmeli, `quote` birebir, ad `name_display_mode`'a göre) ·
  `StarRating` (`rating` yalnızca kayıttaki gerçek puan; yoksa gösterilmez) · `EndCard` (`brand`, `cta`, `url`, `ink`, `bg`, logo) ·
  `CTAPulse` (`text`).
- **İmza anları (Three.js/GLSL):** `LightRays`, `ParticleSwirl`, `HeatShimmer` — **yalnızca reveal ve son kartta**; 15 sn'de en fazla 1.
- **Yardımcı (yalnızca önizleme):** `SafeZoneGuide` (`format`), `BeatMarker` (`beats`) — `ready` üretim planında kullanılamaz.

## Kurallar
- Her animasyon `useCurrentFrame()`'den türetilir; CSS geçişleri, zamanlayıcılar, `Math.random()`, `Date.now()` yok; rastgelelik tohumlu.
- Video katmanı `<OffthreadVideo>`; Remotion'a **ham 4K verilmez**: sahne ara dosyaları (`scripts/ingest/scenes.py`; proxy 1080 kısa
  kenar, final yaklaşma payını taşıyan en küçük çözünürlük).
- Hareket bulanıklığı `@remotion/motion-blur` ya da alt-kare ortalama.
- Formatlar ayrı kompozisyondur; sahneler paylaşılır; yazı/grafik format başına yeniden yerleşir; video formatın oranına göre kadrajlanır.
  Güvenli alan (5.19): 9:16 üst %14, alt %35, yanlar %6 boş (açıklama metni ya da AI içeren planda alt %40: `disclaimer.on` / `ai_share > 0`); 4:5 üst/alt ~250 px, yanlar ~100 px; 1:1 kenarlardan pay.
- Fontlar `@fontsource/<ad>` ile, **`latin` + `latin-ext`** CSS birlikte; nötr şablonda yalnızca `Inter`.
- Render: önizleme 0,5 ölçek (tek sayı → çift), final ölçek 1; işçi bütçesi `max(1, floor(CPU/2))`; sahne önbelleği (5.21).
- Lisans: Remotion lisansı kullanıcı/kuruluş ve ekip kapsamına göre belirlenir (`ref-legal-tr-meta` → Remotion).

## Yeni bileşen kuralı
Gereken efekt yoksa: `src/components/<kategori>.tsx` içinde zod şemalı, deterministik bileşen + `Entry` kaydı (`name`, `category`,
`version`, `schema`, nötr `demo`) → 3 sabit kare + 2 sn test (`render.py gallery --components <Ad>`) → öz denetim (kontak sayfası, ortası
siyah kare kontrolü dahil) → kullanıcı taslakta görür → onaylanırsa sürüm numarası ve test çıktısıyla **profil bileşen kütüphanesine**
(`DD/profiles/<slug>/components/<Ad>@<sürüm>.tsx` + test kareleri) eklenir ve sonraki kampanya projelerinin `src/components/`'ına
kopyalanır; onaylanmazsa kampanyaya özel kalır. Plugin klasörüne yazılmaz (durum bilgisi plugin klasörüne yazılmaz, 14.2); genel fayda
görülürse sistem hafızasına "plugin geliştirme notu" düşülür.

## Resmi belge (vendor kopyası yok; lisans doğrulanmadı)
- Render API: https://www.remotion.dev/docs/renderer/render-media , https://www.remotion.dev/docs/renderer/render-still
- `OffthreadVideo`: https://www.remotion.dev/docs/offthreadvideo · `staticFile`: https://www.remotion.dev/docs/staticfile
- Zod şemalı prop'lar: https://www.remotion.dev/docs/schemas · Hareket bulanıklığı: https://www.remotion.dev/docs/motion-blur
- Three.js: https://www.remotion.dev/docs/three · Fontlar: https://www.remotion.dev/docs/fonts
- Lisans: https://www.remotion.dev/docs/license/faq
