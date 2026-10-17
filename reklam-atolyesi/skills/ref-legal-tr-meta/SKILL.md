---
name: ref-legal-tr-meta
description: "reklam-atolyesi yasal başvuru — Ticari Reklam Yönetmeliği (2026 değişikliği, karşılaştırmalı reklam), TTK haksız rekabet, iddia/fiyat/izin kuralları, Meta AI açıklaması, Meta platform kuralları kaynak protokolü (§7), lisanslar."
---

# ref-legal-tr-meta — yasal kurallar ve kaynakları (spec bölüm 10, 9.1, 11)

**Sınır:** Bu skill izin/kanıt takibini ve kontrol listesini sağlar; hukuki görüş değildir. Otomatik kontrol (uzaklık, eşleşme) hukuki
uygunluk kanıtı sayılmaz; şüphede insan kararı ve gerekirse hukukçu görüşü gerekir. Her madde kaynağı ve kontrol tarihiyle verilir;
**"resmi metinle teyit edilmedi"** işaretli madde kesin zorunluluk diye sunulmaz. Kaynakların kontrol tarihi: **2026-10-15** (kurulum).

## 1. Türkiye — Ticari Reklam ve Haksız Ticari Uygulamalar Yönetmeliği
Esas metin: RG 10.01.2015, sayı 29232 (6502 sayılı Kanun m. 61–63, 84'e dayanır).

### 1a. 2026 değişikliği — RG 01.07.2026, sayı 33297; **yürürlük 01.08.2026** (resmi metin okundu:
https://www.resmigazete.gov.tr/eskiler/2026/07/20260701-9.htm)
- **AI / dijital karakter açıklaması (m. 6 → yönetmeliğin 18. maddesine 8. fıkra):** reklamda yapay zekâ ya da yazılımla üretilen veya
  insandan ayırt edilemeyen dijital karakter kullanılırsa bu durum **açık ve ayırt edilebilir** biçimde belirtilir.
  → Plugin: AI ile insan üretilmez (yüz ve eller gerçek çekimden); ayırt edilmesi zor AI içerik varsa görünür açıklama talimatı (S14).
- **Gerçek kişinin AI kopyasıyla tavsiye yasağı (m. 11 → 27. maddeye 12. fıkra):** gerçek bir kişinin yapay zekâ ile üretilmiş dijital
  kopyası kullanılarak o kişinin ürünü deneyimlediği/tavsiye ettiği izlenimi verilemez. → Ses klonu yok (kullanıcının sesi dahil);
  kişinin AI kopyası yok.
- **Değerlendirmeler (m. 12 → 28/B):** reklamda yalnızca **satın alması doğrulanmış** tüketici değerlendirmeleri kullanılabilir;
  doğrulanmamış değerlendirme kullanılamaz; yanıltıcı değerlendirme/onay için anlaşma yapılamaz. → `reviews` kaydı: gerçek yorum,
  satın alma doğrulaması (`source` alanında sipariş/kanal bilgisi + kanıt dosyasında) ve kullanım izni kanıtı (`consent_type`,
  `consent_evidence_path`); kanıt yoksa ya da `withdrawn_at` doluysa
  kreatif **reddedilir**. Sahte/uydurma yorum yasak.
- **İndirim öncesi fiyat (m. 4 → 14. madde):** indirim duyurusunda indirim öncesi fiyat, indirimden önceki **10 gün içindeki en düşük
  fiyattır** (istisnalar resmi metinde). → Çizili fiyat/indirim oranı yalnızca fiyat geçmişi kanıtıyla; sayfadaki fiyatla eşleşmek
  tek başına indirim iddiasını doğrulamaz (`PriceTag.referencePriceVerified`).
- **Çevresel beyanlar (m. 5 → 17. madde):** çevreyle ilgili beyanlar belgeli olmalı. → Çevre iddiası belgesiz kullanılmaz.
- Ayrıca: 23/A (sosyal medya etkileyicisi), 25/A (hedefli reklam) — plugin kreatifi bu kapsamda bir iş ortaklığı içeriyorsa kullanıcıya
  bildirilir; ayrıntı resmi metinden okunur.

### 1b. Karşılaştırmalı reklam — yönetmeliğin 8. maddesi (değişiklik: RG 04.01.2017, sayı 29938; resmi metin okundu,
TÜRMOB RG arşivi kopyası: https://www.turmob.org.tr/arsiv/mbs/resmigazete/29938-29938-1.pdf)
- 8/1-(c): karşılaştırılan mal veya hizmetler **aynı ihtiyaçları karşılamalı ya da aynı amaca yönelik** olmalı.
- 8/1-(h): **Reklam Kurulunca belirlenen ilkelere aykırı olmamalı.**
- 8/2'ye eklenen cümle: doğrudan karşılaştırmalı reklamlarda herhangi bir kişi veya kurumun **tanıklığına yer verilemez**.
- 8/3: gıda reklamlarında sağlık beyanı kapsamındaki hususlar karşılaştırılamaz; takviye edici gıdanın karşılaştırmalı reklamı yapılamaz.
- 8/4: fiyat düzenlemesine/etkin piyasa gücü yükümlülüğüne tabi sektörlerde fiyat karşılaştırması yapılamaz.
- **Madde 9 (ispat):** reklamveren iddialarının doğruluğunu ispatla yükümlüdür; karşılaştırmaya konu iddialar **her hâlükârda**
  üniversitelerin ilgili bölümlerinden ya da akredite/bağımsız araştırma-test kuruluşlarından alınmış belgelerle, reklamın yayınlandığı
  dönemi kapsayacak biçimde kanıtlanır.
- **Resmi metinle teyit edilmedi:** 8/1'in diğer bentleri (objektif/ölçülebilir özellik, kötülememe, karıştırmama vb.) ve rakip
  markasına doğrudan yer verilmesine ilişkin hükmün güncel durumu — ikincil kaynaklar bu hükmün uygulamasının ertelendiğini ve
  28.12.2018'de yürürlükten kaldırıldığını aktarır (ör. [alomaliye](https://www.alomaliye.com/2018/12/28/ticari-reklam-ve-haksiz-ticari-uygulama/));
  güncel konsolide metin mevzuat.gov.tr'den okunmadan kesin sayılmaz.
- **Plugin varsayılanı: rakip anılmaz.** Kreatifte rakibin adı, logosu, ürünü, tanınır ambalajı ya da reklamına gönderme yoktur.
  Kullanıcı açıkça karşılaştırmalı reklam isterse: aynı ihtiyaç/amaç, kanıtlanabilir özellik, madde 9 belgesi, kötüleme ve karıştırma yok,
  tanıklık yok — **ayrı bir onay kapısıyla** (`decision_log(decision="comparative_ad_approved", note=<belgeler>)`) ve belgeyle ilerlenir.

## 2. Haksız rekabet — 6102 sayılı TTK m. 54–55 (resmi metin okundu; mevzuat.gov.tr TTK PDF)
- m. 54: haksız rekabetin amacı ve genel ilke — rakipler arasında ya da tedarikçi/müşteri ilişkilerinde aldatıcı veya dürüstlük kuralına
  aykırı davranış ve uygulamalar haksızdır.
- m. 55(1)(a): **1** başkalarını, mallarını, iş ürünlerini, fiyatlarını ve faaliyetlerini yanlış, yanıltıcı veya gereksiz yere incitici
  açıklamalarla **kötülemek**; **4** başkasının malları, iş ürünleri, faaliyetleri veya işletmesiyle **karıştırılmaya yol açan** önlemler
  almak; **5** kendisini, mallarını, fiyatlarını vb. başkalarınınkiyle **gerçeğe aykırı, yanıltıcı, gereksiz yere kötüleyici ya da
  tanınmışlıktan yararlanacak biçimde karşılaştırmak**.
- → **Taklit yok:** rakibin sloganı, görsel kimliği, karakteri, jingle'ı, özgün kurgusu ya da ambalaj görünümü taklit edilmez; karıştırılma
  tehlikesi yaratan benzerlik kurulmaz (ayrıca FSEK).
- → **Uzaklık kuralı:** rakipten türeyen (`proven | counter`) konsept kaynak rakip konseptinden ortak sözlükte açı dışında en az iki eksende
  farklı; hook/metin kaynak rakip metnine yakın değil (`concept_distance_check`: normalize metinde 4-gram örtüşmesi ≤ %20). QC yan yana kontrol eder.
- → **Rakibin iddiası bizim iddiamız değildir:** yalnızca bizim `provable_claims_json` listemizde varsa kullanılır.
- → **Rakip varlığı üretime girmez:** önizlemeler ve kullanıcının getirdiği rakip görselleri yalnızca analiz önbelleğinde.

## 3. İddialar, fiyat, kişiler, yorumlar (bölüm 10)
- **İddialar:** yalnızca `products.provable_claims_json`'daki kanıtlanabilir iddialar. Belge gerektirenler: genel üstünlük ("en iyi",
  "ilk", "tek", "en çok satan"), sağlık, güvenlik, çevre, içerik/bileşim, performans/ölçü sayıları, karşılaştırma, garanti/teslim süresi
  taahhüdü. Karşılaştırma ya da zamanla değişim iddiası taşıyan sahne (önce/sonra) **gerçekten çekilir**.
- **Fiyat/indirim:** satış sayfasıyla birebir; indirimde 1a'daki referans fiyat kuralı ve fiyat geçmişi kanıtı.
- **Görüntü ve ses izni:** tanınabilir her kişi (çekimci, kurucu, müşteri) için `person_consents` (açık rıza, kapsam görüntü/ses, tarih,
  kanıt). İzin yoksa/geri çekildiyse klip kullanılamaz.
- **KVKK ve yükleme öncesi izin kapısı:** kişisel veri içeren dosya Claude'a, ElevenLabs'e ya da başka sağlayıcıya gönderilmeden önce
  amaç, alıcı sağlayıcı, işleme ve saklama kapsamı ile işletmenin işleme/yurt dışı aktarım dayanağı doğrulanır
  (`processing_permission_check`). Reklamda gösterim izni sağlayıcıya yükleme/yurt dışı aktarım izniyle eş tutulmaz. Kaynak:
  https://www.kvkk.gov.tr/Icerik/2053/Yurtdisina-Aktarim (resmi kurum sayfası; ayrıntı ve güncel usul oradan okunur).
- **Geri çekme:** `review_withdraw`/`consent_withdraw` varlık → plan → kreatif → reklam bağlarını tarar; yayındaki reklam için insana
  durdurma/değiştirme adımı; plugin Meta'ya yazmaz.
- **Kullanım güvenliği:** gerekiyorsa ürün sayfasına/ambalaja kısa kullanım notu önerisi.

## 4. Meta — AI açıklaması
- Kural: AI kullanımı kanıt zincirinde (`provenance.ai_share`, `generations`) tutulur; S14, güncel reklam türünde **Ads Manager'ın
  sunduğu** açıklama/etiket seçeneğine göre insanın uygulayacağı talimatı verir. Otomatik platform etiketi ile reklamverenin beyanı aynı
  sayılmaz; "bütün açıklanmamış AI reklamları otomatik reddedilir" iddiası yapılmaz.
- Resmi kaynak: https://about.fb.com/news/2025/02/gen-ai-transparency-metas-ads-products/ — **bu kurulumda resmi metin ayrıca
  okunamadı; politika ayrıntıları yalnızca ikincil kaynaklardan derlendi ve "resmi metinle teyit edilmedi"** (ör.
  [contentgrip](https://www.contentgrip.com/meta-ai-ad-labels/) ve benzeri sektör yazıları).
  İlk gerçek AI içerikli yayında Ads Manager ekranındaki güncel seçenek esas alınır ve kontrol tarihiyle buraya değil sistem hafızasına
  (`memory_add(profile_id=None, kind="policy_check")`) yazılır.

## 5. Lisanslar
- **ElevenLabs — Eleven Music (model koşulları; resmi sayfa okundu, son güncelleme 09.10.2026:
  https://elevenlabs.io/eleven-music-model-specific-terms):** ticari kullanım plana bağlıdır; Free–Enterprise Music Lite planlarında
  çevrimiçi/çevrimdışı ticari kullanım film, TV, radyo ve stüdyo oyunları **dışında** izinli; Free/Starter/Creator/Pro **yalnızca
  bireysel** kullanım; Scale ≤ 10, Business ≤ 50 çalışanlı kuruluş; Free planda atıf zorunlu ve indirme yok; müzik kütüphanesi
  oluşturma/dağıtma ve model yeniden satışı yasak; sanatçı/şarkı/plak şirketi adlarıyla prompt ve sanatçı sesi taklidi yasak; çıktıyı
  kullanmadan önce hak temizliği kullanıcının sorumluluğu. → Her müzik üretiminde `approval_scope.license = {source: <URL>,
  checked_at, scope: "<plan, kuruluş büyüklüğü, kullanım: online reklam>"}`; uygunluk belirsizse üretim durur.
- **ElevenLabs diğer modeller (TTS, SFX, görsel/video):** kullanılacak model/özellik ve abonelik için ticari kullanım koşulu üretimden önce
  hesabın plan sayfasından/sağlayıcı koşullarından okunur; ücretli abonelik tek başına bütün modeller için hak kanıtı değildir; beta
  çıktıları kullanılmaz.
- **Remotion (resmi SSS okundu: https://www.remotion.dev/docs/license/faq):** ücretsiz lisans en fazla 3 kişilik ekip/kuruluş için
  (ticari kullanım dahil); daha büyük kuruluşlar Şirket Lisansı gerektirir. Bitmiş video teslimi müşterinin çalışan sayısını lisans
  kapsamına katmaz; render yazılımının müşteriye verilmesi ayrı değerlendirilir. Kodla otomatik render (renderMedia) "Remotion for
  Automators" kapsamındadır (render başına ücret, aylık asgari); ücretsiz lisans sahipleri otomasyon yapabilir. → İlk açılışta kullanıcının
  kuruluş büyüklüğüne göre uygunluk sorulur ve sistem hafızasına kaydedilir; marka sayısı lisansı belirlemez.
- **Fontlar ve medya:** lisans dosya bazında korunur; vendor skill'lerin dağıtım hakkı `PR/vendor-skills/THIRD_PARTY_NOTICES.md`.
- **Instagram trend müzikleri** reklamda kullanılmaz.

## 6. Teslimat öncesi son kontrol listesi (S13)
Yazılar güvenli alanda ve ≥ 1,5 sn · ses -14 LUFS, telefon hoparlöründe VO net · AI klipleri gerçek fotoğrafla karşılaştırıldı, bozulma
yok · iddia listesi kontrol edildi · AI içeren varyasyonlarda Meta açıklama/etiket talimatı güncel kurala uygun · ayırt edilmesi zor AI
içerikte görünür açıklama · yazım ve Türkçe karakterler · yorum izinleri (satın alma doğrulaması dahil) ve kişi izinleri eşleşti · ses
kararları uygulandı · rakipten türeyen konseptler uzaklık kuralını geçti; kreatifte rakip adı, logosu ya da varlığı yok.

## 7. Meta platform kuralları — kaynak protokolü (1.4.2)
Meta'nın platformuna dair her sayı, sınır ya da politika (format ve güvenli alan, kreatif test aracı sınırları, öğrenme ve bütçe
davranışı, AI etiketi, alan adları) kullanıcıya söylenmeden ya da hesaba katılmadan önce **durumu** bellidir:
- **Resmi:** bu oturumda resmi kaynaktan okundu: `ads_get_help_article(search_query)` (Meta yardım merkezi) ya da canlı araç
  (`ads_get_field_context`, hesabın Ads Manager ekranı). Kullanıcıya makale başlığı ve bağlantısıyla söylenir.
- **Yerel koruma kuralı:** plugin'in kendi temkinli tercihidir; "Meta kuralı" diye sunulmaz.
- **Teyit edilmedi:** yalnızca ikincil kaynak ya da eski bilgi; kesin zorunluluk ya da sınır diye sunulmaz.

Uygulama:
1. Aşama bir Meta kuralına dayanıyorsa önce sistem hafızasındaki kayda bakılır (`memory_search("<konu> meta", profile_id=None, layer="semantic")`; `kind="policy_check"` olan öğeler);
   30 günden eski ya da hiç yoksa `ads_get_help_article` ile kontrol edilir. Araç kavram, politika, özellik ve teknik şart içindir;
   performans ya da teklif önerisi için kullanılmaz (aracın kendi kuralı).
2. Okunan resmi bilgi kontrol tarihiyle yazılır: `memory_add(layer="semantic", kind="policy_check", source="data", profile_id=None,
   content="<kural> — <makale başlığı> <bağlantı> (kontrol: <tarih>)", tags=["meta", "<konu>"])`.
3. Araç ilgili makale döndürmezse durum "teyit edilmedi" kalır; sayı uydurulmaz, yakın bir makaleden çıkarım yapılmaz.
4. Resmi bilgi aşağıdaki tablodaki yerel değerle çelişirse resmi olan uygulanır ve tablo bir sonraki sürümde düzeltilmek üzere
   kullanıcıya bildirilir.

| Kural (plugin'deki kullanımı) | Durum (kontrol: 2026-10-17) |
|---|---|
| 9:16 yazı güvenli alanı üst %14, alt %35, yanlar %6 (qc, compose, `checks.py safe`) | Yerel değer. Resmi sayfa yüzde vermiyor; kenarların boş bırakılmasını ve Ads Manager'daki güvenli alan kılavuzunun kullanılmasını öneriyor ([About text overlays and the safe zone](https://www.facebook.com/business/help/980593475366490)) |
| Açıklama metni (disclaimer) içeren 9:16 reklamda alttaki %40 boş (`checks.py safe`: `disclaimer.on` ya da `ai_share > 0`) | **Resmi** (aynı makale) |
| Uzun ekranlarda Meta görüntüyü yakınlaştırıp güvenli alan dışını kırpabilir; kritik öğe güvenli alanın rahatça içinde | **Resmi** (aynı makale) |
| Kreatif test aracında test bütçesi ~%20 (`exploration_share` üst sınırı 0,2) | Teyit edilmedi: üçüncü taraf kaynaklarda Meta'nın **önerisi** olarak geçer, sınır değil. 0,2 plugin'in yerel üst sınırıdır |
| Kreatif test aracında reklam sayısı (2–5; bazı hesaplarda 10 bildiriliyor) | Teyit edilmedi; hesabın Ads Manager ekranından okunur |
| Günlük bütçe artışı ≤ %20, aynı sette aynı gün tek büyük değişiklik (coach) | Yerel koruma kuralı (öğrenmeyi bozmamak için temkin; Meta'nın yayımladığı bir sınır değildir) |
| 3 sn izlenme reklam düzeyinde sayı olarak gelmez, `amount_spent / cost_per_video_view` ile türetilir (track) | **Resmi** (canlı `ads_get_field_context`) |
| Meta alan adları (`meta_fields.json`) | **Resmi** (canlı `ads_get_field_context`) |
| AI açıklama/etiket politikası (launch-pack) | Teyit edilmedi (bölüm 4) |
| Sektör kıyası (`ads_insights_industry_benchmark`) | **Resmi araç**; harcaması olmayan hesapta "veri yok" döner. Kıyas önsel değildir (bkz. track) |
