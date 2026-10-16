---
description: "Bu oturumun profilini ve yeni oturum varsayılanını değiştirir"
argument-hint: "<profil>"
---

Bu komut oturumu plugin moduna alır (UserPromptSubmit/UserPromptExpansion hook'u `/reklam-atolyesi:` önekinden tanır); hook bağlamındaki `session_id`, `plugin` ve `data_dir` değerlerini kullan. Maliyet koruması ve Meta izin listesi bu oturumda geçerlidir.

Hedef: `$ARGUMENTS` (profil kimliği, slug ya da ad). Belirsizse `profile_list` ile en fazla 3 seçenek sun. `profile_set_active(profile_id, session_id)` — bu oturumun seçimi ve yeni oturum varsayılanı değişir; başka oturumların ve görevlerin bağlı kimlikleri değişmez. Yeni profilde Meta veri yolu/yetki durumu kontrol edilir; önceki profilin doğrulaması devralınmaz. Sonra navigator menüsü.
