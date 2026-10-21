---
name: brief
description: "reklam-atolyesi S01 brief — kampanya amacı, sonuç türü, sezon/hedef tarih, reklam seti günlük bütçesi ve toplam Meta harcama sınırı; brief.md. Yeni tur da buradan başlar."
---

# brief — S01 · Brief (spec 4.1, 6.2, 6.3, 17.9)

## Amaç
Kampanyanın (ya da yeni turun) çerçevesini kurmak: ürün, amaç, **sonuç türü**, sezon ve hedef tarih, reklam seti günlük bütçesi,
**toplam Meta harcama sınırı** (`budget_total`) ve varsayımlar. Brief S01b, S02 ve sonraki bütün aşamaların girdisidir.

## Ön koşul
- Profil `active`; ürün tanışması (`products.onboarding_status = done`) tamam. Değilse önce `product-onboarding`. Yalnızca deneme
  kampanyasında kullanıcı bilerek atlayabilir: `campaign_create(..., trial=True)` ve brief'e "ekonomi VARSAYIMSAL".
- Yeni kampanya: `campaign_create(profile_id, product_id, name, goal?, result_type?, season?, budget_total?, budget_total_confirmed?,
  mode="full")` → kampanya S01'de, tur 1 açılır; `session_bind(session_id, profile_id, campaign_id, cycle_id, stage="S01")`.
- Yeni tur (S17 sonrası): S17'nin brief taslağı bağlam paketinde gelir; kampanya kimliği aynı, `cycle_id` yeni turdur.

## Girdiler ve bağlam paketi
`memory_context(profile_id, "S01", campaign_id, cycle_id)` (profil özeti, ürün, kampanya, önceki turun brief taslağı, aktif playbook,
açık hipotezler, ekonomi). Ürünün `economics` alanı (`product_list`), `benchmarks_get`, `history_summary`.

## Kullanılan hazır skill'ler ve OVERRIDES
Yok.

## Adımlar
1. `stage_start(profile_id, "S01", campaign_id, cycle_id)`.
2. **Sorular** (yalnızca bilinmeyenler; seçenekli; önceki turdan bilinen değer önerilen cevap olarak):
   - Kampanya amacı (Meta kampanya amacı; geçmişte kullanılan amaçlar önerilir) → `campaign_update(goal)`.
   - **Sonuç türü** (`purchase · lead · messaging · profile_visit · link_click · engagement`; amaçtan önerilir) → `campaign_update(result_type)`.
     Satış dışı sonucun parasal değeri doğrulanmadıysa hedef maliyet kullanıcı hedefidir; başa baş diye sunulmaz.
     **Müşteri adayı (`lead`, 1.5.0)** hizmet, kurumsal/toptan ve yüksek tutarlı ürünlerde önerilir; yol zorunludur (`lead_method`):
     `instant_form` (Meta anlık form; piksel gerekmez; Meta adayı Meta içinde sayar) · `website` (sitedeki form; Meta'nın Lead olayını
     görmesi gerekir: `meta_signal.lead_seen`, S00b 6b) · `call` (arama). Hedef aday maliyeti ürün ekonomisindeki dönüş oranından
     (`target_cpl`); oran yoksa hedef kullanıcı hedefidir. Kullanıcıya: "Ucuz aday satış demek değildir; haftalık olarak kaçına
     ulaşıldığını, kaçının nitelikli olduğunu ve kaçının satın aldığını sayıyla gireceğiz (kişisel bilgi değil)."
   - Sezon / hedef tarih (yoksa "yok") → `campaign_update(season)`; hedef tarih brief'e yazılır.
   - Reklam seti günlük bütçesi (ilk turda tek reklam setinin günlük bütçesi; sonraki turlarda mevcut setin bütçesi — test payı S02'de
     `exploration_share` ile hesaplanır) → `cycle_set(profile_id, cycle_id, {"adset_budget_daily": …})`.
   - **Toplam Meta harcama sınırı:** "Bu kampanyanın ilk yayınından itibaren bütün turlarındaki Meta reklam harcaması için bir üst
     sınır var mı?" Tutar profilin reklam hesabı para biriminde; üretim/servis ücretleri dahil değil; eski turların harcaması yeni
     turda sıfırlanmaz. Sınır yoksa bu da açık karardır (`NULL`). → `campaign_update(budget_total, budget_total_confirmed=True)`.
   - **Meta satışı görüyor mu (1.4.7):** `meta_signal_get(profile_id)`. Sonuç türü satış olacaksa ve durum `purchase_seen` değilse sunucu
     satış sonucunu reddeder; kullanıcıya üç yol sunulur ve seçimi `meta_signal_set(..., choice=…)` ile kaydedilir:
     (1) **piksel kur** (`pixel_install`): satış sayfasına Meta pikseli; Shopier panelinde piksel alanı olduğu ikincil kaynaklarda geçer,
     Shopier belgesinden teyit edilmedi (`ref-legal-tr-meta` §7) — kurulumdan sonra Events Manager'da Purchase görülünce S00b'nin 6b
     kontrolü yeniden yapılır; (2) **satışları yükle** (`csv_upload`): Events Manager'da veri kümesine CSV ile; müşteri e-posta/telefonu
     Meta'ya gider, bu yüzden KVKK dayanağı (`processing_permission_check`) olmadan önerilmez ve yüklemeyi insan yapar; (3) **bilinçli
     başka sonuç** (`optimize_other`): mesaj, bağlantı tıklaması ya da profil ziyareti; satış yine `sales_add` ile kanala göre izlenir
     ve hüküm "satışa değil, dikkat ve tıklamaya dayanıyor" diye yazılır.
     Yolun kendisi (hangi platformda nasıl, kim yapacak, kaynakları) `reklam-atolyesi:data-connection` ile kullanıcının düzenine göre
     kurulur; brief bu yüzden beklemez, seçim kaydedilir.
   - Elle satış: `sales_add(..., channel, kind)` — kanal (Shopier, site, Instagram DM, WhatsApp, kurumsal, mağaza) ve tür (satış | talep);
     atıf varsayımı söylenir (6.2). Kurumsal/toptan fırsat hedefleniyorsa sonuç türü çoğu zaman mesajdır; Shopier satışına bakılarak
     başarısız sayılmaz.
3. **Ekonomi özeti** (6.2): ürünün başa baş CPA / hedef CPA ve durumu (`exact | assumed | range | unknown`); katkı bilinmiyorsa
   "VARSAYIM". CPA kararı hedefleniyorsa konsept başına beklenen satın alma < 10 ise CPA hükmünün geniş aralıklı yön tahmini
   olacağı baştan yazılır (kesin sayı S02'de).
4. **Kampanya modu:** `full` (yeni çekim) varsayılan; hızlı tur kararı S03'te verilir.
5. `PR/templates/reports/brief.md` şablonundan `DD/profiles/<slug>/campaigns/<kampanya>/c<tur>-brief.md` (tur adıyla; önceki turun
   dosyası üzerine yazılmaz; geçici ad → doğrula → atomik yeniden adlandır). Boş alan "bilinmiyor" yazılır, tahmin yazılmaz.
   "Rakip bağlamı" bölümü S01b sonrası doldurulur (atlanırsa "rakip bağlamı yok — gerekçe").
6. `stage_complete(profile_id, "S01", outputs=[{path: brief}], summary, campaign_id, cycle_id)` → S01b'ye geçilir (kapı yok).

## Çıktılar
`campaigns` (goal, result_type, season, budget_total + teyit), `cycles.adset_budget_daily`, `c<tur>-brief.md`, devam notu,
günlüğe tek satır gerekçe.

## Kontroller
- Sonuç türü kayıtlı; `budget_total` ya pozitif tutar ya da açık `NULL` kararı (teyit ifadesiyle).
- Ekonomi dili ürün kaydıyla aynı (varsayım/aralık gizlenmedi).
- Kampanyanın bağlı olduğu profil adı kullanıcıya gösterildi.

## Kapı mesajı
Kapı yoktur. Geçiş özeti: "Brief hazır: <ürün> · amaç … · sonuç türü … · hedef tarih … · günlük reklam seti bütçesi … · toplam sınır
<tutar|yok>. Şimdi pazara bakalım (rakip analizi); istemezsen atlayabiliriz."
