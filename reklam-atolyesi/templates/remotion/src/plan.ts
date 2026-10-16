// edit_plan.json yükleyici ve zod şeması (spec 5.2). Yetkili doğrulama Python'dadır (admem.editplan; edit_plan_validate);
// bu şema render girdisinin biçimini korur. Geçersiz plan render edilmez.
import { z } from "zod";

export const zSource = z.object({
  kind: z.enum(["footage", "ai_clip", "ai_image", "still", "graphic"]),
  asset: z.string().optional(),
  path: z.string().optional(),
  in_s: z.number().optional(),
  out_s: z.number().optional(),
});

export const zLayer = z.object({
  type: z.enum(["video", "image", "text", "component", "graphic", "audio"]),
  source: zSource.optional(),
  component: z.string().optional(),
  preset: z.string().optional(),
  props: z.record(z.string(), z.any()).optional(),
  text: z.string().optional(),
  anchor: z.string().optional(),
  start_s: z.number().optional(),
  dur_s: z.number().optional(),
  camera: z.object({ preset: z.string().optional(), zoom: z.number().optional() }).partial().optional(),
  review_id: z.number().optional(),
});

export const zScene = z.object({
  id: z.string(),
  role: z.enum(["hook", "context", "reveal", "product", "process", "demo", "proof", "offer", "endcard"]),
  start_s: z.number(),
  dur_s: z.number(),
  beat_lock: z.string().optional(),
  audio: z.object({ mode: z.enum(["original", "original_clean", "user_vo", "generated", "none"]) }).passthrough(),
  layers: z.array(zLayer),
  transition_out: z.object({ type: z.string(), dur_s: z.number() }).partial().optional(),
});

export const zPlan = z.object({
  format: z.enum(["9x16", "4x5", "1x1"]),
  purpose: z.enum(["style_preview", "production"]),
  status: z.enum(["draft", "ready"]),
  duration_s: z.number().positive(),
  fps: z.union([z.literal(30), z.literal(60)]),
  seed: z.number().optional(),
  scenes: z.array(zScene).min(1),
  captions: z.object({ on: z.boolean(), preset: z.string().optional() }).partial().nullable().optional(),
});

export type Plan = z.infer<typeof zPlan>;
export type Scene = z.infer<typeof zScene>;
export type Layer = z.infer<typeof zLayer>;

export const FORMAT_SIZE: Record<string, { width: number; height: number }> = {
  "9x16": { width: 1080, height: 1920 },
  "4x5": { width: 1080, height: 1350 },
  "1x1": { width: 1080, height: 1080 },
};

export const zMasterProps = z.object({
  plan: z.any(),
  style: z.any().optional(),
  // sahne kimliği → katman sırası → public/ altındaki ara dosya yolu (staticFile ile çözülür)
  assets: z.record(z.string(), z.record(z.string(), z.string())).optional(),
  captions: z.array(z.object({ text: z.string(), start: z.number(), end: z.number() })).optional(),
  preview: z.boolean().optional(),
  beats: z.array(z.number()).optional(),
});
export type MasterProps = z.infer<typeof zMasterProps>;

export const parsePlan = (p: unknown): Plan => zPlan.parse(p);
