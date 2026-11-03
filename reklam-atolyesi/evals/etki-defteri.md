# Etki defteri

Her sürümde neyi değiştirdiğimizi ve bunun ne işe yaradığını tek yerde tutar. Sonraki revizeye başlarken ilk okunan dosya budur:
daha önce bozduğu görülen bir değişiklik tekrar denenmez, işe yaradığı görülen bir biçim yeniden kullanılır.

## Nasıl yazılır

Her sürüm bir bölümdür. Bölümde üç şey olur:

1. **Değişiklikler:** değişen her bileşen için bir satır.
   - *Bileşen:* skill, kural (KURALLAR.md), hook, betik, ajan ya da sunucu aracı.
   - *Tür:* işleyiş (kapı, hook, araç, bütçe hesabı gibi nasıl çalıştığı) ya da uzman bilgisi (Meta kuralı, sektör, yasal liste,
     kreatif gibi ne bildiği).
   - *Etkilenen vaka ya da senaryo hücresi:* evals/vakalar/ adı ya da ürün × kullanıcı (ör. P4.U1).
   - *Gözlenen fark:* eval puanı, kör karşılaştırma sonucu ya da sahadaki gösterge; nereden görüldüğüyle.
   - *Karar:* **yardım etti**, **bozdu**, **etkisiz** ya da **karışık**. Aynı sürümde birden çok bileşen birlikte değiştiyse ve hiçbir
     vaka birini tek başına ayırmıyorsa karar "karışık"tır. Uydurulmuş bir neden-sonuç, sonraki sürümleri yanlış yönlendirir.
2. **Sahada:** `python evals/defter_oku.py <defterler>` raporunun 1. tablosundaki bu sürümün satırı. İlk müşteri defterleri gelene
   kadar boş kalır; geldikçe doldurulur.
3. **Ders (en fazla bir):** yalnızca değişiklik satırları destekliyorsa. *Ne zaman:* derslerin geçerli olduğu durumun biçimi (bu
   sürümün ayrıntısı değil). *Ne yap:* hangi bileşende ne yapılacağı. *Dayanak:* hangi satır(lar). *Güven:* yüksek, orta ya da düşük.
   Destek yoksa "ders yok" yazılır.

## Yeni metin nereye konur

Bir revize yeni bir talimat getirdiğinde önce bu sıra denenir: **skill** (tetikleyicisi belli bir durum için) → **betik** (hep aynı
yapılan, kodla doğrulanabilen iş) → **ajan** (girdisi büyük, cevabı küçük ayrı bir iş) → **hook** (modelin atlayamaması gereken
kontrol) → **her zaman bağlamda duran metin** (KURALLAR.md özeti, en son ve yalnızca her oturum için geçerli kısa bir kural). Her
zaman duran metne bir satır eklenirse başka bir satır kısaltılır; CI özetin boyutunu denetler (`scripts/setup/ci_check.py`).

---

## 2.8.0 (2026-11-03): hata defteri ve geliştirme döngüsü

**Değişiklikler**

| Bileşen | Tür | Etkilenen vaka / hücre | Gözlenen fark | Karar |
|---|---|---|---|---|
| `hooks/error_notify.py` | işleyiş | hata-sonrasi-defter-sorusu (P4.U1) | Müşteriye "sağlayıcınıza gönderin" yerine tek ve sade soru; oturumda bir kez soruluyor (`tests/test_customer_update.py`) | ölçülecek (vaka yeni) |
| `admem/s_feedback.py`, `admem/feedback.py` | işleyiş | geri-bildirim-paketi | Defter imza taşıyor (adım · ne oldu · kod · ürün × kullanıcı); anonimlik denetimi aynen geçiyor (`tests/test_v280_feedback_loop.py`) | yardım etti (test) |
| `skills/ref-system-map`, `hooks/menu.json`, KURALLAR K15 | uzman bilgisi | geri-bildirim-paketi | Müşteriye "paket/önizleme/dışa aktarma" yerine "hata defteri" | ölçülecek |
| `evals/defter_oku.py`, `evals/kor_kiyas.py` | işleyiş (admin) | — | Müşteri akışına girmez | — |

**Sahada:** ilk defterler gelince doldurulacak.

**Ders:** yok (ilk sürüm; henüz karşılaştırılacak bir önceki defter yok).
