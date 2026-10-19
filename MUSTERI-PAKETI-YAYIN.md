# Müşteri paketi — 1.4.6

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

Dağıtım hedefi: `roklento/reklam-atolyesi` deposunun `main` dalı, sürüm **1.4.6**.
Müşteri güncelleyicisi bu depoda yayımlanan sürümü alır.
Güncelleyici, yeni hata bildirimi kodu bulunmayan eski sürüme gelirse başarı demek yerine açıklayıcı hata verir.
Sonraki yayınlarda plugin sürümünü artırın ve manifesti güncel tutun.
1.4.6 veritabanı migration'ı içermez: ölçekleme katmanı kaydı mevcut `cycles.budget_plan_json` alanında tutulur. Yeni ad-memory
araçları `scale_layer_set` / `scale_layer_get`; yeni script'ler `scripts/qc/slideshow.py` ve `scripts/analyze/reference.py`
(yeni bağımlılık yok: OpenCV, NumPy, Pillow ve ffmpeg zaten kurulu). 1.4.5'in migration'ı (003) 1.4.5'ten gelmeyen kurulumda yine uygulanır.

## Yerel doğrulama

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
