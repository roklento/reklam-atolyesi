---
name: shoot-feedback
description: "reklam-atolyesi S05 deneme geri bildirimi — deneme klibinde ffprobe, kontak sayfası ve ölçüm; en fazla 3 somut, jargonsuz düzeltme; \"tam çekime geç\" ya da \"bir deneme daha\"; W bekleme."
---

# shoot-feedback — S05 · Deneme geri bildirimi ve W · Çekim bekleniyor (spec 5.3, 5.5, 4.1, 4.2)

## Amaç
Tam çekimden önce kısa bir denemeyle çekimcinin en çok yaptığı hataları yakalamak. Geri bildirim **en fazla 3 somut madde**, jargonsuz
("telefonu masaya yasla"). Teknik sorunlar (VFR, HDR) çekimciye yüklenmez; ingest çözer. İnceleme `cinematographer` ajanının yöntemiyle.

## Ön koşul
S04 kapısı geçilmiş; deneme klip(ler)i kullanıcıdan alınmış → `DD/profiles/<slug>/campaigns/<k>/footage/deneme/` (ham deneme dosyasına
dokunulmaz; tam çekim dosyaları değildir, ingest'e girmez).

## Girdiler ve bağlam paketi
`memory_context(profile_id, "S05", campaign_id, cycle_id)`: ürün çekim tarifi, çekim prosedürleri, önceki deneme geri bildirimleri.
Çekim rehberi ve `analysis/shoot_menu.json`.

## Kullanılan hazır skill'ler ve OVERRIDES
Yok (ölçüm plugin script'leriyle).

## Adımlar
1. `stage_start(profile_id, "S05", campaign_id, cycle_id)`.
2. Her deneme klibi için:
   - Teknik: `PY PR/scripts/ingest/convert.py probe <klip>` (çözünürlük, fps, VFR, HDR, döndürme, ses).
   - Kontak sayfası: `PY PR/scripts/analyze/contact_sheet.py --video <klip> --out analysis/deneme/<ad>_sheet.jpg` → görsele **bak**.
   - Ölçüm: `PY PR/scripts/analyze/measure.py --clip <klip> [--audio <wav>] --out analysis/deneme/<ad>_measure.json`
     (netlik, pozlama/kırpılma, hareket, ses; sarsıntı için `vidstabdetect` ingest'te yapılır, burada kontak sayfasından da değerlendirilir).
3. Bulguları rehberdeki ürün tarifi ve 7 kurala göre sırala; **en etkili en fazla 3** düzeltmeyi seç. Kurtarılamayan üç şeye öncelik:
   odaksız kare, patlamış beyazlar, hareket bulanıklığı. Ses niyeti "çekimdeki ses" olan çekimde gürültü tabanı yüksekse kayıt
   talimatını hatırlat.
4. Sonuç: **"tam çekime geç"** ya da **"bir deneme daha"**. Rapor: `analysis/deneme/c<tur>-deneme-<n>.md` (atomik).
5. Kalıcı bulgu ürün tarifini değiştiriyorsa (ör. parlak yüzey için pozlama kartı) kullanıcıya önerilir; onaylanırsa
   `product_upsert(shoot_profile_json=…)`. Tekrarlayan çekim hatası `memory_add(layer="procedural", kind="shooting", …)`.
6. `stage_complete(profile_id, "S05", outputs=[{path: rapor}], summary, campaign_id, cycle_id)` → kampanya **W** (çekim bekleniyor).

### W · Çekim bekleniyor
- Kullanıcı dosyaları `footage/raw/` ve `photos/raw/` altına koyup **"çekim tamam"** deyince: `shoot_mark_done(profile_id, campaign_id,
  cycle_id, note)` (son 2 dakikada değişen dosya varsa sunucu reddeder: kopyalama sürüyor olabilir; bekle). Kampanya S06'ya geçer.
- Masaüstü uygulaması ve kullanıcı onayı varsa **gece üretimi** görevi kurulur (navigator §6): `/reklam-atolyesi:gece-uretim
  --profile <id> --campaign <id> --cycle <id>`; aksi halde S06 bu oturumda başlar.
- Kullanıcı "bir deneme daha" isterse: `stage_back(profile_id, campaign_id, cycle_id, target_stage="S05", reason)`.
- Navigator açılışında yeni dosya görülürse yalnızca sorulur; kendiliğinden "tamam" sayılmaz.

## Çıktılar
Deneme raporu, kontak sayfaları ve ölçüm JSON'ları (`analysis/deneme/`), varsa ürün tarifi güncellemesi, devam notu; W'de `shoot_done` kararı.

## Kontroller
- En fazla 3 madde; her madde somut ve uygulanabilir; teknik dönüşüm sorunları çekimciye yüklenmedi.
- Deneme dosyaları ingest'e girmedi; ham dosyalar değiştirilmedi.

## Kapı mesajı
Kapı yoktur. Kullanıcıya: "Denemeye baktım. 1) … 2) … 3) … Sonuç: <tam çekime geç | bir deneme daha>. Çekim bitince dosyaları
footage/raw ve photos/raw'a koyup 'çekim tamam' yaz."
