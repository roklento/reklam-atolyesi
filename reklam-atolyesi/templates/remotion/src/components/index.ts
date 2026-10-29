// Bileşen kütüphanesi kaydı (spec 5.12). Kütüphane bir ARAÇ KUTUSUDUR: hiçbir bileşen varsayılan olarak kurgu planına girmez;
// seçim stil kitabına ve efekt bütçesine (5.6) göre yapılır. Yeni bileşen: Claude yazar → 3 sabit kare + 2 sn test → öz denetim →
// kullanıcı taslakta görür → onaylanırsa sürüm numarası ve testiyle buraya eklenir; onaylanmazsa kampanyaya özel kalır.
import { CAMERA } from "./camera";
import { COMPARE } from "./compare";
import { COUNTER } from "./counter";
import { HELPER } from "./helper";
import { LIGHT } from "./light";
import { MARK } from "./mark";
import { MEDIA } from "./media";
import { PRODUCT } from "./product";
import { PROOF } from "./proof";
import { SIGNATURE } from "./signature";
import { TEXT } from "./text";
import { TRANSITION } from "./transition";
import type { Entry } from "./types";

// 1.8.0 bileşenleri (TextMark, BeforeAfter, NumberRoll, PictureInPicture, PhoneScreen) sona eklenir.
export const LIBRARY: Entry[] = [...TEXT, ...TRANSITION, ...LIGHT, ...CAMERA, ...PRODUCT, ...PROOF, ...SIGNATURE, ...HELPER, ...MARK, ...COMPARE, ...COUNTER,
  ...MEDIA];
export const BY_NAME: Record<string, Entry> = Object.fromEntries(LIBRARY.map((e) => [e.name, e]));
export const WRAPPERS = new Set(["KenBurns", "FakeRackFocus", "HandheldDrift", "Spotlight", "LightRays", "ParticleSwirl", "HeatShimmer", "SafeZoneGuide", "PictureInPicture"]);
export { TRANSITIONS } from "./transition";
// Kaynak alan prop'lar (1.8.0): planda kaynak nesnesi ({kind, asset|path, in_s, out_s}); scenes.py ara dosyayı "<katman>.<prop>"
// anahtarıyla üretir, sahne şablonu URL'ye çevirir. admem/editplan.py SOURCE_PROPS ile aynı tablo.
export const SOURCE_PROPS: Record<string, string[]> = { BeforeAfter: ["before", "after"], PictureInPicture: ["inset"], PhoneScreen: ["screen"] };
export type { Entry } from "./types";
