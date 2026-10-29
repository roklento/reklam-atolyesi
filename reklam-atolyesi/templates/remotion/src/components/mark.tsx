// Sözcük vurgusu (1.8.0): yazının içindeki bir sözcük ya da söz öbeği el çizimi gibi işaretlenir — circle, underline, highlight, box.
// Çizim @remotion/rough-notation (MIT) ile; ilerleme useCurrentFrame'den, tohum sabit (aynı kare her render'da aynı çizgi). Yazı
// satırları fit.tsx ile ölçülür (TextReveal gibi). Eşleştirme Türkçe katlamalıdır (admem tr_fold: İ/ı/i ve ğ, ş, ç, ö, ü harf harf;
// "IŞIK" ile "ışık" eşleşir). Bulunamazsa kırmızı "VURGU BULUNAMADI" işareti çizilir. Efekt bütçesi: 15 sn'de en fazla 2 (plan doğrulaması).
import { Box, Circle, Highlight, Underline } from "@remotion/rough-notation";
import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { z } from "zod";
import { FitAlarm, lineStyle, useFit } from "./fit";
import { clamp01, easeOutCubic, Entry } from "./types";

const FOLD: Record<string, string> = { ç: "c", ğ: "g", ı: "i", ö: "o", ş: "s", ü: "u", â: "a", î: "i", û: "u" };
/** Harf harf katlama: uzunluk korunur, böylece katlanmış metindeki konum özgün metne aynen döner. */
export const trFoldChars = (s: string): string =>
  Array.from(s).map((ch) => {
    const low = ch === "I" ? "ı" : ch === "İ" ? "i" : ch.toLocaleLowerCase("tr-TR");
    const one = Array.from(low)[0] ?? ch;
    return FOLD[one] ?? one;
  }).join("");

/** Satırlar içinde vurgulanacak aralıklar: önce öbeğin tamamı bir satırda aranır; yoksa öbeğin sözcükleri ayrı ayrı (ilk geçişleri). */
export const findMarks = (lines: string[], mark: string): { line: number; start: number; end: number }[] => {
  const m = trFoldChars(mark.trim());
  if (!m) return [];
  const folded = lines.map((ln) => trFoldChars(ln));
  for (let i = 0; i < folded.length; i++) {
    const k = folded[i].indexOf(m);
    if (k >= 0) return [{ line: i, start: Array.from(folded[i].slice(0, k)).length, end: Array.from(folded[i].slice(0, k + m.length)).length }];
  }
  const out: { line: number; start: number; end: number }[] = [];
  for (const w of m.split(/\s+/).filter(Boolean)) {
    for (let i = 0; i < folded.length; i++) {
      const k = folded[i].indexOf(w);
      if (k >= 0) {
        out.push({ line: i, start: Array.from(folded[i].slice(0, k)).length, end: Array.from(folded[i].slice(0, k + w.length)).length });
        break;
      }
    }
  }
  return out;
};

const markSchema = z.object({ text: z.string(), mark: z.string(), mode: z.enum(["circle", "underline", "highlight", "box"]).default("underline"),
  color: z.string().default("#1F1F1F"), markColor: z.string().default("#6B6B6B"), fontFamily: z.string().default("Inter"), fontWeight: z.number().default(700),
  fontSize: z.number().default(96), minFontSize: z.number().default(56), maxLines: z.number().int().min(1).default(3), y: z.number().default(0.14),
  startFrame: z.number().int().min(0).default(10), drawFrames: z.number().int().min(1).default(18), strokeWidth: z.number().default(6),
  seed: z.number().int().default(7) });

const TextMark: React.FC<z.infer<typeof markSchema>> = (p) => {
  const f = useCurrentFrame();
  const { width } = useVideoConfig();
  const fit = useFit({ text: p.text, fontFamily: p.fontFamily, fontWeight: p.fontWeight, fontSize: p.fontSize, minFontSize: p.minFontSize,
    boxWidth: width * 0.88, maxLines: p.maxLines }, { component: "TextMark", y: p.y, lineHeight: 1.2 });
  const a = easeOutCubic(f / 10);
  const progress = clamp01((f - p.startFrame) / p.drawFrames);
  const marks = fit.measured ? findMarks(fit.lines, p.mark) : [];
  const missing = fit.measured && marks.length === 0;
  const annotate = (node: React.ReactNode, key: string, i: number) => {
    const common = { progress, seed: p.seed + i, color: p.markColor };
    if (p.mode === "circle") return <Circle key={key} {...common} strokeWidth={p.strokeWidth} padding={{ left: 16, right: 16, top: 0, bottom: 0 }}>{node}</Circle>;
    if (p.mode === "box") return <Box key={key} {...common} strokeWidth={p.strokeWidth} padding={{ left: 10, right: 10, top: 4, bottom: 4 }}>{node}</Box>;
    if (p.mode === "highlight") return <Highlight key={key} {...common} iterations={2}>{node}</Highlight>;
    return <Underline key={key} {...common} strokeWidth={p.strokeWidth}>{node}</Underline>;
  };
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: "6%", right: "6%", top: `${p.y * 100}%`, textAlign: "center", fontFamily: p.fontFamily, fontWeight: p.fontWeight,
        fontSize: fit.fontSize, color: p.color, lineHeight: 1.2, opacity: a, transform: `translateY(${(1 - a) * 24}px)` }}>
        <FitAlarm on={!fit.fits}>
          {fit.lines.map((ln, li) => {
            const chars = Array.from(ln);
            const here = marks.map((m, mi) => ({ ...m, mi })).filter((m) => m.line === li).sort((x, y) => x.start - y.start);
            const parts: React.ReactNode[] = [];
            let at = 0;
            here.forEach((m) => {
              if (m.start > at) parts.push(<span key={`t${at}`}>{chars.slice(at, m.start).join("")}</span>);
              parts.push(annotate(<span style={{ position: "relative" }}>{chars.slice(m.start, m.end).join("")}</span>, `m${m.mi}`, m.mi));
              at = m.end;
            });
            if (at < chars.length) parts.push(<span key={`t${at}`}>{chars.slice(at).join("")}</span>);
            return <div key={li} style={lineStyle(fit)}>{parts}</div>;
          })}
        </FitAlarm>
        {missing ? <div style={{ display: "inline-block", marginTop: 10, background: "#B00020", color: "#FFFFFF", fontFamily: "Inter", fontWeight: 700, fontSize: 30,
          padding: "4px 12px", lineHeight: 1.2 }}>VURGU BULUNAMADI</div> : null}
      </div>
    </AbsoluteFill>
  );
};

export const MARK: Entry[] = [
  { name: "TextMark", category: "text", version: "1.0.0", schema: markSchema, Component: TextMark,
    demo: markSchema.parse({ text: "Örnek başlık İÇİNDE vurgu", mark: "içinde", mode: "circle" }) },
];
