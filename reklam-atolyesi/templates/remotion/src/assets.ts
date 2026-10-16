// staticFile() yolları: proxy (önizleme) / final ara dosya anahtarı (spec 5.12, 5.21).
// Render script'i sahne ara dosyalarını projenin public/ klasörüne koyar; burada yalnızca göreli yol çözülür.
import { staticFile } from "remotion";

export const assetUrl = (rel: string | undefined | null): string | null => {
  if (!rel) return null;
  if (/^(https?:|data:|blob:)/.test(rel)) return rel;
  return staticFile(rel.replace(/^\/+/, "").replace(/\\/g, "/"));
};

export const layerAsset = (assets: Record<string, Record<string, string>> | undefined, sceneId: string, layerIndex: number): string | null =>
  assetUrl(assets?.[sceneId]?.[String(layerIndex)] ?? null);
