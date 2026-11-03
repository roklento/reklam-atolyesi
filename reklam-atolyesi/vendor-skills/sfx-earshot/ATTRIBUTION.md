# Kaynak kaydı — Earshot ses bankası (kodla üretilmiş)

Kaynak: https://github.com/Leonxlnx/earshot, commit `591fa3e028032e6dce56620a20e932e35667e8d8` (sürüm 0.4.0, banka `forge_v2r6+forge04r1+fit1+pluck1`). Earshot kodu MIT (`LICENSE`).
Sesler kayıt içermez: her biri Earshot'un DSP tarifinden kendi tohumunda üretildi (`scripts/setup/sfx_earshot_build.py`),
48 kHz'den OGG Vorbis'e (q6) çevrildi. `fit/` altındaki 15 ses, Earshot'un CC0 1.0 Freesound kayıtlarından çıkardığı
tariflerden üretildi; kaynak kayıtlar ve kaydedenler `CREDITS_FIT.md`'de (CC0: atıf zorunlu değil).
Earshot'un 0.4 tarifleri özel lisanslı örnek seslerin ölçümlerine göre ayarlanmıştır; o örnekler pakette ve burada yoktur.

`scripts/audio/sfx_library.py` yalnızca bu tabloda satırı olan ve SHA-256'sı tutan dosyaları listeler. Earshot'un kendi
denetiminde uyarı alan sesler (`Denetim` sütunu "uyarı") varsayılan aramada **listelenmez**; `--include-flagged` ile görünür.
Seslerin hiçbiri yayın öncesi insan kulağıyla dinlenmeden kullanılmaz (sound skill'indeki telefon testi kuralı).

## Dosyalar

| Dosya | Lisans | Earshot kimliği (tohum) | Denetim | SHA-256 |
|---|---|---|---|---|
| `click/double.ogg` | MIT (Earshot, kodla üretildi) | `click/double` (401884446) | temiz | `552610dbfc8489f4f91249a621da0602df695275e840b2adb56f5087a3f08f87` |
| `click/snap.ogg` | MIT (Earshot, kodla üretildi) | `click/snap` (1664770360) | temiz | `23d22f30b29aee79ae5425bb4d839d5e998bb2c9e6e9ca2d101e39b1671b065d` |
| `click/soft.ogg` | MIT (Earshot, kodla üretildi) | `click/soft` (76560324) | temiz | `3a38deeacee9c57392d1e8d24bf4e3cc953a0220530c03e0490e500ec83a89e6` |
| `click/thock.ogg` | MIT (Earshot, kodla üretildi) | `click/thock` (992592500) | temiz | `ec5fa234f969b4129e8151099728339663d2491a2c1722d0db4cc54e5221fe38` |
| `click/tink.ogg` | MIT (Earshot, kodla üretildi) | `click/tink` (2032936675) | temiz | `39e9a56e0e74bd1913d947957d8ea0beb8e128b4ed7451853239234925725af8` |
| `cut_hit/air.ogg` | MIT (Earshot, kodla üretildi) | `cut_hit/air` (4105) | temiz | `3ac3adbb79ecfe5ed71de1055ef8c1cd932798520a01a1f1367c083bef40b7eb` |
| `cut_hit/kick.ogg` | MIT (Earshot, kodla üretildi) | `cut_hit/kick` (4102) | temiz | `9764bdd57d931aa1dc7aa51b260054ab15c1b39e50b3355187b03fe6af167972` |
| `cut_hit/punch.ogg` | MIT (Earshot, kodla üretildi) | `cut_hit/punch` (4103) | temiz | `2d182ae2eea367b038b5c951ca7e35bd90ae267ee92630c22fbc137d1a24b4ca` |
| `cut_hit/rumble.ogg` | MIT (Earshot, kodla üretildi) | `cut_hit/rumble` (4104) | temiz | `de1c6981539cabc52bcc0be1282ae7963aacd87fbd66832819f0bbd870776811` |
| `cut_hit/sub.ogg` | MIT (Earshot, kodla üretildi) | `cut_hit/sub` (4101) | temiz | `aa44595b4c01ea4c968edde6d9c3e668cf80148dfad2027c7e22d5fd3692ac70` |
| `downlifter/air_fall.ogg` | MIT (Earshot, kodla üretildi) | `downlifter/air_fall` (1367864807) | temiz | `be46fb7c7c2eec9afd012cec7ca3ab41da489c39733841659c85f88e123cbc85` |
| `downlifter/flange_air.ogg` | MIT (Earshot, kodla üretildi) | `downlifter/flange_air` (161576974) | temiz | `1e595342628fe6c31f1d9a768288f30198190962eaebd8a41d48cfc3bd1824b4` |
| `downlifter/shepard_fall.ogg` | MIT (Earshot, kodla üretildi) | `downlifter/shepard_fall` (87989972) | temiz | `7d0b718a9e60403844e79cafedd1eea74ed1f179506a5827ec4ec90da7af8dda` |
| `downlifter/sub_sink.ogg` | MIT (Earshot, kodla üretildi) | `downlifter/sub_sink` (579362556) | temiz | `b3956adf2f19de97a13b4e18383b323b92afbb4c91c4f4ec5f7396b063a358f4` |
| `downlifter/synth_fall.ogg` | MIT (Earshot, kodla üretildi) | `downlifter/synth_fall` (1097657232) | temiz | `8fea58233c24bfd6d189a3cd87d52f5ee2c7533404c15d073300187c2e4b9085` |
| `downlifter/tape.ogg` | MIT (Earshot, kodla üretildi) | `downlifter/tape` (661058652) | temiz | `9149dc48c4b0be5cd88802672d96b281ad18c61ffd1532d0afe588f8a1489489` |
| `drip/bloop.ogg` | MIT (Earshot, kodla üretildi) | `drip/bloop` (1) | temiz | `a965446593906a9980155a759935aeab323890efb51e21cc1f7e816157b5996d` |
| `drip/bubble.ogg` | MIT (Earshot, kodla üretildi) | `drip/bubble` (1) | temiz | `318196a1a59dfdfab7c03049330a64ae15e3e14cfe8eb2355d56699d69040b06` |
| `drip/drop.ogg` | MIT (Earshot, kodla üretildi) | `drip/drop` (1) | temiz | `c7be19ca3df717ac4f7a70694fdb3166f0bcb0aa35a3edab70a0e5fe3978a166` |
| `drip/plink.ogg` | MIT (Earshot, kodla üretildi) | `drip/plink` (1) | temiz | `c9866666886dd7c0cb91de66a4a2813e7c7b09089c84614c6da459b98d33c39a` |
| `drip/tiny.ogg` | MIT (Earshot, kodla üretildi) | `drip/tiny` (1) | temiz | `635e5ce83ddfc51c6aa3d016ef6fe59e8fda70b26c4db887fd2de9f6ff9dda4f` |
| `fit/bell/small_bell.ogg` | MIT (Earshot) + kaynak kayıt CC0 1.0 | `fit/bell/small_bell` (0) | temiz | `57c99d25fad939c37c9706d3357afbdb17771f9196f6935b253e26e6d573be5e` |
| `fit/click/floss_lid.ogg` | MIT (Earshot) + kaynak kayıt CC0 1.0 | `fit/click/floss_lid` (0) | temiz | `74cb71b66c95fd6ef08e1c9e86f40d1e80d311626598fb0f22b338b3ea340899` |
| `fit/hit/bamboo_tok.ogg` | MIT (Earshot) + kaynak kayıt CC0 1.0 | `fit/hit/bamboo_tok` (0) | temiz | `0b9079def1eaa69d11441e3e8d15a52638c3f545812d37b2a093cc4378ebab36` |
| `fit/key-space/thock_space.ogg` | MIT (Earshot) + kaynak kayıt CC0 1.0 | `fit/key.space/thock_space` (0) | temiz | `364bee163a34406138470eaec87d8f78938b2d55deb277961cb6bfeed20ab812` |
| `fit/key/lubed.ogg` | MIT (Earshot) + kaynak kayıt CC0 1.0 | `fit/key/lubed` (0) | temiz | `5ea5cfd97620fb3ac9422d3dbb714e9cebba0d533b2b2551f283aca6a1f96e78` |
| `fit/key/medium.ogg` | MIT (Earshot) + kaynak kayıt CC0 1.0 | `fit/key/medium` (0) | temiz | `bb563965329ba1a108dfc55b1bb08a7cf61c336efa5d06bb7934e2e6a128e1c8` |
| `fit/key/thock.ogg` | MIT (Earshot) + kaynak kayıt CC0 1.0 | `fit/key/thock` (0) | temiz | `617f4083af5eaca73a628e1ab8b6d5325159dc8cdcd1955f0816989fe057e100` |
| `fit/land-light/finger_phone.ogg` | MIT (Earshot) + kaynak kayıt CC0 1.0 | `fit/land.light/finger_phone` (0) | temiz | `a05572b7fa193146294fce62880910fc3c789d355f51843935c23c54ce32c262` |
| `fit/land-light/finger_wood.ogg` | MIT (Earshot) + kaynak kayıt CC0 1.0 | `fit/land.light/finger_wood` (0) | temiz | `49d7321a309c408c705dc4380694d0940714d7892e2d76dd3fd3352840dcafa8` |
| `fit/land-light/fingertip_book.ogg` | MIT (Earshot) + kaynak kayıt CC0 1.0 | `fit/land.light/fingertip_book` (0) | temiz | `89825fa4cb1337c831771952b15c78135274b80b6214d5ab8a12a02d669452c2` |
| `fit/pop/lip_pop.ogg` | MIT (Earshot) + kaynak kayıt CC0 1.0 | `fit/pop/lip_pop` (0) | temiz | `0a6aa00830481856145cfbe2c017ff6540e96f3b2dbcf72649700b89f9523863` |
| `fit/pop/mouth_plop.ogg` | MIT (Earshot) + kaynak kayıt CC0 1.0 | `fit/pop/mouth_plop` (0) | temiz | `f1e33a29b60889bb119dd15e308ddf502c9c7b55363f7914be02dd602f37a26b` |
| `fit/snap/switch_flip.ogg` | MIT (Earshot) + kaynak kayıt CC0 1.0 | `fit/snap/switch_flip` (0) | temiz | `722d905e07257daf16e232625ae04ae0912a07bcb3cd06f58b775d513f51cfbc` |
| `fit/tick/domino.ogg` | MIT (Earshot) + kaynak kayıt CC0 1.0 | `fit/tick/domino` (0) | temiz | `8951ee74db26de195d06f7c9881405d45fd4aca5b149babda80efbda4088ce6d` |
| `fit/whoosh-short/bamboo_swish.ogg` | MIT (Earshot) + kaynak kayıt CC0 1.0 | `fit/whoosh.short/bamboo_swish` (0) | temiz | `940fff0f49f9eb063292e67638eb343c340c56b641539be326011a7c3ad619b5` |
| `glitch/burst.ogg` | MIT (Earshot, kodla üretildi) | `glitch/burst` (4601) | temiz | `3d8da9b627950041d4ef24137d34c39f36666f5b240b205a15dd7a8df3aa0733` |
| `glitch/chirp.ogg` | MIT (Earshot, kodla üretildi) | `glitch/chirp` (4603) | temiz | `92b47bdcab4a2e215356bbc47bd23f9474b80f45e2742ec4e0d31439f4ec8e9a` |
| `glitch/crush.ogg` | MIT (Earshot, kodla üretildi) | `glitch/crush` (3) | temiz | `7d54880214a637ea23c1fc299eb20cb8921b079802167171761df8adc74508dd` |
| `glitch/data.ogg` | MIT (Earshot, kodla üretildi) | `glitch/data` (3) | temiz | `9885f3a991f575a0055ab0d39ccb5c7f78086b3ded32c28705ef503cf1713dbf` |
| `glitch/dropout.ogg` | MIT (Earshot, kodla üretildi) | `glitch/dropout` (3) | uyarı: metallic comb ring in the tail every 10.0 ms (z 24) | `4d5ef4234132fa9e0cd60c73b42a6547e83236fb38c4445bbe679543effcc2f6` |
| `glitch/hit.ogg` | MIT (Earshot, kodla üretildi) | `glitch/hit` (3) | temiz | `78e9e31c327917ddd4a1bbb785f425542b42963639f501ae77e3c4d0f3067fd6` |
| `glitch/mid.ogg` | MIT (Earshot, kodla üretildi) | `glitch/mid` (4602) | temiz | `87fb38f8163b2b3cfe8adf50f9fcc3a37e087766a2f06f6047cc5bc3d47b6e3e` |
| `glitch/scramble.ogg` | MIT (Earshot, kodla üretildi) | `glitch/scramble` (3) | temiz | `c96c0c5207f48608b7b4b8908fc4de75e2acd02d3c85622344fb405c819355fa` |
| `glitch/stutter.ogg` | MIT (Earshot, kodla üretildi) | `glitch/stutter` (3) | temiz | `e11fd6924af8d00897fe4d7cb6424ce6ebd549b034ca98d97700ec86234873fe` |
| `hover_tick/air.ogg` | MIT (Earshot, kodla üretildi) | `hover_tick/air` (460490113) | temiz | `4983eb8018fb319df30cbe3db6b602264812c609e1ea41834ddf518b1aae104c` |
| `hover_tick/detent.ogg` | MIT (Earshot, kodla üretildi) | `hover_tick/detent` (700743171) | uyarı: tail cut at -39 dB re peak: fade it out or render it longer | `36019519b4e8358c6a34dde0dc9c0cd2abaf559f4a33fa9585225182cc667c64` |
| `hover_tick/high.ogg` | MIT (Earshot, kodla üretildi) | `hover_tick/high` (1826701615) | temiz | `30fa952582c80499e0b2b8c24814f0da44d97bf8354b87f099008ea68886663c` |
| `hover_tick/mid.ogg` | MIT (Earshot, kodla üretildi) | `hover_tick/mid` (2026220627) | temiz | `e3df9871d4a298f36869194cf3b92064a21977cb14ca0bfbfc56a9c7e5c2c8c7` |
| `hover_tick/ping.ogg` | MIT (Earshot, kodla üretildi) | `hover_tick/ping` (972919428) | temiz | `917e79eca43dce156d9c407ca9fceba390f6e2be22513c7e96dfdd4862e9c402` |
| `impact/blast.ogg` | MIT (Earshot, kodla üretildi) | `impact/blast` (0) | temiz | `e71e2c5b8c40f5bbde6be1e345c62e2db01dd3a589476ccca89a5b76b647005d` |
| `impact/classic.ogg` | MIT (Earshot, kodla üretildi) | `impact/classic` (0) | temiz | `8119de4e5509eee3e29d21a94bb6f28bb47c24b6920e92af56548f2248ad020d` |
| `impact/deep.ogg` | MIT (Earshot, kodla üretildi) | `impact/deep` (0) | temiz | `79ac567fad7a8b9fdc2a3c59ffbabc8cc87e8191e6fa72ad2d89df4e38e7c286` |
| `impact/metal.ogg` | MIT (Earshot, kodla üretildi) | `impact/metal` (0) | temiz | `531a448efdfa9db3640500e94ffd2d89ad1336ae27590a11a25b32b0d871c386` |
| `impact/punch.ogg` | MIT (Earshot, kodla üretildi) | `impact/punch` (0) | temiz | `7c0501e776ee68d23f26d0e63ab56909835a2f0c9f6365f7bffd0104c7692283` |
| `impact/swell.ogg` | MIT (Earshot, kodla üretildi) | `impact/swell` (0) | temiz | `f39445c9d8dd0f2f0e9fad6a6195543c8782c768d01a7986558242a90cfa14e4` |
| `knock/desk.ogg` | MIT (Earshot, kodla üretildi) | `knock/desk` (1) | temiz | `36fb46b79a0d8afb10ce143a36c69f44e95f6405712db1d0f807449a0bd31ed1` |
| `knock/double.ogg` | MIT (Earshot, kodla üretildi) | `knock/double` (1) | temiz | `edcb2914bf04a0237f09c30905edddf9af4581dac6b8daa470d379b8986677bc` |
| `knock/plastic.ogg` | MIT (Earshot, kodla üretildi) | `knock/plastic` (1) | temiz | `8b60afabecc8084a9d33f3936e67ab50731308cb6abf2176f4691c3fbcf112de` |
| `knock/snap.ogg` | MIT (Earshot, kodla üretildi) | `knock/snap` (1) | temiz | `ef4f8edbbe239ffc08a496fe24dabdc40f86e3e9f352e49b50a294e6b9340aa9` |
| `knock/wood.ogg` | MIT (Earshot, kodla üretildi) | `knock/wood` (1) | temiz | `b64d41b7d47eb8126adf85756b9958e3f89faddb97884c4d08cb295c0d7c8ed8` |
| `logo_sting/reverse_bloom.ogg` | MIT (Earshot, kodla üretildi) | `logo_sting/reverse_bloom` (0) | uyarı: metallic comb ring in the tail every 2.7 ms (z 22) | `a1b96e5ec2050189abc7ea2320e58dbe6b243f6071a0c71e821175d31c48b381` |
| `logo_sting/soft_bloom.ogg` | MIT (Earshot, kodla üretildi) | `logo_sting/soft_bloom` (0) | temiz | `80dc6b619619467f698aae86210345ca023e25042fe986949e2e1e7d7f103461` |
| `logo_sting/spark.ogg` | MIT (Earshot, kodla üretildi) | `logo_sting/spark` (0) | temiz | `5ebfd6dfbbab6a9897876935a123f2a3708362cc7db2f450fa357385cb8efe9a` |
| `logo_sting/whoosh_glass.ogg` | MIT (Earshot, kodla üretildi) | `logo_sting/whoosh_glass` (2029167941) | temiz | `4b9e189cc4da1ba969fade8609a5481b9be096f9057ae846b352824ed9d63780` |
| `logo_sting/zip_ping.ogg` | MIT (Earshot, kodla üretildi) | `logo_sting/zip_ping` (0) | uyarı: pitch climbs 25 semitones over 140 ms (0.02-0.16 s): a rising synth whip reads as cheap | `95b6647e47f2f96938bfbd2771fbe1663ec52a7b03c3a888351c694b13252915` |
| `mallet/celesta.ogg` | MIT (Earshot, kodla üretildi) | `mallet/celesta` (1) | temiz | `61d3c1eaeaf0d1ddff6a0c28184929cf2e03134d71c7dcf4f31d98fad86014c9` |
| `mallet/flourish.ogg` | MIT (Earshot, kodla üretildi) | `mallet/flourish` (1) | temiz | `41d7f1c6ca6f981353cd65fbc2da23fb5d938fad269e1ab0a7ecae632968f4e6` |
| `mallet/glock.ogg` | MIT (Earshot, kodla üretildi) | `mallet/glock` (1) | temiz | `c99589e24ed491438a1563673319dc4d20eb5874f84e42263ab69916a3f37baf` |
| `mallet/marimba.ogg` | MIT (Earshot, kodla üretildi) | `mallet/marimba` (1) | temiz | `1f9cb88c2cebe954515a6d738a0e9a6e4135d427c87391f01156cdf823b4e626` |
| `mallet/pluck.ogg` | MIT (Earshot, kodla üretildi) | `mallet/pluck` (1) | temiz | `5b18596091fec77fef7f06592c853ea7d217ce5e67757723f83f43ec1a91f843` |
| `mallet/up4.ogg` | MIT (Earshot, kodla üretildi) | `mallet/up4` (1) | temiz | `ed19746b509788943e99d72efcba08a90dbb181b2681b040d62a0f544a1e9616` |
| `notify/m0.ogg` | MIT (Earshot, kodla üretildi) | `notify/m0` (1826701615) | temiz | `3eec34ed0428639264f3521117080a97046db8ddfbe450ee107fab6a9d6031b5` |
| `notify/m1.ogg` | MIT (Earshot, kodla üretildi) | `notify/m1` (1367864807) | temiz | `255105497ddf805fa931446f09a3600639dacc07eff2c7928d6e2ad6237b20f8` |
| `notify/m2.ogg` | MIT (Earshot, kodla üretildi) | `notify/m2` (1097657232) | temiz | `ba85a9b5b989b62c4aafa1e425efe97f5de5121b8ef40a34022e243ed93bd3bf` |
| `notify/m3.ogg` | MIT (Earshot, kodla üretildi) | `notify/m3` (579362556) | temiz | `f8fced7b144bfa8d683a9436a0dfeeef82f34f5a0ddc20e2268ba43662cb9865` |
| `notify/m4.ogg` | MIT (Earshot, kodla üretildi) | `notify/m4` (661058652) | temiz | `2710b5c1bedb0c0d7c3ea38a74bdae3eb9a2ec0b6238b461d124b234557557b9` |
| `notify/m5.ogg` | MIT (Earshot, kodla üretildi) | `notify/m5` (87989972) | temiz | `41d2f95f54d30e81d3f96848d1b1ce47dc7491322fccbb99d1ecb01019f0a385` |
| `notify/mid_tine.ogg` | MIT (Earshot, kodla üretildi) | `notify/mid_tine` (1) | temiz | `93823b1404c83d366991c58ab1fa4999d04aa9d960ae027dfb04575314db8f2e` |
| `notify/mid_wood.ogg` | MIT (Earshot, kodla üretildi) | `notify/mid_wood` (1) | temiz | `3b817d4894e5b37e4e2a11b4f196fe461449f117bcc10bbe015738cd42e3992c` |
| `pluck/kalimba.ogg` | MIT (Earshot, kodla üretildi) | `pluck/kalimba` (8001) | temiz | `ff9560750bca0bbd305b0f7e5e314295c982e6f24f701110bb721cf3ac6179a2` |
| `pluck/kalimba_ring.ogg` | MIT (Earshot, kodla üretildi) | `pluck/kalimba_ring` (8006) | temiz | `071ab17fc01c55a5b998dc898d85618a6d5b9374965de0e2549bcb1d18d1117d` |
| `pluck/kalimba_soft.ogg` | MIT (Earshot, kodla üretildi) | `pluck/kalimba_soft` (8009) | temiz | `f576b11e24993698884de1f4692e8d21235da23a0e545ba91493d9b3d813fd7b` |
| `pop/0.ogg` | MIT (Earshot, kodla üretildi) | `pop/0` (1826701615) | temiz | `bbfd57f6d9e78489db9d4cedc0679bbc5781a7801d6e236233dafd11538e8b32` |
| `pop/1.ogg` | MIT (Earshot, kodla üretildi) | `pop/1` (1367864807) | temiz | `02a5587eae4e2e1f896f6f558e77052bc499dee52d18185bede1e09d1682dcf2` |
| `pop/2.ogg` | MIT (Earshot, kodla üretildi) | `pop/2` (1097657232) | uyarı: pitch climbs 6 semitones over 75 ms (0.01-0.09 s): a rising synth whip reads as cheap | `5a7776a8bce6cd22d2c987e4e4869fec784b9ce26c1cd597ebaff4daadf0d795` |
| `pop/3.ogg` | MIT (Earshot, kodla üretildi) | `pop/3` (579362556) | temiz | `3307735ac4fad158399320050558d880e409d61dc556372af80c3639984571ad` |
| `pop/4.ogg` | MIT (Earshot, kodla üretildi) | `pop/4` (661058652) | temiz | `d2db1a70c526710b03542bf0a6ab5994113aad1d0f65ac98a3b7636cbf115212` |
| `pro_click/glass.ogg` | MIT (Earshot, kodla üretildi) | `pro_click/glass` (1825246568) | temiz | `5285d552c73e1022b063073250aa6ff8a44a6eb3b1ca5d365289e1dd3a240f23` |
| `pro_click/mouse.ogg` | MIT (Earshot, kodla üretildi) | `pro_click/mouse` (503102719) | temiz | `3c9f2b2146788203d5b39b04a83387598bde4b39a6ed5fcfb2294387cb110f51` |
| `pro_click/snap.ogg` | MIT (Earshot, kodla üretildi) | `pro_click/snap` (726570697) | temiz | `dc1aa0def54dd1e7116de81c1f6a21d2bfed6c933e5a31e87021ff228e5a5a5d` |
| `pro_click/soft.ogg` | MIT (Earshot, kodla üretildi) | `pro_click/soft` (267885885) | temiz | `9ffc02fc6525dae80d229129a1111303d2064be6d5552e9ed4eff2df9d626db4` |
| `pro_click/tink.ogg` | MIT (Earshot, kodla üretildi) | `pro_click/tink` (1162705466) | temiz | `1e1711ec2e652b56ac3d9f95ecc6d768b7708d0fe7c4addb68e7b2731e7cf4af` |
| `pro_glitch/crunchy.ogg` | MIT (Earshot, kodla üretildi) | `pro_glitch/crunchy` (1367864807) | temiz | `f7c09de0a3356f79baea293d0c3d84e24bab48d04bb3a1fda34a918395835cf3` |
| `pro_glitch/data.ogg` | MIT (Earshot, kodla üretildi) | `pro_glitch/data` (579362556) | temiz | `bf4f6b853ab1cd51d4c621bceb1f79177469ddc2735e87b52dddb306140379b9` |
| `pro_glitch/fastroll.ogg` | MIT (Earshot, kodla üretildi) | `pro_glitch/fastroll` (1097657232) | temiz | `c95fcacf606180032a01b1397d7802bd1ddab39ab0c010587b3b047330e2db93` |
| `pro_glitch/framelock.ogg` | MIT (Earshot, kodla üretildi) | `pro_glitch/framelock` (87989972) | temiz | `4b39d53762ae26f60f11483e1cb5dc28bb081f90948f3af9041c38c6d60e8f2d` |
| `pro_glitch/sparse.ogg` | MIT (Earshot, kodla üretildi) | `pro_glitch/sparse` (661058652) | temiz | `00fe7aac32d31882991d064bdadb23ccab9f69c13c8bd7f792de69af37b1d919` |
| `pro_glitch/standard.ogg` | MIT (Earshot, kodla üretildi) | `pro_glitch/standard` (1826701615) | temiz | `8c7347f892f5ac3f7bdca35cfbc753e4d2aaa99ebf5b3a84ed70f882d2fa5948` |
| `pro_hover_tick/air.ogg` | MIT (Earshot, kodla üretildi) | `pro_hover_tick/air` (368965614) | uyarı: 1 click at 0.022 s | `401f1157713fbdbb592f4a36049fdbc263acc06ebf98f8dfcac0593faccc9637` |
| `pro_hover_tick/detent.ogg` | MIT (Earshot, kodla üretildi) | `pro_hover_tick/detent` (1291544842) | temiz | `853d0ecca5a6ed39ba899fa38e688da8ce8822d0a47a6656b8cfeb37e96a0f1d` |
| `pro_hover_tick/glass.ogg` | MIT (Earshot, kodla üretildi) | `pro_hover_tick/glass` (2019511571) | uyarı: 1 click at 0.021 s | `4454f9942c9dfa7cd9509b8685e3f4240d3317ed8bc036dc55d3f6d3f2bcab91` |
| `pro_hover_tick/ping.ogg` | MIT (Earshot, kodla üretildi) | `pro_hover_tick/ping` (2094108523) | temiz | `bc990833118e69bff67d9e16ec6e613b699ae8d0db1cac3099e140b5a7d42df4` |
| `pro_hover_tick/soft.ogg` | MIT (Earshot, kodla üretildi) | `pro_hover_tick/soft` (335975170) | temiz | `9933e317ce9af0ffc1ddfca732ba2eadcb39ce98a0f42e91ca37413531cad9fe` |
| `pro_impact/air.ogg` | MIT (Earshot, kodla üretildi) | `pro_impact/air` (0) | temiz | `c7ca4393f88f0493336b76cc64603aac47964bedabbaf1ca000b7773863c93a7` |
| `pro_impact/deep.ogg` | MIT (Earshot, kodla üretildi) | `pro_impact/deep` (0) | temiz | `5c7eb00ac2bc6920cf7c9dc61641ef64710e061778f7e22bfaf548a26f3fb131` |
| `pro_impact/rumble.ogg` | MIT (Earshot, kodla üretildi) | `pro_impact/rumble` (0) | temiz | `07f325e8278009b325e930c2e13b78536fb7741baeae7ccd0819d50851bdff9f` |
| `pro_impact/short.ogg` | MIT (Earshot, kodla üretildi) | `pro_impact/short` (0) | temiz | `a39e6ad8ad356227f9c357604d3a67f492df4162c97766f7f2d02ad6975103c7` |
| `pro_impact/swell.ogg` | MIT (Earshot, kodla üretildi) | `pro_impact/swell` (0) | temiz | `bc12c3fea36c1820b7b747aea4fc97ae911a8e77ab696a1b629fe7e7b8286293` |
| `pro_logo_sting/chirp_hum.ogg` | MIT (Earshot, kodla üretildi) | `pro_logo_sting/chirp_hum` (0) | temiz | `c03622f56c0f3ebcb2967a23a0f30af43774c3de7ded18f682bcdc18a9884de1` |
| `pro_logo_sting/sweep_hit.ogg` | MIT (Earshot, kodla üretildi) | `pro_logo_sting/sweep_hit` (0) | uyarı: pitch climbs 29 semitones over 220 ms (0.10-0.32 s): a rising synth whip reads as cheap | `dd9ee72a174d4d97fe2adae84a686dc53870a33f08dc635af54a925ba20d7ecc` |
| `pro_logo_sting/swell_sting.ogg` | MIT (Earshot, kodla üretildi) | `pro_logo_sting/swell_sting` (0) | temiz | `8e5b194bfed680a4293ab2b7601d442bf8d7ebfbca9f6dc86e3779a4e485f295` |
| `pro_logo_sting/taps_tone.ogg` | MIT (Earshot, kodla üretildi) | `pro_logo_sting/taps_tone` (0) | temiz | `28d3439aea9384aad573d2044e35d2ed5ffa2d430e168991430f10b47faa8933` |
| `pro_logo_sting/zap_bloom.ogg` | MIT (Earshot, kodla üretildi) | `pro_logo_sting/zap_bloom` (0) | temiz | `eed7f4f2ad9dc88fb23d8b0c7bb0c1fb6c3e0341b44dbd567486c33bed9def11` |
| `pro_notify/ding_1822.ogg` | MIT (Earshot, kodla üretildi) | `pro_notify/ding_1822` (0) | temiz | `849d874ebb988404647753da86383b8d16fc68f55e2767a5013e74129e6052f5` |
| `pro_notify/ding_1930.ogg` | MIT (Earshot, kodla üretildi) | `pro_notify/ding_1930` (0) | temiz | `e3afa8746d2aac19626bfc26f7eb7caac5c84b6704286d58f7a6d4da51c5703c` |
| `pro_notify/ding_2045.ogg` | MIT (Earshot, kodla üretildi) | `pro_notify/ding_2045` (0) | temiz | `163a4d660eb20183ec6f224c46f0a3926ca85032f5d2b92da010b15be5bc2eed` |
| `pro_notify/ding_2167.ogg` | MIT (Earshot, kodla üretildi) | `pro_notify/ding_2167` (0) | temiz | `aeff8f8504eadf4670538d380abf1d97146467469f2cffe520916046560c1817` |
| `pro_notify/ding_2296.ogg` | MIT (Earshot, kodla üretildi) | `pro_notify/ding_2296` (0) | temiz | `53327a2a8edd9bcae0fc33264e0cb8f22627d84acae16f7b022fd63cde81dad2` |
| `pro_pop/bloop.ogg` | MIT (Earshot, kodla üretildi) | `pro_pop/bloop` (0) | uyarı: pitch climbs 6 semitones over 55 ms (0.01-0.07 s): a rising synth whip reads as cheap | `13c4c643fa1784b27c5514f34648311b7221957842674967d8150ed5b7cc7332` |
| `pro_pop/boop.ogg` | MIT (Earshot, kodla üretildi) | `pro_pop/boop` (0) | temiz | `c8859d5dbf4c41100b596966727aea3b635a48f047da4295968fad312b0168a4` |
| `pro_pop/chirp.ogg` | MIT (Earshot, kodla üretildi) | `pro_pop/chirp` (0) | temiz | `5ad2728e74010153194fe8da3703fff836ff48813010b7efb32e72923475f38d` |
| `pro_pop/double.ogg` | MIT (Earshot, kodla üretildi) | `pro_pop/double` (0) | temiz | `638ee585c9262e39434cd40893217fd6b9b180cbbadf2b5488eb5406f7ee994b` |
| `pro_pop/thup.ogg` | MIT (Earshot, kodla üretildi) | `pro_pop/thup` (0) | temiz | `2de725747d5b3581cc82085b002b5b6528d59a0af753e43d534dce42574b61f6` |
| `pro_pop/tink.ogg` | MIT (Earshot, kodla üretildi) | `pro_pop/tink` (0) | temiz | `b14272c7bf874f879e2329593a13fa25c303129cbbacbc2f7b6fba1adc1653ee` |
| `pro_pop_in/airy.ogg` | MIT (Earshot, kodla üretildi) | `pro_pop_in/airy` (595137824) | temiz | `9b2074e3bfbe27a609a97cbfb25564e8cfff2421d231fdae95d8d06c91511f60` |
| `pro_pop_in/deep.ogg` | MIT (Earshot, kodla üretildi) | `pro_pop_in/deep` (1133510782) | temiz | `352cad211b9771b7fbc60a5ce669c9c06e24e1acfb13852b2577567592ae6937` |
| `pro_pop_in/double.ogg` | MIT (Earshot, kodla üretildi) | `pro_pop_in/double` (1563264929) | temiz | `e95504e42832e965ed77cea568aef727961c545c5252a90fb225fc521e48a320` |
| `pro_pop_in/knock.ogg` | MIT (Earshot, kodla üretildi) | `pro_pop_in/knock` (399595374) | temiz | `98571eb7d3f2e9fac86685296c4beddd148c156d5656917b77f0cc7efea3bf8d` |
| `pro_pop_in/round.ogg` | MIT (Earshot, kodla üretildi) | `pro_pop_in/round` (276866903) | temiz | `7ac686da757fb2b8ab6b109f0a1b0c8db2b6a3fae27f0b365c31ba0ea362b41d` |
| `pro_riser/air_gate.ogg` | MIT (Earshot, kodla üretildi) | `pro_riser/air_gate` (579362556) | temiz | `81d69be36b8a93d49d66c704654d2b89cc13ce129f65488a4de630992efaa8d1` |
| `pro_riser/chop.ogg` | MIT (Earshot, kodla üretildi) | `pro_riser/chop` (1367864807) | temiz | `8d63e6c6e274de3b697274b0f3275e050c6c257507c632d53b89591f7a81ee2e` |
| `pro_riser/nblips.ogg` | MIT (Earshot, kodla üretildi) | `pro_riser/nblips` (1826701615) | temiz | `52b5fba1b198e0862ac0bafce5a97d609b9b20754ff9174a43b73b2c0f8536e5` |
| `pro_riser/nblips_hi.ogg` | MIT (Earshot, kodla üretildi) | `pro_riser/nblips_hi` (661058652) | temiz | `22beee5753a578cb5365403c2ba6e5dacf4351e99518ece3f2e70f6919ce314f` |
| `pro_riser/roll.ogg` | MIT (Earshot, kodla üretildi) | `pro_riser/roll` (1097657232) | temiz | `860936f613dcb80edda61877f67b02a5fff8be45c5a57ef5a80bbec1f1e7cdd3` |
| `pro_shimmer/m0.ogg` | MIT (Earshot, kodla üretildi) | `pro_shimmer/m0` (1826701615) | temiz | `0d2e5fccd3294d77964e087970fcbe6334d374bcc938d83b5aebeee637554da2` |
| `pro_shimmer/m1.ogg` | MIT (Earshot, kodla üretildi) | `pro_shimmer/m1` (1367864807) | temiz | `9bc2282dd6643922eb39773b86e95f785d8fe36dd4422e2a9b9dc32c903171d8` |
| `pro_shimmer/m2.ogg` | MIT (Earshot, kodla üretildi) | `pro_shimmer/m2` (1097657232) | temiz | `1e573c140d83b7c7a19176589448cd69cde8da06ede8f17e51280ef60c0ef194` |
| `pro_shimmer/m3.ogg` | MIT (Earshot, kodla üretildi) | `pro_shimmer/m3` (579362556) | uyarı: metallic comb ring in the tail every 2.1 ms (z 16) | `8f0b0fd1aeb6e9df0feaab866b4e680232ceb9dc2d46149c07257f062bbbb00f` |
| `pro_shimmer/m4.ogg` | MIT (Earshot, kodla üretildi) | `pro_shimmer/m4` (661058652) | temiz | `d65bf60545fbacc248e595b693b7e9a476ab4080ad0847ae2ea8c14bbc9d15f4` |
| `pro_sub_drop/bright.ogg` | MIT (Earshot, kodla üretildi) | `pro_sub_drop/bright` (1241873585) | temiz | `53016980275af90a996fd2b7794c5831d84b9cab12cf1e331e21529cae4cd838` |
| `pro_sub_drop/low.ogg` | MIT (Earshot, kodla üretildi) | `pro_sub_drop/low` (1926751966) | temiz | `2ef9ad8cb8cf65084fc5f1cf47555e0a10d2db71418ab4edd6a96bb403d70747` |
| `pro_sub_drop/quick.ogg` | MIT (Earshot, kodla üretildi) | `pro_sub_drop/quick` (1469265226) | temiz | `c61eeca48417f41bbe1cebd257cae901998540363ba04be591f5970b9ca3b840` |
| `pro_sub_drop/ref.ogg` | MIT (Earshot, kodla üretildi) | `pro_sub_drop/ref` (2029167941) | temiz | `8b20cc9df45bea778c646d3aef71b573ffc59ba6c65c59e40a48193db5ff9cf1` |
| `pro_sub_drop/soft.ogg` | MIT (Earshot, kodla üretildi) | `pro_sub_drop/soft` (1665772335) | temiz | `ccb486509db1ceaadcc767f7b0217528a873d057a344da9425852527017d9a30` |
| `pro_tap/double.ogg` | MIT (Earshot, kodla üretildi) | `pro_tap/double` (268774776) | temiz | `e812b51dd7cd869ba30aba77fd749ae716653cb09acdb9bbabba1f7aaeb53fc6` |
| `pro_tap/finger.ogg` | MIT (Earshot, kodla üretildi) | `pro_tap/finger` (160326542) | temiz | `088de8a317b02552845d332759627cae2507799a61bb01446f9fa1a82b61873b` |
| `pro_tap/glass.ogg` | MIT (Earshot, kodla üretildi) | `pro_tap/glass` (834347243) | temiz | `891101fde84111208ab4b1da03a23dde6d90cb7fb670735a0c10cff56f3a8c48` |
| `pro_tap/knock.ogg` | MIT (Earshot, kodla üretildi) | `pro_tap/knock` (932572530) | temiz | `f55062f2671fb2de5d47b83b6f71543f5835bb9f615bab5a58002cc253fad7bc` |
| `pro_tap/soft.ogg` | MIT (Earshot, kodla üretildi) | `pro_tap/soft` (684045642) | temiz | `482e01d85751a1eb12fc9b418d37614ea7bfd6e88b01f06482d98185f48a0803` |
| `pro_typing_key/blip.ogg` | MIT (Earshot, kodla üretildi) | `pro_typing_key/blip` (87989972) | temiz | `049873b5564790a3343a2f095678c805a5f88b221c6bcd7e7a7e69eb142c9286` |
| `pro_typing_key/crackle.ogg` | MIT (Earshot, kodla üretildi) | `pro_typing_key/crackle` (579362556) | temiz | `41941ec5674afcd760278b56ad480ed86263a24624f002d8551edae6f3e80ec5` |
| `pro_typing_key/double.ogg` | MIT (Earshot, kodla üretildi) | `pro_typing_key/double` (1367864807) | temiz | `4ad31da2088a507e3efd471692e5b156c13ea5d4d167c66ced5600d3456f0696` |
| `pro_typing_key/glass.ogg` | MIT (Earshot, kodla üretildi) | `pro_typing_key/glass` (661058652) | temiz | `077baf985818b48a65ecc7bff0cb65c273dd799141a778450964c8420ec27a16` |
| `pro_typing_key/soft.ogg` | MIT (Earshot, kodla üretildi) | `pro_typing_key/soft` (1097657232) | uyarı: tail cut at -44 dB re peak: fade it out or render it longer | `36b3308b64c4b8dd22dfa6ef04511ed53b96b6bdc136f6b89e3ed34565790c7d` |
| `pro_typing_key/tick.ogg` | MIT (Earshot, kodla üretildi) | `pro_typing_key/tick` (1826701615) | temiz | `287650de0bebfa2c46ec64f19c0cdee505ee7376bfbf7d4133cc4cf49feade21` |
| `pro_typing_run/blip.ogg` | MIT (Earshot, kodla üretildi) | `pro_typing_run/blip` (1097657232) | temiz | `cc98222b68ed9481a133f4970fc848bd29ddc2faf0c6f889da7c194e4b647700` |
| `pro_typing_run/double.ogg` | MIT (Earshot, kodla üretildi) | `pro_typing_run/double` (579362556) | temiz | `7078ea051b39d450c6d2ac32371a2f89c511babbb19c5b107807f53a492da563` |
| `pro_typing_run/glass.ogg` | MIT (Earshot, kodla üretildi) | `pro_typing_run/glass` (1367864807) | temiz | `6d29903206659336f38f9c6c360dbc7b293f644fbf7e9fbe703cde597f78448d` |
| `pro_typing_run/soft.ogg` | MIT (Earshot, kodla üretildi) | `pro_typing_run/soft` (661058652) | temiz | `63d4279ccde7f6eafb603e940e874762cced4d119aeb8de43973bb898ebad44a` |
| `pro_typing_run/standard.ogg` | MIT (Earshot, kodla üretildi) | `pro_typing_run/standard` (1826701615) | temiz | `7aaf6b87bc0089d47efa7c904e98f08c3b0480da3d023af83c8f4a6d7db4e1f7` |
| `pro_typing_run/tick.ogg` | MIT (Earshot, kodla üretildi) | `pro_typing_run/tick` (87989972) | temiz | `539cf69efe45e16a1451b8b26404883ff785bf04b5946248a2cb1c5ce45a965b` |
| `pro_whoosh_big/gritty.ogg` | MIT (Earshot, kodla üretildi) | `pro_whoosh_big/gritty` (960019297) | temiz | `732343e27a8b6342e12f43e1b164fc23600592cb6d0cb8d36cd440b23a7c2411` |
| `pro_whoosh_big/long.ogg` | MIT (Earshot, kodla üretildi) | `pro_whoosh_big/long` (277758907) | temiz | `af112ae4caf5489c1a1c4ef94be162fa2ab69c109ff396906e59a318ae024a9d` |
| `pro_whoosh_big/reverse.ogg` | MIT (Earshot, kodla üretildi) | `pro_whoosh_big/reverse` (1736358612) | temiz | `a3a062d4b83916e7072931c5e7736f4e470c49542ca502df37189a7d5a1acb9f` |
| `pro_whoosh_big/swell.ogg` | MIT (Earshot, kodla üretildi) | `pro_whoosh_big/swell` (1659809102) | temiz | `925385a8385dbafe6a813b5e1fc82abb2096d26174c1c2fc67cc62dcfb9c07f6` |
| `pro_whoosh_big/tonal.ogg` | MIT (Earshot, kodla üretildi) | `pro_whoosh_big/tonal` (19196828) | temiz | `6bf5e030e65888ed025d9e908210110fe0e1479fa1bdd6f18354be95fd149a6d` |
| `pro_whoosh_big/windy.ogg` | MIT (Earshot, kodla üretildi) | `pro_whoosh_big/windy` (23895038) | temiz | `c0fbca747a2cc635dc90dcf3ef9485ade6a644efc59a8d9bdd1484a282dde25b` |
| `pro_zip/arc.ogg` | MIT (Earshot, kodla üretildi) | `pro_zip/arc` (661058652) | uyarı: pitch climbs 23 semitones over 100 ms (0.01-0.11 s): a rising synth whip reads as cheap | `660887484690698b79557b4ae46765944ee2fd3c6bfdc683b83eb675b909cf06` |
| `pro_zip/down.ogg` | MIT (Earshot, kodla üretildi) | `pro_zip/down` (579362556) | temiz | `245e88ad8bb6685179a66643a64102ee44051b3d04d5f430fa4157bda628e65f` |
| `pro_zip/down_warm.ogg` | MIT (Earshot, kodla üretildi) | `pro_zip/down_warm` (87989972) | temiz | `f43becd529aedd34117493af39a4dd34c6a5f1daee5f15f6c1d10d85eb8020f3` |
| `pro_zip/up.ogg` | MIT (Earshot, kodla üretildi) | `pro_zip/up` (1826701615) | uyarı: pitch climbs 20 semitones over 90 ms (0.01-0.10 s): a rising synth whip reads as cheap | `7ed767dccda2e1a607172a70415f9a3cb49cf947eb600044bab008c163fbf076` |
| `pro_zip/up_hi.ogg` | MIT (Earshot, kodla üretildi) | `pro_zip/up_hi` (1097657232) | uyarı: pitch climbs 64 semitones over 230 ms (0.01-0.24 s): a rising synth whip reads as cheap | `aed07da20feefe7bfc44134d38b31ba6047c052b52e645785b807ec9cebb6ef4` |
| `reverse_swell/breath.ogg` | MIT (Earshot, kodla üretildi) | `reverse_swell/breath` (4305) | temiz | `75e348945da3058e5900c2414033cf3ee95112e494aed1450b4f7687a980be44` |
| `reverse_swell/cymbal.ogg` | MIT (Earshot, kodla üretildi) | `reverse_swell/cymbal` (4301) | temiz | `ef1e3144ad855f0591c9e08073be289122a6251a8d97aa030255f35697221241` |
| `reverse_swell/dark.ogg` | MIT (Earshot, kodla üretildi) | `reverse_swell/dark` (4303) | temiz | `0a745bf43666946e56148ebf919ad46011b8024a1cde848f5b32d19cdae7d1c7` |
| `reverse_swell/ring.ogg` | MIT (Earshot, kodla üretildi) | `reverse_swell/ring` (4302) | temiz | `e439b569752a28db258a3d49e65571c8c9d0a6355aea4be6611abf0cb8f49f82` |
| `reverse_swell/short.ogg` | MIT (Earshot, kodla üretildi) | `reverse_swell/short` (4304) | temiz | `50a8d88cba620fc3523b576530ed75e08edeedc84ece7eca9f655eee55126197` |
| `riser/air.ogg` | MIT (Earshot, kodla üretildi) | `riser/air` (1826701615) | temiz | `60ec8528a3fb98876a4564eafaf6fa4e2b73e9d735d87495c53445d5eddafe54` |
| `riser/build.ogg` | MIT (Earshot, kodla üretildi) | `riser/build` (4402) | temiz | `39dd2b85583bebe023b2c236214728733e2e958beafef509ffdeadf188a7fdb5` |
| `riser/dark.ogg` | MIT (Earshot, kodla üretildi) | `riser/dark` (4401) | temiz | `4164f88a78a59f94947654a1c90513dac5b99992e69804c159eb4e57074c8068` |
| `riser/rush.ogg` | MIT (Earshot, kodla üretildi) | `riser/rush` (579362556) | temiz | `bca32c02d3e921676fe534e335ae1d8e3f00cacc79073eb0181464a1dd947fce` |
| `riser/shepard.ogg` | MIT (Earshot, kodla üretildi) | `riser/shepard` (1097657232) | temiz | `b8ad6b8850a40203a2ee176776465d7c2de7789eed7e6d3a08feb46f69fa261e` |
| `riser/snatch.ogg` | MIT (Earshot, kodla üretildi) | `riser/snatch` (4403) | temiz | `5b755b35d5846034c9ca0f2f66e2999f0d245fb31295266533016c3e3845d801` |
| `riser/swell.ogg` | MIT (Earshot, kodla üretildi) | `riser/swell` (661058652) | temiz | `e73c2cb60876eec8376367e19412decd4e44f045e77e90650bf7ba0f68a681c2` |
| `riser/tension.ogg` | MIT (Earshot, kodla üretildi) | `riser/tension` (1367864807) | temiz | `5a3b9bffffe90aa92dd6388f68014c66ec48b65bf9d49d555e53ac0b6047f5d7` |
| `shimmer/m0.ogg` | MIT (Earshot, kodla üretildi) | `shimmer/m0` (1826701615) | temiz | `dfe5938b8fe04dcf6904b3fcb22ccf7756aefce28f640eaf4b052252a1522cda` |
| `shimmer/m1.ogg` | MIT (Earshot, kodla üretildi) | `shimmer/m1` (1367864807) | temiz | `d8433473e493f08105325b575a591b4282574e363c922eab1000f9d377728bfd` |
| `shimmer/m2.ogg` | MIT (Earshot, kodla üretildi) | `shimmer/m2` (1097657232) | temiz | `26e4373ce0f569f2cf7dd46d41417b87a978ae43a5822dd725cc24572c5f0a74` |
| `shimmer/m3.ogg` | MIT (Earshot, kodla üretildi) | `shimmer/m3` (579362556) | temiz | `dd0dd571aee6ed7943e62330dbc9ecbc4fc634e5a9e79d20161647dfed14b07e` |
| `shimmer/m4.ogg` | MIT (Earshot, kodla üretildi) | `shimmer/m4` (661058652) | temiz | `e84a1f279647a427c8b255bcf98ec23babcb600f174c6fd2ce07bc6809923b1a` |
| `shimmer/m5.ogg` | MIT (Earshot, kodla üretildi) | `shimmer/m5` (87989972) | temiz | `54da5c08ff4804225e71cc10596929855e96322068fbeb547d68cfbe0ca9ef6d` |
| `shutter/dslr.ogg` | MIT (Earshot, kodla üretildi) | `shutter/dslr` (1) | temiz | `adb258fd5ef9df71f5349fb6c96495cad83ca947d266dbc7b32e36bb02f9301c` |
| `shutter/film.ogg` | MIT (Earshot, kodla üretildi) | `shutter/film` (1) | temiz | `b4511862c11e5982ea454587bb735f890425998422e744a09b89023333454696` |
| `shutter/mirror.ogg` | MIT (Earshot, kodla üretildi) | `shutter/mirror` (1) | temiz | `73ffee507364b6602a6993a5846233dbd3e4a3e3529f3f0ab6aade9c8110221f` |
| `shutter/quick.ogg` | MIT (Earshot, kodla üretildi) | `shutter/quick` (1) | temiz | `be03e6a3248ecdbc69ec9fd567549cbdc057006255ae8f53871d67f6c02528f7` |
| `shutter/snap.ogg` | MIT (Earshot, kodla üretildi) | `shutter/snap` (1) | temiz | `afbe2a9bd7dc6ffa83d5a58d1e026fcce676fea378fe9d9e7603e133bd7eef19` |
| `sub_drop/808.ogg` | MIT (Earshot, kodla üretildi) | `sub_drop/808` (1342382292) | temiz | `852e147bf8f3a8c2b1d46dfdf718a1304a1f5df9a2bda34be04048fd3fd473ed` |
| `sub_drop/gritty.ogg` | MIT (Earshot, kodla üretildi) | `sub_drop/gritty` (1665772335) | temiz | `1d54b879c56ad07a1d10c6cb87bbccea2dcd8375f111a8d83e5393a8819b2260` |
| `sub_drop/long.ogg` | MIT (Earshot, kodla üretildi) | `sub_drop/long` (1926751966) | temiz | `186c6a3c4bd4a8fea0a37ab65f7e2183b94eb44850967f775deb5e93ab74d345` |
| `sub_drop/pro.ogg` | MIT (Earshot, kodla üretildi) | `sub_drop/pro` (1469265226) | temiz | `e491649a9d2b9730bb75163443b7aed67e9f81756fea9512192efd1414cd2d22` |
| `sub_drop/punch.ogg` | MIT (Earshot, kodla üretildi) | `sub_drop/punch` (1241873585) | temiz | `4e3dd336bb6e9e1afcdd1919b8fbb72dd9a57347de21b069b965ad4576a661ed` |
| `swipe/cloth.ogg` | MIT (Earshot, kodla üretildi) | `swipe/cloth` (883394181) | temiz | `4e0ea9841089d9a343092d48a9aef2bc3728aca2e24689fdec076aae940e921a` |
| `swipe/flick.ogg` | MIT (Earshot, kodla üretildi) | `swipe/flick` (1678714633) | temiz | `229ce6f9d0074a31e033efe09fd79fc90403dc699ab5bd67f4c70a4f530df4d3` |
| `swipe/glide.ogg` | MIT (Earshot, kodla üretildi) | `swipe/glide` (1378931225) | temiz | `9be70d7b7ecf39a944e772c8a48b26417da0e48e9ddac8b61d161a91299ded10` |
| `swipe/paper.ogg` | MIT (Earshot, kodla üretildi) | `swipe/paper` (1264633460) | temiz | `abc8742d6a832cb7232742a081480af0dc7d2b10ee16262f4a2c28cc095addd1` |
| `swipe/velvet.ogg` | MIT (Earshot, kodla üretildi) | `swipe/velvet` (968699985) | temiz | `3e546d8a205ba79c8bcfd100a95942a45b417d9f08f058179a67a613f4190778` |
| `swish/blade.ogg` | MIT (Earshot, kodla üretildi) | `swish/blade` (409661535) | temiz | `5c17485a7d45e32035bda0c76a58601852de6c79ec59cd5693bcbbea5f054179` |
| `swish/bright.ogg` | MIT (Earshot, kodla üretildi) | `swish/bright` (4501) | temiz | `6f491eed3d96526091c21d961c24e817a8269465da3e35613107068a9661a970` |
| `swish/cane.ogg` | MIT (Earshot, kodla üretildi) | `swish/cane` (1752837751) | temiz | `588f2b4c32f6b706d054d5a120fbd39e32ac9c82415753cb4d252344280d5a81` |
| `swish/flick.ogg` | MIT (Earshot, kodla üretildi) | `swish/flick` (4502) | temiz | `841f35cf54e970967be21e85a2c1c6269f45555bbdf084f1ead9bf8b397e190e` |
| `swish/soft.ogg` | MIT (Earshot, kodla üretildi) | `swish/soft` (1007119508) | temiz | `d81cacf4d88b7c55858ef85d86c9b49da7d969d435d2e4b586cfa3ea9ba448ae` |
| `swish/stick.ogg` | MIT (Earshot, kodla üretildi) | `swish/stick` (1442435298) | temiz | `c43502ff54706571d282dc9e8437a8de3c018338c3c8c983965174eb0a36556a` |
| `swish/zing.ogg` | MIT (Earshot, kodla üretildi) | `swish/zing` (756778319) | temiz | `2531b30691d0d6e24a82aa07d63546d877db7e819dec8bf080605684110ddf7e` |
| `tap/finger.ogg` | MIT (Earshot, kodla üretildi) | `tap/finger` (175124325) | temiz | `598bf93551fbce789ee5516ebe02b71a59d34c13956b5fded3106582e70fe236` |
| `tap/glass.ogg` | MIT (Earshot, kodla üretildi) | `tap/glass` (409276250) | temiz | `ff373f057352c2f6abc30e729a7d92f2a555566dcfbb274804e3b8736fb695af` |
| `tap/knuckle.ogg` | MIT (Earshot, kodla üretildi) | `tap/knuckle` (1826701615) | temiz | `209bce649bf88018272100674e3cbd1156605ffb506e9de23513763ded350164` |
| `tap/soft.ogg` | MIT (Earshot, kodla üretildi) | `tap/soft` (575199001) | temiz | `e84fc20e1a9e9bbbe71ee0da80606934e9e321c3768761aadcdfbf6795b272b5` |
| `tap/table.ogg` | MIT (Earshot, kodla üretildi) | `tap/table` (929832608) | temiz | `01c50b4d8c62124fcf64cd8f6952d2e485849e847f702097348a57f23c34ce25` |
| `toggle/latch.ogg` | MIT (Earshot, kodla üretildi) | `toggle/latch` (98727163) | temiz | `87be863684c0c944cfcad5f315046c7f2d4e4f737c4c8230e3526094c329b6e6` |
| `toggle/micro.ogg` | MIT (Earshot, kodla üretildi) | `toggle/micro` (460490113) | temiz | `08d4699b932a28c006b6947e3227dd135e4dbcd782ea68476b47c3720ec388aa` |
| `toggle/off.ogg` | MIT (Earshot, kodla üretildi) | `toggle/off` (1995665369) | temiz | `c97b7e28cbd43670a21aee7e4a72e920d154a12ca09d1cf5022b07b46358b9c6` |
| `toggle/on.ogg` | MIT (Earshot, kodla üretildi) | `toggle/on` (198682238) | temiz | `45828c55768ab1444d3754859e4c6a843b41b5c425571284d6f2931b4e0044f4` |
| `toggle/rocker.ogg` | MIT (Earshot, kodla üretildi) | `toggle/rocker` (2134948140) | temiz | `eef4f9263b931922386f6f018491a19cea88fe749ac3e9be98ff3cee237ed544` |
| `typing_key/clicky.ogg` | MIT (Earshot, kodla üretildi) | `typing_key/clicky` (1097657232) | temiz | `2e023fa48c40639cd1134aed7f7034c253ddf767caf54858ddbef31616ed8e6f` |
| `typing_key/crisp.ogg` | MIT (Earshot, kodla üretildi) | `typing_key/crisp` (1367864807) | temiz | `9e18ed14b4e10f50eadfaade37a9cb36b4954e868619ce7676988a787c753c7c` |
| `typing_key/deep.ogg` | MIT (Earshot, kodla üretildi) | `typing_key/deep` (579362556) | temiz | `5bb6af00853e70745402ddc9d093cd517687b8212934a380fdb51aed4799c708` |
| `typing_key/laptop.ogg` | MIT (Earshot, kodla üretildi) | `typing_key/laptop` (87989972) | uyarı: metallic comb ring in the tail every 2.4 ms (z 23) | `13718f4fd23868430a5029fc3e386f69aff4b289e740bf2fe40c134a5543ad7d` |
| `typing_key/light.ogg` | MIT (Earshot, kodla üretildi) | `typing_key/light` (661058652) | uyarı: metallic comb ring in the tail every 4.9 ms (z 18) | `2f788a27ff0595deb3e6e6e7111c2c0976751441aa3b1e93cde071bdd894a92c` |
| `typing_key/thock.ogg` | MIT (Earshot, kodla üretildi) | `typing_key/thock` (1826701615) | temiz | `489f75501d72078cdf3707e63b4228562fce91be018ae126e8c33c43d0a922a2` |
| `ui_pop/blip.ogg` | MIT (Earshot, kodla üretildi) | `ui_pop/blip` (1) | temiz | `92901bc8427ec17487303700aae9968ec10b39e84959c5dd4af2122deb266319` |
| `ui_pop/boop.ogg` | MIT (Earshot, kodla üretildi) | `ui_pop/boop` (1) | temiz | `bc5fa7cf844408e280d6a2191796f63314052d88a1065149319e154fde48c637` |
| `ui_pop/fall.ogg` | MIT (Earshot, kodla üretildi) | `ui_pop/fall` (1) | temiz | `eda05b55b8dae495d0bc3ac708e9636aed6dad5520dafba6f8f51ef8f4b71452` |
| `ui_pop/soft.ogg` | MIT (Earshot, kodla üretildi) | `ui_pop/soft` (1) | temiz | `9736883bf066ef910f07dca566749b80afb0afae41c2cc1a479097ba5cbdfb4a` |
| `ui_pop/step.ogg` | MIT (Earshot, kodla üretildi) | `ui_pop/step` (1) | temiz | `88c560c1d072b695f19d1f7ddb7b82e408a2e399e57719b22b6a4900ff31f3eb` |
| `ui_pop/wide.ogg` | MIT (Earshot, kodla üretildi) | `ui_pop/wide` (1) | temiz | `59fdeac768e35b482c644bf99934f1bcb7e6dc6c96b9b11490199e302cc50336` |
| `whoosh_big/cape.ogg` | MIT (Earshot, kodla üretildi) | `whoosh_big/cape` (31885684) | temiz | `ded81ce0bc5744b99e4790d23527fa83609e21b4d0277353d40fd467b3ec781b` |
| `whoosh_big/deep.ogg` | MIT (Earshot, kodla üretildi) | `whoosh_big/deep` (254919109) | temiz | `0fa58e0e96c630b489b5b27fcb5c60692c4b27194bf0b1256882b9aa2a07bc47` |
| `whoosh_big/gust.ogg` | MIT (Earshot, kodla üretildi) | `whoosh_big/gust` (1003958671) | temiz | `ca94958edac747a216c5eff899c056b9a3e0528dd00a8bf11ff66896da19a93a` |
| `whoosh_big/jet.ogg` | MIT (Earshot, kodla üretildi) | `whoosh_big/jet` (748279673) | temiz | `1353dd7512e68e3810d880d4c3a2c9fef54c5dd17a7bf385f4bb5f6339b1d24d` |
| `whoosh_big/reverse.ogg` | MIT (Earshot, kodla üretildi) | `whoosh_big/reverse` (645728434) | temiz | `40ee32e3792616ca760b1e5c58a3ebd002cd2bc2199f27d09ee68056ab2a0e97` |
| `whoosh_big/swell.ogg` | MIT (Earshot, kodla üretildi) | `whoosh_big/swell` (696394185) | temiz | `c0a0db91a29b4fff0f76e880195be370a9eb097cb4501e07d78f891a539b2bbc` |
| `whoosh_big/thump.ogg` | MIT (Earshot, kodla üretildi) | `whoosh_big/thump` (4201) | temiz | `9a1536e86f31dc229c403827bc59e2a360c6ec77f3ec58e5d37913c2a7f83f82` |
| `whoosh_big/thump_airy.ogg` | MIT (Earshot, kodla üretildi) | `whoosh_big/thump_airy` (4203) | temiz | `a2b370e2a4b189c485d2fb3b33c44083d2fa57f19bab04b59c7ff649930c5fde` |
| `whoosh_big/thump_deep.ogg` | MIT (Earshot, kodla üretildi) | `whoosh_big/thump_deep` (4202) | temiz | `a34e7d6f4469895acdf688736c1d37c62f9d3ac478ecdcc3eb4b9d4f91f0ef66` |
| `whoosh_fast/crisp.ogg` | MIT (Earshot, kodla üretildi) | `whoosh_fast/crisp` (420116625) | temiz | `ace7f1c92d21b700dfd0713d504a34bf58624b7da5b880cc0bec94ea1a56c27f` |
| `whoosh_fast/heavy.ogg` | MIT (Earshot, kodla üretildi) | `whoosh_fast/heavy` (1864245503) | temiz | `ccc1d43b0891853b5fabfb20f7b5bd66c244211da986e6e5228b4f575f5c7d81` |
| `whoosh_fast/reverse.ogg` | MIT (Earshot, kodla üretildi) | `whoosh_fast/reverse` (436489598) | temiz | `9609a916cd6070efe0ab6be4360bda26ee36e89d4383e0613fdbf2a79ff4bd2e` |
| `whoosh_fast/sleeve.ogg` | MIT (Earshot, kodla üretildi) | `whoosh_fast/sleeve` (1736822116) | temiz | `c4e17d929705f41acdec008ba79efc6d42bf5e743f1a344ccb4cb5e081e9d7b0` |
| `whoosh_fast/tight.ogg` | MIT (Earshot, kodla üretildi) | `whoosh_fast/tight` (1621782255) | temiz | `60d39edd153f98a4ca595d9cebc4ddb2bf88261888c2186be7bf89a91c3c3f71` |
| `whoosh_fast/whip.ogg` | MIT (Earshot, kodla üretildi) | `whoosh_fast/whip` (4503) | temiz | `785577dae4dd92dc62c639d5d2e602dd45c7a678839904e5d940e32306903a84` |
| `whoosh_fast/whistle.ogg` | MIT (Earshot, kodla üretildi) | `whoosh_fast/whistle` (1982965812) | temiz | `b601ebdf026ffcd6ceb3b7fbc9a83bbdf99096753b1e28528b9dfeaf40022105` |
