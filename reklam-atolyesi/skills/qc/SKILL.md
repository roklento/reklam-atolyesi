---
name: qc
description: "reklam-atolyesi S13 kalite kontrol — teknik QC, bağımsız qc-reviewer incelemesi (workflow ya da yedek yol), yasal liste, yorum/kişi izni ve rakip uzaklığı; QC raporu. Kapılı."
---

# qc — S13 · Kalite kontrol (spec bölüm 10, 5.15, 5.19)

## Amaç
Teslim dosyalarını **üretimi görmemiş gözle** teknik, görsel ve yasal ölçütlerle incelemek. Öz denetimden (5.15) ayrıdır. Geçemeyen
kreatif yayın paketine girmez.

## Ön koşul
S12 tamam: `creatives` kayıtları (test + yedek), planlar, miks raporları.

## Girdiler ve bağlam paketi
`memory_context(profile_id, "S13", campaign_id, cycle_id)`: QC prosedürleri, yasal durum, konsept uzaklık kayıtları.
`creative_list(profile_id, campaign_id, cycle_id)`, `review_query`, `consent_query`, `products.provable_claims_json`,
`concepts` (rol, `distance_check_json`, kaynak `library_id`'ler), `ref-legal-tr-meta`.

## Kullanılan hazır skill'ler ve OVERRIDES
- **product-demo-director**: `PR/vendor-skills/product-demo-director/OVERRIDES.md` → `criteria/demo-skill-rubric.md` ve `SKILL.md`
  deterministik QA ilkeleri (Gemini yargıcı ve harici üretim uygulanmaz).
- **promo-video**: `PR/vendor-skills/promo-video/OVERRIDES.md` → `SKILL.md` render'ı kendi kendine doğrulama bölümü.
- **ai-product-video**: `PR/vendor-skills/ai-product-video/OVERRIDES.md` → `references/final-review.md` (ek ölçüt).
- **ffmpeg**: `PR/vendor-skills/ffmpeg/OVERRIDES.md` (yöntem).

## Adımlar
1. `stage_start(profile_id, "S13", campaign_id, cycle_id)`.
2. **Teknik QC (otomatik)** her dosya için:
   `PY PR/scripts/qc/checks.py tech --video <mp4> --plan <plan.json> --expect-duration <sn> --format <9x16|4x5|1x1>` (süre, çözünürlük,
   fps, codec/profil, yuv420p, AAC 48 kHz, faststart, -14 LUFS ±1, ≤ -1 dBTP, siyah kare/donma **bütün videoda**, güvenli alan),
   `checks.py black --video <mp4>`, `checks.py safe --plan <plan.json>` (yazılar güvenli alanda ve ≥ 1,5 sn ekranda), font glif kapsamı
   (`PY PR/scripts/qc/font_coverage.py --plan <plan.json> --project <kampanya>/src --data-dir DD`; eksik karakter ya da yüklenmeyen font →
   düzeltme notu), kontak sayfası (`contact_sheet.py --per-second`) ve yazı şeritleri (`contact_sheet.py --text-bands --plan <plan.json>`;
   kontak sayfasında 32 px yazı ≤ 8 px kalır, küçük yazı şeritten küçültmeden okunur), slayt gösterisi riski (`PY PR/scripts/qc/slideshow.py --plan <plan.json> --video <mp4>`:
   `critical` → düzeltme notu; ham/UGC türünde kullanıcı bilerek kabul ederse gerekçesiyle geçer; `high` → uyarı; eşikler yereldir),
   reklam metni varsa uzunluk (`checks.py copy`; uyarıdır).
3. **Bağımsız görsel/yasal inceleme (paralel):** workflow `qc-review` — `PR/workflows/qc-review.js`, args: `{profile_id, campaign_id,
   cycle_id, campaign_dir, plugin_root, data_dir, py, creatives:[{creative_id, file, plan_path, format, expect_duration, tech_report}],
   now_iso}`; her kreatif için `qc-reviewer`
   ajanı **yalnızca** teslim dosyası, kontak sayfaları, plan, teknik rapor, izin kayıtları ve iddia listesiyle (üretim konuşmasını görmeden).
   **Yedek yol (13.2):** `qc-reviewer`'ı kreatif başına alt ajan olarak çağır (Agent aracı, `subagent_type: "reklam-atolyesi:qc-reviewer"`);
   incelenmiş kreatif tekrar incelenmez; yol `journal_log`'a. Ajan görmediği/duymadığı kanıta (hareket akıcılığı, kısa ürün bozulması,
   ses) onay vermez: bunlar "insan kontrolü gerekli" diye döner.
4. **Görsel ölçütler:** AI kliplerinde ürün bozulması (gerçek fotoğrafla yan yana), yazım ve Türkçe karakterler (yazı şeritlerinden: harf
   başka fontla mı çizilmiş, kırpılmış mı, zemin üstünde okunuyor mu), okunurluk (≥ 1,5 sn),
   marka tutarlılığı, kilitli vurgu anlarının vuruşa oturması, efekt bütçesi.
5. **Yasal ölçütler (`ref-legal-tr-meta`):** yalnızca kanıtlanabilir iddialar · fiyat/indirim satış sayfasıyla birebir ve indirimde
   referans fiyat kanıtı · yüz ve eller gerçek çekimden; AI insan yok · ses klonu yok · AI içeren varyasyon için Meta açıklama/etiket
   talimatı ve Türkiye'de ayırt edilmesi zor AI içerik açıklaması · **Meta reklam standartları (§8):** `checks.py meta-text --plan <plan>`
   uyarılarının her biri gözle "sorun yok" ya da "düzelt" diye karara bağlanır; görüntüde sansasyonel öğe (8b) ve önce/sonra kategorisi
   (8d) kontak sayfasından denetlenir · **her `ReviewCard`** `reviews` kaydıyla eşleşir (izin kanıtı yoksa
   ya da `withdrawn_at` doluysa kreatif **reddedilir**; ad `name_display_mode`'a göre) · kişi tespit edilen **her klip** `person_consents`
   ile eşleşir (izin yoksa/geri çekildiyse klip kullanılamaz) · rakipten türeyen konseptler uzaklık kuralını geçmiş; kreatifte rakip adı,
   logosu, ürünü, tanınır ambalajı, sloganı yok; kurgu planında rakip kaynağı yok (yan yana kontrol için kaynak `library_id` önizlemesi
   yalnızca analiz önbelleğinden) · Instagram trend müziği yok; müzik/model lisans kaydı (`approval_scope_json.license`) var ·
   kullanım güvenliği gerektiren üründe kısa kullanım notu önerisi.
6. **İnsan kontrolleri:** tam oynatma/dinleme gerektiren maddeler (akıcılık, kısa ürün bozulması, telefon hoparlöründe VO netliği)
   kullanıcıya yapılır; kim, hangi sürüm, sonuç raporda tutulur.
7. **Sonuç:** her kreatif için `creative_set_qc(profile_id, campaign_id, creative_ids, status="passed"|"failed"|"pending", report_path)` (`pending` = düzeltme bekliyor; `passed` rapor yolunu ister).
   Düzeltme gerekiyorsa liste çıkar → S12'ye yama ya da ilgili aşamaya dönüş (`stage_back`); düzeltilen dosya yeniden QC'den geçer.
   Tekrarlayan bulgular `memory_add(layer="procedural", kind="qc")`; ürün tarifiyle ilgili bulgu ürün tarifine önerilir.
8. **Son kontrol listesi** (raporun başında, tümü işaretli): yazılar güvenli alanda ve ≥ 1,5 sn · ses -14 LUFS, telefon hoparlöründe VO net ·
   AI klipleri gerçek fotoğrafla karşılaştırıldı, bozulma yok · iddia listesi kontrol edildi · AI içeren varyasyonlarda Meta açıklama
   talimatı güncel kurala uygun · Meta reklam standartları (§8) uyarıları karara bağlandı · yazım ve Türkçe karakterler · yorum ve kişi izinleri eşleşti · ses kararları uygulandı · rakipten
   türeyen konseptler uzaklık kuralını geçti; rakip adı/logosu/varlığı yok.
9. Rapor: `DD/profiles/<slug>/campaigns/<k>/reports/c<tur>-qc-raporu.md` (atomik). `stage_complete(profile_id, "S13", outputs=[{path:
   rapor}], summary, campaign_id, cycle_id)` → `awaiting_gate`. Sunucu, QC'den geçmemiş test kreatifi varken kapıyı açmaz.

## Çıktılar
QC raporu ve düzeltme listesi, `creatives.qc_status`, teknik rapor JSON'ları, insan kontrolü notları, devam notu.

## Kontroller
- Meta platform kuralı (sınır, format, güvenli alan, politika) kullanıldıysa durumu `ref-legal-tr-meta` §7'ye göre belli: resmi
  (bağlantı + tarih), yerel koruma kuralı ya da teyit edilmedi; teyit edilmeyen kural kesin diye sunulmadı.
- `qc-reviewer` üretim bağlamını görmedi; seyrek karelerden hareket/ses için onay verilmedi.
- Her ReviewCard ve her kişili klip izin kaydıyla eşleşti; eşleşmeyen kreatif reddedildi.
- Teknik kontroller bütün video üzerinde; örnek karelerden "geçti" denmedi.

## Kapı mesajı
"QC: N test kreatifinden K'si geçti, L'si düzeltme bekliyor (… ). Yasal liste: …. İnsan kontrolü gereken maddeler: … (sen kontrol ettin
mi?). Geçenlerle yayın paketine geçelim mi?" → açık onayda `gate_approve(...)`.
