---
name: learn
description: "reklam-atolyesi S17 öğrenme — hipotez sonuçları, bağımsız doğrulamalı playbook önerisi, yeniden doğrulama/emeklilik, hafıza konsolidasyonu, sonraki tur brief taslağı. Kapılı."
---

# learn — S17 · Öğrenme (spec 6.14, 6.6, 6.16, 8.5–8.7)

## Amaç
Turun öğrettiğini hafızaya doğru seviyede yazmak: kanıt eşiğini geçen playbook olur, geçmeyen hipotez defterinde kalır. Kararlar
kullanıcının onayıyla. Yöntem `coach` ajanınındır.

## Ön koşul
S16 kapısı geçilmiş (onaylı kararlar ve rapor).

## Girdiler ve bağlam paketi
`memory_context(profile_id, "S17", campaign_id, cycle_id)`: turun bütün hipotezleri, bütün playbook, kalibrasyon, konsolidasyon durumu,
portföy sonucu. `hypothesis_list`, `playbook_get`, `calibration_get`, S16 analiz ve raporu, `ref-metrics-math`.

## Kullanılan hazır skill'ler ve OVERRIDES
Yok.

## Adımlar
1. `stage_start(profile_id, "S17", campaign_id, cycle_id)`.
2. **Hipotezleri sonuçlandır:** `hypothesis_update(profile_id, hypothesis_id, status=supported|rejected|inconclusive, evidence={analiz
   kopyası yolu/hash, metrik, aralık, yeterlilik}, note)`. Eşik altı ya da doğrulanmamış yapı → `inconclusive`.
3. **Playbook önerisi koşulu (6.6):** yalnızca (a) önceden (test başlamadan) sabitlenmiş birincil doğrulama hipotezi, (b) ilk yeterli turda
   aynı yönde bulgu ve (c) sonraki turun **tek başına** verisinde aynı yönde üstünlük olasılığı ≥ 0,95 (oranda iki kola Beta(1,1),
   maliyette sabit Gamma önseli; keşif verisi doğrulama önseline girmez). Üst huni bulgusu ayrıca önceden seçilmiş en az bir alt huni
   metriğiyle aynı yönde ve yeterli veriyle desteklenmeli; yoksa "dikkat bulgusu" olarak hipotez defterinde kalır. Bootstrap ve
   doğrulanmamış yapı turları tek özellik için kontrollü doğrulama sayılmaz. Ölçekleme katmanındaki performans da kontrollü doğrulama
   sayılmaz; bir reklamın ölçeklemeye taşınmış olması tek başına playbook kanıtı değildir. Rol karşılaştırması önceden sabitlenmemişse aday olmaz.
   Koşulu sağlayan → `playbook_propose(profile_id, rule, evidence, scope, season, confidence)` (`proposed`); kullanıcı onaylarsa
   `playbook_activate(profile_id, rule_id, approval_text)`. Her bulguya sezon etiketi.
4. **Yeniden doğrulama ve emeklilik (8.6):** `playbook_round_tick(profile_id)`; `due_revalidation` kurallar bu turun verisiyle
   `playbook_revalidate(profile_id, rule_id, outcome=consistent|contradicted|inconclusive, evidence)`; art arda iki turda çelişen →
   `playbook_retire(profile_id, rule_id, reason)` (silinmez).
5. **Bağımsız doğrulama adayı:** keşif turundaki en değerli aday **sonraki tur başlamadan** seçilir (tur başına en fazla bir birincil
   hipotez, metrik, yön, karşılaştırma). Sabitleme S02'de `hypothesis_add(..., is_primary=True, pre_registration=…)` ile test başlamadan.
6. **Vekil sinyal kalibrasyonu (6.16):** rol beklentileri (`prediction_log` S02) olgun veriyle `prediction_resolve`; profilin rakip
   sözlüğü değerleri (`other:` önerileri) kullanıcıyla gözden geçirilir (`taxonomy_value_add` / sistem hafızasına sabit eksen önerisi).
7. **Hafıza:** `memory_lifecycle_tick(profile_id)`; `journal_fold(profile_id)`; konsolidasyon (`memory` skill'i D adımı: aday grupları
   Claude okur, en fazla 10 grup, gerekirse kullanıcıya sorar); kalibrasyondan eşik/`n_cap` önerisi yalnızca ≥ 30 çözülmüş tahminde ve
   kullanıcı onayıyla.
8. **Sonraki tur brief taslağı:** kazananı büyüt, bir bilinmeyeni test et, ertelenen fikirler, uygulama listesi durumu, "rakip görüntüsü
   tazelenmeli mi" notu → `DD/profiles/<slug>/campaigns/<k>/c<tur+1>-brief-taslak.md`. "Kazananı büyüt" iki yoldan biriyle yazılır:
   ölçekleme katmanına mevcut gönderiyle taşındı/taşınacak (S16 maddesi, gönderi kimliği) ya da ana sette bütçe artışıyla (katman
   koşulları sağlanmadıysa nedeni). Katman açıksa taslağa ayrıca: üyelerin yorgunluk durumu (`track` 6.7), yenileme ihtiyacı (yorulan
   üyenin yerine bir sonraki testin kazananı aday) ve katmanın bütçe payı. Ölçekleme setine yeni konsept doğrudan eklenmez; önce test edilir.
   Katman kaydını sunucu yeni tura kendisi taşır (`scale_layer_get` ile görülür); S02'nin bütçe planı onu silmez.
9. `export_markdown(profile_id)` (playbook.md, hypotheses.md).
10. `stage_complete(profile_id, "S17", outputs=[{path: brief taslağı}, {path: öğrenme özeti md}], summary, campaign_id, cycle_id)` → `awaiting_gate`.
    Onaydan sonra yeni tur S01'den açılır (aynı kampanya, yeni `cycle_id`); kapanan turun reklamları yayında kalır, ölçümleri kampanya
    düzeyinde sürer.

## Çıktılar
Hipotez durumları, playbook önerileri/aktivasyonları/emeklilikler, kalibrasyon çözümleri, hafıza yaşam döngüsü ve konsolidasyon,
sonraki tur brief taslağı, dışa aktarımlar, devam notu.

## Kontroller
- Bağımsız doğrulama verisi olmayan ya da yalnızca keşif verisini tekrar kullanan aday playbook'a girmedi.
- Üst huni bulgusu alt huni teyidi olmadan aktifleşmedi; kural kullanıcı onayı olmadan `active` olmadı.

## Kapı mesajı
"Öğrenilenler: desteklenen … · reddedilen … · sonuçsuz …. Playbook önerisi: <kural, kanıt> (onaylarsan aktifleşir). Emekliye ayrılan: ….
Sonraki tur için öneri: …. Onaylıyor musun?" → `gate_approve(...)`.
