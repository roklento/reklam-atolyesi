---
name: ref-legal-tr-meta
description: "reklam-atolyesi yasal başvuru — Ticari Reklam Yönetmeliği (2026 değişikliği, karşılaştırmalı reklam), TTK haksız rekabet, iddia/fiyat/izin kuralları, Meta AI açıklaması, Meta platform kuralları kaynak protokolü (§7), Meta reklam standartları (§8), lisanslar."
---

# ref-legal-tr-meta — yasal kurallar ve kaynakları (spec bölüm 10, 9.1, 11)

**Sınır:** Bu skill izin/kanıt takibini ve kontrol listesini sağlar; hukuki görüş değildir. Otomatik kontrol (uzaklık, eşleşme) hukuki
uygunluk kanıtı sayılmaz; şüphede insan kararı ve gerekirse hukukçu görüşü gerekir. Her madde kaynağı ve kontrol tarihiyle verilir;
**"resmi metinle teyit edilmedi"** işaretli madde kesin zorunluluk diye sunulmaz. Kaynakların kontrol tarihi maddelerin yanında yazılıdır (en eskisi **2026-10-15**; son gözden geçirme 2026-10-30, 2.0.0).

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
- **Resmi** ([About AI info on ads created or edited with generative AI tools](https://www.facebook.com/business/help/1010479435004531);
  `ads_get_help_article` ile okundu 2026-10-30): Meta, kendi üretken AI araçlarıyla (arka plan/görüntü üretme, animasyon ekleme) ya da
  C2PA gibi meta verilerle algıladığı üçüncü taraf AI araçlarıyla oluşturulan/belirgin biçimde düzenlenen reklama **otomatik** "AI info"
  etiketi koyar; etiket çoğunlukla üç nokta → "Bu reklam hakkında" altındadır. Yayından önce reklam oluşturma akışında etiket
  çıkacağı mesajla bildirilir. Bazı bölgelerde (Avrupa bölgesi, Kaliforniya, New York, Hindistan, Tayvan) reklamveren kendisi beyan
  edebilir; Türkiye bu listede **yok**. Sosyal konu/seçim/siyaset reklamında gerçekçi AI medyası beyanı zorunludur
  ([About media created or edited with AI](https://www.facebook.com/business/help/1486382031937045)); plugin bu kategoride reklam
  hazırlamaz. Türkiye'de görünür açıklama yükümlülüğü Meta'dan değil Ticari Reklam Yönetmeliği'nden gelir (§1a, 18/8).
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
- **Yerel seslendirme (1.4.8; model kartları ve paket meta verisi okundu 20.10.2026):** EMA Lightning (kod ve ağırlıklar
  Apache-2.0: https://github.com/canberk7/ema-lightning, https://huggingface.co/canberkkkkkk/ema-lightning) ve VoxCPM2 (Apache-2.0,
  kartta "free for commercial use": https://huggingface.co/openbmb/VoxCPM2). Ses kütüphanesindeki sesler gerçek kişiye ait değildir
  (metin tarifinden tasarlanmış); kullanıcının ya da başkasının sesi klonlanmaz (1a, m. 11). Üretilen ses yapay zekâ içeriğidir:
  `.tts.json` `ai_generated: true` → bölüm 4 ve 1a'daki açıklama kuralları uygulanır. Ses tasarımı rastlantısal olduğundan bir sesin
  bilinen bir kişiye benzediği fark edilirse o ses kullanılmaz ve kütüphaneden çıkarılır.
- **Yerel yazıya dökme (1.4.8; lisans dosyaları ve model kartı okundu 21.10.2026):** Whisper (OpenAI, MIT:
  https://github.com/openai/whisper/blob/main/LICENSE; large-v3-turbo kartı MIT: https://huggingface.co/openai/whisper-large-v3-turbo),
  faster-whisper (SYSTRAN, MIT: https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE), CTranslate2 biçimli model kartı MIT:
  https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo. Ses bilgisayardan çıkmaz (çalışırken ağ kapalı). Döküm kişisel
  veri içerebilir (konuşan kişinin sözleri): yalnızca kampanya klasöründe tutulur, hafızaya yazılmaz; konuşan kişinin kullanım izni
  (`consent_add`) her zamanki gibi gerekir.
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
içerikte görünür açıklama · Meta reklam standartları (§8) uyarıları karara bağlandı · yazım ve Türkçe karakterler · yorum izinleri (satın alma doğrulaması dahil) ve kişi izinleri eşleşti · ses
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

| Kural (plugin'deki kullanımı) | Durum (kontrol tarihi her satırda; tarihsiz satır 2026-10-17) |
|---|---|
| 9:16 yazı güvenli alanı üst %14, alt %35, yanlar %6 (qc, compose, `checks.py safe`) | Yerel değer. Resmi sayfa yüzde vermiyor; kenarların boş bırakılmasını ve Ads Manager'daki güvenli alan kılavuzunun kullanılmasını öneriyor ([About text overlays and the safe zone](https://www.facebook.com/business/help/980593475366490)) |
| Açıklama metni (disclaimer) içeren 9:16 reklamda alttaki %40 boş (`checks.py safe`: `disclaimer.on` ya da `ai_share > 0`) | **Resmi** (aynı makale) |
| Uzun ekranlarda Meta görüntüyü yakınlaştırıp güvenli alan dışını kırpabilir; kritik öğe güvenli alanın rahatça içinde | **Resmi** (aynı makale) |
| Kreatif test aracında test bütçesi en fazla %20 (`exploration_share` üst sınırı 0,2) | **Resmi öneri** (sınır değil): Meta mevcut kampanya ya da set bütçesinin en fazla %20'sini önerir; yayında başka reklam yoksa test reklamları daha fazlasını alabilir ([Set up a creative test in Meta Ads Manager](https://www.facebook.com/business/help/1423851372208214); okundu 2026-10-29). 0,2 plugin'in yerel üst sınırıdır, aşılmaz. Sık duyulan "%20–30" ajans/araç önerisidir, Meta'ya ait değildir |
| Kreatif test aracı: 2–7 test reklamı; yalnızca "En yüksek hacim" (maliyet hedefi/teklif sınırı yok); başlayınca değiştirilemez; bütçe test reklamlarına eşit bölünür; sonuçta güven düzeyi verilmez; eski Advantage+ alışveriş kampanyalarıyla uyumsuz (`creative_test_tool_max` varsayılanı 7) | **Resmi** ([Set up a creative test in Meta Ads Manager](https://www.facebook.com/business/help/1423851372208214), [About creative testing for the Marketing API](https://www.facebook.com/business/help/1376764284076031); okundu 2026-10-29). Araçlar hesaplara kademeli açılabilir: hesabın Ads Manager ekranındaki sayı daha düşükse o girilir |
| Günlük bütçe artışı ≤ %20, aynı sette aynı gün tek büyük değişiklik (coach) | Yerel koruma kuralı (öğrenmeyi bozmamak için temkin; Meta'nın yayımladığı bir sınır değildir) |
| 3 sn izlenme reklam düzeyinde sayı olarak gelmez, `amount_spent / cost_per_video_view` ile türetilir (track) | **Resmi** (canlı `ads_get_field_context`) |
| Meta alan adları (`meta_fields.json`) | **Resmi** (canlı `ads_get_field_context`) |
| AI açıklama/etiket politikası (launch-pack) | Teyit edilmedi (bölüm 4) |
| Meta reklam standartları: kişisel özellikler, sansasyonel içerik, sağlık ve görünüm, önce/sonra (§8) | **Resmi** (yardım merkezi, bağlantılar §8'de) |
| Sektör kıyası (`ads_insights_industry_benchmark`) | **Resmi araç**; harcaması olmayan hesapta "veri yok" döner. Kıyas önsel değildir (bkz. track) |
| Advantage+ kitlede reklamı kimin göreceğini Meta'nın yapay zekası seçer (geçmiş dönüşümler, piksel verisi, önceki reklam etkileşimleri) (concepts, ref-creative-taxonomy) | **Resmi** ([About Advantage+ audience](https://www.facebook.com/business/help/273363992030035)) |
| Satış kampanyası raporu kitle segmentlerine dökülebilir: yeni kitle, etkileşime geçmiş kitle (reklam hesabı ayarlarında tanımlanır), mevcut müşteri; segmentler önce Reklam ayarları → Kitle segmentleri'nde tanımlanır; özellik her hesapta açık olmayabilir (huni aşaması teşhisi: coach, track, launch-pack) | **Resmi** ([Use audience segments to enable breakdown reporting](https://www.facebook.com/business/help/424052537147870), [Create audience segments](https://www.facebook.com/business/help/1212227546879178); okundu 2026-10-29). Bağlantıda döküm adı `user_segment_key` (kabul edildi, harcamalı hesapta değerle henüz sınanmadı) |
| Web sitesi özel hedef kitlesi: piksel ziyaretçileri en fazla 180 gün geriye (satın alma olayında 2 yıl); Meta birkaç yüz kişi olmadan kullanmamayı önerir (segment tanımı için; plugin kitleyi hedeflemeye eklemez) | **Resmi** ([Options to create a website custom audience](https://www.facebook.com/business/help/2539962959620307), [Troubleshoot website custom audience size](https://www.facebook.com/business/help/1523083297982009); okundu 2026-10-29) |
| Satış amacı sepete ekleme gibi başka bir olaya da optimize edilebilir; farkındalık ve trafik ayrı amaçlardır (huni aşaması kampanya amacını değiştirmez) | **Resmi** ([About the sales objective](https://www.facebook.com/business/help/672411877425804), [About the awareness objective](https://www.facebook.com/business/help/1629235777115312), [About the traffic objective](https://www.facebook.com/business/help/301780226847564); okundu 2026-10-29) |
| Reklam düzeyinde açılış sayfası görüntüleme (`landing_page_view`), içerik görüntüleme (`omni_view_content`), sepete ekleme (`omni_add_to_cart`), ödeme başlatma (`omni_initiated_checkout`), satın alma (`omni_purchase`) okunur | **Resmi** (canlı `ads_get_field_context`, 2026-10-29). Piksel olayı göndermiyorsa alan boş kalır, sıfır sayılmaz |
| TOFU/MOFU/BOFU terimleri Meta'ya ait değildir; plugin'de aşama mesaj hipotezidir, kitle değildir | Yerel tanım (pazarlama literatürü; Meta'nın karşılığı kitle segmentleridir ve aynı şey sayılmaz) |
| Kreatif yorgunluğunda Meta aynı görselin ya da videonun yakın tarihli bütün gösterimlerini sayar; yeni reklam için belirgin biçimde farklı görsel ya da video önerir (aynı videoya yalnızca yeni metin bu öneriyi karşılamaz) (concepts) | **Resmi** ([About creative fatigue recommendations in Meta Ads Manager](https://www.facebook.com/business/help/1346816142327858)) |
| Çok sayıda reklam ve reklam seti açıldığında sistem her biri hakkında daha az öğrenir (az bütçede az ama birbirinden farklı reklam) (strategy, concepts) | **Resmi** ([About the learning phase](https://www.facebook.com/business/help/112167992830700)) |
| Öğrenme aşamasından çıkmak için reklam setinde son büyük düzenlemeden sonraki haftada ~50 sonuç (optimizasyon olayı); ölçekleme seti günlük bütçesi ≥ 7 × hedef maliyet (coach 6a) | ~50 sonuç **resmi** ([About the learning phase](https://www.facebook.com/business/help/112167992830700), [About learning limited](https://www.facebook.com/business/help/269269737396981); okundu 2026-10-29); sayılan satış değil, seçilen optimizasyon olayıdır. 7 × hedef, bu sayıdan türetilen **yerel** eşiktir |
| Advantage+ kampanya bütçesinde (CBO) set başına en az/en fazla harcama limiti konabilir; Meta mümkün olan en az limiti önerir; en az limit hedef aralıktır, garanti değildir; ikisi birlikte önerilmez. CBO'ya yeni set eklemek ya da bir sette büyük düzenleme diğer setlerin öğrenmesini sıfırlamaz (plugin bugün CBO kullanmaz; değerlendirme için) | **Resmi** ([About ad set spend limits with Advantage+ campaign budget](https://www.facebook.com/business/help/454681230514942), [Significant edits and learning phase](https://www.facebook.com/business/help/316478108955072); okundu 2026-10-29) |
| "Mevcut gönderiyi kullan" ile oluşturulan reklam gönderinin beğeni, yorum ve paylaşımlarını taşır; yeni reklam olarak kopyalamak taşımaz (coach 6a, launch-pack) | Teyit edilmedi: yaygın uygulama; yardım merkezi metni `ads_get_help_article` ile okunup tabloya işlenecek |
| Aynı gönderi ölçekleme ve test setinde birlikte yayında kalmaz (coach 6a) | Yerel koruma kuralı (kendi kendisiyle yarışmayı önlemek için temkin; Meta'nın yayımladığı bir kural değildir) |
| Satışlar Events Manager'da veri kümesine CSV ile yüklenebilir; olay zamanı ve en az bir müşteri tanımlayıcısı gerekir, zaman sınırı vardır (brief, S00b 6b) | **Resmi** (geliştirici belgesi: [Offline events](https://developers.facebook.com/documentation/ads-commerce/conversions-api/offline-events), kontrol 2026-10-20). Müşteri e-posta/telefonu Meta'ya gider: KVKK dayanağı olmadan önerilmez; yüklemeyi insan yapar |
| Shopier panelinde Meta pikseli için alan var; Shopier CAPI desteği (brief) | Teyit edilmedi: yalnızca ikincil kaynaklar (kontrol 2026-10-20); Shopier'in kendi belgesinden ve kurulumdan sonra Events Manager'da Purchase görülerek doğrulanır |
| Meta satışı görmüyorsa satış optimizasyonu alıcıyı tanıyamaz; tıklamaya optimize edilen kampanya tıklayanı bulur (brief, sunucu kuralı) | Optimizasyonun olay sinyaline dayanması **resmi** genel ilkedir (Advantage+ kitle satırı); "Purchase görülmeden satış sonucu yok" plugin'in **yerel** kuralıdır |
| Reklam metni önerilen uzunluğu: birincil metin 125, başlık 40, açıklama 30 karakter; bu küçük ekranda görünen kısımdır, metin yerleşime ve cihaza göre kesilebilir (`checks.py copy`) | **Resmi** ([Lead ads tasarım önerileri](https://www.facebook.com/business/help/908491205873167); bağlantı açıklaması 25: [Audience Network özellikleri](https://www.facebook.com/business/help/488625428422195); görünen bağlantı 25: [Hedef bağlantılar](https://www.facebook.com/business/help/152143699744690); kontrol 2026-10-20). Reels/Stories için ayrı sayı yayımlanmamış (teyit edilmedi) |
| Mesaj hedefli kampanyada başlatılan konuşma sayısı (dm-sales, coach) | Bu bağlantıda ayrı alan yok: `results` kampanya hedefinin sonucudur; "Meta leads" (`onsite_conversion_lead_grouped`) form ve sohbet adaylarını sayar (**resmi**: canlı `ads_get_field_context`, 2026-10-20) |
| Meta A/B testleri okunabilir (`ads_experiment_list_tests`, `ads_experiment_abtest_get_test`) | Liste okuma iki hesapta hatasız (2026-10-20; çalışma yok). Test ayrıntısı ve sonuç okuma bir çalışma olmadan sınanamadı. Uygunluk denetimi (`ads_experiment_check_eligibility`) 1.5.0'da izin listesine eklendi: araç tanımı okundu, salt okuma (yazma yok); çalışma oluşturma araçları listede değil |
| A/B testi: tek değişken; en az 7 gün önerilir, en fazla 30 gün; deneyler aracında en fazla 5 kampanya; sürümlere aynı bütçe; kitle aynı anda çalışan başka kampanyalarla çakışmamalı; Meta kitleyi böler, kimse iki sürümü görmez (strategy, launch-pack) | **Resmi** ([Best practices for A/B testing](https://www.facebook.com/business/help/290009911394576), [About A/B testing](https://www.facebook.com/business/help/1738164643098669), [Create an A/B test in Experiments](https://www.facebook.com/business/help/3506622486044209); okundu 2026-10-21). Hücre başına ≥ 30 beklenen sonuç **yerel** eşiktir (Meta sayı vermez) |
| Özel reklam kategorisi (konut, istihdam, finansal ürün ve hizmetler): ABD'deki reklamveren ya da ABD, Kanada veya listelenen Avrupa bölgelerine gösterimde seçilir; hedefleme kısıtlanır; Türkiye listede yok (product-onboarding, launch-pack; `s_lead.SAC_REGIONS`) | **Resmi** ([About ads for housing, employment or financial products and services](https://www.facebook.com/business/help/399587795372584); okundu 2026-10-21) |
| Müşteri adayı alanları: `lead` (bağlı araçlar + Meta içi), `onsite_conversion_lead_grouped` (Meta içi form/sohbet), `cost_per_lead`; amaç OUTCOME_LEADS; optimizasyon LEAD_GENERATION, QUALITY_LEAD, QUALITY_CALL (brief, coach) | **Resmi** (canlı `ads_get_field_context`, 2026-10-21) |
| Anlık form: form türleri (daha fazla hacim, daha yüksek niyet, zengin içerik), en az bir soru, iletişim bilgisi önceden doldurulabilir, en fazla 100 kayıtlı form (launch-pack) | **Resmi** ([About lead ads with instant form](https://www.facebook.com/business/help/761812391313386); okundu 2026-10-21) |
| Anlık formda gizlilik politikası bağlantısı (launch-pack) | **Çelişkili resmi kaynak**: aynı yardım merkezinde biri "isteğe bağlı", biri "gerekli" diyor ([761812391313386](https://www.facebook.com/business/help/761812391313386), [1019886738092553](https://www.facebook.com/business/help/1019886738092553)). Sistem bağlantıyı her durumda ister (**yerel kural**; KVKK aydınlatma yükümlülüğü de gerektirir) |
| Sağlık hizmetlerinde reklam/tanıtım: Sağlık Hizmetlerinde Tanıtım ve Bilgilendirme Faaliyetleri Hakkında Yönetmelik (RG 29.07.2023, sayı 32263) (product-onboarding, concepts, organic) | **Teyit edilmedi**: Resmî Gazete ve mevzuat.gov.tr bu ortamdan açılamadı (2026-10-21); bilgi ikincil kaynaklardan. Resmi metin okunana kadar sağlık hizmetinde **güvenli varsayılan**: önce/sonra görseli, hasta/ameliyat görüntüsü, fiyat-indirim-kampanya, sonuç garantisi ve hasta yorumu kullanılmaz; bu bir yasa özeti değil, temkin kuralıdır. Okunduğunda bu satır güncellenir |
| Birbirine çok benzeyen reklamlar tek varlık gibi gruplanıp aynı kişilere gider (Andromeda) | Teyit edilmedi: üçüncü taraf kaynaklarda geçer, yardım merkezinde bulunamadı; Meta'nın Andromeda mühendislik yazısı ([2024-12-02](https://engineering.fb.com/2024/12/02/production-engineering/meta-andromeda-advantage-automation-next-gen-personalized-ads-retri)) da bunu söylemiyor (kontrol 2026-10-29). Resmi olan yakın bilgi: "kreatif çeşitliliği" metriği setteki görselleri ve video kapaklarını benzerlik için karşılaştırır ([Creative diversity](https://www.facebook.com/business/help/2371176336684086)). S03'teki "keşifte her konsept farklı alıcıya, tek test açılışıyla" kuralı (1.4.5) bu yüzden **yerel koruma kuralıdır** |

## 8. Meta reklam standartları — metin, görüntü ve hook (resmi; kontrol: 2026-10-17)
Kaynak: [About Meta advertising standards](https://www.facebook.com/business/help/488043719226449). Tam liste Meta Şeffaflık Merkezi'ndedir.
Bu bölüm plugin'in ürettiği reklamlarla ilgili dört başlığı özetler. Bağlayıcı olan resmi metindir: şüphede §7'deki protokolle yeniden
okunur. Türkçe örnekler plugin'in uyarlamasıdır; resmi örnekler İngilizcedir. Bu kurallar ürün kategorisinden bağımsız olarak her
reklamda uygulanır; marka ya da ürün adı içermez.

### 8a. Kişisel özellikler ([politika](https://www.facebook.com/business/help/2557868957763449))
- Reklam, izleyicinin kişisel özelliğini **iddia edemez ve ima edemez**; soru biçiminde ima da yasaktır. Liste: ırk, etnik köken, renk,
  ulusal köken, din, yaş, cinsiyet, cinsel yönelim, cinsiyet kimliği, aile durumu, engellilik, tıbbi ya da genetik durum, fiziksel ya da
  ruh sağlığı, kırılgan maddi durum, oy durumu, sendika üyeliği, sabıka kaydı, ad.
- "Sen/siz" kullanılabilir; yasak olan, izleyicide bu özelliğin olduğunu varsaymaktır.
- **Soru (1.9.0):** izleyiciye soru sormak serbesttir; yasak olan, yukarıdaki listeden bir özelliği izleyicide varsayan sorudur. ✓ "Hediye
  seçmek zor mu geliyor?", "Kargo ne kadar sürer diye düşünüyor musun?" · ✗ "Kilo mu aldın?". Plugin'in önceki "… misin? hiç yok"
  yönergesi Meta'dan sıkı yerel kuraldı; 1.9.0'da bu listeye daraltıldı. `checks.py meta-text` yalnızca özellik + ikinci şahıs birlikteliğini
  işaretler (uyarıdır, karar değildir).
- Mahremiyet: kişisel bilgi (kimlik, iletişim, adres, finansal, tıbbi) reklamda paylaşılmaz ve istenmez.
- Türkçe örnekler: ✗ "Kilo mu aldın?", "Diyabetin varsa…", "Borç batağında mısın?", "40'ını geçtin mi?", "Yeni mi evlendin?" ·
  ✓ ürünün faydasını anlatan ya da ürün/an odaklı ifade ("Akşamları evi ısıtan yün battaniye", "Yeni ev hediyesi").

### 8b. Sansasyonel içerik ([politika](https://www.facebook.com/business/help/304110064285796))
- Dikkat çekmek için şok edici ya da korkutucu taktik kullanılamaz.
- Görüntüde yok: şiddet, yaralanma, kan; kaza ya da suç sahnesi; ölüm ya da hayati tehlike; çürüme; vücut atığı; grafik hijyen/bakım
  ayrıntısı (ör. sivilce sıkma); hayvana eziyet; izleyiciye doğrultulmuş ya da kullanıma hazırlanan silah.
- Hook kuralı: ilk saniyelerin durdurma etkisi şok, korku ya da tehlike imasıyla kurulmaz (ör. yangın/kaza çağrıştıran açılış, alarm sesi
  ve korku metni). Görsel merak, süreç, sonuç ve ürün anı kullanılır.

### 8c. Sağlık ve iyi oluş, kişisel sağlık ve görünüm ([politika](https://www.facebook.com/business/help/2489235377779939))
- Diyet, kilo ya da sağlık ürünü tanıtmak için **olumsuz öz algı** yaratılamaz.
- Kilo verme/alma ürün ve hizmetleri: belirli vücut bölgesinde sıkıştırılmış yağ yakın planı yok; sonucun yalnızca giyilebilir ürünle
  elde edildiği iddiası yok.
- Kilo ya da kozmetik ürün/işlem: görünümü, vücut bölgesini ya da hijyeni aşağılayan ifade veya soru yok.
- Kalıcı cilt rengi değişikliği yapan beyazlatma ürünleri tanıtılamaz.
- Tedavisi olmayan hastalıkları (diyabet, herpes, tiroid, sedef, ebola, kanser, otizm, Alzheimer, Parkinson, ALS, HIV) iyileştirme ya da
  ortadan kaldırma iddiası yok; sağlık profesyoneli ağzından da yok. Belirti yönetimi iddiası bu yasağın dışındadır.
- Sağlık ya da kilo bağlamında tıklama tuzağı yok: abartılı/uç iddia ya da açıklama/koşul olmadan "belirli sürede belirli sonuç" vaadi.
- Yalnızca 18 yaş ve üzeri hedeflemeyle: diyet ürünleri (kullanım, etki ve sonuç süresi gösterilebilir), kozmetik işlem ve ameliyatlar,
  genel kozmetik ürün/işlemlerde önce/sonra dönüşümü.

### 8d. Önce/sonra sahnesi — kategori uyarısı
Meta önce/sonrayı genel olarak yasaklamaz; kural ürün kategorisine bağlıdır. Bazı ikincil kaynaklar "Facebook önce/sonrayı yasaklar" der;
resmi metin kategoriye göre kısıt koyar.

| Ürün kategorisi | Meta kuralı (8c) |
|---|---|
| Sağlık, kilo ve kozmetik dışı (ev, dekor, temizlik, onarım, el işi…) | Bu politikanın kapsamı dışında. TR hukukuna göre sahne gerçekten çekilir (§3) |
| Genel kozmetik ürün ya da işlem | Yalnızca 18+ hedeflemeyle; görünümü aşağılayan ifade yok |
| Kilo verme/alma | 18+; sıkıştırılmış yağ yakın planı yok; olumsuz öz algı yok; koşulsuz süre vaadi yok |
| Kalıcı cilt beyazlatma | Tanıtılamaz |
| Sağlık iddiası taşıyan ürün | 8c'deki hastalık ve tıklama tuzağı kuralları; TR'de sağlık beyanı ayrıca belge ister (§3) |

### 8e. Uygulama
- **S03 konsept:** hook ve metin 8a–8c'ye göre yazılır; `PY PR/scripts/qc/checks.py meta-text --text <taslak.txt>` ön taraması.
  `proof=before_after` seçilirse ürün kategorisi 8d'ye göre işaretlenir; 18+ gerekiyorsa not S14'e taşınır.
- **S04 çekim planı:** önce/sonra çekimi 8d'ye göre; kozmetik ve kilo kategorisinde yakın plan ve kadraj kuralı karta yazılır.
- **S10 kurgu (1.8.0):** `BeforeAfter` bileşeninde kategori `category` prop'una yazılır (general · cosmetic · weight · health_claim ·
  skin_whitening); plan doğrulaması cilt beyazlatmayı, AI kaynağı, konseptte before_after seçilmemesini ve sağlık hizmeti sektörünü
  reddeder; kozmetik/kilo için 18+ notu verir. Önce/sonra kaynaklarına renk eşitleme uygulanmaz (fark kanıtın kendisidir).
- **S13 QC:** `checks.py meta-text --plan <plan.json>` ekrandaki her yazıyı tarar. Tarama kelime/kalıp tabanlı bir **uyarıdır, karar
  değildir**: her uyarı gözle incelenip "sorun yok" ya da "düzelt" diye kayda geçer. Görüntüdeki sansasyonel öğe (8b) ve önce/sonra
  kategorisi (8d) kontak sayfasından gözle denetlenir.
- **S14 yayın paketi:** birincil metin, başlık ve açıklama `checks.py meta-text --text` ile taranır; 18+ hedefleme gerekiyorsa kurulum
  talimatına yazılır.
- Kurallar §7 protokolüyle 30 günde bir yeniden kontrol edilir; resmi metin değişmişse bu bölüm bir sonraki sürümde güncellenir.
