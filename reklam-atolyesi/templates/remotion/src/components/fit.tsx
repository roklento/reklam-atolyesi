// Gerçek ölçümlü yazı sığdırma (1.6.0): satırlar tarayıcıda @remotion/layout-utils measureText ile ölçülür, yazı kutuya ve satır
// sınırına sığana dek fontSize'dan minFontSize'a küçültülür (büyütülmez). Sığmıyorsa blok kırmızı çerçeve + "YAZI SIĞMIYOR" çizer
// (FİYAT YOK gibi görünür bir QC işareti). Ölçüm konsola "RA_LAYOUT {json}" satırı olarak yazılır; render.mjs bunları toplayıp
// <çıktı>.layout.json yazar, qc/checks.py safe --layout tahmin yerine bu ölçümü kullanır.
// Ölçüm font yüklenmeden yapılmaz: measureText sonucu önbelleğe alır, yedek fontla alınan ölçü kalıcı olurdu.
import { measureText } from "@remotion/layout-utils";
import React, { useEffect, useMemo, useState } from "react";
import { continueRender, delayRender, useVideoConfig } from "remotion";

export type FitSpec = {
  text: string;
  fontFamily: string;
  fontWeight: number;
  fontSize: number;     // istenen (üst sınır)
  minFontSize: number;  // bunun altına inilmez
  boxWidth: number;     // px, iç boşluklar düşülmüş
  maxLines: number;
  letterSpacing?: string;
};

export type Fit = { fontSize: number; lines: string[]; fits: boolean; widest: number; measured: boolean };

export type Place = { component: string; part?: string; y?: number; mode?: "top" | "center" | "full"; lineHeight: number; padY?: number };

const TR_SAMPLE = "ğşıİçöüĞŞÇÖÜ";

const firstFamily = (f: string) => f.split(",")[0].trim().replace(/^['"]|['"]$/g, "");

const readySpecs = new Set<string>();

const declared = (family: string): boolean => {
  let hit = false;
  document.fonts.forEach((f) => {
    if (f.family.replace(/^['"]|['"]$/g, "") === family) hit = true;
  });
  return hit;
};

/** Ailenin bu ağırlığı yüklenene kadar false; yüklenince yeniden çizim ister. document.fonts.check'e güvenilmez: @font-face CSS'i henüz
 *  eklenmemişse check true döner ve yedek fontla ölçülür (gerçek render'da görüldü). Önce yüz tanımı beklenir (en çok 3 sn; tanımsız
 *  aile sistem/yedek fonttur, ölçüm de onunla yapılır), sonra yüklenir. Sekme başına bir kez. */
export const useFontReady = (family: string, weight: number): boolean => {
  const fam = firstFamily(family);
  const spec = `${weight} 32px "${fam}"`;
  const hasFonts = typeof document !== "undefined" && !!(document as Document).fonts;
  const [ready, setReady] = useState(() => !hasFonts || readySpecs.has(spec));
  const [handle] = useState(() => (ready ? null : delayRender(`yazı ölçümü: ${spec}`)));
  useEffect(() => {
    if (ready || handle === null) return;
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      readySpecs.add(spec);
      setReady(true);
      continueRender(handle);
    };
    const t0 = Date.now();
    const waitDeclared = () => new Promise<void>((res) => {
      const tick = () => (declared(fam) || Date.now() - t0 > 3000 ? res() : void setTimeout(tick, 40));
      tick();
    });
    waitDeclared().then(() => document.fonts.load(spec, TR_SAMPLE)).then(() => document.fonts.ready).then(finish, finish);
  }, [ready, handle, spec, fam]);
  return ready;
};

const width = (s: FitSpec, text: string, fs: number) =>
  measureText({ text, fontFamily: s.fontFamily, fontWeight: s.fontWeight, fontSize: fs, letterSpacing: s.letterSpacing, validateFontIsLoaded: false }).width;

/** Açık satır sonları (\n) korunur; sözcükler açgözlü yerleşir. Kutudan geniş tek sözcük kendi satırında kalır (widest onu gösterir). */
export const wrapLines = (s: FitSpec, fs: number): { lines: string[]; widest: number } => {
  const lines: string[] = [];
  for (const para of s.text.split("\n")) {
    const words = para.split(/\s+/).filter(Boolean);
    let cur = "";
    for (const w of words) {
      const cand = cur ? `${cur} ${w}` : w;
      if (!cur || width(s, cand, fs) <= s.boxWidth) {
        cur = cand;
      } else {
        lines.push(cur);
        cur = w;
      }
    }
    lines.push(cur);
  }
  const widest = Math.max(0, ...lines.map((ln) => (ln ? width(s, ln, fs) : 0)));
  return { lines, widest };
};

export const fitLines = (s: FitSpec): Fit => {
  const min = Math.min(s.minFontSize, s.fontSize);
  const step = Math.max(1, Math.round(s.fontSize * 0.04));
  let fs = s.fontSize;
  for (;;) {
    const r = wrapLines(s, fs);
    if (r.lines.length <= s.maxLines && r.widest <= s.boxWidth + 0.5) return { fontSize: fs, ...r, fits: true, measured: true };
    if (fs <= min) return { fontSize: fs, ...r, fits: false, measured: true };
    fs = Math.max(min, fs - step);
  }
};

const reported = new Set<string>();

/** Ölçülmüş yerleşim. Font hazır değilken ölçmez: istenen boyut ve açık satırlar döner (render bu durumda kare almaz). */
export const useFit = (s: FitSpec, place: Place): Fit => {
  const ready = useFontReady(s.fontFamily, s.fontWeight);
  const { width: W, height: H } = useVideoConfig();
  const key = JSON.stringify(s);
  const fit = useMemo<Fit>(
    () => (ready && typeof document !== "undefined" && s.text.trim()
      ? fitLines(s)
      : { fontSize: s.fontSize, lines: s.text.split("\n"), fits: true, widest: 0, measured: false }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ready, key],
  );
  useEffect(() => {
    if (!fit.measured) return;
    const rec = {
      component: place.component, part: place.part ?? "text", text: s.text.slice(0, 160), requested: s.fontSize, minFontSize: s.minFontSize,
      fontSize: fit.fontSize, lines: fit.lines.length, maxLines: s.maxLines, fits: fit.fits, widest: Math.round(fit.widest),
      boxWidth: Math.round(s.boxWidth), heightPx: Math.round(fit.lines.length * fit.fontSize * place.lineHeight + (place.padY ?? 0)),
      y: place.y ?? null, mode: place.mode ?? "top", width: W, height: H,
    };
    const line = "RA_LAYOUT " + JSON.stringify(rec);
    if (reported.has(line)) return;
    reported.add(line);
    console.log(line);
  }, [fit, key, place.component, place.part, place.y, place.mode, place.lineHeight, place.padY, W, H, s.text, s.fontSize, s.minFontSize, s.maxLines, s.boxWidth]);
  return fit;
};

/** Sığmayan yazı için görünür işaret (render'da da çizilir; QC kaçırmasın diye). */
export const FitAlarm: React.FC<{ on: boolean; children: React.ReactNode }> = ({ on, children }) =>
  on ? (
    <div style={{ outline: "6px solid #B00020", outlineOffset: 6, position: "relative" }}>
      <div style={{ position: "absolute", top: -58, left: 0, background: "#B00020", color: "#FFFFFF", fontFamily: "Inter", fontWeight: 700,
        fontSize: 30, padding: "4px 12px", letterSpacing: 0, lineHeight: 1.2, whiteSpace: "nowrap" }}>YAZI SIĞMIYOR</div>
      {children}
    </div>
  ) : <>{children}</>;

/** Ölçülmüş satırlar: tarayıcı yeniden kırmasın diye her satır nowrap (ölçülmemişse normal kırılma). */
export const lineStyle = (fit: Fit): React.CSSProperties => (fit.measured ? { whiteSpace: "nowrap" } : {});
