# Bu depoda çalışan Claude oturumları için

Bu depo `reklam-atolyesi` plugin'idir. Çalışma kuralları ve yayın adımları `reklam-atolyesi/README.md` ve
`reklam-atolyesi/evals/README.md` içindedir. Plugin'in değişmez kuralları `reklam-atolyesi/KURALLAR.md`'dedir.

## Düzeltme yazarken iki kural (2.10.0)

1. **`reklam-atolyesi/evals/kapali/` klasörünü açma.** Oradaki vakalar, bir düzeltmenin gördüğümüz vakaların dışında da işe yarayıp
   yaramadığını gösteren tek ölçüdür. Yalnızca yayından önce `claude plugin eval` ile çalıştırılırlar. Bir kapalı vaka gerilerse
   onu açıp ona göre düzeltme yapma; bu sürümün düzeltmelerini genel kural olarak yeniden yaz. İstisna: kapalı vakayı yazmak ya da
   açık gruba taşımak için admin açıkça isterse.
2. **Vakanın kelimelerini plugin metnine yazma.** Düzeltme genel bir kural olarak yazılır: vakadaki ürün, marka, tutar ya da cümle
   skill'e, kurala ya da hook'a girmez. CI'daki ezber denetimi (`reklam-atolyesi/evals/ezber_denetimi.py`) 6 kelimelik birebir
   kopyayı ve vaka adını yakalar. Etki defterine (`reklam-atolyesi/evals/etki-defteri.md`) her değişikliğin gerekçesi yazılır.

Kullanıcıya ve müşteriye giden her metin KURALLAR K16'ya (sade ve net dil) uyar.
