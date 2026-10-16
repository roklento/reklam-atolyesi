---
name: concepts
description: "reklam-atolyesi S03 konsept görüşmesi — ürün, veri, rakip haritası ve strateji çerçevesinde kullanıcıyla birlikte konsept, hook (4 parça), ses niyeti, hipotez ve çekim yolu kararı. Kapılı."
---

# concepts — S03 · Konsept görüşmesi (spec 4.3, 4.7, 4.6, 6.6, 10)

## Amaç
Konsept, hook ve hipotezi Claude'un üretip "onaylatması" değil; ürünün, verinin, pazarın ve kullanıcının **birlikte** karar verdiği bir
görüşme (ilke 9). Kapıda onaylanan şey görüşmede varılan kararların özetidir. Görüşmeyi `creative-strategist` ajanının yöntemiyle ana
oturumda yürüt (kullanıcıyla konuşma ana oturumdadır; ajan gerekirse aday listesi ve çeşitlilik kontrolü hazırlar).

## Ön koşul
- S02 kapısı geçilmiş (onaylı stratejik yön, açı portföyü, kreatif tavanı). Soğuk başlangıçta 2–3 konsept.
- Strateji çerçevesi bağlayıcıdır, kilit değildir: kullanıcı çerçeve dışı yön isterse söylenir; isterse S02'ye dönülür (`stage_back`)
  ya da konsept `free` rolüyle portföye işlenir.

## Girdiler ve bağlam paketi
`memory_context(profile_id, "S03", campaign_id, cycle_id)`: tercihler, kapsamı eşleşen playbook, son iki turun koçluk özeti, rekabet
haritası ve onaylı strateji, reddedilen/ertelenen fikirler, ürün, marka belgeleri, açık hipotezler, çekim kütüphanesi özeti. Ayrıca
ürün fotoğraf/videosu (`products.photos_json`), `metrics_query`, `priors_get`, `playbook_get`, `strategy_get`, `competitive_insights_get`,
`taxonomy_get(profile_id)`, `DD/profiles/<slug>/brand/docs/`.

## Kullanılan hazır skill'ler ve OVERRIDES
- **ad-creative-video** (hook matrisi yöntemi): önce `PR/vendor-skills/ad-creative-video/OVERRIDES.md`, sonra
  `PR/vendor-skills/ad-creative-video/SKILL.md` — yalnızca hook taksonomisi, "tek değişken" kuralı ve hook→CTA mesaj eşleşmesi
  (adım 6). iart.ai yönlendirmeleri ve örnek metin/renkler uygulanmaz.

## Adımlar
1. `stage_start(profile_id, "S03", campaign_id, cycle_id)`.
2. **Mod:** aynı kampanya amacından geçmiş veri var mı? *Veriyle* ya da *soğuk başlangıç*; kullanıcıya söyle.
3. **Ürünü incele:** fotoğraf/videoya bak, gördüklerini söyle (tür, ambalaj, etiket, renk, doku, çeşitler); kullanıcı düzeltir.
   Doğrulanamayan "teyit edilmedi".
4. **Veriyi oku** (varsa): neyin işe yaradığı, tabanlar, en iyi/en zayıf reklamlar; her bulgu **"kanıt"** (yeterli veri, aralıkla) ya
   da **"yön"** (az veri). Hesap farkı belirtilir. Sonra **pazarı oku:** rekabet haritasının 3–5 cümlelik özeti — "kategori gözlemi"
   ya da "vekil" etiketiyle; hesap verisiyle karıştırılmaz.
5. **Referans tahtası:** hesabın kendi en iyi reklamları (`ads_get_creatives` + kontak sayfası) ve S01b görüntüsünden seçilen örnekler
   (uzun soluklu rakip konseptleri, kategori normu, boşluğa en yakın). S03 Kütüphanede ayrıca tarama yapmaz; kullanıcı yeni bir marka
   adı verirse o marka için **tek** `ads_library_search` yapılır ve rakip setine eklensin mi diye sorulur. Tahta yön gösterir; **kanıt
   değildir** ve kopyalanmaz. Kaydet: `DD/profiles/<slug>/campaigns/<k>/c<tur>-referans-tahtasi.md` (görseller yalnızca
   `competitors/cache/` bağlantısıyla; kampanya üretim klasörlerine kopyalanmaz). Kütüphane bölge için sonuç vermiyorsa tahta hesabın
   kendi reklamları ve kullanıcının örnekleriyle kurulur.
6. **Soru turu** (en fazla 3–4, seçenekli): bu kampanyada ne öğrenmek istiyorsun · hangi duyguyu/anı öne çıkaralım · neyi istemiyorsun ·
   çekimde ne yapabiliyorsun.
7. **Yön önerileri** (her seferde 2–3). Her yön: fikir · **neden önerildiği** (kaynak: `evidence | direction | general | product |
   brand_doc | competitor`) · neyi test ettiği · çekim yükü · izinli iddialarla uyumu · **portföydeki yeri** (`proven | gap | counter |
   free`) · rakipten türüyorsa kaynak rakip konsepti. `competitor` önerisi "kategori gözlemi, bu hesapta kanıtlanmadı" diye sunulur;
   hesabın verisiyle çelişirse hesabın verisi geçerli; soğuk başlangıçta `competitor`, `general`'den önce gelir. Marka belgesindeki
   konseptler hazır karar değil öneridir. Kullanıcı seçer, birleştirir, reddeder ya da kendi fikrini getirir; Claude geliştirir.
   Her karar **aynı çağrıda devam notuyla**: `concept_upsert(profile_id, campaign_id, cycle_id, code, name, source, angle, decision=
   accepted|merged|rejected|deferred, user_said, rationale, competitive_role, source_competitor_ad_ids, features={sözlük eksenleri},
   sound_intent?, checkpoint={…})`. Profil eksenine yeni değer gerekiyorsa kullanıcıyla `taxonomy_value_add`.
8. **Hook'lar:** hook ilk 1–2 sn ve dört parça: **açılış karesi** (`first_frame_type` sözlükten + açıklama) · **ilk hareket** · **ilk
   ses** · **metin**. Kaydırmayı durduran öncelikle ilk üçüdür. Her seçilen konsept için en az biri görsel olarak farklı **3 hook
   alternatifi**; kullanıcı seçer ya da yazar. Yalnızca metni/rengi farklı hook aynı varlıktır (Andromeda) → `reserve=True`.
   Belgesiz iddia, ayırt edilmesi zor AI yüz ve rakip hook'unun yakın benzeri önerilmez. → `hook_upsert(profile_id, concept_id, code,
   first_frame_type, first_frame_desc, first_motion, first_sound, text, vo?, duration_s?, decision, user_said, reserve, checkpoint)`.
9. **Ses niyeti:** her konsept için sesin nereden geleceği konuşulur — çekimdeki ses (ortam/ürün/konuşan kişi) · kullanıcının kendi
   seslendirmesi · üretilmiş seslendirme · yalnızca müzik ve efekt → `concept_upsert(..., sound_intent=…)`. Kesin karar S09'da.
10. **Hipotezler** seçilen konseptlerden doğar: `hypothesis_add(profile_id, statement, metric, campaign_id, cycle_id, feature?,
    concept_id)` ve `concept_upsert(..., hypothesis_id=…)`. Önce hipotez yazıp sonra konsept uydurulmaz (birincil doğrulama hipotezi istisnası).
11. **Çeşitlilik, uzaklık ve tavan:** keşif konseptleri sözlükte en az iki eksende (`emotion`, `moment`, `proof`, `first_frame`) farklı.
    Rakipten türeyen (`proven | counter`) her konsept için `concept_distance_check(profile_id, concept_id)` geçmeli (açı dışında ≥ 2
    eksen farkı; hook/metin 4-gram örtüşmesi ≤ %20); geçmezse yön değiştirilir — otomatik kontrol hukuki uygunluk kanıtı değildir.
    Portföy dağılımı S02'ye uyar. Doğrulama çiftinde yalnızca hedef özellik değişir (çeşitlilik şartı aranmaz). Seçilen test hook'ları
    S02 tavanını aşamaz; fazlası `reserve`.
12. **Çekim yolu:** seçilen konseptler profil çekim kütüphanesiyle kurulabiliyor mu? `asset_query(profile_id, scope="profile", …)` ile
    eşleşmeyi göster (konsept → klip/fotoğraf, eksikler; daha önce açılış karesi olmuş klip işaretli). Kullanıcı "yeni çekim" ya da
    "kütüphaneden" seçer → `campaign_update(mode="full"|"quick")`. Hızlı turda eksik çekim varsa yalnızca onlar için kısa S04 açılır.
13. `hooks_export_csv(profile_id, campaign_id, cycle_id)` → `DD/profiles/<slug>/campaigns/<k>/c<tur>-hooks.csv`.
14. Görüşme özeti: `DD/profiles/<slug>/campaigns/<k>/c<tur>-konsept-gorusmesi.md` (seçilenler ve gerekçeleri, kaynakları, rolleri;
    reddedilen/ertelenenler ve nedenleri; açık sorular; çekim yolu; referans tahtası bağlantısı; atomik).
15. `stage_complete(profile_id, "S03", outputs=[{path: özet}, {path: hooks.csv}, {path: referans tahtası}], summary, campaign_id, cycle_id)`.
16. Tercihler: kabul/ret örüntüsü `memory_add(layer="preference", source="user", evidence_id=<karar kimliği>)` (eşleştirme kuralıyla).

## Çıktılar
`concepts` (kaynak, karar, rol, kaynak rakip reklamları, sözlük özellikleri, ses niyeti, uzaklık kontrolü), `hooks`, `hypotheses`,
`campaigns.mode`, `c<tur>-hooks.csv`, görüşme özeti, referans tahtası, tercih gözlemleri, devam notu.

## Kontroller
- Kullanıcı kararı olmadan hiçbir konsept/hook `accepted` değil; her önerinin kaynağı ve kararı kayıtlı.
- Her seçilen konseptin seçilmiş hook'u ve hipotezi var; rakipten türeyenler uzaklık kuralını geçti (sunucu kapıda denetler).
- Test reklamı sayısı ≤ S02 tavanı; yedekler ayrı.
- Hook'lar dört parçalı; görsel olarak farklı her hook çekim menüsüne ayrı satır olacak.

## Kapı mesajı
"Görüşme özeti: seçilen konseptler <A (rol, kaynak): fikir — hook h1/h2…>, gerekçeleri …; reddedilen/ertelenen: …; hipotezler: …;
ses niyetleri: …; açık sorular: …; çekim yolu: <yeni çekim | kütüphaneden>. Bu özeti onaylıyor musun, neyi değiştirelim?" → açık onayda
`gate_approve(..., cycle_id, checkpoint=…)`. Reddedilen/ertelenen fikirler sonraki tur için saklanır.
