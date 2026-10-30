# Yayın paketi — {{kampanya}} · tur {{tur}}

> Şablon (spec 4.1 S14, 5.18, 6.3, 9.2, bölüm 10). Plugin Meta'ya YAZMAZ: yayın, bütçe ve limitleri insan Ads Manager'da uygular.
> Paket onayı yayın yapıldığı anlamına gelmez; gerçek yayından sonra `launch_confirm` ile reklam kimlikleri, gerçek tarih ve teyit kaydedilir.

## Yüklenecek dosyalar (yalnızca test kreatifleri; yedekler listede yok)
| creative_key (= Meta reklam adı) | 9:16 dosyası | 4:5 dosyası | Medya | AI içeriği | Risk sınırı |
|---|---|---|---|---|---|
| {{…}} | | | | evet/hayır | {{tutar}} |

## Metinler
- Birincil metin / başlık / açıklama / CTA (yalnızca izinli iddialar; fiyat satış sayfasıyla birebir): {{…}}

## Ads Manager kurulum talimatı
{{İlk tur (bootstrap): tek kampanya, tek reklam seti, teklif stratejisi "En yüksek hacim"; turun konseptleri birlikte.}}
{{Sonraki tur (creative_test): aynı reklam setinde, yayındaki bir reklamdan başlatılan kreatif test; test bütçesi ≤ %20 (Meta önerisi); 2–7 test reklamı; süre 7 gün; "En yüksek hacim".}}
{{Huni turu (round_mode=funnel): aşama reklamları aynı sette; ayrı set ya da yeniden hedefleme kitlesi kurulmaz. Kitle segmentleri (raporlama için, hedeflemeye eklenmez): etkileşime geçmiş kitle {{tanım}} · mevcut müşteri {{tanım}} · {{tanımlı | hesapta görünmüyor}}}}
Adım adım: {{…}} (sayı/bütçe/süre kısıtları hesabın güncel ekranında doğrulanır)

## Advantage+ kreatif iyileştirmeleri (her reklamda kontrol)
Meta bazı iyileştirmeleri varsayılan açar ve yüklenen metni/görseli ayarlayabilir ([resmi](https://www.facebook.com/business/help/1082295769403815)).
- Nereye bakılır: reklam kurulumunda "İyileştirmeler" + önizlemede Genişlet → gelişmiş önizleme → Advantage+ kreatif sekmesi (bazıları yalnızca burada).
  Yayındaki reklamda: Reklamlar → reklam → Düzenle → Advantage+ kreatif.
- {{Kreatif testi / A/B testi turu: metin, görsel, müzik ve varış yeri (ürün gezinme, site bağlantıları) iyileştirmelerini KAPAT — test tek değişkenli kalsın, QC'den geçen sürüm yayında aynı kalsın.}}
- {{İlk tur / ölçekleme: iyileştirmeler senin seçimin; metin/görsel değiştirenler QC'nin denetlemediği sürümler üretir.}}
- Ürün gezinme: 28.10.2026'dan beri mevcut reklamlarda varsayılan açık olabilir (Meta bildirimi); Ads Manager bildirimine ve reklamın varış yeri ayarına bak.
- Yayından sonra açık kalanları adıyla yaz: {{…}}

## Harcama ve bitiş sınırları (insan uygular)
- Kampanya toplam sınırı: {{budget_total}} · gerçekleşen: {{…}} · kalan: {{…}}
- Uygulanacak harcama limiti ve/veya bitiş tarihi: {{…}} (tarih/günlük bütçe tahmini tek başına kesin parasal tavan değildir)
- Reklam başı zarar-risk sınırı: {{tutar}} — sınıra ulaşan reklam için durdurma önerisi üretilir

## AI açıklaması
{{AI içeren varyasyonlar için Ads Manager'ın sunduğu açıklama/etiket seçenekleri; kaynak ve kontrol tarihi ref-legal-tr-meta'da}}

## Planlanan takvim
- Planlanan yayın (launch_at): {{tarih}} · günlük takip 09:00 · karar hazırlığı plan günü sabahı ({{tarih}})

## Yayından sonra (kullanıcı)
"Yayına aldım" de: reklam kimliklerini (Ads Manager'dan), gerçek yayın saatini ve açık kalan Meta iyileştirmelerini (yoksa "hepsi kapalı") yaz; sistem salt okuma ile karşılaştırır.
