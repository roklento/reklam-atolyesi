---
name: launch-pack
description: "reklam-atolyesi S14 yayın paketi — reklam adları, metinler, Ads Manager kurulum talimatı, harcama/risk sınırları, AI açıklaması, takvim; insan yayınından sonra launch_confirm. Kapılı."
---

# launch-pack — S14 · Yayın paketi ve gerçek yayın kaydı (spec 4.1, 4.2, 4.4, 5.18, 6.3, 9.2, bölüm 10)

## Amaç
İnsanın Ads Manager'da uygulayacağı eksiksiz yayın paketini hazırlamak. **Plugin Meta'ya yazmaz;** yayın, bütçe ve limitleri insan
uygular. Paket onayı yayın yapıldığı anlamına gelmez; S15'e geçiş yalnızca `launch_confirm` ile olur.

## Ön koşul
S13 kapısı geçilmiş; bütün test kreatifleri `qc_status=passed`.

## Girdiler ve bağlam paketi
`memory_context(profile_id, "S14", campaign_id, cycle_id)`: bütçe durumu, risk sınırları, test kreatifleri, takvim. `creative_list`,
`campaign_get`, `cycles.budget_plan_json`, `metrics_query` (gerçekleşen kampanya harcaması), `strategy_get`, `ref-legal-tr-meta` (AI açıklaması).

## Kullanılan hazır skill'ler ve OVERRIDES
Yok.

## Adımlar
1. `stage_start(profile_id, "S14", campaign_id, cycle_id)`.
2. **Ayrı reklam sayısı ve bütçe yeniden doğrulanır:** test `creative_key` sayısı ≤ `allowed_test_ads` (fazlası yedekte kalır; sessizce
   eklenmez). Meta kurulumu formatları tek reklamda kabul etmezse ayrı reklam anahtarları formatı da içerir ve her biri ayrıca sayılır/
   kapsanır. Toplam harcama planı güncel veri kesimiyle yeniden hesaplanır (`budget.py`); ölçekleme katmanı açıksa (`scale_layer_get`)
   girdiye `scale_layer_daily` = katmanın günlük bütçesi yazılır ve plan bunu ayrıca sayar (S14 kapısı katman bütçesi plana girmediyse
   açılmaz); kalan bütçeyi aşıyorsa paket onaya açılmaz.
3. **Risk sınırı eşlemesi:** onaylı reklam başı sınır her yayınlanacak `creative_key` ile eşlenir →
   `cycle_set(profile_id, cycle_id, {risk_limits_json: {per_ad:{…aynı onay…}, mapping:{<creative_key>: {amount, currency}}}})`.
   Sınır değişikliği yeni açık kullanıcı onayı ister; eski onay kanıtı korunur. Eşleme eksikse paket onaya açılmaz (sunucu da reddeder).
4. **Metinler:** birincil metin, başlık, açıklama, CTA (Meta CTA türü) — yalnızca kanıtlanabilir iddialar; fiyat/indirim satış
   sayfasıyla birebir ve indirimde referans fiyat kanıtı; marka tonu; kaçınılacaklar. Metinler `checks.py meta-text --text` ile taranır
   ve uzunluğu `checks.py copy --texts metin.json --plan <plan> --promise "<ana vaat/teklif sözcükleri>"` ile denetlenir (birincil
   metin 125, başlık 40, açıklama 30 görünür karakter — Meta önerisi; ana vaat görünür kısımda; dikey videoda ilk cümle; videoda yazı/
   konuşma yoksa mesajı metin taşır; profil/stil kitabında daha sıkı hedef varsa `--targets`) ve Meta reklam standartları (`ref-legal-tr-meta` §8): kişisel özellik ima eden ifade yok, şok/korku taktiği yok, sağlık ve görünümde olumsuz öz algı ya da süreli/kesin sonuç vaadi yok; önce/sonra ürün kategorisine göre (8d); 18+ hedefleme gerekiyorsa kurulum talimatına yazılır.
5. **Ads Manager kurulum talimatı** (adım adım, hesabın güncel ekranında doğrulanacağı notuyla):
   - **İlk tur (`bootstrap`):** tek kampanya, tek reklam seti, teklif stratejisi "En yüksek hacim"; turun konseptleri birlikte.
     Hükümler "Meta'nın dağıtımı altında".
   - **Sonraki turlar (`creative_test`):** aynı reklam setinde, yayındaki bir reklamdan başlatılan Meta kreatif testi; yeni konseptler
     test reklamı (araç sınırı içinde); test bütçesi ≤ `exploration_share` (plugin'in yerel üst sınırı 0,2; Meta'nın ~%20 önerisi teyit edilmedi, §7); reklam sayısı Ads Manager ekranından; süre 7 gün (ya da S02'nin seçtiği); "En yüksek hacim".
     Maliyet hedefi/teklif sınırı/ROAS hedefi kreatif testi engeller. Test dışında konsept başına ayrı set (ABO) desteklenmez: bütçeyi
     parçalar ve her set ayrı öğrenir (çok set → daha az öğrenme, resmi; §7); eşit harcama da kontrollü karşılaştırma değildir. Ayrı
     hücreler yalnızca aşağıdaki Meta A/B testi içinde geçerlidir.
   - **Meta A/B testi (`ab_test`, 1.5.0; yalnızca S02'de uygun bulunup kullanıcı seçtiyse):** her konsept ayrı kampanya (ya da ayrı reklam
     seti), ayarlar aynı, tek değişken kreatif; hücreler kurulunca uygunluk salt okumayla `ads_experiment_check_eligibility(ad_account_id,
     ad_entity_ids=[hücre kampanyaları])` (uygun değilse test kurulmaz, varsayılan yapıya dönülür ve kullanıcıya gerekçe söylenir);
     Deneyler (Experiments) → A/B testi → mevcut kampanyaları seç (en fazla 5); hücrelere
     **aynı bütçe**; takvim S02'deki gün sayısı (7–30); kazanan ölçüsü "sonuç başına maliyet"; kitle aynı anda çalışan başka kampanyalarla
     çakışmamalı (resmi; §7). Test kurulunca kullanıcı çalışma kimliğini verir ya da `ads_experiment_list_tests` ile bulunur →
     `ads_experiment_abtest_get_test(study_id)` okunur → `cycle_set(profile_id, cycle_id, {structure_detected: "ab_test", meta_test_id:
     <kimlik>, structure_evidence_json: {study_read: {cells: [<konsept kodları>], variable, start, end}, source: "meta_mcp"}})`. Hücreler
     konsept kodlarıyla eşlenir (eşlenemeyen hücre yazılmaz). Okunamazsa yapı `unverified` kalır.
   - **Müşteri adayı (`lead`, 1.5.0):** amaç "Potansiyel müşteriler"; dönüşüm yeri `instant_form` → anlık form (form türü: daha fazla hacim
     · daha yüksek niyet · zengin içerik; en az bir soru; giriş metni; bitiş ekranında sonraki adım), `website` → sitedeki form ve Lead
     olayı, `call` → arama. **Gizlilik politikası bağlantısı istenir** (Meta makaleleri çelişiyor: biri isteğe bağlı, biri gerekli diyor;
     KVKK aydınlatması için de gerekir — yerel kural, §7). Formda yalnızca gereken bilgi sorulur; nitelik için 1–2 soru (bütçe, tarih,
     ihtiyaç). Adaylar Meta'nın potansiyel müşteri merkezinden ya da CRM'den kullanıcıya gelir; **bu sisteme kişisel bilgi girmez**,
     yalnızca haftalık sayılar (`lead_outcome_set`).
   - **Özel reklam kategorisi:** `service_info` gerekli diyorsa (konut/istihdam/finansal + ABD/Kanada/listelenen Avrupa kitlesi) kampanya
     oluştururken kategori seçilir; hedefleme kısıtlanır (resmi; §7). Gerekmiyorsa satır yazılmaz.
     İlk turun aç kalan konseptleri kaybeden sayılmaz; sonraki turun kreatif testinde ilk sıradadır (coach, learn).
   - **Ölçekleme katmanı (`scale`, varsa):** S16'da onaylanan ayrı kampanya; tek reklam seti, geniş kitle, "En yüksek hacim". Yeni turun
     test reklamları **buraya eklenmez**; yeni fikirler yalnızca test katmanında sınanır. Pakette katmanın durumu tek satırla yer alır
     (üyeler, günlük bütçe, kalan bütçeye etkisi). Üye ekleme her zaman S16 uygulama listesinden ve **mevcut gönderiyle** yapılır
     ("Mevcut gönderiyi kullan" → gönderi kimliği); yeni reklam olarak kopyalamak beğeni ve yorum birikimini taşımaz (§7).
   - Test başlangıcı mümkünse hesap saat diliminde **gece yarısı** (günlük veride sınır günleri dışlanır, 6.4).
6. **Harcama ve bitiş sınırları:** kampanya toplam sınırı, gerçekleşen ve kalan; insanın uygulayacağı, hesabın desteklediği kapsamlı
   **harcama limiti ve/veya bitiş tarihi** talimatı (tarih/günlük bütçe tahmini tek başına kesin parasal tavan değildir); reklam başı risk
   sınırı ve sınıra ulaşınca durdurma önerisi üretileceği.
7. **AI açıklaması:** AI içeren her varyasyon için güncel reklam türünde Ads Manager'ın sunduğu açıklama/etiket seçeneği ve Türkiye'de
   ayırt edilmesi zor AI içerik için görünür açıklama talimatı (`ref-legal-tr-meta`, kaynak ve kontrol tarihiyle; doğrulanmamış
   politika kesin zorunluluk diye sunulmaz).
8. **Takvim:** planlanan `launch_at`, günlük takip 09:00, plan günü (karar hazırlığı sabahı), test bitişi.
9. Paket: `PR/templates/reports/yayin-paketi.md` → `DD/profiles/<slug>/campaigns/<k>/c<tur>-yayin-paketi.md` (yükleme listesi yalnızca
   test kreatifleri; atomik). `stage_complete(profile_id, "S14", outputs=[{path: paket}], summary, campaign_id, cycle_id)` → `awaiting_gate`.
10. Kapı onayından sonra kullanıcıya: "Yayına aldığında 'yayına aldım' yaz; reklam kimliklerini ve gerçek saati gir."

### Gerçek yayın kaydı (S14 → S15)
11. Kullanıcı "yayına aldım" deyince: Ads Manager'dan reklam kimlikleri (her biri `creative_key` adını taşır), reklam seti, gerçek yayın
    saati ve test başlangıcı istenir. MCP yolunda salt okuma karşılaştırma: `ads_get_ad_entities(level="ad", …)` → okunan kimlikler
    `readback={ad_ids:[…]}`. Adlandırma eşlemesi: `PY PR/scripts/meta/meta_tools.py naming --name "<reklam adı>"`.
12. `launch_confirm(profile_id, campaign_id, cycle_id, s14_stage_run_id, output_version, ads=[{meta_ad_id, creative_key, meta_ad_name,
    adset_id, campaign_meta_id}], launched_at, user_confirmation, test_start?, readback?)` → `ads` kayıtları, `cycles.launched_at`,
    S15 geçişi. Yedek anahtar ya da risk eşlemesi olmayan anahtar reddedilir.
13. **Zamanlanmış işler** (masaüstü uygulaması + kullanıcı onayı; navigator §6): günlük takip (kampanya başına tek; yeni turda kopya
    yok) ve plan günü karar hazırlığı kurulur/güncellenir; `job_upsert`. Takvim gerçek yayın tarihiyle kesinleşir (`cycle_set`:
    `test_start`, `test_end`, `plan_day`, `decision_due_at`).

## Çıktılar
Yayın paketi, `cycles.risk_limits_json.mapping`, güncel bütçe planı; yayından sonra `ads`, `cycles.launched_at/test_start/test_end`,
`launch_confirm` kararı, görev kayıtları, devam notu.

## Kontroller
- Meta platform kuralı (sınır, format, güvenli alan, politika) kullanıldıysa durumu `ref-legal-tr-meta` §7'ye göre belli: resmi
  (bağlantı + tarih), yerel koruma kuralı ya da teyit edilmedi; teyit edilmeyen kural kesin diye sunulmadı.
- Yükleme listesinde yalnızca QC'den geçmiş test kreatifleri; her birinin risk sınırı eşlemesi var; tavan aşılmadı.
- Kurulum talimatı yapıya uygun; insan uygulayacak; plugin hiçbir Meta yazma aracını çağırmadı.
- Ölçekleme katmanı açıksa harcaması toplam plana girdi ve yeni test reklamı ölçekleme setine yazılmadı.
- `launch_confirm` olmadan S15'e geçilmedi.

## Kapı mesajı
"Yayın paketi: N test reklamı (… ), yedekte K. Kurulum: <ilk tur | kreatif test> — adımlar pakette. Sınırlar: kampanya toplam … (kalan …),
reklam başı risk …; uygulanacak harcama limiti/bitiş: …. AI açıklaması gereken: …. Planlanan yayın: …. Paketi onaylıyor musun?"
→ `gate_approve(...)`. Yayının kendisi ayrıca `launch_confirm` ile kaydedilir.
