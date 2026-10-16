// Işık ve atmosfer (spec 5.12): LightSheen, SoftGlow, Bokeh, Particles (tohumlu), GradeOverlay (gren, vinyet), LensFlareSoft.
// Kullanım efekt bütçesine tabidir (5.6): sahne boyu süren atmosfer efekti stil izin vermedikçe yok.
import React from "react";
import { AbsoluteFill, random, useCurrentFrame, useVideoConfig } from "remotion";
import { z } from "zod";
import { clamp01, easeInOut, Entry } from "./types";

const sheenSchema = z.object({ angle: z.number().default(25), width: z.number().default(0.18), intensity: z.number().default(0.55),
  startFrame: z.number().default(6), durationFrames: z.number().default(24), color: z.string().default("#FFFFFF") });
const LightSheen: React.FC<z.infer<typeof sheenSchema>> = (p) => {
  const f = useCurrentFrame();
  const t = easeInOut((f - p.startFrame) / p.durationFrames);
  if (t <= 0 || t >= 1) return null;
  const pos = -30 + t * 160;
  return (
    <AbsoluteFill style={{ mixBlendMode: "screen", pointerEvents: "none",
      background: `linear-gradient(${90 + p.angle}deg, rgba(255,255,255,0) ${pos - p.width * 100}%, ${p.color} ${pos}%, rgba(255,255,255,0) ${pos + p.width * 100}%)`,
      opacity: p.intensity }} />
  );
};

const glowSchema = z.object({ x: z.number().default(0.5), y: z.number().default(0.5), radius: z.number().default(0.45), color: z.string().default("#FFFFFF"),
  intensity: z.number().default(0.35), pulse: z.boolean().default(false) });
const SoftGlow: React.FC<z.infer<typeof glowSchema>> = (p) => {
  const f = useCurrentFrame();
  const k = p.pulse ? 0.85 + 0.15 * Math.sin(f / 9) : 1;
  return <AbsoluteFill style={{ mixBlendMode: "screen", opacity: p.intensity * k,
    background: `radial-gradient(circle at ${p.x * 100}% ${p.y * 100}%, ${p.color} 0%, rgba(0,0,0,0) ${p.radius * 100}%)`, filter: "blur(18px)" }} />;
};

const bokehSchema = z.object({ count: z.number().default(18), seed: z.number().default(11), color: z.string().default("#FFFFFF"),
  minSize: z.number().default(30), maxSize: z.number().default(120), opacity: z.number().default(0.3), drift: z.number().default(0.4) });
const Bokeh: React.FC<z.infer<typeof bokehSchema>> = (p) => {
  const f = useCurrentFrame();
  const { width, height } = useVideoConfig();
  return (
    <AbsoluteFill style={{ mixBlendMode: "screen" }}>
      {Array.from({ length: p.count }, (_, i) => {
        const s = p.minSize + random(`${p.seed}-s-${i}`) * (p.maxSize - p.minSize);
        const x = random(`${p.seed}-x-${i}`) * width + Math.sin(f / 40 + i) * p.drift * 20;
        const y = random(`${p.seed}-y-${i}`) * height - f * p.drift;
        return <div key={i} style={{ position: "absolute", left: x - s / 2, top: ((y % height) + height) % height - s / 2, width: s, height: s,
          borderRadius: "50%", background: `radial-gradient(circle, ${p.color} 0%, rgba(255,255,255,0) 70%)`,
          opacity: p.opacity * (0.5 + 0.5 * random(`${p.seed}-o-${i}`)), filter: "blur(2px)" }} />;
      })}
    </AbsoluteFill>
  );
};

const particlesSchema = z.object({ count: z.number().default(60), seed: z.number().default(5), color: z.string().default("#FFFFFF"),
  size: z.number().default(5), speed: z.number().default(1.2), opacity: z.number().default(0.6) });
const Particles: React.FC<z.infer<typeof particlesSchema>> = (p) => {
  const f = useCurrentFrame();
  const { width, height } = useVideoConfig();
  return (
    <AbsoluteFill>
      {Array.from({ length: p.count }, (_, i) => {
        const vx = (random(`${p.seed}-vx-${i}`) - 0.5) * p.speed * 2;
        const vy = -(0.3 + random(`${p.seed}-vy-${i}`)) * p.speed * 2;
        const x = (((random(`${p.seed}-x-${i}`) * width + vx * f) % width) + width) % width;
        const y = (((random(`${p.seed}-y-${i}`) * height + vy * f) % height) + height) % height;
        const s = p.size * (0.5 + random(`${p.seed}-s-${i}`));
        return <div key={i} style={{ position: "absolute", left: x, top: y, width: s, height: s, borderRadius: "50%", background: p.color,
          opacity: p.opacity * (0.4 + 0.6 * random(`${p.seed}-o-${i}`)) }} />;
      })}
    </AbsoluteFill>
  );
};

const gradeSchema = z.object({ grain: z.number().min(0).max(1).default(0), vignette: z.number().min(0).max(1).default(0), seed: z.number().default(9) });
const GradeOverlay: React.FC<z.infer<typeof gradeSchema>> = (p) => {
  const f = useCurrentFrame();
  const id = `g${p.seed}`;
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {p.grain > 0 ? (
        <svg width="100%" height="100%" style={{ position: "absolute", inset: 0, mixBlendMode: "overlay", opacity: p.grain }}>
          <filter id={id}><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed={(p.seed * 997 + f) % 10000} stitchTiles="stitch" /></filter>
          <rect width="100%" height="100%" filter={`url(#${id})`} />
        </svg>
      ) : null}
      {p.vignette > 0 ? <AbsoluteFill style={{ background: `radial-gradient(ellipse at center, rgba(0,0,0,0) 55%, rgba(0,0,0,${0.75 * p.vignette}) 100%)` }} /> : null}
    </AbsoluteFill>
  );
};

const flareSchema = z.object({ x: z.number().default(0.75), y: z.number().default(0.25), color: z.string().default("#FFFFFF"),
  intensity: z.number().default(0.45), startFrame: z.number().default(0), durationFrames: z.number().default(40) });
const LensFlareSoft: React.FC<z.infer<typeof flareSchema>> = (p) => {
  const f = useCurrentFrame();
  const t = clamp01((f - p.startFrame) / p.durationFrames);
  const a = Math.sin(Math.PI * t) * p.intensity;
  const ghosts = [0.3, 0.55, 0.8].map((k) => ({ x: p.x + (0.5 - p.x) * 2 * k, y: p.y + (0.5 - p.y) * 2 * k, r: 6 + 10 * k }));
  return (
    <AbsoluteFill style={{ mixBlendMode: "screen", opacity: a }}>
      <AbsoluteFill style={{ background: `radial-gradient(circle at ${p.x * 100}% ${p.y * 100}%, ${p.color} 0%, rgba(0,0,0,0) 28%)` }} />
      {ghosts.map((g, i) => <AbsoluteFill key={i} style={{ background: `radial-gradient(circle at ${g.x * 100}% ${g.y * 100}%, rgba(255,255,255,0.35) 0%, rgba(0,0,0,0) ${g.r}%)` }} />)}
    </AbsoluteFill>
  );
};

export const LIGHT: Entry[] = [
  { name: "LightSheen", category: "light", version: "1.0.0", schema: sheenSchema, Component: LightSheen, demo: sheenSchema.parse({}) },
  { name: "SoftGlow", category: "light", version: "1.0.0", schema: glowSchema, Component: SoftGlow, demo: glowSchema.parse({ pulse: true }) },
  { name: "Bokeh", category: "light", version: "1.0.0", schema: bokehSchema, Component: Bokeh, demo: bokehSchema.parse({}) },
  { name: "Particles", category: "light", version: "1.0.0", schema: particlesSchema, Component: Particles, demo: particlesSchema.parse({}) },
  { name: "GradeOverlay", category: "light", version: "1.0.0", schema: gradeSchema, Component: GradeOverlay, demo: gradeSchema.parse({ grain: 0.35, vignette: 0.6 }) },
  { name: "LensFlareSoft", category: "light", version: "1.0.0", schema: flareSchema, Component: LensFlareSoft, demo: flareSchema.parse({}) },
];
