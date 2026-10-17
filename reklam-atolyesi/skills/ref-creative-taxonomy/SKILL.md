---
name: ref-creative-taxonomy
description: "reklam-atolyesi ortak kreatif sözlüğü — kendi konsept/hook/kreatiflerimiz ve rakip konseptleri için aynı eksenler; sabit ve profil eksenleri, unknown kuralı, çeşitlilik ve uzaklık eşikleri."
---

# ref-creative-taxonomy — ortak kreatif sözlüğü (spec 4.7, 4.3, 4.5, 6.6, 10)

Kendi konseptlerimiz (`concepts.features_json`), hook'larımız (`hooks.first_frame_type`), kreatiflerimiz (`creatives.features_json`) ve
rakip konseptleri (`competitor_ads.features_json`) **aynı kontrollü sözlükle** kodlanır. Böylece rekabet haritası, S03 çeşitlilik ve uzaklık
kontrolü, özellik keşfi ve tur karşılaştırması aynı dili konuşur. Kaynak: `PR/servers/ad_memory/taxonomy.json` (sürümlü;
`taxonomy_get(profile_id)` profil değerleriyle birlikte döndürür; `ad-memory` her yazmada doğrular). Kodlar İngilizce, etiketler Türkçe.

## Sabit eksenler (kapalı liste; değer eklemek sözlük sürümü = plugin güncellemesi gerektirir)
| Eksen | Değerler |
|---|---|
| `video_type` | `reveal` · `process` · `testimonial` · `raw_ugc` · `ai_assisted` |
| `first_frame` | `product` · `product_in_hand` · `person` · `text_card` · `process` · `result` · `context` |
| `proof` | `none` · `process` · `review` · `number` · `document` · `before_after` (Meta kuralı kategoriye bağlı: `ref-legal-tr-meta` §8d) · `demo` · `expert` |
| `offer` | `none` · `discount` · `free_shipping` · `bundle` · `gift_with_purchase` · `limited` |
| `price_shown` | `yes` · `no` |
| `media` | `video` · `static` · `carousel` |
| `duration_band` | `le6` · `7_15` · `16_30` · `gt30` |
| `vo` | `none` · `generated` · `user` · `original_speech` |
| `people` | `none` · `hands` · `person` |
| `text_density` | `low` · `medium` · `high` |
| `cta` | Meta CTA türü (`SHOP_NOW`, `LEARN_MORE`, `ORDER_NOW`, `BUY_NOW`, `SIGN_UP`, `CONTACT_US`, `SEND_MESSAGE`, `SEND_WHATSAPP_MESSAGE`, `GET_OFFER`, `BOOK_NOW`, `SUBSCRIBE`, `NO_BUTTON`) |

## Profil eksenleri (açık; değerler profilden doğar — kurulum hiç değer yazmaz, ilke 12)
`angle` (konseptin konusu; sahne rolü değildir) · `moment` (S00c satın alma anlarıyla aynı kayıt) · `buyer` (video kime konuşuyor; S00c
alıcılarıyla aynı kayıt — an bir zamandır, alıcı bir kişi tipidir; iç kayıttır, reklam metninde izleyiciye atfedilmez:
`ref-legal-tr-meta` §8a) · `emotion` · `tone` (S00a marka tonu).
Değerler `taxonomy_values`'ta profil kapsamlı: S00a/S00c/S03 görüşmesinde kullanıcıyla `taxonomy_value_add(profile_id, axis, code, label,
status, user_said)`. Rakip kodlamasında profilde olmayan değer `other:<kısa ad>` diye **önerilir**; kullanıcı onaylarsa profile eklenir.

## Kurallar
- **`unknown` geçerli bir değerdir; tahmin edilen değer yazılmaz.** Görsel eksen görülemiyorsa (önizleme/ekran görüntüsü yok) `unknown`.
- Her kayıt `taxonomy_version` taşır; sürümler arası karşılaştırma yalnızca eşlenmiş değerlerle.
- Sabit eksen önerileri (`other:` birikimi) sistem hafızasına (`memory_add(profile_id=None, kind="taxonomy_proposal")`) yazılır; ancak
  plugin güncellemesiyle sözlüğe girer.
- **Çeşitlilik (S03; yerel koruma kuralı, kaynak durumu `ref-legal-tr-meta` §7):** Advantage+ kitlede reklamı kimin göreceğini Meta'nın
  yapay zekası seçer (resmi); birbirine çok benzeyen reklamların aynı kişilere gittiği ise teyit edilmedi. Bu yüzden test hakkı önce
  farklı alıcılara konuşan farklı fikirlere harcanır. **Keşif konsepti** = seçilmiş, birincil doğrulama hipotezine bağlı olmayan ve en az bir test (yedek
  olmayan) hook'u olan konsept. Her keşif konseptinin **tek test hook'u** ve **tek alıcısı** (`buyer`) vardır; keşif konseptleri ikişer
  ikişer **farklı alıcıya** konuşur ve `emotion`, `moment`, `proof`, `first_frame` eksenlerinden **en az ikisinde** farklıdır (konsept
  bütününe ait; `first_frame` test hook'unun açılış karesidir). Bilinmeyen (`unknown`) ya da boş değer fark sayılmaz. Aynı konseptin
  açılış karşılaştırması yalnızca birincil doğrulama çiftiyle yapılır; doğrulama çiftinde yalnızca hedef özellik değişir ve çeşitlilik
  şartı aranmaz. Denetim: `concept_diversity_check(profile_id, campaign_id, cycle_id)`; S03 kapısı aynı kontrolü yapar.
- **Uzaklık (bölüm 10):** rakipten türeyen konsept kaynak rakip konseptinden `angle` dışında **en az 2 eksende** farklı; hook/metin kaynak
  metne normalize 4-gram örtüşmesiyle **≤ %20** (`concept_distance_check`; yerel: `comp_tools.py distance`). Hukuki uygunluk kanıtı değildir.
- **Özellik etkisi (6.6):** özellik farkları, önceden yazılmış hipotez + diğer unsurlar sabit + doğrulanmış yapı olmadan yalnızca
  keşif/ilişkidir; `competitive_role` da bir özelliktir ve aynı kurala tabidir.
- Rol (`proven · gap · counter · free`) sözlük ekseni değil, strateji portföyü alanıdır (`concepts.competitive_role`).
