---
name: materials
description: "reklam-atolyesi S09 malzeme — sahne başına ses kararı (kullanıcıyla), seslendirme, müzik, efekt, AI görsel/klip; her ücretli üretim tahmin → kayıt → açık onay → rezervasyon yolundan. Kapılı."
---

# materials — S09 · Malzeme (spec 5.7–5.11, 5.13 ses kararı, 3.2, 9.1, bölüm 10, 11)

## Amaç
Seçilen stil taslağının sahne seslerini kullanıcıyla kararlaştırmak ve eksik malzemeyi tamamlamak: seslendirme (üretilmiş ya da
kullanıcının kaydı), müzik, efekt, AI görsel ve klip. AI oranı sabit değildir (ilke 6); kurguya ve üretilen görüntünün kalitesine göre.
Ses hattı `sound-designer`, görsel kabul `art-director` yöntemiyle. **Hiçbir ücretli çağrı onaysız yapılmaz.**

## Ön koşul
- S08 kapısı geçilmiş (seçilen stil `styles/v<N>.json`, `style_preview` planı).
- Oturuma bağlı profil **ve kampanya** (`session_bind`): `cost_guard` ücretli çağrıyı yalnızca bağlı kampanyanın onaylı kaydıyla geçirir.
- Canlı kontrolde `el_estimate_schema` maddesi geçmiş olmalı; geçmediyse `estimate_only` reddedilir ve ücretli üretim kapalı kalır
  (yerel/kullanıcı malzemesiyle devam).

## Girdiler ve bağlam paketi
`memory_context(profile_id, "S09", campaign_id, cycle_id)`: üretim prosedürleri (işe yarayan prompt/ayar), model kabul oranları, ses
tercihleri, seçilen konseptler (ses niyeti), maliyet özeti. Ayrıca `analysis/material-map.json`, S07 ses ölçümleri (`asset_query`),
S04 `sfx_plan`, `brands.elevenlabs_voice_id`, `cost_summary`, `generation_find`.

## Kullanılan hazır skill'ler ve OVERRIDES
Her biri için **önce** `OVERRIDES.md` (REST/SDK/CLI/anahtar akışları kapalıdır; yalnızca model adı ve parametre bilgisi):
- `PR/vendor-skills/text-to-speech/{OVERRIDES.md, SKILL.md, references/voice-settings.md}` — VO.
- `PR/vendor-skills/music/{OVERRIDES.md, SKILL.md}` — müzik.
- `PR/vendor-skills/sound-effects/{OVERRIDES.md, SKILL.md}` — organik efekt.
- `PR/vendor-skills/voice-isolator/{OVERRIDES.md, SKILL.md}` — gerekiyorsa ses temizleme (ücretli).
- `PR/vendor-skills/speech-to-text/{OVERRIDES.md, SKILL.md}` — Scribe kelime zamanları (ücretli; yalnızca yerel Whisper kurulamıyorsa yedek).
- `PR/vendor-skills/ai-product-video/{OVERRIDES.md, references/sound-design.md, references/music-beat-sync.md}` — ses tasarımı
  yöntemi; efekt arşivi yalnızca `ATTRIBUTION.md`'de kaynağı kayıtlı dosyalar.
- `PR/vendor-skills/xilo-opus-video/OVERRIDES.md` — koddan sentezlenen tasarım sesi fikri.

## Adımlar

### 1. Sahne ses kararı (kapının yarısı; 5.13)
`stage_start(profile_id, "S09", campaign_id, cycle_id)`. Her sahne için `audio.mode` kullanıcıya sorulur:
`original` · `original_clean` · `user_vo` · `generated` · `none`. Claude S07 ölçümüne göre **önerir** (örnek: "s2'nin çekim sesinde trafik
gürültüsü var, temizlesek bile …; üretilmiş efekt ve müzik öneriyorum") ve konseptin ses niyetini hatırlatır; **karar kullanıcınındır**.
Kamerada konuşan kişi olan sahnede seçenek yalnızca `original`, `original_clean` ya da sahneyi kurgudan çıkarmaktır.
Her karar `decision_log(profile_id, decision="scene_audio:<sahne>=<mode>", note, campaign_id, cycle_id, stage="S09", checkpoint=…)`;
planda `audio.decision_id`. Tercih gözlemi `memory_add(layer="preference", kind="sound")`.

### 2. Ücretli üretim protokolü (her çağrıda aynı; 9.1)
1. **Kampanya başına tek flow:** yoksa `creative_create_flow` (ücretsiz); kimliği devam notuna. Birbirini besleyen üretimler aynı flow'da.
2. **Güncel model:** `creative_get_flow_node_types`; yeni model için `creative_get_model_guide`, parametreler `creative_get_model_schema`.
3. **Ticari kullanım hakkı (bölüm 10):** kullanılacak model/özellik, abonelik ve kullanım biçiminin reklam lisansı doğrulanır (kaynak
   URL, kontrol tarihi, kapsam). Belirsizse o ücretli üretim **durur**; hakları belgeli mevcut malzeme seçilebilir. Beta çıktıları
   kullanılmaz. Müzik için `ref-legal-tr-meta`'daki Eleven Music özetine bak (plan/kuruluş büyüklüğü/kullanım türü).
4. **Kişisel veri:** girdi tanınabilir kişi/ses içeriyorsa önce `processing_permission_check(profile_id, provider="elevenlabs",
   purpose, contains_personal_data=True, data_kinds, session_id, consent_ids)`; dayanak yoksa gönderim yok. Yükleme araçları
   (`creative_create_asset_upload`, `creative_attach_reference_file`…) hook tarafından bu kayıt olmadan reddedilir.
5. **Fiyat:** aynı çağrı `estimate_only: true` ile (ücretsiz; flow'a boş düğüm ekleyebilir).
6. **Kayıt:** `generation_log(profile_id, campaign_id, cycle_id, tool_name, params, estimate_credits, model, kind, input_file_hashes?,
   flow_snapshot_sha256?)` — `params` gerçek çağrıyla **birebir** aynı olmalı (`context`, `estimate_only`, arayüz alanları hash'e girmez;
   `generations_count` varsayılanı doldurulur). `creative_run_flow_nodes` için `creative_get_flow` görüntüsünün hash'i zorunlu.
   Sonuç `blocked` ise (aynı talep sürüyor/belirsiz/tamamlanmış) yeni çağrı yapılmaz; uzlaştırma ya da yeniden indirme.
7. **Onay:** kullanıcıya araç, model, adet, tahmini kredi, ne üretileceği ve lisans notu söylenir; **açık onay** alınca
   `generation_approve(profile_id, generation_id, approved_max_credits, count, approval_text, approval_scope={license:{source,
   checked_at, scope}, purpose, contains_personal_data, processing_permission_ref?})`. Parametre ya da fiyat değişirse yeni onay.
8. **Çağrı:** gerçek çağrı yapılır; `cost_guard` aynı Store koduyla `estimated → running` rezervasyonunu atomik alır ve onayı tüketir.
   Reddedilirse sebebi okunur; **yeniden onaylatılıp körlemesine yürütülmez**, önce neden düzeltilir.
9. **İzleme:** sağlayıcı kimliği/flow oturumları gelir gelmez `generation_update(profile_id, generation_id, provider_request_id,
   flow_id, session_ids)`; `creative_get_flow_run_status` ile `poll_after_seconds` bekleyerek izlenir (tekrar çağrı yok).
   Bağlantı kopması/zaman aşımı `unknown`'dur, `failed` değil. `running/unknown/completed` talep otomatik yeniden çağrılmaz.
10. **Sonuç:** dosya `campaigns/<k>/audio/{vo,music,sfx}/` ya da `ai/` altına indirilir → `generation_update(..., status="completed",
    cost_credits, output_path)`; kabul kontrolünden sonra `accepted=True|False` (+ `evidence`). Kabul oranları prosedürel hafızaya.

### 3. Seslendirme (5.7)
- **Kullanıcının kaydı:** `audio/user_vo/` → temizlik (`PY PR/scripts/audio/loudness.py clean --in … --out …`; yetmezse voice-isolator,
  ücretli protokol) → kelime zamanları (aşağıda) → ses kütüphanesi. **Gerçek bir kişinin sesi klonlanmaz** (kullanıcınınki dahil).
  Kayıtta duraksama, "eee" ya da yeniden başlanan cümle varsa aynı konuşmalı kurgu yolu kullanılır (`asr_local.py cuts`, `compose` 2b).
- **Üretilmiş (yerel, varsayılan; 1.4.8):** metin konsept ve hook'tan; 15 sn ≈ 30–35 kelime; yalnızca izinli iddialar; emoji, #etiket,
  @kullanıcı adı ve bağlantı yok (yüksek sesle okunur; araç reddeder). Sayı ve para yazıldığı gibi kalabilir ("850 TL"): okunuşa
  normalizer-tr çevirir, altyazı VO metniyle birebir kalır. Üretim:
  `PY PR/scripts/audio/tts_local.py synth --data-dir DD --voice <stil kitabı sound.voice | ema-varsayilan> --script vo.txt
  --out audio/vo/<ad>.wav --takes 3` → `<ad>.wav`, `<ad>_alim2.wav` …; her alım için `.words.json` (kelime zamanları; Scribe gerekmez)
  ve `.tts.json` (kaynak, `ai_generated: true`).
  Ücretsiz ve bilgisayardan çıkmaz: ücretli üretim protokolü gerekmez. Motor kurulu değilse kullanıcıya boyutu söylenip onayla
  `PY PR/scripts/setup/tts_setup.py --data-dir DD --engine ema --yes` (≈ 0,6 GB, CPU yeterli).
  **Ses seçimi:** `tts_local.py voices` listesi (cinsiyet, yaş, ton, tempo, uygun ürün türleri) kullanıcıya gösterilir, deneme cümlesiyle
  dinletilir; seçim stil kitabına `sound.voice`. EMA tek sestir; kütüphanedeki diğer sesler `voxcpm` motorunu ister (≈ 12 GB indirme, NVIDIA GPU
  önerilir; kurulu değilse EMA sesi önerilir, zorlanmaz). Kütüphanedeki sesler gerçek kişiye ait değildir (metinle tasarlanmış yapay
  sesler); kullanıcının ya da başkasının sesi klonlanmaz.
  **Alımlar:** `--takes 3` (1–4) tek çağrıda farklı tohumlarla (model bir kez yüklenir; ücretsiz). ElevenLabs seslendirmesi yalnızca kullanıcı açıkça isterse yedek yoldur (ücretli
  protokol, `brands.elevenlabs_voice_id`); ElevenLabs'in bu sistemdeki ana görevi çekimde olmayan sahnelerin görsel/klip üretimidir.
- **Ön seçim:** süresi kurguya uyanlar (ffprobe) → **okunuş denetimi** → dinleyerek seçilen 1–2 alım. Whisper motoru kuruluysa
  `tts_local.py` her alımı yerelde döker ve VO metniyle karşılaştırır (`pronunciation_ok`, `diffs`: "850 ↔ sekiz yüz altmış",
  "metinde var, duyulmadı"; sayı/para/yüzde okunuşu fark sayılmaz); metinle birebir alımlar listede öne gelir, farklı olanlar
  kullanıcıya farkıyla gösterilir. Denetim yalnızca sözcükleri ölçer: ton, vurgu ve doğallık için **kullanıcı dinler ve seçer**
  (oturumda dosyayı dinleyebilen doğrulanmış araç yoksa); döküm dinlemenin yerine geçmez. Türkçe okunuş hatası → yazım düzeltilir
  (yerel seste sayı/kısaltma yazımı ya da noktalama; ElevenLabs yedeğinde gerekirse IPA), tek alım yeniden (yerelde ücretsiz; ElevenLabs
  yedeğinde yeni tahmin + onay).
- **Kelime zamanları:** yerel seslendirmede `tts_local.py` aynı adımda üretir (EMA: modelin zamanları; kütüphane sesi: aynı metnin
  EMA okunuşundan DTW ile aktarım). Kullanıcının kendi kaydı ve ElevenLabs alımı için **yerel Whisper** (ücretsiz, bilgisayardan çıkmaz):
  `PY PR/scripts/audio/asr_local.py transcribe --data-dir DD --in audio/user_vo/<ad>.wav --script vo.txt --out-dir audio/user_vo`
  → `audio/user_vo/<ad>.words.json` (yazım VO metninden, zaman dökümden; okunduğu gibi değilse `diffs`). Motor kurulu değilse kullanıcıya boyut
  söylenip onayla `PY PR/scripts/setup/tts_setup.py --data-dir DD --engine whisper --yes` (≈ 1,9 GB, CPU yeterli). Kurulamıyorsa yedek:
  `creative_transcribe_audio` (Scribe; **ücretli**, protokolle) →
  `PY PR/scripts/audio/words_align.py --transcript t.json --script vo.txt --out audio/vo/<ad>.words.json` (altyazı metni VO metniyle birebir).

### 4. Müzik (5.8)
Stil kitabından tür, tempo aralığı, duygu eğrisi; süre = kurgu + 2 sn. ElevenLabs `music` düğümü (`eleven_music_v2_5`), varsayılan **enstrümantal** (VO ile çakışma ve söz lisansı riski; sözlü müzik yalnızca kullanıcının
kararı ve ayrı lisans kontrolüyle);
protokolle 2–4 aday. Her aday için `PY PR/scripts/audio/beats.py --audio <aday.wav> --out audio/music/<aday>.beats.json`; kullanıcıya
15 sn önizleme; seçim. Ölçü sınırına göre kırpma/döngü; reveal anı güçlü vuruşa gelecek ofset. Instagram trend müzikleri kullanılmaz.

### 5. Efekt (5.9)
Liste konseptlerden ve `sfx_plan`'dan. **Önce kütüphane:** `PY PR/scripts/audio/sfx_library.py --query <etiket> --profile-dir
DD/profiles/<slug>`. Eksik **tasarım** sesleri (whoosh, shimmer, riser, impact, pop) kodla:
`PY PR/scripts/audio/sfx_synth.py --kind <tür> --dur <sn> --out audio/sfx/<ad>.wav --seed <n>` (ücretsiz). Eksik **organik** sesler
(kağıt, kumaş, cam, sıvı, dokunma…) ElevenLabs `sfx` (`eleven_text_to_sound_v2`, süre ve `loop`), protokolle. Seviye eşitleme, kısa
fade, etiketleme; profil ses kütüphanesine.

### 6. AI görsel ve klip (5.10, 5.11)
- **Ne zaman:** malzeme haritasında eksik/zayıf sahne ya da ağırlığı "AI" olan sahne. **Asla:** ürünün gerçekliğini kanıtlayan sahne,
  karşılaştırma iddiası, insan yüzü/eli ya da AI karakter (yüz ve eller gerçek çekimden).
- Gerçek çekimli eş yoksa (S07) önce ek çekim ya da konsept uyarlaması; AI klibi gerçek eş olmadan teste girmez.
- Varsayılan modeller `ref-production-recipes` tablosunda (ör. gerçek kareden kısa hareket `kling-3-pro`, ucuz deneme önce); sıra üretim
  hafızasındaki kabul oranlarıyla güncellenir. Prompt şablonu: kamera dili + özne + zamanla değişen + mekan + atmosfer + **değişmeyecekler**.
  Gerçek kare aynı flow'a yüklenir (izin kapısı), `connect_from`.
- **Kabul kontrolü:** gerçek kareyle yan yana kontak sayfası (ürünün şekli, parça sayısı, rengi, üzerindeki yazı) → `generation_update(accepted)`.
  Kabul edilen katman planda `ai_clip`/`ai_image` kaynağı ve AI etiketi bayrağıyla; `provenance.ai_share` buradan.

### 7. Planı bağla ve bitir
Seçilen taslağın sahne sesleri ve varlıkları üretim planına bağlanır: `edit_plan_save(…, plan={purpose:"production", status:"draft",
scenes[].audio.mode + decision_id, music, vo, …})` ve `edit_plan_validate`. Maliyet özeti (`cost_summary`) çıkar.
`stage_complete(profile_id, "S09", outputs=[{path: malzeme özeti md}, {path: plan json}], summary, campaign_id, cycle_id)` → `awaiting_gate`.

## Çıktılar
Sahne ses kararları (`decisions`), `audio/{vo,user_vo,music,sfx}/`, `*.words.json`, `beats.json`, `ai/` (prompt kayıtlarıyla),
`generations` kayıtları (tahmin, onay kapsamı, maliyet, kabul), güncel plan, malzeme ve maliyet özeti, devam notu.

## Kontroller
- Her ücretli çağrının `generations` kaydı, açık onayı ve lisans kapsamı var; transkripsiyon da ücretli sayıldı.
- Ses klonu yok; AI ile insan üretilmedi; ürün gerçekliğini kanıtlayan sahnede AI yok.
- Kamerada konuşan kişi sahnesinde ses değiştirilmedi; her sahnede kullanıcı kararı var.
- Belirsiz (`unknown`) çağrı yeniden başlatılmadı; uzlaştırma bekliyor.

## Kapı mesajı
"Ses kararları: s1 none · s2 original_clean · … (gerekçeler). Malzeme: VO <kaynak, seçilen alım>, müzik <aday>, efektler <liste>,
AI <katmanlar, kabul durumu>. Bu tur ücretli kullanım: … kredi (onaylı tahmin …; gerçekleşen …). Onaylıyor musun, neyi değiştirelim?"
→ `gate_approve(...)`. S10 yeni sahne ekler ya da ses seçimini değiştirirse yalnızca etkilenen sahnenin kararı yeniden sorulur.
