---
name: ref-metrics-math
description: "reklam-atolyesi koçluk matematiği — metrikler, ekonomi, bütçe/matris, test penceresi ve olgunluk, Beta-Binom/Gamma, eşikler, hüküm dili, yorgunluk, kalibrasyon, bağımsız doğrulama."
---

# ref-metrics-math — metrikler ve matematik (spec bölüm 6)

Uygulama kodu: `PR/scripts/analytics/{budget,bayes,coach,charts,report,calibration}.py` ve `ad-memory` (`decision_input_snapshot`,
`metrics_*`, `prediction_*`, `calibration_get`). Bu skill yöntemi ve dili tanımlar; hesap her zaman koddan ve sabit girdi kopyasından yapılır.

## 1. Metrikler (6.1)
| Metrik | Formül | Neyi ölçer |
|---|---|---|
| Hook oranı | 3 sn izlenme / gösterim | ilk saniyeler durduruyor mu |
| Tutma oranı | ThruPlay / 3 sn izlenme | hikâye tutuyor mu |
| Bağlantı CTR | bağlantı tıklaması / gösterim | teklif ilgi çekiyor mu |
| CVR | satın alma / bağlantı tıklaması | sayfa ve teklif ikna ediyor mu |
| CPA | harcama / satın alma | satış başına maliyet |
| ROAS | gelir / harcama | getiri |
| CPM | harcama / gösterim × 1000 | erişim maliyeti |
| Frekans | gösterim / erişim | aynı kişiye tekrar |
- 3 sn izlenme reklam düzeyinde gelmez: `amount_spent / cost_per_video_view` ile türetilir (türetme payı veri kalitesinde raporlanır).
- Hüküm **sonuç türüne** göre verilir; hook, tutma, CTR teşhis metrikleridir. Üst huniye dayanan hüküm açıkça yazılır.
- **Huni aşaması (1.9.0):** aşaması olan konsept kendi aşama metriğiyle teşhis edilir — TOFU hook ve tutma; MOFU bağlantı CTR'si,
  açılış sayfası / tıklama, içerik görüntüleme / tıklama; BOFU sepete ekleme / tıklama, ödeme başlatma / tıklama, satın alma başı
  maliyet. Payda her zaman yazılır; olay gelmiyorsa "okunamadı". Farklı aşamaların sonuç maliyeti kıyası keşiftir; huni turunda
  TOFU/MOFU yalnızca satış maliyetiyle kapatılmaz. Aşama kitle değildir; kimin gördüğü yalnızca Meta'nın segment dökümüyle söylenir.
- **Tıklamadan sonra adım adım (2.4.0):** sayfaya ulaşma = açılış sayfası / tıklama; ürünü görme = içerik görüntüleme / açılış sayfası;
  sepete ekleme = sepet / içerik görüntüleme; ödemeye geçme = ödeme başlatma / sepet; ödemeyi tamamlama = satın alma / ödeme başlatma.
  Her adım bir öncekine bölünür (çarpılmaz); okunamayan adım atlanır ve sonraki adım en yakın okunan adıma bölünür (geçmişle kıyaslanmaz).
  Darboğaz yalnızca geçmiş ortalamaya göre (payda ≥ 30, yerel eşik); adımların ham oranları birbiriyle kıyaslanmaz.
- Erişim benzersiz kişidir; reklam/gün erişimleri toplanmaz; dönem frekansı yalnızca Meta'nın tekilleştirilmiş erişimi varsa.
- Huni oranları iç içe koşullu olasılık değildir, **çarpılmaz** (hook × CTR × CVR yok).

## 2. Ekonomi (6.2)
Başa baş CPA = sipariş başına reklam öncesi katkı (net sepet − ürün − satıcı kargosu − komisyon − paketleme − beklenen iade; çift sayma
yok). Başa baş ROAS = sepet / katkı. Hedef CPA = katkı × 0,7 (güvenlik payı). Katkı bilinmiyor/aralık → sonuç varsayım/aralık; katkı ≤ 0 →
pozitif başa baş yok. Satış dışı sonuçta hedef kullanıcı hedefidir. Piksel yoksa elle satış; atıf varsayımı ve tarih aralığı yazılır.

## 3. Bütçe, matris, takvim (6.3, 4.4)
- Kreatif başına gereken harcama ≈ eşik gösterim × CPM / 1000 (hook 1.000, CTR 3.000; CPM kıyas/geçmiş ya da "VARSAYIM").
- Test bütçesi = günlük test bütçesi × test günü (ilk tur: reklam seti günlük bütçesi; sonra × `exploration_share` ≤ 0,2 — yerel üst sınır; Meta'nın resmi önerisi de en fazla %20, `ref-legal-tr-meta` §7).
- İzin verilen test reklamı = ⌊test bütçesi / kreatif başına gereken harcama⌋ (2. turdan itibaren ≤ kreatif test aracı sınırı).
- `test_günü = max(7, 7 × ceil((gereken × n / günlük) / 7))`; önce 7, sonra 14; iki reklam sığmıyorsa üretim bekler; gereken günlük =
  2 × gereken / test günü (sonraki turda ÷ `exploration_share`). `tur = test + 7`; plan günü = test bitişi + 3; yayın = plan + 4.
- CPA kararında konsept başına beklenen satın alma < 10 → geniş aralıklı yön tahmini uyarısı.
- Toplam harcama planı: veri kesiminden `launch_at + cycle_days`'e kadar bütün aktif reklamlar (bekleme/üretim/kayma dahil, aynı set bir
  kez); kalanı aşarsa S02/S14 durur. Bir tahmindir.
- Zarar-risk sınırı: reklam başı onaylı azami harcama (`ad_launch_to_stop`); sonuç sayısından bağımsız durdurma önerisi doğurur.

## 4. Ölçüm penceresi (6.4)
- `measurement_json`: saat dilimi, sonuç türü, atıf penceresi, `action_report_time`, veri kesimi,
  `maturity_days = max(3, atıf günleri + raporlama gecikmesi)` (gecikme başlangıçta 3 VARSAYIM). Son 72 saat en az geçici.
- Test aralığı `[test_start, test_end)` hesap saat diliminde. Günlük satırın günü bütünüyle içerideyse teste girer; **karışık sınır günleri
  kontrollü karşılaştırmadan çıkar** (oranla bölünmez; toplam harcamada tam sayılır). 18:00→18:00 yedi günlük test: 6 tam gün; gece
  yarısı başlangıç: 7 tam gün. Olgunluk `test_end + maturity_days`'e kadar.
- Ölçüm parmak izi: bağlam alanlarının sabit sıralı JSON'unun SHA-256'sı; uyumsuz içe alma reddedilir; aynı tanımdaki sağlayıcı
  düzeltmesi güncel satırı yeniler, eski karar kopyaları değişmez.
- **Değişmez girdi kopyası:** her rapor/uyarıdan önce `decision_input_snapshot`; hesap yalnızca ondan.

## 5. Model (6.6)
- **Oranlar:** önsel aynı profil + `objective`, test öncesi geçmiş; `m` ortalama, `n_eff = min(n_source, n_cap=30)`; `a = max(0.001, m·n_eff)`,
  `b = max(0.001, (1−m)·n_eff)`; yoksa Beta(1,1). Turda dondurulur. Sonsal `Beta(a+başarı, b+payda−başarı)`; %90 eşit kuyruklu aralık;
  geçmişe ve diğer konsepte üstünlük olasılığı (10.000 örnek, tohum 1729, kimliğe göre sıralı girdi). Konsept: aynı koşuldaki pay/payda
  toplanır (hiperönsel yok). Farklı sonuç türü, medya türü, test dönemi/sonrası, atıf ayarı karışmaz; pay > payda olan oran model dışı.
- **Sonuç maliyeti:** doğrulanmış hedef `T > 0`: `s = harcama/T`, `λ ~ Gamma(0.5 + y, rate = 0.5 + s)`, maliyet örnekleri `T/λ`;
  satışta `T` = başa baş CPA ise `P(λ > 1)` başa baş altı olasılığı. Hedef yoksa yalnızca gerçekleşen maliyet.
- **Eşikler:** hook ≥ 1.000 gösterim; CTR ≥ 3.000; maliyet ≥ 10 uygun sonuç; satışta ≥ 2 × başa baş CPA harcama inceleme uyarısıdır.
  Eşik altı → "yön/yetersiz veri": istatistiksel kazanan/büyüt/kaybeden gerekçeli kapat yok (sınır kaynaklı durdurma ayrı).
- Bootstrap ve doğrulanmamış yapı: "Meta'nın dağıtımı altında"; aç kalan (< %10 harcama payı) kaybeden sayılmaz.
- Yayında açık kalan Advantage+ kreatif iyileştirmesi (2.3.0): ilgili konseptin hükmüne "Meta iyileştirmesi açık" eklenir.
- Bunlar model koşullarındaki belirsizlik ölçüleridir; Meta dağıtımının seçim yanlılığını kaldırmaz.

- **Karar metriği raporda yazılır (1.4.7):** üstünlük olasılığı hook oranı üzerindendir ve "tüm konseptlerin en iyisi olma" olasılığıdır
  (ikili A>B değil); her olasılığın yanında payda (izlenme / gösterim) ve etiket. Karar sonuç maliyetinden mi üst huniden mi verildi,
  Meta bu turda satış olayı gördü mü — Özet'te tek satır.
- **Reklam mı, teklif mi, sayfa mı? (1.4.7, yerel eşikler):** eşiği geçmiş konseptler arasında ortancanın %80'i altında hook → açılış;
  CTR → teklif/fiyat gösterimi/son kart; kampanyada ≥ 100 bağlantı tıklaması ve görünür web satışı (piksel + elle Shopier/site) sıfır →
  "reklam sonrası şüpheli" (sayfa, fiyat, kargo, güven, teklif); bu turda kreatife satış gerekçeli olumsuz hüküm yazılmaz. DM/WhatsApp/
  kurumsal satış ve talepler kanala göre ayrı yazılır, Meta'da görünmez.

- **Tek satış defteri (1.4.8):** kanal ve dönem başına: kullanıcının verdiği dışa aktarım aralığı elle girişin dönemini tamamen kapsıyorsa dosya; kapsamıyorsa
  ve mesaj kanallarında max(elle, kaynak) — kaynakta olan satış iki kez sayılmaz, kaynağa girmemiş satış kaybolmaz. Meta ↔ mağaza
  yalnızca piksel kanallarında (site, Shopier). Mağaza kaydı varsa tıklama→satış oranı onunla hesaplanır, piksel sayısı eklenmez (aynı satış).
  Meta ↔ mağaza: Meta'nın atfettiği satın alma mağazanın ödenmiş siparişinden belirgin fazlaysa (×1,1 ve ≥ 3) piksel şüphesi.
- **Müşteri adayı (1.5.0):** başa baş aday maliyeti = satış başına katkı × adaydan satışa dönüş oranı; hedef = × güvenlik payı. Aday başı
  maliyet Meta'nın sonuç sayısından; nitelikli/satış başına maliyet kullanıcının dönem toplamından (`lead_outcomes`). Adaydan satışa oran
  Beta(1,1) ile %90 aralık (≥ 3 aday); varsayılan oran aralık dışındaysa hedef yeniden hesaplanır. Hedef maliyet yalnızca teyitli
  ekonomide olasılık üretir.
- **Meta A/B testi (1.5.0):** hücre = konsept; sonuç oranı (sonuç/harcama) Gamma(0,5 + sonuç, 0,5 + harcama/ölçek) ile; her hücrenin en
  düşük sonuç maliyetine sahip olma olasılığı (20.000 çekiliş, sabit tohum). Meta'nın kazananı ayrıca okunur; uyuşmazlık yazılır.
  Hücre başına < 30 sonuç "yön". Kitle rastgele bölündüğü için hüküm dilinde "Meta'nın dağıtımı altında" yoktur.
- **Mesajla satış (1.4.8):** gün/kanal başına günlük toplam (yoksa tek tek kayıtlar); satış/konuşma oranı Beta(1,1) ile %90 aralık
  (≥ 3 konuşma); kampanyaya yalnızca kanıtlı konuşma bağlanır; günlük toplam kampanyaya bölünmez.

## 6. Bağımsız doğrulama ve playbook (6.6, 6.14)
Tur başına en fazla bir birincil hipotez (kol, metrik, yön, karşılaştırma) **test öncesi** sabitlenir. Playbook önerisi: ilk yeterli turda
aynı yön + sonraki turun **tek başına** verisinde aynı yönde üstünlük ≥ 0,95 (oranda iki kola Beta(1,1), maliyette sabit Gamma; keşif
verisi girmez). Üst huni bulgusu önceden seçilmiş alt huni metriğiyle teyit edilmeli. Yaşam boyu hata oranı garantisi verilmez; S17 insan onayı korunur.

## 7. Yorgunluk, anomali, sahne kaybı (6.7, 6.8)
- 7 günlük hook < ilk 3 gün bazının %80'i; frekans ↑ & CTR ↓; CPM ≥ 1,5 × baz → uyarı (neden kesin değil). İlk kez gösterim oranı yalnızca
  sağlayıcı doğrudan veriyorsa.
- Tutma eğrisi p25/p50/p75/p95/p100 + ortalama izlenme; yüzdelik zamanlar plandaki sahnelere eşlenir; **beklenen eğri** (aynı format/süre
  ortanca; yoksa kampanya ortancası) ile karşılaştırılır; çıktı olasılık cümlesidir.
- Metrik → neyi değiştir: hook zayıf → ilk 2 sn; tutma zayıf → orta kısım tempo/sıra; CTR zayıf → son kart, CTA, fiyat gösterimi;
  maliyet zayıf → konsept; frekans + düşüş → yeni hook/konsept değerlendirmesi.

## 8. Kararlar ve koruma (6.10–6.11)
Tut/büyüt/kapat/yenile → somut Ads Manager adımı. Günlük bütçe artışı ≤ %20 (yerel koruma kuralı; Meta'nın yayımladığı bir sınır değil); aynı sette aynı gün tek büyük değişiklik; eşik altına
istatistiksel "kapat" yok. Uygulanma salt okuma ya da kullanıcı kanıtıyla doğrulanır.

## 9. Kalibrasyon ve rekabet (6.13, 6.16)
Tahminler `prediction_log` (girdi kopyası referansıyla), olgun veriyle `prediction_resolve`. ≥ 30 çözülmüş tahminde kalibrasyon ve eşik/
`n_cap` önerisi (kullanıcı onayıyla); azında yalnızca sayı. Rapor sürümleri yeni tahmin sayılmaz. Rekabet bağlamı nedensellik iddiası
taşımaz; rol başına portföy sonucu keşiftir; vekil sinyal kalibrasyonu rol beklentileriyle.
