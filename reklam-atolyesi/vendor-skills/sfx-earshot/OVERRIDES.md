# OVERRIDES — sfx-earshot (Leonxlnx/earshot ses bankası)

Bu klasör skill değildir; yalnızca ses dosyası ve kaynak kaydıdır (2.6.0). Earshot kodu MIT; sesler kayıt değil, Earshot'un
tariflerinden kodla üretilmiş dosyalardır (reklamda, ticari işte, düzenleyerek kullanılabilir). `fit/` altındaki 15 ses CC0 1.0
kayıtlardan çıkarılmış tariflerden üretildi (`CREDITS_FIT.md`).

## Kullanılan kısımlar
- 252 ses, 44 aile: arayüz (click, hover_tick, tap, toggle, pop, pop_in, ui_pop, notify, swipe, zip), geçiş (whoosh_fast, whoosh_big,
  swish, riser, downlifter, reverse_swell), vuruş (impact, sub_drop, cut_hit, knock, mallet), parıltı/marka (shimmer, logo_sting,
  pluck), dijital (glitch), klavye (typing_key, typing_run), nesne (drip, shutter), gerçek kayıttan türetilmiş (`fit/`).
  `pro_` önekli aileler aynı türün ikinci kuşak tarifleridir.
- **Yalnızca** `ATTRIBUTION.md` tablosunda satırı olan ve SHA-256'sı tutan dosyalar kullanılır (`scripts/audio/sfx_library.py`).
- Earshot denetiminde uyarı alan 16 ses (yükselen perde, metalik kuyruk, kesik kuyruk, tık) varsayılan aramada listelenmez;
  `sfx_library.py --include-flagged` ile görünür ve yalnızca dinlenerek seçilir.

## Alınmadı
- Earshot'un analiz kısmı (CLAP/AST modelleri, `describe`, `match`, `critique`, MCP sunucusu): torch + ~1,1 GB model ister,
  çekirdek ortama torch girmez. `critique` 7 SaaS lansman filminden türetilmiştir, e-ticaret reklamına ölçüt değildir.
- `skills/real-sound` (Freesound/Mixkit kayıtlarıyla film sesi süreci): kayıtları biz dağıtamayız; lisans tablosu fikir olarak okundu.

## Kurallar
- Bu klasöre elle ses eklenmez; banka yalnız `scripts/setup/sfx_earshot_build.py` ile, pinli commit'ten yeniden üretilir.
- Efekt bütçesi (stil `effects`, saniyede en fazla 2 efekt, aynı efekt 2 sn içinde tekrar yok) bu dosyalar için de geçerlidir.
- Kodla üretilmiş ses olduğu için organik sesin (kumaş, kağıt, sıvı, ambalaj) yerine geçmez; o sesler profil kütüphanesinden,
  yoksa ElevenLabs'ten (fiyat ve onayla) gelir. `drip`, `shutter`, `swipe/paper|cloth` yalnızca stilize karşılıktır.
