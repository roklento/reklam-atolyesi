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
birlikte çalışırlar (`claude plugin eval` `evals/` altındaki her vakayı bulur). Matristeki kayıtları `kapali_cases` bölümündedir.

Neden: açık vakaları gördük ve plugin'i onlara göre düzelttik. Bir düzeltmenin gerçekten genel olup olmadığını, yalnızca hiç
bakmadığımız vakalar gösterir. Kapalı vakaların her biri şimdiye kadar hiçbir açık vakada sınanmamış bir kullanıcıyı ya da kuralı
içerir (U8 toplam sınırı yetmeyen kullanıcı, K04 yayındaki tur, K12 kanıt eşiği).

- Kapalı bir vaka yeni sürümde gerilerse sürüm durur ve `kor_kiyas.py puan` "ezbere kayma şüphesi" der. Yapılacak iş vakayı açıp ona
  göre düzeltmek **değildir**: önce bu sürümün düzeltmeleri genel kural olarak yeniden yazılır.
- Bir kapalı vaka bir kez açılıp ona göre düzeltme yapılırsa `eval_cases`'e (ve `vakalar/`'a) taşınır, yerine yeni bir kapalı vaka
  yazılır.
- `defter_oku.py` "bu imzayı kapsayan vaka var mı" sorusuna yalnızca açık vakalara bakarak cevap verir. Sahadan gelen hata için
  her zaman açık bir vaka yazılır.
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
matristeki kaydına `"alinti": true` yazılır. O vakadan gelen eşleşmeler raporda görünür ama CI'ı durdurmaz. Bugün iki vaka böyledir:
`hata-sonrasi-defter-sorusu` ve `s02-strateji-yeni-baslayan`.

Denetim yalnızca kelime kopyasını yakalar; "fiyat 100 TL ise şunu yap" gibi bir vakaya özgü mantığı yakalayamaz. Bunun için
`etki-defteri.md`'deki "Gerekçe" sütunu kullanılır: gerekçe bir vaka adıysa düzeltmenin hangi başka hücrelere de uyduğu yazılır.

## Puan farkı ve harcama (2.10.0, yayın öncesi, ücretsiz)

```
claude plugin eval ./reklam-atolyesi --trust-plugin --runs 3 --threshold 0.8 --ablation with-without --json /tmp/yeni.json
python evals/kor_kiyas.py puan --eski /tmp/eski.json --yeni /tmp/yeni.json
```

`eski.json` önceki yayının aynı komutla alınmış çıktısıdır (yayın testinde saklanır; yoksa önceki sürümün etiketinden alınır). Yeni bir
koşu gerekmez.

- **Oynama payı:** eski sürümün kendi koşuları arasındaki en büyük puan farkı. Yeni ortalama eskisinden bu paydan fazla yüksekse
  "iyileşti", fazla düşükse "geriledi", aradaysa "fark yok" yazılır. Eski koşuların hepsi aynı puanı aldıysa oynama payı sıfırdır ve
  her fark sayılır. Gerileyen vaka varsa çıkış kodu 1 (sürüm durur).
- **Harcama:** JSON'daki harcama okunur, varsa vaka başına, yoksa yalnızca toplam. Yeni sürüm %20 ya da daha fazla harcıyorsa ve
  hiçbir vaka iyileşmediyse uyarı verilir. Uyarı sürümü durdurmaz (bazı kurallar bilerek harcama artırır), ama etki defterine
  gerekçe yazılır.
- JSON'da koşu puanı bulunamazsa betik bunu söyler. O zaman puanlar HTML rapordan okunur ve
  `{"puanlar": {"<vaka>": [0.8, 1.0, 1.0]}, "harcama_usd": 1.23}` biçiminde bir dosyaya yazılıp betiğe verilir.
- Kör karşılaştırma (aşağıda) aynen kalır. İkisi birlikte okunur: puan "fark yok" diyorsa hakemin tercihi etki defterine
  "yardım etti" olarak yazılmaz.

## Önceki sürümle kör karşılaştırma (2.8.0, yayın öncesi)

Eşiği geçmek yeni sürümün eskisinden iyi olduğunu göstermez. Yayından önce aynı vakalarda iki sürümün cevapları, hangisinin hangi
sürüm olduğu gizlenerek bir hakeme verilir:

```
python evals/kor_kiyas.py hazirla --eski <eski-cevaplar> --yeni <yeni-cevaplar> --out /tmp/kor
python evals/kor_kiyas.py hakem --dir /tmp/kor          # isteğe bağlı, ücretli; ya da hakem.md'leri elle değerlendirip karar.md yazın
python evals/kor_kiyas.py sonuc --dir /tmp/kor          # regresyon varsa çıkış kodu 1
```

Cevaplar `<vaka>/<n>.md` düzeninde bir klasör ya da `claude plugin eval --json` çıktısıdır (eski sürüm için önceki yayının
etiketinden ya da kurulu kopyasından aynı komutla alınır). JSON'dan cevap çıkarma en iyi çabadır: bulunamazsa betik söyler ve
cevaplar HTML rapordan klasör düzenine kaydedilir. "Eski daha iyi" çıkan her vaka regresyondur: değişiklik düzeltilir ya da geri
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
olup olmadığı, önceki sürüme göre kötüleşen ya da iyileşen imzalar. Kapsanmayan imza için iskelet yazılır.

Döngü: imza → iskelet doldurulur → vaka düzeltmeden **önce** kalmalı (hata yeniden üretildi) → düzeltme → vaka geçer, eski vakalar
bozulmaz (kör karşılaştırma) → `etki-defteri.md` → sonraki sürümün defterleri düzeltmenin sahada tuttuğunu gösterir. Araç hatası
imzaları model cevabıyla değil, `tests/` altında bir birim testiyle yeniden üretilir.

Hangi hücre nasıl çıkarılır: ürün P8 (katkı ≤ 0) → P4 (hizmet ya da aday) → P7 (katkı aralık) → P6 (katkı bilinmiyor) → P5
(sezon) → P1-3 (kayıttan ayrılamaz); kullanıcı U4 (birden çok profil) → U5 (CSV) → U6 (TRY dışı) → U3 (2. tur ve sonrası) → Ux
(U1/U2/U7/U8 bütçeye göreli, ayrılamaz). Bilinmeyen tahmin edilmez.

## Revizeye başlarken (2.10.0)

`python evals/etki_ozeti.py` çalıştırılır. Etki defterinden iki liste verir: en az iki sürümdür "etkisiz" olup hiç işe yaramamış
bileşenler (silmeye aday) ve üç sürümdür "ölçülecek" diye bekleyenler. Betik hiçbir şeyi silmez; karar admin'indir.

## Yeni vaka ya da senaryo ekleme

1. Gerekirse `senaryo-matrisi.json`'a ürün/kullanıcı ekleyin (`expect` alanıyla beklenen kapı sonucu).
2. Vaka için `eval_cases` altına `{product, user, rubric}` yazın.
3. `vakalar/<ad>/prompt.md` (durum + kullanıcının sözü) ve her rubrik ölçütü için `graders/<rN>-<ad>.md` (`type: llm`,
   `weight`, ölçüt kodu ve geçer/kalır tarifi) ekleyin.
4. `tests/test_v250_scenarios.py::test_matrix_and_eval_cases_are_consistent` matris, rubrik ve dosyaların birbirini tuttuğunu denetler;
   `tests/test_v2100_overfit.py` aynısını kapalı vakalar için yapar.
5. Kapalı vaka eklenecekse `kapali/<ad>/` altına ve matriste `kapali_cases`'e yazılır. Kapalı vakayı, o sürümde düzeltme yazmayan bir
   oturum yazar; yazıldıktan sonra düzeltme oturumlarında açılmaz.
