---
description: "Aktif kampanyanın durumunu, takvimini ve bekleyen işleri gösterir"
---

Bu komut oturumu plugin moduna alır (UserPromptSubmit/UserPromptExpansion hook'u `/reklam-atolyesi:` önekinden tanır); hook bağlamındaki `session_id`, `plugin` ve `data_dir` değerlerini kullan. Maliyet koruması ve Meta izin listesi bu oturumda geçerlidir.

`campaign_status(profile_id, campaign_id)`, `stage_resume`, `action_items_list`, `checkpoint_get` ve tur takvimiyle navigator üst satırı biçiminde kısa durum ver (aşama, bekleyen kapı, uyarılar, uygulama listesi, G<n>/<test günü>, plan günü). Değişiklik yapma.
