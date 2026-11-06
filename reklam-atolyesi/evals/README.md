# Değerlendirme seti (2.5.0, 2.8.0'de geliştirme döngüsü, 2.10.0'da ezber önlemleri eklendi)

Plugin iki katmanda sınanır. İkisi de aynı senaryo matrisine (`senaryo-matrisi.json`) dayanır: 8 ürün türü × 8 kullanıcı profili.

| Katman | Ne sınar | Nerede | Ne zaman |
|---|---|---|---|
| A. Deterministik | Kurallar, kapılar, bütçe hesabı, taslak denetimi; her ürün × kullanıcı birleşimi S00a'dan yayın kaydına kadar | `tests/test_v250_scenarios.py` (pytest) | Her push ve PR'da CI (`.github/workflows/ci.yml`) |
| B. Model cevabı | Modelin kullanıcıya cevabı: kural uyumu, seçenekli soru, sade dil, dürüstlük, ürüne uygunluk, net adım | `vakalar/<ad>/` (`claude plugin eval`) + `rubrik.md` | Her sürümden önce elle |

## Ürünler ve kullanıcılar

Ürünler: P1 düşük fiyatlı fiziksel · P2 yüksek fiyatlı fiziksel · P3 dijital · P4 hizmet (müşteri adayı) · P5 sezonluk ·
P6 katkısı bilinmeyen · P7 katkısı aralık · P8 zararına satılan (katkı ≤ 0).

Kullanıcılar: U1 yeni başlayan düşük bütçe · U2 orta bütçe sınırsız · U3 deneyimli (2. turda kreatif test) · U4 ajans çok profil ·
U5 CSV modu · U6 USD hesap · U7 bütçesi iki reklama yetmeyen · U8 toplam sınırı planı karşılamayan.

Beklenen sonuçlar matriste yazılıdır (kodun kendisinden türetilmez): U7 ve U8'de S02 kapısı bütçe nedeniyle kapanır; P8'de kullanıcı
zararı bilerek kabul edip sözü kaydedilmeden kapı açılmaz; diğer birleşimler yayın kaydına kadar ilerler.

## Katman A'yı çalıştırma

```
cd servers/ad_memory
uv run --with pytest python -m pytest -q ../../tests/test_v250_scenarios.py
```

Her birleşimde: kayıtlardan üretilen belge her metin aşamasında ilk turda geçer (yanlış alarm yok); belgedeki bir sayı kayıttan
saptırılınca denetim kritik sorun bulur (kaçırma yok); kapı beklenen nedenle açılır ya da kapanır.

## Katman B'yi çalıştırma (yayın öncesi)

```
claude plugin eval ./reklam-atolyesi --trust-plugin --runs 3 --threshold 0.8 --ablation with-without
```

- Vakalar araç çağırmadan kullanıcıya verilecek cevabı ister; ad-memory ve Meta sunucuları başlatılmaz (mock yok). Bu bilinçli bir
  sınırdır: araç akışını Katman A sınar, burada yalnızca cevabın niteliği puanlanır.
- `--ablation with-without` plugin'siz bir kol da çalıştırır; fark plugin'in katkısını gösterir.
- Çalıştırma sahibinin Claude hesabıyla yapılır ve ücretlidir; `--max-cost-usd` ile sınır konabilir.
- Sonuçlar `evals/results/` altına yazılır (depoya girmez).
- Eşik: her vaka ≥ 0,8. Altında kalan vaka sürümü durdurur; ilgili skill ya da `KURALLAR.md` düzeltilir, vaka yeniden çalıştırılır.
- **Koşular arasındaki fark bir bulgudur (2.8.0):** bir vakanın 3 koşusundan biri R1'de (kural uyumu) kalıp diğerleri geçiyorsa ortalama
  eşiği geçse bile vaka incelenir. Davranış koşudan koşuya değişiyorsa ilgili skill o kararı şansa bırakıyor demektir; skill'e açık
  bir adım ya da hook'a bir kontrol eklenir.

## Kapalı vakalar (2.10.0)

`kapali/` altındaki vakalar **düzeltme yazarken açılmaz**. Yalnızca yayından önce, Katman B'nin aynı komutuyla diğer vakalarla
birlikte çalışırlar (`claude plugin eval` `evals/` altındaki her vakayı bulur).

**2.10.14'ten beri kapalı vakalar plugin deposunda değildir.** Plugin klasörü her müşteriye kopyalandığı için içindeki vaka da müşteriye
gidiyordu; bu, vakaların bağımsızlığını bozuyordu. Kapalı vakalar artık proje dosyalarındaki **`kapali-vakalar/` klasöründe** durur ve müşteriye verilmez:

- Yönetici yayından önce o klasörü `reklam-atolyesi/evals/kapali/` altına kopyalar. Bu klasör `.gitignore`'dadır; plugin deposuna
  girmez. Vakaların kaydı (`{ad: {product, user, rubric}}`) o klasördeki `kapali-matris.json` dosyasındadır (`kapali_cases`).
- Proje dosyalarını bu projedeki bütün oturumlar görebilir; koruma yalnız CLAUDE.md'deki "açma" kuralıdır.
- Kopya yoksa `kor_kiyas.py puan` ve `kor_kiyas.py kabul` durur ("kapalı vakalar bulunamadı"); yayın onayı yalnız açık vakalarla verilmez.
- CI'da kopya yoktur: ezber denetimi orada yalnız açık vakalara bakar; kapalı vakalarla ezber denetimi yayından önce yöneticinin
  bilgisayarında, kopya yerindeyken çalıştırılır.
- 2.10.0'da yazılan üç kapalı vaka depo geçmişinde açık durduğu için artık gizli sayılmaz; proje dosyalarına taşındılar ama yerlerine yeni
  kapalı vakalar yazılır.

Neden: açık vakaları gördük ve plugin'i onlara göre düzelttik. Bir düzeltmenin gerçekten genel olup olmadığını, yalnızca hiç
bakmadığımız vakalar gösterir. Kapalı vakaların her biri şimdiye kadar hiçbir açık vakada sınanmamış bir kullanıcıyı ya da kuralı
içerir (U8 toplam sınırı yetmeyen kullanıcı, K04 yayındaki tur, K12 kanıt eşiği).

- Kapalı bir vaka yeni sürümde gerilerse sürüm durur ve `kor_kiyas.py puan` "ezbere kayma şüphesi" der. Yapılacak iş vakayı açıp ona
  göre düzeltmek **değildir**: önce bu sürümün düzeltmeleri genel kural olarak yeniden yazılır.
- Bir kapalı vaka bir kez açılıp ona göre düzeltme yapılırsa `eval_cases`'e (ve `vakalar/`'a) taşınır, yerine yeni bir kapalı vaka
  yazılır.
- `defter_oku.py` "bu imzayı kapsayan vaka var mı" sorusuna yalnızca açık vakalara bakarak cevap verir. Sahadan gelen hata için
  her zaman açık bir vaka yazılır.
- Kapsama (2.10.2): imzanın bir hata kodu varsa onu yalnızca `eval_cases` içinde o kodu `"kodlar": ["<kod>"]` listesinde taşıyan vaka
  kapsar. Bunu vakanın hatayı düzeltmeden önce yeniden ürettiği (kaldığı) görüldükten sonra yazın. Aynı aşama ve hücredeki öteki
  vakalar raporda "ilgili olabilir" diye ayrı yazılır. Kodsuz sinyallerde ("-") aşama ve hücre yeterlidir.
- Bu kural teknik olarak kilitlenemez (vakalar aynı depoda). Depo kökündeki `CLAUDE.md` onu bu depoda çalışan her Claude oturumuna
  hatırlatır; ezber denetimi kapalı vakalardan yapılan kopyayı da yakalar.

## Ezber denetimi (2.10.0, her push ve PR'da)

```
python evals/ezber_denetimi.py            # bu daldaki değişiklik (CI aynısını çalıştırır)
python evals/ezber_denetimi.py --hepsi    # bütün mevcut metin, bilgi amaçlı
```

Plugin'in davranışını belirleyen metinlere (`KURALLAR.md`, skill'ler, ajanlar, komutlar, hook'lar, rapor şablonları) bu değişiklikte
**eklenen** satırlarda, bir vakadan birebir alınmış 6 kelimelik bir parça ya da bir vaka klasörünün adı varsa CI kırmızı yanar ve
hangi satırın hangi vakaya benzediğini yazar. Yapılacak iş, düzeltmeyi vakanın kelimeleriyle değil genel bir kural olarak yeniden
yazmaktır.

Bir vaka plugin'in mevcut bir cümlesini bilerek alıntılıyorsa (ör. müşteriye sorulan hata defteri sorusu, sözlükteki bir açıklama)
matristeki kaydına `"alinti": [...]` ile alıntılanan plugin cümleleri tek tek yazılır. Yalnızca bu cümlelerin içindeki eşleşmeler
raporda görünür ama CI'ı durdurmaz; aynı vakadan gelen başka her parça ve vaka adı yine durdurur (2.10.1). Bugün iki vaka böyledir:
`hata-sonrasi-defter-sorusu` ve `s02-strateji-yeni-baslayan`.

Denetim yalnızca kelime kopyasını yakalar; "fiyat 100 TL ise şunu yap" gibi bir vakaya özgü mantığı yakalayamaz. Bunun için
`etki-defteri.md`'deki "Gerekçe" sütunu kullanılır: gerekçe bir vaka adıysa düzeltmenin hangi başka hücrelere de uyduğu yazılır.

## Puan farkı ve harcama (2.10.0; 2.10.1'de sıkılaştı, yayın öncesi, ücretsiz)

İki sürüm **aynı vaka setiyle** (matristeki açık ve kapalı vakaların hepsi), **aynı koşu sayısıyla** ve **aynı Claude sürümüyle**
çalıştırılır. Eski yayının eski vaka setiyle alınmış JSON'u kullanılamaz: eski sürümün klasörüne güncel `evals/vakalar` ve
`evals/kapali` kopyalanır ve eski sürüm yeniden çalıştırılır. Her çıktı klasörü yeni olmalıdır.

```
claude plugin eval <eski-plugin> --trust-plugin --runs 3 --threshold 0.8 --ablation with-without --json /tmp/eski.json
python evals/kor_kiyas.py kayit --json /tmp/eski.json --plugin-root <eski-plugin>
claude plugin eval ./reklam-atolyesi --trust-plugin --runs 3 --threshold 0.8 --ablation with-without --json /tmp/yeni.json
python evals/kor_kiyas.py kayit --json /tmp/yeni.json --plugin-root ./reklam-atolyesi
python evals/kor_kiyas.py puan --eski /tmp/eski.json --yeni /tmp/yeni.json
```

`kayit`, sonucun yanına `<json>.kayit.json` yazar: plugin sürümü, commit, Claude sürümü, koşu sayısı ve vaka dosyalarının parmak izi
(dosyalar kimse tarafından okunmaz, yalnızca bayt özeti alınır). `puan` iki kayıt yoksa ya da tutmuyorsa karşılaştırma yapmaz.

**Eksik sonuçta durur.** `puan` aşağıdakilerden biri varsa karşılaştırma yapmadan başarısız biter ve nedenini yazar. Hatalı koşu
ayıklanıp geri kalanla devam edilmez:

- şema sürümü 1 değil, ya da değerlendirme yarım kalmış (`partial`);
- bir eklentili koşuda `error`, `aborted` ya da `skippedPaidGraders` dolu;
- bir koşunun puanı okunamıyor, bir hakemin puanı eksik, ya da puan 0 ile 1 arasında bir sayı değil (NaN, sonsuz dahil);
- aynı vaka iki kez geçiyor, matristeki bir vaka eksik ya da matriste olmayan bir vaka var, ya da koşu sayısı `--kosu` (varsayılan
  3) ile tutmuyor;
- deney kaydı yok, ya da iki kayıtta vaka parmak izi, Claude sürümü veya koşu sayısı tutmuyor.

Sonuç tamsa:

- **Oynama payı:** eski sürümün kendi koşuları arasındaki en büyük puan farkı. Yeni ortalama eskisinden bu paydan fazla yüksekse
  "iyileşti", fazla düşükse "geriledi", aradaysa "fark yok" yazılır. Bu kaba bir karar kuralıdır, istatistiksel güven aralığı
  değildir: "fark yok" iki sürümün eşit olduğunu kanıtlamaz. Eski koşuların hepsi aynı puanı aldıysa oynama payı sıfırdır ve her
  fark sayılır.
- **Eşik:** her vakanın yeni ortalaması en az 0,8 olmalı. "Fark yok" çıksa bile eşiğin altındaki vaka sürümü durdurur.
- Gerileyen ya da eşiğin altında kalan vaka varsa çıkış kodu 1 (sürüm durur). Kapalı vakada gerileme "ezbere kayma şüphesi" diye
  işaretlenir; bu ezberin kanıtı değildir, genel bir gerileme ya da oynama da olabilir.
- **Harcama:** iki tarafta da her vakanın her koşusunda harcama varsa vaka başına toplam karşılaştırılır; yoksa iki belgenin
  toplamı (eklentisiz kol ve hakem dahil olabilir); o da yoksa "ölçülemedi" yazılır. Yeni sürüm %20 ya da daha fazla harcıyorsa ve
  hiçbir vaka iyileşmediyse uyarı verilir. Uyarı sürümü durdurmaz (bazı kurallar bilerek harcama artırır), ama etki defterine
  gerekçe yazılır. Bu sayı değerlendirmenin harcamasıdır, müşterinin kullanım maliyeti değildir.
- JSON'da koşu puanı bulunamazsa puanlar HTML rapordan okunur ve `{"puanlar": {"<vaka>": [0.8, 1.0, 1.0]}, "harcama_usd": 1.23}`
  biçiminde bir dosyaya yazılıp betiğe verilir. Bu dosya da aynı kapsam ve sayı denetiminden geçer.
- Kör karşılaştırma (aşağıda) aynen kalır. İkisi birlikte okunur: puan "fark yok" diyorsa hakemin tercihi etki defterine
  "yardım etti" olarak yazılmaz.

**Henüz doğrulanmayan:** koşu başına puan, harcama ve cevap alanlarının gerçek JSON'daki kesin yolu. Okuyucu bilinen birkaç adı
dener; bulamazsa durur. Kesin yollar küçük bir gerçek koşuyla (ücretli, ayrıca onay ister) belirlenince okuyucu yalnızca onları
okuyacak şekilde daraltılır. Bu yapılana kadar "sürüm eval ile doğrulandı" denmez.

**Yayın kararı** hepsinin birlikte geçmesidir: `claude plugin eval` çıkış kodu 0, `puan` çıkış kodu 0, kör karşılaştırma
`sonuc` çıkış kodu 0. CI model değerlendirmesini çalıştırmaz; yeşil CI bunun yerine geçmez.

## Kabul kaydı (2.10.14, her müşteri sürümü için)

CI model değerlendirmesini bilerek çalıştırmaz (ücretli). Bu yüzden "bu sürüm gerçek modelle denendi" bilgisi tek bir kayıtta durur:
`evals/kabul/<sürüm>.json`. Kayıt, Katman B koşusundan ve deney kaydından (`kor_kiyas.py kayit`) sonra yazılır:

```
python evals/kor_kiyas.py kabul --json /tmp/yeni.json --karar kabul --model <model adı> --sure-dk 95
```

Alanlar: sürüm, commit, Claude sürümü, model, tarih, koşu sayısı, vaka parmak izi, açık vakaların ortalama puanı, kapalı vakaların
yalnızca sayısı / en düşük / ortalama puanı (adları depoya yazılmaz), eşik altı vaka sayısı, toplam harcama, süre ve karar.
Deney kaydı yoksa, sonuç dosyası sonradan değiştiyse, bir vaka eksikse ya da kapalı vaka kopyası yoksa kayıt yazılmaz. Eşik altında
vaka varken karar "kabul" olamaz. Kayıt commit'lenir; `tests/test_v21014_bakim.py` mevcut kayıtların biçimini denetler.

## Önceki sürümle kör karşılaştırma (2.8.0, yayın öncesi)

Eşiği geçmek yeni sürümün eskisinden iyi olduğunu göstermez. Yayından önce aynı vakalarda iki sürümün cevapları, hangisinin hangi
sürüm olduğu gizlenerek bir hakeme verilir:

```
python evals/kor_kiyas.py hazirla --eski <eski-cevaplar> --yeni <yeni-cevaplar> --out /tmp/kor
python evals/kor_kiyas.py hakem --dir /tmp/kor          # isteğe bağlı, ücretli; ya da hakem.md'leri elle değerlendirip karar.md yazın
python evals/kor_kiyas.py sonuc --dir /tmp/kor          # regresyon varsa çıkış kodu 1
```

Cevaplar `<vaka>/<n>.md` düzeninde bir klasör ya da `claude plugin eval --json` çıktısıdır (yukarıdaki gibi iki sürüm aynı vaka
setiyle çalıştırılır). JSON'dan yalnızca eklentili koldaki cevaplar alınır ve belge `puan` ile aynı denetimden geçer; bir koşunun
cevabı bulunamazsa betik durur ve cevaplar HTML rapordan klasör düzenine kaydedilir. İki tarafta da matrisin bütün vakaları ve
aynı sayıda koşu olmalıdır. `--out` her seferinde yeni, boş bir klasördür; eski `karar.md` dosyaları yeniden kullanılmaz. "Eski daha iyi" çıkan her vaka regresyondur: değişiklik düzeltilir ya da geri
alınır ve `etki-defteri.md`'ye "bozdu" diye yazılır. Çıktı klasörünü `evals/` altına koymayın (`claude plugin eval` oradaki her
`prompt.md`'yi vaka sayar).

## Sahadan gelen hata defterleri (2.8.0)

Müşteri bir hata gördüğünde plugin ona sade bir soru sorar: "Bunu hata defterine yazıp geliştiriciye gönderelim mi?" Müşteri
"evet" derse defter bilgisayarına yazılır (`logs/hata-defteri/`) ve müşteri dosyayı bize gönderir. Defterde ad, marka, ürün, tutar
ya da serbest metin yoktur; yalnızca hangi adımda ne olduğu, kodu, senaryo hücresi (ürün × kullanıcı) ve kaç kez olduğu yazılır.

Gelen defterler toplu okunur (kapsama için yalnızca açık vakalara bakılır, bkz. "Kapalı vakalar"):

```
python evals/defter_oku.py <defter-dosyaları-ya-da-klasörü> --out /tmp/defter-raporu.md --iskelet /tmp/yeni-vakalar
```

Rapor üç şey verir: sürüm başına saha göstergeleri (etki defterinin "sahada" kısmına), tekrarlayan imzalar ve onları kapsayan vaka
olup olmadığı, önceki sürüme göre kötüleşen ya da iyileşen imzalar. Kapsanmayan imza için iskelet yazılır. Sürüm kıyası (2.10.2)
ham sayıyla değil, sırasıyla aynı aşamanın tamamlanma sayısına, bütün aşamaların tamamlanma sayısına, gözlem gününe ya da defter
sayısına bölünerek yapılır; hangisinin kullanıldığı tabloda yazar.

Döngü: imza → iskelet doldurulur → vaka düzeltmeden **önce** kalmalı (hata yeniden üretildi) → düzeltme → vaka geçer, eski vakalar
bozulmaz (kör karşılaştırma) → `etki-defteri.md` → sonraki sürümün defterleri düzeltmenin sahada tuttuğunu gösterir. Araç hatası
imzaları model cevabıyla değil, `tests/` altında bir birim testiyle yeniden üretilir.

Hangi hücre nasıl çıkarılır: ürün P8 (katkı ≤ 0) → P4 (hizmet ya da aday) → P7 (katkı aralık) → P6 (katkı bilinmiyor) → P5
(sezon) → P1-3 (kayıttan ayrılamaz); kullanıcı U4 (birden çok profil) → U5 (CSV) → U6 (TRY dışı) → U3 (2. tur ve sonrası) → Ux
(U1/U2/U7/U8 bütçeye göreli, ayrılamaz). Bilinmeyen tahmin edilmez.

## Revizeye başlarken (2.10.0)

`python evals/etki_ozeti.py` çalıştırılır. Etki defterinden iki liste verir: en az iki sürümdür "etkisiz" olup hiç işe yaramamış
bileşenler (silmeye aday) ve üç sürümdür "ölçülecek" diye bekleyenler. 2.10.2'den beri üçüncü bir liste de verir: kararı yalnız
birim testine ("yardım etti (test)") ya da bekleyen ölçüme dayanan bileşenler. "Ölçülmemiş: yok" bütün bileşenlerin ölçüldüğü anlamına
gelmez; bu üçüncü liste eval ya da sahayla henüz ölçülmemiş olanları gösterir. Betik hiçbir şeyi silmez; karar admin'indir.

## Yeni vaka ya da senaryo ekleme

1. Gerekirse `senaryo-matrisi.json`'a ürün/kullanıcı ekleyin (`expect` alanıyla beklenen kapı sonucu).
2. Vaka için `eval_cases` altına `{product, user, rubric}` yazın.
3. `vakalar/<ad>/prompt.md` (durum + kullanıcının sözü) ve her rubrik ölçütü için `graders/<rN>-<ad>.md` (`type: llm`,
   `weight`, ölçüt kodu ve geçer/kalır tarifi) ekleyin.
4. `tests/test_v250_scenarios.py::test_matrix_and_eval_cases_are_consistent` matris, rubrik ve dosyaların birbirini tuttuğunu denetler;
   `tests/test_v2100_overfit.py` aynısını kapalı vakalar için yapar.
5. Kapalı vaka eklenecekse `kapali-vakalar/<ad>/` altına ve o klasörün `kapali-matris.json` dosyasında `kapali_cases`'e yazılır
   (2.10.14). Kapalı vakayı, o sürümde düzeltme yazmayan bir
   oturum yazar; yazıldıktan sonra düzeltme oturumlarında açılmaz.
