---
description: "Bekleyen kapıyı kullanıcının açık onayıyla geçirir"
argument-hint: "[not]"
---

Bu komut oturumu plugin moduna alır (UserPromptSubmit/UserPromptExpansion hook'u `/reklam-atolyesi:` önekinden tanır); hook bağlamındaki `session_id`, `plugin` ve `data_dir` değerlerini kullan. Maliyet koruması ve Meta izin listesi bu oturumda geçerlidir.

Bekleyen kapıyı bul (`campaign_status` / `stage_resume`). Kapı özetini (aşamanın kapı mesajı) bu oturumda kullanıcıya göstermediysen önce göster ve onayı sor; gösterildiyse bu komut kullanıcının o özete açık onayıdır: `gate_approve(profile_id, stage_run_id, output_version, approval_text="/onayla $ARGUMENTS", cycle_id, note="$ARGUMENTS", checkpoint=…)`. Sunucu engel bildirirse (eksik risk sınırı, QC'den geçmemiş kreatif, eski sürüm…) onaylanmadığını ve nedenini söyle. Değişiklik isteği onay değildir.
