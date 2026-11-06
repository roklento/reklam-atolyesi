---
description: "Onayını bekleyen adımı, senin açık onayınla tamamlar"
argument-hint: "[tutar]"
---

Bu komut oturumu plugin moduna alır (UserPromptSubmit/UserPromptExpansion hook'u `/reklam-atolyesi:` önekinden tanır); hook bağlamındaki `session_id`, `plugin` ve `data_dir` değerlerini kullan. Maliyet koruması ve Meta izin listesi bu oturumda geçerlidir.

Bekleyen kapıyı bul (`campaign_status` / `stage_resume`). Kapı özetini (aşamanın kapı mesajı) bu oturumda kullanıcıya göstermediysen önce göster ve onayı sor; gösterildiyse bu komut kullanıcının o özete açık onayıdır: `gate_approve(session_id, profile_id, stage_run_id, output_version, cycle_id=…, note="$ARGUMENTS", checkpoint=…)` (onay bu komut mesajının kendisidir; hook onu oturuma yazar). Komutun arkasına yalnızca onay kelimeleri ya da onaylanan tutar yazılabilir; şart, ret ya da değişiklik içeren ek ("/onayla ama …", "/onaylama") onay sayılmaz, sunucu reddeder ve kullanıcıya yeniden sorarsın. Sunucu engel bildirirse (eksik risk sınırı, QC'den geçmemiş kreatif, eski sürüm…) onaylanmadığını ve nedenini söyle. Değişiklik isteği onay değildir.
