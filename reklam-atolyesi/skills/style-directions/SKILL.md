---
name: style-directions
description: "reklam-atolyesi S08 stil yönleri — çekimden 2–3 farklı yön (renk/LUT, tipografi, hareket, ses imzası, efekt bütçesi), 3 kare + 5 sn test, öz denetim, sürümlü stil kitabı. Kapılı."
---

# style-directions — S08 · Stil yönleri ve stil kitabı (spec 5.6, 5.2, 5.15, 4.2)

## Amaç
Stili masa başında değil eldeki çekime bakarak seçmek: 2–3 **belirgin farklı** yön → önizleme → kullanıcı seçer ya da karıştırır →
sürümlü `style.json`. Profilin **onaylı stil kitabı varsa** yeni yön üretilmez: yeni malzemenin uyumu kontrol edilir ve kapıda yalnızca
"aynı stille devam / stili yenile" sorulur. Yöntem `art-director` ajanınındır.

## Ön koşul
S07 tamam (malzeme haritası). Profil `style.json` iskeleti (S00a, logodan renkler) var.

## Girdiler ve bağlam paketi
`memory_context(profile_id, "S08", campaign_id, cycle_id)`: güncel stil, stil tercihleri, marka, stil prosedürleri, referans tahtası.
`DD/profiles/<slug>/style.json`, `styles/v*.json`, `brand/` (logo, belgeler), `analysis/material-map.json`, `c<tur>-referans-tahtasi.md`.

## Kullanılan hazır skill'ler ve OVERRIDES
- **xilo-opus-video**: `PR/vendor-skills/xilo-opus-video/OVERRIDES.md` → `SKILL.md` `第 2 步` ve `第 3 步` (önce 3 yön + önizleme,
  onaydan sonra kare kare render). Canvas/HTML motoru, AI karakter ve "referans görünüşünü kopyalama" uygulanmaz.
- **motion-design**: `PR/vendor-skills/motion-design/OVERRIDES.md` → `SKILL.md` `## 8. Critique loop` (kontak sayfasıyla doğrulama).
- **ai-product-video**: `PR/vendor-skills/ai-product-video/OVERRIDES.md` → `references/aesthetic-rules.md` (öz denetime ek ölçüt) ve
  `references/shots/{typography,transition,camera}/*.md` (hareket dili; kod kopyalanmaz).
- **remotion (resmi bilgi)**: vendor kopyası yoktur (lisans doğrulanmadı); `ref-remotion-components` ve `ref-vendor-map`'teki resmi
  belge bölümleri.

## Adımlar
1. `stage_start(profile_id, "S08", campaign_id, cycle_id)`. Kampanya Remotion projesi yoksa:
   `PY PR/scripts/render/render.py init --project <kampanya>/src` (şablon kopyalanır; özelleştirilmiş dosyalar korunur).
2. **Onaylı stil kitabı var mı?** (`styles/v<N>.json` onaylı ve `style.json` ona eşit) → yeni malzemeden 3 sabit kare bu stille render
   edilir, uyum kontrol edilir; kapıda "aynı stille devam / stili yenile". "Yenile" seçilirse aşağıdaki akış.
3. **Sahne taslağı:** S03 konseptleri + S07 malzeme haritasından kurgu planı taslağı (`purpose="style_preview"`, `status="draft"`,
   `audio.mode="none"` — bu bir sahne ses onayı değildir; ücretli ses üretilmez) → `edit_plan_save(profile_id, campaign_id, cycle_id, plan)`.
4. **Yönler (2–3):** her yön `palette`, `fonts`, `grade` (LUT, gren, vinyet), `motion` (easing, süreler, stagger), `effects` (efekt
   bütçesi), `sound` (reveal sesi, geçiş sesi, müzik türü/tempo aralığı), `layout` (format başına yazı konumları) tanımlar. Yönler
   birbirinden belirgin farklıdır; **en az biri markanın mevcut görsel dilinden** (logo, renkler, belgeler, referans tahtası) türetilir;
   hiçbiri şablonun nötr varsayılanı değildir. Ham/UGC türünde efekt 0 olabilir; genişletme gerekçe ister.
   Varsayılan efekt bütçesi: 15 sn'de en fazla 1 imza anı, en fazla 2 farklı geçiş türü, sahne boyu süren atmosfer yok.
   - LUT: `PY PR/scripts/render/grade_lut.py make --out DD/profiles/<slug>/styles/luts/<yön>.cube --contrast … --temperature …
     --saturation … --lift … --gain …` (parametreler yön kararından; varsayılanlar nötr).
   - Klipler arası eşitleme (1.7.0): `grade.match` (varsayılan `true`) farklı ışıkta çekilmiş kliplerin pozlamasını ve beyaz dengesini
     LUT'tan önce referans klibe çeker (`grade.match_ref`: varlık anahtarı; yoksa pozlaması en iyi klip). Sınır ±0,5 stop ve kanal
     başına ±%12; aşan klip düzeltilmez, "yeniden çekim adayı" olur. Renk doğruluğu ürünün kendisi olan kategorilerde (giyim, boya,
     kozmetik, saç boyası, mobilya kumaşı) yön `grade.match: false` yazar: ürün rengi ekranda değişmemeli.
   - Font: yönün fontu `@fontsource/<ad>` ile `DD/.node` altına kurulur (`npm install @fontsource/<ad>` — çalışma dizini `DD/.node`);
     **hem `latin` hem `latin-ext`** CSS'i içe aktarılır (yalnızca latin-ext ile temel harfler yedek fonta düşer); içe aktarma kampanya
     projesinin `src/` dosyasındadır ve kullanılan her ağırlık için ayrıdır. Doğrulama: `PY PR/scripts/qc/font_coverage.py --plan <plan>
     --style <yön.json> --project <src> --data-dir DD` (çıkış 0 değilse eksik karakterler/ağırlıklar düzeltilmeden önizleme yapılmaz;
     öz denetim de aynı kontrolü yapar). Font lisansı dosya
     bazında kaydedilir.
5. **Önizleme:** her yön için gerçek çekimden **3 sabit kare** + **5 sn hareket testi**:
   `PY PR/scripts/render/render.py plan --data-dir DD --project <src> --plan <plan_yön.json> --style <yön.json> --out
   analysis/style/<yön>_still_<n>.png --still <kare>` ve aynı komut `--out analysis/style/<yön>_test.mp4 --quality preview` (5 sn plan).
   Eşitleme açıksa ve bir klip düzeltildiyse önce|sonra kareleri: `PY PR/scripts/analyze/color_match.py compare --report
   footage/scenes/color_match.json --out-dir analysis/style/color_match` (sahne ara dosyaları `scenes.py` ile üretildikten sonra).
6. **Öz denetim (5.15)** her render'dan sonra, kullanıcıya göstermeden önce:
   `PY PR/scripts/render/self_review.py --video <test.mp4> --plan <plan> --out-dir analysis/review_<yön> --style <yön.json>
   --project <src> --data-dir DD --round 1` → kontak sayfası, kareler ve yazı şeritleri (`text_bands_<n>.jpg`, küçültmeden) **görülür**;
   Türkçe karakter (font glif kapsamı bulgusu dahil), güvenli alan, efekt bütçesi, siyah kare/donma, slayt gösterisi riski.
   S03'te referans video ölçüldüyse (`references/<ad>/reference.json`) çekim süresi ve hareket profili `motion` yönünü besler; renk,
   yazı ve kurgu referanstan birebir alınmaz. Sorun varsa plan düzeltilir,
   yeniden render (en fazla 3 tur); kalan sorun kullanıcıya açıkça söylenir. Tekrarlayan hata → `memory_add(layer="procedural")`.
7. **Sunum:** yönler referans tahtasıyla yan yana gösterilir. "İlk saniye kaydırmayı durdurur mu, marka gibi duruyor mu" yargısını
   kullanıcı verir; Claude yalnızca gözlemini söyler. Kullanıcı seçer, karıştırır ya da yeniden ister.
8. **Kayıt:** seçilen/karışık stil `DD/profiles/<slug>/styles/v<N+1>.json` olarak **değişmez kopya** (atomik) + `style.json` güncel profil
   stili; planlar kopyanın yolunu ve `style_snapshot_sha256`'sını taşır. Eski planlar ve yayınlanmış kreatifler değişmez.
   Stil tercihleri `memory_add(layer="preference", kind="style", evidence_id=<karar>)`.
9. `stage_complete(profile_id, "S08", outputs=[{path: styles/v<N+1>.json}, {path: önizleme kontak sayfası}], summary, campaign_id, cycle_id)`
   → `awaiting_gate`.

## Çıktılar
Stil yönleri (JSON), LUT'lar, önizleme kareleri ve testleri, renk eşitleme önce|sonra kareleri, öz denetim kayıtları, `styles/v<N>.json` + `style.json`, `style_preview`
planları, devam notu.

## Kontroller
- Yönler belirgin farklı; en az biri markadan türetilmiş; nötr şablon hiçbir yönün başlangıç noktası değil.
- Her yön için 3 sabit kare + 5 sn test öz denetimden geçti; efekt bütçesi alanları dolu.
- Önizleme ücretli ses üretmedi; `audio.mode=none`.
- `color_match.json` okundu: düzeltilen klipler önce|sonra kareleriyle kapıda gösterildi; yeniden çekim adayları adıyla söylendi.

## Kapı mesajı
"Stil yönleri: A — … (renk/tipografi/hareket/ses), B — …, C — …. Öz denetimde kalan not: …. Hangisiyle devam edelim, ya da hangilerini
karıştıralım?" Klip eşitlemesi yapıldıysa: "Farklı ışıktaki <n> klibi referans klibe eşitledim (önce|sonra kareleri ekte);
<klip> farkı çok büyük olduğu için düzeltilmedi, yeniden çekim adayı." (onaylı stil varsa: "Aynı stille devam mı, stili yenileyelim mi?") → seçim açık ifadeyle `gate_approve(...)`.
