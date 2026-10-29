// reklam-atolyesi programatik Remotion render'ı (spec 5.12, 5.21).
// Kullanım: node render.mjs <config.json>
// config: { entry, publicDir, nodeModules, bundleOut?, jobs: [{ composition, inputProps, out, still?, frameRange?, scale, quality, concurrency, crf? }] }
// Çalışma dizini <data_dir>/.node olmalıdır (headless Chrome orada; plugin köküne .remotion yazılmaz). Bağımlılıklar nodeModules'tan çözülür.
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const cfgPath = process.argv[2];
if (!cfgPath) {
  console.error("kullanım: node render.mjs <config.json>");
  process.exit(2);
}
const cfg = JSON.parse(fs.readFileSync(cfgPath, "utf-8"));
const req = createRequire(path.join(cfg.nodeModules, "..", "package.json"));
const { bundle } = req("@remotion/bundler");
const { renderMedia, renderStill, selectComposition, ensureBrowser } = req("@remotion/renderer");

const log = (o) => process.stderr.write(JSON.stringify(o) + "\n");

// 1.6.0: bileşenlerin ölçtüğü yazı yerleşimi (components/fit.tsx) konsola "RA_LAYOUT {json}" olarak düşer; iş başına toplanır,
// video işlerinde <çıktı>.layout.json yazılır (qc/checks.py safe --layout). Aynı kayıt birden çok sekmeden gelebilir: tekilleştirilir.
const layoutCollector = () => {
  const seen = new Set();
  const records = [];
  const onBrowserLog = ({ text }) => {
    if (typeof text !== "string" || !text.startsWith("RA_LAYOUT ")) return;
    const body = text.slice("RA_LAYOUT ".length);
    if (seen.has(body)) return;
    seen.add(body);
    try {
      records.push(JSON.parse(body));
    } catch {
      // bozuk satır yok sayılır
    }
  };
  return { onBrowserLog, records };
};

const main = async () => {
  await ensureBrowser();
  let serveUrl = cfg.bundleOut && fs.existsSync(path.join(cfg.bundleOut, "index.html")) && cfg.reuseBundle ? cfg.bundleOut : null;
  if (!serveUrl) {
    const t0 = Date.now();
    serveUrl = await bundle({
      entryPoint: cfg.entry,
      publicDir: cfg.publicDir ?? null,
      outDir: cfg.bundleOut ?? undefined,
      enableCaching: true,
      webpackOverride: (c) => ({
        ...c,
        resolve: { ...(c.resolve ?? {}), modules: [cfg.nodeModules, "node_modules"] },
        resolveLoader: { ...(c.resolveLoader ?? {}), modules: [cfg.nodeModules, "node_modules"] },
      }),
    });
    log({ event: "bundled", ms: Date.now() - t0 });
  }
  const results = [];
  for (const job of cfg.jobs) {
    const t0 = Date.now();
    const lay = layoutCollector();
    const composition = await selectComposition({ serveUrl, id: job.composition, inputProps: job.inputProps ?? {}, chromiumOptions: { gl: cfg.gl ?? "swangle" } });
    fs.mkdirSync(path.dirname(job.out), { recursive: true });
    if (job.still !== undefined && job.still !== null) {
      const isJpeg = job.out.endsWith(".jpg") || job.out.endsWith(".jpeg");
      await renderStill({ serveUrl, composition, output: job.out, frame: job.still, inputProps: job.inputProps ?? {}, scale: job.scale ?? 1,
        imageFormat: isJpeg ? "jpeg" : "png", ...(isJpeg ? { jpegQuality: 92 } : {}), chromiumOptions: { gl: cfg.gl ?? "swangle" },
        onBrowserLog: lay.onBrowserLog });
    } else {
      await renderMedia({ serveUrl, composition, codec: "h264", outputLocation: job.out, inputProps: job.inputProps ?? {}, scale: job.scale ?? 1,
        concurrency: job.concurrency ?? 1, crf: job.crf ?? (job.quality === "final" ? 16 : 23), pixelFormat: "yuv420p", muted: true,
        frameRange: job.frameRange ?? null, imageFormat: "jpeg", jpegQuality: job.quality === "final" ? 95 : 80, colorSpace: "bt709",
        x264Preset: job.quality === "final" ? "medium" : "veryfast", chromiumOptions: { gl: cfg.gl ?? "swangle" },
        onBrowserLog: lay.onBrowserLog,
        onProgress: ({ progress }) => { if (Math.round(progress * 100) % 25 === 0) log({ event: "progress", out: job.out, progress }); } });
      fs.writeFileSync(`${job.out}.layout.json`, JSON.stringify({ records: lay.records }, null, 1));
    }
    const ms = Date.now() - t0;
    results.push({ out: job.out, composition: job.composition, ms, width: composition.width, height: composition.height,
      fps: composition.fps, durationInFrames: composition.durationInFrames, frameRange: job.frameRange ?? null, still: job.still ?? null,
      layout: lay.records });
    log({ event: "done", out: job.out, ms });
  }
  process.stdout.write(JSON.stringify({ ok: true, serveUrl, results }) + "\n");
};

main().catch((e) => {
  process.stdout.write(JSON.stringify({ ok: false, error: String(e && e.stack ? e.stack : e).slice(0, 4000) }) + "\n");
  process.exit(1);
});
