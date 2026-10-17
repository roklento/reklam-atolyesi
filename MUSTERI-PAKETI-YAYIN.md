# Müşteri paketi — 1.4.4

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

Dağıtım hedefi: `roklento/reklam-atolyesi` deposunun `main` dalı, sürüm **1.4.4**.
Müşteri güncelleyicisi bu depoda yayımlanan sürümü alır.
Güncelleyici, yeni hata bildirimi kodu bulunmayan eski sürüme gelirse başarı demek yerine açıklayıcı hata verir.
Sonraki yayınlarda plugin sürümünü artırın ve manifesti güncel tutun.

## Yerel doğrulama

43 kontrol geçti: `test_customer_update.py`, `test_hooks.py`, `test_dagitim.py`.
Windows PowerShell 5.1 güncelleme kontrol akışı sahte dış komutlarla; SQLite WAL yedeği, migration açılışı,
doğrulama kayıtlarının korunması ve hata bildirimi geçici veri klasörlerinde sınandı.
Gerçek GitHub güncellemesi ve müşteri bilgisayarında uçtan uca kurulum yapılmadı.
Eski smoke/render/galeri kanıtları manifestte 1.4.3'ten taşındığı belirtilerek korunmuştur.
