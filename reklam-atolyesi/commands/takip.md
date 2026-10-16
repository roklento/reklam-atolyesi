---
description: "Günlük takip işi (zamanlanmış): Meta okuma, metrikler, uyarılar"
argument-hint: "--profile <id> --campaign <id>"
---

Bu komut oturumu plugin moduna alır (UserPromptSubmit/UserPromptExpansion hook'u `/reklam-atolyesi:` önekinden tanır); hook bağlamındaki `session_id`, `plugin` ve `data_dir` değerlerini kullan. Maliyet koruması ve Meta izin listesi bu oturumda geçerlidir.

Argümanlar: `$ARGUMENTS` — `--profile <id>` ve `--campaign <id>` **zorunlu**.

**İş kuralları (4.4):** bu bir zamanlanmış iş girişidir. Kullanıcıya **soru sorma**; kapı geçirme; karar verme. Ücretli dış servis (ElevenLabs ücretli araçları) ve Meta yazma aracı **asla** çağrılmaz. Kimlikler yalnızca argümanlardan gelir: aktif profil varsayılanını kullanma. Gerekli kimlik eksikse: elle (etkileşimli) çağrıldıysa navigator'de hedefi seçtirip bağla; zamanlanmış görevde çalışma, nedeni günlüğe ve bildirime yaz. Başlarken `session_bind(session_id, profile_id, campaign_id?, cycle_id?)`, sonra `job_claim(profile_id, job_id, session_id)` (iş kimliği `profiles.jobs_json`'da; navigator `job_upsert` ile oluşturur). Sahiplenme reddedilirse mevcut çalışmanın durumunu bildir ve dur; yarım kalmış sahiplenme varsa önce çıktı/işlem durumunu uzlaştır (`job_finish(..., status="reconciled")`). Bitince `job_finish(profile_id, job_id, session_id, status=ok|failed|skipped, data_version, output_ref, note)` — tetiklenme başarı sayılmaz. Karar gerektiren durum (OAuth süresi, yapı sapması, bütçe sınırı, risk sınırı aşımı) devam notuna ve navigator üst satırına yazılır, bildirim bırakılır.

İş: `reklam-atolyesi:track` skill'inin takip adımları (eksik tarih aralığını al; MCP yolunda salt okuma, CSV profilinde dış veri beklendiğini kaydet; ölçüm bağlamı; yapı tespiti; veri kalitesi; yorgunluk/anomali; bütçe ve zarar-risk uyarıları → `action_items_set` (`proposed`) + bildirim; uygulandı mı kontrolü). Uyarı yoksa bildirim yok. Asla: ücretli dış servis veya Meta yazma çağrısı.
