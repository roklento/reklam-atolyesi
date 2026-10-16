// İmza anları (spec 5.12): LightRays, ParticleSwirl, HeatShimmer — Three.js/GLSL; yalnızca reveal ve son kartta.
// Bütün uniform'lar kareden türetilir (deterministik); parçacık konumları tohumlu.
import React, { useMemo } from "react";
import { ThreeCanvas } from "@remotion/three";
import { AbsoluteFill, random, useCurrentFrame, useVideoConfig } from "remotion";
import * as THREE from "three";
import { z } from "zod";
import { clamp01, Entry } from "./types";
import { DemoPanel } from "./demo";

const FULLSCREEN_VS = `varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`;

const RAYS_FS = `
precision highp float; varying vec2 vUv; uniform float uTime; uniform vec2 uOrigin; uniform vec3 uColor; uniform float uIntensity; uniform float uAspect;
float hash(float n){ return fract(sin(n)*43758.5453123); }
void main(){
  vec2 p = vUv - uOrigin; p.x *= uAspect;
  float ang = atan(p.y, p.x); float r = length(p);
  float rays = 0.0;
  for (int i = 0; i < 6; i++) { float fi = float(i); rays += pow(0.5 + 0.5*sin(ang*(7.0+fi*3.0) + uTime*(0.4+0.15*fi) + hash(fi)*6.28), 6.0) * (0.5 + 0.5*hash(fi+3.0)); }
  float fall = exp(-r*2.2);
  float a = rays/6.0 * fall * uIntensity;
  gl_FragColor = vec4(uColor * a, a);
}`;

const SHIMMER_FS = `
precision highp float; varying vec2 vUv; uniform float uTime; uniform float uStrength; uniform vec3 uColor;
void main(){
  float w = sin(vUv.y*80.0 + uTime*6.0 + sin(vUv.x*12.0 + uTime*2.0)*2.0);
  float band = smoothstep(0.0, 0.6, vUv.y) * smoothstep(1.0, 0.4, vUv.y);
  float a = (0.5 + 0.5*w) * band * uStrength * 0.25;
  gl_FragColor = vec4(uColor, a);
}`;

const ShaderPlane: React.FC<{ fs: string; uniforms: Record<string, THREE.IUniform>; additive?: boolean }> = ({ fs, uniforms, additive }) => {
  const mat = useMemo(() => new THREE.ShaderMaterial({ vertexShader: FULLSCREEN_VS, fragmentShader: fs, uniforms, transparent: true, depthWrite: false,
    blending: additive ? THREE.AdditiveBlending : THREE.NormalBlending }), [fs]);
  Object.entries(uniforms).forEach(([k, v]) => { mat.uniforms[k].value = v.value; });
  return <mesh frustumCulled={false} material={mat}><planeGeometry args={[2, 2]} /></mesh>;
};

const raysSchema = z.object({ originX: z.number().default(0.5), originY: z.number().default(0.35), color: z.string().default("#FFFFFF"),
  intensity: z.number().default(0.9), fadeFrames: z.number().default(10) });
const LightRays: React.FC<z.infer<typeof raysSchema> & { children?: React.ReactNode }> = (p) => {
  const f = useCurrentFrame();
  const { width, height, fps, durationInFrames } = useVideoConfig();
  const fade = clamp01(f / p.fadeFrames) * clamp01((durationInFrames - f) / p.fadeFrames);
  const c = new THREE.Color(p.color);
  return (
    <AbsoluteFill>
      {p.children ?? <DemoPanel />}
      <AbsoluteFill style={{ mixBlendMode: "screen" }}>
        <ThreeCanvas width={width} height={height}>
          <ShaderPlane fs={RAYS_FS} additive uniforms={{ uTime: { value: f / fps }, uOrigin: { value: new THREE.Vector2(p.originX, 1 - p.originY) },
            uColor: { value: new THREE.Vector3(c.r, c.g, c.b) }, uIntensity: { value: p.intensity * fade }, uAspect: { value: width / height } }} />
        </ThreeCanvas>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const swirlSchema = z.object({ count: z.number().default(600), seed: z.number().default(17), color: z.string().default("#FFFFFF"), radius: z.number().default(2.2),
  speed: z.number().default(0.6), size: z.number().default(0.035) });
const Swirl: React.FC<z.infer<typeof swirlSchema>> = (p) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const geo = useMemo(() => {
    const g = new THREE.BufferGeometry();
    const pos = new Float32Array(p.count * 3);
    for (let i = 0; i < p.count; i++) {
      const r = p.radius * Math.sqrt(random(`${p.seed}-r-${i}`));
      const a = random(`${p.seed}-a-${i}`) * Math.PI * 2;
      pos[i * 3] = Math.cos(a) * r;
      pos[i * 3 + 1] = (random(`${p.seed}-y-${i}`) - 0.5) * 2.4;
      pos[i * 3 + 2] = Math.sin(a) * r;
    }
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    return g;
  }, [p.count, p.seed, p.radius]);
  return (
    <points geometry={geo} rotation={[0.35, (f / fps) * p.speed * Math.PI, 0]}>
      <pointsMaterial color={p.color} size={p.size} transparent opacity={0.85} depthWrite={false} blending={THREE.AdditiveBlending} />
    </points>
  );
};
const ParticleSwirl: React.FC<z.infer<typeof swirlSchema> & { children?: React.ReactNode }> = (p) => {
  const { width, height } = useVideoConfig();
  return (
    <AbsoluteFill>
      {p.children ?? <DemoPanel />}
      <AbsoluteFill style={{ mixBlendMode: "screen" }}>
        <ThreeCanvas width={width} height={height} camera={{ position: [0, 0, 5], fov: 50 }}>
          <Swirl {...p} />
        </ThreeCanvas>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const shimmerSchema = z.object({ strength: z.number().default(0.8), color: z.string().default("#FFFFFF") });
const HeatShimmer: React.FC<z.infer<typeof shimmerSchema> & { children?: React.ReactNode }> = (p) => {
  const f = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const c = new THREE.Color(p.color);
  const wobble = Math.sin((f / fps) * 5) * 0.6;
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ transform: `skewX(${wobble * 0.3}deg) scaleY(${1 + wobble * 0.002})` }}>{p.children ?? <DemoPanel />}</AbsoluteFill>
      <AbsoluteFill>
        <ThreeCanvas width={width} height={height}>
          <ShaderPlane fs={SHIMMER_FS} uniforms={{ uTime: { value: f / fps }, uStrength: { value: p.strength }, uColor: { value: new THREE.Vector3(c.r, c.g, c.b) } }} />
        </ThreeCanvas>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

export const SIGNATURE: Entry[] = [
  { name: "LightRays", category: "signature", version: "1.0.0", schema: raysSchema, Component: LightRays, demo: raysSchema.parse({}) },
  { name: "ParticleSwirl", category: "signature", version: "1.0.0", schema: swirlSchema, Component: ParticleSwirl, demo: swirlSchema.parse({}) },
  { name: "HeatShimmer", category: "signature", version: "1.0.0", schema: shimmerSchema, Component: HeatShimmer, demo: shimmerSchema.parse({}) },
];
