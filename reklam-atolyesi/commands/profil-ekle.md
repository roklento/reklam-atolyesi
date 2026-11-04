---
description: "Yeni bir marka ya da reklam hesabı eklemek için tanışmayı başlatır"
argument-hint: "[profil adı]"
---

Bu komut oturumu plugin moduna alır (UserPromptSubmit/UserPromptExpansion hook'u `/reklam-atolyesi:` önekinden tanır); hook bağlamındaki `session_id`, `plugin` ve `data_dir` değerlerini kullan. Maliyet koruması ve Meta izin listesi bu oturumda geçerlidir.

Yeni profil adı: `$ARGUMENTS` (boşsa sor). `reklam-atolyesi:brand-onboarding` skill'ini yeni profil olarak başlat (mevcut profiller etkilenmez; 17.3).
