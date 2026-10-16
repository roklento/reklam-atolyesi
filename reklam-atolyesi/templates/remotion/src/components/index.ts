// Bileşen kütüphanesi kaydı (spec 5.12). Kütüphane bir ARAÇ KUTUSUDUR: hiçbir bileşen varsayılan olarak kurgu planına girmez;
// seçim stil kitabına ve efekt bütçesine (5.6) göre yapılır. Yeni bileşen: Claude yazar → 3 sabit kare + 2 sn test → öz denetim →
// kullanıcı taslakta görür → onaylanırsa sürüm numarası ve testiyle buraya eklenir; onaylanmazsa kampanyaya özel kalır.
import { CAMERA } from "./camera";
import { HELPER } from "./helper";
import { LIGHT } from "./light";
import { PRODUCT } from "./product";
import { PROOF } from "./proof";
import { SIGNATURE } from "./signature";
import { TEXT } from "./text";
import { TRANSITION } from "./transition";
import type { Entry } from "./types";

export const LIBRARY: Entry[] = [...TEXT, ...TRANSITION, ...LIGHT, ...CAMERA, ...PRODUCT, ...PROOF, ...SIGNATURE, ...HELPER];
export const BY_NAME: Record<string, Entry> = Object.fromEntries(LIBRARY.map((e) => [e.name, e]));
export const WRAPPERS = new Set(["KenBurns", "FakeRackFocus", "HandheldDrift", "Spotlight", "LightRays", "ParticleSwirl", "HeatShimmer", "SafeZoneGuide"]);
export { TRANSITIONS } from "./transition";
export type { Entry } from "./types";
