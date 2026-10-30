---
name: coach
description: "reklam-atolyesi S16 koçluk — değişmez girdi kopyasından Beta-Binom/Gamma analizi, hüküm dili, sahne kaybı, rekabet bağlamı, grafikler, kararlar ve Ads Manager uygulama listesi. Kapılı."
---

# coach — S16 · Analiz ve koçluk (spec 6.1, 6.3, 6.4, 6.6, 6.8–6.13, 6.16)

## Amaç
Yayındaki reklamın verisini matematikle okuyup insan diline çevirmek; kararları somut Ads Manager adımlarına dönüştürmek. Hesap
`media-analyst`, yorum ve uygulama listesi `coach` ajanının yöntemiyle. **Hesap yalnızca değişmez girdi kopyasından yapılır.**

## Ön koşul
- S15 tamam; test bitmiş ve mümkünse `test_end + maturity_days` geçmiş. Olgunlaşmamışsa rapor **geçici/proxy** temellidir; kullanıcı turu
  "yetersiz veri" ile kapatabilir ya da olgun sonucu bekler. Kesin performans hükmü verilmez.
- Koçluk turu öncesi Meta geçmişi artımlı tazelenir (`meta-history`, test aralığının tamamı ve olgunluk penceresi).
- Plan günü sabahı karar hazırlığı işi (`/reklam-atolyesi:karar-hazirla`) çalıştıysa onun **taslağı** ve rakip fark görüntüsü hazırdır;
  aynı veri sürümünde tekrarlanmaz.

## Girdiler ve bağlam paketi
`memory_context(profile_id, "S16", campaign_id, cycle_id)`: açık hipotezler, önceki kalibrasyon, açık uygulama maddeleri, kapsamı eşleşen
playbook, rekabet bağlamı, önceki portföy sonucu. `ref-metrics-math` (yöntem ve eşikler).

## Kullanılan hazır skill'ler ve OVERRIDES
Yok.

## Adımlar
1. `stage_start(profile_id, "S16", campaign_id, cycle_id)`.
2. **Değişmez girdi kopyası (6.4):** yapı `ab_test` ise önce çalışma salt okumayla okunur: `ads_experiment_abtest_get_test(study_id=
   cycles.meta_test_id)` → kazanan hücre (varsa `winner_result`) konsept koduna eşlenir. Sonra
   `decision_input_snapshot(profile_id, campaign_id, cycle_id, kind="coach_report", extra={competitor_snapshot_id, ab_test?: {study_id,
   winner_concept, confidence?}, audience_segments?: {<konsept kodu>: {new, engaged, existing}}})` (kazanan yoksa ya da eşlenemezse
   `winner_concept` yazılmaz; tahmin edilmez). **Kitle segmentleri (1.9.0):** konseptlerde aşama varsa test penceresi için bir kez
   `ads_get_ad_entities(level="ad", breakdowns=["user_segment_key"], fields=["amount_spent"], time_range=<test>)` okunur; reklamlar
   `creative_key` üzerinden konsepte toplanır ve harcama segment başına `audience_segments`'e yazılır. Segmentler tanımlı değilse ya da
   döküm boş/`null` dönerse alan yazılmaz; raporda "kimin gördüğü okunamadı" çıkar (tahmin edilmez)
   — kullanılan satırlar ve kaynak/çekim zamanları, ölçüm bağlamı, dahil/dışlanan zaman aralıkları ve nedenleri, elle satış, ekonomi/hedef,
   bütçe ve risk sınırı, yapı kanıtı, dondurulmuş önseller, model/eşik sürümü, parametreler, tohum (1729), rakip görüntüsü kimliği ve hash'i.
   Kopya `reports/` altına tur/rapor sürümüyle, atomik ve SHA-256'lı; eski kopyanın üzerine yazılmaz. **Kopya saklanamazsa rapor
   tamamlanmış sayılmaz.**
3. **Analiz:** `PY PR/scripts/analytics/coach.py --snapshot <kopya.json> --out reports/c<tur>-analysis-v<n>.json` (deterministik;
   aynı kopya → aynı sonuç). Kapsam: oranlar Beta-Binom (önsel aynı profil ve amaçtan, `n_cap=30`, yoksa Beta(1,1)); %90 eşit kuyruklu
   aralık; geçmişe ve diğer konsepte üstünlük olasılığı; sonuç maliyeti Gamma (`T` doğrulanmış hedef ise); eşikler (hook ≥ 1.000, CTR ≥ 3.000
   gösterim, maliyet ≥ 10 sonuç); harcama dağılımı (aç kalan < %10 → "yetersiz veri", kaybeden değil); yorgunluk; sahne düzeyinde kayıp
   (beklenen eğriye göre; olasılık cümlesi); veri yeterliliği; limit uyarıları; rol başına portföy sonucu (keşif).
   1.4.7: **karar metriği** (`metric_basis`: üstünlük olasılığı hook oranı üzerindendir — "tüm konseptlerin en iyisi olma", satış değil;
   karar sonuç maliyetinden mi üst huniden mi; Meta bu turda satış gördü mü), **"Reklam mı, teklif mi, sayfa mı?"** teşhisi
   (`funnel_diagnosis`: konseptler arası göreli açılış ve tıklama; kampanyada ≥ 100 tıklama ve görünür web satışı yoksa "reklam sonrası
   şüpheli" — sayfa, fiyat, kargo, güven, teklif) ve **kanal özeti** (`channels`: elle girilen satış/talep kanala göre).
   1.4.8: kanal özeti tek satış defteridir — kullanıcının verdiği dışa aktarım aralığı elle girişin dönemini tamamen kapsıyorsa dosya esastır; kapsamıyorsa
   ve mesaj kanallarında (DM modülü) aynı kanal ve dönemde ikisinden büyüğü sayılır; her çakışma rapora yazılır ("kaynak dönemi tam
   kapsamıyor" satırı kullanıcıyla kontrol edilir); **Meta ↔ mağaza** (`store_vs_meta`, yalnızca pikselin görebildiği site/Shopier
   siparişleri: Meta'nın atfettiği satın alma mağazanın ödenmiş siparişinden belirgin fazlaysa piksel/çift olay şüphesi); **mesajla satış hunisi** (`dm`: konuşma → nitelikli →
   teklif → satış, %90 aralık, kayıp nedenleri, ilk cevap süresi, kampanyaya kanıtla bağlı konuşmalar).
   1.5.0: **müşteri adayı** (`lead`: aday başı maliyet, kayıttan nitelikli ve satış başına maliyet, adaydan satışa %90 aralık, varsayılan
   dönüş oranının gözlenenle tutarlılığı; aday sonrası kayıt yoksa "ucuz aday satış demek değildir" uyarısı). Hedef maliyet sonuç türüne
   göre: satışta hedef CPA, adayda hedef aday maliyeti (`target_cpl`; ikisi de yalnızca teyitliyse olasılık üretir). **Meta A/B testi**
   (`ab_test`, yapı `ab_test` iken: hücre başına sonuç, sonuç başına maliyet, en düşük maliyet olasılığı; Meta'nın okunan kazananı ve
   uyuşma). A/B yapısında hüküm dilinde "Meta'nın dağıtımı altında" yoktur (kitle rastgele bölünür). Tıklama çok, satış/aday sonrası
   zayıfsa `profile-check` önerilir.
   1.9.0: **huni aşamaları** (`stages`): aşaması olan her konsept KENDİ aşamasının teşhis metriğiyle okunur — TOFU hook ve tutma, MOFU
   bağlantı CTR'si, açılış sayfası ve içerik görüntüleme oranı, BOFU sepete ekleme ve ödeme başlatma oranı ile satın alma başı maliyet;
   piksel olayı göndermiyorsa metrik "okunamadı" yazılır, sıfır sayılmaz. Segment dökümü varsa konsept başına yeni / etkileşime geçmiş /
   mevcut müşteri harcama payı; BOFU harcamasının çoğu yeni kitleye gittiyse bu açıkça yazılır. **Hüküm kuralı değişmez** (sonuç türü,
   toplam satış ve katkı). Huni turunda TOFU/MOFU konsepti yalnızca satış maliyetiyle "kapat" almaz (`coach.py` "tut — huni turu" yazar);
   aşamalar arası sonuç maliyeti karşılaştırması keşiftir (kısa pencere satın almaya yakın mesajı kayırabilir; beklenti, doğrulanmış
   bulgu değil).
4. **Grafikler:** `PY PR/scripts/analytics/charts.py --analysis <analysis.json> --snapshot <kopya.json> --out-dir reports/c<tur>-charts-v<n>`.
   Her grafiğin altına tek cümlelik yorum; görselleri **açıp bak**.
5. **Kalibrasyon (6.13):** `calibration_get(profile_id)`; 30'dan az çözülmüş tahminde yalnızca sayı ("12 tahminden 9'u tuttu"), eşik önerisi yok.
   Olgunlaşmış önceki tahminler `prediction_resolve(profile_id, prediction_id, outcome, outcome_snapshot)` (çözüm kopyası ayrı hash).
6. **Kararlar (6.10):** tut / büyüt / kapat / yenile, gerekçeli ve sonuç türüne göre. Hüküm dili test dönemine göre: bootstrap ve
   doğrulanmamış yapıda "Meta'nın dağıtımı altında"; eşik altı → "yön/yetersiz veri" (istatistiksel kazanan, büyüt ya da kaybeden
   gerekçeli kapat **yok**). Küçük bütçede hüküm üst huniden geliyorsa açıkça yazılır ("satışa değil, dikkat ve tıklamaya dayanıyor").
   Hook × CTR × CVR çarpımı yapılmaz; erişim toplamından frekans türetilmez. Konsept önceliği yalnızca sonraki test adaylarını sıralar.
   İlk turda (tek set) Meta'nın aç bıraktığı konsept (`carry_over`) kaybeden değildir; sonraki turun kreatif testine **öncelikli aday**
   olarak rapora ve S17 brief taslağına yazılır (hazır kreatifiyle; yeniden çekim/render yok).
   Reklam düzeyinde "kapat" performans gerekçesiyle önerilmez (Meta zaten harcama vermiyorsa gereksiz); onaylı sınır aşımı ayrı kuraldır.
   Teşhis "reklam sonrası şüpheli" ise kreatife satış/maliyet gerekçeli olumsuz karar yazılmaz; uygulama listesine önce satış sayfası ve
   teklif kontrolü girer (S02'nin kendi sayfa kontrol listesiyle).
6a. **Ölçekleme katmanı (test ayrı, ölçek tek):** "büyüt" hükmü alan reklam için iki yol vardır: ana reklam setinde kalıp bütçe
   artışıyla büyümek (varsayılan) ya da ayrı **ölçekleme kampanyasına** (tek reklam seti, geniş kitle, "En yüksek hacim", kreatif test
   yok) **mevcut gönderiyle** taşınmak. Taşıma önerisi ancak hepsi sağlanırsa yapılır:
   - **Hüküm:** yapı `creative_test` (doğrulanmış), reklam eşikleri geçmiş (maliyet ≥ 10 sonuç) ve sonuç maliyeti doğrulanmış hedefin
     altında, P(maliyet < `T`) ≥ 0,90. Bootstrap, doğrulanmamış yapı, eşik altı ya da yalnızca üst huni bulgusu → taşıma yok.
   - **Öğrenme bütçesi:** ölçekleme setinin günlük bütçesi ≥ 7 × `T` (öğrenme aşaması için 7 günde ~50 optimizasyon olayı; durumu
     `ref-legal-tr-meta` §7). Karşılanmıyorsa katman önerilmez, kazanan ana sette kalır. Kullanıcı yine de isterse "öğrenme sınırlı
     kalabilir" uyarısı kararla birlikte kaydedilir.
   - **Toplam sınır:** katmanın ve ana setin günlük bütçesi × turun kalan günleri, kampanya toplam harcama sınırının kalanına sığıyor.
     Sığmıyorsa öneri yok; eksik tutar gösterilir.
   İlk üç koşulu `coach.py` hesaplar (`budget.py` `scale_check`): analizdeki `scale_candidates` her "büyüt" konsepti için `checks`
   {structure, cost, min_daily, fits_total}, `min_daily`, kaynak reklamlar ve gerekçeleri verir; skill yeniden hesaplamaz.
   - **Gönderi kimliği:** reklamın gönderisi salt okumayla `ads_get_creatives` üzerinden okunur (Facebook: `effective_object_story_id`,
     Instagram: `effective_instagram_media_id`; alan adları `ads_get_field_context` ile doğrulanmadan kesin sayılmaz). Okunamazsa
     kullanıcıdan Ads Manager önizlemesindeki gönderi kimliği/bağlantısı istenir. Kimlik yoksa taşıma maddesi yazılmaz; yeni reklam
     olarak kopyalamak beğeni ve yorum birikimini sıfırlar.
   Katman zaten açıksa yalnızca yeni üye taşıma ve yorgunluk kararları üretilir. Katmandaki reklamların verisi test verisi değildir:
   hüküm dili "Meta'nın dağıtımı altında"; raporda ayrı bölümdür ve test hükümlerine, önsele ya da playbook kanıtına girmez.
7. **Uygulama listesi:** her karar somut bir Ads Manager adımı (örnek biçim: "Y reklam setinin günlük bütçesini <mevcut> → <yeni> yap"; tutarlar ve para birimi profilden).
   **Koruma sınırları (yerel; Meta kuralı diye sunulmaz, §7):** günlük bütçe artışı ≤ %20; aynı reklam setinde aynı gün birden fazla büyük değişiklik yok; eşik altı kreatife
   istatistiksel "kapat" yok. → `action_items_set(profile_id, campaign_id, items=[{action, reason_kind:"performance", target_meta_id,
   before, after, evidence:{input_snapshot}}], cycle_id)` (onay S16 kapısında).
   Ölçekleme maddeleri (`scale_candidates[].eligible` ve okunmuş gönderi kimliği varsa) sırasıyla, `kind` alanıyla:
   (1) katman yoksa `kind:"scale_open"`, `reason_kind:"structure"`, `after:{daily_budget}` — "Ölçekleme kampanyası aç: tek reklam seti,
   geniş kitle, günlük <B>, En yüksek hacim, kreatif test yok"; (2) `kind:"scale_move"`, `reason_kind:"performance"`,
   `after:{post_id}`, `evidence:{input_snapshot, scale_checks:<checks>}` — "<reklam adı>'nı ölçekleme setine yeni reklam olarak ekle →
   Mevcut gönderiyi kullan → gönderi kimliği <post_id>"; (3) `kind:"scale_pause_source"`, `reason_kind:"structure"`, `after:{post_id}`
   — "Aynı gönderiyi test setinde duraklat" (aynı gönderi iki sette kendi kendisiyle yarışmasın diye; yerel koruma kuralı, §7). Sunucu
   gönderi kimliği ya da dört koşuldan biri eksik taşıma maddesini reddeder. Ölçekleme seti bütçesindeki sonraki artışlar da ≤ %20/gün.
   İnsan uyguladıktan ve `track` doğruladıktan sonra katman kaydedilir: `scale_layer_set(profile_id, campaign_id, cycle_id,
   layer={campaign_meta_id, adset_id, daily_budget, members:[{creative_key, meta_ad_id, post_id, source_meta_ad_id}]},
   learning_warning_ack?)`. Araç üyeleri ölçekleme setinin `adset_id`'siyle kreatife bağlar (`ad_link`), kaydı S02'nin bütçe planından
   korur ve yeni tura taşır; günlük bütçe < 7 × hedef ise yalnızca kullanıcının açık ifadesiyle (`learning_warning_ack`) kaydeder.
8. **Tahminler:** her P(kazanır)/beklenen aralık `prediction_log(profile_id, campaign_id, cycle_id, subject, metric, input_snapshot=<yol/hash>,
   p_win, interval)`; aynı test/özne/metrik için rapor sürümleri yeni tahmin sayılmaz.
9. **Rekabet bağlamı (6.16):** test penceresinde rakip tarafında ne değişti (fark görüntüsü); anomalilerin yanında **bağlam** olarak;
   nedensellik iddiası yok, hüküm diline ve eşiklere girmez. Açı portföyü sonucu rol başına keşif etiketli; önceden sabitlenmiş birincil
   hipotez değilse playbook adayı olmaz.
10. **Rapor:** `PY PR/scripts/analytics/report.py --analysis <analysis.json> --snapshot <kopya.json> --charts <charts.json> --calibration
    <calib.json> --actions <actions.json> --next <sonraki.md> --out reports/c<tur>-koçluk-raporu-v<n>.md`. Bölümler: Özet (3 cümle;
    karar metriği satırıyla) · Kararlar (olasılıklar metrik adı ve payda/paydayla) · Reklam mı, teklif mi, sayfa mı · Grafikler · Sahne düzeyinde izleyici kaybı · Ölçekleme katmanı (varsa: üyeler, harcama, frekans, yorgunluk; taşıma
    önerisi ya da neden önerilmediği) · Uygulama listesi ve durumu · Rekabet bağlamı · Öğrenilenler · Sonraki tur ·
    Veri yeterliliği · Koçluğun isabeti. Dil sade; her hükmün yanında veri yeterliliği.
11. `stage_complete(profile_id, "S16", outputs=[{path: rapor}, {path: kopya}, {path: analysis}], summary, campaign_id, cycle_id)` → `awaiting_gate`.
12. Onaydan sonra kararlar `decision_log` ile; maddeler `action_item_set_status(item_id, "approved", approval_text, decision_id)`.
    Uygulamayı insan yapar; gerçekleşme `track` 6.11 ile doğrulanır. Kapalı turun verisi sonradan değişirse yeni rapor sürümü
    (yeniden değerlendirme adayı); eski karar ve kopyası değişmez.

## Çıktılar
Girdi kopyası (hash'li), analiz JSON'u, grafikler, sürümlü koçluk raporu, `action_items` (önerilen → onaylı), `coaching_predictions`,
çözülen tahminler, devam notu.

## Kontroller
- Kıyas (`benchmarks_get`) yalnızca bağlam satırıdır; hüküm ve önsel girdisi değildir; yoksa "kıyas yok" yazılır.
- Meta platform kuralı (sınır, format, güvenli alan, politika) kullanıldıysa durumu `ref-legal-tr-meta` §7'ye göre belli: resmi
  (bağlantı + tarih), yerel koruma kuralı ya da teyit edilmedi; teyit edilmeyen kural kesin diye sunulmadı.
- Rapor ve hesap aynı kopyayı referans veriyor (yol/hash/sürüm); hesap sırasında tablodan yeniden veri alınmadı.
- Eşik altı hüküm yok; sonuç türleri, medya türleri, test dönemi/sonrası ve atıf ayarları karışmadı.
- Koruma sınırları aşılmadı; Meta'ya yazılmadı; rekabet bağlamında nedensellik dili yok.
- Ölçekleme taşıması yalnızca 6a'nın dört koşuluyla önerildi; taşıma maddesinde gönderi kimliği var; ölçekleme katmanı verisi test
  hükmüne, önsele ya da playbook kanıtına karışmadı.

## Kapı mesajı
"Koçluk özeti (3 cümle) … Kararlar: 1) … (veri yeterliliği: …) 2) … Ölçekleme: <taşınacak reklam + gönderi kimliği | önerilmedi: neden>.
Uygulama listesi: N adım (Ads Manager'da senin uygulaman gerekiyor).
Hangi kararları onaylıyorsun, neyi değiştirelim?" → açık onayda `gate_approve(...)`.
