// reklam-atolyesi Remotion yapılandırması (studio/CLI için). Programatik render scripts/render/render.mjs'tedir.
// Bağımlılıklar <data_dir>/.node/node_modules altındadır; webpack çözümlemesi render script'inde ayarlanır (12.6).
import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setPixelFormat("yuv420p");
