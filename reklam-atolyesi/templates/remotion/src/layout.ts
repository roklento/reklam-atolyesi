// Yazı yerleşimi (5.19): format başına rol, çapa ve bileşen konumları layout.json'dan. Aynı tabloyu güvenli alan denetimi
// (scripts/lib/text_layout.py) okur; burada değişen konum denetimde de değişir. Katmanın props.y değeri her zaman önceliklidir.
import L from "./layout.json";

type Fmt = "9x16" | "4x5" | "1x1";
const fmt = (format: string): Fmt => (format in L.role_y ? format : "9x16") as Fmt;

export const anchorY = (anchor: string | undefined, role: string, titleY: number, format: string): number => {
  const f = fmt(format);
  if (anchor === "safe_top") return titleY + 0.02;
  const a = (L.anchor_y[f] as Record<string, number>)[anchor ?? ""];
  if (a !== undefined) return a;
  const r = (L.role_y[f] as Record<string, number | string>)[role];
  return typeof r === "number" ? r : titleY + 0.02;
};

export const componentY = (name: string, format: string): number | undefined =>
  (L.component_y[fmt(format)] as Record<string, number>)[name];
