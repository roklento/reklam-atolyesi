---
description: "Rakip analizini (S01b) çalıştırır; kampanya yoksa profil düzeyinde görüntü alır"
argument-hint: "[yenile]"
---

Bu komut oturumu plugin moduna alır (UserPromptSubmit/UserPromptExpansion hook'u `/reklam-atolyesi:` önekinden tanır); hook bağlamındaki `session_id`, `plugin` ve `data_dir` değerlerini kullan. Maliyet koruması ve Meta izin listesi bu oturumda geçerlidir.

`reklam-atolyesi:competitor-analysis` skill'ini çalıştır. Aktif kampanya S01b'deyse aşama olarak; değilse **profil düzeyinde** görüntü (`campaign_id`/`cycle_id` boş). `$ARGUMENTS` `yenile` ise 14 günden yeni görüntü olsa da tam görüntü al; değilse tazelik kuralı (yalnızca fark).
