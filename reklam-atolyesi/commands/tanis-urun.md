---
description: "S00c ürün tanışmasını başlatır"
argument-hint: "<ürün>"
---

Bu komut oturumu plugin moduna alır (UserPromptSubmit/UserPromptExpansion hook'u `/reklam-atolyesi:` önekinden tanır); hook bağlamındaki `session_id`, `plugin` ve `data_dir` değerlerini kullan. Maliyet koruması ve Meta izin listesi bu oturumda geçerlidir.

Bağlı profil için `reklam-atolyesi:product-onboarding` skill'ini çalıştır; ürün adı/kimliği: `$ARGUMENTS` (boşsa sor). Profil `active` değilse önce tanışmanın eksik adımı tamamlanır.
