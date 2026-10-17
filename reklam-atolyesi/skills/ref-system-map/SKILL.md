---
name: ref-system-map
description: "reklam-atolyesi'nin kendi haritası (system_manifest). \"Ne yapabilirsin\", \"sistem durumu\", sürüm, bileşen ve canlı doğrulama sorularında plugin modunda kullanılır."
---

# ref-system-map — sistem kendini bilir (spec 12.13, ilke 11)

## Amaç
"Ne yapabilirsin?", "Sistem ve hesap durumu", "hangi sürüm", "şu kontrol geçti mi" sorularını **tahminle değil** manifest ve canlı
kayıtla cevaplamak.

## Kaynaklar
- **Dağıtılan manifest** `PR/system_manifest.json` (değişmez; hesap, makine, OAuth, canlı sonuç ya da görev durumu içermez).
  Bölümleri: `plugin_version`, `capabilities`, `stages`, `skills`, `agents`, `commands`, `workflows`, `hooks`, `mcp_servers`,
  `mcp_tools`, `pipelines`, `scripts` (işlev → dosya haritası), `templates`, `tests` (statik/sentetik sonuçlar), `deviations`
  (belgeden sapmalar ve gerekçeleri), `neutrality_audit`, `live_checks` (canlı kontrol tanımları), `component_hashes`.
- **Canlı kayıt** `settings.runtime_verification_json` (veritabanında): madde, kapsam (`common | profile:<id> | account:<id> |
  data_path:<mcp|csv>`), durum (`pending | passed | failed | not_applicable | stale`), zaman, kanıt referansı, doğrulanan bileşen
  hash'leri, manifest SHA-256'sı. Token/kimlik bilgisi içermez.
- **Kuruluma özgü sapmalar:** makineye/kuruluma ait, kullanıcının açıkça kabul ettiği sapmalar (ör. disk alanı) dağıtılan manifeste
  yazılmaz; `settings.install_deviations_json`'da tutulur ve `system_manifest_get().install_deviations` ile görünür.
- **Birleşik görünüm:** `system_manifest_get(section?)`. Eşleşmeyen ya da eski manifest hash'li kayıt başarı sayılmaz (`stale`);
  canlı kayıt yoksa uygulanabilir bütün maddeler `pending` görünür.

## Kullanım
1. Genel soru → `system_manifest_get()`; ayrıntı → `system_manifest_get(section="capabilities" | "stages" | "deviations" | …)`.
2. Cevap manifestteki gerçek bileşenlerle sınırlıdır; manifestte olmayan yetenek vaat edilmez. Sapma (`deviations` ve `install_deviations`) varsa söylenir
   (ör. workflow yerine yedek yol; bu kurulumdaki disk alanı kararı).
3. **Canlı kayıt yazma:** yalnızca canlı kontrol gerçekten yürütüldüğünde `runtime_record(item_id, status, scope, evidence_ref,
   component_hashes, not_applicable_reason?)`. Uygulanamaz madde gerekçe ister; başarısız güvenlik kontrolü "uygulanamaz" etiketiyle
   gizlenmez. Ortak zorunlu maddeler geçince ve statik kontrol (`setup_static_ok_at`, doctor) kayıtlıysa `setup_verified_at` sunucu tarafından
   yazılır; statik kayıt yoksa kurulum dosyası (`kur.cmd`) yeniden çalıştırılır. Dağıtılan manifest değiştirilmez.
4. **"Sistem ve hesap durumu" ekranı:** bağlantılar (ElevenLabs, Meta MCP ya da CSV yolu), OAuth durumu, disk (`data_dir` sürücüsü ve
   sistem sürücüsü), son yedek (`settings.last_backup_at`), hata kayıtları (`DD/logs/`), `cost_summary`, render süreleri (sistem
   hafızası), `calibration_get` (koçluk isabeti), kullanım raporu (`memory_tools.py usage-report`).

## Yetenek özeti (manifestle doğrulanarak söylenir)
- Faz 2 tanışma: marka (S00a), Meta geçmişi (S00b), ürün (S00c).
- Faz 3 döngü: brief → rakip analizi → strateji (kapı) → konsept görüşmesi (kapı) → çekim rehberi → deneme → ingest → analiz →
  stil (kapı) → malzeme (kapı, maliyet) → kurgu → ses (kapı, taslak) → varyasyon/export → QC (kapı) → yayın paketi (kapı) →
  insan yayını (`launch_confirm`) → takip → koçluk (kapı) → öğrenme (kapı).
- Plugin **yapmaz:** Meta'ya yazmak, reklam yayına almak, bütçe değiştirmek; onaysız ücretli üretim; rakip hesaplarına erişim,
  sosyal medya kazıma; çekimin kendisi.

## Kontroller
- Manifestte "ilk açılışta bekliyor" olan canlı maddeler geçmiş gibi anlatılmaz.
- Sürüm değişiminden sonra etkilenen canlı maddeler `stale`'dir; yeniden doğrulanır, kanıt taşınmaz.
