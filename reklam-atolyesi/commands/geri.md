---
description: "Geçmiş bir aşamaya döner; sonraki çıktılar eski işaretlenir"
argument-hint: "<aşama>"
---

Bu komut oturumu plugin moduna alır (UserPromptSubmit/UserPromptExpansion hook'u `/reklam-atolyesi:` önekinden tanır); hook bağlamındaki `session_id`, `plugin` ve `data_dir` değerlerini kullan. Maliyet koruması ve Meta izin listesi bu oturumda geçerlidir.

Hedef aşama: `$ARGUMENTS` (ör. S03). Etkisini açıkla (sonraki aşamaların çıktıları ve onayları "eski" olur; ücretli üretimler silinmez, yeniden kullanılmak üzere işaretlenir; gerçek yayın kaydından sonra S14 ve öncesine dönülmez) ve kullanıcı onaylarsa `stage_back(profile_id, campaign_id, cycle_id, target_stage, reason)`. Sonra o aşamanın skill'i.
