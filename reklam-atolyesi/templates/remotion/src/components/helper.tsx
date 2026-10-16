// Yardımcılar (spec 5.12, 5.19): SafeZoneGuide, BeatMarker — yalnızca önizleme; hazır üretim planında kullanılamaz.
import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { z } from "zod";
import { Entry } from "./types";
import { DemoPanel } from "./demo";

// Yazı güvenli alanı (5.19): 9:16 üst %14, alt %35, yanlar %6 · 4:5 üst/alt ~250 px, yanlar ~100 px · 1:1 kenarlardan pay
export const SAFE_ZONES: Record<string, { top: number; bottom: number; left: number; right: number }> = {
  "9x16": { top: 0.14, bottom: 0.35, left: 0.06, right: 0.06 },
  "4x5": { top: 250 / 1350, bottom: 250 / 1350, left: 100 / 1080, right: 100 / 1080 },
  "1x1": { top: 0.08, bottom: 0.08, left: 0.08, right: 0.08 },
};

const safeSchema = z.object({ format: z.enum(["9x16", "4x5", "1x1"]).default("9x16"), color: z.string().default("rgba(255,0,80,0.35)") });
const SafeZoneGuide: React.FC<z.infer<typeof safeSchema> & { children?: React.ReactNode }> = (p) => {
  const z0 = SAFE_ZONES[p.format];
  return (
    <AbsoluteFill>
      {p.children ?? <DemoPanel />}
      <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: `${z0.top * 100}%`, background: p.color }} />
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: `${z0.bottom * 100}%`, background: p.color }} />
      <div style={{ position: "absolute", top: 0, bottom: 0, left: 0, width: `${z0.left * 100}%`, background: p.color }} />
      <div style={{ position: "absolute", top: 0, bottom: 0, right: 0, width: `${z0.right * 100}%`, background: p.color }} />
    </AbsoluteFill>
  );
};

const beatSchema = z.object({ beats: z.array(z.number()).default([]), color: z.string().default("#FF0050"), flashFrames: z.number().default(3) });
const BeatMarker: React.FC<z.infer<typeof beatSchema>> = (p) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const hit = p.beats.some((b) => f >= Math.round(b * fps) && f < Math.round(b * fps) + p.flashFrames);
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", right: 30, top: 30, width: 60, height: 60, borderRadius: "50%", background: hit ? p.color : "rgba(0,0,0,0.25)" }} />
    </AbsoluteFill>
  );
};

export const HELPER: Entry[] = [
  { name: "SafeZoneGuide", category: "helper", version: "1.0.0", schema: safeSchema, Component: SafeZoneGuide, demo: safeSchema.parse({}), previewOnly: true },
  { name: "BeatMarker", category: "helper", version: "1.0.0", schema: beatSchema, Component: BeatMarker, demo: beatSchema.parse({ beats: [0.25, 0.75, 1.25, 1.75] }), previewOnly: true },
];
