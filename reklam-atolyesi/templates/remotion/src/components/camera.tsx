// Kamera (spec 5.12): KenBurns, Parallax25D (maskeden 2.5D), FakeRackFocus, HandheldDrift (çok hafif).
// Kamera bileşenleri çocuk içeriği (video/görsel katmanı) sarar.
import React from "react";
import { AbsoluteFill, Img, random, useCurrentFrame, useVideoConfig } from "remotion";
import { z } from "zod";
import { clamp01, easeInOut, Entry } from "./types";
import { DemoPanel, DemoSubject } from "./demo";

// 1.8.0: focus {x, y} (0–1, kadrajdaki nokta) verilirse kamera o noktaya yaklaşır ve onu merkeze doğru taşır (kenar boşluğu açılmaz);
// settleFrames: hareket sahne bitmeden bu kadar kare önce durur ("kesimden önce otur"). İkisi de yoksa davranış 1.0.0 ile aynı.
const kbSchema = z.object({ fromScale: z.number().default(1.0), toScale: z.number().default(1.15), fromX: z.number().default(0), toX: z.number().default(-2),
  fromY: z.number().default(0), toY: z.number().default(-1.5), focus: z.object({ x: z.number().min(0).max(1), y: z.number().min(0).max(1) }).nullable().default(null),
  settleFrames: z.number().int().min(0).default(0) });
export const kenBurnsTransform = (p: z.infer<typeof kbSchema>, t: number): string => {
  const s = p.fromScale + (p.toScale - p.fromScale) * t;
  if (!p.focus) {
    const x = p.fromX + (p.toX - p.fromX) * t;
    const y = p.fromY + (p.toY - p.fromY) * t;
    return `scale(${s}) translate(${x}%, ${y}%)`;
  }
  // ölçek s'de görüntü her yandan (s-1)/2 taşar; odak merkeze en çok bu pay kadar taşınır (çerçeve dışı görünmez)
  const room = (s - 1) / (2 * s) * 100;
  const cl = (v: number) => Math.max(-room, Math.min(room, v));
  const x = cl((0.5 - p.focus.x) * 100 * t);
  const y = cl((0.5 - p.focus.y) * 100 * t);
  return `scale(${s}) translate(${x}%, ${y}%)`;
};
export const KenBurns: React.FC<z.input<typeof kbSchema> & { children?: React.ReactNode }> = (p) => {
  const f = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const p2 = kbSchema.parse(p);
  const moving = Math.max(1, durationInFrames - 1 - p2.settleFrames);
  const t = easeInOut(Math.min(1, f / moving));
  return <AbsoluteFill style={{ transform: kenBurnsTransform(p2, t) }}>{p.children ?? <DemoPanel />}</AbsoluteFill>;
};

const parallaxSchema = z.object({ background: z.string().nullable().default(null), foreground: z.string().nullable().default(null),
  depth: z.number().default(3), zoom: z.number().default(1.06) });
export const Parallax25D: React.FC<z.infer<typeof parallaxSchema>> = (p) => {
  const f = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const t = easeInOut(f / Math.max(1, durationInFrames - 1));
  const bg = { transform: `scale(${p.zoom}) translateX(${-p.depth * t}%)` };
  const fg = { transform: `scale(${1 + (p.zoom - 1) * 1.6}) translateX(${p.depth * 1.5 * t}%)` };
  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      <AbsoluteFill style={bg}>{p.background ? <Img src={p.background} style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : <DemoPanel withProduct={false} label="" />}</AbsoluteFill>
      <AbsoluteFill style={fg}>{p.foreground ? <Img src={p.foreground} style={{ width: "100%", height: "100%", objectFit: "contain" }} /> : <DemoSubject />}</AbsoluteFill>
    </AbsoluteFill>
  );
};

const rackSchema = z.object({ fromBlur: z.number().default(10), toBlur: z.number().default(0), startFrame: z.number().default(4), durationFrames: z.number().default(24) });
export const FakeRackFocus: React.FC<z.infer<typeof rackSchema> & { children?: React.ReactNode }> = (p) => {
  const f = useCurrentFrame();
  const t = easeInOut((f - p.startFrame) / p.durationFrames);
  const b = p.fromBlur + (p.toBlur - p.fromBlur) * clamp01(t);
  return <AbsoluteFill style={{ filter: `blur(${b}px)` }}>{p.children ?? <DemoPanel />}</AbsoluteFill>;
};

const driftSchema = z.object({ amplitude: z.number().max(1.5).default(0.6), rotation: z.number().max(0.6).default(0.2), seed: z.number().default(21) });
export const HandheldDrift: React.FC<z.infer<typeof driftSchema> & { children?: React.ReactNode }> = (p) => {
  const f = useCurrentFrame();
  const n = (k: string, ff: number) => {
    const a = random(`${p.seed}-${k}-${Math.floor(ff / 20)}`);
    const b = random(`${p.seed}-${k}-${Math.floor(ff / 20) + 1}`);
    const t = (ff % 20) / 20;
    return (a + (b - a) * (0.5 - Math.cos(Math.PI * t) / 2)) * 2 - 1;
  };
  return (
    <AbsoluteFill style={{ transform: `scale(1.03) translate(${n("x", f) * p.amplitude}%, ${n("y", f) * p.amplitude}%) rotate(${n("r", f) * p.rotation}deg)` }}>
      {p.children ?? <DemoPanel />}
    </AbsoluteFill>
  );
};

export const CAMERA: Entry[] = [
  { name: "KenBurns", category: "camera", version: "1.1.0", schema: kbSchema, Component: KenBurns, demo: kbSchema.parse({}) },
  { name: "Parallax25D", category: "camera", version: "1.0.0", schema: parallaxSchema, Component: Parallax25D, demo: parallaxSchema.parse({}) },
  { name: "FakeRackFocus", category: "camera", version: "1.0.0", schema: rackSchema, Component: FakeRackFocus, demo: rackSchema.parse({}) },
  { name: "HandheldDrift", category: "camera", version: "1.0.0", schema: driftSchema, Component: HandheldDrift, demo: driftSchema.parse({}) },
];
