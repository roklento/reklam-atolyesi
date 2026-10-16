# Reklam Atölyesi (reklam-atolyesi) · 1.4.0

Meta video reklamlarını **rakip analiziyle stratejiden yayın paketine** kadar üreten, yayındaki reklamları matematikle okuyup koçluk
yapan ve her turda öğrenen bir Claude Code plugin'i. Marka, reklam hesabı ve ürünler **profil verisidir**; plugin kodu markadan bağımsızdır.

## Kurulum
**Dağıtılan kurulum (Windows):** Müşteri, kurulum paketindeki `kur.cmd` dosyasını çalıştırır. Betik sırayla şunları yapar:
1. Özel GitHub marketplace'ini ekler.
2. Plugin'i `--config data_dir=<klasör>` ile kullanıcı kapsamında kurar.
3. Plugin'in `scripts/setup/windows/kurulum.ps1` adımlarını çalıştırır: araçlar, `.venv`, `.node`, sonra `scripts/setup/kurulum_dogrula.py`.

Doğrulama sırası:
1. Duman testi.
2. Türkçe render ve galeri; referans karelerle karşılaştırılır.
3. `doctor --write-ok`.

Aynı betik güncellemeyi de yapar: yedek alır ve `doctor --update` çalıştırır.

**Yerel marketplace (geliştirme):** Plugin'in üst klasöründeki `.claude-plugin/marketplace.json` (`reklam-atolyesi-local`) kullanılır.
Plugin bu klasörden yerinde okunur. Kurulumda `data_dir` sorulur:

```
claude plugin marketplace add <plugin-üst-klasörü>
claude plugin install reklam-atolyesi@reklam-atolyesi-local --scope user
```

## Başlatma
Yeni bir Claude Code oturumu açın ve yalnızca şunu yazın:

```
reklam-atolyesi
```

İlk açılışta: canlı kurulum kontrolü → `/mcp` ile **ElevenLabs** ve **Meta Ads (salt okuma)** OAuth bağlantıları → marka tanışması.
Sonrasında arayüz numaralı menüdür (navigator); komut yazmanız beklenmez. "menü" menüyü yeniden gösterir, "çık" plugin modundan çıkar.

## Döngü
Brief → rakip analizi → strateji (kapı) → konsept görüşmesi (kapı) → çekim rehberi (kapı) → deneme → çekim → ingest → analiz →
stil yönleri (kapı) → malzeme (kapı: ses kararları + maliyet) → kurgu → ses (kapı: taslak) → varyasyon/export → QC (kapı) →
yayın paketi (kapı) → **insan yayına alır** → takip → koçluk (kapı) → öğrenme (kapı) → yeni tur.

Kapılarda sistem durur ve **açık onayınızı** bekler. Yaratıcı kararlar birlikte alınır; Claude bitmiş işi "onaylatmaz".

## Neler yapmaz
- Meta'ya yazmaz: reklam oluşturmaz, yayına almaz, bütçe değiştirmez (izin listesi hook'u + salt okuma OAuth).
- Onaysız ücretli üretim yapmaz: her ElevenLabs üretimi tahmin → kayıt → açık onay → tek kullanımlık atomik rezervasyon yolundan geçer.
- Rakip hesaplarına girmez, sosyal medya kazımaz; rakip varlıkları üretime girmez.
- AI ile insan yüzü/eli üretmez, ses klonlamaz, sahte yorum kullanmaz.

## Bileşenler
| Klasör | İçerik |
|---|---|
| `skills/` | navigator, 21 aşama skill'i (S00a–S17), `memory`, `ref-system-map`, 7 referans skill'i |
| `agents/` | meta-historian, competitor-analyst, creative-strategist, cinematographer, footage-analyst, art-director, editor, sound-designer, qc-reviewer, media-analyst, coach |
| `commands/` | `/reklam-atolyesi:basla`, `kurulum-kontrol`, `profiller`, `profil-ekle`, `profil-sec`, `tanis-marka`, `tanis-urun`, `meta-gecmis`, `yeni-kampanya`, `durum`, `sonraki`, `onayla`, `geri`, `rapor`, `rakip-analizi`, `takip`, `karar-hazirla`, `gece-uretim`, `bakim` |
| `workflows/` | `analyze-footage`, `analyze-competitors`, `render-variants`, `qc-review` (kapısız paralel işler; yedek yol: alt ajanlar) |
| `hooks/` | plugin modu ve navigator bağlamı, Meta izin listesi + Kütüphane sorgu bütçesi, ElevenLabs maliyet koruması, render mini-QC, Stop uyarısı |
| `servers/ad_memory/` | `ad-memory` MCP sunucusu (Python, SQLite WAL, FTS5 trigram, numaralı migration'lar) |
| `scripts/` | ingest, analiz, ses, kurgu planı, render, export, QC, Meta CSV, rekabet, analitik, hafıza, kurulum, duman testi |
| `templates/` | Remotion projesi ve 37 bileşenli kütüphane, nötr stil kitabı, LUT, rapor şablonları |
| `vendor-skills/` | pinlenmiş, lisanslı hazır skill'ler (skill olarak kaydedilmez; `OVERRIDES.md` önce okunur) |
| `system_manifest.json` | sistemin kendi haritası, test sonuçları, sapmalar, canlı kontrol tanımları |

## Veri
Bütün durum `data_dir` altındadır (userConfig; plugin klasörüne durum yazılmaz): `db/ad-memory.sqlite`, `.venv`, `.node`,
`profiles/<profil>/…`, `memory/system/`, `logs/`, `backups/`, `.sessions/` (geçici oturum durumu). Yedekler haftalık ve her
migration öncesi alınır; son 8 yedek tutulur.

## Geliştirici notları
- `<py>` = `<data_dir>/.venv/Scripts/python.exe` (Windows) ya da `<data_dir>/.venv/bin/python` (macOS/Linux).
- Testler (plugin kökünden): `<py> -m pytest tests -q -p no:cacheprovider` (FFmpeg PATH'te olmalı).
- Statik kurulum kontrolü: `<py> scripts/setup/doctor.py --data-dir <data_dir>`.
- `hooks/hooks.json` kurulum işletim sistemine göre üretilir; plugin başka bir işletim sistemine taşınırsa `<py> scripts/setup/gen_config.py <plugin-kökü>`
  yeniden çalıştırılmalıdır (doctor uyumsuz yorumlayıcı yolunu kırmızı gösterir).
- Hook ve `.mcp.json` üretimi: `scripts/setup/gen_config.py <plugin-kökü>` (exec biçimi; Windows/posix yorumlayıcı yolu).
- `ad-memory` sunucusu `uv run` ile değil, `data_dir` sanal ortamının Python'uyla `servers/ad_memory/server.py` olarak başlar.
  - Sanal ortam: `uv sync --project servers/ad_memory --frozen --no-install-project` (yalnızca bağımlılıklar).
  - Kod her zaman yüklü plugin sürümünün klasöründen okunur.
  - Gerekçe: Dağıtılan kurulumda her sürüm ayrı bir önbellek klasörüne kopyalanır.
- Vendor güncelleme: `scripts/setup/update-vendor.sh <repo> <commit>` (fark incelemesi ve insan onayı).
- Lisanslar: `vendor-skills/THIRD_PARTY_NOTICES.md`; Remotion ve ElevenLabs kullanım koşulları `skills/ref-legal-tr-meta`.
