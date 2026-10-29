// Ekran içinde ekran (1.8.0): PictureInPicture (konuşan kişi köşede, arkada ürün çekimi) ve PhoneScreen (sade telefon çerçevesi içinde
// ekran kaydı ya da görsel). Kaynaklar plan katmanının props'unda kaynak nesnesi olarak gelir ({kind: "footage", asset, in_s, out_s});
// scenes.py ara dosyasını üretir, sahne şablonu URL'ye çevirir. Kaynak yoksa nötr yer tutucu çizilir.
// Fikir kaynağı: RemotionUI ve snapcn (MIT) bileşenleri; kod bu kütüphanenin zod/Entry kuralıyla sıfırdan yazıldı.
import React from "react";
import { AbsoluteFill, Img, OffthreadVideo, useCurrentFrame, useVideoConfig } from "remotion";
import { z } from "zod";
import { assetUrl } from "../assets";
import L from "../layout.json";
import { DemoPanel } from "./demo";
import { easeOutCubic, Entry } from "./types";

const VIDEO_EXT = /\.(mp4|mov|m4v|webm|mkv)(\?|#|$)/i;

/** Kaynak alan: sahne şablonunun çözdüğü URL ya da ham kaynak nesnesi. Ham nesne yalnız 1.8.0 öncesi sahne şablonuyla gelir
 * (`render.py init --force-library` components/ dışını tazelemez); o zaman özgün dosya path'ten açılır, in_s'den başlar. */
export const zSource = z.union([z.string(), z.object({ path: z.string().nullable().optional(), in_s: z.number().optional() }).passthrough()])
  .nullable().default(null);
export type Source = z.infer<typeof zSource>;

/** Video ya da görsel; kaynak yoksa yer tutucu. Video sessizdir (ses sahne miksinden gelir). */
export const Media: React.FC<{ src: Source; fit?: "cover" | "contain"; style?: React.CSSProperties; placeholder?: string; tone?: number }> = (p) => {
  const { fps } = useVideoConfig();
  const st: React.CSSProperties = { width: "100%", height: "100%", objectFit: p.fit ?? "cover", ...(p.style ?? {}) };
  const raw = p.src && typeof p.src === "object" ? p.src : null;
  const url = typeof p.src === "string" ? p.src : assetUrl(raw?.path ?? null);
  // ham nesne çözülemedi (asset anahtarı eski sahne şablonunda URL'ye çevrilmez): yer tutucu bunu açıkça söyler, reklama sessizce girmez
  if (!url) return <DemoPanel label={raw ? "KAYNAK ÇÖZÜLEMEDİ: projeyi yeniden kurun" : p.placeholder ?? "Ürün A"} tone={p.tone ?? 0} withProduct={false} />;
  return VIDEO_EXT.test(url) ? <OffthreadVideo src={url} muted style={st} startFrom={raw?.in_s ? Math.round(raw.in_s * fps) : undefined} />
    : <Img src={url} style={st} />;
};

type Fmt = "9x16" | "4x5" | "1x1";
const fmtOf = (w: number, h: number): Fmt => (h / w > 1.5 ? "9x16" : h / w > 1.1 ? "4x5" : "1x1");

/** Köşe kutusu (0–1 oranları): güvenli alan payları layout.json pip_box'tan; checks.py safe aynı tabloyu okur. */
type Box = { top: number; bottom: number; side: number };
// 1.8.0 öncesi projenin layout.json'unda pip_box yoktur (init --force-library yalnız components/'ı tazeler): aynı değerler yedek
const PIP_DEFAULT: Record<Fmt, Box> = { "9x16": { top: 0.15, bottom: 0.64, side: 0.06 }, "4x5": { top: 0.19, bottom: 0.81, side: 0.093 },
  "1x1": { top: 0.08, bottom: 0.92, side: 0.08 } };
export const pipRect = (corner: string, size: number, w: number, h: number) => {
  const b = ((L as unknown as { pip_box?: Record<Fmt, Box> }).pip_box ?? PIP_DEFAULT)[fmtOf(w, h)];
  const bw = size;
  const bh = (size * w) / h;  // kare kutu
  const left = corner.endsWith("left") ? b.side : 1 - b.side - bw;
  const top = corner.startsWith("top") ? b.top : b.bottom - bh;
  return { left, top, width: bw, height: bh };
};

const pipSchema = z.object({ inset: zSource, shape: z.enum(["circle", "rounded"]).default("circle"),
  corner: z.enum(["top_left", "top_right", "bottom_left", "bottom_right"]).default("top_right"), size: z.number().min(0.18).max(0.45).default(0.34),
  border: z.string().default("#FFFFFF"), enterFrames: z.number().int().min(0).default(8) });
/** Sarmalayıcı: alttaki katmanlar (ürün çekimi) arka plan, konuşan kişi köşede. */
const PictureInPicture: React.FC<z.infer<typeof pipSchema> & { children?: React.ReactNode }> = (p) => {
  const f = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const r = pipRect(p.corner, p.size, width, height);
  const a = p.enterFrames ? easeOutCubic(f / p.enterFrames) : 1;
  return (
    <AbsoluteFill>
      {p.children ?? <DemoPanel />}
      <div style={{ position: "absolute", left: `${r.left * 100}%`, top: `${r.top * 100}%`, width: `${r.width * 100}%`, height: `${r.height * 100}%`,
        borderRadius: p.shape === "circle" ? "50%" : "14%", overflow: "hidden", border: `6px solid ${p.border}`, boxSizing: "border-box",
        boxShadow: "0 18px 40px rgba(0,0,0,0.35)", opacity: a, transform: `scale(${0.85 + 0.15 * a})` }}>
        <Media src={p.inset} placeholder="Kişi" tone={1} />
      </div>
    </AbsoluteFill>
  );
};

const zRegion = z.object({ x: z.number().min(0).max(1), y: z.number().min(0).max(1), w: z.number().min(0).max(1), h: z.number().min(0).max(1) });
const phoneSchema = z.object({ screen: zSource,
  // kaynağın kenarlarından kırpılacak pay (kaynak boyutunun oranı): durum çubuğu, alt gezinme çubuğu
  crop: z.object({ top: z.number().min(0).max(0.4).default(0), bottom: z.number().min(0).max(0.4).default(0),
    left: z.number().min(0).max(0.3).default(0), right: z.number().min(0).max(0.3).default(0) }).default({ top: 0, bottom: 0, left: 0, right: 0 }),
  // kayıtta başka kişinin adı/numarası/fotoğrafı: "blurred" + blurRegions (ekran alanı oranları); "none" = yok (kapıda soruldu)
  personalData: z.enum(["unknown", "none", "blurred"]).default("unknown"), blurRegions: z.array(zRegion).default([]),
  height: z.number().min(0.4).max(0.82).default(0.7), y: z.number().default(0.47), body: z.string().default("#141414"),
  enterFrames: z.number().int().min(0).default(10) });
const PHONE_RATIO = 9 / 19.5;

const PhoneScreen: React.FC<z.infer<typeof phoneSchema>> = (p) => {
  const f = useCurrentFrame();
  const { height } = useVideoConfig();
  const a = p.enterFrames ? easeOutCubic(f / p.enterFrames) : 1;
  const ph = height * p.height;
  const pw = ph * PHONE_RATIO;
  const bezel = pw * 0.035;
  const c = p.crop;
  const visW = 1 - c.left - c.right;
  const visH = 1 - c.top - c.bottom;
  const warn = p.personalData === "unknown" || (p.personalData === "blurred" && p.blurRegions.length === 0);
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: "50%", top: `${p.y * 100}%`, width: pw, height: ph, transform: `translate(-50%, -50%) translateY(${(1 - a) * 40}px)`,
        opacity: a, background: p.body, borderRadius: pw * 0.13, padding: bezel, boxSizing: "border-box", boxShadow: "0 40px 80px rgba(0,0,0,0.35)" }}>
        <div style={{ position: "relative", width: "100%", height: "100%", borderRadius: pw * 0.1, overflow: "hidden", background: "#000" }}>
          {/* kırpılmış kaynak: görünen bölge ekranı doldurur */}
          <div style={{ position: "absolute", width: `${100 / visW}%`, height: `${100 / visH}%`, left: `${(-c.left / visW) * 100}%`, top: `${(-c.top / visH) * 100}%` }}>
            <Media src={p.screen} placeholder="Ekran" />
          </div>
          {p.blurRegions.map((r, i) => (
            <div key={i} style={{ position: "absolute", left: `${r.x * 100}%`, top: `${r.y * 100}%`, width: `${r.w * 100}%`, height: `${r.h * 100}%`,
              backdropFilter: "blur(22px)", WebkitBackdropFilter: "blur(22px)", background: "rgba(128,128,128,0.6)", borderRadius: 8 }} />
          ))}
          <div style={{ position: "absolute", top: bezel * 0.6, left: "50%", width: pw * 0.28, height: pw * 0.075, transform: "translateX(-50%)",
            background: p.body, borderRadius: 999 }} />
        </div>
      </div>
      {warn ? <div style={{ position: "absolute", left: "50%", top: `${(p.y + p.height / 2) * 100}%`, transform: "translate(-50%, 12px)", background: "#B00020",
        color: "#FFFFFF", fontFamily: "Inter", fontWeight: 700, fontSize: 30, padding: "4px 12px", whiteSpace: "nowrap" }}>KİŞİSEL VERİ KONTROLÜ YOK</div> : null}
    </AbsoluteFill>
  );
};

export const MEDIA: Entry[] = [
  { name: "PictureInPicture", category: "product", version: "1.0.0", schema: pipSchema, Component: PictureInPicture, demo: pipSchema.parse({}) },
  { name: "PhoneScreen", category: "product", version: "1.0.0", schema: phoneSchema, Component: PhoneScreen,
    demo: phoneSchema.parse({ personalData: "blurred", blurRegions: [{ x: 0.08, y: 0.2, w: 0.84, h: 0.08 }], crop: { top: 0.04 } }) },
];
