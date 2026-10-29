// Ürün (spec 5.12): BehindSubjectText, Spotlight, OutlineGlow, StillTurn (fotoğraftan hafif dönüş hissi, AI yok).
// Maske/kesik (cutout) görselleri arka plan kaldırma çıktısıdır (birefnet; 5.10); yoksa sentetik özne gösterilir.
import React from "react";
import { AbsoluteFill, Img, useCurrentFrame, useVideoConfig } from "remotion";
import { z } from "zod";
import { clamp01, easeInOut, easeOutCubic, Entry } from "./types";
import { DemoPanel, DemoSubject } from "./demo";
import { FitAlarm, lineStyle, useFit } from "./fit";

const bstSchema = z.object({ text: z.string(), background: z.string().nullable().default(null), cutout: z.string().nullable().default(null),
  color: z.string().default("#FFFFFF"), fontFamily: z.string().default("Inter"), fontSize: z.number().default(220), y: z.number().default(0.32),
  minFontSize: z.number().default(120), maxLines: z.number().int().min(1).default(2) });
const BehindSubjectText: React.FC<z.infer<typeof bstSchema>> = (p) => {
  const f = useCurrentFrame();
  const { width } = useVideoConfig();
  const t = easeOutCubic(f / 14);
  const fit = useFit({ text: p.text, fontFamily: p.fontFamily, fontWeight: 700, fontSize: p.fontSize, minFontSize: p.minFontSize, boxWidth: width * 0.94,
    maxLines: p.maxLines, letterSpacing: "-0.02em" }, { component: "BehindSubjectText", y: p.y, lineHeight: 1.1 });
  return (
    <AbsoluteFill>
      {p.background ? <Img src={p.background} style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : <DemoPanel withProduct={false} label="" />}
      <div style={{ position: "absolute", left: 0, right: 0, top: `${p.y * 100}%`, textAlign: "center", fontFamily: p.fontFamily, fontWeight: 700,
        fontSize: fit.fontSize, color: p.color, opacity: t, transform: `translateY(${(1 - t) * 40}px)`, letterSpacing: "-0.02em", lineHeight: 1.1 }}>
        <FitAlarm on={!fit.fits}>{fit.lines.map((ln, i) => <div key={i} style={lineStyle(fit)}>{ln}</div>)}</FitAlarm>
      </div>
      {p.cutout ? <Img src={p.cutout} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "contain" }} /> : <DemoSubject />}
    </AbsoluteFill>
  );
};

const spotSchema = z.object({ x: z.number().default(0.5), y: z.number().default(0.5), radius: z.number().default(0.32), darkness: z.number().default(0.65),
  moveX: z.number().default(0.08) });
const Spotlight: React.FC<z.infer<typeof spotSchema> & { children?: React.ReactNode }> = (p) => {
  const f = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const t = easeInOut(f / Math.max(1, durationInFrames - 1));
  const x = (p.x - p.moveX / 2 + p.moveX * t) * 100;
  return (
    <AbsoluteFill>
      {p.children ?? <DemoPanel />}
      <AbsoluteFill style={{ background: `radial-gradient(circle at ${x}% ${p.y * 100}%, rgba(0,0,0,0) ${p.radius * 100}%, rgba(0,0,0,${p.darkness}) ${p.radius * 100 + 25}%)` }} />
    </AbsoluteFill>
  );
};

const outlineSchema = z.object({ cutout: z.string().nullable().default(null), color: z.string().default("#FFFFFF"), strength: z.number().default(14),
  startFrame: z.number().default(4), durationFrames: z.number().default(30) });
const OutlineGlow: React.FC<z.infer<typeof outlineSchema>> = (p) => {
  const f = useCurrentFrame();
  const a = Math.sin(Math.PI * clamp01((f - p.startFrame) / p.durationFrames));
  const filter = `drop-shadow(0 0 ${p.strength * a}px ${p.color}) drop-shadow(0 0 ${p.strength * a * 0.5}px ${p.color})`;
  return (
    <AbsoluteFill>
      {p.cutout ? <Img src={p.cutout} style={{ width: "100%", height: "100%", objectFit: "contain", filter }} /> : <AbsoluteFill style={{ filter }}><DemoSubject /></AbsoluteFill>}
    </AbsoluteFill>
  );
};

const turnSchema = z.object({ photo: z.string().nullable().default(null), degrees: z.number().max(14).default(9), sheen: z.boolean().default(false) });
const StillTurn: React.FC<z.infer<typeof turnSchema>> = (p) => {
  const f = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const t = easeInOut(f / Math.max(1, durationInFrames - 1));
  const deg = -p.degrees / 2 + p.degrees * t;
  return (
    <AbsoluteFill style={{ perspective: 1600, background: "#1F1F1F" }}>
      <AbsoluteFill style={{ transform: `rotateY(${deg}deg) scale(0.94)`, transformStyle: "preserve-3d" }}>
        {p.photo ? <Img src={p.photo} style={{ width: "100%", height: "100%", objectFit: "contain" }} /> : <DemoPanel />}
        {p.sheen ? <AbsoluteFill style={{ mixBlendMode: "screen", opacity: 0.35,
          background: `linear-gradient(105deg, rgba(255,255,255,0) ${t * 100 - 20}%, rgba(255,255,255,0.8) ${t * 100}%, rgba(255,255,255,0) ${t * 100 + 20}%)` }} /> : null}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

export const PRODUCT: Entry[] = [
  { name: "BehindSubjectText", category: "product", version: "1.1.0", schema: bstSchema, Component: BehindSubjectText, demo: bstSchema.parse({ text: "ÖRNEK" }) },
  { name: "Spotlight", category: "product", version: "1.0.0", schema: spotSchema, Component: Spotlight, demo: spotSchema.parse({}) },
  { name: "OutlineGlow", category: "product", version: "1.0.0", schema: outlineSchema, Component: OutlineGlow, demo: outlineSchema.parse({}) },
  { name: "StillTurn", category: "product", version: "1.0.0", schema: turnSchema, Component: StillTurn, demo: turnSchema.parse({ sheen: true }) },
];
