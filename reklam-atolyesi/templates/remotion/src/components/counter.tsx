// Rakam sayacı (1.8.0): sayı 0'dan (ya da fromValue'dan) hedefe sayar; isteğe bağlı hane dönmesi. Biçim Intl.NumberFormat(locale);
// yer en uzun (son) değere göre baştan ayrılır, sayarken yazı kaymaz. Değer ya fiyattır (kind: "price", para birimi zorunlu; PriceTag
// kuralı) ya da kanıtlanabilir iddia listesindeki bir sayıdır (kind: "claim", claimIndex ya da claimRef → products.provable_claims_json). İkisi de
// değilse plan doğrulaması reddeder; render'da da kırmızı işaret çizilir. Fikir kaynağı: RemotionUI counter; kod sıfırdan yazıldı.
import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { z } from "zod";
import { FitAlarm, lineStyle, useFit } from "./fit";
import { clamp01, easeOutCubic, Entry } from "./types";

const rollSchema = z.object({ value: z.number().nullable(), kind: z.enum(["price", "claim"]).nullable().default(null),
  currency: z.string().nullable().default(null), claimIndex: z.number().int().min(0).nullable().default(null), claimRef: z.string().nullable().default(null),
  fromValue: z.number().default(0), decimals: z.number().int().min(0).max(3).nullable().default(null), prefix: z.string().default(""),
  suffix: z.string().default(""), label: z.string().default(""), roll: z.boolean().default(false), locale: z.string().default("tr-TR"),
  startFrame: z.number().int().min(0).default(4), countFrames: z.number().int().min(1).default(30), y: z.number().default(0.4),
  fontSize: z.number().default(160), minFontSize: z.number().default(72), color: z.string().default("#1F1F1F"), fontFamily: z.string().default("Inter") });

const decimalsOf = (v: number) => (Number.isInteger(v) ? 0 : Math.min(3, (String(v).split(".")[1] ?? "").length));

export const formatNumber = (v: number, locale: string, decimals: number) =>
  new Intl.NumberFormat(locale, { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(v);

/** Hane dönmesi: her rakam 0–9 şeridinde hedef rakama kayar; sağdaki haneler biraz daha geç oturur. */
const RollDigits: React.FC<{ text: string; progress: number }> = ({ text, progress }) => {
  const chars = Array.from(text);
  const digits = chars.filter((c) => /\d/.test(c)).length;
  let k = 0;
  return (
    <>
      {chars.map((c, i) => {
        if (!/\d/.test(c)) return <span key={i}>{c}</span>;
        const order = k++;
        const local = clamp01(progress * 1.25 - (order / Math.max(1, digits)) * 0.25);
        const pos = Number(c) * easeOutCubic(local);
        return (
          <span key={i} style={{ display: "inline-block", height: "1.1em", overflow: "hidden", verticalAlign: "top" }}>
            <span style={{ display: "block", transform: `translateY(${-pos * 1.1}em)` }}>
              {"0123456789".split("").map((d) => <span key={d} style={{ display: "block", height: "1.1em" }}>{d}</span>)}
            </span>
          </span>
        );
      })}
    </>
  );
};

const NumberRoll: React.FC<z.infer<typeof rollSchema>> = (p) => {
  const f = useCurrentFrame();
  const { width } = useVideoConfig();
  const missing = p.value === null || p.kind === null || (p.kind === "price" && !p.currency) || (p.kind === "claim" && p.claimIndex === null && !p.claimRef);
  const value = p.value ?? 0;
  const dec = p.decimals ?? decimalsOf(value);
  const suffix = p.kind === "price" && p.currency ? `${p.suffix} ${p.currency}` : p.suffix;
  const finalText = `${p.prefix}${formatNumber(value, p.locale, dec)}${suffix}`;
  const fit = useFit({ text: finalText, fontFamily: p.fontFamily, fontWeight: 700, fontSize: p.fontSize, minFontSize: p.minFontSize, boxWidth: width * 0.88,
    maxLines: 1 }, { component: "NumberRoll", part: "value", y: p.y, mode: "center", lineHeight: 1.1 });
  const lf = useFit({ text: p.label, fontFamily: p.fontFamily, fontWeight: 400, fontSize: 44, minFontSize: 30, boxWidth: width * 0.88, maxLines: 2 },
    { component: "NumberRoll", part: "label", y: p.y, mode: "center", lineHeight: 1.2 });
  const t = easeOutCubic(clamp01((f - p.startFrame) / p.countFrames));
  const a = easeOutCubic(f / 8);
  if (missing) {
    return (
      <AbsoluteFill style={{ alignItems: "center" }}>
        <div style={{ position: "absolute", top: `${p.y * 100}%`, transform: "translateY(-50%)", background: "#B00020", color: "#FFFFFF", fontFamily: "Inter",
          fontWeight: 700, fontSize: 44, padding: "14px 28px" }}>SAYI KANITI/FİYAT YOK</div>
      </AbsoluteFill>
    );
  }
  const current = p.fromValue + (value - p.fromValue) * t;
  const shownText = p.roll ? finalText : `${p.prefix}${formatNumber(t >= 1 ? value : current, p.locale, dec)}${suffix}`;
  return (
    <AbsoluteFill style={{ alignItems: "center" }}>
      <div style={{ position: "absolute", top: `${p.y * 100}%`, transform: "translateY(-50%)", textAlign: "center", fontFamily: p.fontFamily, color: p.color,
        opacity: a, width: "88%" }}>
        <FitAlarm on={!fit.fits}>
          {/* yer son değerle ayrılır (görünmez kopya); sayan metin üstüne ortalanır */}
          <div style={{ position: "relative", display: "inline-block", fontSize: fit.fontSize, fontWeight: 700, lineHeight: 1.1, fontVariantNumeric: "tabular-nums",
            whiteSpace: "nowrap" }}>
            <span style={{ visibility: "hidden" }}>{finalText}</span>
            <span style={{ position: "absolute", left: 0, right: 0, top: 0, textAlign: "center" }}>
              {p.roll ? <RollDigits text={shownText} progress={t} /> : shownText}
            </span>
          </div>
        </FitAlarm>
        {p.label ? <div style={{ fontSize: lf.fontSize, lineHeight: 1.2, marginTop: 10 }}>
          <FitAlarm on={!lf.fits}>{lf.lines.map((ln, i) => <div key={i} style={lineStyle(lf)}>{ln}</div>)}</FitAlarm></div> : null}
      </div>
    </AbsoluteFill>
  );
};

export const COUNTER: Entry[] = [
  { name: "NumberRoll", category: "proof", version: "1.0.0", schema: rollSchema, Component: NumberRoll,
    demo: rollSchema.parse({ value: 1250, kind: "claim", claimIndex: 0, suffix: " adet", label: "Örnek kanıtlı sayı" }) },
];
