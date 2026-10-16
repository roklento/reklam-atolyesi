# Strateji — {{kampanya}} · tur {{tur}}

> Şablon (spec 4.6, 6.3, 4.4). (A) otomatik hesap; (B) kullanıcıyla birlikte seçilen stratejik yön. Kapı: ✅ strateji.

## (A) Ekonomi, bütçe ve takvim
| Kalem | Değer |
|---|---|
| Kreatif başına gereken harcama | {{eşik}} gösterim × CPM {{cpm}} / 1000 = {{tutar}} ({{cpm_kaynağı}}) |
| Günlük test bütçesi | {{günlük_test}} ({{ilk tur: reklam seti günlük bütçesi | sonraki turlar: × exploration_share}}) |
| Test günü / tur süresi | {{test_günü}} / {{tur_süresi}} gün |
| İzin verilen test reklamı sayısı | {{n}} (araç sınırı {{araç_sınırı}}) |
| Toplam harcama planı | ek {{ek_tahmin}} · kalan {{kalan}} · sığıyor mu: {{evet/hayır}} |
| Zarar-risk sınırı (reklam başı, kapsam ad_launch_to_stop) | {{tutar}} {{para_birimi}} — onay: {{onay_ifadesi}} |
| Takvim | yayın G0 {{tarih}} · test bitişi {{tarih}} · plan günü {{tarih}} · sonraki yayın {{tarih}} |

Uyarılar: {{bütçe uyarıları}} — Bu bir tahmindir; Meta'nın günlük harcamasının sabit ya da kesin sınırlı olduğu iddia edilmez.

## (B) Stratejik yön
- Konumlandırma: *{{tür}}: {{tek_cümle}}* — ana vaat: {{vaat}} · destekleyen kanıtlanabilir iddia: {{iddia}} · ayrıştığı rakipler: {{rakipler}} · risk: {{risk}} · kaynak: {{etiket}}
- Mesaj sırası: ana vaat → kanıt → teklif → CTA; hook'un taşıdığı: {{…}}
- Açı portföyü ({{n}} reklam): proven {{a}} · gap {{b}} · counter {{c}} · free {{d}} {{birincil doğrulama çifti varsa önce}}
- Teklif tutumu: {{eşleş | değerle ayrış | yalnızca belirli dönemde}} (fiyat/indirim kararı kullanıcınındır)
- Zamanlama: önerilen yayın {{tarih}} ({{gerekçe}})
- Hipotez adayları (S03'te seçilen konseptten doğar): {{…}}
- Dayanılan rakip görüntüsü: #{{snapshot_id}} (SHA-256 {{hash}}) {{ya da "rakip bağlamı yok"}}

## Reddedilen konumlandırmalar (sonraki tur için saklanır)
- {{…}}
