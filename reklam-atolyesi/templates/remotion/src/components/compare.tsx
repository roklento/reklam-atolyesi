// Önce/sonra (1.8.0; proof=before_after). Kipler: wipe (kayan çizgi sonrayı açar), split (yan yana ya da üst alta), cut (etiketli düz
// geçiş, sürenin ortasında). İki kaynak da gerçek çekimdir (kind: footage); plan doğrulaması AI kaynağı, konseptte before_after seçilmemiş
// olmasını ve sağlık hizmeti sektörünü reddeder, ürün kategorisini (ref-legal-tr-meta §8d) ister. Renk eşitleme bu kaynaklara uygulanmaz:
// fark kanıtın kendisidir. Fikir kaynağı: RVE Image Comparison Slider, RemotionUI split-screen; kod sıfırdan yazıldı.
import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { z } from "zod";
import { FitAlarm, lineStyle, useFit } from "./fit";
import { Media, zSource } from "./media";
import { clamp01, easeInOut, easeOutCubic, Entry } from "./types";

const baSchema = z.object({ before: zSource, after: zSource,
  mode: z.enum(["wipe", "split", "cut"]).default("wipe"), orientation: z.enum(["vertical", "horizontal"]).default("vertical"),
  labelBefore: z.string().default("Önce"), labelAfter: z.string().default("Sonra"), showLabels: z.boolean().default(true),
  startFrame: z.number().int().min(0).default(12), dividerFrames: z.number().int().min(1).default(30), labelY: z.number().default(0.16),
  // ürün kategorisi (ref-legal-tr-meta §8d): plan doğrulaması okur; çizim etkilenmez
  category: z.enum(["general", "cosmetic", "weight", "health_claim", "skin_whitening"]).nullable().default(null),
  ink: z.string().default("#FFFFFF"), chip: z.string().default("rgba(0,0,0,0.55)"), fontFamily: z.string().default("Inter") });

const Label: React.FC<{ text: string; align: "left" | "right" | "center"; top: number; fontFamily: string; ink: string; chip: string; opacity: number;
  inset: string }> = (p) => {
  const { width } = useVideoConfig();
  const fit = useFit({ text: p.text, fontFamily: p.fontFamily, fontWeight: 700, fontSize: 48, minFontSize: 32, boxWidth: width * 0.4 - 48, maxLines: 1 },
    { component: "BeforeAfter", part: "label", y: p.top, mode: "top", lineHeight: 1.2, padY: 20 });
  if (!p.text) return null;
  const side: React.CSSProperties = p.align === "left" ? { left: p.inset } : p.align === "right" ? { right: p.inset } : { left: "50%", transform: "translateX(-50%)" };
  return (
    <div style={{ position: "absolute", top: `${p.top * 100}%`, ...side, opacity: p.opacity, background: p.chip, color: p.ink, fontFamily: p.fontFamily,
      fontWeight: 700, fontSize: fit.fontSize, lineHeight: 1.2, padding: "10px 24px", borderRadius: 999 }}>
      <FitAlarm on={!fit.fits}>{fit.lines.map((ln, i) => <div key={i} style={lineStyle(fit)}>{ln}</div>)}</FitAlarm>
    </div>
  );
};

const BeforeAfter: React.FC<z.infer<typeof baSchema>> = (p) => {
  const f = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const lab = { fontFamily: p.fontFamily, ink: p.ink, chip: p.chip, inset: "6%" };
  const before = <Media src={p.before} placeholder="Önce örneği" tone={1} />;
  const after = <Media src={p.after} placeholder="Sonra örneği" />;
  const vertical = p.orientation === "vertical";

  if (p.mode === "split") {
    const a = easeOutCubic((f - p.startFrame) / 12);
    const half = (first: boolean): React.CSSProperties => vertical
      ? { position: "absolute", top: 0, bottom: 0, width: "50%", left: first ? 0 : "50%", overflow: "hidden" }
      : { position: "absolute", left: 0, right: 0, height: "50%", top: first ? 0 : "50%", overflow: "hidden" };
    return (
      <AbsoluteFill style={{ background: "#000" }}>
        <div style={half(true)}>{before}</div>
        <div style={half(false)}>{after}</div>
        <div style={vertical ? { position: "absolute", left: "50%", top: 0, bottom: 0, width: 6, marginLeft: -3, background: p.ink }
          : { position: "absolute", top: "50%", left: 0, right: 0, height: 6, marginTop: -3, background: p.ink }} />
        {p.showLabels ? (vertical ? <>
          <Label text={p.labelBefore} align="left" top={p.labelY} opacity={a} {...lab} />
          <Label text={p.labelAfter} align="right" top={p.labelY} opacity={a} {...lab} />
        </> : <>
          <Label text={p.labelBefore} align="center" top={p.labelY} opacity={a} {...lab} />
          <Label text={p.labelAfter} align="center" top={0.5 + 0.03} opacity={a} {...lab} />
        </>) : null}
      </AbsoluteFill>
    );
  }

  if (p.mode === "cut") {
    const cutAt = Math.round(durationInFrames / 2);
    const isAfter = f >= cutAt;
    const a = easeOutCubic((isAfter ? f - cutAt : f) / 8);
    return (
      <AbsoluteFill style={{ background: "#000" }}>
        {isAfter ? after : before}
        {p.showLabels ? <Label text={isAfter ? p.labelAfter : p.labelBefore} align="left" top={p.labelY} opacity={a} {...lab} /> : null}
      </AbsoluteFill>
    );
  }

  // wipe: çizgi soldan sağa (dikey) ya da yukarıdan aşağı (yatay) ilerler; geçtiği yerde "sonra" görünür
  const t = easeInOut(clamp01((f - p.startFrame) / p.dividerFrames));
  const pos = t * 100;
  const clip = vertical ? `inset(0 ${100 - pos}% 0 0)` : `inset(0 0 ${100 - pos}% 0)`;
  const la = easeOutCubic(f / 8);
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      {before}
      <AbsoluteFill style={{ clipPath: clip, WebkitClipPath: clip }}>{after}</AbsoluteFill>
      {t > 0 && t < 1 ? <div style={vertical
        ? { position: "absolute", top: 0, bottom: 0, left: `${pos}%`, width: 6, marginLeft: -3, background: p.ink, boxShadow: "0 0 18px rgba(0,0,0,0.45)" }
        : { position: "absolute", left: 0, right: 0, top: `${pos}%`, height: 6, marginTop: -3, background: p.ink, boxShadow: "0 0 18px rgba(0,0,0,0.45)" }} /> : null}
      {p.showLabels ? <>
        <Label text={p.labelBefore} align="right" top={p.labelY} opacity={la * (1 - clamp01((t - 0.75) / 0.25))} {...lab} />
        <Label text={p.labelAfter} align="left" top={p.labelY} opacity={clamp01((t - 0.2) / 0.3)} {...lab} />
      </> : null}
    </AbsoluteFill>
  );
};

export const COMPARE: Entry[] = [
  { name: "BeforeAfter", category: "proof", version: "1.0.0", schema: baSchema, Component: BeforeAfter, demo: baSchema.parse({ category: "general" }) },
];
