---
name: ref-remotion-components
description: "reklam-atolyesi Remotion bileşen kütüphanesi — kompozisyonlar, plan katmanı → bileşen eşlemesi, bileşen prop'ları, geçiş/kamera/yazı presetleri, determinizm, yeni bileşen kuralı."
---

# ref-remotion-components — bileşen kütüphanesi (spec 5.12, 5.6, 5.19, 5.21)

Kütüphane bir **araç kutusudur**: hiçbir bileşen varsayılan olarak kurgu planına girmez; seçim stil kitabına ve efekt bütçesine göre
yapılır. Bütün demo/örnek prop'lar nötr yer tutucudur ("Marka A", "Örnek başlık"); içerik varsayılanı değildir.

## Proje ve kompozisyonlar
Şablon `PR/templates/remotion/` → kampanyaya `render.py init --project <k>/src` ile kopyalanır (kopya kampanyayla sabit kalır; plugin
güncellemesi eski projeyi değiştirmez). Eski projeyi güncel şablona getirmek: `render.py upgrade --project <k>/src [--dry-run]`
(2.0.0; yalnızca yayımlanmış bir şablon sürümüyle bayt bayt aynı dosyalar güncellenir, elle değiştirilenler `kept_customized`
listesinde kalır; `templates/remotion/template_history.json`). Plan projenin çizemediği bir özelliği kullanıyorsa render başlamadan
durur (gri "bilinmeyen bileşen" paneli finalde görünmez). Sahne önbelleği anahtarı projenin kendi kod dosyalarını içerir. Bağımlılıklar `DD/.node/node_modules`
(Remotion 4.0.532, zod 4.5.4, three 0.178.0, react 19.1.0).
- `src/Root.tsx`: `Master-916` (1080×1920), `Master-45` (1080×1350), `Master-11` (1080×1080; isteğe bağlı), `Gallery`. Remotion
  kimliklerinde alt çizgi geçersizdir. Sabit kareler aynı kompozisyondan `--still <kare>`.
- `src/plan.ts` (zod; yetkili doğrulama Python `edit_plan_validate`), `src/style.ts` (planın hash'le bağlandığı stil kopyası),
  `src/beats.ts` (kilitli anlar, ≤ 3 kare yaslanma), `src/scenes/` (rol başına sahne), `src/components/`, `src/assets.ts` (`staticFile()`
  proxy/final ara dosya anahtarı).

## Plan katmanı → render
| Katman `type` | Ne olur |
|---|---|
| `video` | `source.kind=footage|ai_clip` → sahne ara dosyası `<OffthreadVideo>`; `camera.preset`: `static` · `kenburns_in` · `kenburns_out` · `handheld` · `rack_focus` · `punch_in` (sabit yakınlaştırma 1,0–1,2; konuşmalı kurguda kesik gizleme) (+ `zoom`; 1.8.0: `focus: {x, y}` 0–1 kenburns'ü o noktaya yöneltir, `settle_s` hareketi kesimden bu kadar önce durdurur) |
| `image` | `source.kind=still|ai_image` (fotoğraf/AI görsel) |
| `text` | `preset`: `text_reveal` (TextReveal) · `kinetic`/`kinetic_words` (KineticWords) · `soft_type` (SoftType) · `lower_third` (LowerThird); `anchor`: `safe_top` · `safe_bottom` · `center`; konum `style.layout[format].titleY`, rol ve format (`src/layout.json`; `props.y` önceliklidir). Fiyat etiketi, buton, alt bant ve altyazının format başına varsayılan yeri de bu tablodadır; 2 satırlık blok güvenli alanda kalır (9:16'da açıklamalı reklamın alt %40'ı dahil). `props.y` verirken bloğun alt kenarı da güvenli alanda kalmalı (1.5.2) |
| `component` | `component: "<Ad>"`, `props: {…}` (zod şemasıyla doğrulanır); sarmalayıcılar (`KenBurns`, `FakeRackFocus`, `HandheldDrift`, `Spotlight`, `LightRays`, `ParticleSwirl`, `HeatShimmer`, `SafeZoneGuide`, `PictureInPicture`) altındaki katmanı sarar. **Kaynak alan prop'lar (1.8.0):** `BeforeAfter.before/after`, `PictureInPicture.inset`, `PhoneScreen.screen` kaynak nesnesidir — `{kind: "footage", asset, in_s, out_s}` (ya da görsel için `{kind: "still", path}`); `scenes.py` ara dosyayı `<katman>.<prop>` anahtarıyla üretir. Konuşan kişinin kaynağına `speaking_person: true` ve sahne sesi ondan alınacaksa `audio: true` yazılır. Bu kaynaklara renk eşitleme uygulanmaz |
| `graphic` | düz grafik/renk alanı |
Sahne geçişi: `transition_out: {type, dur_s}`; `type`: `cut` · `crossfade` · `dipToColor` · `lightLeak` · `whipPan` · `maskReveal` ·
`matchZoom` · `slideBlur` · `filmBurn`. Efekt bütçesi: 15 sn'de en fazla 2 farklı geçiş türü (stil daraltabilir).

## Bileşenler (kategori · ad · başlıca prop'lar)
- **Yazı:** `TextReveal`, `KineticWords`, `SoftType` (ortak: `text`, `color`, `fontFamily`, `fontWeight`, `fontSize`, `minFontSize`, `maxLines`, `y` 0–1, `align`) ·
  `LowerThird` (`title`, `subtitle`, `color`, `bg`, `accent`, `y`, `minFontSize`) · `PriceTag` (`price`, `currency`, `referencePrice`,
  `referencePriceVerified`, `label`, `locale` — sayı biçimi profilin dilinden/para biriminden, ör. `tr-TR`, `en-US`; fiyat yoksa kırmızı uyarı kutusu
  render eder; **çizili/referans fiyat yalnızca
  `referencePriceVerified=true`** ve fiyat geçmişi kanıtıyla) · `CaptionTrack` (`captions:[{text,start,end,words?,emph?}]`, `fontSize`, `y`,
  `offsetS`, `preset`: `plain` · `keyword` (parçada en fazla bir vurgu sözcüğü, vurgu rengi + hafif büyütme) · `keyword_upper` (aynı +
  Türkçe büyük harf, i → İ) · `karaoke` (o an söylenen sözcük vurgulu), `accent` (stil `captions.accent`, yoksa `palette.accent`; görece parlaklığı < 0,3 olan koyu renk okunur sarıya düşer); metin
  VO ile birebir; planda `captions.preset`; 1.5.0) · **`TextMark`** (1.8.0; `text` içinde `mark` sözcüğü/öbeği el çizimi gibi
  işaretlenir: `mode` circle|underline|highlight|box, `markColor`, `seed`; `@remotion/rough-notation` 4.0.532, MIT; eşleşme Türkçe katlamalı
  — "İYİ" ile "iyi"; bulunamazsa kırmızı VURGU BULUNAMADI; efekt bütçesi 15 sn'de en fazla 2).
- **Geçiş (bileşen olarak test):** `Crossfade`, `DipToColor`, `LightLeak`, `WhipPan` (hareket bulanıklıklı), `MaskReveal`, `MatchZoom`,
  `SlideBlur`, `FilmBurn` (`type`, `color`, `durationFrames`, `seed`).
- **Işık/atmosfer:** `LightSheen` (`angle`, `width`, `intensity`) · `SoftGlow` (`x`,`y`,`radius`,`color`,`pulse`) · `Bokeh` (`count`,`seed`) ·
  `Particles` (`count`,`seed`; tohumlu) · `GradeOverlay` (`grain` 0–1, `vignette` 0–1; nötr varsayılan 0) · `LensFlareSoft`.
  Sahne boyu süren atmosfer efekti varsayılan bütçede yoktur.
- **Kamera:** `KenBurns` (`fromScale`,`toScale`,`fromX`,`toX`,`fromY`,`toY`; 2× üstünde netlik düşer; 1.1.0: `focus {x,y}`, `settleFrames`) · `Parallax25D` (`background`,
  `foreground` maske) · `FakeRackFocus` · `HandheldDrift` (çok hafif; `amplitude ≤ 1,5`).
- **Ürün:** `BehindSubjectText` (`text`, `background`, `cutout` maske) · `Spotlight` · `OutlineGlow` (`cutout`) · `StillTurn` (fotoğraftan
  hafif dönüş hissi, `degrees ≤ 14`, `sheen` varsayılan kapalı, AI yok) · **`PictureInPicture`** (1.8.0, sarmalayıcı: alttaki çekim arka
  plan, `inset` konuşan kişi köşede; `shape` circle|rounded, `corner`, `size` 0,18–0,45; köşe kutusu `layout.json pip_box`'tan güvenli
  alanda, `checks.py safe` yazı/altyazıyla çakışmayı denetler; konuşan kişinin izni her zamanki gibi) · **`PhoneScreen`** (1.8.0: sade
  telefon çerçevesi içinde ekran kaydı/görsel; `screen`, `crop {top,bottom,left,right}` kaynak oranı; **`personalData`** `none` ya da
  `blurred` + `blurRegions [{x,y,w,h}]` — kayıtta başka kişinin adı/numarası/fotoğrafı var mı kapıda sorulur; sorulmadıysa hazır plan
  reddedilir ve render'da kırmızı KİŞİSEL VERİ KONTROLÜ YOK çizilir).
- **Kanıt/kapanış:** `ReviewCard` (`reviewId` **zorunlu** ve `reviews` kaydıyla eşleşmeli, `quote` birebir, ad `name_display_mode`'a göre) ·
  `StarRating` (`rating` yalnızca kayıttaki gerçek puan; yoksa gösterilmez) · `EndCard` (`brand`, `cta`, `url`, `ink`, `bg`, logo) ·
  `CTAPulse` (`text`) · **`BeforeAfter`** (1.8.0; `mode` wipe|split|cut, `orientation`, `labelBefore`/`labelAfter` "Önce"/"Sonra",
  `before`/`after` **gerçek çekim**; `category` general|cosmetic|weight|health_claim|skin_whitening zorunlu — §8d; yalnızca konseptte
  `proof=before_after` seçiliyse; sağlık hizmeti sektöründe hiç kullanılmaz; cilt beyazlatma reddedilir, kozmetik/kilo 18+ notu) ·
  **`NumberRoll`** (1.8.0; sayaç ya da `roll` hane dönmesi; `value` ya fiyat — `kind: "price"` + `currency` — ya da kanıtlı iddia —
  `kind: "claim"` + `claimIndex` (`products.provable_claims_json` sırası) ya da `claimRef` (iddianın `code`u; belge isteyen iddia doğrulanmış olmalı); ikisi de değilse plan
  reddedilir, render'da kırmızı SAYI KANITI/FİYAT YOK; biçim `Intl.NumberFormat(locale)`, yer son değere göre ayrılır).
- **İmza anları (Three.js/GLSL):** `LightRays`, `ParticleSwirl`, `HeatShimmer` — **yalnızca reveal ve son kartta**; 15 sn'de en fazla 1.
- **Yardımcı (yalnızca önizleme):** `SafeZoneGuide` (`format`), `BeatMarker` (`beats`) — `ready` üretim planında kullanılamaz.

## Kurallar
- Her animasyon `useCurrentFrame()`'den türetilir; CSS geçişleri, zamanlayıcılar, `Math.random()`, `Date.now()` yok; rastgelelik tohumlu.
- Video katmanı `<OffthreadVideo>`; Remotion'a **ham 4K verilmez**: sahne ara dosyaları (`scripts/ingest/scenes.py`; proxy 1080 kısa
  kenar, final yaklaşma payını taşıyan en küçük çözünürlük).
- Hareket bulanıklığı `@remotion/motion-blur` ya da alt-kare ortalama.
- **Yazı sığdırma (1.6.0, `components/fit.tsx`):** TextReveal, KineticWords, SoftType, LowerThird, PriceTag etiketi, CTAPulse, EndCard ve
  BehindSubjectText satırlarını tarayıcıda gerçek fontla ölçer (`@remotion/layout-utils` measureText); yazı kutuya ve `maxLines`'a sığana dek
  `fontSize`'dan `minFontSize`'a küçülür, büyütülmez. Sığmazsa kırmızı **YAZI SIĞMIYOR** çerçevesi çizilir ve `<mp4>.layout.json` kaydı
  `fits:false` olur; `checks.py safe --layout` bunu sorun sayar. Çözüm metni kısaltmak ya da bileşeni değiştirmektir; `minFontSize`'ı
  okunmayacak kadar düşürmek çözüm değildir. Yeni yazı bileşeni `useFit` ile yazılır.
- Formatlar ayrı kompozisyondur; sahneler paylaşılır; yazı/grafik format başına yeniden yerleşir; video formatın oranına göre kadrajlanır.
  Güvenli alan (5.19): 9:16 üst %14, alt %35, yanlar %6 boş (açıklama metni ya da AI içeren planda alt %40: `disclaimer.on` / `ai_share > 0`); 4:5 üst/alt ~250 px, yanlar ~100 px; 1:1 kenarlardan pay.
- Fontlar `@fontsource/<ad>` ile, **`latin` + `latin-ext`** CSS birlikte; nötr şablonda yalnızca `Inter`. Render, stilin display/body/brand
  fontları ve plandaki `fontFamily`'ler yüklenene kadar bekler (`useFontsReady(fontFamiliesOf(style, plan))`, 1.5.1); karakter kapsamı
  `scripts/qc/font_coverage.py` ile (öz denetim ve S13 bunu çalıştırır).
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
