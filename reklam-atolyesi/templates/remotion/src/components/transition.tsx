// Geçişler (spec 5.12): Crossfade, DipToColor, LightLeak, WhipPan, MaskReveal, MatchZoom, SlideBlur, FilmBurn.
// Master kompozisyonu sahne sınırında [sınır − d/2, sınır + d/2] penceresinde ilerlemeyi (p: 0→1) hesaplar;
// giden sahneye exit(p), gelen sahneye enter(p) stili uygulanır, gerekiyorsa üstte overlay çizilir.
// Pencere boyunca giden sahnenin son karesi / gelen sahnenin ilk karesi dondurulur (ara dosya sınırı aşılmaz).
import React from "react";
import { AbsoluteFill, random, useCurrentFrame, useVideoConfig } from "remotion";
import { z } from "zod";
import { clamp01, easeInOut, Entry } from "./types";
import { DemoPanel } from "./demo";

export type TransitionImpl = {
  exit: (p: number) => React.CSSProperties;
  enter: (p: number) => React.CSSProperties;
  Overlay?: React.FC<{ p: number; color: string; seed: number }>;
};

const Dip: React.FC<{ p: number; color: string }> = ({ p, color }) => (
  <AbsoluteFill style={{ background: color, opacity: 1 - Math.abs(p * 2 - 1) }} />
);
const Leak: React.FC<{ p: number; color: string }> = ({ p, color }) => {
  const a = Math.sin(Math.PI * clamp01(p));
  return (
    <AbsoluteFill style={{ mixBlendMode: "screen", opacity: a * 0.85,
      background: `radial-gradient(ellipse at ${20 + 60 * p}% 40%, ${color} 0%, rgba(255,255,255,0.0) 60%)` }} />
  );
};
const Burn: React.FC<{ p: number; color: string; seed: number }> = ({ p, color, seed }) => {
  const a = Math.sin(Math.PI * clamp01(p));
  const blobs = Array.from({ length: 5 }, (_, i) => ({ x: random(`${seed}-bx-${i}`) * 100, y: random(`${seed}-by-${i}`) * 100, r: 30 + random(`${seed}-br-${i}`) * 40 }));
  return (
    <AbsoluteFill style={{ mixBlendMode: "screen", opacity: a }}>
      {blobs.map((b, i) => (
        <AbsoluteFill key={i} style={{ background: `radial-gradient(circle at ${b.x}% ${b.y}%, ${color} 0%, rgba(0,0,0,0) ${b.r}%)` }} />
      ))}
      <AbsoluteFill style={{ background: "#FFFFFF", opacity: Math.max(0, a - 0.75) * 2 }} />
    </AbsoluteFill>
  );
};

export const TRANSITIONS: Record<string, TransitionImpl> = {
  cut: { exit: (p) => ({ opacity: p < 0.5 ? 1 : 0 }), enter: (p) => ({ opacity: p < 0.5 ? 0 : 1 }) },
  crossfade: { exit: () => ({}), enter: (p) => ({ opacity: easeInOut(p) }) },
  dipToColor: { exit: (p) => ({ opacity: p < 0.5 ? 1 : 0 }), enter: (p) => ({ opacity: p < 0.5 ? 0 : 1 }), Overlay: Dip },
  lightLeak: { exit: () => ({}), enter: (p) => ({ opacity: clamp01((p - 0.35) / 0.3) }), Overlay: Leak },
  whipPan: {
    exit: (p) => ({ transform: `translateX(${-easeInOut(p) * 100}%)`, filter: `blur(${Math.sin(Math.PI * p) * 18}px)` }),
    enter: (p) => ({ transform: `translateX(${(1 - easeInOut(p)) * 100}%)`, filter: `blur(${Math.sin(Math.PI * p) * 18}px)` }),
  },
  maskReveal: { exit: () => ({}), enter: (p) => ({ clipPath: `circle(${easeInOut(p) * 75}% at 50% 50%)` }) },
  matchZoom: {
    exit: (p) => ({ transform: `scale(${1 + 0.35 * easeInOut(p)})`, opacity: 1 - clamp01((p - 0.4) / 0.4) }),
    enter: (p) => ({ transform: `scale(${0.85 + 0.15 * easeInOut(p)})`, opacity: clamp01((p - 0.3) / 0.4) }),
  },
  slideBlur: {
    exit: (p) => ({ transform: `translateY(${-easeInOut(p) * 25}%)`, filter: `blur(${p * 14}px)`, opacity: 1 - clamp01(p) }),
    enter: (p) => ({ transform: `translateY(${(1 - easeInOut(p)) * 25}%)`, filter: `blur(${(1 - p) * 14}px)`, opacity: clamp01(p * 1.5) }),
  },
  filmBurn: { exit: (p) => ({ opacity: p < 0.5 ? 1 : 0 }), enter: (p) => ({ opacity: p < 0.5 ? 0 : 1 }), Overlay: Burn },
};

// Galeri/test bileşeni: iki sentetik panel arasında geçiş (2 sn testte ortadaki pencere).
// Demo penceresi 30 kare: galerinin 0,75 ve 1,25 sn kareleri geçişin ortasını (p≈0,25 ve 0,75) gösterir.
const schema = z.object({ type: z.string(), color: z.string().default("#FFFFFF"), durationFrames: z.number().default(30), seed: z.number().default(3) });
const makeDemo = (type: string): React.FC<z.infer<typeof schema>> => (p) => {
  const f = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const mid = Math.floor(durationInFrames / 2);
  const prog = clamp01((f - (mid - p.durationFrames / 2)) / p.durationFrames);
  const impl = TRANSITIONS[type] ?? TRANSITIONS.cut;
  const showA = prog < 1;
  const showB = prog > 0;
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      {showA ? <AbsoluteFill style={impl.exit(prog)}><DemoPanel label="Sahne A" tone={0} /></AbsoluteFill> : null}
      {showB ? <AbsoluteFill style={impl.enter(prog)}><DemoPanel label="Sahne B" tone={1} /></AbsoluteFill> : null}
      {impl.Overlay && prog > 0 && prog < 1 ? <impl.Overlay p={prog} color={p.color} seed={p.seed} /> : null}
    </AbsoluteFill>
  );
};

const names: [string, string, string][] = [
  ["Crossfade", "crossfade", "#FFFFFF"], ["DipToColor", "dipToColor", "#1F1F1F"], ["LightLeak", "lightLeak", "#FFFFFF"],
  ["WhipPan", "whipPan", "#FFFFFF"], ["MaskReveal", "maskReveal", "#FFFFFF"], ["MatchZoom", "matchZoom", "#FFFFFF"],
  ["SlideBlur", "slideBlur", "#FFFFFF"], ["FilmBurn", "filmBurn", "#BDBDBD"],
];
export const TRANSITION: Entry[] = names.map(([name, type, color]) => ({
  name, category: "transition", version: "1.0.0", schema, Component: makeDemo(type),
  demo: schema.parse({ type, color }),
}));
export const transitionKey = (name: string) => name[0].toLowerCase() + name.slice(1);
