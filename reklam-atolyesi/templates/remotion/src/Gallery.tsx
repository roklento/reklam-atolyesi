// Galeri/test kompozisyonu (spec 5.12): her bileşen sentetik nötr sahne üzerinde 2 sn; galeri 4 eşit aralıklı kare gösterir.
// Galeri bileşenlerin ÇALIŞTIĞINI kanıtlar; gerçek çekim üzerindeki estetik uygunluğu S08 stil testleri ve taslak kapısı belirler.
import React from "react";
import { AbsoluteFill } from "remotion";
import { z } from "zod";
import { BY_NAME } from "./components";
import { DemoPanel } from "./components/demo";
import { useFontsReady } from "./style";

export const zGalleryProps = z.object({ component: z.string() });
const OVERLAY_CATEGORIES = new Set(["text", "light", "proof", "helper"]);
const SELF_CONTAINED = new Set(["EndCard", "ReviewCard", "BehindSubjectText", "StillTurn", "Parallax25D"]);

export const Gallery: React.FC<z.infer<typeof zGalleryProps>> = ({ component }) => {
  useFontsReady();
  const e = BY_NAME[component];
  if (!e) return <AbsoluteFill style={{ background: "#B00020" }} />;
  const C = e.Component;
  const needsBackdrop = OVERLAY_CATEGORIES.has(e.category) && !SELF_CONTAINED.has(component);
  return (
    <AbsoluteFill style={{ background: "#2A2A2A" }}>
      {needsBackdrop ? <DemoPanel /> : null}
      <C {...(e.demo as object)} />
    </AbsoluteFill>
  );
};

export const TurkishTest: React.FC = () => {
  useFontsReady();
  return (
    <AbsoluteFill style={{ background: "#E6E6E6", alignItems: "center", justifyContent: "center", fontFamily: "Inter", color: "#1F1F1F", textAlign: "center" }}>
      <div style={{ fontSize: 120, fontWeight: 700, lineHeight: 1.2 }}>ğ ş ı İ ç ö ü</div>
      <div style={{ fontSize: 120, fontWeight: 700, lineHeight: 1.2 }}>Ğ Ş I Ç Ö Ü</div>
      <div style={{ fontSize: 60, fontWeight: 400, marginTop: 40, padding: "0 6%", lineHeight: 1.3 }}>Örnek sınama metni</div>
      <div style={{ fontSize: 60, fontWeight: 400, padding: "0 6%", lineHeight: 1.3 }}>ığü şöç ĞÜŞ İıI öçğ</div>
    </AbsoluteFill>
  );
};
