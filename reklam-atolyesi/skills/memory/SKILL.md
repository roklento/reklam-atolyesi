---
name: memory
description: "reklam-atolyesi hafızası (ad-memory) için yöntem: profil kartı, aşama bağlam paketi, arama, ekleme/eşleştirme, devam notu, konsolidasyon, \"neler yaptık\", unutma. Yalnızca plugin modunda."
---

# memory — hafıza sistemi (spec bölüm 8)

## Amaç
Sistemin **neler yaptığımızı her zaman bilmesi**, kullanıcıdan ve veriden öğrenmesi ve bunu verimli tutması. Tek gerçek kaynak
`DD/db/ad-memory.sqlite`'tır; Markdown dosyaları yalnızca dışa aktarımdır, okunmaz ve geri yazılmaz. Kampanya verisi ve öğrenme
Claude Code'un kendi hafızasına (CLAUDE.md, auto-memory) **yazılmaz**.

## Ön koşul
- `ad-memory` bağlı; işin bağlı olduğu `profile_id` açık (sistem hafızası için `profile_id=None`).
- Hesaplanabilen bilgi hafızaya yazılmaz: aktif kampanya, aşama, kapılar, maliyet, metrikler her okunuşta tablolardan üretilir.

## Girdiler ve bağlam paketi
- **Profil kartı:** `memory_card(profile_id)` — açılışta, canlı üretilir (≤ ~1.500 token).
- **Aşama bağlam paketi:** `memory_context(profile_id, stage, campaign_id, cycle_id)` — reçeteler `PR/servers/ad_memory/memory_recipes.json`'da;
  bütçe varsayılan 2.000 token, sığmayanlar yalnızca başlık+kimlik olarak gelir. Aşama skill'i bağlamı **tek çağrıyla** alır; ayrıntıyı
  gerekirse `memory_search` ile açar.
- **Arama:** `memory_search(query, profile_id, layer?, include_journal?, stage?, scope?)` — FTS5 trigram; Türkçe normalleştirme
  (İ→i, I→ı; ayrıca aksansız kopya ı→i, ş→s, ğ→g, ü→u, ö→o, ç→c). Kök bulma yoktur: ör. "paket" "paketleme"yi bulabilir, "paketi"nin
  bulması garanti değildir. 3 harften kısa sorgu etiket/LIKE ile aranır. **Anlam eşitliğini Claude adayları okuyarak kurar**;
  FTS sonucu tek başına "aynı şey" sayılmaz (8.10 kurulmaz).

## Kullanılan hazır skill'ler ve OVERRIDES
Yok.

## Adımlar

### A. Yazma (8.3)
1. **Devam notu.** Her kullanıcı kararından, her kapı onayından ve her uzun işin (render, üretim) başında/sonunda güncellenir.
   Yapı: `{stage, done_steps, decisions:[{id, özet, gerekçe}], open_questions, next_step, refs:{dosya/kayıt kimlikleri}}`,
   ≤ ~400 token, öncekinin üzerine yazılır. Görüşmenin tamamı nota sığdırılmaz; not kalıcı karar kimliklerine ve sıradaki soruya işaret eder.
   - Karar mutasyonları notu **aynı çağrıda** taşır: `concept_upsert(..., checkpoint=…)`, `hook_upsert(..., checkpoint=…)`,
     `gate_approve(..., checkpoint=…)`, `decision_log(..., checkpoint=…)`.
   - Karar içermeyen ilerleme: `checkpoint_save(profile_id, stage, state, campaign_id, cycle_id, scope_key?)`.
   - Aşama bitince `stage_complete` notu kapatır ve özeti günlüğe tek kayıt geçirir (`checkpoint_close` yalnızca aşama dışı işler için).
   - Kullanıcıya "kaydedildi" ancak mutasyon + not birlikte commit edilince söylenir. Stop hook'u 3 karar turu notsuz geçince hatırlatır;
     bu bir dayanıklılık mekanizması değildir.
2. **Günlük.** Sunucu aşama/kapı/üretim/metrik olayları için günlük üretmez (tablolarda var). Claude iş bitince tablolardan
   çıkarılamayan anlatıyı 1–3 satırla yazar: `journal_log(summary, profile_id, type, campaign_id, detail, links)`.
3. **Eklerken eşleştirme.** `memory_add(layer, kind, content, source, profile_id, scope, tags, confidence, evidence_id)` önce aynı
   katman/kapsam/etiketten adayları ve en yakın 5 metin sonucunu döndürür. Claude bunları okur:
   - **aynı şeyi söylüyorsa** yeni kayıt açma → `memory_observe(item_id, evidence_id)` (kanıt kimliği benzersiz; aynı mesaj/karar
     tekrar gözlem sayılmaz);
   - **çelişiyorsa** → `memory_update(item_id, conflict=True)`; bir sonraki ilgili görüşmede kullanıcıya sor;
   - **gerçekten yeniyse** → `memory_add(..., force_new=True)`.
   Tercihlerin tamamı ilgili kapsamda sayfalı okunabilir; ilk 5 sonuç eş anlamlı tercihin bulunacağını garanti etmez.
4. Katmanlar: `semantic` (tablolardan türemeyen bilgi), `preference` (beğeni/beğenmeme, ton, iletişim biçimi), `procedural`
   (işe yarayan prompt/model ayarı, kabul oranı, maliyet sapması, tekrarlayan hata kuralı). Her öğe kapsam (profil/ürün/amaç/sezon/format),
   etiket, güven, kanıt ve kaynakla yazılır.
5. **Kullanıcı açık isteği:** "şunu hatırla" → `memory_add(..., source="user")` doğrudan `active`; "bunu unut" → C adımı.

### B. Öğrenme ve yaşam döngüsü (8.5–8.6)
- Öğrenilen her şey önce `proposed` doğar. Tercih: üç tutarlı gözlemle (`observations ≥ 3`, açık eşleştirmeyle) `active`;
  kullanıcı aksini söylerse hemen güncellenir.
- Playbook kuralı yalnızca 6.6 bağımsız doğrulama koşuluyla ve kullanıcı onayıyla `active` (bkz. `learn`); her 3 turda ya da
  90 günde yeniden doğrulamaya düşer; art arda iki turda çelişirse `retired` (silinmez).
- Güven yarı ömürle düşer (varsayılan 180 gün); son 3 turda hiç kullanılmayan `active` öğe `archived` olur (playbook hariç).
  Bu geçişleri `memory_lifecycle_tick(profile_id)` uygular (S17 sonunda ve bakımda).
- Marka/ürün gerçeklerinde `brands/products`, kararda ilgili tablo esastır; hafıza bunların kopyasını bağımsız gerçek diye tutmaz.

### C. Görünürlük ve kontrol — "Neler yaptık" (8.8)
1. `journal_summary(profile_id, days=30)` + açık devam notları (`checkpoint_get`) + `playbook_get(status="active")` + aktif tercihler
   (`memory_search` katman `preference`) + bekleyen doğrulamalar. Sade bir liste olarak göster.
2. Kullanıcı düzeltirse `memory_update(item_id, content=…, by_user=True)`.
3. Silme: önce neyin silineceğini göster, açık onay al → `memory_forget(item_id, confirm_text, profile_id)`. Araç öğeyi, FTS kaydını,
   kullanım/kanıt kopyalarını, türeyen özet ve dışa aktarımları temizler; öğeyi içeren yerel yedekleri silip temiz yedek alır; günlükte
   içerik taşımayan iz kalır. Meta'da yayınlanmış içerik, kullanıcının harici kopyaları ve sağlayıcı kayıtları yerel silmeyle yok
   olmuş sayılmaz: yerel tamamlananlar ile insan/sağlayıcı tarafında bekleyenler ayrı raporlanır. Kişisel medya/yorum için
   `consent_withdraw` / `review_withdraw` (bölüm 10).

### D. Verimlilik (8.7)
- **Özet katlama:** `journal_fold(profile_id)` (gün → hafta → ay; ham kayıtlar arşive).
- **Konsolidasyon:** zamanı S17 sonu ve `consolidation_due(profile_id)` eşiği (ör. 50 yeni öğe/kayıt). `memory_consolidate(profile_id,
  max_groups=10)` aday grupları verir (aynı katman/kapsam, etiket örtüşmesi, trigram benzerliği). Claude her grubu **okur** ve
  birleştirir (`memory_merge(keep_id, merge_ids, merged_content)`), ayırır ya da çelişki işaretler. Belirsiz grupta kullanıcıya sorar.
  Bir seferde en fazla 10 grup. Zamanlanmış bakım işi yalnızca aday sayısını raporlar; birleştirme yapmaz.
- Önizleme (salt okuma): `PY PR/scripts/memory/memory_tools.py consolidation-preview|usage-report|fold-preview --data-dir DD --profile-id N`.
- Dışa aktarım (okunabilirlik): `export_markdown(profile_id)` → `DD/profiles/<slug>/{playbook.md, hypotheses.md, memory/}`.

### E. Sistem hafızası (8.9)
Plugin geliştirme notları (marka belgesinden gelen sistem önerileri dahil), model davranışları, fiyat gözlemleri, render süreleri,
hata/kurtarma kayıtları `profile_id=None` ile yazılır. Profillere yalnızca **"genel bilgi"** etiketiyle girer; plugin kendiliğinden değişmez.

## Çıktılar
`memory_items`, `memory_usage`, `journal`, `journal_rollups`, `resume_state` kayıtları; dışa aktarım dosyaları. Kalıcı her kayıt açık
`profile_id` taşır (sistem hafızası hariç).

## Kontroller
- Profil yalıtımı: bir profilin hafızası başka profilin kararında kullanılmaz ("genel bilgi" etiketi dışında).
- Bağlama ham veri toptan yüklenmez; profil kartı ve paket bütçeleri aşılmaz; kritik kimlik/kapı/engel kırpılmaz.
- Otomatik anlam eşleştirme iddiası yoktur; birleştirme Claude'un açık okumasıyla ve gerekiyorsa kullanıcıyla yapılır.

## Kapı mesajı
Hafızanın kendi kapısı yoktur. Silme ve birleştirme kullanıcı onayıyla yapılır: "Şu öğeyi siliyorum: «…». Yerel kopyalar ve yedekler
temizlenecek; Meta'daki yayın ve sağlayıcı kayıtları ayrıca senin işlemini gerektirir. Onaylıyor musun?"
