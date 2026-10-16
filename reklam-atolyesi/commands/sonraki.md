---
description: "Aktif kampanyanın mevcut aşamasını yürütür (devam et)"
---

Bu komut oturumu plugin moduna alır (UserPromptSubmit/UserPromptExpansion hook'u `/reklam-atolyesi:` önekinden tanır); hook bağlamındaki `session_id`, `plugin` ve `data_dir` değerlerini kullan. Maliyet koruması ve Meta izin listesi bu oturumda geçerlidir.

Aktif kampanyanın mevcut aşamasını oku (`campaign_status`); önce `stage_resume` ile devam notunu tablo/dosya hash'leriyle doğrula; ilgili aşama skill'ini çalıştır (`S01→brief`, `S01b→competitor-analysis`, `S02→strategy`, `S03→concepts`, `S04→shoot-guide`, `S05→shoot-feedback`, `W→` çekim bekleniyor (yalnızca dosya durumunu sor), `S06→ingest`, `S07→analyze`, `S08→style-directions`, `S09→materials`, `S10→compose`, `S11→sound`, `S12→variants`, `S13→qc`, `S14→launch-pack`, `S15→track`, `S16→coach`, `S17→learn`). Kapıda ise özet ve açık onay sorusu; kapıyı kendiliğinden geçme.
