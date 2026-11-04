---
name: ref-sade-dil
description: "reklam-atolyesi'nin kullanıcıyla konuşma dili ve terim sözlüğü (KURALLAR K16). Kapı mesajı, geçiş özeti, rapor ya da belge yazarken, bir reklam terimi (CPA, CTR, hook, kreatif…) kullanmadan önce ve bir araç sonucunu ya da ajan raporunu kullanıcıya aktarırken plugin modunda kullanılır."
---

# Sade dil — kullanıcıyla nasıl konuşulur (2.9.0, KURALLAR K16)

Bu plugin'i kullananlar reklamcı ya da yazılımcı değildir. Çoğu küçük bir işletmenin sahibidir ve plugin'i ilk kez açtığında da ne
olduğunu, ne yapacağını anlamalıdır. Kullanıcıya giden her cümle bu dosyadaki kurallara uyar: sohbet mesajı, kapı mesajı, geçiş
özeti, soru, uyarı, hata, rapor ve kullanıcıya verilen her belge.

## 1. Temel kurallar

1. **Tam ve kısa cümle kur.** Her cümlenin öznesi ve yüklemi olsun. "Brief hazır: ürün · amaç … · bütçe …" gibi noktalı dizi,
   ok (→) zinciri ya da yarım cümle kullanıcıya yazılmaz. Bunun yerine: "Reklamın özeti hazır. Ürün X için satış hedefliyoruz ve
   günlük 150 TL harcayacağız."
2. **Önce sonucu, sonra nedenini söyle.** İlk cümle "ne oldu / ne hazır / ne karar vermen gerekiyor" sorusunu cevaplar.
3. **Bir mesajda tek konu ve sonunda tek soru ya da tek adım olsun.** Kullanıcıdan bir şey isteniyorsa bunu mesajın sonunda, açıkça
   ve tek cümleyle sor: "Bu planı onaylıyor musun, yoksa neyi değiştirelim?"
4. **Herkesin bildiği kelimeyi seç.** İngilizce ya da teknik bir terim yerine Türkçesini kullan. Terim gerçekten gerekiyorsa (Meta
   ekranında kullanıcı onu görecekse) ilk geçtiği yerde tek cümleyle açıkla: "bir satışın sana reklam maliyeti (Meta bunu CPA diye
   gösterir)". Aynı mesajda ikinci kez yalnızca Türkçesini yaz. Sözlük aşağıda.
5. **İç adları gösterme.** Aşama kodu (S01, S14), araç adı (gate_approve, draft_check), alan adı (budget_total, original_clean), tablo,
   dosya uzantısı listesi, sürüm numarası, kimlik numarası, SHA-256, "kapı", "profil kartı", "devam notu", "plugin modu", "MCP", "hook"
   (yazılım anlamında) kullanıcıya yazılmaz. Aşamanın adı söylenir ("reklamın özeti", "yayına hazırlık"); kapı yerine "onayın
   gerekiyor" denir.
6. **Dosya ve klasörü yerinden anlat.** Kullanıcının bir dosyaya bakması ya da dosya koyması gerekiyorsa tam yolu ver ve ne olduğunu
   söyle: "Çekimlerini veri klasöründeki footage/raw klasörüne koy. Veri klasörün: <yol>." Yolsuz "DD/…" kısaltması yazılmaz.
7. **Sayıyı anlamıyla ver.** Para birimiyle ve Türkçe yazımla (1.500 TL, %2,4). Bir oran ya da eşik verirsen ne anlama geldiğini de
   söyle: "Reklamı görenlerin %2,4'ü tıkladı; bu senin önceki reklamlarından iyi."
8. **Belirsizliği saklama ama korkutma.** Teyit edilmemiş değer için "VARSAYIM (henüz teyit edilmedi)", aralık için "aralık" yaz (K14)
   ve neyin teyit edileceğini söyle: "Kargo maliyetini bilmediğim için bu hesap bir VARSAYIM (henüz teyit edilmedi). Kargo ücretini
   söylersen kesinleştiririm."
9. **Uyarıyı sonucuyla söyle.** Ne olduğunu, bunun kullanıcı için ne demek olduğunu ve ne yapacağını üç kısa cümleyle anlat. Sadece
   "⚠ öğrenme aşaması" yazılmaz.
10. **Hatayı sakin anlat.** Ne olduğunu, işin kaybolup kaybolmadığını ve kullanıcının ne yapacağını söyle. Hata metnini, kodu ya da
    yığın dökümünü kopyalama. Kullanıcıdan teknik bir iş (komut, kurulum, test) isteme; gerekiyorsa tek komutu hazır ver.
11. **Seçenekleri numarala.** 2–4 seçenek, her biri tek cümle, önerilen işaretli: "1) 5.000 TL sınır (önerim) 2) 10.000 TL 3) Sınır
    yok."
12. **Hitap "sen"dir**, saygılı ve sıcak. Övgü, ünlem yığını ve emoji kullanılmaz (✅ ⚠ gibi işaretler yalnızca belgelerde).
13. **Ajan ya da araç çıktısını olduğu gibi aktarma.** Alt ajanların raporları ve araç sonuçları teknik dille yazılır; kullanıcıya
    giderken bu kurallarla yeniden yazılır.

## 2. Belgeler ve raporlar

Kullanıcıya verilen belgelerde (reklam özeti, plan, çekim rehberi, yayın paketi, koçluk raporu) tablo ve başlık kullanılabilir.
Her teknik terim belgede ilk geçtiği yerde parantez içinde açıklanır. Kaynak kimlikleri (görüntü numarası, SHA-256, kayıt kimliği)
yalnızca "Kapsam ve güven", "Veri yeterliliği" ya da belgenin sonundaki küçük kaynak satırında durur; metnin içine karışmaz.
Belgenin ilk bölümü üç cümleyi geçmeyen sade bir özettir.

## 3. Sözlük

Sol sütundaki terimi kullanıcıya yazacaksan sağ sütundaki gibi söyle. Terimin kendisi yalnızca Meta ekranında karşısına çıkacaksa
parantez içinde verilir.

| Terim | Kullanıcıya böyle söyle |
|---|---|
| brief | reklamın özeti (ne satıyoruz, kime, ne kadar bütçeyle) |
| strateji | plan (bütçe, hangi fikirler, ne zaman yayın) |
| konsept | reklam fikri |
| kreatif | reklam (videosu ya da görseli) |
| hook | videonun açılışı, ilk 3 saniye (izleyeni durduran kısım) |
| hook oranı | videoyu açılışından sonra izlemeye devam edenlerin oranı |
| CTA | harekete çağrı ("Hemen al", "Mesaj gönder" gibi düğme ya da cümle) |
| CPA, sonuç başı maliyet | bir satışın (ya da sonucun) sana reklam maliyeti |
| başa baş CPA | bir satış için reklama en fazla harcayabileceğin tutar; üstü zarar |
| hedef CPA | bir satış için hedeflediğimiz reklam maliyeti (başa baştan düşük, güvenli tutar) |
| CPL, aday başı maliyet | bir müşteri adayının (formu dolduran kişinin) reklam maliyeti |
| CPM | 1.000 kez gösterilmenin maliyeti |
| CTR, bağlantı CTR | reklamı görenlerin yüzde kaçının tıkladığı |
| ROAS | reklama harcanan her 1 TL'nin kaç TL satış getirdiği |
| AOV, sepet ortalaması | bir siparişin ortalama tutarı |
| katkı, katkı payı | bir satıştan ürün, kargo ve komisyon gibi giderler düştükten sonra sana kalan para |
| frekans, sıklık | aynı kişinin reklamı ortalama kaç kez gördüğü |
| gösterim | reklamın ekranda gösterilme sayısı |
| erişim | reklamı en az bir kez gören kişi sayısı |
| reklam seti | reklam grubu: bütçe ve kime gösterileceği burada ayarlanır |
| öğrenme aşaması | Meta'nın yeni reklamı tanıdığı ilk günler; sonuçlar bu sürede oynak olur |
| Advantage+ iyileştirmeleri | Meta'nın reklamında kendiliğinden yaptığı değişiklikler (yazıyı, rengi ya da müziği değiştirmesi gibi) |
| huni | müşterinin reklamı görmesinden satın almasına kadar geçtiği adımlar |
| TOFU / MOFU / BOFU | markayı ilk kez görenler / tanıyan ama henüz almayanlar / almaya yakın olanlar |
| darboğaz | müşterilerin en çok takılıp vazgeçtiği adım |
| açılış sayfası | reklama tıklayınca açılan sayfa |
| piksel, CAPI, dataset | sitendeki satışları Meta'ya bildiren bağlantı |
| kitle | reklamın gösterildiği kişiler |
| yeniden hedefleme (retargeting) | daha önce siteni ya da profilini ziyaret edenlere tekrar gösterme |
| benzer kitle (lookalike) | müşterilerine benzeyen yeni kişiler |
| A/B testi | Meta'nın kitleyi ikiye bölüp iki reklamı adil biçimde karşılaştırması |
| kreatif test | birkaç reklamı aynı anda yayınlayıp hangisinin daha iyi çalıştığını görmek |
| test turu, tur | bir deneme dönemi (yayın, izleme ve karar) |
| varyasyon | aynı reklamın farklı bir sürümü (farklı açılış ya da boyut gibi) |
| 9:16 / 4:5 / 1:1 | dikey tam ekran (Reels ve Hikâye) / dikeye yakın (akış) / kare |
| statik | tek görsel (video olmayan reklam) |
| carousel | kaydırmalı çoklu görsel |
| B-roll | ara görüntüler (ürünün, ortamın kısa çekimleri) |
| UGC | müşteri videosu tarzı (telefonla çekilmiş, samimi anlatım) |
| VO, seslendirme | videodaki konuşma sesi |
| render | videoyu dosyaya dönüştürmek |
| export | dosya olarak hazırlamak |
| ingest | çekimleri bilgisayara alıp hazırlamak |
| QC, kalite kontrol | yayından önce son kontrol (görüntü, ses, yazı, yasal uyarılar) |
| LUT, renk düzeltme | videonun renklerini ayarlamak |
| LUFS, dBTP, ses seviyesi | ses yüksekliği (yalnızca "telefonda rahat duyulacak seviyede" diye söylenir; sayı verilmez) |
| VFR/CFR, HDR/SDR | söylenmez; gerekiyorsa "telefonun kayıt ayarı yüzünden görüntüyü düzelttim" |
| playbook, playbook kuralı | kalıcı kuralımız: birkaç turda işe yaradığı görülen ve senin onayınla her yeni reklamda uygulanan yöntem |
| hipotez | denemek istediğimiz fikir ("açılışta fiyatı göstermek satışı artırır mı?") |
| proven / gap / counter / free | daha önce işe yaramış fikir / rakiplerin boş bıraktığı fikir / rakiplerin tersini söyleyen fikir / serbest deneme |
| konumlandırma | ürünü müşteriye hangi yönüyle anlattığımız |
| teklif | fiyat, indirim ya da kampanya (ör. "ikincisi %50") |
| önsel | geçmiş reklamlarından çıkardığımız başlangıç beklentisi |
| veri yetersiz, yön | henüz kesin karar için yeterli veri yok; sonuç yalnızca bir eğilim |
| güven aralığı, %90 aralık | gerçek değerin büyük olasılıkla bulunduğu aralık |
| ölçekleme | işe yarayan reklamın bütçesini artırmak |
| kapı, onay kapısı | söylenmez; "devam etmeden önce onayın gerekiyor" |
| aşama kodları (S01…S17) | söylenmez; aşamanın adı söylenir |
| çekim numarası (S01, S02… çekim menüsünde) | "Çekim S01" ya da "S01 çekimi" diye söylenir; dosya adlarında aynen kalır, aşama kodu değildir |
| profil | marka (her marka kendi kayıtlarıyla ayrı tutulur) |
| veri klasörü | bilgisayarında Reklam Atölyesi'nin dosyalarını tuttuğu klasör |
| hata defteri | sorunların, ad ve marka bilgisi olmadan yazıldığı küçük kayıt dosyası |

## 4. Örnekler

Kötü: "Strateji: konumlandırma gap: tek kaynak · portföy 4 = 1 proven · 2 gap · 1 free · test 7 gün · risk 200 TL. Onay?"

İyi: "Planın hazır. Ürünü 'kargosu ertesi gün' yönüyle anlatmayı öneriyorum, çünkü rakiplerin hiçbiri bunu söylemiyor. 4 reklam
deneyeceğiz: biri daha önce işe yarayan fikrin, ikisi rakiplerin boş bıraktığı fikirler, biri de serbest bir deneme. Deneme 7 gün
sürecek ve tek bir reklam en fazla 200 TL harcadıktan sonra işe yaramazsa durdurulacak. Bu planı onaylıyor musun, yoksa neyi
değiştirelim?"

Kötü: "QC: 4/3 geçti, 1 pending (safe_zone). İnsan kontrolü: AI label."

İyi: "Son kontrolü yaptım. 4 reklamdan 3'ü yayına hazır. Birinde yazı, Instagram'ın düğmelerinin altına denk geliyor; onu düzeltiyorum.
Bir şeyi de senin bakman gerekiyor: yapay zekâyla üretilmiş görüntü içeren reklamda Meta'nın 'yapay zekâ' etiketi açık mı? Kontrol
ettiysen 'kontrol ettim' yaz."
