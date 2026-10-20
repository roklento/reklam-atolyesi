---
name: ref-production-recipes
description: "reklam-atolyesi üretim tarifleri — script haritası, ffmpeg komutları, ses hedefleri, AI model yönlendirme, çekim kurtarma, render altyapısı, export/adlandırma, maliyet kuralları."
---

# ref-production-recipes — üretim tarifleri (spec 5.4, 5.13, 5.10–5.11, 5.16–5.21, 11)

Yollar: `PR` = `${CLAUDE_PLUGIN_ROOT}`, `DD` = `${user_config.data_dir}`, `PY` = `DD/.venv/Scripts/python.exe` (Windows) ya da
`DD/.venv/bin/python`. PATH'teki Python'a güvenilmez. Script'ler `ad-memory` veritabanına yazmaz; kayıtlar MCP araçlarıyla.
Parametreler `style.json` ve kampanya ayarlarından gelir; aşağıdaki sayılar spec varsayılanlarıdır.

## Ortak kurallar (5.1)
Bütün görüntü/yazı/efekt/ses kurgu planına bağlıdır · her ücretli üretim önce `estimate_only` + `generations` + kullanıcı onayı ·
her render kullanıcıya gösterilmeden önce öz denetim · taslaklar proxy'den, final 4K kaynaktan kesilen ara dosyalardan 1080 ·
yerel işler doğrulanmış çıktılardan sürer; ücretli çağrı otomatik tekrarlanmaz (`unknown` uzlaştırılır) · **ham çekime dokunulmaz** ·
her adımın girdisi/sonucu/maliyeti ilgili tabloya.

## Script haritası (işlev → dosya)
| İşlev | Komut |
|---|---|
| probe / ingest (CFR, HDR→SDR, proxy, sarsıntı, sabitleme, ses, HEIC/EXIF) | `PY PR/scripts/ingest/convert.py probe <dosya>` · `… ingest --campaign-dir <k> [--fps 30|60] [--only …]` |
| sahne ara dosyaları | `PY PR/scripts/ingest/scenes.py --plan … --assets … --out-dir footage/scenes --quality proxy|final [--style …] [--map-out …]` |
| ölçüm (netlik, pozlama, hareket, ses, kişi) | `PY PR/scripts/analyze/measure.py --clip … [--shake-permille …] [--audio …] --out …` |
| kontak sayfası | `PY PR/scripts/analyze/contact_sheet.py --video … --out … [--per-second] [--times …]` |
| malzeme haritası | `PY PR/scripts/analyze/material_map.py --menu … --clips … [--photos …] --out … [--json-out …]` |
| logodan renk | `PY PR/scripts/analyze/palette.py --logo … [--n 5] [--out …]` |
| vuruş haritası | `PY PR/scripts/audio/beats.py --audio … --out beats.json` |
| temizlik / ducking / loudnorm / ölçüm / telefon testi | `PY PR/scripts/audio/loudness.py clean|duck|loudnorm|measure|phone …` |
| sahne sesi + miks | `PY PR/scripts/audio/mix.py --plan … --scene-audio … [--music …] [--vo …] [--sfx-map …] --out-dir audio/stems` |
| tasarım sesi sentezi | `PY PR/scripts/audio/sfx_synth.py --kind whoosh|shimmer|riser|impact|pop|tone --dur … --out … [--seed …]` |
| ses kütüphanesi | `PY PR/scripts/audio/sfx_library.py --query … [--profile-dir …]` |
| yerel seslendirme (+ okunuş denetimi) | `PY PR/scripts/audio/tts_local.py synth --data-dir DD --voice … --script vo.txt --out … --takes 3` (1–4) |
| yazıya dökme (yerel Whisper) | `PY PR/scripts/audio/asr_local.py transcribe --data-dir DD --in … [--script vo.txt] --out-dir …` |
| konuşmalı kurgu kesimi / altyazı birleştirme | `PY PR/scripts/audio/asr_local.py cuts --transcript … --out … --asset … --at …` · `captions --words a@0 --words b` |
| ses motoru kurulumu | `PY PR/scripts/setup/tts_setup.py --data-dir DD --engine ema|voxcpm|whisper [--yes]` (boyut önce gösterilir) |
| kelime zamanları / altyazı (Scribe yedeği) | `PY PR/scripts/audio/words_align.py --transcript … --script vo.txt --out …words.json` |
| plan doğrulama | `PY PR/scripts/compose/validate_plan.py <plan> [--style] [--beats] [--assets]` |
| render (init / plan / galeri / Türkçe final) | `PY PR/scripts/render/render.py init|plan|gallery|turkish …` |
| öz denetim | `PY PR/scripts/render/self_review.py --video … --plan … --out-dir … [--style] [--beats] [--round n]` |
| LUT | `PY PR/scripts/render/grade_lut.py identity|make|apply …` |
| export / ad / anahtar | `PY PR/scripts/render/export.py video|name|key …` |
| teknik QC | `PY PR/scripts/qc/checks.py black|safe|tech …` |
| Meta CSV / adlandırma / önsel kontrolü | `PY PR/scripts/meta/meta_tools.py csv-check|naming|priors|synth-csv …` |
| rakip yardımcıları | `PY PR/scripts/competitive/comp_tools.py diff|group|map|distance|offer|library-normalize …` |
| bütçe / koçluk / grafik / rapor / kalibrasyon | `PY PR/scripts/analytics/{budget,coach,charts,report,calibration}.py …` |
| hafıza önizlemeleri (salt okuma) | `PY PR/scripts/memory/memory_tools.py consolidation-preview|usage-report|fold-preview --data-dir DD` |

## FFmpeg tarifleri (spec örnekleri aynen; script'ler bunları uygular)
```bash
# VFR → 30 fps CFR, HDR(HLG) → SDR, 4K korunur
ffmpeg -i in.mov -vf "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p,fps=30" \
  -c:v libx264 -crf 14 -preset slow -c:a pcm_s16le out_sdr_cfr.mov

# Sabitleme (2 geçiş)
ffmpeg -i in.mov -vf vidstabdetect=shakiness=6:accuracy=15:result=t.trf -f null -
ffmpeg -i in.mov -vf vidstabtransform=input=t.trf:smoothing=20:zoom=3,unsharp=5:5:0.6 -c:v libx264 -crf 14 out_stab.mov

# Ducking: müziği VO'ya göre kıs
ffmpeg -i music.wav -i vo.wav -filter_complex \
 "[0:a][1:a]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=300[m];[m][1:a]amix=inputs=2:normalize=0" mix.wav
# Loudness (1. geçiş ölç, 2. geçiş uygula)
ffmpeg -i mix.wav -af loudnorm=I=-14:TP=-1:LRA=11:print_format=json -f null -
ffmpeg -i mix.wav -af loudnorm=I=-14:TP=-1:LRA=11:measured_I=..:measured_TP=..:measured_LRA=..:measured_thresh=..:linear=true final.wav
```
Not: bazı FFmpeg sürümlerinde `vidstabdetect` varsayılan olarak ikili TRF yazar; script'ler her zaman `fileformat=ascii` kullanır.

## Ses hedefleri (5.13)
Müzik VO/konuşmanın 4–5 dB altında + `sidechaincompress`; efektler kare hassasiyetinde; iki geçişli `loudnorm` **-14 LUFS entegre,
≤ -1 dBTP**, `pyloudnorm` doğrulaması; telefon testi 300–3400 Hz (dinleme insan/doğrulanmış araç). `original_clean`: önce `afftdn`,
yetmezse ElevenLabs voice-isolator (ücretli).

## AI model yönlendirme (varsayılanlar; her kampanyada `creative_get_flow_node_types` ile tazelenir, kabul oranıyla güncellenir)
**Görsel (5.10):**
| İş | Varsayılan | Alternatif | Kural |
|---|---|---|---|
| Ürün fotoğrafını sahneye yerleştirme / arka plan (ürün değişmeden) | `gpt-image-2` (referanslı düzenleme) | `gemini-3-pro-image`, `flux-3-image` | ürün korunur; gerçek fotoğrafla yan yana |
| Doku, zemin, son kart arka planı | `flux-3-image` | `recraft-v4.1`, `bytedance-seedream-5-pro` | marka paletine göre |
| Arka plan kaldırma (maske) | `birefnet-v2-bg-removal` | — | `BehindSubjectText`, `Parallax25D` |
| Görsel büyütme | `topaz-image-upscale` | — | |

**Video (5.11)** — asla: ürün gerçekliğini kanıtlayan sahne, karşılaştırma iddiası, insan yüzü/AI karakter:
| İş | Varsayılan | Alternatif | Not |
|---|---|---|---|
| Gerçek kareden kısa hareket (5–10 sn) | `kling-3-pro` | `bytedance-seedance-v2.5`, `veo-3.1-generate-001` | gerçek kare aynı flow'a, `connect_from` |
| Gerçekçi ortam/atmosfer | `veo-3.1-generate-001` | `kling-3-pro` | |
| Var olan videonun ışığını/arka planını değiştirme | `runway-aleph2` | `kling-o3-edit-video` | yeni görüntü → AI etiketi |
| Klibi uzatma | `bytedance-seedance-v2.5-extend` | `gemini-omni-1.1-flash-extend` | |
| Çözünürlük artırma | `topaz-video-upscale` | — | odaksızı düzeltmez |
| Ucuz taslak denemesi | `veo-3.1-fast-generate-001` | `ltx-v2-fast` | önce ucuz dene |
Ses: seslendirme yerel `scripts/audio/tts_local.py` (EMA varsayılan, VoxCPM2 ses kütüphanesi; 1.4.8), ElevenLabs TTS `eleven_v4` yalnızca kullanıcı isterse yedek; müzik `eleven_music_v2_5` varsayılan enstrümantal (sözlü müzik yalnızca kullanıcı kararı ve lisans kontrolüyle); efekt `eleven_text_to_sound_v2`.
Prompt şablonu: kamera dili + özne + zamanla değişen + mekan + atmosfer + **değişmeyecekler** listesi.

## Amatör çekim kurtarma (5.20)
| Sorun | Tarif | Sınır |
|---|---|---|
| Titreyen el | `vidstab` 2 geçiş + hafif zoom | çok sert sarsıntı kurtarılmaz |
| Düz kadraj | 4K → 1080 `KenBurns` | 2× üstünde netlik düşer |
| Renk tutarsızlığı | ortak LUT + eğri eşitleme | karışık ışık tam düzelmez |
| Gürültü | `hqdn3d`/Topaz + ince gren | aşırı karanlık kurtarılmaz |
| Düşük netlik | Topaz upscale | odaksız kareyi düzeltmez |
| Yavaş çekim yok | `minterpolate` veya AI ara kare | 60 fps çekim her zaman daha temiz |
| Dağınık arka plan | maske + bulanıklık / Runway Aleph | kenar kontrolü gerekli |
| Gürültülü ses | voice-isolator / `afftdn` | müzik altındaki konuşma zor |
| Eksik sahne | gerçek kareden AI klip | ürün gerçekliğini kanıtlayan sahnede kullanılmaz |

## Render altyapısı (5.21)
Önizleme 0,5 ölçek (9:16 → 540×960; tek sayı çift sayıya: 4:5 → 540×674) proxy ara dosyalardan; final ölçek 1, `--quality final`, final ara
dosyalardan. İşçi bütçesi `max(1, floor(CPU/2))`; `J` paralel render → her birinin concurrency'si `max(1, floor(bütçe/J))`, `J ≤ bütçe`;
bellek yetersizliğinde `J` düşer. Final render süreleri sistem hafızasına. Sahne önbelleği: çözülmüş sahne, kaynak hash'leri, stil kopyası,
font/LUT hash'leri, bileşen kodu, kilit dosyası render sürümleri, format, fps, ölçek/kalite, tohum, zamanlama, komşu geçişler, ilgili ses/beat;
yalnızca bitmiş ve hash'i doğrulanmış dosya. Yarıda kalan render doğrulanmış sahneleri kullanır.

## Export, formatlar, adlandırma (5.16, 5.18, 5.19)
- Export: H.264 High, yuv420p, 30 fps CFR, CRF 16–18 (ya da 12–16 Mbps), AAC 48 kHz 256 kbps, `+faststart`.
- Formatlar: 9:16 1080×1920 (Reels/Stories; yazı güvenli alanı üst %14, alt %35, yanlar %6; açıklama metni ya da AI içeren reklamda alt %40 — Meta, `ref-legal-tr-meta` §7) · 4:5 1080×1350 (Feed; üst/alt ~250 px, yanlar
  ~100 px) · 1:1 1080×1080 isteğe bağlı. Varsayılan teslim 9:16 + 4:5.
- Dosya adı `<MARKA>_<KAMPANYA>_<KONSEPT>_<MEDYA>_<SÜRE>_<HOOK>_<VO>_<KAYNAK>_<TUR>_<REV>_<FORMAT>[_k<KART>]` (örnek biçim:
  `MRK_K1_A_video_15_h1_vo_ai_c1_r1_916.mp4`); `MEDYA`: video|static|carousel; `KAYNAK`: real|ai; statik/carousel süresi `na`.
  `creative_key` = format ve kart numarası çıkarılmış ad = Meta reklam adı.

## Maliyet ve güvenlik (11)
Yaklaşık kredi (referans; gerçek fiyat her üretimde `estimate_only`): seslendirme ~200/alım (kısa cümle ~35), müzik ~900/20 sn aday, efekt
~50/alım; video/görsel her seferinde tahminle. Yerel render ve kod efektleri kredi harcamaz (Remotion/font lisansı ayrı). Ücretli araçlara
kalıcı/genel izin verilmez; zamanlanmış işlerde ücretli araçlar izin katmanında da engellenir; `bypassPermissions` kullanılmaz. Anahtar
dosyaya yazılmaz, loglanmaz. Meta salt okuma; plugin reklam oluşturmaz, bütçe değiştirmez.
