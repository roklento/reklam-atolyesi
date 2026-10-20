# Müşteri paketi — 1.4.8

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

Dağıtım hedefi: `roklento/reklam-atolyesi` deposunun `main` dalı, sürüm **1.4.8**.
Müşteri güncelleyicisi bu depoda yayımlanan sürümü alır.
Güncelleyici, yeni hata bildirimi kodu bulunmayan eski sürüme gelirse başarı demek yerine açıklayıcı hata verir.
Sonraki yayınlarda plugin sürümünü artırın ve manifesti güncel tutun.
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
