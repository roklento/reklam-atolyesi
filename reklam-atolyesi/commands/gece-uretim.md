---
description: "Gece üretimi (zamanlanmış): çekim tamam sonrası ingest, analiz ve tamamlanmamış render'lar"
argument-hint: "--profile <id> --campaign <id> --cycle <id>"
---

Bu komut oturumu plugin moduna alır (UserPromptSubmit/UserPromptExpansion hook'u `/reklam-atolyesi:` önekinden tanır); hook bağlamındaki `session_id`, `plugin` ve `data_dir` değerlerini kullan. Maliyet koruması ve Meta izin listesi bu oturumda geçerlidir.

Argümanlar: `$ARGUMENTS` — `--profile`, `--campaign`, `--cycle` **zorunlu**.

**İş kuralları (4.4):** bu bir zamanlanmış iş girişidir. Kullanıcıya **soru sorma**; kapı geçirme; karar verme. Ücretli dış servis (ElevenLabs ücretli araçları) ve Meta yazma aracı **asla** çağrılmaz. Kimlikler yalnızca argümanlardan gelir: aktif profil varsayılanını kullanma. Gerekli kimlik eksikse: elle (etkileşimli) çağrıldıysa navigator'de hedefi seçtirip bağla; zamanlanmış görevde çalışma, nedeni günlüğe ve bildirime yaz. Başlarken `session_bind(session_id, profile_id, campaign_id?, cycle_id?)`, sonra `job_claim(profile_id, job_id, session_id)` (iş kimliği `profiles.jobs_json`'da; navigator `job_upsert` ile oluşturur). Sahiplenme reddedilirse mevcut çalışmanın durumunu bildir ve dur; yarım kalmış sahiplenme varsa önce çıktı/işlem durumunu uzlaştır (`job_finish(..., status="reconciled")`). Bitince `job_finish(profile_id, job_id, session_id, status=ok|failed|skipped, data_version, output_ref, note)` — tetiklenme başarı sayılmaz. Karar gerektiren durum (OAuth süresi, yapı sapması, bütçe sınırı, risk sınırı aşımı) devam notuna ve navigator üst satırına yazılır, bildirim bırakılır.

İş (tek seferlik): kampanya S06'daysa `reklam-atolyesi:ingest`, ardından `reklam-atolyesi:analyze` (workflow ya da yedek yol). Onaylı kurgu planları varsa aynı turdaki **tamamlanmamış** yerel render'lar (`render-variants`; doğrulanmış çıktılar yeniden yapılmaz). Yalnızca hâlâ geçerli ve tamamlanmamış çıktılar üretilir. Asla: ücretli üretim (maliyet koruması zaten engeller), kapı geçmek, kullanıcıya soru.
