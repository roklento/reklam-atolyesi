---
description: "Haftalık bakım (zamanlanmış): yedek, Meta senkronu, OAuth kontrolü, hafıza adayları"
argument-hint: "--profile <id>"
---

Bu komut oturumu plugin moduna alır (UserPromptSubmit/UserPromptExpansion hook'u `/reklam-atolyesi:` önekinden tanır); hook bağlamındaki `session_id`, `plugin` ve `data_dir` değerlerini kullan. Maliyet koruması ve Meta izin listesi bu oturumda geçerlidir.

Argümanlar: `$ARGUMENTS` — `--profile <id>` **zorunlu** (bakım profil başına çalışır).

**İş kuralları (4.4):** bu bir zamanlanmış iş girişidir. Kullanıcıya **soru sorma**; kapı geçirme; karar verme. Ücretli dış servis (ElevenLabs ücretli araçları) ve Meta yazma aracı **asla** çağrılmaz. Kimlikler yalnızca argümanlardan gelir: aktif profil varsayılanını kullanma. Gerekli kimlik eksikse: elle (etkileşimli) çağrıldıysa navigator'de hedefi seçtirip bağla; zamanlanmış görevde çalışma, nedeni günlüğe ve bildirime yaz. Başlarken `session_bind(session_id, profile_id, campaign_id?, cycle_id?)`, sonra `job_claim(profile_id, job_id, session_id)` (iş kimliği `profiles.jobs_json`'da; navigator `job_upsert` ile oluşturur). Sahiplenme reddedilirse mevcut çalışmanın durumunu bildir ve dur; yarım kalmış sahiplenme varsa önce çıktı/işlem durumunu uzlaştır (`job_finish(..., status="reconciled")`). Bitince `job_finish(profile_id, job_id, session_id, status=ok|failed|skipped, data_version, output_ref, note)` — tetiklenme başarı sayılmaz. Karar gerektiren durum (OAuth süresi, yapı sapması, bütçe sınırı, risk sınırı aşımı) devam notuna ve navigator üst satırına yazılır, bildirim bırakılır.

İş: ortak yedek `backup_if_due(days=7)` (`last_backup_at` ile tekrarlanmaz) · MCP profilinde Meta geçmiş senkronu (`meta-historian`, artımlı, salt okuma; CSV profilinde eksik dışa aktarımı not et) · OAuth durumu (okuma çağrısı başarısızsa üst satıra) · `consolidation_due(profile_id)` ve aday grup **sayısı** raporu · `generations_reconcile_due` (salt okuma uzlaştırma) · rakip önizleme önbelleğinde 30 günü geçen dosyaların temizliği (yalnızca `DD/profiles/<slug>/competitors/cache/` altında; `competitor_ads` satırları kalır). Asla: hafıza öğelerini birleştirmek (kullanıcıyla yapılır), ücretli/yazma çağrısı.
