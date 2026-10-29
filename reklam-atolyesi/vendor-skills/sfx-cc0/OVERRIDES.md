# OVERRIDES — sfx-cc0 (kapishdima/soundcn, Kenney ses paketleri)

Bu klasör skill değildir; yalnızca ses dosyası ve kaynak kaydıdır (1.7.0). Depo kodu MIT; sesler Kenney'in CC0 1.0 paketleridir
(kamu malı adanması: reklamda, ticari işte, düzenleyerek kullanılabilir; atıf zorunlu değil, istenirse "Kenney (www.kenney.nl)").

## Kullanılan kısımlar
- `interface-sounds/` (100), `digital-audio/` (62), `impact-sounds/` (130), `music-jingles/` (85): toplam 377 OGG.
- **Yalnızca** `ATTRIBUTION.md` tablosunda satırı olan ve SHA-256'sı tutan dosyalar kullanılır. `scripts/audio/sfx_library.py` bunu
  makinece uygular; tabloda olmayan dosya (ör. `digital-audio/Preview.ogg`, paket önizleme montajı) listelenmez.
- Kaynak kanıtları ve dışarıda bırakılanlar `ATTRIBUTION.md`'de.

## Alınmadı
- soundcn `assets/wow/` (110 dosya): Blizzard Entertainment'ın mülkü, CC0 değil (soundcn README'si). Hiçbir koşulda eklenmez.
- `kenney_sci-fi-sounds` (dosya sayısı Kenney kaydıyla tutmuyor), `kenney_casino-audio`, `kenney_rpg-audio`, `kenney_voiceover-pack*`.
- soundcn'in base64'e çevrilmiş registry/TS dosyaları ve web uygulaması: plugin'de kullanılmaz.

## Kurallar
- Bu klasöre elle ses eklenmez; yeni dosya ancak kaynak URL'si ve lisansıyla `ATTRIBUTION.md`'ye satır olarak girerse kullanılır.
- Efekt bütçesi (stil `effects`, saniyede en fazla 2 efekt, aynı efekt 2 sn içinde tekrar yok) bu dosyalar için de geçerlidir.
- `music-jingles` kısa müzik vuruşudur (bitiş kartı, fiyat anı); müzik yatağıyla çakışıyorsa müziğin tonu/temposuyla uyumu dinlenerek
  seçilir, dinleme yapılamıyorsa kullanıcıya bırakılır.
