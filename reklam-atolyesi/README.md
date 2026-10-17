# Reklam Atölyesi (reklam-atolyesi) · 1.4.5

Meta video reklamlarını **rakip analiziyle stratejiden yayın paketine** kadar üreten, yayındaki reklamları matematikle okuyup koçluk
yapan ve her turda öğrenen bir Claude Code plugin'i. Marka, reklam hesabı ve ürünler **profil verisidir**; plugin kodu markadan bağımsızdır.

## Kurulum
**Dağıtılan kurulum (Windows):** Müşteri, kurulum paketindeki `kur.cmd` dosyasını çalıştırır. Betik sırayla şunları yapar:
1. Özel GitHub marketplace'ini ekler.
2. Plugin'i `--config data_dir=<klasör>` ile kullanıcı kapsamında kurar.
3. Plugin'in `scripts/setup/windows/kurulum.ps1` adımlarını çalıştırır: araçlar, `.venv`, `.node`, sonra `scripts/setup/kurulum_dogrula.py`.

Doğrulama sırası:
1. Duman testi.
2. Türkçe render ve galeri; referans karelerle karşılaştırılır.
3. `doctor --write-ok`.

Aynı betik güncellemeyi de yapar: yedek alır ve `doctor --update` çalıştırır.

**Yerel marketplace (geliştirme):** Plugin'in üst klasöründeki `.claude-plugin/marketplace.json` (`reklam-atolyesi-local`) kullanılır.
Plugin bu klasörden yerinde okunur. Kurulumda `data_dir` sorulur:

```
claude plugin marketplace add <plugin-üst-klasörü>
claude plugin install reklam-atolyesi@reklam-atolyesi-local --scope user
```

## Başlatma
Yeni bir Claude Code oturumu açın ve yalnızca şunu yazın:

```
reklam-atolyesi
```

İlk açılışta: canlı kurulum kontrolü → `/mcp` ile **ElevenLabs** ve **Meta Ads (salt okuma)** OAuth bağlantıları → marka tanışması.
Sonrasında arayüz **sabit** numaralı ana menüdür (navigator); komut yazmanız beklenmez. Maddeler ve numaralar hiç değişmez
(`hooks/menu.json`); metni model değil `hooks/menu.py` üretir. Her an "menü" yazmak ana menüye döndürür (yarım iş devam notuna
kaydedilir, "1. Devam et" oradan sürdürür). Tek sayı yalnızca son ekran ana menüyse menü maddesidir. "çık" plugin modundan çıkar.

## Döngü
Brief → rakip analizi → strateji (kapı) → konsept görüşmesi (kapı) → çekim rehberi (kapı) → deneme → çekim → ingest → analiz →
stil yönleri (kapı) → malzeme (kapı: ses kararları + maliyet) → kurgu → ses (kapı: taslak) → varyasyon/export → QC (kapı) →
yayın paketi (kapı) → **insan yayına alır** → takip → koçluk (kapı) → öğrenme (kapı) → yeni tur.

Kapılarda sistem durur ve **açık onayınızı** bekler. Yaratıcı kararlar birlikte alınır; Claude bitmiş işi "onaylatmaz".

## Neler yapmaz
- Meta'ya yazmaz: reklam oluşturmaz, yayına almaz, bütçe değiştirmez (izin listesi hook'u + salt okuma OAuth).
- Onaysız ücretli üretim yapmaz: her ElevenLabs üretimi tahmin → kayıt → açık onay → tek kullanımlık atomik rezervasyon yolundan geçer.
- Rakip hesaplarına girmez, sosyal medya kazımaz; rakip varlıkları üretime girmez.
- AI ile insan yüzü/eli üretmez, ses klonlamaz, sahte yorum kullanmaz.

## Bileşenler
| Klasör | İçerik |
|---|---|
| `skills/` | navigator, 21 aşama skill'i (S00a–S17), `memory`, `ref-system-map`, 7 referans skill'i |
| `agents/` | meta-historian, competitor-analyst, creative-strategist, cinematographer, footage-analyst, art-director, editor, sound-designer, qc-reviewer, media-analyst, coach |
| `commands/` | `/reklam-atolyesi:basla`, `kurulum-kontrol`, `profiller`, `profil-ekle`, `profil-sec`, `tanis-marka`, `tanis-urun`, `meta-gecmis`, `yeni-kampanya`, `durum`, `sonraki`, `onayla`, `geri`, `rapor`, `rakip-analizi`, `takip`, `karar-hazirla`, `gece-uretim`, `bakim` |
| `workflows/` | `analyze-footage`, `analyze-competitors`, `render-variants`, `qc-review` (kapısız paralel işler; yedek yol: alt ajanlar) |
| `hooks/` | plugin modu ve navigator bağlamı, Meta izin listesi + Kütüphane sorgu bütçesi, ElevenLabs maliyet koruması, render mini-QC, Stop uyarısı |
| `servers/ad_memory/` | `ad-memory` MCP sunucusu (Python, SQLite WAL, FTS5 trigram, numaralı migration'lar) |
| `scripts/` | ingest, analiz, ses, kurgu planı, render, export, QC, Meta CSV, rekabet, analitik, hafıza, kurulum, duman testi |
| `templates/` | Remotion projesi ve 37 bileşenli kütüphane, nötr stil kitabı, LUT, rapor şablonları |
| `vendor-skills/` | pinlenmiş, lisanslı hazır skill'ler (skill olarak kaydedilmez; `OVERRIDES.md` önce okunur) |
| `system_manifest.json` | sistemin kendi haritası, test sonuçları, sapmalar, canlı kontrol tanımları |

## Veri
Bütün durum `data_dir` altındadır (userConfig; plugin klasörüne durum yazılmaz): `db/ad-memory.sqlite`, `.venv`, `.node`,
`profiles/<profil>/…`, `memory/system/`, `logs/`, `backups/`, `.sessions/` (geçici oturum durumu). Yedekler haftalık ve her
migration öncesi alınır; son 8 yedek tutulur.

## Geliştirici notları
- Kurulumu Claude'un yürüttüğü (etkileşimsiz) durumda: `kurulum.ps1 -DataDir <data_dir> -GlobalSkills tasi|birak` (çakışan genel skill
  kararı; varsayılan `sor` kurulum penceresinde sorar).
- `<py>` = `<data_dir>/.venv/Scripts/python.exe` (Windows) ya da `<data_dir>/.venv/bin/python` (macOS/Linux).
- Testler (plugin kökünden): `<py> -m pytest tests -q -p no:cacheprovider` (FFmpeg PATH'te olmalı).
- Statik kurulum kontrolü: `<py> scripts/setup/doctor.py --data-dir <data_dir>`.
- `hooks/hooks.json` kurulum işletim sistemine göre üretilir; plugin başka bir işletim sistemine taşınırsa `<py> scripts/setup/gen_config.py <plugin-kökü>`
  yeniden çalıştırılmalıdır (doctor uyumsuz yorumlayıcı yolunu kırmızı gösterir).
- Hook ve `.mcp.json` üretimi: `scripts/setup/gen_config.py <plugin-kökü>` (exec biçimi; Windows/posix yorumlayıcı yolu).
- `ad-memory` sunucusu `uv run` ile değil, `data_dir` sanal ortamının Python'uyla `servers/ad_memory/server.py` olarak başlar.
  - Sanal ortam: `uv sync --project servers/ad_memory --frozen --no-install-project` (yalnızca bağımlılıklar).
  - Kod her zaman yüklü plugin sürümünün klasöründen okunur.
  - Gerekçe: Dağıtılan kurulumda her sürüm ayrı bir önbellek klasörüne kopyalanır.
- Vendor güncelleme: `scripts/setup/update-vendor.sh <repo> <commit>` (fark incelemesi ve insan onayı).
- Lisanslar: `vendor-skills/THIRD_PARTY_NOTICES.md`; Remotion ve ElevenLabs kullanım koşulları `skills/ref-legal-tr-meta`.

## Müşteri paketi
Deponun `musteri-paketi/` klasöründe ilk kurulum (`kur.cmd`) ve testsiz güncelleme (`guncelle.cmd`) ayrıdır.
Eski kök kurulum betikleri aynı davranışı korur. Yeni güncelleyici SQLite yedeği alır, plugin'i günceller,
yalnızca değişen bağımlılıkları alır ve gerekli migration'ları uygular. İlk kurulumu tamamlamış kullanıcıda
toplu canlı kabul testleri açılışta tekrarlanmaz; önceki test kayıtları değiştirilmez.
Gerçek araç hataları `PostToolUseFailure` ile yerel loga yazılır ve kullanıcıya sağlayıcısına göndermesi söylenir.
Kaynak: https://code.claude.com/docs/en/hooks#posttoolusefailure
Python/Claude başlayamıyorsa hook çalışamaz; kullanıcı ekrandaki hatayı iletir. Arka plan log izleyicisi yoktur.

## Sürüm notları
**1.4.5**
- Kreatif çeşitliliği: test hakkı önce farklı alıcılara konuşan farklı fikirlere gider. Yeni `buyer` (kime konuşuyor) sözlük ekseni
  (sözlük 1.5.0); ürün tanışmasının 5. sorusu alıcıları ve anları ayrı kaydeder (`buyers_json`, migration 003).
- S03 kapısı keşif konseptlerini denetler: konsept başına tek test hook'u (öteki açılışlar yedek, sonraki turun karşılaştırması için),
  tek alıcı, konseptler arasında farklı alıcı ve `emotion/moment/proof/first_frame`'den en az ikisinde fark. Aynı denetim görüşme
  sırasında `concept_diversity_check` ile. Birincil doğrulama çifti muaf. Yedek hook'tan üretilen çıktı test reklamı olarak kaydedilemez.
- `concept_upsert` / `hook_upsert` güncellemede verilmeyen alanları korur; ses niyeti gibi tek alanlı güncelleme kararı, alıcıyı ve
  yedek işaretini silmez.
- Meta dayanağı `ref-legal-tr-meta` §7'de: Advantage+ kitle, kreatif yorgunluğu ve öğrenme aşaması resmi; "benzer reklamlar aynı
  kişilere gider" teyit edilmedi, kural yerel koruma kuralıdır. Alıcı etiketi reklam metninde izleyiciye atfedilmez (§8a).

**1.4.4**
- Ayrı müşteri kurulum/güncelleme paketi; güncellemede test ve örnek render yok.
- Kullanım hatalarında yerel log ve kullanıcı bildirimi; otomatik veri gönderimi yok.

**1.4.3**
- Meta reklam standartları (`ref-legal-tr-meta` §8, resmi yardım merkezi metinlerinden): kişisel özellikler, sansasyonel içerik, sağlık
  ve görünüm, önce/sonra sahnesinin kategoriye göre kuralı. Konsept, çekim planı, QC, yayın paketi ve QC incelemecisi bunu denetler.
- `checks.py meta-text --plan | --text`: Türkçe metinde kişisel özellik imaları, şok/korku dili, sağlıkta kesin/süreli sonuç vaadi ve
  önce/sonra için uyarı taraması. Uyarıdır, karar değildir; her uyarı QC'de gözle karara bağlanır.

**1.4.2**
- Meta platform kuralları için kaynak protokolü (`ref-legal-tr-meta` §7): her kural resmi (yardım merkezi `ads_get_help_article` ya da
  canlı araç, bağlantı + tarih), yerel koruma kuralı ya da "teyit edilmedi" olarak işaretlenir. Strateji, yayın paketi, QC, takip,
  koçluk ve kurgu bu durumu denetler.
- Güvenli alan: açıklama metni (`disclaimer.on`) ya da AI (`ai_share > 0`) içeren 9:16 planda alttaki %40 boş (Meta resmi kılavuzu).
- Kreatif test payı ~%20 artık "Meta sınırı" diye değil, plugin'in yerel üst sınırı ve teyit edilmemiş Meta önerisi diye yazılır;
  günlük bütçe artışı ≤ %20 yerel koruma kuralıdır.
- Takip: ilk harcamadan sonra Meta kıyas araçları (`ads_insights_industry_benchmark`, `ads_insights_auction_ranking_benchmarks`)
  bağlam olarak; veri yoksa "kıyas yok". Kıyas önsel değildir.
- Geçmiş ve kıyas yokken "sektör ortalaması" vaadi engellendi.

**1.4.1**
- Sabit ana menü (9 madde, `hooks/menu.json` + `hooks/menu.py`); "menü" her yerden ana ekrana döner; sayılar yalnızca menüdeyken menü
  maddesidir. Yeni `menu_render(session_id)` aracı hook'la aynı metni verir.
- İlk kurulum düzeltmesi: Claude Code'u kuran resmi betiğin açtığı katı mod `kurulum.ps1`'i 1/5'te durduruyordu (`Set-StrictMode -Off`).
- Hook çıktısı ASCII kaçışlı JSON: Windows kod sayfasında Türkçe karakterler artık bozulmaz.
- Doctor: çakışan genel skill'ler ayrı madde (`global_skills`); "dokunma" kararı sapma olarak kaydedilir. `setup_verified_at` statik kontrol
  geçmeden yazılmaz.
- `meta_fields.json` canlı doğrulanmış kanonik adlarla; ekonomi hesabında bilinmeyen maliyet kalemi çökme yerine "bilinmiyor"; rakip görüntüsünde
  `competitor_id` doğrulaması; profil düzeyinde tek açık devam notu; `memory_add` kaynak değeri skill'de düzeltildi.
- Güncelleme: aynı kurulum dosyası (`kur.cmd`) yeniden çalıştırılır; veriler korunur, canlı kontrollerin etkilenen maddeleri yeniden yapılır.
