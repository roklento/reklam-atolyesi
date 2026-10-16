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
  cümlesi), efekt arşivi (yalnızca kaynağı kayıtlı dosyalar).
- **ffmpeg**: `PR/vendor-skills/ffmpeg/OVERRIDES.md` → `SKILL.md` (yöntem; loudness ve export kuralları plugin'indir).

## Adımlar
1. `stage_start(profile_id, "S11", campaign_id, cycle_id)`.
2. **Vuruş haritası** (yoksa): `PY PR/scripts/audio/beats.py --audio audio/music/<seçilen>.wav --out audio/beats.json`.
3. **Sahne sesi uygulaması:** `generated` ve `none` sahnelerde çekim sesi kaldırılır; `original_clean` önce ücretsiz `afftdn`
   (`PY PR/scripts/audio/loudness.py clean --in … --out …`), yetmezse voice-isolator (ücretli protokol: tahmin → kayıt → açık onay).
   Kullanıcının seslendirmesi ve tutulan konuşma için gürültü azaltma + yüksek geçiren filtre.
4. **Yeni efekt ihtiyacı** (S10 yeni `audio_cues` eklediyse): önce ses kütüphanesi (`sfx_library.py`) ve kodla sentez (`sfx_synth.py`);
   ElevenLabs gerekiyorsa fiyat ve onay **S11 içinde** alınır (S09 kapısı yeniden açılmaz).
5. **Miks:** `PY PR/scripts/audio/mix.py --plan <plan.json> --scene-audio footage/scenes/map_final.json (ya da map_proxy.json)
   --music <müzik.wav> --vo <vo.wav> --sfx-map audio/sfx/map.json --out-dir audio/stems [--duck-db 4.5]`
   → stem'ler (diyalog, VO, müzik, efekt) ayrı; müzik VO/konuşmanın 4–5 dB altında + konuşma anlarında ek kısma; çekim sesi ↔ üretilmiş
   ses geçişleri kısa çapraz geçişle; efektler kare hassasiyetinde (kesimler ve reveal anı); iki geçişli `loudnorm` → **-14 LUFS entegre,
   ≤ -1 dBTP**, `pyloudnorm` doğrulaması (`mix_report.json`).
6. **Telefon testi:** `PY PR/scripts/audio/loudness.py phone --in audio/stems/mix_final.wav --out audio/stems/phone_test.wav` (300–3400 Hz
   bant). Oturumda dosyayı gerçekten dinleyebilen doğrulanmış araç yoksa **kullanıcı dinler**; seslendirme anlaşılır olmalı. Ölçüm
   sesin doğal/anlaşılır olduğunu tek başına doğrulamaz: dinleyen, dosya sürümü ve sonuç çıktıda tutulur.
7. **Altyazı (5.14):** VO ya da tutulan konuşma varsa `CaptionTrack` kelime zamanlarından; font/konum stil kitabından, güvenli alanda;
   altyazı metni VO metniyle **birebir**. VO yoksa ana mesaj ekran yazısıyla.
8. **Taslak render (miksli önizleme):** `render.py plan … --quality preview` (ses miksiyle) → öz denetim (`self_review.py`, ses seviyesi dahil).
9. **Taslak kapısı:** taslak, **referans tahtasıyla yan yana** gösterilir; "ilk saniye kaydırmayı durdurur mu, marka gibi duruyor mu"
   yargısı kullanıcınındır — Claude yalnızca gözlemini söyler. İstenen düzeltmeler plana yama (`edit_plan_patch`) → yeniden render →
   yeni çıktı sürümü (eski onay geçersiz). Düzeltme istekleri tercih hafızasına (`memory_add(layer="preference", kind="edit")`).
10. `stage_complete(profile_id, "S11", outputs=[{path: taslak mp4}, {path: mix_report.json}, {path: dinleme notu md}], summary, campaign_id,
    cycle_id)` → `awaiting_gate`.

## Çıktılar
`audio/stems/` (stem'ler, `mix_pre.wav`, `mix_final.wav`, `phone_test.wav`, `mix_report.json`), `audio/beats.json`, altyazı parçaları,
miksli taslak, dinleme notu (`analysis/c<tur>-dinleme.md`: kim dinledi, hangi dosya/sürüm, sonuç), devam notu.

## Kontroller
- Her sahnenin `audio.mode`'u uygulandı (`mix_report.applied_modes`); kamerada konuşan sahnede ses değiştirilmedi.
- Loudness -14 LUFS (±1) ve ≤ -1 dBTP ölçümle doğrulandı; telefon testi dinlendi (ya da kullanıcı kontrolü bekliyor diye yazıldı).
- Altyazı = VO metni; ücretli yeni efekt/temizlik onaysız yapılmadı.

## Kapı mesajı
"Taslak: <konsept/hook>, M sn, ses: VO <kaynak>, müzik <ad>, efektler <n>; -14,0 LUFS / -1,2 dBTP; telefon testi: <sonuç | senin
dinlemen gerekiyor>. Referans tahtasıyla yan yana izle. Bu taslağı onaylıyor musun, neyi değiştirelim?" → açık onayda `gate_approve(...)`.
