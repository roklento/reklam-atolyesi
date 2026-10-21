---
name: organic
description: "reklam-atolyesi organik destek — reklam için çekilip kullanılmamış iyi kliplerden, kazanan reklamlardan ve konuşma çekimlerinden organik paylaşım adayları, haftalık takvim ve açıklama taslakları. Paylaşım yapılmaz; reklam kararlarına girmez."
---

# organic — Organik destek (1.5.0)

## Amaç
Reklamın getirdiği kişi profilde canlı, güven veren bir hesap görmeli. Her çekimde reklama girmeyen iyi anlar kalır; bunlar az emekle
organik paylaşıma dönüşür. Modül adayları seçer, sıralar, takvime koyar; paylaşımı kullanıcı yapar.

**Sınırlar:** Instagram'a paylaşım yapılmaz, zamanlanmaz. Organik sonuçlar (beğeni/yorum) reklam hükümlerine, önsellere ve
playbook'a girmez (farklı dağıtım, erişim bu bağlantıda yok). Kişili klip izinsizse aday olmaz.

## Ön koşul
Aktif profil; çekim kütüphanesinde analiz edilmiş klipler (S07) ya da koçluk analizi. Profil kontrolü önerilir (`profile-check`).

## Girdiler ve bağlam paketi
`asset_query(profile_id, scope="profile", kind="footage")`, son koçluk analizi JSON'u (varsa), `analysis/speech/*.transcript.json`
(varsa), marka sesi, ürün kartı (kanıtlanabilir iddialar), `profile-check` sonucu (sıklık önerisi için).

## Kullanılan hazır skill'ler ve OVERRIDES
Yok.

## Adımlar
1. **Adaylar:** `asset_query` sonucu `analysis/organic/assets.json` olarak yazılır →
   `PY PR/scripts/organic/candidates.py --assets analysis/organic/assets.json [--analysis reports/c<n>-analysis-v<k>.json]
   [--speech-dir analysis/speech] --consent analysis/organic/consent.json --per-week <2–4> --start <tarih> --out analysis/organic/organik.json`
   (`consent.json` = `consent_query(profile_id)` sonucu: izni olmayan ya da **geri çekilmiş** kişili klipler aday olmaz).
   Sıra: kazanan reklam (koçlukta "büyüt/tut" + kanıt) → konuşma çekimi (en az 12 sözcük) → kullanılmamış klip (puan ≥ 0,6, aralık
   ≥ 3 sn). Elenenler gerekçesiyle sayılır (reklamda kullanıldı, düşük puan, izinsiz kişi, kısa).
2. **Biçim:** kullanılmamış klip → 7–15 sn dikey kısa video (`compose` hızlı yolu, efekt bütçesi düşük, altyazı `keyword`); konuşma →
   `asr_local.py cuts` ile temizlenmiş kısa anlatım; kazanan reklam → gönderi zaten profildeyse yeniden paylaşılmaz.
3. **Açıklama taslakları:** her aday için 1 taslak: ilk cümle ne gösterdiği, tek yönlendirme (profildeki bağlantı / DM / randevu), 3–5
   etiket; yalnızca ürün kartındaki kanıtlanabilir iddialar; düzenlenen sektörde (`service_json.regulated_sector`) ref-legal-tr-meta
   kuralları. Taslaklar sohbette verilir, kaydedilmez.
4. **Takvim:** haftada 2–4 paylaşım (profil kontrolündeki sıklığa göre); tarih listesi kullanıcıya. Paylaşılan aday
   `asset_mark_used(profile_id, asset_id, creative_key="organic:<tarih>", role="organic")` ile işaretlenir (bir klip iki kez önerilmez).
5. **İzleme:** sonraki profil kontrolünde organik paylaşımların beğeni/yorum ortancası türlere göre okunur; yalnızca organik planı
   ayarlamak için kullanılır.

## Çıktılar
`analysis/organic/organik.json` (adaylar, elenenler, takvim), sohbette açıklama taslakları, kullanılan kliplerin işareti.

## Kontroller
- Paylaşım yapılmadı; organik veri reklam kararlarına girmedi.
- İzinsiz kişili klip aday olmadı; iddialar ürün kartındakilerle sınırlı.
- Reklamda kullanılmış klip "kullanılmamış" diye önerilmedi.

## Kapı mesajı
"Organik adaylar: N aday (K kazanan reklam, T konuşma, U kullanılmamış klip); bu hafta için 3 tarih ve taslaklar hazır. Hangilerini
hazırlayayım?"
