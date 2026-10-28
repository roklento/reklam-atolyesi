// Ana kompozisyon: kurgu planını (edit_plan.json) çizer (spec 5.2, 5.12). Formatlar ayrı kompozisyondur; sahneler paylaşılır,
// yerleşim style.layout'tan gelir. Geçişlerde giden/gelen sahnenin sınır karesi dondurulur.
import React from "react";
import { AbsoluteFill, Freeze, Sequence, useCurrentFrame, useVideoConfig } from "remotion";
import { BY_NAME, TRANSITIONS } from "./components";
import type { MasterProps, Plan, Scene } from "./plan";
import { SCENE_TEMPLATES } from "./scenes";
import { fontFamiliesOf, resolveStyle, Style, useFontsReady } from "./style";

const tKey = (t?: string) => (t ? t[0].toLowerCase() + t.slice(1) : "cut");

const SceneSlot: React.FC<{ scene: Scene; style: Style; format: string; assets?: MasterProps["assets"]; preview?: boolean;
  pre: number; dur: number; post: number; inType: string; inFrames: number; outType: string; outFrames: number }> = (p) => {
  const f = useCurrentFrame();
  const sceneFrame = f - p.pre;
  const Tpl = SCENE_TEMPLATES[p.scene.role] ?? SCENE_TEMPLATES.product;
  let style: React.CSSProperties = {};
  if (p.inFrames > 0 && f < p.inFrames) {
    const impl = TRANSITIONS[tKey(p.inType)] ?? TRANSITIONS.cut;
    style = { ...style, ...impl.enter(f / p.inFrames) };
  }
  const outStart = p.pre + p.dur - Math.ceil(p.outFrames / 2);
  if (p.outFrames > 0 && f >= outStart) {
    const impl = TRANSITIONS[tKey(p.outType)] ?? TRANSITIONS.cut;
    style = { ...style, ...impl.exit((f - outStart) / p.outFrames) };
  }
  const freezeAt = sceneFrame < 0 ? 0 : sceneFrame >= p.dur ? p.dur - 1 : null;
  const inner = (
    <Sequence from={0} durationInFrames={p.dur} layout="none">
      <Tpl scene={p.scene} style={p.style} format={p.format} assets={p.assets} preview={p.preview} />
    </Sequence>
  );
  return (
    <AbsoluteFill style={style}>
      <Sequence from={p.pre} layout="none">
        {freezeAt !== null ? <Freeze frame={freezeAt}>{inner}</Freeze> : inner}
      </Sequence>
    </AbsoluteFill>
  );
};

export const Master: React.FC<MasterProps> = (props) => {
  const plan = props.plan as Plan;
  const style = resolveStyle(props.style);
  useFontsReady(fontFamiliesOf(style, plan), Array.from(new Set([400, 700, style.fonts.displayWeight])));
  const { fps } = useVideoConfig();
  const scenes = plan.scenes;
  const caption = BY_NAME["CaptionTrack"];
  const grade = BY_NAME["GradeOverlay"];
  return (
    <AbsoluteFill style={{ background: style.palette.bg }}>
      {scenes.map((s, i) => {
        const from = Math.round(s.start_s * fps);
        const dur = Math.max(1, Math.round(s.dur_s * fps));
        const prev = i > 0 ? scenes[i - 1].transition_out : undefined;
        const inFrames = prev && prev.type && prev.type !== "cut" ? Math.round((prev.dur_s ?? 0) * fps) : 0;
        const out = i < scenes.length - 1 ? s.transition_out : undefined;
        const outFrames = out && out.type && out.type !== "cut" ? Math.round((out.dur_s ?? 0) * fps) : 0;
        const pre = Math.ceil(inFrames / 2);
        const post = Math.ceil(outFrames / 2);
        return (
          <Sequence key={s.id} from={from - pre} durationInFrames={pre + dur + post} layout="none">
            <SceneSlot scene={s} style={style} format={plan.format} assets={props.assets} preview={props.preview}
              pre={pre} dur={dur} post={post} inType={prev?.type ?? "cut"} inFrames={inFrames} outType={out?.type ?? "cut"} outFrames={outFrames} />
          </Sequence>
        );
      })}
      {scenes.slice(0, -1).map((s, i) => {
        const t = s.transition_out;
        const impl = t?.type ? TRANSITIONS[tKey(t.type)] : undefined;
        if (!impl?.Overlay || !t?.dur_s) return null;
        const d = Math.round(t.dur_s * fps);
        const boundary = Math.round((s.start_s + s.dur_s) * fps);
        const Ov = impl.Overlay;
        return (
          <Sequence key={`ov-${i}`} from={boundary - Math.ceil(d / 2)} durationInFrames={d} layout="none">
            <OverlayClock d={d} render={(p) => <Ov p={p} color={style.palette.bg} seed={(plan.seed ?? 0) + i} />} />
          </Sequence>
        );
      })}
      {plan.captions?.on && props.captions?.length ? <caption.Component {...(caption.schema.parse({ captions: props.captions, fontFamily: style.fonts.body,
        preset: plan.captions?.preset ?? "plain", accent: style.captions?.accent ?? style.palette.accent }) as object)} /> : null}
      {(style.grade.grain > 0 || style.grade.vignette > 0) ? <grade.Component {...(grade.schema.parse({ grain: style.grade.grain, vignette: style.grade.vignette, seed: plan.seed ?? 9 }) as object)} /> : null}
    </AbsoluteFill>
  );
};

const OverlayClock: React.FC<{ d: number; render: (p: number) => React.ReactNode }> = ({ d, render }) => {
  const f = useCurrentFrame();
  return <>{render(Math.min(1, Math.max(0, f / Math.max(1, d))))}</>;
};
