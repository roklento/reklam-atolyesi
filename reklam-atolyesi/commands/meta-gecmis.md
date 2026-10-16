---
description: "Meta geçmişini (S00b) çalıştırır ya da artımlı senkron yapar"
---

Bu komut oturumu plugin moduna alır (UserPromptSubmit/UserPromptExpansion hook'u `/reklam-atolyesi:` önekinden tanır); hook bağlamındaki `session_id`, `plugin` ve `data_dir` değerlerini kullan. Maliyet koruması ve Meta izin listesi bu oturumda geçerlidir.

Bağlı profil için `reklam-atolyesi:meta-history` skill'ini çalıştır (tam ya da artımlı; MCP yolunda `meta-historian` ajanıyla salt okuma, CSV yolunda dışa aktarım).
