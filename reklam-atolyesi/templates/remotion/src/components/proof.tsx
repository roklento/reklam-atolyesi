// Kanıt ve kapanış (spec 5.12, bölüm 10): ReviewCard (izin kaydı zorunlu), StarRating (gerçek puan), EndCard, CTAPulse.
// Yorum metni birebir; ad name_display_mode'a göre (tam · baş harf · gizli). Puan/izin yoksa görünür uyarı çizilir.
import React from "react";
import { AbsoluteFill, Img, useCurrentFrame, useVideoConfig } from "remotion";
import { z } from "zod";
import { clamp01, easeOutCubic, Entry } from "./types";

const reviewSchema = z.object({ reviewId: z.number().nullable(), quote: z.string(), displayName: z.string().nullable().default(null),
  rating: z.number().min(0).max(5).nullable().default(null), color: z.string().default("#1F1F1F"), bg: z.string().default("#F2F2F2"),
  accent: z.string().default("#6B6B6B"), fontFamily: z.string().default("Inter") });
const ReviewCard: React.FC<z.infer<typeof reviewSchema>> = (p) => {
  const f = useCurrentFrame();
  const t = easeOutCubic(f / 14);
  if (p.reviewId === null) {
    return <AbsoluteFill style={{ background: "#B00020", color: "#FFF", fontFamily: "Inter", fontSize: 54, fontWeight: 700,
      display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center" }}>YORUM İZİN KAYDI YOK</AbsoluteFill>;
  }
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
      <div style={{ width: "82%", background: p.bg, borderRadius: 28, padding: "56px 54px", fontFamily: p.fontFamily, color: p.color,
        opacity: t, transform: `translateY(${(1 - t) * 40}px)`, boxShadow: "0 24px 60px rgba(0,0,0,0.18)" }}>
        <div style={{ fontSize: 90, lineHeight: 0.6, color: p.accent }}>“</div>
        <div style={{ fontSize: 50, lineHeight: 1.25, fontWeight: 400 }}>{p.quote}</div>
        {p.rating !== null ? <div style={{ marginTop: 26 }}><Stars rating={p.rating} size={48} color={p.accent} progress={clamp01((f - 10) / 20)} /></div> : null}
        {p.displayName ? <div style={{ marginTop: 22, fontSize: 36, fontWeight: 700 }}>— {p.displayName}</div> : null}
      </div>
    </AbsoluteFill>
  );
};

const Stars: React.FC<{ rating: number; size: number; color: string; progress: number }> = ({ rating, size, color, progress }) => (
  <div style={{ display: "flex", gap: size * 0.18 }}>
    {Array.from({ length: 5 }, (_, i) => {
      const fill = clamp01(rating * progress - i);
      return (
        <div key={i} style={{ position: "relative", width: size, height: size, fontSize: size, lineHeight: 1 }}>
          <span style={{ position: "absolute", color: "rgba(0,0,0,0.18)" }}>★</span>
          <span style={{ position: "absolute", color, width: `${fill * 100}%`, overflow: "hidden", whiteSpace: "nowrap" }}>★</span>
        </div>
      );
    })}
  </div>
);

const starSchema = z.object({ rating: z.number().min(0).max(5).nullable(), size: z.number().default(96), color: z.string().default("#6B6B6B"),
  y: z.number().default(0.45), fillFrames: z.number().default(24) });
const StarRating: React.FC<z.infer<typeof starSchema>> = (p) => {
  const f = useCurrentFrame();
  if (p.rating === null) {
    return <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", fontFamily: "Inter", fontSize: 44, color: "#B00020", fontWeight: 700 }}>PUAN KAYDI YOK</AbsoluteFill>;
  }
  return (
    <AbsoluteFill style={{ alignItems: "center" }}>
      <div style={{ position: "absolute", top: `${p.y * 100}%` }}><Stars rating={p.rating} size={p.size} color={p.color} progress={clamp01(f / p.fillFrames)} /></div>
    </AbsoluteFill>
  );
};

const endSchema = z.object({ brand: z.string(), cta: z.string(), url: z.string().default(""), ink: z.string().default("#1F1F1F"), bg: z.string().default("#E6E6E6"),
  accent: z.string().default("#6B6B6B"), fontFamily: z.string().default("Inter"), logo: z.string().nullable().default(null), brandTracking: z.string().default("0em") });
const EndCard: React.FC<z.infer<typeof endSchema>> = (p) => {
  const f = useCurrentFrame();
  const a = easeOutCubic(f / 12);
  const b = easeOutCubic((f - 8) / 12);
  return (
    <AbsoluteFill style={{ background: p.bg, alignItems: "center", justifyContent: "center", fontFamily: p.fontFamily, color: p.ink }}>
      {p.logo ? <Img src={p.logo} style={{ width: "40%", opacity: a, transform: `scale(${0.9 + 0.1 * a})` }} /> :
        <div style={{ fontSize: 110, fontWeight: 700, letterSpacing: p.brandTracking, opacity: a, transform: `scale(${0.9 + 0.1 * a})` }}>{p.brand}</div>}
      <div style={{ marginTop: 50, background: p.accent, color: p.bg, padding: "22px 46px", borderRadius: 999, fontSize: 52, fontWeight: 700,
        opacity: b, transform: `translateY(${(1 - b) * 20}px)` }}>{p.cta}</div>
      {p.url ? <div style={{ marginTop: 26, fontSize: 36, opacity: b }}>{p.url}</div> : null}
    </AbsoluteFill>
  );
};

const ctaSchema = z.object({ text: z.string(), color: z.string().default("#E6E6E6"), bg: z.string().default("#1F1F1F"), fontFamily: z.string().default("Inter"),
  y: z.number().default(0.8), periodFrames: z.number().default(30) });
const CTAPulse: React.FC<z.infer<typeof ctaSchema>> = (p) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const k = 1 + 0.05 * Math.sin((2 * Math.PI * f) / p.periodFrames);
  const a = easeOutCubic(f / (fps * 0.4));
  return (
    <AbsoluteFill style={{ alignItems: "center" }}>
      <div style={{ position: "absolute", top: `${p.y * 100}%`, transform: `translateY(-50%) scale(${k})`, opacity: a, background: p.bg, color: p.color,
        fontFamily: p.fontFamily, fontSize: 56, fontWeight: 700, padding: "24px 56px", borderRadius: 999 }}>{p.text}</div>
    </AbsoluteFill>
  );
};

export const PROOF: Entry[] = [
  { name: "ReviewCard", category: "proof", version: "1.0.0", schema: reviewSchema, Component: ReviewCard,
    demo: reviewSchema.parse({ reviewId: 0, quote: "Örnek yorum metni; gerçek yorum yalnızca izin kaydıyla kullanılır.", displayName: "A. B.", rating: 4 }) },
  { name: "StarRating", category: "proof", version: "1.0.0", schema: starSchema, Component: StarRating, demo: starSchema.parse({ rating: 3.5 }) },
  { name: "EndCard", category: "proof", version: "1.0.0", schema: endSchema, Component: EndCard, demo: endSchema.parse({ brand: "Marka A", cta: "Örnek çağrı", url: "ornek.test" }) },
  { name: "CTAPulse", category: "proof", version: "1.0.0", schema: ctaSchema, Component: CTAPulse, demo: ctaSchema.parse({ text: "Örnek çağrı" }) },
];
