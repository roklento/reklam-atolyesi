---
description: "Son koçluk raporunu ya da güncel performans özetini gösterir"
---

Bu komut oturumu plugin moduna alır (UserPromptSubmit/UserPromptExpansion hook'u `/reklam-atolyesi:` önekinden tanır); hook bağlamındaki `session_id`, `plugin` ve `data_dir` değerlerini kullan. Maliyet koruması ve Meta izin listesi bu oturumda geçerlidir.

Aktif kampanyanın son koçluk raporunu (`reports/` en yeni sürüm) ve uygulama listesi durumunu göster. Rapor yoksa ya da veri yenilenmişse `reklam-atolyesi:track` + `reklam-atolyesi:coach` akışını öner (S16 kapısı kullanıcı onayı ister).
