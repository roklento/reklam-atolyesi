// <Composition> kayıtları (spec 5.12): Master-916, Master-45, Master-11 (Remotion kimliklerinde alt çizgi geçersizdir).
// Sabit kareler aynı kompozisyondan `--still <kare>` ile alınır. Gallery ve TurkishTest kurulum testleri içindir.
import React from "react";
import { Composition } from "remotion";
import { Gallery, TurkishTest, zGalleryProps } from "./Gallery";
import { Master } from "./Master";
import { FORMAT_SIZE, MasterProps, zMasterProps } from "./plan";

// Nötr örnek plan (yalnızca stüdyo önizlemesi; varlık içermez, "Örnek başlık" yer tutucuları).
const DEMO_PLAN = {
  campaign: "ornek", cycle_id: "c1", concept: "A", hook: "h1", format: "9x16", purpose: "style_preview", status: "draft", version: 1,
  duration_s: 3, fps: 30, style: "style.json", seed: 1,
  scenes: [
    { id: "s1", role: "hook", start_s: 0, dur_s: 1.5, audio: { mode: "none" }, layers: [{ type: "video", source: { kind: "footage" } }, { type: "text", preset: "text_reveal", text: "Örnek başlık" }],
      transition_out: { type: "crossfade", dur_s: 0.3 } },
    { id: "s2", role: "endcard", start_s: 1.5, dur_s: 1.5, audio: { mode: "none" }, layers: [{ type: "component", component: "EndCard", props: { brand: "Marka A", cta: "Örnek çağrı" } }] },
  ],
};

const masterMeta = (format: string) => async ({ props }: { props: MasterProps }) => {
  const plan = props.plan as { duration_s: number; fps: number; format: string };
  const size = FORMAT_SIZE[format];
  return { durationInFrames: Math.max(1, Math.round(plan.duration_s * plan.fps)), fps: plan.fps, width: size.width, height: size.height };
};

export const RemotionRoot: React.FC = () => (
  <>
    {(["9x16", "4x5", "1x1"] as const).map((fmt) => (
      <Composition key={fmt} id={`Master-${fmt.replace("x", "")}`} component={Master} schema={zMasterProps}
        width={FORMAT_SIZE[fmt].width} height={FORMAT_SIZE[fmt].height} fps={30} durationInFrames={90}
        defaultProps={{ plan: { ...DEMO_PLAN, format: fmt }, style: null, assets: {}, preview: true }}
        calculateMetadata={masterMeta(fmt)} />
    ))}
    <Composition id="Gallery" component={Gallery} schema={zGalleryProps} width={540} height={960} fps={30} durationInFrames={60}
      defaultProps={{ component: "TextReveal" }} />
    <Composition id="TurkishTest" component={TurkishTest} width={1080} height={1920} fps={30} durationInFrames={60} />
  </>
);
