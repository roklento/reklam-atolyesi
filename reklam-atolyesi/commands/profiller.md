---
description: "Profil listesini gösterir"
---

Bu komut oturumu plugin moduna alır (UserPromptSubmit/UserPromptExpansion hook'u `/reklam-atolyesi:` önekinden tanır); hook bağlamındaki `session_id`, `plugin` ve `data_dir` değerlerini kullan. Maliyet koruması ve Meta izin listesi bu oturumda geçerlidir.

`profile_list()` ile profilleri (ad, durum, reklam hesabı, son iş) göster; bu oturuma bağlı profili ve yeni oturum varsayılanını belirt. Sonra navigator menüsüne dön.
