---
name: track
description: "reklam-atolyesi S15 takip — günlük Meta okuması/CSV, ölçüm bağlamı, test yapısı tespiti, veri kalitesi, olgunluk, yorgunluk/anomali, bütçe ve risk uyarıları, uygulandı mı kontrolü."
---

# track — S15 · Takip (spec 6.3–6.7, 6.10, 6.11, 4.4, 9.2)

## Amaç
Yayındaki reklamların günlük verisini **salt okuma** ile almak, ölçüm bağlamıyla kaydetmek ve hükme girmeden önce sağlığını izlemek:
yapı tespiti, veri kalitesi, olgunluk etiketi, yorgunluk/anomali, harcama sınırı uyarıları ve uygulama listesinin gerçekleşmesi.
Günlük takip **aşamadan bağımsızdır**: kampanyada yayında reklam olduğu sürece her gün çalışır (`/reklam-atolyesi:takip` işi ya da
navigator açılışı, son çekim 24 saatten eskiyse).

## Ön koşul
- `launch_confirm` yapılmış (`cycles.launched_at` dolu). Zamanlanmış işte kimlikler komut argümanlarından gelir (`--profile`, `--campaign`);
  aktif profil varsayılanı kullanılmaz; işler soru sormaz.
- Profil veri yolu `mcp` ya da `csv`. CSV'de görev dış veri beklediğini kaydeder; veri yüklenmeden güncel takip/uygulanma doğrulaması
  yapıldığı söylenmez.

## Girdiler ve bağlam paketi
`memory_context(profile_id, "S15", campaign_id, cycle_id)`: açık uygulama maddeleri, ölçüm tanımı, risk sınırları, bütçe durumu.
`meta_fields.json`, `cycles.measurement_json`, `metrics_query`, `action_items_list`, `sales_list`.

## Kullanılan hazır skill'ler ve OVERRIDES
Yok.

## Adımlar
1. Etkileşimli turda `stage_start(profile_id, "S15", campaign_id, cycle_id)` (zamanlanmış takip aşama açmaz; `job_claim` ile sahiplenir,
   `job_finish` ile veri sürümünü yazar).
2. **Veri çekme (MCP):** `ads_get_ad_entities(level="ad", time_increment="1", time_range={since, until}, fields=<meta_fields.json>)` — eksik
   günler + en az olgunluk penceresi yeniden alınır; son 72 saat **geçici**. `next_actions` kuralı ve sayfalama `meta-history`'deki gibi.
   **Ölçüm bağlamı** (`account_id, timezone, currency, result_definition, metric_definitions, attribution_window, action_report_time`)
   zorunlu; doğrulanamayan alan `null` + `null_reasons`. → `metrics_ingest(profile_id, rows, source="meta_mcp", measurement_context)`.
   Uyumsuz tanımlı satır tüm içe almayı geri alır; hangi ayarın gerektiği kullanıcıya/devam notuna yazılır.
   **CSV:** kullanıcı dışa aktarımı → `meta_tools.py csv-check` → `metrics_import_csv`.
3. **Test yapısı tespiti (6.3):** kampanya/reklam seti/bütçe/teklif `ads_get_ad_entities`; test durumu `ads_experiment_list_tests`,
   `ads_experiment_abtest_get_test` (okunabiliyorsa). Okunamıyorsa test kimliği, reklamları ve başlangıç/bitiş kullanıcıdan Ads Manager
   ekranı/dışa aktarımıyla doğrulanır. A/B testinde (1.5.0) çalışma salt okumayla okunmadan `ab_test` yazılmaz (sunucu reddeder:
   `meta_test_id` + `study_read`); çalışma bittiğinde sonucu (`winner_result` vb.) okunup koçluk kopyasına `extra.ab_test =
   {study_id, winner_concept, confidence?}` olarak verilir (kazanan hücre konsepte eşlenerek; eşlenemezse yazılmaz). Test sürerken
   bütçe/kitle/kreatif değişikliği önerilmez (araç tanımı da uyarır). → `cycle_set(profile_id, cycle_id, {structure_detected: bootstrap|creative_test|ab_test|deviated|unverified,
   structure_evidence_json: {source, at, evidence}, meta_test_id?, test_start?, test_end?})`. Eşit harcama kontrollü test kanıtı değildir.
   Turun planında A/B testi varsa (`budget_plan_json.ab_test`) konsept başına ayrı kampanya/set sapma sayılmaz: çalışma okunana kadar yapı
   `unverified` kalır, okununca `ab_test`.
   Sapma (konsept başına ayrı reklam seti, kreatif test açılmamış, maliyet hedefi/teklif sınırı/ROAS hedefi) → navigator üst satırı +
   nasıl düzeltileceği + turun hükümleri "doğrulanmamış yapı". `scale_layer_get` ile kayıtlı ölçekleme kampanyası/seti
   sapma sayılmaz ve test yapısı tespitine girmez; üyelerinin satırları test hesabından ayrı tutulur (yalnızca harcama, frekans,
   yorgunluk ve limit uyarısı). Kayıtsız ikinci kampanya ya da ölçekleme setine eklenmiş yeni (test edilmemiş) reklam sapmadır.
   Onaylı ölçekleme maddeleri (katman açma, gönderiyle taşıma, test setinde duraklatma) 6.11 ile salt okuma doğrulanır; taşınan
   reklamın gönderi kimliği `ads_get_creatives` ile okunup maddedeki kimlikle karşılaştırılır. Doğrulanan taşıma sonrasında katman
   `scale_layer_set` ile kaydedilir (coach 7); kayıt yapılana kadar ölçekleme reklamının satırları test setininkilerden ayrılamaz,
   bu yüzden kayıt doğrulamayla aynı oturumda yapılır.
4. **Değişmez girdi kopyası:** uyarı/takip hesabından **önce** `decision_input_snapshot(profile_id, campaign_id, cycle_id, kind="daily_track")`
   → dönen yol/hash; hesap yalnızca bu kopyadan: `PY PR/scripts/analytics/coach.py --snapshot <kopya> --out reports/c<tur>-track-<tarih>.json`
   (veri kalitesi, yorgunluk, limit uyarıları bölümleri kullanılır; S16 hükmü burada verilmez).
5. **Veri kalitesi (6.5):** eksik gün; harcama/gösterim tutarsızlığı; `video_3s` türetme payı; adı `creative_key`'e eşleşmeyen reklam; ani
   CPM sıçraması; karışık ölçüm tanımları. Sorunlu veri hükme girmez.
6. **Olgunluk:** `maturity_days = max(3, atıf penceresi gün + raporlama gecikmesi)` (gecikme başlangıçta varsayımsal 3); test aralığı
   `[test_start, test_end)` hesap saat diliminde; günlük veride karışık sınır günleri kontrollü karşılaştırmadan çıkar (toplam harcamada
   tam sayılır). G3'te "ilk sinyal" notu yalnızca **yön** etiketli, karar değil.
7. **Yorgunluk ve anomali (6.7):** 7 günlük hook oranı ilk 3 gün bazının %20'den fazla altında · frekans artarken CTR düşüyor · CPM bazın
   1,5 katı. İlk kez gösterim oranı alanı yoksa "mevcut değil". Aynı döneme denk gelen rakip olayı (fark görüntüsü) yalnızca bağlam;
   neden olarak sunulmaz. `ads_insights_anomaly_signal` bağlam olarak okunabilir.
7b. **Kıyas (bağlam; ilk harcamadan sonra, günde en fazla bir kez):** test reklam setleri için
   `ads_insights_industry_benchmark(ad_account_id, entity_ids=[reklam seti], date_preset="last_7d")` ve
   `ads_insights_auction_ranking_benchmarks` (salt okuma, izin listesinde). Dönen değerler
   `benchmarks_upsert(profile_id, items=[{kind: "industry"|"auction_ranking", metric, value, context: {source_tool, date_range,
   peer_group, entity_id}}])`. Maliyet metriğinde "kıyasın üstü" daha iyi demektir (aracın kendi tanımı); kullanıcıya bu yönle söylenir.
   "Veri yok" dönerse hiçbir şey yazılmaz ve "kıyas yok" denir; değer uydurulmaz, başka hesaptan taşınmaz. Kıyas **önsel değildir**
   (önsel yalnızca aynı profilin geçmişinden, 6.6) ve hüküm vermez; yalnızca koçluk raporunda bağlam satırıdır.
8. **Bütçe ve zarar-risk (6.3, 6.10):** her aktif reklamın (eski turlarınkiler dahil) ilk yayından biriken harcaması kendi onaylı sınırıyla;
   kampanya toplamı `budget_total` ile. Sınıra ulaşma/aşma ya da kalan tutarın bir sonraki kontrole yetmemesi → sonuç sayısı 10'un altında,
   hatta sıfır olsa da **beklemeden** `action_items_set(profile_id, campaign_id, items=[{action:"<Ads Manager adımı>", reason_kind:"limit",
   target_meta_id, before, after, evidence:{input_snapshot:<yol/hash>}}], cycle_id)` (`proposed`) + bildirim + navigator üst satırı.
   Bu "istatistiksel kaybeden" değildir; ölçüm sorunu varsa "zarar kesin" denmez. Aynı hedef/sınır/onay sürümü için açık madde kopyalanmaz.
   Zamanlanmış iş onay vermez; kullanıcı onaylarsa `decision_log` + `action_item_set_status(item_id, "approved", approval_text)`.
8b. **Müşteri adayı sonrası (1.5.0, `result_type='lead'`):** haftada bir kullanıcıya: "Geçen hafta gelen adaylardan kaçına ulaştınız,
   kaçı nitelikli, kaçı satın aldı (varsa ciro)?" → `lead_outcome_set(profile_id, campaign_id, period_start, period_end, leads,
   reached?, qualified?, won?, revenue?, currency?, source=crm_export|meta_leads_center|manual)`. Bilinmeyen aşama boş bırakılır (sıfır
   yazılmaz); dönemler çakışmaz; aday kişisel bilgisi istenmez. Meta'nın saydığı aday ile kayıttaki aday belirgin farklıysa (ör. formlar
   indirilmemiş) rapor bunu yazar.
9. **Elle satış ve talep (6.2):** navigator "Satış gir" → `sales_add(profile_id, campaign_id, period_start, period_end, units,
   revenue, source_note, channel, kind)` — kanal (`shopier | site | instagram_dm | whatsapp | kurumsal | magaza | diger`) ve tür
   (`sale` | `lead`: ör. "40 adet buket" DM isteği). Atıf varsayımı ve tarih aralığı raporda; kreatiflere dağıtılmaz; DM/WhatsApp/kurumsal
   Meta'da görünmez, raporda kanala göre ayrı yazılır. Mesajla satış yapan profilde günlük takipte kullanıcıya bir kez sorulur:
   "Dünkü mesaj toplamı?" → `dm_daily_set` (`reklam-atolyesi:dm-sales`); cevap yoksa boş bırakılır, tahmin yazılmaz. Mağaza
   sipariş dışa aktarımı geldiyse `sales_import_csv` (`reklam-atolyesi:data-connection` 7).
10. **Uygulandı mı (6.11):** onaylı maddeler Meta'dan okunur (reklam durumu, bütçe, harcama limiti, bitiş) →
    `action_items_verify(profile_id, campaign_id, readings=[{item_id, source:"meta_mcp"|"user_evidence", observed:{…}}])`. Okunamıyorsa
    kullanıcı kanıtı; yoksa beklemede kalır. "3 adımdan 2'si uygulandı" üst satıra; uygulanmayan karar raporda işaretlenir.
11. Günlük özet devam notuna (otomatik takip, etkileşimli S03 notunun üzerine yazmaz); uyarı yoksa bildirim yok.
12. Test bitip olgunluk penceresi dolunca (ya da plan günü) S16'ya geçilir: `stage_complete(profile_id, "S15", outputs=[{path: son takip
    raporu}], summary, campaign_id, cycle_id)`.

## Çıktılar
`metrics_daily` (bağlam + parmak izi), `cycles.structure_*`, takip raporu JSON'ları ve girdi kopyaları (`reports/`), `action_items`
(önerilen sınır adımları; doğrulama sonuçları), `sales_manual`, devam notu, uyarılar.

## Kontroller
- Meta platform kuralı (sınır, format, güvenli alan, politika) kullanıldıysa durumu `ref-legal-tr-meta` §7'ye göre belli: resmi
  (bağlantı + tarih), yerel koruma kuralı ya da teyit edilmedi; teyit edilmeyen kural kesin diye sunulmadı.
- Hiçbir Meta yazma ya da ücretli araç çağrılmadı; zamanlanmış işte soru sorulmadı.
- Uyarılar sabit girdi kopyasından üretildi; kopya yazılamadıysa uyarı tamamlandı sayılmadı.
- Eski veriyle güncel güvence verilmedi; CSV profilinde otomatik doğrulama iddiası yok.

## Kapı mesajı
Kapı yoktur. Kullanıcıya/üst satıra: "Tur N · G<k>/<test günü> · veri: <tarih> (son 72 saat geçici). Uyarılar: … Uygulama listesi: x/y
uygulandı. Yapı: <doğrulandı | sapma: …>."
