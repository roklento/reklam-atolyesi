"""Ürün ayırma işçisi (2.10.17). Yalnızca kendi sanal ortamında çalışır (DD/.gorsel/cutout/.venv: onnxruntime, numpy, pillow).

Çağrı: <motor python> -I cutout_worker.py <istek.json> <yanit.json>
İstek: {"model": "<onnx yolu>", "items": [{"image": "<girdi>", "mask": "<çıktı maskesi .png>"}]}
Yanıt: {"items": [{"image": ..., "mask": ..., "size": [w, h]}]}

Ağ kullanılmaz; model kurulumda indirilmiş ve sha256 ile doğrulanmıştır. Model: BiRefNet-lite (MIT). Girdi 1024×1024'e ölçeklenir,
ImageNet ortalaması/sapmasıyla normalize edilir; çıktı sigmoid → 0–1 aralığına yayılır → 8 bit gri maske, görselin kendi boyutunda.
Aynı girdi her çalıştırmada aynı maskeyi verir (yalnızca CPU; 900×1200 fotoğrafta 4 çekirdekte ≈ 12 sn).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageOps

SIDE = 1024
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def load_rgb(path: str) -> Image.Image:
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)  # telefon fotoğrafındaki döndürme bilgisi uygulanır (çıktılar aynı yönde olsun)
    return im.convert("RGB")


def predict(sess: ort.InferenceSession, im: Image.Image) -> Image.Image:
    x = np.asarray(im.resize((SIDE, SIDE), Image.Resampling.BICUBIC), dtype=np.float32) / 255.0
    x = ((x - MEAN) / STD).transpose(2, 0, 1)[None].astype(np.float32)
    out = sess.run(None, {sess.get_inputs()[0].name: x})[0]
    pred = 1.0 / (1.0 + np.exp(-out[0, 0]))
    lo, hi = float(pred.min()), float(pred.max())
    pred = (pred - lo) / (hi - lo) if hi - lo > 1e-6 else np.zeros_like(pred)
    m = Image.fromarray((pred * 255).round().astype(np.uint8), mode="L")
    return m.resize(im.size, Image.Resampling.LANCZOS)


def main() -> None:
    req = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    so = ort.SessionOptions()
    so.intra_op_num_threads = min(4, os.cpu_count() or 1)  # 1 ve 4 iş parçacığında maske bayt bayt aynı çıktı (ölçüldü, 26.11.2026)
    so.inter_op_num_threads = 1
    sess = ort.InferenceSession(req["model"], sess_options=so, providers=["CPUExecutionProvider"])
    done = []
    for it in req["items"]:
        im = load_rgb(it["image"])
        m = predict(sess, im)
        Path(it["mask"]).parent.mkdir(parents=True, exist_ok=True)
        m.save(it["mask"])
        done.append({"image": it["image"], "mask": it["mask"], "size": list(im.size)})
    Path(sys.argv[2]).write_text(json.dumps({"items": done}, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
