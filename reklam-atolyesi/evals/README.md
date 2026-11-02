# Değerlendirme seti (2.5.0)

Plugin iki katmanda sınanır. İkisi de aynı senaryo matrisine (`senaryo-matrisi.json`) dayanır: 8 ürün türü × 8 kullanıcı profili.

| Katman | Ne sınar | Nerede | Ne zaman |
|---|---|---|---|
| A. Deterministik | Kurallar, kapılar, bütçe hesabı, taslak denetimi; her ürün × kullanıcı birleşimi S00a'dan yayın kaydına kadar | `tests/test_v250_scenarios.py` (pytest) | Her push ve PR'da CI (`.github/workflows/ci.yml`) |
| B. Model cevabı | Modelin kullanıcıya cevabı: kural uyumu, seçenekli soru, sade dil, dürüstlük, ürüne uygunluk, net adım | `vakalar/<ad>/` (`claude plugin eval`) + `rubrik.md` | Her sürümden önce elle |

## Ürünler ve kullanıcılar

Ürünler: P1 düşük fiyatlı fiziksel · P2 yüksek fiyatlı fiziksel · P3 dijital · P4 hizmet (müşteri adayı) · P5 sezonluk ·
P6 katkısı bilinmeyen · P7 katkısı aralık · P8 zararına satılan (katkı ≤ 0).

Kullanıcılar: U1 yeni başlayan düşük bütçe · U2 orta bütçe sınırsız · U3 deneyimli (2. turda kreatif test) · U4 ajans çok profil ·
U5 CSV modu · U6 USD hesap · U7 bütçesi iki reklama yetmeyen · U8 toplam sınırı planı karşılamayan.

Beklenen sonuçlar matriste yazılıdır (kodun kendisinden türetilmez): U7 ve U8'de S02 kapısı bütçe nedeniyle kapanır; P8'de kullanıcı
zararı bilerek kabul edip sözü kaydedilmeden kapı açılmaz; diğer birleşimler yayın kaydına kadar ilerler.

## Katman A'yı çalıştırma

```
cd servers/ad_memory
uv run --with pytest python -m pytest -q ../../tests/test_v250_scenarios.py
```

Her birleşimde: kayıtlardan üretilen belge her metin aşamasında ilk turda geçer (yanlış alarm yok); belgedeki bir sayı kayıttan
saptırılınca denetim kritik sorun bulur (kaçırma yok); kapı beklenen nedenle açılır ya da kapanır.

## Katman B'yi çalıştırma (yayın öncesi)

```
claude plugin eval ./reklam-atolyesi --trust-plugin --runs 3 --threshold 0.8 --ablation with-without
```

- Vakalar araç çağırmadan kullanıcıya verilecek cevabı ister; ad-memory ve Meta sunucuları başlatılmaz (mock yok). Bu bilinçli bir
  sınırdır: araç akışını Katman A sınar, burada yalnızca cevabın niteliği puanlanır.
- `--ablation with-without` plugin'siz bir kol da çalıştırır; fark plugin'in katkısını gösterir.
- Çalıştırma sahibinin Claude hesabıyla yapılır ve ücretlidir; `--max-cost-usd` ile sınır konabilir.
- Sonuçlar `evals/results/` altına yazılır (depoya girmez).
- Eşik: her vaka ≥ 0,8. Altında kalan vaka sürümü durdurur; ilgili skill ya da `KURALLAR.md` düzeltilir, vaka yeniden çalıştırılır.

## Yeni vaka ya da senaryo ekleme

1. Gerekirse `senaryo-matrisi.json`'a ürün/kullanıcı ekleyin (`expect` alanıyla beklenen kapı sonucu).
2. Vaka için `eval_cases` altına `{product, user, rubric}` yazın.
3. `vakalar/<ad>/prompt.md` (durum + kullanıcının sözü) ve her rubrik ölçütü için `graders/<rN>-<ad>.md` (`type: llm`,
   `weight`, ölçüt kodu ve geçer/kalır tarifi) ekleyin.
4. `tests/test_v250_scenarios.py::test_matrix_and_eval_cases_are_consistent` matris, rubrik ve dosyaların birbirini tuttuğunu denetler.
