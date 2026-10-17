---
name: shoot-guide
description: "reklam-atolyesi S04 çekim planı — hiç video çekmemiş biri için ürün tarifini uygulayan kartlar, numaralı çekim menüsü (her hook ayrı satır), fotoğraf listesi, ses talimatı, sfx_plan. Kapılı."
---

# shoot-guide — S04 · Çekim planı (spec 5.3, 4.3, bölüm 10)

## Amaç
Seçilen konseptleri telefonla çekecek **amatör** kişi için adım adım, jargonsuz bir rehber üretmek: önce ürünün çekim tarifi
(`products.shoot_profile_json`), sonra genel kurallar; çatışırsa **ürün tarifi geçerlidir**. Kart dili ve telefon ayarları
`ref-shooting-basics`'tedir. İçerik `cinematographer` ajanıyla hazırlanabilir; kapı ana oturumdadır.

## Ön koşul
- S03 kapısı geçilmiş; `campaigns.mode = full` (hızlı turda S04 atlanır; yalnızca eksik çekimler için kısa S04 açılabilir).
- Seçilmiş konseptler, hook'lar (4 parça) ve ses niyetleri kayıtlı.

## Girdiler ve bağlam paketi
`memory_context(profile_id, "S04", campaign_id, cycle_id)`: ürün çekim tarifi, seçilen konseptler, çekim prosedürleri, çekim tercihleri.
Ayrıca `c<tur>-hooks.csv`, `strategy_get`, `products.provable_claims_json` (önce/sonra gibi karşılaştırma sahneleri gerçekten çekilir).

## Kullanılan hazır skill'ler ve OVERRIDES
- **ai-product-video** (çekim tarifi kartları): önce `PR/vendor-skills/ai-product-video/OVERRIDES.md`; sonra ilgili kartlar
  `PR/vendor-skills/ai-product-video/references/shots/camera/*.md` ve `…/shots/transition/*.md` — yalnızca kamera hareketi **dili**;
  amatör çekimci kartına çevrilir (parametre tabloları uyarlanır, kod kopyalanmaz; dlazy CLI zinciri uygulanmaz).

## Adımlar
1. `stage_start(profile_id, "S04", campaign_id, cycle_id)`.
2. **Hazırlık bölümü:** telefon ≥ %80 şarj, ≥ 20 GB boş, uçak modu, lens silinmiş; iPhone ve Android için adım adım ayarlar (4K 30 fps;
   yavaş çekim istenen çekimde 4K 60; HDR video kapalı; dikey; filtre/güzelleştirme yok) — `ref-shooting-basics`.
3. **Ürün tarifi kartları** (önce): her kart `risk · ne çekiyoruz · telefon nereye · ne yap · ne zaman dur · başardın mı · hangi genel
   kuralı neden değiştiriyor`. Terimler ilk geçtiği yerde açıklanır.
4. **7 altın kural** ve ayrıntılar (`ref-shooting-basics`). Kurtarılamayan üç şey (odaksız kare, patlamış beyazlar, hareket bulanıklığı)
   özellikle önlenir.
5. **Çekim menüsü (numaralı):** her satır: no (`S01`…), hizmet ettiği konsept(ler), ne çekileceği, süre, kamera hareketi, tek dikkat
   noktası, AI ile tamamlanabilir mi, **öncelikli** işareti. Görsel olarak farklı her hook (açılış karesi + ilk hareket) **ayrı satır**;
   test hook'ları öncelikli, yedek hook'lar (`hooks.csv` rolü "yedek") aynı çekim gününde eklenebiliyorsa çekilir (sonraki turun açılış
   karşılaştırması için).
   Ortak çekimler birden çok konsepte hizmet eder. AI klibi planlanan her sahne için **gerçek çekimli eşin** hangi çekimden kurulacağı
   yazılır (`real_twin_for`). Ürünün gerçekliğini kanıtlayan sahne, karşılaştırma ve önce/sonra sahneleri AI'a bırakılmaz.
   Makine okunur kopya: `DD/profiles/<slug>/campaigns/<k>/analysis/shoot_menu.json` =
   `[{"no","concept","what","hook","duration_s","motion","focus","ai_ok","real_twin_for","priority"}]` (S07 `material_map.py` bunu okur).
6. **Ses:** yalnızca ses niyeti "çekimdeki ses" ya da "kullanıcının sesi" olan çekimlerde kayıt talimatı (telefon konuşana/ses
   kaynağına yakın, sessiz ortam, müzik ve TV kapalı, gerekirse ucuz yaka mikrofonu; kullanıcı seslendirmesi için telefonun ses kaydı
   uygulamasıyla, sessiz odada, 3 alım). Diğer çekimlerde ses dikkate alınmaz; efektleri sistem üretir.
7. **Fotoğraf listesi:** konsept başına 5–8, aynı oturumda ve telefonun **fotoğraf modunda**: ürün tek başına, kullanımda, ayrıntı,
   statik ve carousel için yazı boşluklu kadrajlar.
8. **İzin hatırlatması:** görüntüde ya da seste tanınabilir her kişi (çekimci dahil) için kullanım izni — `consent_add(profile_id,
   person_label, scope=image|voice|image_voice, consent_type, consent_date, evidence_path, processing_scope)`; yükleme öncesi izin
   kapısı (bölüm 10) dosya istenmeden önce.
9. **Teslim:** sıkıştırmadan (WhatsApp değil; Drive, AirDrop, kablo), dosya adı çekim numarasıyla; videolar `footage/raw/`, fotoğraflar
   `photos/raw/` (ham klasörler salt okunur kabul edilir).
10. **sfx_plan:** konseptlerden ve çekim menüsünden üretilecek efektlerin başlangıç listesi (organik → ElevenLabs, tasarım → kodla sentez).
11. Rehber: `PR/templates/reports/cekim-rehberi.md` → `DD/profiles/<slug>/campaigns/<k>/c<tur>-cekim-rehberi.md` (atomik).
12. `stage_complete(profile_id, "S04", outputs=[{path: rehber}, {path: shoot_menu.json}], summary, campaign_id, cycle_id)` → `awaiting_gate`.

## Çıktılar
Çekim rehberi, `shoot_menu.json`, fotoğraf listesi ve `sfx_plan` (rehber içinde), izin kayıtları, devam notu.

## Kontroller
- Önce/sonra çekimi varsa ürün kategorisi `ref-legal-tr-meta` §8d'ye göre işaretli (kozmetik/kilo: 18+ notu, yakın plan ve
  kadraj kuralı kartta; kalıcı cilt beyazlatma tanıtılmaz); şok/korku çağrıştıran açılış çekimi yok (§8b).
- Kart yapısı tam; ürün tarifi genel kuralın önünde; ses talimatı yalnızca ses niyeti gerektiren çekimlerde.
- Hook satırları ayrı; AI planlı her sahnenin gerçek eşi yazılı; izin hatırlatması var; 7 kural var; fotoğraf listesi var.
- Rehber jargonsuz; teknik sorunlar (VFR, HDR) çekimciye yüklenmez (ingest çözer).

## Kapı mesajı
"Çekim planı: N çekim (öncelikli: …), M fotoğraf; ürün tarifi kartları: …; ses kaydı gereken çekimler: …; tahmini süre: …. Rehberi
çekimciye verebiliriz. Onaylıyor musun, neyi değiştirelim?" → `gate_approve(...)`. Onaydan sonra kısa bir **deneme** çekimi istenir (S05).
