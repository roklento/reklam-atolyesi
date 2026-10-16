---
name: ref-shooting-basics
description: "reklam-atolyesi telefonla çekim temelleri — 7 altın kural, iPhone/Android ayarları, ışık ve ses, kart yapısı, görüntü özelliğine göre ürün riskleri, fotoğraf listesi, teslim."
---

# ref-shooting-basics — telefonla çekim temelleri (spec 5.3)

Rehber **hiç video çekmemiş biri** içindir: her çekim bir kart; terimler ilk geçtiği yerde açıklanır; dil jargonsuz. Teknik dönüşümler
(VFR, HDR) çekimciye yüklenmez; ingest çözer.

## Kurtarılamayan üç şey
Odaksız kare · patlamış beyazlar · hareket bulanıklığı. Rehber bunları önlemeye odaklanır; gerisini kurgu kurtarır (`ref-production-recipes`).

## 7 altın kural
1. **Doğal ışık:** gündüz, pencere yanında, tavan lambası kapalı.
2. **Telefon sabit:** tripod ya da kitap yığını.
3. **Odak ve ışık kilidi:** ekranda ürüne basılı tut (kilit simgesi çıkana kadar).
4. **Zoom yok:** telefonu yaklaştır.
5. **Yavaş hareket:** her hareket en az 5 sn.
6. **Boşluk bırak:** kayda bas, 3 sn bekle, çek, 3 sn bekle, durdur.
7. **Her çekimi en az 3 kez al.**

## Ayrıntılar
Ürün pencereye yan; güneş vuruyorsa tül; gölge tarafına beyaz karton; akşam gerekiyorsa tek lamba. Ekrandaki güneş simgesiyle parlaklığı biraz
düşür (beyazlar patlamasın). Ya kamera ya ürün hareket etsin, ikisi birden değil. Ürün elle gösterilecekse eller temiz, dikkat dağıtan aksesuar
yok. Ürün ortada, üstte ve altta yazı boşluğu (9:16'da üst %14, alt %35 yazıya ayrılır). Lens silinmiş, telefon ≥ %80 şarj, ≥ 20 GB boş,
uçak modu açık.

## Telefon ayarları
- **Ortak:** 4K 30 fps (yavaş çekim istenen çekimde 4K 60), **HDR video kapalı**, dikey, filtre/güzelleştirme yok, ızgara açık.
- **iPhone (örnek menü yolu; sürüme göre değişebilir):** Ayarlar → Kamera → Video Kaydı → 4K 30 fps · Ayarlar → Kamera → Biçimler/Video →
  HDR Video kapalı · Kamera uygulamasında ekrana basılı tutarak AE/AF Kilidi · Izgara: Ayarlar → Kamera → Izgara.
- **Android (üreticiye göre değişir; örnek):** Kamera → Ayarlar → Video boyutu → UHD/4K 30 fps · HDR10+/HDR video kapalı · Ekrana basılı
  tutarak odak/pozlama kilidi · Izgara çizgileri açık · Video sabitleme varsa açık.
Kart, kullanıcının telefon modeline göre "ayarı bulamazsan ekran görüntüsünü at" yedeğiyle yazılır.

## Ses (yalnızca ses niyeti gerektiren çekimlerde)
Niyet "çekimdeki ses" ya da "kullanıcının sesi" ise: telefon konuşana/ses kaynağına yakın, sessiz ortam, müzik ve TV kapalı, gerekiyorsa
ucuz bir yaka mikrofonu. Kullanıcının seslendirmesi: telefonun ses kaydı uygulamasıyla, sessiz bir odada, **3 alım**. Diğer çekimlerde ses
dikkate alınmaz; efektleri sistem üretir.

## Kart yapısı (genel kurallar ve ürün tarifi aynı yapıda)
`ne çekiyoruz` · `telefon nereye` · `ne yap` · `ne zaman dur` · `başardın mı` (+ ürün tarifinde `risk`, `hangi genel kuralı neden değiştiriyor`).
`products.shoot_profile_json = {"cards":[{risk, what, phone, do, stop_when, success_check, overrides_rule, why}]}`.

## Ürün riskleri — kategoriye göre değil **görüntü özelliğine** göre (örnek türler; hiçbiri varsayılan değildir)
| Görüntü özelliği | Tipik uyarlama |
|---|---|
| Kendisi ışık yayan ya da çok parlak yüzey | pozlama ona kilitlenir ve düşürülür; doğal ışık kuralı yerine ortam ışığı + dolgu |
| Yansıtıcı ya da şeffaf ambalaj | yansıma kontrolü, açı değişimi, siyah/beyaz karton |
| Çok küçük ayrıntı ya da yazı | makro mesafe, sabit odak, tripod |
| Hareketli, akışkan ya da kısa ömürlü an | 60 fps, birden çok alım, an öncesi kayıt |
| Yalnızca belirli ortamda/ışıkta anlam kazanan kullanım | kullanım ortamının tarifi |
| Kullanımla görünüşü değişen ürün | önce/sonra setleri, aynı kadraj ve ışık |
Fotoğraf/videodan risk çıkarılamıyorsa kart üretilmez; genel kurallar geçerlidir. Çatışmada **ürün tarifi** geçerlidir.

## Fotoğraf listesi
Konsept başına 5–8 fotoğraf, video oturumunda ve telefonun **fotoğraf modunda** (video karesi değil): ürün tek başına, kullanımda,
ayrıntı, statik reklam ve carousel için yazı boşluklu kadrajlar.

## İzin ve teslim
Görüntüde ya da seste tanınabilir kişi (çekimci dahil) → kullanım izni kaydı. Teslim sıkıştırmadan (WhatsApp değil; Drive, AirDrop,
kablo), dosya adı çekim numarasıyla; videolar `footage/raw/`, fotoğraflar `photos/raw/`.

## Hareket dili kaynağı
Kamera hareketi/geçiş adları ve tarifleri: `PR/vendor-skills/ai-product-video/references/shots/` (önce `OVERRIDES.md`); amatör karta
çevrilirken her hareket "telefonu nasıl tutar/oynatır" cümlesine indirgenir.
