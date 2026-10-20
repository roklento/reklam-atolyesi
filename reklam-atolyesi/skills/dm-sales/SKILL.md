---
name: dm-sales
description: "reklam-atolyesi mesajla satış — Instagram DM, WhatsApp, Messenger, telefon ve diğer kanallardan gelen konuşmaların kişisel veri tutmadan kaydı (tek tek ya da günlük toplam), konuşma → nitelikli → teklif → satış hunisi, cevap ve teklif taslakları, takip listesi, kampanya bağı yalnızca kanıtla."
---

# dm-sales — Mesajla satış (1.4.8)

## Amaç
Satışın bir kısmı ya da tamamı mesajla kapanan her işletmede (DM'den sipariş, WhatsApp'tan teklif, kurumsal toplu sipariş, telefonla
satış) reklamın sonucunu doğru görmek ve satıcının cevap işini hızlandırmak. Ölçmeden "reklam satış getirmedi" denmez; mesajla gelen
satış ve talep ayrı kanal olarak sayılır.

**Sınırlar (değişmez):**
- Plugin mesaj **okumaz ve göndermez**. Kayıt kullanıcıdan gelir; taslakları kullanıcı kendi uygulamasından gönderir. Otomatik cevap,
  toplu mesaj ya da hesaba bağlanan otomasyon kurulmaz.
- **Kişisel veri tutulmaz.** Konuşma takma kodla izlenir (`M-0001`). Ad, telefon, e-posta, adres, IBAN, kimlik no, @kullanıcı adı
  kaydedilmez; not ve kanıt alanında görülürse sunucu reddeder. Müşteri bilgisi kullanıcının mesaj uygulamasında kalır.
- Konuşmanın reklamla geldiği **yalnızca kanıtla** yazılır (`source="ad"` + `source_evidence` + `campaign_id`); kanıt yoksa `unknown`.

## Ön koşul
Aktif profil. Kampanya şart değildir (organik ve tekrar müşteriler de kaydedilir); kampanya bağı yalnızca kanıtlı konuşmada.

## Girdiler ve bağlam paketi
`dm_summary`, `dm_follow_ups`, ürün kartı (fiyat, teslim süresi, kişiselleştirme kapasitesi, kanıtlanabilir iddialar), strateji
belgesindeki teklif ve problem tanımı, marka sesi (`brand`), satış sayfası (`cta_url`), `sales_orders_summary` (mağaza bağlantısıyla
ödenen DM satışları için).

## Kullanılan hazır skill'ler ve OVERRIDES
Yok.

## Adımlar
1. **Kayıt biçimini seç (bir kez sorulur, profile hafızasına yazılır):**
   - **Tek tek** — kurumsal/toplu talepler, yüksek tutarlı ya da reklamla geldiği görünen konuşmalar; az sayıda konuşma alan hesaplar.
   - **Günlük toplam** — günde çok mesaj alan hesaplar: gün sonunda kanal başına sayılar (`dm_daily_set`).
   - **İkisi birlikte** — günlük toplam o günün BÜTÜN konuşmalarıdır; tek tek kaydedilenler bu toplamın içindedir. Sunucu, tek tek
     kayıtların günlük toplamı aşmasına izin vermez. Gün, markanın saat dilimindeki gündür.
2. **Konuşma aç:** `dm_thread_open(profile_id, channel, opened_at?, campaign_id?, source, source_evidence?, meta_ad_id?, creative_key?,
   segment, intent, quantity?, note?)`.
   - `channel`: `instagram_dm | messenger | whatsapp | phone | web_chat | email | other`.
   - `source`: `ad` (kanıt: uygulamanın gösterdiği reklam bağlamı, reklamın mesaj düğmesinden geliş, müşterinin reklamı gördüğünü
     söylemesi; hangisi olduğu yazılır) · `organic` · `referral` (tavsiye) · `repeat` (tekrar müşteri) · `unknown`.
   - `segment`: `individual | corporate | reseller | unknown` — kurumsal ve bayi talepleri ayrı izlenir.
   - `intent`: `price | shipping | personalization | bulk | stock | payment | return | product_info | other`.
   - Yalnızca tarih verilirse saat, markanın saat diliminde günün başı sayılır.
3. **Olaylar (durum makinesi):** `dm_thread_event(profile_id, ref, event, at?, …)`.

   | Olay | Kimden | Kime | Zorunlu |
   |---|---|---|---|
   | `responded` | açık durumlar | (değişmez) | — · ilk cevap süresi buradan |
   | `qualified` | open | qualified | — · gerçek ilgi (ürün/adet/tarih sordu) |
   | `quoted` | open, qualified, quoted, stale | quoted | tutar verilirse `currency` |
   | `won` | open, qualified, quoted, stale | won | `paid_via`: `store_link` (mağaza bağlantısıyla ödedi) · `bank_transfer` · `cash_on_delivery` · `card_link` · `in_person` · `other`; tutar verilirse `currency` |
   | `lost` | open, qualified, quoted, stale | lost | `lost_reason`: `price` · `shipping_time` · `shipping_cost` · `no_reply` · `stock` · `personalization` · `payment` · `trust` · `competitor` · `other` |
   | `stale` | open, qualified, quoted | stale | — · uzun süre ses yok |
   | `reopened` | lost, stale | open | — |
   | `follow_up`, `note` | — | (değişmez) | `next_follow_up_at` verilebilir |

   Kapanmış (won/lost) konuşma yalnızca `reopened` ile açılır; olay zamanı açılıştan önce, takip zamanı olaydan önce olamaz.
4. **Çift sayım yok (tek satış defteri):** `paid_via="store_link"` satış mağaza siparişlerinde zaten vardır (içe aktarma ya da piksel);
   DM dönüşümünde sayılır, satış toplamına ayrıca eklenmez. Mesaj kanalında DM modülünde satış varsa aynı kanal ve dönem için `sales_add`
   ile elle girilen satış raporda sayılmaz ve bildirilir. Mağaza kanallarında içe aktarılan siparişler elle girişten önce gelir.
5. **Takip listesi:** `dm_follow_ups(profile_id)` — zamanı gelmiş takipler ve 3+ gündür sessiz açık konuşmalar (yerel eşik). Navigator
   açılışında varsa üst satırda tek cümle: "N konuşma takip bekliyor (M'si teklif aşamasında)". Konuşmayı `stale`/`lost` yapmak kullanıcının
   kararıdır; sistem kendiliğinden kapatmaz.
6. **Cevap ve teklif taslakları** (kullanıcı ister ya da takip listesinden):
   - Önce konuşmanın amacı (`intent`) ve segmenti; taslak marka sesiyle, kısa, tek bir sonraki adımla biter (sipariş bağlantısı, ödeme
     bilgisi isteme, teklif onayı, görüşme zamanı).
   - **Yalnızca bilinen gerçek:** fiyat satış sayfası ve stratejiyle birebir; teslim süresi, stok, kişiselleştirme kapasitesi ürün
     kartından. Bilinmeyen her bilgi `{{teslim süresi}}` gibi yer tutucuyla bırakılır ve kullanıcıya işaretlenir; uydurulmaz.
   - Kanıtlanamayan iddia, sahte aciliyet ("son 2 adet" stok bilinmiyorsa), baskı dili, rakibi kötüleme yok (`ref-legal-tr-meta`).
   - **Kurumsal/toplu teklif:** adet, teslim tarihi, kişiselleştirme (logo, kart, not), paketleme, fatura türü, ödeme şekli ve teklifin
     geçerlilik süresi sorulur ya da teklife yazılır; birim fiyat ve toplam ayrı; kapasite ürün kartında yoksa "üretici teyidi gerekir".
   - **Takip taslakları:** 1. takip (ilk sorudan yaklaşık 1 gün sonra, kısa hatırlatma + yeni bilgi), 2. takip (yaklaşık 3 gün sonra, son
     hatırlatma ve kapı açık bırakma). Süreler yerel öneridir.
   - Fatura/kargo için gereken kişisel bilgiler konuşmada kullanıcı ile müşteri arasında kalır; taslak bu bilgileri plugin'e yazmaz.
7. **Ölçüm ve koçluk:** `dm_summary(profile_id, date_from?, date_to?, campaign_id?)` → konuşma → nitelikli → teklif → satış, kanal,
   kayıp nedenleri, ilk cevap ortancası, segmentler, açık teklif toplamı, mağaza dışı ödenen satışlar. Koçluk (S16) aynı hesabı değişmez
   kopyadan yapar ve rapora "Reklam mı, teklif mi, sayfa mı" bölümünde yazar; satış oranı için Beta(1,1) önseliyle %90 aralık.
   Meta tarafı: mesaj hedefli kampanyada Meta'nın **sonuç** (`results`) sayısı başlatılan konuşmalardır; "Meta leads"
   (`onsite_conversion_lead_grouped`) form ve sohbet adaylarını sayar. Bu bağlantıda ayrı bir "başlatılan mesaj" alanı okunamadı
   (`ads_get_field_context`, 2026-10-20) — Meta'nın saydığı konuşma ile kaydedilen konuşma farkı raporda yazılır, biri diğerinin yerine
   konmaz.
8. **Öğrenme:** kayıp nedenleri (`price`, `shipping_time`, `personalization` …) S02 teklif tasarımına ve S17 brief taslağına girer;
   kreatife hüküm yazılmaz.

## Çıktılar
`dm_threads`, `dm_events`, `dm_daily` kayıtları (kişisel verisiz), takip listesi, taslaklar (sohbette; kaydedilmez), koçluk raporunda
mesajla satış satırları.

## Kontroller
- Kişisel veri kaydedilmedi; kanıtsız reklam bağı kurulmadı.
- Tek tek kayıtlar günlük toplamı aşmadı; mağaza bağlantısıyla ödenen satış satış toplamına ikinci kez eklenmedi.
- Taslakta bilinmeyen bilgi yer tutucuyla bırakıldı; fiyat satış sayfasıyla aynı; otomatik gönderim yok.

## Kapı mesajı
Kapı yoktur. Kayıttan sonra tek satır: "M-0007 açıldı (WhatsApp, kurumsal, toplu). Takip: <tarih>. Menüye dönmek için 'menü' yaz."
