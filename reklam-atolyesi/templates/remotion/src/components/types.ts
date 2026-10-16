import type React from "react";
import type { z } from "zod";

export type Category = "text" | "transition" | "light" | "camera" | "product" | "proof" | "signature" | "helper";

export type Entry<S extends z.ZodTypeAny = z.ZodTypeAny> = {
  name: string;
  category: Category;
  version: string;
  schema: S;
  // Galeri/test için nötr yer tutucu prop'lar ("Marka A", "Örnek başlık"); hiçbir zaman varsayılan içerik değildir (ilke 12).
  demo: z.infer<S>;
  Component: React.FC<any>;
  // Yalnızca önizleme (SafeZoneGuide, BeatMarker): hazır üretim planında kullanılamaz.
  previewOnly?: boolean;
};

export const easeOutCubic = (t: number) => 1 - Math.pow(1 - Math.min(1, Math.max(0, t)), 3);
export const easeInOut = (t: number) => {
  const x = Math.min(1, Math.max(0, t));
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
};
export const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
