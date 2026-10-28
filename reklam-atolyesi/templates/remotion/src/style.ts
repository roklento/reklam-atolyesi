// Stil kopyası yükleyici (spec 5.6). Kurulumdaki varsayılanlar NÖTRDÜR (ilke 12): nötr gri palet, tek nötr sans-serif
// (Inter, Türkçe karakter destekli; latin + latin-ext birlikte), LUT/gren/vinyet yok, efekt bütçesi varsayılanı.
// Bu değerler yalnızca stil seçilmeden önceki önizlemeler içindir; hiçbir yöne başlangıç noktası yapılmaz.
import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-ext-400.css";
import "@fontsource/inter/latin-700.css";
import "@fontsource/inter/latin-ext-700.css";
import { useEffect, useState } from "react";
import { continueRender, delayRender } from "remotion";

export type Style = {
  palette: { ink: string; accent: string; bg: string };
  captions?: { accent?: string };  // altyazı vurgu rengi (yoksa palette.accent; 1.5.0)
  fonts: { display: string; displayStyle: "normal" | "italic"; displayWeight: number; body: string; brand: string; brandTracking: string };
  grade: { lut: string | null; grain: number; vignette: number };
  motion: { easeIn: [number, number, number, number]; charStaggerMs: number; revealMs: number };
  effects: { signatureMax: number; transitionTypesMax: number; persistentAtmosphere: boolean };
  sound: { signatureReveal: string | null; transition: string | null; musicBpmRange: [number, number] | null };
  layout: Record<string, { titleY: number }>;
};

export const NEUTRAL_STYLE: Style = {
  palette: { ink: "#1F1F1F", accent: "#6B6B6B", bg: "#E6E6E6" },
  fonts: { display: "Inter", displayStyle: "normal", displayWeight: 700, body: "Inter", brand: "Inter", brandTracking: "0em" },
  grade: { lut: null, grain: 0, vignette: 0 },
  motion: { easeIn: [0.16, 1, 0.3, 1], charStaggerMs: 0, revealMs: 400 },
  effects: { signatureMax: 1, transitionTypesMax: 2, persistentAtmosphere: false },
  sound: { signatureReveal: null, transition: null, musicBpmRange: null },
  // Yazı güvenli alanı içinde (5.19): 9:16 üst %14, 4:5 üst ~250 px (%18,5), 1:1 kenarlardan pay.
  layout: { "9x16": { titleY: 0.14 }, "4x5": { titleY: 0.19 }, "1x1": { titleY: 0.1 } },
};

export const resolveStyle = (s?: Partial<Style> | null): Style => ({
  ...NEUTRAL_STYLE,
  ...(s ?? {}),
  palette: { ...NEUTRAL_STYLE.palette, ...(s?.palette ?? {}) },
  fonts: { ...NEUTRAL_STYLE.fonts, ...(s?.fonts ?? {}) },
  grade: { ...NEUTRAL_STYLE.grade, ...(s?.grade ?? {}) },
  motion: { ...NEUTRAL_STYLE.motion, ...(s?.motion ?? {}) },
  effects: { ...NEUTRAL_STYLE.effects, ...(s?.effects ?? {}) },
  layout: { ...NEUTRAL_STYLE.layout, ...(s?.layout ?? {}) },
});

const TR_SAMPLE = "ğşıİçöüĞŞÇÖÜ";

/** Yüklenmesi beklenecek font aileleri: stilin display/body/brand fontları, plandaki katmanların fontFamily'leri ve bileşen varsayılanı
 *  Inter (1.5.1). Yalnızca Inter beklenirse marka fontu kare alınırken henüz yüklenmemiş olabilir ve yazı yedek fontla çizilir. */
export const fontFamiliesOf = (style: Style, plan?: { scenes?: { layers?: { props?: Record<string, unknown> }[] }[] }): string[] => {
  const fams = new Set<string>(["Inter", style.fonts.display, style.fonts.body, style.fonts.brand]);
  for (const s of plan?.scenes ?? []) {
    for (const l of s.layers ?? []) {
      const f = l.props?.fontFamily;
      if (typeof f === "string" && f.trim()) fams.add(f.split(",")[0].trim().replace(/^['"]|['"]$/g, ""));
    }
  }
  return Array.from(fams).filter(Boolean);
};

/** Fontlar yüklenene kadar render'ı bekletir (Türkçe karakterlerin yedek fonta düşmemesi için). Aile verilmezse yalnızca Inter. */
export const useFontsReady = (families: string[] = ["Inter"], weights: number[] = [400, 700]) => {
  const [handle] = useState(() => delayRender("fontlar yükleniyor"));
  const key = families.join("|") + "/" + weights.join("|");
  useEffect(() => {
    let done = false;
    const finish = () => {
      if (!done) {
        done = true;
        continueRender(handle);
      }
    };
    if (typeof document !== "undefined" && (document as Document).fonts) {
      const fams = key.split("/")[0].split("|").filter(Boolean);
      const ws = key.split("/")[1].split("|").map(Number);
      Promise.all(fams.flatMap((f) => ws.map((w) => document.fonts.load(`${w} 32px "${f}"`, TR_SAMPLE))))
        .then(() => document.fonts.ready)
        .then(finish, finish);
    } else {
      finish();
    }
  }, [handle, key]);
};

export const cubic = (e: [number, number, number, number]) => e;
