# Müşteri paketi — 1.8.0

`musteri-paketi/` müşteriye gönderilir: ilk kurulum `kur.cmd`, sonraki güncellemeler `guncelle.cmd`.
Eski kök `kur.cmd` / `kur.ps1` ve eski masaüstü kurulum klasörü/ZIP'i korunmuştur.

Yeni güncelleyici önce SQLite yedeği alır, marketplace ve plugin'i günceller, yalnızca değişen bağımlılıkları alır,
gereken veritabanı migration'larını uygular. Smoke, pytest, render, galeri veya doctor çağırmaz.
Önceden ilk kurulumu tamamlayan müşteride sonraki açılışta toplu canlı kabul testleri de tekrarlanmaz.
Yeni test başarısı uydurulmaz; güncelleme kaydı `tests_run: false` taşır, eski doğrulama kayıtları korunur.

Güncelleme hatasında işlem başarısız koduyla çıkar ve log dosyasını sağlayıcıya gönderme mesajı gösterir.
Kullanımda gerçek araç hataları Claude'un PostToolUseFailure olayıyla dosyalanıp kullanıcıya bildirilir.
Bu, çalışan bir Claude oturumundaki araç hatalarını kapsar; Python/Claude başlamıyorsa veya hook hiç yüklenmiyorsa
otomatik bildirim üretilemez. Bu durumda kullanıcı ekrandaki hatayı iletir. Arka planda tüm disk loglarını izleyen servis yoktur.
Loglar otomatik gönderilmez; otomatik geri alma yapılmaz. Yedekler `backups`, günlükler `logs` altındadır.

## Yayın

Dağıtım hedefi: `roklento/reklam-atolyesi` deposunun `main` dalı, sürüm **1.8.0**.
Müşteri güncelleyicisi bu depoda yayımlanan sürümü alır.
Güncelleyici, yeni hata bildirimi kodu bulunmayan eski sürüme gelirse başarı demek yerine açıklayıcı hata verir.
Sonraki yayınlarda plugin sürümünü artırın ve manifesti güncel tutun.
1.8.0 migration içermez. Yeni bağımlılık: npm `@remotion/rough-notation` 4.0.532 (MIT; + roughjs ve dört küçük MIT paketi);
güncelleyici kilit dosyası değiştiği için `npm ci`'yi kendisi çalıştırır. Mevcut kampanya projelerinin `components/` klasörü
`render.py init` ile kopyalandığı için yeni beş bileşen yalnız yeni projelerde tam çalışır. Eski projede bu bileşenler "bilinmeyen bileşen"
paneli olarak çizilir; `render.py init --force-library` bileşenleri getirir ama sahne şablonu (`scenes/index.tsx`) eski kaldığı için
kaynak alanları (önce/sonra, köşe video, telefon ekranı) kırmızı değil gri "KAYNAK ÇÖZÜLEMEDİ: projeyi yeniden kurun" yer tutucusu
gösterir ve KenBurns odak yok sayılır; çökme olmaz. Bu bileşenleri kullanacak kampanya için yeni proje klasörü kurun. Galeri referansı
yenilendi (yeni beş bileşen eklendi; eski bileşen kareleri aynı).
1.7.0 migration içermez, yeni bağımlılık yok (ffmpeg'in standart `colorchannelmixer` süzgeci kullanılır; doctor bunu da arar).
Renk eşitleme varsayılan açıktır: düzeltme gereken klibin sahne ara dosyası ve tüm render segmentleri ilk render'da bir kez yeniden
üretilir (segment anahtarı artık ara dosya içeriğini görüyor). Düzeltilmeyen klipte ara dosya anahtarı 1.6.0 ile aynıdır. Kapatmak için
stilde `grade.match: false`. Yeni `vendor-skills/sfx-cc0/` klasörü ~4,4 MB (Kenney CC0 OGG; dosya başına kaynak kaydı `ATTRIBUTION.md`).
1.6.0 migration içermez. Yeni bağımlılıklar: npm `@remotion/layout-utils` 4.0.532 (MIT) ve Python `scenedetect` 0.7.2 (BSD-3, + tqdm);
güncelleyici kilit dosyaları değiştiği için `npm ci` ve `uv sync`'i kendisi çalıştırır. Mevcut kampanya projelerinin `components/`
klasörü `render.py init` ile kopyalandığı için eski bileşenlerle çizer (ölçüm kaydı üretmez, denetim tahmine döner); yeni ölçülü yazı
yeni projelerde ya da `render.py init --force-library` sonrasında gelir. Kurulum doğrulaması (kur.cmd) artık öteki plugin'leri de sorar;
güncelleme yolunda bu soru yok, navigator çakışan plugin için menüde tek satır uyarır. Galeri referansı yenilendi (yalnız TextReveal,
KineticWords, SoftType).
1.5.3 migration içermez, yeni bağımlılık yok. Kreatif test aracının reklam tavanı varsayılanı 5 → 7 (Meta resmi sınırı); kayıtlı eski
turların bütçe planları değişmez, yeni S02 hesabı 7'yi kullanır. Yalnızca skill metinleri, `budget.py` ve sunucu sabiti değişti.
1.5.2 migration içermez, yeni bağımlılık yok. Yazı konumları `templates/remotion/src/layout.json`'dan; yeni kampanya projesine
kopyalanır. Mevcut projelerin `scenes/index.tsx` ve `Master.tsx` dosyaları değişmediği için eski konumlarla çizer; denetim yeni tabloyu
kullanır, bu yüzden eski projede fiyat/buton/altyazı uyarısı çıkabilir (projeyi yeniden kurmak düzeltir).
1.5.1 migration içermez, yeni bağımlılık yok. Yeni script `scripts/qc/font_coverage.py` (font glif kapsamı); öz denetim yazı
şeritleri üretir ve `--project`/`--data-dir` verilmezse proje ile veri klasörünü çıktı yolundan bulur. Şablondaki font bekleme
değişikliği (`style.ts`, `Master.tsx`) yalnızca yeni kampanya projelerine kopyalanır; mevcut projelerin `src` dosyaları değiştirilmez.
1.5.0 migration 006 içerir: `campaigns` ve `cycles` tabloları aynı sütun, satır ve kimliklerle yeniden kurulur (sonuç türüne `lead`,
yapıya `ab_test` eklenir; SQLite CHECK kısıtını yerinde değiştiremez). Bu iki tabloya bağlı tablolar olduğu için çalıştırıcı bu
migration'ı yabancı anahtar denetimi kapalıyken tek işlemde uygular, sonda `PRAGMA foreign_key_check` boş değilse geri alır; Store
açılışı öncesinde yedek alır. Ayrıca `products.kind`, `products.service_json` ve `lead_outcomes` tablosu eklenir. Yeni bağımlılık yok.
Meta izin listesine salt okuma `ads_experiment_check_eligibility` eklendi.
1.4.9 migration içermez, yeni bağımlılık yok. Varsayılan ses EMA; ses kütüphanesi (VoxCPM2) yalnızca uygun ekran kartı ve yeterli
diskte kullanıcıya öneri olarak sunulur (`tts_local.py capability`); uygun olmayan bilgisayarda kurulum reddedilir. 1.4.8'de kütüphane
sesi seçilmiş bir stil kitabı varsa ve bilgisayar uygun değilse üretim EMA ile sürer (gerekçe çıktıda).
1.4.8 migration 005 içerir: mesajla satış (`dm_threads`, `dm_events`, `dm_daily`), sipariş içe aktarma (`sales_imports`,
`sales_orders`) tabloları ve `profiles.data_connection_json` sütunu eklenir; mevcut tablolar yeniden kurulmaz, satırlar korunur, Store
açılışı öncesinde yedek alır. Kişisel veri tutulmaz (takma kod, sipariş no özeti). Çekirdek ortama yeni bağımlılık yok.
1.4.8 yerel ses motorları (EMA seslendirme, VoxCPM2 ses kütüphanesi, Whisper yazıya dökme) **isteğe bağlıdır** ve güncelleyici kurmaz:
her biri kullanıcı onayıyla, kendi ortamına (`DD/.tts/<motor>`) `scripts/setup/tts_setup.py --engine ema|voxcpm|whisper --yes` ile kurulur
(boyut önce gösterilir: EMA ≈ 0,6 GB, Whisper ≈ 1,9 GB, VoxCPM2 ≈ 12 GB ve NVIDIA önerilir). Modeller sabit sürümdür, çalışırken ağ
kullanılmaz. Ses kütüphanesi dosyaları (`templates/voices/`, 6 wav ≈ 6 MB) plugin'le gelir. Motor kurulu değilken eski yol (ElevenLabs,
onaylı ücretli) çalışmaya devam eder.
1.4.7 migration 004 içerir: `profiles.meta_signal_json`, `sales_manual.channel` ve `sales_manual.kind` (varsayılan `sale`) sütunları
eklenir; tablo yeniden kurulmaz, satırlar korunur, Store açılışı öncesinde yedek alır. Satış sonuçlu **yeni** kampanya artık Meta'nın
satışı gördüğü doğrulanmadan açılamaz; mevcut kampanyalar engellenmez, durum ekranında uyarı görünür.
1.4.6 veritabanı migration'ı içermez: ölçekleme katmanı kaydı mevcut `cycles.budget_plan_json` alanında tutulur. Yeni ad-memory
araçları `scale_layer_set` / `scale_layer_get`; yeni script'ler `scripts/qc/slideshow.py` ve `scripts/analyze/reference.py`
(yeni bağımlılık yok: OpenCV, NumPy, Pillow ve ffmpeg zaten kurulu). 1.4.5'in migration'ı (003) 1.4.5'ten gelmeyen kurulumda yine uygulanır.

## Yerel doğrulama

**1.6.0** (Linux bulut ortamı): tam paket 351 geçti, aynı 3 ortam başarısızlığı, 5 atlandı; yeni testler `test_v160_plugins.py` (8),
`test_v160_fit.py` (5), referans ve döküm (birer). Gerçek Remotion render'ında (headless Chromium) 8 yazı bileşeni demo ve uzun metinle
ölçüldü; galerinin değişmeyen 34 bileşeni eski referansla eşleşti (ortalama 46 dB). `tsc --noEmit` temiz.

**1.5.3** (Linux bulut ortamı): tam paket 336 geçti, aynı 3 ortam başarısızlığı, 5 atlandı. Kural kayıtları Meta yardım merkezinden `ads_get_help_article` ile 2026-10-29'da okundu.

**1.5.2** (Linux bulut ortamı): tam paket 336 geçti, aynı 3 ortam başarısızlığı, 5 atlandı; yeni testler `test_v152_safe_zone.py` (9).
Gerçek Remotion render'ında üç formatta her yazı bloğunun ekrandaki üst ve alt kenarı ölçüldü; hepsi denetimin tahmin ettiği aralığın
içinde ve güvenli alanda. `tsc --noEmit` temiz.

**1.5.1** (Linux bulut ortamı): tam paket 327 geçti, 3 başarısız, 5 atlandı; yeni testler `test_v151_text_qc.py` (8) geçti. Üç
başarısızlık bu değişiklikten önce de vardı ve ortamdan geliyor (`test_dagitim.py::test_doctor_resolves_mcp_command_with_spaces`,
`test_media.py::test_ingest_outputs`, `test_media.py::test_measure_contact_sheet_material_map`). Gerçek Remotion render'ında: yalnızca
`latin-700` yüklü projede glif denetimi ğ/ş/İ eksiğini buldu ve yazı şeridinde yedek font göründü; `latin-ext` eklenince denetim geçti,
şerit doğru harfleri gösterdi. `tsc --noEmit` eski ve yeni şablonda temiz. Windows'ta ve müşteri bilgisayarında güncelleme denenmedi.

**1.5.0** (Windows geliştirici ortamı): tam paket 327 geçti, 0 başarısız (yeni testler `test_v150.py`, `test_v150_media.py`,
`test_v150_review.py`, `test_v150_verify.py`); iki bağımsız inceleme turu yapıldı (11 + 6 bulgu ve ikincil notlar düzeltildi, testlendi); migration 006, 005 şemalı ve
alt tablolarında satır olan bir veritabanında sınandı (satırlar ve kimlikler korunuyor, yabancı anahtar bütünlüğü boş, denetim yeniden
açık, ihlalli migration geri alınıyor). Duman testi vurgulu altyazıyla (`keyword_upper`) render dahil. Meta: aday alanları, A/B testi ve
özel reklam kategorisi kuralları canlı araç/yardım merkezinden okundu; A/B testi ve aday kampanyası canlı bir hesapta kurulup okunmadı;
sağlık hizmetleri yönetmeliği resmi kaynaktan açılamadı (§7, güvenli varsayılan).

**1.4.9** (Windows geliştirici ortamı): tam paket 295 geçti, 0 başarısız (yeni testler `test_tts_local.py`: donanım koşulları, öneri,
varsayılan sese düşme, uygun olmayan donanımda kurulum reddi). Gerçek motorla: kütüphane motoru olmayan veri klasöründe kütüphane sesi
istendi → EMA ile üretildi, gerekçe yazıldı. RTX 5070'te öneri ve kullanım yolu doğrulandı. Ekran kartı olmayan/eski kartlı bilgisayar
sahte donanım bilgisiyle sınandı; gerçek böyle bir bilgisayarda denenmedi.

**1.4.8** (Windows geliştirici ortamı): tam paket 286 geçti, 0 başarısız. Yeni testler `test_dm_orders.py`, `test_tts_local.py`,
`test_asr_local.py`. Migration 005, 004 şemalı bir veritabanında sınandı. Duman testi (9 adım, render dahil; örnek planda `punch_in`
sahnesi) geçti. Gerçek motorlarla sınandı (CPU Whisper large-v3-turbo, EMA; VoxCPM2 RTX 5070): 37 seslendirme alımının okunuş denetimi
(fiyat "1.249,90 TL", "99,90 TL'ye", tarih dahil), Whisper sözcük başlangıcı EMA'ya göre ortanca 60 ms / %90'ı 120 ms, konuşmalı kurgu
(yarım alım + dolgu + tekrar içeren 12,2 sn kayıt → 5,8 sn; kesilen ses yeniden dökülünce metin birebir). İki bağımsız inceleme turu
yapıldı (ilk tur 18, ikinci tur 10 bulgu; hepsi düzeltildi ve testlendi). Linux'ta tam paket, temiz bilgisayarda motor kurulumu ve
müşteri bilgisayarında uçtan uca güncelleme yapılmadı.

**1.4.7** (Windows geliştirici ortamı): tam paket 186 geçti, 0 başarısız. Yeni testler `test_signal_diagnosis.py` (7) ve
`test_scale_reference.py` eklemeleri; migration 004, 003 şemalı bir veritabanında sınandı (satırlar korunuyor, öncesinde yedek). Duman
testi sonucu manifestte. Shopier piksel alanı ve CAPI desteği canlı doğrulanmadı.

**1.4.6** (Windows geliştirici ortamı): tam paket 176 geçti, 0 başarısız, 0 atlandı. Yeni testler `test_scale_reference.py`
dosyasındadır (23). Önceki 4 güncelleyici testi hatası ortamdan değil testten geliyordu (Windows geçici klasör yolundaki "pytest"
sözcüğü komut sanılıyordu); düzeltildi. Duman testi (9 adım, render ve öz denetim dahil) Windows'ta geçti (141 sn); manifestteki duman
kanıtı bu çalıştırmadır. Galeri ve Türkçe render kanıtları 1.4.3'ten taşınır (render hattı değişmedi). Referans video script'i gerçek
bir dikey videoda denendi. Linux'ta tam paket, gerçek GitHub güncellemesi ve müşteri bilgisayarında uçtan uca kurulum yapılmadı.

**1.4.5** (Linux geliştirici ortamı): tam paket 145 geçti, 5 atlandı (Windows'a özgü), 3 başarısız. Üç hata değişiklikten önce de
vardı ve ortama bağlıdır: `test_doctor_resolves_mcp_command_with_spaces` (üretilmiş `.mcp.json` Windows yolu taşır) ve
`test_media.py` içindeki iki ingest/ölçüm testi (bu ffmpeg derlemesinde gereken filtre yok). Yeni testler `test_s03_portfolio.py`
dosyasındadır. Migration 003, 1.4.4 şemalı bir veritabanında sınandı: satırlar ve kimlikleri korunuyor, öncesinde yedek alınıyor.
Windows'ta tam paket, gerçek GitHub güncellemesi ve müşteri bilgisayarında uçtan uca kurulum yapılmadı. Render hattı değişmedi;
smoke/render/galeri kanıtları manifestte 1.4.3'ten taşınır.

**1.4.4:** 43 kontrol geçti: `test_customer_update.py`, `test_hooks.py`, `test_dagitim.py`.
Windows PowerShell 5.1 güncelleme kontrol akışı sahte dış komutlarla; SQLite WAL yedeği, migration açılışı,
doğrulama kayıtlarının korunması ve hata bildirimi geçici veri klasörlerinde sınandı.
Gerçek GitHub güncellemesi ve müşteri bilgisayarında uçtan uca kurulum yapılmadı.
Eski smoke/render/galeri kanıtları manifestte 1.4.3'ten taşındığı belirtilerek korunmuştur.
