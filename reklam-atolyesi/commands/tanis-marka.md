---
description: "S00a marka tanışmasını doğrudan başlatır"
---

Bu komut oturumu plugin moduna alır (UserPromptSubmit/UserPromptExpansion hook'u `/reklam-atolyesi:` önekinden tanır); hook bağlamındaki `session_id`, `plugin` ve `data_dir` değerlerini kullan. Maliyet koruması ve Meta izin listesi bu oturumda geçerlidir.

Oturuma bağlı (yoksa seçilen) profil için `reklam-atolyesi:brand-onboarding` skill'ini çalıştır. Profil yoksa yeni profil açılır.
