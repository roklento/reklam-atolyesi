---
name: sound
description: "reklam-atolyesi S11 ses — sahne ses kararlarını uygular, vuruş haritası, temizlik, ducking, -14 LUFS/≤-1 dBTP miks, telefon testi, altyazı; taslağı kullanıcıyla izletir. Kapılı (taslak)."
---

# sound — S11 · Ses miksi ve taslak (spec 5.13, 5.14, 5.15)

## Amaç
S09'daki sahne ses kararlarını uygulamak, miksi teslim seviyesine getirmek ve **taslak kapısında** kullanıcıyla birlikte izlemek.
Ses tasarımı `sound-designer` yöntemiyle; ses imzası her konseptte aynı.

## Ön koşul
S10 tamam: `ready` üretim planı ve öz denetimden geçmiş önizleme.

## Girdiler ve bağlam paketi
`memory_context(profile_id, "S11", campaign_id, cycle_id)`: ses prosedürleri, ses tercihleri, güncel planlar. Plan (`edit_plan_get`),
`footage/scenes/map_*.json` (sahne ses parçaları), `audio/{vo,user_vo,music,sfx}/`, `beats.json`, `*.words.json`, stil `sound` alanı.

## Kullanılan hazır skill'ler ve OVERRIDES
- **voice-isolator**: `PR/vendor-skills/voice-isolator/OVERRIDES.md` → `SKILL.md` (yalnızca `afftdn` yetmezse; ücretli, `materials`
  skill'indeki protokolle).
- **ai-product-video**: `PR/vendor-skills/ai-product-video/OVERRIDES.md` → `references/sound-design.md` (riser → impact → sparkle
  cümlesi; riser kodla sentezlenir, silinen dosyaların karşılığı OVERRIDES'ta), efekt arşivi (yalnızca kaynağı kayıtlı dosyalar).
- **ffmpeg**: `PR/vendor-skills/ffmpeg/OVERRIDES.md` → `SKILL.md` (yöntem; loudness ve export kuralları plugin'indir).

## Adımlar
1. `stage_start(profile_id, "S11", campaign_id, cycle_id)`.
2. **Vuruş haritası** (yoksa): `PY PR/scripts/audio/beats.py --audio audio/music/<seçilen>.wav --out audio/beats.json`.
3. **Sahne sesi uygulaması:** `generated` ve `none` sahnelerde çekim sesi kaldırılır; `original_clean` önce ücretsiz `afftdn`
   (`PY PR/scripts/audio/loudness.py clean --in … --out …`), yetmezse voice-isolator (ücretli protokol: tahmin → kayıt → açık onay).
   Kullanıcının seslendirmesi ve tutulan konuşma için gürültü azaltma + yüksek geçiren filtre.
4. **Yeni efekt ihtiyacı** (S10 yeni `audio_cues` eklediyse; yoğunluk kuralı: 1 saniyede ≤ 2, aynı efekt 2 sn içinde tekrar yok — 1.5.0):
   önce ses kütüphanesi (`sfx_library.py`; profil kütüphanesi → CC0 çekirdek `vendor-skills/sfx-cc0/` (Kenney: arayüz, dijital,
   darbe/adım sesleri, kısa müzik vuruşları) → Earshot bankası `vendor-skills/sfx-earshot/` (2.6.0; kodla üretilmiş 236 temiz ses: whoosh,
   riser, downlifter, logo sting, sub drop, glitch, klavye, bildirim); Türkçe sorgu da olur: "tık", "darbe cam", "onay",
   "logo", "iniş") ve kodla sentez (`sfx_synth.py`). 2.10.14'ten beri pakette Mixkit sesi yoktur (lisansı yeniden dağıtıma izin
   vermiyor); alkış, kalp atışı gibi organik ses kütüphanede yoksa profil kütüphanesinden ya da ElevenLabs'ten gelir; Earshot denetiminde uyarılı 16 ses yalnızca `--include-flagged` ile ve dinlenerek;
   ElevenLabs gerekiyorsa fiyat ve onay **S11 içinde** alınır (S09 kapısı yeniden açılmaz).
   **Aday anlar (2.7.0):** önizlemeden ya da ham çekimden `PY PR/scripts/analyze/sfx_moments.py --video <önizleme.mp4> --plan <plan.json>
   --frames-dir analysis/sfx-anlar --out analysis/sfx_moments.json` → kesme, ani hareket, hareketin başlaması ve durması (ürün masaya
   kondu, kapak oturdu); `uncovered` listesindeki adayların karelerine bakılır, yalnız görüntüye gerçekten uyanlar cue olur (yoğunluk
   kuralı geçerli). Cue alanları: `at_s` (görüntüdeki an), isteğe bağlı `role` (impact, whoosh, riser, logo, click, pop…; yoksa dosya
   adından), `anchor` (`auto` varsayılan: darbe/tık gövdesiyle, riser/whoosh/logo doruğuyla, müzik/ortam başıyla kareye oturur;
   `start` 2.6 davranışı), `level` (`role` varsayılan: türün tepe hedefi; `file` dosyanın kendi seviyesi), `gain_db` (ince ayar).
5. **Miks:** `PY PR/scripts/audio/mix.py --plan <plan.json> --scene-audio footage/scenes/map_final.json (ya da map_proxy.json)
   --music <müzik.wav> --vo <vo.wav> --sfx-map audio/sfx/map.json --out-dir audio/stems [--duck-db 4.5]`
   → stem'ler (diyalog, VO, müzik, efekt) ayrı; müzik VO/konuşmanın 4–5 dB altında + konuşma anlarında ek kısma; çekim sesi ↔ üretilmiş
   ses geçişleri kısa çapraz geçişle; efektler kare hassasiyetinde (kesimler ve reveal anı); iki geçişli `loudnorm` → **-14 LUFS entegre,
   ≤ -1 dBTP**, `pyloudnorm` doğrulaması (`mix_report.json`; `sfx_placed`: her efektin türü, oturma noktası, kaydırması, kazancı).
   **Eksik konuşma (2.10.13):** planın anlatıcı (`generated`, `user_vo`) ya da sahnenin kendi sesini (`original`) beklediği yerde dosya
   yoksa ya da o aralık sessizse miks yapılmaz (çıkış 2, neden ekranda). Kullanıcıya hangi kaydın eksik olduğunu sade dille söyle; sesi
   olmayan reklamı teslime götürme.
   **Efekt öz puanlaması (2.7.0):** `PY PR/scripts/qc/sfx_review.py --mix-report audio/stems/mix_report.json --plan <plan.json>
   --moments analysis/sfx_moments.json --out audio/stems/sfx_review.json` → senkron, seviye, konuşma üstü, yoğunluk, kapsama, kesilme
   eksenleri (1–10, geçme 8) ve en kötü üç sorun. Yalnız bu üçü düzeltilir, yeniden miks, tekrar puan. `listen` listesindeki en fazla 5
   an taslak kapısında kullanıcıya zaman koduyla verilir: "şu anları telefonda dinle". Puan "dinlendi" demek değildir.
6. **Telefon testi:** `PY PR/scripts/audio/loudness.py phone --in audio/stems/mix_final.wav --out audio/stems/phone_test.wav` (300–3400 Hz
   bant). Oturumda dosyayı gerçekten dinleyebilen doğrulanmış araç yoksa **kullanıcı dinler**; seslendirme anlaşılır olmalı. Ölçüm
   sesin doğal/anlaşılır olduğunu tek başına doğrulamaz: dinleyen, dosya sürümü ve sonuç çıktıda tutulur.
7. **Altyazı (5.14):** VO ya da tutulan konuşma varsa `CaptionTrack` kelime zamanlarından (ön ayar ve vurgu: compose 2; miks konuşma
   üstündeki efekti ~6 dB kısar, konuşmayı kısmaz — `mix_report.sfx_duck_db`); font/konum stil kitabından, güvenli alanda;
   altyazı metni VO metniyle **birebir**. VO yoksa ana mesaj ekran yazısıyla.
8. **Taslak render (miksli önizleme):** `render.py plan … --quality preview` (ses miksiyle) → öz denetim (`self_review.py … --captions <words.json> --project <k>/src --data-dir DD`, ses seviyesi, altyazı
   şeridi ve altyazı fontunun glif kapsamı dahil).
9. **Taslak kapısı:** taslak, **referans tahtasıyla yan yana** gösterilir; "ilk saniye kaydırmayı durdurur mu, marka gibi duruyor mu"
   yargısı kullanıcınındır — Claude yalnızca gözlemini söyler. İstenen düzeltmeler plana yama (`edit_plan_patch`) → yeniden render →
   yeni çıktı sürümü (eski onay geçersiz). Düzeltme istekleri tercih hafızasına (`memory_add(layer="preference", kind="edit")`).
10. `stage_complete(profile_id, "S11", outputs=[{path: taslak mp4}, {path: mix_report.json}, {path: dinleme notu md}], summary, campaign_id,
    cycle_id)` → `awaiting_gate`.

## Çıktılar
`audio/stems/` (stem'ler, `mix_pre.wav`, `mix_final.wav`, `phone_test.wav`, `mix_report.json`, `sfx_review.json`), `analysis/sfx_moments.json`, `audio/beats.json`, altyazı parçaları,
miksli taslak, dinleme notu (`analysis/c<tur>-dinleme.md`: kim dinledi, hangi dosya/sürüm, sonuç), devam notu.

## Kontroller
- Her sahnenin `audio.mode`'u uygulandı (`mix_report.applied_modes`); kamerada konuşan sahnede ses değiştirilmedi.
- Loudness -14 LUFS (±1) ve ≤ -1 dBTP ölçümle doğrulandı; telefon testi dinlendi (ya da kullanıcı kontrolü bekliyor diye yazıldı).
- Altyazı = VO metni; ücretli yeni efekt/temizlik onaysız yapılmadı.
- Efekt varsa `sfx_review.json` üretildi; 8'in altındaki eksen ya düzeltildi ya da kapı mesajında gerekçesiyle yazıldı.

## Kapı mesajı
"Videonun taslağı hazır: <reklam fikri ve açılışı>, M saniye. Seslendirme: <kimin sesi>, müzik: <ad>, ses efekti: <n> tane. Kendi
değerlendirmemde en zayıf bulduğum yön: <yön ve puanı>. Sesin yüksekliğini Meta'nın önerdiği seviyeye ayarladım. Telefon
hoparlöründe deneme: <sonuç | bunu senin telefonunda dinlemen gerekiyor>. Ses efektleri için şu saniyeleri dinle: <saniyeler>.
Taslağı beğendiğin örnek reklamlarla yan yana izle. Bu taslağı onaylıyor musun, değiştirmek istediğin bir yer var mı?" → açık onayda `gate_approve(...)`.
Ölçülen ses değerleri (-14,0 LUFS / -1,2 dBTP gibi) taslak belgesinde ve kontrol raporunda kalır; kullanıcı mesajında sayı verilmez.
