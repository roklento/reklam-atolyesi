---
description: "Reklam Atölyesi ana menüsünü (navigator) açar"
---

Bu komut oturumu plugin moduna alır (UserPromptSubmit/UserPromptExpansion hook'u `/reklam-atolyesi:` önekinden tanır); hook bağlamındaki `session_id`, `plugin` ve `data_dir` değerlerini kullan. Maliyet koruması ve Meta izin listesi bu oturumda geçerlidir.

`reklam-atolyesi:navigator` skill'ini çalıştır: canlı doğrulama durumu, profil 0 ise tanışma, açık devam notu varsa "kaldığımız yer", sonra numaralı menü (17.1–17.2). Kullanıcının yalnızca plugin adını yazmasıyla aynıdır.
