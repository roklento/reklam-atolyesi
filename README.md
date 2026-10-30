# Reklam Atölyesi — Kurulum

Reklam Atölyesi, Claude Code'a kurulan bir plugin'dir. Meta video reklamlarını rakip analiziyle stratejiden yayın paketine kadar üretir,
yayındaki reklamları okuyup koçluk yapar ve her turda öğrenir. Bu belge kurulumu ve güncellemeyi anlatır.

## Başlamadan önce

| Gerekli | Not |
|---|---|
| Windows 10 veya 11 (64 bit) | Program kurma izni (kurulum sırasında Windows birkaç kez onay isteyebilir) |
| Claude hesabı ve Claude masaüstü uygulaması | Ücretli plan (Pro, Max, Team veya Enterprise). Claude Code komut satırı da yeterlidir |
| GitHub hesabı | Sağlayıcınız bu hesaba depo daveti gönderir. Daveti GitHub'da (e-posta ya da github.com bildirimleri) kabul edin |
| ElevenLabs hesabı | Seslendirme, müzik ve efekt için; reklam kullanımına uygun ücretli plan. Ücretli üretimler sizin kredinizden düşer ve her biri önce onayınıza sunulur |
| Facebook hesabı | Markanın reklam hesabına Business portföyü üzerinden yetkili kişisel hesap. Reklam Atölyesi Meta'ya yalnızca okuma izniyle bağlanır, reklam oluşturmaz veya bütçe değiştirmez |
| Disk alanı | Veri klasörünün sürücüsünde en az 50 GB, sistem sürücüsünde (genellikle C:) en az 10 GB boş alan |
| İnternet | İlk kurulumda yaklaşık 3 GB indirilir |

**Remotion lisansı:** Videolar Remotion ile üretilir. Remotion en fazla 3 kişilik şirketler için ücretsizdir; daha büyük şirketlerin
remotion.pro adresinden şirket lisansı alması gerekir. Lisans sorumluluğu kullanan şirkete aittir.

## Kurulum

1. Sağlayıcınızın gönderdiği kurulum paketini (ZIP) bir klasöre çıkarın (ör. `Belgeler\ReklamAtolyesi-kurulum`). Klasörde
   `kur.cmd`, `kur.ps1`, `guncelle.cmd`, `guncelle.ps1`, `guncelle.py` ve `KULLANIM.txt` yan yana olmalıdır (paketin kaynağı bu
   deponun `musteri-paketi/` klasörüdür).
2. **`kur.cmd`** dosyasına çift tıklayın.
   - Windows "Bilgisayarınız korundu" derse **Ek bilgi → Yine de çalıştır**'ı seçin.
3. Betik sırayla şunları yapar ve gerektiğinde size sorar:
   - git ve Claude Code'u denetler, eksikse kurar.
   - **GitHub girişi:** İlk seferde tarayıcıda GitHub girişi açılır. Daveti kabul ettiğiniz hesapla giriş yapın.
   - **Veri klasörü:** Markalarınızın verisi, çekimler ve render'lar burada tutulur. Önerilen klasörü Enter ile kabul edebilir ya da
     boş alanı fazla olan bir sürücüde yeni bir klasör yazabilirsiniz. Bu klasör boş olmalıdır.
   - Node.js, uv ve FFmpeg (tam sürüm) eksikse kurar. Windows onay isterse **Evet** deyin.
   - Python ve Remotion bağımlılıklarını veri klasörüne kurar.
   - **Doğrulama (15-20 dk):** Sistem sentetik bir deneme yapar ve örnek videolar oluşturur. Kareler beklenenden farklı çıkarsa iki
     görsel açılır ve size "aynı görünüyor mu?" diye sorulur.
4. **KURULUM TAMAMLANDI** yazısını görünce Claude masaüstü uygulamasını tamamen kapatın: sistem tepsisindeki simgeye sağ tıklayıp
   **Çıkış**'ı seçin. Ardından uygulamayı yeniden açın.
5. Yeni bir oturum açıp yalnızca şunu yazın:

   ```
   reklam-atolyesi
   ```

   İlk açılışta ElevenLabs ve Meta hesaplarınızı bağlamanız istenir (`/mcp`). Ardından marka tanışmasıyla başlanır.

Kurulum bütünüyle ilk seferde ortalama 20-40 dakika sürer.

**Kurulum yarıda kaldıysa** (doğrulama geçmedi, pencere kapandı, internet kesildi): sorunu giderip **`kur.cmd`**'yi yeniden çalıştırın.
Betik kayıtlı veri klasörünü bulur ve kaldığı yerden sürdürür. Kurulum tamamlanmışsa `kur.cmd` sizi `guncelle.cmd`'ye yönlendirir.

## Güncelleme

Sağlayıcınız yeni sürüm duyurduğunda:

1. Claude masaüstü uygulamasını sistem tepsisinden tamamen kapatın; açık Claude Code oturumlarını da kapatın.
2. **`guncelle.cmd`** dosyasına çift tıklayın.

Betik kayıtlı veri klasörünü kullanır ve şunları yapar:

- Veritabanınızın yedeğini alır (`<veri klasörü>\backups`).
- Plugin'i yayımlanan sürüme günceller.
- Yalnızca değişen bağımlılıkları kurar ve gereken veritabanı geçişlerini uygular.

Test ve örnek render çalıştırmaz. Profil, kampanya ve hafıza verilerinize dokunulmaz. Bitince Claude'u yeniden açıp yeni oturumda
`reklam-atolyesi` yazın.

**Güncellemeden önce başlamış kampanyalar:** Her kampanyanın video projesi, kurulduğu sürümün şablonuyla sabit kalır; güncelleme bu
projeleri kendiliğinden değiştirmez (onayladığınız taslakların görünümü bozulmasın diye). Böyle bir kampanyada yeni bir bileşen
(ör. önce/sonra, rakam sayacı, telefon ekranı) istenirse Reklam Atölyesi bunu söyler ve projeyi güncellemek için onayınızı ister;
onaydan sonra taslakları yeniden çizip gösterir. Yeni kampanyalar her zaman güncel şablonla kurulur.

## Sorun giderme

| Durum | Ne yapmalı |
|---|---|
| "Depoya erişilemedi" | GitHub davetini kabul ettiğinizden emin olun. Yanlış hesapla giriş yaptıysanız Windows **Kimlik Bilgileri Yöneticisi → Windows Kimlik Bilgileri**'nden `git:https://github.com` kaydını silip tekrar çalıştırın |
| "winget yok" | Microsoft Store'dan **Uygulama Yükleyicisi** (App Installer) uygulamasını kurun |
| Disk alanı uyarısı | Yer açın ya da boş alanı fazla olan bir sürücüde veri klasörü seçin. Yine de devam ederseniz bu durum kayda geçer |
| Doğrulama geçmedi | Ayrıntılar `<veri klasörü>\logs\kurulum-dogrulama-*.json` dosyasındadır. Bu dosyayı ve pencerede yazan kurulum günlüğünü sağlayıcınıza gönderin. Sorun giderilince `kur.cmd` kaldığı yerden sürer |
| Güncelleme tamamlanamadı | Ekrandaki mesajı ve `<veri klasörü>\logs\reklam-atolyesi-guncelleme-*.log` dosyasını sağlayıcınıza gönderin. Yedek `backups` klasöründedir; sorun giderilince `guncelle.cmd` yeniden çalıştırılabilir |

## Kaldırma

1. Plugin'i kaldırmak için Claude'da `/plugin` menüsünü açıp **reklam-atolyesi**'yi kaldırın ya da komut satırında şunu çalıştırın:

   ```bash
   claude plugin uninstall reklam-atolyesi@reklam-atolyesi
   ```

2. Veri klasörü sizin verinizdir ve otomatik silinmez. Gerekirse yedeğini alıp kendiniz silebilirsiniz.
