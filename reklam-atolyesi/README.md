# Reklam Atölyesi (reklam-atolyesi) · 2.2.0

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

Müşteri paketinde (`musteri-paketi/`) `kur.cmd` yalnızca ilk kurulumu yapar (yarıda kalan kurulumu kaldığı yerden sürdürür);
tamamlanmış kurulumun güncellemesi `guncelle.cmd` ile testsiz yapılır (yedek, plugin, değişen bağımlılıklar, migration). Depo kökündeki
eski `kur.cmd` hem kurulum hem güncelleme yapar: yedek alır ve `doctor --update` çalıştırır.

**Yerel marketplace (geliştirme):** Plugin'in üst klasöründeki `.claude-plugin/marketplace.json` (adı `reklam-atolyesi`) kullanılır.
Plugin bu klasörden yerinde okunur. `data_dir` kurulumda verilir (verilmezse sorulur):

```
claude plugin marketplace add <plugin-üst-klasörü>
claude plugin install reklam-atolyesi@reklam-atolyesi --scope user --config data_dir=<veri-klasörü>
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
| `skills/` | navigator, 21 aşama skill'i (S00a–S17), 4 destek skill'i (`data-connection`, `dm-sales`, `organic`, `profile-check`), `memory`, `ref-system-map`, 7 referans skill'i (toplam 35) |
| `agents/` | meta-historian, competitor-analyst, creative-strategist, cinematographer, footage-analyst, art-director, editor, sound-designer, qc-reviewer, media-analyst, coach |
| `commands/` | `/reklam-atolyesi:basla`, `kurulum-kontrol`, `profiller`, `profil-ekle`, `profil-sec`, `tanis-marka`, `tanis-urun`, `meta-gecmis`, `yeni-kampanya`, `durum`, `sonraki`, `onayla`, `geri`, `rapor`, `rakip-analizi`, `takip`, `karar-hazirla`, `gece-uretim`, `bakim` |
| `workflows/` | `analyze-footage`, `analyze-competitors`, `render-variants`, `qc-review` (kapısız paralel işler; yedek yol: alt ajanlar) |
| `hooks/` | plugin modu ve navigator bağlamı, Meta izin listesi + Kütüphane sorgu bütçesi, ElevenLabs maliyet koruması, render mini-QC, Stop uyarısı |
| `servers/ad_memory/` | `ad-memory` MCP sunucusu (Python, SQLite WAL, FTS5 trigram, numaralı migration'lar) |
| `scripts/` | ingest, analiz, ses, kurgu planı, render, export, QC, Meta CSV, rekabet, analitik, hafıza, kurulum, duman testi |
| `templates/` | Remotion projesi ve 42 bileşenli kütüphane, nötr stil kitabı, LUT, rapor şablonları |
| `vendor-skills/` | pinlenmiş, lisanslı hazır skill'ler (skill olarak kaydedilmez; `OVERRIDES.md` önce okunur) |
| `system_manifest.json` | sistemin kendi haritası, test sonuçları, sapmalar, canlı kontrol tanımları |

## Veri
Bütün durum `data_dir` altındadır (userConfig; plugin klasörüne durum yazılmaz): `db/ad-memory.sqlite`, `.venv`, `.node`,
`profiles/<profil>/…`, `memory/system/`, `logs/`, `backups/`, `.sessions/` (geçici oturum durumu). Yedekler haftalık ve her
migration öncesi alınır; son 8 yedek tutulur. Denetim ve geri dönüş: `<py> scripts/setup/db_restore.py check --data-dir <dd>`,
`restore --data-dir <dd> --backup <dosya> [--confirm]` (Claude Code kapalıyken; mevcut veritabanı `db/onceki-<zaman>/` altında kalır).

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
**2.2.0** — profil kontrolü: 5 etiket sınırı, "kendi ortancasının kaç katı", profil puanı, İstatistikler girdisi; organik açıklama denetimi
- Etiket bulgusu "10'dan fazla ortalama" yerine "5'ten fazla etiketli paylaşım" (Instagram Aralık 2025'ten beri paylaşım ve Reels başına
  en fazla 5 etiket; Instagram'ın Threads duyurusu ikincil kaynaklardan, yardım merkezinde teyit edilmedi — ref-legal-tr-meta). Eski
  eşik yeni paylaşımlarda hiç tetiklenmiyordu. Etiket sayımı Türkçe harfli etiketleri de sayar.
- **Kendi ortancasına göre kat** (`outliers`): son 30 paylaşımda her paylaşımın beğeni+yorumu hesabın ortancasının kaç katı; en iyi ve
  en zayıf 5 paylaşım, türe göre ortanca kat ve güven düzeyi (6'dan az paylaşımda hesaplanmaz). İzlenme/erişim araçta yok; kat yalnızca
  beğeni+yorumdan hesaplanır.
- **Profil puanı** (`score`): araçtan ölçülenler + kullanıcının verdiği yazılı alanlar (isim alanı, biyografi, bağlantı, öne çıkanlar,
  sabitlenmiş, iletişim düğmesi, hikâye) 100 üzerinden, yerel ağırlıklarla; bilinmeyen madde paydadan düşer ("kazanılan / bilinen").
  Skill puan kaybına göre sırayla kopyalanabilir taslak verir (isim alanı 3 seçenek, biyografi, sabitlenmiş 3'ün görevleri, öne
  çıkan adları); profile hiçbir şey yazılmaz.
- **İstatistikler girdisi** (`--insights`): kullanıcının ekran görüntüsünden okunan izlenme, erişim, takipçi dışı erişim, gönderme,
  kaydetme, takip; izlenme katı, erişim başına gönderme/takip ve teşhis ("görüntü çok, takip az" → profil; "görüntü az" → açılış).
- **Organik açıklama denetimi** (`scripts/organic/caption_check.py`): akışta görünen ilk 125 karakter (organik için resmi sayı yok,
  yerel varsayım), ilk satır, görünen kısımda somut bilgi, en fazla 5 etiket, tek yönlendirme kanalı, görünmez karakter temizliği;
  `organic` taslakları bununla denetlenir.
- Fikir kaynağı: Jakeschincariol/instagram-agent-skill (MIT) değerlendirmesi; kod alınmadı.
- Veritabanı migration'ı yok, yeni bağımlılık yok.

**2.1.0** — yerel seslendirme (EMA): cümle duraklaması, okunuş raporu ve okunuş sözlüğü
- Gerekçe EMA'nın kaynak kodundan (ema-lightning 1.1.2, `chunker.py`): ~10 sn'ye (≈ 180 harf) kadar metin tek parça okunur, cümle
  arasına duraklama yalnızca motorun böldüğü yerde girer; 15 sn'lik VO'da cümleler birbirine bitişiyordu. Artık metin cümlelere
  bölünür, her cümle ayrı okunur (model cümle sonuyla biten parçalarla eğitilmiş), baş/son sessizliği kırpılır ve araya `--pause`
  kadar sessizlik konur (varsayılan 0,25 sn, motorun kendi cümle duraklaması; `0` = eski davranış). Kelime zamanları kaydırılır.
- **Okunuş raporu:** `tts_local.py check` sentezden önce, ses üretmeden normalleştiricinin emin olmadığı ifadeleri ("10x" → "bir sıfır
  iks", "24/7", "4,8/5") ve Türkçe harflerle okunacak yabancı görünen sözcükleri listeler. "3. kat" (sıra sayısı), "1-3 gün" (aralık) ve
  telefon numarası normalleştiriciye ipucuyla verilir ("üçüncü kat", "bir ila üç gün"). Rapor `synth` çıktısında da (`reading`).
- **Okunuş sözlüğü:** genel liste (`templates/voices/okunus-genel.json`: Wi-Fi, Bluetooth, USB-C, Hz, Black Friday, vs., örn. …) +
  marka profilinde `okunus.json` (`tts_local.py lexicon --profile-dir … --add "Yazım=okunuş"`). Yalnızca okunuş değişir: altyazı özgün
  yazımla kalır, Whisper okunuş denetimi iki yazımı da kabul eder. Sayılar metinde rakamla kalır (normalleştirici 850 TL, 2.499,90 TL,
  %12,5, 5.3, 500 ml, 14:30'u doğru okuyor; bulut ortamında 30 cümleyle denendi).
- **Kurulum önerisi:** `capability` çıktısında `install`: EMA ve Whisper eksikse birlikte önerilir (Whisper'sız okunuş denetimi yapılmaz).
- Bulut ortamında EMA ve Whisper modelleri indirilemediği için gerçek ses üretilip dinlenmedi: kod ve testler sentetik sesle ve gerçek
  normalleştiriciyle sınandı; ilk kullanımda duraklama süresi ve sözlük girdileri dinlenerek doğrulanmalıdır.
- Veritabanı migration'ı yok, yeni bağımlılık yok.

**2.0.0** — deneme kullanıcısına hazırlık: uçtan uca denetim ve düzeltmeler
- Son güncellemeler (1.6.0–1.9.0: ölçülü yazı, renk eşitleme, CC0 ses efektleri, beş yeni bileşen, ses araması, huni planlaması)
  birlikte denetlendi: kurulum, doctor, manifest, migration zinciri 001–007, testler, duman testi (9/9 adım, gerçek Remotion
  render'ı dahil), komut/skill/script/araç adı çapraz kontrolü ve belgeler. Ardından algoritma, mimari, güvenlik, dayanıklılık, yasal
  içerik, ilk kullanım ve performans ayrı ayrı denetlendi (aşağıda). Veritabanı migration'ı yok; yeni bağımlılık yok; tek yeni araç
  `scripts/setup/db_restore.py`.
- **Eski kampanya projeleri:** `render.py upgrade --project <k>/src [--dry-run]` önceki bir sürümle kurulmuş kampanya projesini güncel
  şablona getirir. Yalnızca yayımlanmış bir şablon sürümüyle bayt bayt aynı (elle değiştirilmemiş) dosyalar güncellenir; değiştirilmiş
  dosyalar `kept_customized` listesinde kalır (`templates/remotion/template_history.json`, üretici `scripts/setup/template_history.py`).
  Plan projenin çizemediği bir özelliği (ör. 1.8.0 bileşenleri, KenBurns odak) kullanıyorsa render başlamadan açık bir mesajla durur;
  önceden finalde gri "bilinmeyen bileşen" paneli çiziliyordu. S10 kullanıcıya sade dille sorar, onayla günceller ve taslakları yeniden çizer.
- **Sahne önbelleği:** segment anahtarı artık plugin şablonunu değil kampanya projesinin kendi kod dosyalarını içerir. Önceden projeye
  bileşen eklenince ya da proje tazelenince eski segmentler yeniden kullanılabiliyordu; plugin güncellemesi de değişmemiş projenin bütün
  segmentlerini boşuna yeniden render ettiriyordu.
- **Kurulum:** müşteri paketindeki `kur.cmd`, doğrulaması tamamlanmamış (yarıda kalmış) kurulumu artık kaldığı yerden sürdürür. Önceden
  "zaten kurulu, guncelle.cmd kullanın" diyordu; `guncelle.cmd` ise veritabanı olmadığı için "ilk kurulum için kur.cmd kullanın" diyerek
  kullanıcıyı döngüde bırakıyordu. Kurulumun veri klasörü denetimi isteğe bağlı ses motoru klasörünü (`.tts`) de tanır.
- **Ingest:** sarsıntı ölçümü `fileformat` seçeneğini yalnızca FFmpeg'in libvidstab'ı destekliyorsa verir (libvidstab 1.1.1+). Eski
  sürümde FFmpeg seçeneği tanımayıp çıkıyor, klibin ingest'i bütünüyle başarısız oluyordu.
- **Testler:** önceki sürümlerde "ortamdan" sayılan başarısızlıklar giderildi: ingest testleri yukarıdaki gerçek uyumluluk hatasıydı;
  doctor testi depodaki Windows `.mcp.json`'ını makinenin işletim sistemine göre denetliyordu (artık dosyanın üretildiği sisteme göre).
  Linux'ta tam paket 427 geçti, 0 başarısız, 5 atlandı (Windows'a özgü); 2.0.0 düzeltmelerinin her biri için test var
  (`tests/test_v200_*.py`).
- **Koçluk ve istatistik:** önseller kampanyanın Meta amacından dondurulur (önceden markanın bütün amaçlarının önselleri karışıyor,
  metrik başına rastgele bir amacınki kullanılıyordu; amaç okunamazsa ve birden çok amaç varsa Beta(1,1)). Ölçülmemiş metrik sıfır
  sayılmaz: ThruPlay sütunu olmayan dışa aktarımda tutma oranı "%0 · kanıt" değil, yoktur (koç ve `metrics_query`). Kalibrasyon kutuları
  tamsayı yüzdeyle (etiket "%70–79" çıkıyordu) ve "kaybeder" diyen tahminin isabeti doğru yönde sayılır. Yorgunluk penceresi baz
  günleriyle örtüşmez; tutma eğrisi beklentisi aynı format/süredeki kreatiflerden. Eşlenmemiş reklamlar konsept kıyasına, tahmin
  kaydına ve "kapat" kararına girmez. Aday kampanyasında büyütme aday ekonomisine bakar. Risk sınırı kreatif başı harcamanın altındaysa
  S02 gerekçesi bunu söyler.
- **Metrik alımı:** daha az alanla yapılan yeniden çekim önceki ölçümü silmez. CSV tarih sırası (gün/ay) dosyadan belirlenir; belirsizse
  (03/04/2026) hiçbir satır yazılmadan `csv_date_order` istenir (önceden İngilizce dışa aktarım sessizce yanlış güne yazılıyordu).
- **Ses ve görüntü:** ara miks kırpılmadan kayan noktada yazılır (yüksek müzik + VO toplamı kalıcı bozuluyordu); müzik konuşma altında
  gerçekten 4,5 dB kısılır (konuşma maskesi örnek yerine 20 ms pencereyle); negatif müzik konumu hata vermez. Renk eşitleme, gri/beyaz
  alanı olmayan klipte beyaz dengesine dokunmaz, yalnız pozlamayı eşitler (kırmızı ürün yakın çekimi "sıcak ışık" sanılıp ürün rengi
  kayıyordu). Emojili uzun yazının render ölçümü artık eşleşir; köşe kutusu çakışması ölçülmüş yazı bloğuyla denetlenir.
- **İki oturum ve yarıda kalan işler:** kapı onayı, aşama tamamlama, çekim tamam ve yayın kaydı işlem içinde yeniden denetlenir (iki
  pencerede aynı anda onay S17'de iki tur açabiliyordu). Oturum dosyası kilitle yazılır: paralel Reklam Kütüphanesi sorguları sorgu
  bütçesini, hook yazımı oturum bağlamasını ve yükleme iznini silmez. `ingest --only` önceki klipleri manifestten silmez. Yarıda kalan
  sahne sesi ve final birleştirme bitmiş dosya adıyla kalmaz.
- **Yedek ve geri dönüş:** yedek geçici ada yazılıp bütünlüğü denetlenerek yerine konur; yeni kurulumda boş veritabanının migration
  yedekleri alınmaz. `db_restore.py check|restore` veritabanını ve yedekleri denetler, seçilen yedeği önceki veritabanını
  `db/onceki-<zaman>/` altında saklayarak geri koyar (Claude Code kapalıyken).
- **Güvenlik:** aşama çıktısı yalnızca kendi profilinin klasöründen kabul edilir; `metrics_export_csv` profil klasörü dışına yazmaz;
  kurgu planı dosya adına plandaki serbest metin yol olarak giremez. İddia eşleştirmesi Türkçe büyük/küçük harfi doğru tanır.
- **Yasal:** Meta AI etiketi resmi metinden okundu (otomatik "AI info" etiketi; Türkiye'de reklamveren beyanı seçeneği yok; Türkiye'deki
  görünür açıklama yükümlülüğü Ticari Reklam Yönetmeliği'nden). İlk açılışta profil yokken kurulum eksiği marka tanışmasından önce gelir.
- **Meta kıyas:** `ads_insights_performance_vs_peers` (salt okuma) izin listesine eklendi: takip, reklam setini benzer reklamverenlere
  göre metrik başına yüzdelikle gösterir (`kind: "peers"`). Yüzdelik bağlamdır; önsel, hüküm ya da CPM tahmini değildir.
- **Belgeler:** kurulum/güncelleme yönergesi müşteri paketine göre düzeltildi (`kur.cmd` ilk kurulum, `guncelle.cmd` güncelleme, yarıda
  kalan kurulum, eski kampanyalar); yerel marketplace adı (`reklam-atolyesi`), skill sayısı (35) ve `.gitignore` (`*.egg-info/`).

**1.9.0** — huni aşamasına göre içerik planlama (TOFU/MOFU/BOFU)
- Aşama bir kitle değil, mesajın seslendiği karar anıdır. Plugin yine tek geniş set kurar, yeniden hedefleme kitlesi kurmaz; reklamı kimin
  gördüğünü Meta seçer. Taksonomiye sabit `stage` ekseni (tofu, mofu, bofu) eklendi.
- Mesaj kartı (S03, `concept_upsert(message=...)`): aşama ve dayanağı (veri, kullanıcı, varsayım), değişmesi istenen düşünce, odak
  (ihtiyaç, istek, satın alma engeli), kanıt ve beklenen eylem. Test konseptinin kartı yoksa S03 kapısı açılmaz.
- Satın alma engelleri ürün kartında (`products.objections_json`, S00c). BOFU konsepti gerçek kanıt ister (onaylı ve geri çekilmemiş yorum,
  kanıtlanabilir iddia ya da okunma tarihli sayfa bilgisi); engele odaklanan konsept üründe kayıtlı bir engele bağlanır. Uydurma yorum,
  istatistik, stok azlığı ya da kampanya süresi yok.
- Huni turu (S02, `budget_plan_json.round_mode = "funnel"`): aynı alıcı için 2–3 konsept, her biri farklı aşamada. Yalnızca 2. turdan
  itibaren açılır (ilk tur keşif turudur). Varsayılan keşif turu değişmedi.
- Koç: konsept başına aşama ölçüleri (TOFU izlenme/tutma, MOFU bağlantı tıklaması/sayfa görüntüleme, BOFU sepet/ödeme/satın alma) ve
  Meta kitle segmenti dökümü (yeni, etkileşime geçmiş, mevcut müşteri) okunabiliyorsa rapora. Huni turunda TOFU/MOFU kreatifi yalnızca
  satın alma az diye kapatılmaz; kendi aşama ölçüsü de zayıfsa kapatılır.
- Yeni günlük metrikler: `landing_page_views`, `view_content`, `initiate_checkout` (migration 007).
- QC: `checks.py funnel-diff` huni turundaki planlar yalnızca son sahne/CTA'da ayrışıyorsa uyarır.
- Soru yasağı Meta'nın kişisel özellik listesine (§8a) daraltıldı: "Hediye seçmek zor mu geliyor?" serbest, "Kilo mu aldın?" gibi kişisel
  özelliği izleyicide varsayan soru yasak. `checks.py meta-text` taraması zaten bu ayrımı yapıyordu.

**1.8.1** — ses efekti aramasında kalan boşluklar
- `sfx_library.py`: "alkış", "kalp", "ışıltı", "sayaç", "daktilo", "kalem", "damla" gibi arşivdeki organik sesler için Türkçe etiketler
  (önceden "alkış" ve "kalp" sonuç vermiyordu, "ışıltı" önce cam kırılma seslerini getiriyordu). Ekli sorgu kökle açılır ("geçişi" →
  geçiş). Eşit puanda ve aynı kaynakta eşleşen karşılık sayısı sıralar ("geçiş" → önce transition/); CC0 önceliği değişmedi. Profil
  dosyaları kütüphaneye göre göreli puanlanır (mutlak yoldaki klasör adları artık eşleşmiyor).
- Kaynağı doğrulanamayan 5 Mixkit arşiv dosyası silindi (`sparkle`, `riser-cine`, `keyboard`, `whoosh-big`, `pop`; zaten
  listelenmiyordu). "riser → impact → sparkle" cümlesi sentez riser ve kayıtlı dosyalarla kurulur; karşılıklar ai-product-video `OVERRIDES.md`.
- S04 `sfx_plan` organik sesleri önce kütüphaneye yönlendirir (doğrudan ElevenLabs değil); `ref-vendor-map` ATTRIBUTION yolu düzeltildi.

**1.8.0** — beş yeni bileşen ve KenBurns odak (37 → 42)
- `BeforeAfter` (önce/sonra; wipe, split, cut): iki kaynak da gerçek çekim olmalı; plan doğrulaması AI kaynağını, konseptte
  `before_after` seçilmemesini, sağlık hizmeti sektörünü ve cilt beyazlatma kategorisini reddeder; kozmetik/kilo için 18+ uyarısı verir.
  Renk eşitleme bu kaynaklara uygulanmaz (fark kanıtın kendisidir).
- `NumberRoll` (rakam sayacı, isteğe bağlı hane dönmesi): değer ya fiyattır (para birimi zorunlu) ya da kanıtlanabilir iddia
  listesindeki bir sayıdır (`claimIndex`/`claimRef`); belgesiz iddia reddedilir. `TextMark` (el çizimi vurgu, `@remotion/rough-notation`;
  Türkçe katlamalı eşleşme, 15 sn'de en fazla 2). `PictureInPicture` (köşe video; yazıyla çakışırsa güvenli alan uyarısı).
  `PhoneScreen` (telefon çerçevesinde ekran kaydı; kişisel veri durumu `none`/`blurred` beyan edilmeden hazır plan geçmez).
- Kamera: `kenburns_in/out` için `focus {x,y}` (yakınlaşma o noktaya kayar) ve `settle_s` (sonda duruş). KenBurns 1.1.0.
- Bileşen kaynak alanları (`before`, `after`, `inset`, `screen`) sahne ara dosyası olarak kesilir; konuşan kişi tespiti bunları da görür.

**1.7.0** — klipler arası renk eşitleme, CC0 ses efekti çekirdeği
- Farklı ışıkta çekilmiş klipler sahne ara dosyasında (LUT'tan önce) referans klibe eşitlenir: pozlama ve beyaz dengesi doğrusal ışıkta
  5 kareden ölçülür (`scripts/analyze/color_match.py`), düzeltme `colorchannelmixer` kazancıdır. Sınır ±0,5 stop ve kanal başına ±%12;
  aşan klip düzeltilmez, `color_match.json`'da yeniden çekim adayıdır. Referans `grade.match_ref` ya da pozlaması en iyi klip.
  `grade.match: false` kapatır (giyim, boya, kozmetik gibi renk hassas kategoriler). S08 kapısında önce|sonra kareleri (`compare`).
  Kurulum ffmpeg'de `colorchannelmixer` süzgecini de arar.
- Render segment önbelleği artık ara dosyanın içeriğini görür (önceden hash'ler eşleşmeyen anahtarla yazılıyordu; ara dosya değişince
  segment bayat kalabiliyordu). İlk render'da segmentler bir kez yeniden üretilir.
- CC0 ses efekti çekirdeği `vendor-skills/sfx-cc0/`: soundcn deposundan yalnız Kenney paketleri (arayüz, dijital, darbe/adım, kısa müzik
  vuruşları; 377 dosya), dosya başına kaynak URL ve SHA-256. soundcn'in World of Warcraft koleksiyonu (Blizzard, CC0 değil) alınmadı.
  `sfx_library.py` sözcük bazlı arar, Türkçe sorguyu ("tık", "darbe cam", "onay") İngilizce etiketlere açar; sıra profil → CC0 → Mixkit.

**1.6.0** — kurulum denetimi bütün plugin'ler, ölçülü yazı, sahne kesimi, döküm güveni
- Kurulum denetimi kurulu **bütün** plugin'lere bakar (`claude plugin list --json`, olmazsa `~/.claude/plugins` kayıtları, claude.ai
  senkronu, skills-dir). Video üretimi skill'i ya da ücretli/yayın sağlayıcısı MCP'si olan etkin plugin doctor'da `plugins` maddesidir;
  kurulumda kullanıcı kapatır (`claude plugin disable`, geri alınabilir) ya da kimlik bazında sapma olarak bırakır (`--plugins`).
  Kurulumdan sonra eklenen böyle bir plugin için navigator tek satır uyarır.
- Yazı bileşenleri (TextReveal, KineticWords, SoftType, LowerThird, PriceTag etiketi, CTAPulse, EndCard, BehindSubjectText) satırlarını
  gerçek fontla ölçer (`@remotion/layout-utils` 4.0.532, MIT); sığana dek `minFontSize`'a küçülür, sığmazsa kırmızı **YAZI SIĞMIYOR**.
  Ölçüm `<video>.layout.json`'a yazılır; `checks.py safe --layout` (ve `tech`) blok boyunu ölçümden alır, taşmayı sorun sayar. Tahmin
  yolu da sözcük sözcük kırmaya geçti.
- Referans videoda kesimler PySceneDetect 0.7.2 (BSD-3) AdaptiveDetector ile (hızlı kamera hareketini kesim saymaz); kurulu değilse
  ffmpeg yöntemine düşer ve `cut_method` kaydedilir. `--cut-method both` iki yöntemi karşılaştırır; kararmalar `fades_s`.
- Yerel döküm: Whisper'ın emin olmadığı sözcükler (olasılık < 0,5) kullanıcıya gösterilen metinde `[?sözcük]` ve `low_confidence`
  listesinde; altyazıya girmez.

**1.5.3** — Meta kural kayıtları resmi kaynakla güncellendi
- `ref-legal-tr-meta` §7: Meta yardım merkezinden yeniden okundu (2026-10-29). Öğrenme aşaması için ~50 sonuç/hafta ve kreatif test
  aracında bütçenin en fazla %20'si artık **resmi** (önceden "teyit edilmedi"); sayılan şey seçilen optimizasyon olayıdır.
- Kreatif test aracı 2–7 test reklamı alır (önceden "2–5, bazı hesaplarda 10"): `budget.py` ve sunucudaki `creative_test_tool_max`
  varsayılanı 5 → 7. Hesabın Ads Manager ekranındaki sayı daha düşükse girdiyle verilir. İlk turun reklam tavanı da bu sınırdır.
- §7'ye Advantage+ kampanya bütçesi (CBO) set harcama limitleri ve "yeni set diğerlerini sıfırlamaz" kuralı eklendi (plugin CBO
  kullanmaz; değerlendirme kaydı). "Benzer reklamlar tek varlık gibi gruplanır" hâlâ teyit edilmedi.
- strategy, launch-pack, ref-metrics-math, yayın paketi şablonu ve `exploration_share` açıklaması aynı bilgiye çekildi.

**1.5.2** — yazı konumu ve güvenli alan
- Yazıların yeri tek tablodan (`templates/remotion/src/layout.json`): şablon ve güvenli alan denetimi aynı dosyayı okur. Fiyat etiketi,
  harekete geçirme butonu, alt bant, altyazı ve rol yazılarının (reveal, offer, alt çapa) 9:16 varsayılanı yukarı alındı (ör. fiyat
  ortası %70 → %53, buton %80 → %55, altyazı %70 → %52); 2 satırlık blok açıklamalı reklamın alt %40'ı dahil güvenli alanda kalır. 4:5'te
  buton ve rol yazıları da sınır içine çekildi; 1:1 değişmedi. `props.y` her zaman önceliklidir.
- `checks.py safe` artık yazı bloğunun üst ve alt kenarına bakar (satır sayısı ve bileşen boyu tahmini; gerçek render'la ölçüldü),
  bileşen varsayılanlarını, `props.y` önceliğini ve altyazıyı (`--captions`) kapsar. Yazı şeritleri aynı hesabı kullanır.

**1.5.1** — küçük yazının denetimi
- **Yazı şeritleri:** öz denetim (`self_review.py`) önizlemeden her yazı anını (katman yazısı, fiyat etiketi, alt bant, kapanış kartı,
  altyazı) yazının durduğu yükseklikte 540 piksel genişliğinde, küçültmeden keser ve sayfalara dizer (`text_bands`). Kontak sayfasındaki
  270 piksellik karelerde 32 piksellik yazı okunamıyordu; bozuk harf, yedek font ve taşma artık şeritte görülür.
- **Font glif kapsamı** (`scripts/qc/font_coverage.py`): projenin yüklediği fontların (Fontsource alt kümeleri ve ağırlıkları) plandaki
  yazının, altyazının ve Türkçe alfabenin her karakterini kapsayıp kapsamadığını denetler. Eksikte (ör. `latin-ext` yüklenmemiş: ğ ş İ Ğ
  Ş ₺) öz denetim bulgu verir; yüklenmeyen ağırlık uyarıdır. Önceki Türkçe testi yalnızca Inter'i sınıyordu.
- **Önizlemede font bekleme:** şablon (`style.ts`, `Master.tsx`) stilde ve planda kullanılan bütün fontları her ağırlıkta, Türkçe örnek
  metinle yükleyip bekler; ilk karede yedek fontla çizim olmaz. Mevcut kampanya projeleri eski `src` dosyalarını korur; glif denetimi
  onlarda da çalışır.

**1.5.0** — yol haritasının son maddeleri
- **Müşteri adayı (form) sonucu + hizmet işletmesi:** sonuç türü `lead` (yol: anlık form · sitedeki form · arama; sitedeki form için
  Meta'nın Lead olayını görmesi gerekir). Ürün kaydı hizmet olabilir (`kind='service'`: süre, kapasite, randevu biçimi, bölge, düzenlenen
  alan, Meta özel reklam kategorisi ve kitle ülkeleri). Başa baş/hedef aday maliyeti = katkı × adaydan satışa dönüş oranı. Aday sonrası
  huni (ulaşılan → nitelikli → satış) haftalık dönem toplamıyla, kişisel veri olmadan (`lead_outcome_set`); koçlukta aday başı,
  nitelikli ve satış başına maliyet, dönüş oranı %90 aralığı, varsayılan oranın gözlenenle tutarlılığı. Tanışma, brief, konsept, çekim
  ve yayın paketinde hizmet dalı; özel reklam kategorisi resmi bölge listesinden; sağlıkta yönetmelik doğrulanamadığı için güvenli
  varsayılan (§7).
- **Meta A/B testi (yüksek bütçe):** `budget.py` `ab_check` (2–5 hücre, 7–30 gün, eşit bütçe — resmi; hücre başına ≥ 30 beklenen sonuç
  — yerel); uygunsa seçenek olarak sunulur, testi kullanıcı Deneyler'de kurar. Yapı `ab_test` yalnızca okunmuş çalışmayla yazılır; koçlukta
  hücre başına en düşük maliyet olasılığı ve Meta'nın kazananıyla uyuşma; hükümlerde "Meta'nın dağıtımı altında" yok.
  `ads_experiment_check_eligibility` (salt okuma) izin listesine eklendi; çalışma oluşturma araçları listede değil.
- **Vurgulu altyazı:** parçada en fazla bir vurgu sözcüğü (anahtar kelime → sayı/fiyat → en uzun anlamlı sözcük); ön ayarlar `plain` ·
  `keyword` · `keyword_upper` (Türkçe büyük harf) · `karaoke`; vurgu rengi stilden.
- **Ses efekti yoğunluğu:** 1 saniyede en fazla 2 efekt, aynı efekt 2 saniye içinde tekrar yok, efekt sahne içinde (doğrulayıcı); miks
  konuşma üstündeki efekti ~6 dB kısar, konuşmayı kısmaz.
- **Profil kontrolü** (`profile-check`): IG profili salt okumayla (son paylaşım, sıklık, video payı, yönlendirme, etkileşim); araçta
  olmayanlar (biyografi, bağlantı, öne çıkanlar) kontrol listesi.
- **Organik destek** (`organic`): kullanılmamış iyi klipler, kazanan reklamlar ve konuşma çekimlerinden aday listesi, haftalık takvim,
  taslaklar; paylaşım yapılmaz, reklam kararlarına girmez.
- Migration 006: `campaigns` ve `cycles` aynı satır ve kimliklerle yeniden kurulur (CHECK değişimi; yabancı anahtar denetimi işlem dışında
  kapatılır, sonda bütünlük denetlenir, ihlalde geri alınır); `products.kind`, `products.service_json`, `lead_outcomes` eklenir.

**1.4.9**
- **Varsayılan ses EMA**; ses kütüphanesi (VoxCPM2, 6 tasarlanmış ses) artık varsayılan değil. `tts_local.py capability` bilgisayarı
  ölçer: NVIDIA ekran kartı, RTX 30xx ve sonrası (bfloat16 için compute ≥ 8.0), ≥ 8 GB ekran belleği, sürücü CUDA ≥ 12.8, ≥ 15 GB boş
  disk. Uygunsa ve kurulu değilse kütüphane kullanıcıya **öneri** olarak sunulur (ek ses sayısı, indirme boyutu, boş alan); kabul ederse
  kurulur. Uygun değilse önerilmez, EMA kullanılır. Eşikler bu sürümde ölçüldü (RTX 5070: üretimde ≈ 6,1 GB ek ekran belleği, kurulu
  ≈ 9,8 GB).
- Seçilmiş kütüphane sesi bu bilgisayarda ya da o an çalışamıyorsa (motor yok, ekran belleği dolu) üretim EMA ile yapılır; sonuçta ve
  `.tts.json`'da `fallback` gerekçesi ve istenen ses yazılır.
- `tts_setup.py --engine voxcpm` uygun olmayan donanımda kurulumu reddeder (CPU yolu kaldırıldı). `voices --data-dir` her sesin bu
  bilgisayarda kullanılabilirliğini gösterir; doktor kütüphane uygunluğunu bilgi olarak yazar.

**1.4.8**
- **Mesajla satış modülü** (`dm-sales`): Instagram DM, WhatsApp, Messenger, telefon, web sohbeti, e-posta. Konuşma takma kodla
  (M-0001) tek tek ya da günlük toplam olarak kaydedilir; kişisel veri (telefon, e-posta, IBAN, kimlik no, @kullanıcı adı) sunucuda
  reddedilir. Durum makinesi: açık → nitelikli → teklif → satış/kayıp (kayıp nedeni zorunlu), sessiz/yeniden açma; satışta ödeme yolu
  zorunlu (mağaza bağlantısıyla ödenen satış çift sayılmaz). Günlük toplam o günün bütün konuşmalarıdır, tek tek kayıtlar onu aşamaz;
  gün markanın saat dilimindedir. Reklam bağı yalnızca kanıtla. Takip listesi, cevap/teklif/takip taslakları (gönderim yok).
- **Veri bağlantısı** (`data-connection`): satış düzenine (site platformu, Shopier, pazaryeri, DM, mağaza, kurumsal), ayarlara erişime ve
  müşteri verisi tercihine göre yol seçimi — platform entegrasyonu, piksel kodu, Events Manager'a yükleme (yalnızca açık onayla), sipariş
  içe aktarma, DM, elle. Platforma özgü adım yalnızca okunan resmi kaynakla "doğrulandı"; "tamam" yalnızca Purchase olayı görülerek ya da
  içe aktarmayla.
- **Mağaza sipariş içe aktarma** (`sales_import_csv`): her platformun CSV dışa aktarımı; yalnızca eşlenen sütunlar okunur, sipariş no
  hash'lenir, çok satırlı sipariş birleştirilir, aynı dosya iki kez sayılmaz, durum değişen sipariş güncellenir. Platform adı yazımından
  bağımsız; gün/ay sırası ve ondalık ayırıcı dosya için bir kez belirlenir; para birimi 3 harfli kod; UTF-16 okunur; aynı no farklı
  tarihle gelirse eski kayıt korunur.
- **Tek satış defteri** (koçluk): verilen dışa aktarım aralığı elle girişin dönemini kapsıyorsa dosya esastır; kapsamıyorsa ve mesaj
  kanallarında (DM modülü) aynı kanal ve dönemde ikisinden büyüğü sayılır; her çakışma rapora yazılır. Mağaza kaydı varken piksel satışı
  ayrıca eklenmez. **Meta ↔ mağaza** satırı (yalnızca pikselin gördüğü site/Shopier siparişleri) piksel sağlığını gösterir.
  Rapora mesajla satış hunisi (%90 aralık, kayıp nedenleri, ilk cevap süresi).
- **Reklam metni uzunluğu** (`checks.py copy`): Meta önerisi birincil 125 / başlık 40 / açıklama 30 görünür karakter (resmi kaynakla) +
  videonun yapısına göre kurallar (ana vaat görünür kısımda, dikeyde ilk cümle, videoda yazı/konuşma yoksa mesajı metin taşır, fiyat
  videodaysa tekrar etme); profil daha sıkı hedef verebilir.
- **Yerel seslendirme** (`tts_local.py`): VO artık bilgisayarda ve ücretsiz üretilir; ElevenLabs TTS yalnızca kullanıcı isterse yedek
  (ElevenLabs'in ana görevi çekimde olmayan sahnelerin görsel/klip üretimi). EMA Lightning (Apache-2.0, CPU) varsayılan ses; ses
  kütüphanesinde VoxCPM2 (Apache-2.0) ile metin tarifinden tasarlanmış 3 kadın + 3 erkek ses (gerçek kişiye ait değil; ekran kartı
  önerilir). Tek model yüklemesiyle 2–4 alım, kelime zamanları, okunuş eşlemesi (altyazı "850 TL" yazar), tepe koruması.
- **Yerel yazıya dökme** (`asr_local.py`, Whisper large-v3-turbo, MIT; CPU int8, torch yok, ≈ 1,9 GB): kullanıcı kaydı ve kamerada
  konuşmanın kelime zamanları ücretsiz (Scribe artık yedek). Sayı/para/yüzde okunuşu eşlenir ("850 TL" = "sekiz yüz elli lira").
  **Okunuş denetimi:** yerel seslendirmenin her alımı dökülüp metinle karşılaştırılır; farklı okunan alım farkıyla gösterilir.
- **Konuşmalı kurgu** (`asr_local.py cuts`): kameraya konuşan çekimde dolgu ("eee", dökümde olmayan sesli bölge), uzun sessizlik ve
  yeniden başlanan cümle (son alım tutulur) kesim **önerisi**; kullanıcı geri alabilir. Whisper'ın sözcük sınırları ses enerjisine
  oturtulur (duraklamadan sonraki sözcüğün başını sessizliğe çekiyordu). Tutulan parçalar kurgu planı sahnesi olur; kesikler dönüşümlü
  `punch_in` yakınlaştırmayla gizlenir; altyazı kurgu zamanına taşınır, VO altyazısıyla birleştirilebilir. Çekim rehberine "beğenmezsen
  cümlenin başından yeniden söyle" talimatı.
- Ses motorları isteğe bağlı ve ayrı ortamlarda (`tts_setup.py --engine ema|voxcpm|whisper`; boyut önce gösterilir, onaysız indirme yok;
  güncelleyici kurmaz). Windows 260 karakter yol sınırı hem motor ortamı hem model önbelleği için baştan denetlenir. Bütün modeller
  sınanan sürüme sabit ve çalışırken ağ kapalı; Whisper bağımlılıkları sabit (PyAV 19 faster-whisper 1.2.1 ile ses açamıyor). Doktor
  motor durumunu bilgi olarak gösterir.
- Satış kanalları genişledi (pazaryeri, Messenger, telefon). Migration 005 (yeni tablolar ve sütun; mevcut tablolar yeniden kurulmaz).
- §7: metin uzunluğu resmi; mesaj hedefli kampanyada başlatılan konuşma için ayrı alan bu bağlantıda yok (`results`); A/B test listesi
  okunabiliyor, ayrıntı bir çalışma olmadan sınanamadı.

**1.4.7**
- **Meta satışı görüyor mu:** S00b veri kümesinde son 7 günün Purchase olayını salt okumayla kontrol eder (`meta_signal_set/get`).
  Satış sonuçlu kampanya yalnızca Meta satışı görüyorsa açılır (sunucu kuralı). Görmüyorsa üç yol: piksel kur, satışları KVKK
  dayanağıyla Events Manager'a yükle, ya da bilinçli olarak mesaj/tıklama sonucuna optimize et. Durum ekranı uyarır.
- **Karar metriği raporda:** üstünlük olasılığı hook oranı üzerindendir ("tüm konseptlerin en iyisi olma", satış değil); her olasılık
  payda ile yazılır; Özet'te kararın sonuç maliyetinden mi üst huniden mi verildiği ve Meta'nın satış görüp görmediği.
- **"Reklam mı, teklif mi, sayfa mı?" teşhisi** (rapor bölümü): konseptler arası göreli açılış ve tıklama; tıklama var ama görünür satış
  yoksa "reklam sonrası şüpheli" — o turda kreatife satış gerekçeli olumsuz hüküm ve playbook kanıtı yazılmaz.
- **Satış kanalı ve talep:** `sales_add` kanal (Shopier, site, Instagram DM, WhatsApp, kurumsal, mağaza) ve tür (satış | talep) alır;
  rapor kanala göre yazar. Migration 004 (yalnızca sütun ekler).
- **Strateji:** problem tanımı ("ürün değil, alıcının problemi"), fiyat dışı teklif tasarımı (kişiselleştirme, paket, teslim güvencesi,
  kurumsal yol) ve kendi satış sayfası kontrol listesi.
- İlk tur yapısı değişmedi (tek set, "Meta'nın dağıtımı altında"); konsept başına eşit bütçeli ayrı set ve tahmine dayalı "ana reklam +
  kreatif test" seçenekleri değerlendirildi, eklenmedi (gerekçe: bütçe parçalanması ve ayrı öğrenme, eşit harcamanın kontrol sağlamaması,
  şema değişikliği riski, ana reklamın kanıtsız %80 bütçe alması).
- İlk turun reklam tavanı da kreatif test aracı sınırıdır: aç kalan konseptlerin hepsi sonraki turun tek testine sığar; S02 uyarısı
  Meta'nın tek sette bütçeyi eşit dağıtmadığını söyler.
- Aç kalan konsept (`carry_over`) sonraki turun kreatif testinde ilk sıradadır; hazır kreatifi yeni tur adıyla yeniden dışa aktarılır
  (render/çekim yok, ses korunur).

**1.4.6**
- Ölçekleme katmanı (test ayrı, ölçek tek): S16'da "büyüt" hükmü alan reklam ya ana sette bütçe artışıyla büyür ya da ayrı ölçekleme
  kampanyasına **mevcut gönderiyle** (beğeni ve yorumlar taşınır) taşınır. Taşıma dört koşul ister: doğrulanmış kreatif test yapısında
  hedef altı maliyet (P ≥ 0,90), günlük bütçe ≥ 7 × hedef maliyet (öğrenme için ~50 olay/hafta; yerel eşik), kampanya toplam sınırına
  sığma ve okunmuş gönderi kimliği. Hesap `coach.py` (`scale_candidates`, `budget.py scale_check`); sunucu eksik koşullu ya da gönderi
  kimliksiz taşıma maddesini reddeder.
- Yeni araçlar `scale_layer_set` / `scale_layer_get`: katman kaydı doğrulanır, üyeler ölçekleme setinin kimliğiyle kreatife bağlanır.
  S02'nin yeni bütçe planı kaydı silmez, kayıt yeni tura taşınır. Ölçekleme satırları test hesabından ayrılır; raporda ayrı bölüm
  ("Ölçekleme katmanı"), test hükmüne, önsele ve playbook kanıtına girmez. Ölçekleme harcaması toplam plana girer (`scale_layer_daily`);
  girmezse S02/S14 kapısı açılmaz. Takip, kayıtlı ölçekleme kampanyasını sapma saymaz.
- Slayt gösterisi riski (`scripts/qc/slideshow.py`): durağan kaynak payı, zayıf hareket, açılışta hareket, ardışık tekrar, tekdüze
  ritim, yazıya yaslanma. Öz denetimde `critical` düzeltilecek bulgu, `high` uyarı; QC'de de çalışır. Eşikler yereldir.
- Referans video (`scripts/analyze/reference.py`): kullanıcının "şuna benzer" dediği videonun kesimleri, çekim süreleri, hareket
  profili, sesi ve ekran yazısı bantları ölçülür; S03'te sözlükle kodlanıp **farklılaşan** yönler önerilir. Referans klasörü
  (`/references/`) kurgu planında kaynak olamaz.
- Son iki madde açık kaynak OpenMontage'daki fikirlerden uyarlandı; kod ve eşikler bu plugin'indir (AGPLv3 kodu alınmadı).
- §7: "%20–30 test bütçesi" ajans önerisi olarak işaretlendi (Meta'nın değil); öğrenme olayı sayısı ve "mevcut gönderi beğenileri
  taşır" teyit edilmedi; aynı gönderinin iki sette birlikte yayında kalmaması yerel koruma kuralı.
- Test düzeltmesi: güncelleyici testi Windows'ta geçici klasör yolundaki "pytest" sözcüğünü komut sanıyordu.

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
- Takip: ilk harcamadan sonra Meta kıyas araçları (`ads_insights_industry_benchmark`, `ads_insights_auction_ranking_benchmarks`;
  2.0.0'dan itibaren `ads_insights_performance_vs_peers`)
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
