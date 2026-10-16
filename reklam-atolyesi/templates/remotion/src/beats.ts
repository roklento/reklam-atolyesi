// Vuruş haritası → kilitli anlar ve yaslanma (spec 5.2). Aksiyon kesimi en yakın vuruşa ≤ 3 kare ise vuruşa yaslanır.
export const nearestBeat = (t: number, beats: number[]): number | null => {
  if (!beats.length) return null;
  let best = beats[0];
  for (const b of beats) if (Math.abs(b - t) < Math.abs(best - t)) best = b;
  return best;
};

export const snapToBeat = (t: number, beats: number[], fps: number, maxFrames = 3): number => {
  const b = nearestBeat(t, beats);
  if (b === null) return t;
  return Math.abs(b - t) * fps <= maxFrames + 1e-9 ? b : t;
};

export const beatFrames = (beats: number[], fps: number): number[] => beats.map((b) => Math.round(b * fps));
