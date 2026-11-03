"""Efektin kareye oturması ve türe göre seviyesi (2.7.0).

1.x–2.6 miksi efektin İLK örneğini `at_s` karesine koyuyordu: sesi yavaş yükselen riser, whoosh, swell kareden önce değil SONRA
doruğa çıkıyor, başında sessizlik olan darbe geç duyuluyordu. Artık her efektin bir "oturma noktası" (anchor) var:
  start   ilk duyulur örnek kareye (müzik vuruşu, jingle, ortam sesi, uzun dokular),
  arrive  sesin gövdesinin geldiği an kareye: zarfın ilk kez tepeye 6 dB yaklaştığı yer (darbe, tık, pop, bildirim, klavye),
  peak    en yüksek an kareye (riser, whoosh, swell, logo sting, ters swell: doruk kesmeye denk gelir).
`auto` (varsayılan) türü cue'nun `role` alanından ya da dosya adından çıkarır; tür bilinmiyorsa sesin kendisine bakar:
hızlı yükselen (tepeye 60 ms içinde) → arrive, yavaş yükselen → peak.

Seviye: `level: "role"` (varsayılan) efektin tepe seviyesini türünün hedefine getirir (darbe -4 dBFS, whoosh -9, tık -14…), sonra
`gain_db` ince ayar olarak eklenir. `level: "file"` 2.6 davranışıdır (dosyanın kendi seviyesi + gain_db). Miks sonunda loudnorm
bütün parçayı -14 LUFS'e taşır; hedefler efektlerin BİRBİRİNE göre dengesidir.

Fikir kaynağı: Clipwing real-sfx (yalnız yöntem; kod kopyalanmadı, depoda lisans dosyası yok). Hedef değerler ölçüm ve kulakla
ayarlanabilir; kesin kural değil, başlangıç dengesi.
"""
from __future__ import annotations

import re

import numpy as np

SR = 48000
ANCHORS = ("auto", "start", "arrive", "peak")
LEVELS = ("role", "file")
MAX_BOOST_DB = 18.0  # çok kısık bir dosya tür hedefine çekilirken gürültüsü de yükselir; yükseltme sınırı

# Tür → tepe hedefi (dBFS, efekt izinde, loudnorm öncesi). Darbe gövdeli ve önde; arayüz sesleri geride; doku en geride.
ROLE_PEAK_DB = {
    "impact": -4.0, "hit": -4.0, "sub_drop": -5.0, "cut_hit": -6.0, "logo": -6.0,
    "whoosh": -9.0, "swish": -11.0, "riser": -12.0, "downlifter": -12.0, "swell": -12.0,
    "glitch": -12.0, "shimmer": -13.0, "chime": -13.0, "notify": -13.0, "camera": -10.0,
    "click": -14.0, "ui": -14.0, "pop": -14.0, "typing": -15.0, "tap": -14.0, "knock": -11.0, "water": -14.0,
    "music": -8.0, "ambience": -24.0, "foley": -12.0, "paper": -12.0, "glass": -10.0, "coin": -12.0,
    "default": -10.0,
}
# Tür → varsayılan oturma noktası
ROLE_ANCHOR = {
    "impact": "arrive", "hit": "arrive", "sub_drop": "arrive", "cut_hit": "arrive", "click": "arrive", "ui": "arrive",
    "pop": "arrive", "typing": "arrive", "tap": "arrive", "knock": "arrive", "notify": "arrive", "chime": "arrive",
    "camera": "arrive", "glitch": "arrive", "coin": "arrive", "glass": "arrive", "water": "arrive", "foley": "arrive",
    "paper": "arrive",
    "whoosh": "peak", "swish": "peak", "riser": "peak", "swell": "peak", "logo": "peak", "shimmer": "peak",
    "downlifter": "start", "music": "start", "ambience": "start",
}
# Dosya yolundaki sözcük → tür (Kenney, Earshot, Mixkit adları). Sıra önemli: ilk eşleşen kazanır.
_PATH_ROLE = [
    ("reverse_swell", "swell"), ("reverse", "swell"), ("logo", "logo"), ("sting", "logo"), ("sub_drop", "sub_drop"),
    ("subdrop", "sub_drop"), ("cut_hit", "cut_hit"), ("downlifter", "downlifter"), ("riser", "riser"), ("swell", "swell"),
    ("whoosh", "whoosh"), ("woosh", "whoosh"), ("swoosh", "whoosh"), ("sweep", "whoosh"), ("transition", "whoosh"),
    ("swish", "swish"), ("swipe", "swish"), ("zip", "swish"),
    ("impact", "impact"), ("punch", "impact"), ("hit", "hit"), ("knock", "knock"), ("mallet", "chime"),
    ("glitch", "glitch"), ("shimmer", "shimmer"), ("sparkle", "shimmer"), ("spark", "shimmer"),
    ("notify", "notify"), ("notification", "notify"), ("ding", "notify"), ("bell", "chime"), ("bong", "chime"),
    ("jingle", "music"), ("pluck", "chime"), ("kalimba", "chime"),
    ("typing", "typing"), ("keyboard", "typing"), ("key", "typing"), ("shutter", "camera"), ("camera", "camera"),
    ("click", "click"), ("tick", "click"), ("select", "click"), ("toggle", "click"), ("switch", "click"), ("hover", "ui"),
    ("tap", "tap"), ("pop", "pop"), ("drop", "pop"), ("drip", "water"), ("bubble", "water"), ("splash", "water"),
    ("coin", "coin"), ("cash", "coin"), ("glass", "glass"), ("paper", "paper"), ("page", "paper"),
    ("ambience", "ambience"), ("ambient", "ambience"), ("room", "ambience"), ("crowd", "ambience"),
    ("footstep", "foley"), ("cloth", "foley"),
]


def role_from_path(path: str | None) -> str | None:
    if not path:
        return None
    p = re.sub(r"([a-z])([A-Z])", r"\1_\2", str(path).replace("\\", "/")).lower()
    tail = "/".join(p.split("/")[-2:])  # aile klasörü + dosya adı (mutlak yoldaki klasör adları sayılmaz)
    words: set[str] = set()
    for seg in re.split(r"[/.]", tail):
        toks = re.findall(r"[a-z]+", seg)
        words |= set(toks) | {f"{a}_{b}" for a, b in zip(toks, toks[1:])}  # "pro_sub_drop" → sub_drop da
    for key, role in _PATH_ROLE:
        if key in words or ("_" not in key and any(w.startswith(key) and len(key) >= 4 for w in words)):
            return role
    return None


def envelope(clip: np.ndarray, win_s: float = 0.005) -> np.ndarray:
    mono = np.abs(clip).max(axis=1) if clip.ndim == 2 else np.abs(clip)
    w = max(1, int(win_s * SR))
    n = int(np.ceil(len(mono) / w))
    pad = np.pad(mono.astype(np.float64), (0, n * w - len(mono)))
    return pad.reshape(n, w).max(axis=1)


def measure(clip: np.ndarray) -> dict:
    """Örnek konumları (saniye): ilk duyulur örnek (tepenin -40 dB'i), gövdenin gelişi (tepenin -6 dB'i), en yüksek an."""
    if clip is None or not len(clip):
        return {"onset_s": 0.0, "arrive_s": 0.0, "peak_s": 0.0, "peak_db": -120.0, "dur_s": 0.0}
    env = envelope(clip)
    w = 0.005
    pk = float(env.max())
    if pk <= 0:
        return {"onset_s": 0.0, "arrive_s": 0.0, "peak_s": 0.0, "peak_db": -120.0, "dur_s": len(clip) / SR}
    i_peak = int(env.argmax())
    i_on = int(np.argmax(env >= pk * 10 ** (-40 / 20)))
    i_arr = int(np.argmax(env >= pk * 10 ** (-6 / 20)))
    return {"onset_s": round(i_on * w, 4), "arrive_s": round(i_arr * w, 4), "peak_s": round(i_peak * w, 4),
            "peak_db": round(20 * np.log10(pk), 2), "dur_s": round(len(clip) / SR, 4)}


def resolve(cue: dict, path: str | None, clip: np.ndarray) -> dict:
    """Bir cue'nun türü, oturma noktası, kaydırma ve kazancı. Dönen offset_s: sesin kareden ne kadar ÖNCE başlayacağı."""
    m = measure(clip)
    role = cue.get("role") or role_from_path(path)
    anchor = cue.get("anchor") or "auto"
    if anchor not in ANCHORS:
        anchor = "auto"
    how = "cue"
    if anchor == "auto":
        if role and role in ROLE_ANCHOR:
            anchor, how = ROLE_ANCHOR[role], "role"
        else:  # tür bilinmiyor: sesin kendisi karar verir
            anchor, how = ("arrive" if m["peak_s"] - m["onset_s"] <= 0.06 else "peak"), "shape"
    offset = {"start": m["onset_s"], "arrive": m["arrive_s"], "peak": m["peak_s"]}[anchor]
    level = cue.get("level") or "role"
    trim = float(cue.get("gain_db", 0) or 0)
    if level == "file":
        gain_db, target = trim, None
    else:
        target = ROLE_PEAK_DB.get(role or "default", ROLE_PEAK_DB["default"])
        gain_db = min(MAX_BOOST_DB, target - m["peak_db"]) + trim if m["peak_db"] > -100 else trim
    return {"role": role, "anchor": anchor, "anchor_from": how, "offset_s": round(offset, 4), "level": level,
            "target_peak_db": target, "gain_db": round(gain_db, 2), "measure": m}
