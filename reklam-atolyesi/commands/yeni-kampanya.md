---
description: "Bir ürün için yeni kampanya açar ve reklamın özetini hazırlamakla başlar"
argument-hint: "<ürün>"
---

Bu komut oturumu plugin moduna alır (UserPromptSubmit/UserPromptExpansion hook'u `/reklam-atolyesi:` önekinden tanır); hook bağlamındaki `session_id`, `plugin` ve `data_dir` değerlerini kullan. Maliyet koruması ve Meta izin listesi bu oturumda geçerlidir.

Bağlı profilde `$ARGUMENTS` ürünü için (boşsa ürün seçtir; ürün tanışılmamışsa önce `product-onboarding`) `campaign_create` → `session_bind` → `reklam-atolyesi:brief` skill'i (17.9).
