// Sahne rolü başına şablon (spec 5.2, 5.12): Hook, Context, Reveal, Product, Process, Demo, Proof, Offer, EndCard.
// Roller sabit ve ürün türünden bağımsızdır. Şablonlar katman yığınını çizer; role özgü tek fark varsayılan yazı yerleşimidir
// (yerleşim stil kitabının layout'undan gelir). Konsept açıları rol değil, konseptin konusudur.
import React from "react";
import { AbsoluteFill, Img, OffthreadVideo, Sequence, useVideoConfig } from "remotion";
import { layerAsset, assetUrl } from "../assets";
import { BY_NAME, SOURCE_PROPS, WRAPPERS } from "../components";
import { FakeRackFocus, HandheldDrift, KenBurns } from "../components/camera";
import { DemoPanel } from "../components/demo";
import type { Layer, Scene } from "../plan";
import type { Style } from "../style";
import { anchorY, componentY } from "../layout";

export type SceneProps = {
  scene: Scene;
  style: Style;
  format: string;
  assets?: Record<string, Record<string, string>>;
  preview?: boolean;
};

const TEXT_PRESETS: Record<string, string> = {
  text_reveal: "TextReveal", kinetic: "KineticWords", kinetic_words: "KineticWords", soft_type: "SoftType", lower_third: "LowerThird",
};

const withCamera = (node: React.ReactNode, cam: Layer["camera"], fps: number): React.ReactNode => {
  const preset = cam?.preset;
  const z = cam?.zoom ?? 1.0;
  const aim = { focus: cam?.focus ?? null, settleFrames: Math.round((cam?.settle_s ?? 0) * fps) };  // 1.8.0
  if (!preset || preset === "none" || preset === "static") return node;
  // konuşmalı kurguda kesik gizleme: aynı çekimin ardışık parçaları dönüşümlü sabit yakınlaştırma (asr_local.py cuts; 1.4.8)
  if (preset === "punch_in") return <KenBurns fromScale={Math.min(1.2, Math.max(1.0, z))} toScale={Math.min(1.2, Math.max(1.0, z))} fromX={0} toX={0} fromY={0} toY={0}>{node}</KenBurns>;
  if (preset === "kenburns_in") return <KenBurns fromScale={1} toScale={Math.max(1.0, z)} fromX={0} toX={-1.5} fromY={0} toY={-1} {...aim}>{node}</KenBurns>;
  if (preset === "kenburns_out") return <KenBurns fromScale={Math.max(1.0, z)} toScale={1} fromX={-1.5} toX={0} fromY={-1} toY={0} {...aim}>{node}</KenBurns>;
  if (preset === "handheld") return <HandheldDrift amplitude={0.5} rotation={0.15} seed={3}>{node}</HandheldDrift>;
  if (preset === "rack_focus") return <FakeRackFocus fromBlur={8} toBlur={0} startFrame={2} durationFrames={20}>{node}</FakeRackFocus>;
  return node;
};

const timed = (l: Layer, fps: number, node: React.ReactNode, key: string | number) => {
  if (l.start_s === undefined && l.dur_s === undefined) return <React.Fragment key={key}>{node}</React.Fragment>;
  const from = Math.round((l.start_s ?? 0) * fps);
  const dur = l.dur_s !== undefined ? Math.max(1, Math.round(l.dur_s * fps)) : undefined;
  return <Sequence key={key} from={from} durationInFrames={dur} layout="none"><AbsoluteFill>{node}</AbsoluteFill></Sequence>;
};

export const LayerStack: React.FC<SceneProps> = ({ scene, style, format, assets, preview }) => {
  const { fps } = useVideoConfig();
  let content: React.ReactNode = null;
  scene.layers.forEach((l, i) => {
    let node: React.ReactNode = null;
    if (l.type === "video") {
      const src = layerAsset(assets, scene.id, i) ?? assetUrl(l.source?.path);
      node = src ? <OffthreadVideo src={src} muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        : <DemoPanel label={preview ? "eksik varlık" : "Ürün A"} />;
      node = withCamera(node, l.camera, fps);
    } else if (l.type === "image" || l.type === "graphic") {
      const src = layerAsset(assets, scene.id, i) ?? assetUrl(l.source?.path);
      node = src ? <Img src={src} style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : <DemoPanel label="eksik görsel" />;
      node = withCamera(node, l.camera, fps);
    } else if (l.type === "text") {
      const name = TEXT_PRESETS[l.preset ?? "text_reveal"] ?? "TextReveal";
      const e = BY_NAME[name];
      const props = { ...(e.schema.parse({ text: l.text ?? "", title: l.text ?? "",
        color: style.palette.ink, fontFamily: style.fonts.display, fontWeight: style.fonts.displayWeight,
        y: anchorY(l.anchor, scene.role, style.layout[format]?.titleY ?? 0.12, format), ...(l.props ?? {}) }) as object) };
      node = <e.Component {...props} />;
    } else if (l.type === "component" && l.component) {
      const e = BY_NAME[l.component];
      if (!e) {
        node = <DemoPanel label={`bilinmeyen bileşen: ${l.component}`} />;
      } else {
        const dy = componentY(l.component, format);  // format başına güvenli konum (layout.json); props.y önceliklidir
        // kaynak alan prop'lar (1.8.0): ara dosya "<katman>.<prop>" anahtarıyla; yoksa kaynağın path'i; ikisi de yoksa null (yer tutucu)
        const raw: Record<string, unknown> = { ...(l.props ?? {}) };
        for (const k of SOURCE_PROPS[l.component] ?? []) {
          const v = raw[k] as { path?: string } | string | null | undefined;
          if (v && typeof v === "object") raw[k] = assetUrl(assets?.[scene.id]?.[`${i}.${k}`] ?? null) ?? assetUrl(v.path);
        }
        const props = e.schema.parse({ ...(dy !== undefined ? { y: dy } : {}), ...raw }) as Record<string, unknown>;
        if (WRAPPERS.has(l.component)) {
          content = timed(l, fps, <e.Component {...props}>{content}</e.Component>, `w${i}`);
          return;
        }
        node = <e.Component {...props} />;
      }
    }
    if (node !== null) {
      const placed = timed(l, fps, node, i);
      content = <>{content}{placed}</>;
    }
  });
  return <AbsoluteFill style={{ background: style.palette.bg, overflow: "hidden" }}>{content}</AbsoluteFill>;
};

const make = (role: string): React.FC<SceneProps> => (p) => <LayerStack {...p} />;

export const SCENE_TEMPLATES: Record<string, React.FC<SceneProps>> = {
  hook: make("hook"), context: make("context"), reveal: make("reveal"), product: make("product"), process: make("process"),
  demo: make("demo"), proof: make("proof"), offer: make("offer"), endcard: make("endcard"),
};
