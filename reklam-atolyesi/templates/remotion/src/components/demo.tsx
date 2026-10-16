// Galeri ve testler için NÖTR sentetik sahne (spec 12.12): gri tonlar, soyut şekiller, "Ürün A" yer tutucusu.
// Gerçek ürün türü, marka, sezon ya da kişi içermez (ilke 12).
import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";

export const DemoPanel: React.FC<{ label?: string; tone?: number; withProduct?: boolean }> = ({ label = "Ürün A", tone = 0, withProduct = true }) => {
  const f = useCurrentFrame();
  const g1 = tone ? "#BDBDBD" : "#D9D9D9";
  const g2 = tone ? "#8F8F8F" : "#A8A8A8";
  return (
    <AbsoluteFill style={{ background: `linear-gradient(160deg, ${g1} 0%, ${g2} 100%)`, fontFamily: "Inter" }}>
      <AbsoluteFill style={{ background: "repeating-linear-gradient(90deg, rgba(255,255,255,0.05) 0 2px, rgba(0,0,0,0) 2px 80px)" }} />
      {withProduct ? (
        <div style={{ position: "absolute", left: "50%", top: "52%", width: "38%", aspectRatio: "3 / 4",
          transform: `translate(-50%,-50%) rotate(${Math.sin(f / 30) * 1.5}deg)`, borderRadius: 28,
          background: "linear-gradient(180deg, #F2F2F2 0%, #C7C7C7 100%)", boxShadow: "0 30px 60px rgba(0,0,0,0.25)",
          display: "flex", alignItems: "center", justifyContent: "center", fontSize: 54, fontWeight: 700, color: "#4A4A4A" }}>
          {label}
        </div>
      ) : (
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 96,
          fontWeight: 700, color: "#3A3A3A" }}>{label}</div>
      )}
    </AbsoluteFill>
  );
};

/** Maske gerektiren bileşenlerin testi için soyut sentetik özne (belirli bir ürün biçimi ima etmez) — SVG, dosyasız. */
export const DemoSubject: React.FC<{ fill?: string }> = ({ fill = "#EDEDED" }) => (
  <svg viewBox="0 0 100 100" style={{ position: "absolute", left: "31%", top: "28%", width: "38%", height: "50%" }} preserveAspectRatio="none">
    <rect x="10" y="10" width="80" height="80" rx="18" fill={fill} stroke="#9A9A9A" strokeWidth="2" />
  </svg>
);
