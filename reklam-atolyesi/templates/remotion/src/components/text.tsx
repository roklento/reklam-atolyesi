// Yazı bileşenleri (spec 5.12): TextReveal, KineticWords, SoftType, LowerThird, PriceTag, CaptionTrack.
// Bütün animasyonlar useCurrentFrame()'den türetilir; CSS geçişi/zamanlayıcı/Math.random yok.
// 1.6.0: TextReveal, KineticWords, SoftType, LowerThird ve PriceTag etiketi satırlarını gerçek ölçümle kurar (fit.tsx): yazı kutuya
// ve maxLines'a sığana dek fontSize'dan minFontSize'a küçülür; sığmıyorsa "YAZI SIĞMIYOR" çerçevesi çizilir.
import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { z } from "zod";
import { FitAlarm, FitSpec, lineStyle, useFit } from "./fit";
import { clamp01, easeOutCubic, Entry } from "./types";

const base = z.object({
  color: z.string().default("#1F1F1F"),
  fontFamily: z.string().default("Inter"),
  fontWeight: z.number().default(700),
  fontSize: z.number().default(88),
  minFontSize: z.number().default(52),  // sığdırırken inilebilecek en küçük boy (1.6.0)
  maxLines: z.number().int().min(1).default(3),
  y: z.number().min(0).max(1).default(0.14),
  align: z.enum(["left", "center", "right"]).default("center"),
});
type Base = z.infer<typeof base>;
// textBlock kutusu: soldan/sağdan %6 → iç genişlik bileşen genişliğinin %88'i
const blockSpec = (p: Base & { text: string }, W: number, fontWeight = p.fontWeight, reserve = 0): FitSpec => ({ text: p.text,
  fontFamily: p.fontFamily, fontWeight, fontSize: p.fontSize, minFontSize: p.minFontSize, boxWidth: W * 0.88 - reserve, maxLines: p.maxLines,
  letterSpacing: "-0.01em" });
const NBSP = "\u00a0";

const textBlock = (p: { y: number; align: string; fontFamily: string; fontWeight: number; fontSize: number; color: string }): React.CSSProperties => ({
  position: "absolute", left: "6%", right: "6%", top: `${p.y * 100}%`, textAlign: p.align as React.CSSProperties["textAlign"],
  fontFamily: p.fontFamily, fontWeight: p.fontWeight, fontSize: p.fontSize, color: p.color, lineHeight: 1.12, letterSpacing: "-0.01em",
});

// --- TextReveal: satır satır maske açılışı
const textRevealSchema = base.extend({ text: z.string(), revealFrames: z.number().default(14), staggerFrames: z.number().default(5) });
const TextReveal: React.FC<z.infer<typeof textRevealSchema>> = (p) => {
  const f = useCurrentFrame();
  const { width } = useVideoConfig();
  const fit = useFit(blockSpec(p, width), { component: "TextReveal", y: p.y, lineHeight: 1.12 });
  return (
    <AbsoluteFill>
      <div style={{ ...textBlock(p), fontSize: fit.fontSize }}>
        <FitAlarm on={!fit.fits}>
          {fit.lines.map((ln, i) => {
            const t = easeOutCubic((f - i * p.staggerFrames) / p.revealFrames);
            return (
              <div key={i} style={{ overflow: "hidden" }}>
                <div style={{ transform: `translateY(${(1 - t) * 110}%)`, opacity: clamp01(t * 1.4), ...lineStyle(fit) }}>{ln || NBSP}</div>
              </div>
            );
          })}
        </FitAlarm>
      </div>
    </AbsoluteFill>
  );
};

// --- KineticWords: kelime kelime
const kineticSchema = base.extend({ text: z.string(), framesPerWord: z.number().default(6), emphasis: z.array(z.number()).default([]),
  emphasisColor: z.string().default("#6B6B6B") });
const KineticWords: React.FC<z.infer<typeof kineticSchema>> = (p) => {
  const f = useCurrentFrame();
  const { width } = useVideoConfig();
  const fit = useFit(blockSpec(p, width), { component: "KineticWords", y: p.y, lineHeight: 1.12 });
  let idx = 0;  // vurgu dizini metnin bütün sözcükleri üzerinden sayılır
  return (
    <AbsoluteFill>
      <div style={{ ...textBlock(p), fontSize: fit.fontSize }}>
        <FitAlarm on={!fit.fits}>
          {fit.lines.map((ln, li) => (
            <div key={li} style={lineStyle(fit)}>
              {ln.split(/\s+/).filter(Boolean).map((w, wi) => {
                const i = idx++;
                const t = easeOutCubic((f - i * p.framesPerWord) / 8);
                return (
                  <React.Fragment key={wi}>
                    {wi > 0 ? " " : null}
                    <span style={{ display: "inline-block", opacity: t, transform: `translateY(${(1 - t) * 30}px) scale(${0.92 + 0.08 * t})`,
                      color: p.emphasis.includes(i) ? p.emphasisColor : p.color }}>{w}</span>
                  </React.Fragment>
                );
              })}
              {ln ? null : NBSP}
            </div>
          ))}
        </FitAlarm>
      </div>
    </AbsoluteFill>
  );
};

// --- SoftType: yavaş daktilo
const softTypeSchema = base.extend({ text: z.string(), charsPerSecond: z.number().default(18), cursor: z.boolean().default(true) });
const SoftType: React.FC<z.infer<typeof softTypeSchema>> = (p) => {
  const f = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const weight = Math.min(p.fontWeight, 500);
  const fit = useFit(blockSpec(p, width, weight, p.cursor ? p.fontSize * 0.6 : 0), { component: "SoftType", y: p.y, lineHeight: 1.12 });
  const lines = fit.lines.map((ln) => Array.from(ln));
  const total = lines.reduce((a, l) => a + l.length, 0) + Math.max(0, lines.length - 1);
  const n = Math.min(total, Math.floor((f / fps) * p.charsPerSecond));
  const blink = Math.floor(f / (fps / 2)) % 2 === 0;
  // satırlar baştan yerinde durur (blok boyu yazarken değişmez); imleç o an yazılan satırdadır
  let left = n;
  let cursorDone = false;
  return (
    <AbsoluteFill>
      <div style={{ ...textBlock({ ...p, fontWeight: weight }), fontSize: fit.fontSize }}>
        <FitAlarm on={!fit.fits}>
          {lines.map((cs, i) => {
            const shown = cs.slice(0, Math.max(0, left)).join("");
            const here = !cursorDone && (left <= cs.length || i === lines.length - 1);
            if (here) cursorDone = true;
            left -= cs.length + 1;
            return (
              <div key={i} style={lineStyle(fit)}>
                {shown || (here ? null : NBSP)}
                {p.cursor && here ? <span style={{ opacity: blink ? 1 : 0 }}>▍</span> : null}
              </div>
            );
          })}
        </FitAlarm>
      </div>
    </AbsoluteFill>
  );
};

// --- LowerThird
const lowerThirdSchema = z.object({ title: z.string(), subtitle: z.string().default(""), color: z.string().default("#1F1F1F"),
  bg: z.string().default("rgba(230,230,230,0.92)"), accent: z.string().default("#6B6B6B"), fontFamily: z.string().default("Inter"), y: z.number().default(0.62),
  minFontSize: z.number().default(36) });  // başlık için; alt başlık aynı oranda (1.6.0)
const LowerThird: React.FC<z.infer<typeof lowerThirdSchema>> = (p) => {
  const f = useCurrentFrame();
  const { width } = useVideoConfig();
  const t = easeOutCubic(f / 12);
  const box = width * 0.88 - 70;  // en çok %88 genişlik; iç boşluk 2×30 + sol şerit 10
  const tf = useFit({ text: p.title, fontFamily: p.fontFamily, fontWeight: 700, fontSize: 54, minFontSize: p.minFontSize, boxWidth: box, maxLines: 2 },
    { component: "LowerThird", part: "title", y: p.y, lineHeight: 1.2, padY: 44 });
  const sf = useFit({ text: p.subtitle, fontFamily: p.fontFamily, fontWeight: 400, fontSize: 36, minFontSize: Math.round((p.minFontSize * 36) / 54),
    boxWidth: box, maxLines: 2 }, { component: "LowerThird", part: "subtitle", y: p.y, lineHeight: 1.2 });
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: "6%", maxWidth: "88%", boxSizing: "border-box", top: `${p.y * 100}%`, transform: `translateX(${(1 - t) * -60}px)`, opacity: t,
        background: p.bg, padding: "22px 30px", borderLeft: `10px solid ${p.accent}`, fontFamily: p.fontFamily, color: p.color }}>
        <FitAlarm on={!tf.fits || !sf.fits}>
          <div style={{ fontSize: tf.fontSize, fontWeight: 700, lineHeight: 1.2 }}>{tf.lines.map((ln, i) => <div key={i} style={lineStyle(tf)}>{ln}</div>)}</div>
          {p.subtitle ? <div style={{ fontSize: sf.fontSize, fontWeight: 400, opacity: 0.85, lineHeight: 1.2 }}>
            {sf.lines.map((ln, i) => <div key={i} style={lineStyle(sf)}>{ln}</div>)}</div> : null}
        </FitAlarm>
      </div>
    </AbsoluteFill>
  );
};

// --- PriceTag: satış sayfasıyla aynı fiyat kuralı (bölüm 10). Para birimi zorunlu; çizili fiyat yalnızca referans fiyat kanıtlıysa.
const priceTagSchema = z.object({ price: z.number().nullable(), currency: z.string().nullable(), referencePrice: z.number().nullable().default(null),
  referencePriceVerified: z.boolean().default(false), label: z.string().default(""), color: z.string().default("#1F1F1F"),
  bg: z.string().default("#E6E6E6"), fontFamily: z.string().default("Inter"), x: z.number().default(0.5), y: z.number().default(0.7),
  // Sayı biçimi profilin dilinden/para biriminden gelir (plan prop'u); varsayılan userConfig dil varsayılanıyla (tr) aynıdır.
  locale: z.string().default("tr-TR"), labelMinFontSize: z.number().default(24) });
const fmt = (v: number, locale: string) => v.toLocaleString(locale, { minimumFractionDigits: v % 1 ? 2 : 0, maximumFractionDigits: 2 });
const PriceTag: React.FC<z.infer<typeof priceTagSchema>> = (p) => {
  const f = useCurrentFrame();
  const { width } = useVideoConfig();
  const t = easeOutCubic(f / 10);
  const missing = p.price === null || !p.currency;
  const lf = useFit({ text: p.label, fontFamily: p.fontFamily, fontWeight: 400, fontSize: 32, minFontSize: p.labelMinFontSize, boxWidth: width * 0.88 - 68,
    maxLines: 2 }, { component: "PriceTag", part: "label", y: p.y, mode: "center", lineHeight: 1.2 });
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: `${p.x * 100}%`, top: `${p.y * 100}%`, transform: `translate(-50%,-50%) scale(${0.85 + 0.15 * t})`,
        opacity: t, background: missing ? "#B00020" : p.bg, color: missing ? "#FFFFFF" : p.color, fontFamily: p.fontFamily, padding: "18px 34px",
        borderRadius: 14, textAlign: "center", maxWidth: "88%", boxSizing: "border-box" }}>
        {missing ? (
          <div style={{ fontSize: 40, fontWeight: 700 }}>FİYAT/PARA BİRİMİ YOK</div>
        ) : (
          <>
            {p.label ? <FitAlarm on={!lf.fits}><div style={{ fontSize: lf.fontSize, lineHeight: 1.2 }}>
              {lf.lines.map((ln, i) => <div key={i} style={lineStyle(lf)}>{ln}</div>)}</div></FitAlarm> : null}
            {p.referencePrice !== null && p.referencePriceVerified ? (
              <div style={{ fontSize: 34, textDecoration: "line-through", opacity: 0.7 }}>{fmt(p.referencePrice, p.locale)} {p.currency}</div>
            ) : null}
            <div style={{ fontSize: 72, fontWeight: 700 }}>{fmt(p.price as number, p.locale)} {p.currency}</div>
          </>
        )}
      </div>
    </AbsoluteFill>
  );
};

// --- CaptionTrack: kelime zamanlı altyazı (metin VO metniyle birebir; 5.14). Ön ayar (1.5.0): plain · keyword (parçada en fazla
// bir vurgu sözcüğü, vurgu rengiyle) · keyword_upper (aynı + Türkçe büyük harf: i → İ) · karaoke (o an söylenen sözcük vurgulu).
const zWord = z.object({ text: z.string(), start: z.number(), end: z.number() });
const captionSchema = z.object({ captions: z.array(z.object({ text: z.string(), start: z.number(), end: z.number(),
    words: z.array(zWord).optional(), emph: z.number().nullable().optional() })),
  color: z.string().default("#FFFFFF"), stroke: z.string().default("rgba(0,0,0,0.75)"), fontFamily: z.string().default("Inter"),
  fontSize: z.number().default(58), y: z.number().default(0.7), offsetS: z.number().default(0),
  preset: z.enum(["plain", "keyword", "keyword_upper", "karaoke"]).default("plain"), accent: z.string().default("#FFD84D") });
const trUpper = (s: string) => s.toLocaleUpperCase("tr-TR");
// Vurgu rengi koyuysa (görece parlaklık < 0,3) beyaz yazı ve koyu kontur üstünde seçilmez: okunur sarıya düşülür.
const luminance = (hex: string) => {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return 1;
  const c = [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
};
const readableAccent = (hex: string) => (luminance(hex) < 0.3 ? "#FFD84D" : hex);
const CaptionTrack: React.FC<z.infer<typeof captionSchema>> = (p) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = f / fps + p.offsetS;
  const c = p.captions.find((x) => t >= x.start && t < x.end);
  if (!c) return null;
  const k = clamp01((t - c.start) * 8);
  const upper = p.preset === "keyword_upper";
  const words = c.words && c.words.length ? c.words : null;
  const accent = readableAccent(p.accent);
  const hot = (i: number, w: { start: number; end: number }) =>
    p.preset === "karaoke" ? t >= w.start && t < Math.max(w.end, w.start + 0.12) : (p.preset !== "plain" && c.emph === i);
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: "8%", right: "8%", top: `${p.y * 100}%`, textAlign: "center", fontFamily: p.fontFamily,
        fontWeight: 700, fontSize: p.fontSize, color: p.color, WebkitTextStroke: `2px ${p.stroke}`, opacity: k, lineHeight: 1.15,
        transform: `translateY(${(1 - k) * 8}px)` }}>
        {words && p.preset !== "plain"
          ? words.map((w, i) => {
              const on = hot(i, w);
              return (
                <span key={i} style={{ color: on ? accent : p.color, display: "inline-block",
                  transform: on && p.preset !== "karaoke" ? "scale(1.08)" : undefined, margin: "0 0.12em" }}>
                  {upper ? trUpper(w.text) : w.text}
                </span>
              );
            })
          : (upper ? trUpper(c.text) : c.text)}
      </div>
    </AbsoluteFill>
  );
};

export const TEXT: Entry[] = [
  { name: "TextReveal", category: "text", version: "1.1.0", schema: textRevealSchema, Component: TextReveal,
    demo: textRevealSchema.parse({ text: "Örnek başlık\nğüşiöç İĞÜŞÇÖ" }) },
  { name: "KineticWords", category: "text", version: "1.1.0", schema: kineticSchema, Component: KineticWords,
    demo: kineticSchema.parse({ text: "Örnek metin kelime kelime açılır", emphasis: [1] }) },
  { name: "SoftType", category: "text", version: "1.1.0", schema: softTypeSchema, Component: SoftType,
    demo: softTypeSchema.parse({ text: "Örnek yazı yavaşça yazılır" }) },
  { name: "LowerThird", category: "text", version: "1.1.0", schema: lowerThirdSchema, Component: LowerThird,
    demo: lowerThirdSchema.parse({ title: "Marka A", subtitle: "Örnek alt başlık" }) },
  { name: "PriceTag", category: "text", version: "1.1.0", schema: priceTagSchema, Component: PriceTag,
    demo: priceTagSchema.parse({ price: 100, currency: "PB", label: "Örnek fiyat" }) },
  { name: "CaptionTrack", category: "text", version: "1.0.0", schema: captionSchema, Component: CaptionTrack,
    demo: captionSchema.parse({ preset: "keyword", captions: [
      { text: "Örnek altyazı bir", start: 0, end: 1, emph: 1, words: [{ text: "Örnek", start: 0, end: 0.3 }, { text: "altyazı", start: 0.3, end: 0.7 }, { text: "bir", start: 0.7, end: 1 }] },
      { text: "İğne iplik iki", start: 1, end: 2, emph: 0, words: [{ text: "İğne", start: 1, end: 1.3 }, { text: "iplik", start: 1.3, end: 1.7 }, { text: "iki", start: 1.7, end: 2 }] }] }) },
];
