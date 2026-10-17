---
description: "Canlı kurulum kontrolü: hesap bağlantıları, hook tetiklenmeleri, MCP şemaları, canlı kabul listesi"
argument-hint: "[madde-id]"
---

Bu komut oturumu plugin moduna alır (UserPromptSubmit/UserPromptExpansion hook'u `/reklam-atolyesi:` önekinden tanır); hook bağlamındaki `session_id`, `plugin` ve `data_dir` değerlerini kullan. Maliyet koruması ve Meta izin listesi bu oturumda geçerlidir.

Canlı kurulum kontrolünü yürüt (spec 12.10 canlı liste, 16.5, 12.13). Statik kısım kurulumda `doctor.py` ile yapıldı; durumunu
`system_manifest_get()` ile göster. Argüman verildiyse (`$ARGUMENTS`) yalnızca o maddeyi yeniden çalıştır. Madde kimlikleri
`system_manifest_get(section="live_checks")`'tedir.

1. **Hesap bağlantıları:** kullanıcıyı `/mcp` ekranına yönlendir: `plugin:reklam-atolyesi:ElevenLabs` ve `plugin:reklam-atolyesi:meta-ads` için
   OAuth (Meta'da hesap ve sayfalar seçilir, izin seviyesi **salt okuma**). Meta MCP erişilemiyorsa (`is_ads_mcp_enabled=false`, yetki yok)
   CSV yolu açıkça seçilir: `settings_set("meta_data_mode_default", "csv")` (MCP ise `"mcp"`).
2. **ad-memory:** plugin içinden `data_dir` ile başladı mı, şema sürümü doğru mu (`system_manifest_get`).
3. **UserPromptSubmit gerçekten tetikleniyor:** bu mesajın bağlamında `[reklam-atolyesi] plugin modu: açık` satırı ve veritabanından okunan
   profil sayısı görünüyor mu.
4. **PreToolUse (Meta) gerçekten tetikleniyor:** izin listesinde **olmayan ama zararsız bir okuma aracı** (`ads_get_ad_account_custom_audiences`)
   plugin'in `meta-ads` sunucusunda çağrılır ve hook'un reddettiği görülür. Yazan ya da harcama başlatan araçla bu test **yapılmaz**.
5. **ElevenLabs:** bağlı; araç listesi `hooks/elevenlabs_tools.json` sınıflarıyla karşılaştırılır (sınıflandırılmamış ücretli araç bildirilir;
   liste insan onayıyla güncellenir). Her ücretli aracın canlı şemasında `estimate_only` desteği okunur ve
   `runtime_record("el_estimate_schema", "passed", component_hashes={"tools_with_estimate_only": [...]})` yazılır. Desteklenen bir araçta
   `estimate_only: true` ile fiyat dönüyor mu (ücretsiz). Maliyet korumasının gerçek host tetiklenmesi ücretsiz bir listeleme çağrısında
   geçici deny testiyle sınanır; geçici kural test sonunda kaldırılır.
6. **Meta veri yolu:** MCP'de salt okuma ve `ads_get_ad_accounts` → `is_queryable`; `ads_get_field_context` ile `meta_fields.json` alanları;
   izin listesi gerçek araç listesiyle karşılaştırılır; deney araçları (`ads_experiment_list_tests`) okunabiliyor mu. CSV yolunda sentetik
   örnekle eşleme şeması (`meta_tools.py synth-csv` + `csv-check`) ve otomatik çekmenin kapalı olduğu gösterilir; MCP'ye özgü maddeler
   `not_applicable` + gerekçe.
7. **Reklam Kütüphanesi kapsamı:** kullanıcının verdiği bir terim ve hesap bölgesinin ülke koduyla tek `ads_library_search`; ticari reklam dönüyor
   mu, hangi alanlar geliyor (başlangıç/bitiş, önizleme bağlantısı, platformlar). Dönmüyorsa S01b yedek yolu o profil için varsayılan.
8. **Zamanlanmış işler** (masaüstü uygulaması varsa): dört iş sentetik profil için bir kez "Şimdi çalıştır" ile denenir; okuma araçlarına
   "her zaman izin ver", ücretli ve Meta yazma araçları görev izinlerinde engelli; sonra iş tanımları silinir. Yalnızca terminal varsa
   gerekçesiyle kaydedilir.
9. **Workflow'lar:** `analyze-footage` iki sentetik klipte (ya da yedek yol), `render-variants`, `qc-review`, `analyze-competitors`.
10. **Canlı kabul listesi (16.5)** sentetik profilde (`profile_create(..., synthetic=True)`), **hiçbir ücretli çağrı ve Meta yazma olmadan**;
    sonunda sentetik profil arşivlenir.

Her madde `runtime_record(item_id, status, scope, evidence_ref, component_hashes, not_applicable_reason?)` ile kaydedilir; `component_hashes` içine maddenin `components` listesindeki her anahtarın `system_manifest_get(section="component_hashes")` değeri konur (sürüm değişince yalnızca etkilenen maddeler `stale` olur; 12.13). Profil/hesap/veri yoluna özgü sonuçlar `scope="profile:<id>" | "account:<id>" | "data_path:mcp|csv"` ile yazılır. Ortak zorunlu
maddeler geçince ve statik kontrol kayıtlıysa (`setup_static_ok_at`) `setup_verified_at` sunucu tarafından yazılır. `setup_static_ok_at` boşsa
kullanıcıya kurulum dosyasını (`kur.cmd`) yeniden çalıştırmasını söyle (veri korunur, güncelleme olarak tanınır). Geçmeyen madde kullanıcıya nasıl düzeltileceğiyle söylenir; başarısız
güvenlik kontrolü "uygulanamaz" diye gizlenmez.
