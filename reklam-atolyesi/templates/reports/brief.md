# Brief — {{kampanya}} · tur {{tur}}

> Şablon (spec 4.1 S01, 6.2, 6.3). `{{…}}` alanları kampanya verisinden doldurulur; boş kalan alan "bilinmiyor" yazılır, tahmin yazılmaz.

## Kampanya
- Ürün: {{ürün}} (tanışma: {{ürün_tanışma_durumu}})
- Kampanya amacı: {{amaç}}
- Sonuç türü: {{sonuç_türü}} (purchase · lead · messaging · profile_visit · link_click · engagement; lead ise yol: instant_form · website · call)
- Sezon / hedef tarih: {{sezon}} / {{hedef_tarih}}
- Kampanya modu: {{tam_tur_ya_da_hızlı_tur}}

## Toplam Meta harcama sınırı (6.3)
- `budget_total`: {{tutar_ya_da_NULL}} {{para_birimi}} — bu kampanyanın ilk yayınından itibaren BÜTÜN turlarındaki Meta reklam harcamasının üst sınırı; üretim/servis ücretleri dahil değildir. NULL: kullanıcı sınır tanımlamadı (açık karar).
- Kullanıcı teyidi: {{teyit_ifadesi_ve_tarihi}}

## Ekonomi (6.2)
- Başa baş CPA: {{başa_baş}} · hedef CPA (güvenlik payı {{pay}}): {{hedef}} · durum: {{exact|assumed|range|unknown}}
- Varsayımlar (VARSAYIM etiketli): {{varsayımlar}}
{{deneme_kampanyası_ise: "ekonomi VARSAYIMSAL (ürün tanışması atlandı; 17.7)"}}

## Rakip bağlamı
{{S01b atlandıysa: "rakip bağlamı yok — kullanıcı rakip analizini atladı (gerekçe: …)"}}

## Varsayımlar ve açık sorular
- {{…}}
