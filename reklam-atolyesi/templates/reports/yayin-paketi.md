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
{{Sonraki tur (creative_test): aynı reklam setinde, yayındaki bir reklamdan başlatılan kreatif test; test bütçesi ≤ ~%20; süre 7 gün; "En yüksek hacim".}}
Adım adım: {{…}} (sayı/bütçe/süre kısıtları hesabın güncel ekranında doğrulanır)

## Harcama ve bitiş sınırları (insan uygular)
- Kampanya toplam sınırı: {{budget_total}} · gerçekleşen: {{…}} · kalan: {{…}}
- Uygulanacak harcama limiti ve/veya bitiş tarihi: {{…}} (tarih/günlük bütçe tahmini tek başına kesin parasal tavan değildir)
- Reklam başı zarar-risk sınırı: {{tutar}} — sınıra ulaşan reklam için durdurma önerisi üretilir

## AI açıklaması
{{AI içeren varyasyonlar için Ads Manager'ın sunduğu açıklama/etiket seçenekleri; kaynak ve kontrol tarihi ref-legal-tr-meta'da}}

## Planlanan takvim
- Planlanan yayın (launch_at): {{tarih}} · günlük takip 09:00 · karar hazırlığı plan günü sabahı ({{tarih}})

## Yayından sonra (kullanıcı)
"Yayına aldım" de: reklam kimliklerini (Ads Manager'dan) ve gerçek yayın saatini yaz; sistem salt okuma ile karşılaştırır.
