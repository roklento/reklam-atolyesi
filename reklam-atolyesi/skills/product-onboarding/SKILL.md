---
name: product-onboarding
description: "reklam-atolyesi S00c ürün tanışması — ürün gözlemi (foto/video), fiyat ve katkı, başa baş CPA, alıcılar ve satın alma anları, kanıtlanabilir iddialar, ürüne özgü çekim tarifi. Her yeni üründe."
---

# product-onboarding — S00c · Ürün tanışması (spec 17.7, 5.3, 6.2, bölüm 10)

## Amaç
Her yeni ürünü en fazla **7 soruyla** tanımak; ürün gözlemini, ekonomiyi, alıcıları ve satın alma anlarını, kanıtlanabilir iddiaları
ve ürüne özgü çekim tarifini kurmak. **Gerçek kampanyadan önce atlanamaz** (kullanıcı yalnızca bilerek deneme kampanyasında atlayabilir; o
zaman brief'e "ekonomi VARSAYIMSAL" yazılır ve `campaign_create(..., trial=True)`).

## Ön koşul
- Profil `active` ya da S00a onaylı (S00b'nin bitmesi beklenmez; Meta önerileri hazır olduğu soruda kullanılır).
- Fotoğraf/video istemeden önce yükleme öncesi izin kapısı (bölüm 10): görüntüde tanınabilir kişi varsa `person_consents` ve işleme
  dayanağı; yoksa kişisiz ürün görüntüsü istenir.

## Girdiler ve bağlam paketi
`memory_context(profile_id, "S00c")`; MCP yolunda katalog önerileri: `ads_catalog_list_catalogs`, `ads_catalog_list_products`
(ad, fiyat, görsel). Meta geçmişindeki ürün bilgisi (`history_summary`).

## Kullanılan hazır skill'ler ve OVERRIDES
Yok. Çekim tarifi kartlarının dili `ref-shooting-basics`'tedir.

## Adımlar
1. `product_upsert(profile_id, name)` (taslak) → `stage_start(profile_id, "S00c", scope_key="product:<product_id>")`.
2. **Ürün girdisi:** 1–3 fotoğraf ve varsa kısa video → `DD/profiles/<slug>/products/<ürün>/`. Claude görsellere bakar ve **ne
   gördüğünü söyler** (ürün türü, ambalaj, etiket, renk, doku, çeşitler); kullanıcı düzeltir. Doğrulanamayan (çeşit sayısı, belge
   gerektiren özellik) "teyit edilmedi" diye işaretlenir. → `product_upsert(observation_json={seen, corrected_by_user, unverified},
   photos_json=[…])`.
2b. **Hizmet mi? (1.5.0):** S00a'da hizmet dendiyse ya da kullanıcı söylerse `product_upsert(..., kind="service")`. Hizmette ürün
   gözlemi yerine **hizmetin yapıldığı yer ve an** gözlenir (mekân, ekipman, uygulayan kişi, süreç); fotoğraf/video yine istenir.
   Ek sorular: süre (`duration_min`), haftalık kapasite (`capacity_per_week`), randevu biçimi (`booking`: appointment · walk_in ·
   online · on_site · mixed), hizmet bölgesi (`area`: city, districts, radius_km, online), düzenlenen alan (`regulated_sector`), Meta özel
   reklam kategorisi (`special_ad_category`: housing · employment · financial_products_services ya da yok) ve kitlenin ülkeleri
   (`audience_regions`) → `product_upsert(service_json={…})` (sunucu doğrular; nota kişisel veri girmez). `service_info` özel kategori
   gerekliliğini resmi bölge listesinden söyler. Hizmette satış çoğu zaman **müşteri adayı** ile başlar: soru 3'e ek olarak **adaydan
   satışa dönüş oranı** sorulur ("10 kişi form doldurursa/ararsa kaçı müşteri olur?") → `economics_json.lead_close_rate` (0–1),
   kullanıcının kayıtlarından teyitliyse `lead_close_rate_confirmed: true`. Bilinmiyorsa boş kalır; ilk turdan sonra `lead_outcome_set`
   kayıtlarıyla gözlenen oran önerilir.
3. **Sorular:**

   | # | Soru | Biçim | Kayıt |
   |---|---|---|---|
   | 1 | Ürünün adı ve 1–3 fotoğrafı (varsa video) | Önerilen: katalogdan; dosya | `name`, `photos_json`, `catalog_product_id` |
   | 2 | Satış fiyatı | Önerilen: katalogdan | `price`, `currency` |
   | 3 | Reklam öncesi sipariş katkısı ya da onu hesaplayacak kalemler | Tam değer, aralık ya da "bilmiyorum"; ürün maliyeti, satıcının üstlendiği kargo, ödeme/pazaryeri komisyonu, paketleme, beklenen iade birlikte doğrulanır | `economics_json` (aşağıda) |
   | 4 | Ortalama sepet tutarı | Önerilen: satış verisinden; "bilmiyorum" | `aov` |
   | 5 | Kim alıyor, hangi an için? (iki parçalı tek soru) | İki çoklu seçim: **(a) alıcılar** — ürünü kim alıyor ya da kime alınıyor, reklam kime konuşabilir (2–4 öneri + diğer); **(b) satın alma anları** — ne zaman (3–5 öneri + diğer). İkisi de ürün gözleminden ve Meta geçmişinden çıkarılır. Alıcı bir kişi tipidir, an bir zamandır: aynı an farklı alıcılara, aynı alıcı farklı anlara düşebilir; seçenekleri bu farkla kur. Alıcı etiketi iç kayıttır, reklam metninde izleyiciye atfedilmez (`ref-legal-tr-meta` §8a) | `buyers_json` ve `occasions_json` (`[{code, label}]`); her alıcı `taxonomy_value_add(axis="buyer", code, label, status="active", user_said)`, her an `taxonomy_value_add(axis="moment", …)` |
   | 6 | Kanıtlayabildiğin özellikler | Gözlemden çıkarılan öneriler (malzeme, üretim yöntemi, ölçü, kullanım…) + diğer; her biri için "belgesi var mı" | `provable_claims_json=[{claim, evidence_kind, document_path?, needs_document, verified}]` |
   | 7 | Üretim veya stok sınırı var mı? | yok · haftada N adet · sezonluk | `capacity_limit` |

   Seçenekler sabit listeden değil **o ürünün gözleminden** üretilir (ilke 12). Her cevap `onboarding_save(profile_id, "product",
   product_id, question_key, answer, source, confirmed)`.
4. **Ekonomi (6.2):** `economics_json = {basis: "net_of_vat|gross", net_basket, variable_costs:{product, shipping, commission,
   packaging, expected_returns}, contribution?, contribution_low?, contribution_high?, confirmed: bool, source, scope_note}`.
   Aynı maliyet iki kez düşülmez; brüt marj bu kalemlerin hepsini içermiyorsa tek başına başa baş değildir. Sunucu `economics`
   alanında başa baş CPA (= katkı), başa baş ROAS (sepet/katkı) ve hedef CPA'yı (katkı × güvenlik payı, varsayılan 0,7) hesaplar.
   Katkı bilinmiyor/aralıksa sonuç varsayım/aralıktır; katkı ≤ 0 ise pozitif başa baş CPA üretilmez. Sonucu kullanıcıya bu dille söyle.
   **Aday ekonomisi (1.5.0):** `lead_close_rate` varsa başa baş aday maliyeti = katkı × dönüş oranı, hedef aday maliyeti = × güvenlik payı
   (`breakeven_cpl`, `target_cpl`); ikisi de teyitliyse `cpl_status: exact`, değilse varsayım. Örnek dil: "Satış başına katkın 900, 10
   adaydan 2'si müşteri oluyorsa bir aday en fazla 180 değerinde; hedefimiz 126'nın altı.".
5. **Ürüne özgü çekim tarifi (5.3):** sorular bitince ürün gözleminden **görüntü özelliğine göre** çekim riskleri çıkarılır (ışık
   yayan/çok parlak yüzey · yansıtıcı/şeffaf ambalaj · çok küçük ayrıntı/yazı · hareketli/akışkan/kısa ömürlü an · belirli ortamda
   anlam kazanan kullanım · kullanımla değişen görünüş). Her risk için genel kuralı uyarlayan kart **önerilen cevap** olarak
   gösterilir (soru sayılmaz). Kart alanları: `risk, what, phone, do, stop_when, success_check, overrides_rule, why`. Fotoğraf/videodan
   risk çıkarılamıyorsa kart üretilmez, genel kurallar geçerlidir. Onaylanınca `product_upsert(shoot_profile_json={"cards":[…]})`.
   **Hizmette çekim tarifi:** risk kartları hizmetin görüntüsüne göre: uygulayan kişi kameraya konuşuyor (ses niyeti "çekimdeki ses",
   konuşmalı kurgu), süreç adımları (eller, ekipman; kişi yüzü izinsiz görünmez), mekân güveni (temizlik, belge/sertifika görünürse
   gerçek olmalı), sonuç gösterimi (düzenlenen alanda önce/sonra ve müşteri görüntüsü §7'ye göre; sağlıkta resmi metin okunana kadar
   **kullanılmaz**). Müşteri yorumu yalnızca izinle (`review_add`).
6. Ürün kartını yaz: `DD/profiles/<slug>/products/<ürün>/urun-karti.md` (gözlem, ekonomi ve dili, alıcılar, anlar, iddialar, çekim
   tarifi; atomik).
7. `stage_complete(profile_id, "S00c", outputs=[{path: urun-karti.md}], summary, scope_key="product:<id>")` → `awaiting_gate`.

## Çıktılar
`products` (gözlem, ekonomi, alıcılar, anlar, iddialar, kapasite, çekim tarifi), `onboarding_answers`, `taxonomy_values` (buyer, moment), ürün kartı
dosyası; tercihler gözlemlenirse `memory_add(layer="preference", …)`; devam notu her cevaptan sonra.

## Kontroller
- En fazla 7 soru; katalog/Meta/gözlemden çıkarılabilen sorulmadı, önerildi.
- Alıcılar ve anlar ayrı kayıtlı (`buyers_json` / `occasions_json`); S03'te her keşif konsepti bu alıcılardan birine konuşur.
- İddiaların her biri belge durumu taşıyor; "en iyi/ilk/tek", sağlık, çevre, güvenlik türü iddialar belgesiz kanıtlanabilir
  listesine girmez (`ref-legal-tr-meta`).
- Ekonomi kesin değilse "VARSAYIM" ya da aralık dili kullanıldı.
- Kampanyaya özgü sorular (hedef tarih, test bütçesi, amaç, sonuç türü) burada sorulmadı; S01'de.

## Kapı mesajı
"Ürün: <ad> · gözlem: … (teyit edilmeyenler: …) · fiyat … · katkı … → başa baş CPA … / hedef CPA … (<kesin|varsayım|aralık>) ·
alıcılar: … · anlar: … · kanıtlanabilir iddialar: … · çekim tarifi: N kart (…). Onaylıyor musun, neyi düzeltelim?" → `gate_approve(...)`;
onaydan sonra ürün kampanyaya hazırdır.
