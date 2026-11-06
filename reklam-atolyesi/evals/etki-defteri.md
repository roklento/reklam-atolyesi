# Etki defteri

Her sürümde neyi değiştirdiğimizi ve bunun ne işe yaradığını tek yerde tutar. Sonraki revizeye başlarken ilk okunan dosya budur:
daha önce bozduğu görülen bir değişiklik tekrar denenmez, işe yaradığı görülen bir biçim yeniden kullanılır.

**Kapalı vakalar (2.10.0):** `evals/kapali/` altındaki vakalar düzeltme yazarken açılmaz. Bir düzeltmenin gördüğümüz vakaların
dışında da işe yaradığını yalnızca onlar gösterir; açıp onlara göre düzeltme yapılırsa bu bilgi kaybolur. Ayrıntı:
`evals/README.md` "Kapalı vakalar".

## Nasıl yazılır

Her sürüm bir bölümdür. Bölümde üç şey olur:

1. **Değişiklikler:** değişen her bileşen için bir satır.
   - *Bileşen:* skill, kural (KURALLAR.md), hook, betik, ajan ya da sunucu aracı.
   - *Tür:* işleyiş (kapı, hook, araç, bütçe hesabı gibi nasıl çalıştığı) ya da uzman bilgisi (Meta kuralı, sektör, yasal liste,
     kreatif gibi ne bildiği).
   - *Etkilenen vaka ya da senaryo hücresi:* evals/vakalar/ adı ya da ürün × kullanıcı (ör. P4.U1).
   - *Gerekçe (2.10.0):* değişikliği ne istedi: bir saha imzası, bir vaka ya da bir revize. Gerekçe bir vaka adıysa, düzeltmenin o
     vakanın dışında hangi ürün × kullanıcı hücrelerine de uyduğu aynı hücrede yazılır. Yalnızca o vakaya uyan bir düzeltme genel
     kural değildir, yeniden yazılır.
   - *Gözlenen fark:* eval puanı (`kor_kiyas.py puan` sonucu: iyileşti / geriledi / fark yok), kör karşılaştırma sonucu ya da sahadaki
     gösterge; nereden görüldüğüyle. Puan "fark yok" diyorsa karar "yardım etti" yazılmaz.
   - *Harcama farkı (2.10.0):* `kor_kiyas.py puan` raporundaki harcama değişimi (ör. "+%12") ya da "ölçülmedi".
   - *Karar:* **yardım etti**, **bozdu**, **etkisiz** ya da **karışık**. Aynı sürümde birden çok bileşen birlikte değiştiyse ve hiçbir
     vaka birini tek başına ayırmıyorsa karar "karışık"tır. Uydurulmuş bir neden-sonuç, sonraki sürümleri yanlış yönlendirir.
   - Silinen bir bileşen için de satır yazılır ve karar sütununa **silindi** yazılır.
2. **Sahada:** `python evals/defter_oku.py <defterler>` raporunun 1. tablosundaki bu sürümün satırı. İlk müşteri defterleri gelene
   kadar boş kalır; geldikçe doldurulur.
3. **Ders (en fazla bir):** yalnızca değişiklik satırları destekliyorsa. *Ne zaman:* derslerin geçerli olduğu durumun biçimi (bu
   sürümün ayrıntısı değil). *Ne yap:* hangi bileşende ne yapılacağı. *Dayanak:* hangi satır(lar). *Güven:* yüksek, orta ya da düşük.
   Destek yoksa "ders yok" yazılır.

## Silmeye aday parçalar (2.10.0)

Revizeye başlarken `python evals/etki_ozeti.py` çalıştırılır. Betik bu dosyadaki tablolardan iki liste çıkarır:

- **Silmeye aday:** en az iki sürümde "etkisiz" diye yazılmış ve hiç "yardım etti" almamış bileşenler.
- **Ölçülmemiş:** üç ya da daha çok sürümde "ölçülecek" diye kalmış bileşenler. Bunlar ya ölçülür ya da etkisiz sayılır.

Betik hiçbir şeyi silmez. Silme kararı admin'indir. Silinen parça bu dosyaya "silindi" diye yazılır ve kör karşılaştırmayla bir şeyi
bozmadığı gösterilir.

## Yeni metin nereye konur

Bir revize yeni bir talimat getirdiğinde önce bu sıra denenir: **skill** (tetikleyicisi belli bir durum için) → **betik** (hep aynı
yapılan, kodla doğrulanabilen iş) → **ajan** (girdisi büyük, cevabı küçük ayrı bir iş) → **hook** (modelin atlayamaması gereken
kontrol) → **her zaman bağlamda duran metin** (KURALLAR.md özeti, en son ve yalnızca her oturum için geçerli kısa bir kural). Her
zaman duran metne bir satır eklenirse başka bir satır kısaltılır; CI özetin boyutunu denetler (`scripts/setup/ci_check.py`).

---

## 2.8.0 (2026-11-03): hata defteri ve geliştirme döngüsü

**Değişiklikler**

| Bileşen | Tür | Etkilenen vaka / hücre | Gerekçe | Gözlenen fark | Harcama farkı | Karar |
|---|---|---|---|---|---|---|
| `hooks/error_notify.py` | işleyiş | hata-sonrasi-defter-sorusu (P4.U1) | — (2.10.0 öncesi) | Müşteriye "sağlayıcınıza gönderin" yerine tek ve sade soru; oturumda bir kez soruluyor (`tests/test_customer_update.py`) | ölçülmedi | ölçülecek (vaka yeni) |
| `admem/s_feedback.py`, `admem/feedback.py` | işleyiş | geri-bildirim-paketi | — (2.10.0 öncesi) | Defter imza taşıyor (adım · ne oldu · kod · ürün × kullanıcı); anonimlik denetimi aynen geçiyor (`tests/test_v280_feedback_loop.py`) | ölçülmedi | yardım etti (test) |
| `skills/ref-system-map`, `hooks/menu.json`, KURALLAR K15 | uzman bilgisi | geri-bildirim-paketi | — (2.10.0 öncesi) | Müşteriye "paket/önizleme/dışa aktarma" yerine "hata defteri" | ölçülmedi | ölçülecek |
| `evals/defter_oku.py`, `evals/kor_kiyas.py` | işleyiş (admin) | — | — (2.10.0 öncesi) | Müşteri akışına girmez | ölçülmedi | — |

**Sahada:** ilk defterler gelince doldurulacak.

**Ders:** yok (ilk sürüm; henüz karşılaştırılacak bir önceki defter yok).

---

## 2.9.0 (2026-11-04): sade ve net dil

**Değişiklikler**

| Bileşen | Tür | Etkilenen vaka / hücre | Gerekçe | Gözlenen fark | Harcama farkı | Karar |
|---|---|---|---|---|---|---|
| KURALLAR K16 + `skills/ref-sade-dil` | uzman bilgisi | s02-strateji-yeni-baslayan (P1.U1), s13-son-kontrol-sade (P3.U1), hata-sonrasi-defter-sorusu | — (2.10.0 öncesi) | Her oturumda bağlama giren tek kural; sözlük ve örnekler skill'de | ölçülmedi | ölçülecek (vakalar yeni) |
| 25 skill'in kapı mesajı | uzman bilgisi | bütün hücreler | — (2.10.0 öncesi) | Kalıp mesajlarda iç ad ve terim kalmadı (`tests/test_v290_plain_language.py::test_gate_messages_are_plain`) | ölçülmedi | yardım etti (test) |
| `admem/stages.py`, `hooks/menu.py`, `hooks/menu.json`, `hooks/error_notify.py`, `admem/feedback.py`, `scripts/audio/tts_local.py` | işleyiş | bütün hücreler | — (2.10.0 öncesi) | Koddan gelen metinler taramadan bulgusuz geçiyor; menü numaraları aynı (`tests/test_hooks.py`) | ölçülmedi | yardım etti (test) |
| `templates/reports/*.md`, `scripts/analytics/report.py`, `scripts/analytics/coach.py` | uzman bilgisi | s02-*, s14-*, koçluk | — (2.10.0 öncesi) | Taslak denetimi başlık ve satır adlarını aynen buluyor (`tests/test_v250_drafts.py`); rapor taramadan geçiyor | ölçülmedi | yardım etti (test) |
| `musteri-paketi/*`, `scripts/setup/windows/kurulum.ps1` | işleyiş | U1, U5 | — (2.10.0 öncesi) | Kurulum ve güncelleme mesajları sade; Windows güncelleyici testi yeni ifadeyi arıyor | ölçülmedi | ölçülecek (Windows'ta) |

**Sahada:** ilk defterler gelince doldurulacak. 2.8.0 defterleriyle karşılaştırırken bakılacak gösterge: "kullanıcı taslakta değişiklik
istedi" imzasının sıklığı (anlaşılmayan mesaj çoğu zaman düzeltme isteği olarak döner).

**Ders:** yok (değişiklikler aynı sürümde birlikte yapıldı; tek tek etkisini ayıran vaka henüz koşulmadı).

---

## 2.10.0 (2026-11-04): ezber önlemleri

**Değişiklikler**

| Bileşen | Tür | Etkilenen vaka / hücre | Gerekçe | Gözlenen fark | Harcama farkı | Karar |
|---|---|---|---|---|---|---|
| `evals/ezber_denetimi.py`, `.github/workflows/ci.yml` | işleyiş (admin) | — | Revize: RRSI "eleştirmen" fikri; sahadan gelen düzeltmelerin vakayı ezberlemesini önlemek | 2.9.0 farkında 7 eşleşme bulundu, hepsi plugin cümlesini bilerek alıntılayan iki vakadan; bu vakalar işaretlendi (`tests/test_v2100_overfit.py`) | yok (müşteriye girmez) | yardım etti (test) |
| `evals/kapali/` (3 vaka), `senaryo-matrisi.json` → `kapali_cases` | işleyiş (admin) | P7.U8, P3.U3, P5.U5 | Revize: RRSI ayrık test grubu; K04, K12 ve U8 ilk kez model cevabıyla sınanıyor | Biçim doğrulandı (ücretsiz koşu); puanlar ilk yayın testinde | yayın testi yaklaşık +%23 | ölçülecek (vakalar yeni) |
| `evals/kor_kiyas.py puan` | işleyiş (admin) | bütün vakalar | Revize: RRSI oynama payı, HarnessPro maliyet | Sahte JSON'larla sınandı; gerçek JSON'daki koşu puanı alan adı ilk yayın testinde doğrulanacak | yok | ölçülecek |
| `evals/etki_ozeti.py`, etki defteri sütunları | işleyiş (admin) | — | Revize: RRSI budama | Bugünkü defterde silmeye aday yok | yok | — |
| `CLAUDE.md` (depo kökü) | işleyiş (admin) | — | Kapalı vaka kuralının sonraki oturumlara geçmesi | Müşteri paketine girmez | yok | — |

**Sahada:** müşteri akışı değişmedi; gösterge beklenmez.

**Ders:** yok (yalnızca admin tarafı ölçüm araçları).

---

## 2.10.1 (2026-11-05): karşılaştırma eksik sonucu reddeder

**Değişiklikler**

| Bileşen | Tür | Etkilenen vaka / hücre | Gerekçe | Gözlenen fark | Harcama farkı | Karar |
|---|---|---|---|---|---|---|
| `evals/kor_kiyas.py` (`puan`, `hazirla`, yeni `kayit`) | işleyiş (admin) | bütün vakalar | Dış inceleme: yarım, hatalı ya da eksik eval sonucu başarılı sayılıyordu; 2.9.0 sonucu kapalı vakaları içermiyordu | Sahte JSON'larla her olumsuz durum sınandı (`tests/test_v2101_eval_gate.py`); gerçek koşu yapılmadı | yok | ölçülecek (alan yolları gerçek koşuyla) |
| `evals/ezber_denetimi.py`, `senaryo-matrisi.json` → `alinti` | işleyiş (admin) | hata-sonrasi-defter-sorusu, s02-strateji-yeni-baslayan | Toptan izin, aynı vakadan gelen gerçek bir kopyayı da gizleyebiliyordu | Bugünkü 8 eşleşmenin hepsi listelenen cümlelerin içinde | yok | — |

**Sahada:** müşteri akışı değişmedi; gösterge beklenmez.

**Ders:** karşılaştırma aracı da bir yayın kapısıdır; "hiç sonuç yoksa dur" yetmez, "sonucun bir kısmı eksikse de dur" gerekir.

---

## 2.10.2 (2026-11-05): ölçülmeyen değer sonuç sayılmaz

**Değişiklikler**

| Bileşen | Tür | Etkilenen vaka / hücre | Gerekçe | Gözlenen fark | Harcama farkı | Karar |
|---|---|---|---|---|---|---|
| `scripts/analytics/coach.py` (huni adımları, aşama oranları), `scripts/analytics/report.py`, `admem/s_meta.py` (önsel) | işleyiş | bütün ürünler; olayın bazı reklamlarda gelmediği her kullanıcı | Dış sürüm denetimi: pay ve payda farklı satırlardan toplanıyordu | Yarım ölçülen olayda oran doğru, kapsama yazılıyor (`tests/test_v2102_kanit_kapilari.py`) | yok | yardım etti (test) |
| `admem/s_draft.py`, `admem/s_stage.py` (taslak kapısı) | işleyiş | metin aşaması olan bütün hücreler | Dış sürüm denetimi: eski denetim kayıt değişince ve başka adla geçerli kalıyordu | Bütçe değişince ve ad değişince aşama durur; normal akış aynı | yok | yardım etti (test) |
| `scripts/audio/tts_worker.py` (okunuş sözlüğü) | işleyiş | seslendirme kullanan bütün hücreler | Dış sürüm denetimi: Türkçe büyük İ seslendirmeyi durduruyordu | İ, I, ı, i ve İngilizce büyük yazım sınandı | yok | yardım etti (test) |
| `scripts/qc/sfx_review.py` | işleyiş | ses efekti kullanan hücreler | Dış sürüm denetimi: ölçülmeyen eksen "geçti"ye karışıyordu | Efekt izi yokken sonuç "ölçülemedi" | yok | yardım etti (test) |
| `admem/s_coach.py` (`playbook_propose`) | işleyiş | 2. tur ve sonrası (U3) | Dış sürüm denetimi: çağıranın beyanına güveniliyordu | Kontrolsüz, sapmış ya da iyileştirmesi açık turda aday yok | yok | yardım etti (test) |
| `evals/defter_oku.py`, `evals/etki_ozeti.py` | işleyiş (admin) | — | Dış sürüm denetimi: farklı gözlem süreleri kıyaslanıyordu; aynı hücre kapsama sayılıyordu; "ölçülmemiş yok" yanıltıcıydı | Sentetik defterlerle sınandı | yok | yardım etti (test) |

**Sahada:** henüz defter yok. Beklenen: huni adımlarında "veri yetersiz" satırı biraz artabilir (önceden yanlış bir oran gösteriliyordu).

**Ders:** *Ne zaman:* iki toplamın oranı hesaplanırken satırların bir kısmında değerlerden biri yoksa. *Ne yap:* pay ve paydayı aynı
satırlardan topla, kapsamayı yaz, kapsama yetmezse hüküm verme. *Dayanak:* bu sürümün huni satırı. *Güven:* yüksek.

## 2.10.3 (2026-11-06): sahiplik, onay ve silme

**Değişiklikler**

| Bileşen | Tür | Etkilenen vaka / hücre | Gerekçe | Gözlenen fark | Harcama farkı | Karar |
|---|---|---|---|---|---|---|
| `admem/s_coach.py` (`action_items_set`, `action_items_verify`) | işleyiş | koçluk turu olan bütün hücreler (U2, U3 en çok) | Dış kod denetimi: onaylı adım değişince onay taşınıyordu; tek alan okununca "uygulandı" deniyordu | Değişen adım yeniden öneri olur; okunmayan alan yazılır (`tests/test_v2103_sahiplik_onay.py`) | yok | yardım etti (test) |
| `admem/s_stage.py` (`gate_approve`, `checkpoint_close`, `cycle_set`) | işleyiş | kapılı aşaması olan bütün hücreler; çok profilli U4 | Dış kod denetimi: değişmiş belge onaylanabiliyordu; başka profilin notu kapanabiliyordu; tur durumu geri alınıp önsel değişiyordu | Üç durum da duruyor; normal akış aynı | yok | yardım etti (test) |
| `admem/s_creative.py` (sahne önbelleği), migration 010 | işleyiş | U4 (aynı kurulumda birden çok marka) | Dış kod denetimi: iki profil aynı anahtarı yazınca dosya karışıyordu | Her profil kendi dosyasını alıyor; eski kayıtlar taşınıyor | yok | yardım etti (test) |
| `admem/s_memory.py` (`memory_forget`) | işleyiş | hafıza kullanan bütün hücreler | Dış kod denetimi: `%` joker sayılıp ilgisiz kayıtlar siliniyordu | Düz metin eşleşmesi; kısa içerik yalnız kendi başına geçerse | yok | yardım etti (test) |
| `hooks/hooks.json`, `scripts/setup/gen_config.py` (`onFailure`) | işleyiş | Meta ve ElevenLabs kullanan bütün hücreler | Dış kod denetimi + Claude Code hook belgesi: koruma çalışamazsa çağrı izin akışına düşüyordu | Üretici ve dosya aynı; gerçek host'ta eksik yorumlayıcı denemesi yapılmadı | yok | ölçülecek (host denemesi) |
| `hooks/cost_guard.py`, `admem/s_legal.py` (yükleme izni), `skills/materials`, `skills/brand-onboarding` | işleyiş | kişi ya da ses içeren malzemeyle çalışan hücreler | Dış kod denetimi: izin profil ve sağlayıcıya bağlıydı, dosyaya değil | Başka dosya ve geri çekilmiş izin reddediliyor; ElevenLabs aracının gerçek alan adlarıyla denenmedi | yok | ölçülecek (canlı şema) |
| `scripts/setup/db_restore.py` | işleyiş | yedekten dönen her kurulum | Dış kod denetimi: kopya yarıda kalırsa veritabanı kayboluyordu | Bozuk kopyada mevcut veritabanı yerinde | yok | yardım etti (test) |

**Sahada:** henüz defter yok. Beklenen: onaylanmış bir bütçe önerisi değiştiğinde kullanıcıya yeniden soru sorulur.

**Ders:** *Ne zaman:* bir onay ya da izin, sonradan değişebilen bir kayda (tutar, dosya, tur) bağlıysa. *Ne yap:* onayı verildiği anki
içeriğe (özet, alanlar, dosya) bağla; içerik değişince onayı düşür ve yeniden sor. *Dayanak:* bu sürümün onay, kapı ve yükleme
satırları. *Güven:* orta (birim testi; saha verisi yok).

## 2.10.4 (2026-11-06): karar verisi

**Değişiklikler**

| Bileşen | Tür | Etkilenen vaka / hücre | Gerekçe | Gözlenen fark | Harcama farkı | Karar |
|---|---|---|---|---|---|---|
| `scripts/analytics/coach.py` (`analyze`, ölçüm tanımı ve ayarlar), `admem/s_coach.py` (anlık görüntü ayarları) | işleyiş | koçluk raporu alan bütün hücreler; U3 | Dış kod denetimi: karışık ölçüm tanımından üstünlük olasılığı üretiliyordu; kayda yazılan aralık uygulanmıyordu | Karışık tanımda hüküm ve tahmin yok; uygulanmayan ayar reddediliyor (`tests/test_v2104_karar_verisi.py`) | yok | yardım etti (test) |
| `scripts/analytics/coach.py` (`channel_summary`), `scripts/analytics/report.py` | işleyiş | U6 (USD hesap) ve birden çok para birimiyle satan hücreler | Dış kod denetimi: TRY ve USD aynı gelire toplanıyordu | Farklı para birimi ayrı yazılıyor, tek para biriminde sonuç aynı | yok | yardım etti (test) |
| `admem/s_conn.py` (`sales_import_csv`) | işleyiş | mağaza dışa aktarımı kullanan hücreler | Dış kod denetimi: yalnız adet düzeltmesi aktarılmıyordu | Adet ve para birimi düzeltmesi güncelleme sayılıyor | yok | yardım etti (test) |
| `admem/s_base.py` (`economics`), `scripts/analytics/budget.py` (`plan`) | işleyiş | P6, P7 (katkısı bilinmeyen/aralık), U8 (toplam sınır) | Dış kod denetimi: "NaN" katkı kesin ekonomi, eksi bütçe sığan plan üretiyordu | Geçersiz değer bilinmiyor sayılıyor; eksi/sonsuz bütçe reddediliyor | yok | yardım etti (test) |

**Sahada:** henüz defter yok.

**Ders:** *Ne zaman:* bir hesap farklı kaynaklardan gelen sayıları topluyorsa (birim, para birimi, ölçüm tanımı). *Ne yap:* toplamadan
önce birimin aynı olduğunu denetle; değilse ayrı göster ve hüküm verme. *Dayanak:* bu sürümün ölçüm tanımı ve para birimi satırları.
*Güven:* orta (birim testi).
