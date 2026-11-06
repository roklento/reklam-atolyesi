"""2.10.13: video ve ölçüm doğruluğu (dış bağımsız denetim 2.10.10 B7, B8, B10, B20). Sentetik veri; ağ ve ücretli çağrı yok."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import coach
import fixtures as FX
import mix as MX
import scene_cache as SC
from conftest import ROOT
from test_generation import setup
from test_v2108_koc_rapor import CTX
from admem.util import AdMemoryError


# ----------------------------------------------------------------------------- B10: altyazı metni önbellek anahtarında
PLAN = {"format": "9x16", "fps": 30, "seed": 1, "captions": {"on": True, "preset": "plain"},
        "scenes": [{"id": "s1", "start_s": 0, "dur_s": 1, "audio": {"mode": "none"}, "layers": []},
                   {"id": "s2", "start_s": 1, "dur_s": 1, "audio": {"mode": "none"}, "layers": []}]}


def _key(i, caps):
    a, b = round(PLAN["scenes"][i]["start_s"] * 30), round((PLAN["scenes"][i]["start_s"] + 1) * 30) - 1
    return SC.scene_key(PLAN, i, source_hashes={}, style_sha=None, quality="final", scale=1.0, component_sha="x",
                        captions_sha=SC.captions_in_range(caps, a / 30, (b + 1) / 30))


def test_changed_caption_text_changes_only_its_scene_key():
    old = [{"text": "Örnek fiyat 100", "start": 0, "end": 1}, {"text": "Sabit metin", "start": 1, "end": 2}]
    new = [{"text": "Örnek fiyat 150", "start": 0, "end": 1}, {"text": "Sabit metin", "start": 1, "end": 2}]
    assert _key(0, old) != _key(0, new)
    assert _key(1, old) == _key(1, new)  # değişmeyen sahne yeniden kullanılır


def test_caption_timing_change_changes_key():
    a = [{"text": "Metin", "start": 0, "end": 0.5}]
    b = [{"text": "Metin", "start": 0, "end": 0.9}]
    assert _key(0, a) != _key(0, b)


def test_scene_without_captions_keeps_its_old_key():
    plain = SC.scene_key(PLAN, 1, source_hashes={}, style_sha=None, quality="final", scale=1.0, component_sha="x")
    assert _key(1, [{"text": "yalnız ilk sahne", "start": 0, "end": 1}]) == plain


def test_unreadable_caption_times_invalidate_every_scene():
    assert SC.captions_in_range([{"text": "zamansız"}], 5, 6) is not None


def test_render_passes_captions_into_the_key():
    src = (ROOT / "scripts" / "render" / "render.py").read_text(encoding="utf-8")
    assert "captions_sha=cap_sha" in src and "SC.captions_in_range(captions" in src


# ----------------------------------------------------------------------------- B20: eksik konuşma
def _plan(mode):
    return {"duration_s": 2, "fps": 30, "music": {"offset_s": 0, "gain_db": -8},
            "scenes": [{"id": "s1", "start_s": 0, "dur_s": 2, "audio": {"mode": mode}, "layers": []}]}


def test_missing_voice_file_stops_the_mix(tmp_path):
    music = FX.click_track(tmp_path / "m.wav", 100, 3)
    with pytest.raises(MX.MissingVoice, match="anlatıcı sesi dosyası bulunamadı"):
        MX.mix(_plan("user_vo"), {}, str(music), str(tmp_path / "olmayan.wav"), {}, tmp_path / "out")
    assert not (tmp_path / "out" / "mix_final.wav").exists()


def test_silent_voice_file_stops_the_mix(tmp_path):
    import numpy as np
    import soundfile as sf
    music = FX.click_track(tmp_path / "m.wav", 100, 3)
    silent = tmp_path / "sessiz.wav"
    sf.write(str(silent), np.zeros((48000 * 2, 2), np.float32), 48000)
    with pytest.raises(MX.MissingVoice, match="sessiz"):
        MX.mix(_plan("user_vo"), {}, str(music), str(silent), {}, tmp_path / "out")


def test_missing_scene_sound_stops_the_mix(tmp_path):
    music = FX.click_track(tmp_path / "m.wav", 100, 3)
    with pytest.raises(MX.MissingVoice, match="sahnenin kendi sesi"):
        MX.mix(_plan("original"), {}, str(music), None, {}, tmp_path / "out")


def test_real_voice_still_mixes(tmp_path):
    music = FX.click_track(tmp_path / "m.wav", 100, 3)
    vo = FX.noisy_voice(tmp_path / "vo.wav", 2)
    r = MX.mix(_plan("user_vo"), {}, str(music), str(vo), {}, tmp_path / "out")
    assert r["loudness_ok"]


def test_mix_cli_exits_with_message(tmp_path):
    import subprocess, sys
    (tmp_path / "plan.json").write_text(json.dumps(_plan("user_vo")), encoding="utf-8")
    (tmp_path / "sa.json").write_text("{}", encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "audio" / "mix.py"), "--plan", str(tmp_path / "plan.json"),
                        "--scene-audio", str(tmp_path / "sa.json"), "--vo", str(tmp_path / "yok.wav"), "--out-dir", str(tmp_path / "o")],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 2 and "miks yapılmadı" in r.stderr


# ----------------------------------------------------------------------------- B7: sayım sütunları
@pytest.mark.parametrize("imp,spend", [('"1,250"', "45"), ('"1.250"', "45"), ("1250", '"45,50"'), ('"1,250"', "45.50")])
def test_counts_read_the_same_in_any_locale(store, data_dir, imp, spend):
    p, c, cy = setup(store)
    f = data_dir / "sayim.csv"
    f.write_text(f"Day,Ad ID,Impressions,Amount spent\n2026-03-02,78,{imp},{spend}\n", encoding="utf-8")
    store.metrics_import_csv(p, str(f), CTX)
    row = [r for r in store.metrics_daily_rows(p)["rows"] if r["meta_ad_id"] == "78"][0]
    assert row["impressions"] == 1250
    assert row["spend"] in (45.0, 45.5)


def test_fractional_count_is_refused(store, data_dir):
    p, c, cy = setup(store)
    f = data_dir / "kesir.csv"
    f.write_text('Day,Ad ID,Impressions,Amount spent\n2026-03-02,78,"12,5",45\n', encoding="utf-8")
    with pytest.raises(AdMemoryError, match="sayım sütununda"):
        store.metrics_import_csv(p, str(f), CTX)
    assert not store.metrics_daily_rows(p)["rows"]


# ----------------------------------------------------------------------------- B8: ölçülmeyen sonuç
def test_ab_with_unmeasured_cell_has_no_winner():
    args = {"A": {"totals": {"spend": 1000, "results": None}}, "B": {"totals": {"spend": 1000, "results": 30}}}
    sec = coach.ab_section({}, args, "ab_test")
    assert sec["gated"] == "measurement_coverage" and "leader" not in sec
    assert all(c["p_lowest_cost"] is None for c in sec["cells"].values())


def test_ab_from_rows_separates_unmeasured_from_zero():
    rows_a_unknown = [{"spend": 500, "results": None}, {"spend": 500, "results": None}]
    rows_a_zero = [{"spend": 500, "results": 0}, {"spend": 500, "results": 0}]
    rows_b = [{"spend": 500, "results": 15}, {"spend": 500, "results": 15}]
    unk = coach.posteriors({"A": rows_a_unknown, "B": rows_b}, {})
    sec = coach.ab_section({}, unk, "ab_test")
    assert "leader" not in sec and sec["cells"]["A"]["measured"] is False
    zero = coach.posteriors({"A": rows_a_zero, "B": rows_b}, {})
    sec = coach.ab_section({}, zero, "ab_test")
    assert sec["leader"] == "B" and sec["cells"]["B"]["p_lowest_cost"] > 0.9


def test_cost_with_no_measured_result_gives_no_probability():
    out = coach.cost_measured([{"spend": 220, "results": None}], 30, True)
    assert out["threshold_met"] is False and "p_below_target" not in out and out["label"] == "ölçülmedi"


def test_report_says_comparison_was_not_made():
    import report
    src = (ROOT / "scripts" / "analytics" / "report.py").read_text(encoding="utf-8")
    assert 'ab.get("gated") == "measurement_coverage"' in src
