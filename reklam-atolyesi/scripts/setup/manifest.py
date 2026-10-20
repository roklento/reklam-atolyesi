"""system_manifest.json üreticisi (spec 12.13, 16.4): sistemin kendi haritası.

Dağıtılan sürümün DEĞİŞMEZ tanımlarını yazar: aşamalar, skill/ajan/komut/workflow/hook listeleri, MCP sunucuları ve araçları, boru hatları,
işlev → script haritası, şablonlar, statik/sentetik test sonuçları, belgeden sapmalar (gerekçesiyle), nötrlük denetimi sonucu, canlı kontrol
tanımları ve bileşen hash'leri. Hesap, makine yolu, OAuth, canlı sonuç ya da görev durumu YAZILMAZ (canlı sonuçlar data_dir'deki
settings.runtime_verification_json'dadır). Çıktı deterministiktir: aynı dosyalar ve sonuç girdileri → aynı manifest.

Kullanım: manifest.py --plugin-root <kök> [--results-dir <dizin>] [--out <kök>/system_manifest.json]
results-dir (isteğe bağlı) içinde: pytest.json, smoke.json, gallery.json, turkish.json, workflow_trial.json, neutrality.json, install_checks.json,
customer_update.json.
Kuruluma/makineye özgü sapmalar (ör. disk alanı) bu manifeste YAZILMAZ: doctor --deviations-json ile data_dir veritabanına
(settings.install_deviations_json) işler; system_manifest_get onları 'install_deviations' olarak gösterir.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
from pathlib import Path

SKIP_DIRS = {"node_modules", ".bundle", ".segments", "__pycache__", ".pytest_cache", ".venv"}
# Metnin HERHANGİ bir yerindeki mutlak yol (sürücü harfli, UNC, file:// ya da bilinen posix kökleri). Windows klasör adlarında boşluk
# olabilir: ayırıcıyla biten her parça yola dahildir, son parça boşlukta biter. Parçada ; ve , olamaz (yolun ardından gelen düz metin
# bir sonraki / ile yola katılmasın); fazla temizleme güvenli taraftır.
# Ayırıcı tek ya da çift olabilir (Python repr'i: 'C:\\Users\\...'); uzun yol öneki \\?\ de kapsanır.
_WIN_SEG = r"(?:[^\\/:*?\"'<>|\r\n;,]+[\\/]+)*[^\\/:*?\"'<>|\r\n\s;,]*"
ABS_PATH_RE = re.compile(
    r"(?:file:/{2,3}[^\s\"'<>]+"
    r"|(?<![A-Za-z0-9])(?:\\{2,4}\?\\{1,2})?[A-Za-z]:[\\/]+" + _WIN_SEG +
    r"|\\{2,4}[^\\/\s\"'<>?]+[\\/]+" + _WIN_SEG +
    r"|(?<![\w.<>-])/(?:Users|home|tmp|var|private|mnt|Volumes|opt|root|srv|etc|media|run|data|workspace|usr|snap)/[^\s\"'<>]*)")
DROP_KEYS = {"trace"}  # yığın dökümü makine yollarıyla doludur ve manifest için gereksizdir
_HOME_ROOTS = {"users", "home"}


def _redact_one(m: re.Match) -> str:
    parts = [p for p in re.split(r"[\\/]+", m.group(0)) if p]
    if ".selftest" in parts:
        return "<data_dir>/" + "/".join(parts[parts.index(".selftest"):])
    name = parts[-1] if parts else ""
    # Dosya adı (uzantılı) korunur; klasör adı korunmaz: yol kullanıcı klasöründe bitiyorsa son parça kullanıcı adıdır.
    if len(parts) >= 2 and "." in name[1:] and parts[-2].lower() not in _HOME_ROOTS:
        return "<yol>/" + name
    return "<yol>"


def redact_paths(obj):
    """Test sonuçlarındaki mutlak yolları makineden bağımsız biçime çevirir (manifeste makine yolu yazılmaz, 12.13).
    Değerlerde ve anahtarlarda, dizgenin her yerinde çalışır. Duman testi klasörü altındaki yollar `<data_dir>/.selftest/...` olur;
    diğer mutlak yollardan yalnızca dosya adı kalır. `trace` alanları atılır."""
    if isinstance(obj, dict):
        return {redact_paths(k): redact_paths(v) for k, v in obj.items() if k not in DROP_KEYS}
    if isinstance(obj, list):
        return [redact_paths(v) for v in obj]
    if isinstance(obj, str):
        return ABS_PATH_RE.sub(_redact_one, obj)
    return obj


def find_abs_paths(obj) -> list[str]:
    """Nesnedeki (anahtar ve değer) bütün mutlak yol eşleşmeleri; test ve yayın kapısı kullanır."""
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            found += find_abs_paths(k) + find_abs_paths(v)
    elif isinstance(obj, list):
        for v in obj:
            found += find_abs_paths(v)
    elif isinstance(obj, str):
        found += [m.group(0) for m in ABS_PATH_RE.finditer(obj)]
    return found


def sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def tree_hash(root: Path, patterns: tuple[str, ...] = ("*",)) -> str:
    h = hashlib.sha256()
    if not root.exists():
        return h.hexdigest()
    files = []
    for pat in patterns:
        files += [p for p in root.rglob(pat) if p.is_file() and not (set(p.relative_to(root).parts) & SKIP_DIRS)]
    for p in sorted(set(files), key=lambda x: x.relative_to(root).as_posix()):
        h.update(p.relative_to(root).as_posix().encode("utf-8"))
        h.update(b"\0")
        h.update(sha_file(p).encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def frontmatter(p: Path) -> dict:
    t = p.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", t, re.S)
    out = {}
    if m:
        for ln in m.group(1).splitlines():
            k, _, v = ln.partition(": ")
            v = v.strip()
            if v.startswith('"'):
                try:
                    v = json.loads(v)
                except json.JSONDecodeError:
                    pass
            out[k.strip()] = v
    return out


def ad_memory_tools(root: Path) -> list[str]:
    import shutil
    import tempfile
    sys.path.insert(0, str(root / "servers" / "ad_memory"))
    tmp = Path(tempfile.mkdtemp(prefix="manifest-probe-"))
    old = {k: os.environ.get(k) for k in ("AD_MEMORY_DB", "AD_MEMORY_DATA_DIR")}
    os.environ["AD_MEMORY_DB"] = str(tmp / "probe.sqlite")
    os.environ["AD_MEMORY_DATA_DIR"] = str(tmp)
    try:
        import server  # type: ignore
        tools = asyncio.run(server.mcp.list_tools())
        return sorted(t.name for t in tools)
    except Exception as e:  # sunucu yüklenemezse liste boş kalır; doctor bunu hata sayar
        return [f"<yüklenemedi: {type(e).__name__}>"]
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(tmp, ignore_errors=True)


SKILL_KIND = {"navigator": "entry", "memory": "system", "ref-system-map": "system", "dm-sales": "module", "data-connection": "module"}

LIVE_CHECKS = [
    {"id": "oauth_elevenlabs", "title": "ElevenLabs uzak MCP OAuth bağlı", "required": True, "applies_to": "both", "components": ["mcp_json"]},
    {"id": "meta_data_path", "title": "Meta veri yolu seçildi: salt okuma MCP doğrulandı ya da CSV yolu açıkça seçildi", "required": True,
     "applies_to": "both", "components": ["mcp_json", "hooks"]},
    {"id": "ad_memory_live", "title": "ad-memory plugin içinden data_dir ile başladı, şema sürümü doğru", "required": True, "applies_to": "both",
     "components": ["ad_memory", "mcp_json"]},
    {"id": "hook_userpromptsubmit_live", "title": "UserPromptSubmit gerçekten tetikleniyor (durum satırı veritabanından)", "required": True,
     "applies_to": "both", "components": ["hooks"]},
    {"id": "hook_pretooluse_meta_live", "title": "PreToolUse Meta izin listesi gerçek çağrıda reddediyor (zararsız okuma aracıyla)",
     "required": True, "applies_to": "mcp", "components": ["hooks"]},
    {"id": "hook_cost_guard_live", "title": "Maliyet koruması gerçek host tetiklenmesi (geçici deny testi, sonra kaldırıldı)", "required": True,
     "applies_to": "both", "components": ["hooks"]},
    {"id": "el_estimate_schema", "title": "ElevenLabs ücretli araçlarında estimate_only desteği canlı şemadan okundu", "required": True,
     "applies_to": "both", "components": ["hooks"]},
    {"id": "el_paid_tool_classes", "title": "ElevenLabs araç listesi hook sınıflarıyla karşılaştırıldı", "required": True, "applies_to": "both",
     "components": ["hooks"]},
    {"id": "meta_allowlist_vs_tools", "title": "İzin listesi gerçek Meta araç listesiyle karşılaştırıldı", "required": True, "applies_to": "mcp",
     "components": ["hooks"]},
    {"id": "meta_fields_verified", "title": "meta_fields.json alanları ads_get_field_context ile doğrulandı", "required": True, "applies_to": "mcp",
     "components": ["ad_memory"]},
    {"id": "meta_experiments_readable", "title": "Kreatif test durumu deney araçlarıyla okunabiliyor mu", "required": False, "applies_to": "mcp",
     "components": ["hooks"]},
    {"id": "library_coverage", "title": "Reklam Kütüphanesi hesap bölgesi kapsamı ve dönen alanlar", "required": False, "applies_to": "mcp",
     "components": ["hooks"]},
    {"id": "csv_mapping_synthetic", "title": "CSV yolunda eşleme şeması sentetik örnekle doğrulandı; otomatik çekme kapalı", "required": True,
     "applies_to": "csv", "components": ["ad_memory", "scripts"]},
    {"id": "scheduled_tasks_trial", "title": "Dört zamanlanmış iş bir kez denendi, izinler ayarlandı, tanımlar silindi", "required": False,
     "applies_to": "both", "components": ["commands"]},
    {"id": "workflows_live", "title": "Workflow'lar (ya da yedek yol) sentetik girdide çalıştı", "required": False, "applies_to": "both",
     "components": ["workflows", "agents"]},
    {"id": "acceptance_16_5", "title": "Canlı kabul listesi (16.5) sentetik profilde, ücretli/yazma çağrısı olmadan", "required": True,
     "applies_to": "both", "components": ["skills", "agents", "commands", "hooks", "ad_memory"]},
]

SCRIPT_MAP = {
    "ingest: probe, cfr, hdr2sdr, proxy, stabilize, fotoğraf (HEIC/EXIF)": "scripts/ingest/convert.py",
    "ingest: sahne ara dosyaları": "scripts/ingest/scenes.py",
    "analyze: sharpness, exposure, shake, motion, audio, people": "scripts/analyze/measure.py",
    "analyze: contact_sheet": "scripts/analyze/contact_sheet.py",
    "analyze: material_map": "scripts/analyze/material_map.py",
    "analyze: palette (logodan renk)": "scripts/analyze/palette.py",
    "compose: edit_plan şeması ve doğrulama": "scripts/compose/validate_plan.py",
    "compose: sahne önbelleği": "scripts/compose/scene_cache.py",
    "audio: beats": "scripts/audio/beats.py",
    "audio: sfx_synth": "scripts/audio/sfx_synth.py",
    "audio: clean, duck, loudnorm, phone_test": "scripts/audio/loudness.py",
    "audio: words_align": "scripts/audio/words_align.py",
    "audio: sahne sesi ve miks": "scripts/audio/mix.py",
    "audio: ses kütüphanesi": "scripts/audio/sfx_library.py",
    "render: render, still, galeri, Türkçe final": "scripts/render/render.py",
    "render: Remotion programatik render": "scripts/render/render.mjs",
    "render: export ve adlandırma": "scripts/render/export.py",
    "render: grade_lut": "scripts/render/grade_lut.py",
    "render: self_review": "scripts/render/self_review.py",
    "qc: tech_qc, safe_zone, black_frames, meta-text, copy (reklam metni uzunluğu)": "scripts/qc/checks.py",
    "qc: slayt gösterisi riski (durağan pay, zayıf hareket, açılış hareketi, tekrar, ritim, yazıya yaslanma)": "scripts/qc/slideshow.py",
    "analyze: referans video (sahne kesimleri, ritim, hareket, yazı/konuşma, ses, kontak sayfası)": "scripts/analyze/reference.py",
    "meta: csv_import kontrolü, priors_from_history doğrulaması, naming_match": "scripts/meta/meta_tools.py",
    "competitive: snapshot_diff, variant_group, competitive_map, distance_check, offer_parse": "scripts/competitive/comp_tools.py",
    "analytics: budget (S02 ekonomi, matris, takvim, toplam plan)": "scripts/analytics/budget.py",
    "analytics: bayes": "scripts/analytics/bayes.py",
    "analytics: fatigue, retention, priority, limit uyarıları (koçluk boru hattı)": "scripts/analytics/coach.py",
    "analytics: calibration": "scripts/analytics/calibration.py",
    "analytics: charts": "scripts/analytics/charts.py",
    "analytics: report": "scripts/analytics/report.py",
    "memory: konsolidasyon, özet katlama, kullanım önizlemesi": "scripts/memory/memory_tools.py",
    "selftest: nötr sentetik fikstürler": "scripts/selftest/fixtures.py",
    "selftest: duman testi": "scripts/selftest/smoke.py",
    "setup: vendor-skills": "scripts/setup/vendor-skills.sh",
    "setup: update-vendor": "scripts/setup/update-vendor.sh",
    "setup: doctor": "scripts/setup/doctor.py",
    "setup: manifest": "scripts/setup/manifest.py",
    "setup: hooks.json ve .mcp.json üretimi": "scripts/setup/gen_config.py",
    "setup: MCP stdio sondası": "scripts/setup/mcp_probe.py",
    "setup: dağıtılan kurulumun makinede doğrulaması (duman testi, render ve galeri karşılaştırması, doctor)": "scripts/setup/kurulum_dogrula.py",
    "setup: Windows araç ve bağımlılık kurulumu (dağıtım; kök kur.ps1 çağırır)": "scripts/setup/windows/kurulum.ps1",
}

PIPELINES = {
    "üretim (bölüm 5)": ["S04 shoot-guide", "S05 shoot-feedback", "S06 ingest", "S07 analyze", "S08 style-directions", "S09 materials",
                         "S10 compose", "S11 sound", "S12 variants", "S13 qc", "S14 launch-pack"],
    "rekabet (4.5–4.7)": ["S01b competitor-analysis", "S02 strategy (B)", "S03 concepts (uzaklık)", "S13 qc (rakip varlığı)", "S16 rekabet bağlamı"],
    "koçluk (bölüm 6)": ["S15 track", "S16 coach", "S17 learn"],
    "hafıza (bölüm 8)": ["memory_card", "memory_context", "memory_search", "memory_add/observe", "checkpoint", "consolidate", "lifecycle", "forget"],
}

CAPABILITIES = [
    "Profil yönetimi: birden çok marka/reklam hesabı ve ürün; profil yalıtımı",
    "Tanışma: marka (S00a), Meta geçmişi salt okuma ya da CSV (S00b), ürün ve ürüne özgü çekim tarifi (S00c)",
    "Kampanya döngüsü S01–S17: brief, rakip analizi, strateji, konsept görüşmesi, çekim rehberi, ingest/analiz, stil, malzeme, kurgu, ses, "
    "varyasyon/export, QC, yayın paketi, takip, koçluk, öğrenme",
    "Ücretli üretim yalnızca tahmin → kayıt → açık onay → tek kullanımlık atomik rezervasyon",
    "Meta: yalnızca izin listesindeki salt okuma araçları; plugin Meta'ya yazmaz",
    "Remotion ile deterministik render (9:16, 4:5, isteğe bağlı 1:1), 37 bileşenli kütüphane, görsel öz denetim",
    "Koçluk: Beta-Binom/Gamma, değişmez girdi kopyası, kalibrasyon, bağımsız doğrulamalı playbook",
    "Hafıza: profil kartı, aşama bağlam paketi, Türkçe trigram arama, devam notu, yaşam döngüsü, konsolidasyon, unutma",
    "Zamanlanmış işler (masaüstü uygulaması): günlük takip, karar hazırlığı, gece üretimi, haftalık bakım",
]

DOES_NOT = ["Meta'da reklam oluşturmak/yayına almak/bütçe değiştirmek", "Onaysız ücretli üretim", "Rakip hesabına erişim, sosyal medya kazıma",
            "AI ile insan üretmek, ses klonlamak, sahte yorum", "Çekimin kendisi"]


def build(root: Path, results_dir: Path | None) -> dict:
    sys.path.insert(0, str(root / "servers" / "ad_memory"))
    from admem import stages as ST  # type: ignore
    plugin = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    skills = []
    for d in sorted((root / "skills").iterdir()):
        f = d / "SKILL.md"
        if f.exists():
            fm = frontmatter(f)
            kind = SKILL_KIND.get(d.name) or ("reference" if d.name.startswith("ref-") else "stage")
            skills.append({"name": fm.get("name", d.name), "kind": kind, "description": fm.get("description", ""), "sha256": sha_file(f)})
    agents = [{"name": frontmatter(f).get("name", f.stem), "description": frontmatter(f).get("description", ""), "sha256": sha_file(f)}
              for f in sorted((root / "agents").glob("*.md"))]
    commands = [{"name": f"/reklam-atolyesi:{f.stem}", "description": frontmatter(f).get("description", ""), "sha256": sha_file(f)}
                for f in sorted((root / "commands").glob("*.md"))]
    workflows = []
    for f in sorted((root / "workflows").glob("*.js")):
        t = f.read_text(encoding="utf-8")
        workflows.append({"name": f.stem, "agent_types": sorted(set(re.findall(r"agentType:\s*'([^']+)'", t))), "sha256": sha_file(f),
                          "deterministic_ok": not re.search(r"Date\.now|Math\.random|new Date\(\)|import\(", t),
                          "fallback": "ilgili aşama skill'i ajanı alt ajan olarak çağırır (13.2)"})
    hooks_json = json.loads((root / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    hooks = []
    for ev, arr in (hooks_json.get("hooks") or {}).items():
        for m in arr:
            for h in m.get("hooks", []):
                script = next((Path(a).name for a in h.get("args", []) if str(a).endswith(".py")), None)
                hooks.append({"event": ev, "matcher": m.get("matcher"), "script": script, "timeout": h.get("timeout"),
                              "sha256": sha_file(root / "hooks" / script) if script and (root / "hooks" / script).exists() else None})
    mcp = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
    mcp_servers = [{"name": k, "type": v.get("type", "stdio"), "url": v.get("url")} for k, v in (mcp.get("mcpServers") or {}).items()]
    stages = []
    for code in ST.ONBOARDING_STAGES + ST.CAMPAIGN_STAGES:
        stages.append({"code": code, "skill": ST.SKILLS.get(code), "gate": ST.GATES.get(code)})
    templates = {p.relative_to(root).as_posix(): sha_file(p) for p in sorted((root / "templates").rglob("*"))
                 if p.is_file() and not (set(p.relative_to(root).parts) & SKIP_DIRS) and p.suffix in (".json", ".md", ".cube", ".ts", ".tsx", ".png")}
    component_hashes = {
        "plugin_json": sha_file(root / ".claude-plugin" / "plugin.json"),
        "mcp_json": sha_file(root / ".mcp.json"),
        "skills": tree_hash(root / "skills"),
        "agents": tree_hash(root / "agents"),
        "commands": tree_hash(root / "commands"),
        "workflows": tree_hash(root / "workflows"),
        "hooks": tree_hash(root / "hooks", ("*.py", "*.json")),
        "ad_memory": tree_hash(root / "servers" / "ad_memory", ("*.py", "*.sql", "*.json", "*.toml", "*.lock")),
        "scripts": tree_hash(root / "scripts", ("*.py", "*.mjs", "*.sh", "*.ps1", "*.png")),
        "templates": tree_hash(root / "templates", ("*.json", "*.md", "*.cube", "*.ts", "*.tsx")),
        "vendor_skills": tree_hash(root / "vendor-skills"),
    }
    results = {}
    if results_dir and results_dir.exists():
        for name in ("pytest", "smoke", "gallery", "turkish", "workflow_trial", "neutrality", "install_checks", "customer_update"):
            f = results_dir / f"{name}.json"
            if f.exists():
                results[name] = redact_paths(json.loads(f.read_text(encoding="utf-8")))
    neutrality = results.get("neutrality") or {"status": "pending", "note": "kurulum nötrlük denetimi henüz kaydedilmedi"}
    tests = {k: results[k] for k in ("pytest", "smoke", "gallery", "turkish", "workflow_trial", "install_checks", "customer_update") if k in results}
    deviations = [
        {"id": "remotion_skills_not_vendored", "spec": "12.4, 12.5",
         "deviation": "remotion-dev/skills pinli commit'te lisans dosyası yok; kopyalanmadı. İşlevler ref-remotion-components + ref-vendor-map'te "
                      "resmi belge bölümlerine bağlandı.", "decided_by": "spec 12.5 kuralı", "status": "applied"},
        {"id": "comparative_ad_partial_verification", "spec": "10, 12.10",
         "deviation": "Ticari Reklam Yönetmeliği m. 8'in 2017 değişikliği (c, h bentleri, 2.-4. fıkra) ve m. 9 resmi RG metninden okundu; diğer bentler "
                      "ve rakip markasına doğrudan yer verme hükmünün güncel durumu konsolide resmi metinden okunamadı: skill'de "
                      "'resmi metinle teyit edilmedi' işaretli. Plugin varsayılanı zaten 'rakip anılmaz'.", "decided_by": "kurulum", "status": "recorded"},
        {"id": "meta_ai_label_policy_unverified", "spec": "10, 12.10",
         "deviation": "Meta AI açıklama politikasının resmi metni kurulumda okunamadı; ikincil kaynaklar 'resmi metinle teyit edilmedi' işaretiyle "
                      "skill'de. S14 talimatı Ads Manager'ın güncel seçeneklerine dayanır.", "decided_by": "kurulum", "status": "recorded"},
        {"id": "generation_call_hash", "spec": "9.1, 7.4",
         "deviation": "params_hash girdi dosyası hash'lerini içerir; hook bunları göremediği için rezervasyon eşleşmesi aynı kanonik koddan dosya "
                      "hash'leri hariç hesaplanan call_hash ile yapılır (migration 002). Onay ve tekrar koruması params_hash'e bağlı kalır.",
         "decided_by": "kurulum", "status": "applied"},
        {"id": "ad_memory_exec_launch", "spec": "12.6, 12.7",
         "deviation": "ad-memory `uv run --project ...` yerine data_dir sanal ortamının Python'uyla `${CLAUDE_PLUGIN_ROOT}/servers/ad_memory/server.py` "
                      "olarak başlar; sanal ortama yalnızca bağımlılıklar kurulur (uv sync --no-install-project). Dağıtılan kurulumda plugin "
                      "her sürümde yeni bir önbellek klasörüne kopyalanır; düzenlenebilir proje kurulumu eski sürümün klasörüne bağlı "
                      "kalıyordu. uv yalnızca kurulumda kullanılır.", "decided_by": "dağıtım hazırlığı", "status": "applied"},
    ]
    if results.get("workflow_trial", {}).get("path") == "fallback":
        deviations.append({"id": "workflow_trial_fallback", "spec": "12.1, 13.2",
                           "deviation": "Kurulum oturumunda deneme workflow'u çalıştırılamadı; aşama skill'leri yedek yolu (alt ajanlar) kullanır.",
                           "decided_by": "kurulum", "status": "applied"})
    return {
        "name": plugin["name"], "plugin_version": plugin["version"], "spec_version": "1.4",
        "capabilities": CAPABILITIES, "does_not": DOES_NOT,
        "stages": stages, "skills": skills, "agents": agents, "commands": commands, "workflows": workflows, "hooks": hooks,
        "mcp_servers": mcp_servers, "mcp_tools": {"ad-memory": ad_memory_tools(root)},
        "pipelines": PIPELINES, "scripts": SCRIPT_MAP, "templates": templates,
        "tests": tests, "deviations": deviations, "neutrality_audit": neutrality,
        "live_checks": LIVE_CHECKS, "component_hashes": component_hashes,
        "notes": "Canlı (C) maddeler ilk açılışta bekliyor; sonuçlar data_dir veritabanında settings.runtime_verification_json'da tutulur. "
                 "Kuruluma/makineye özgü kullanıcı kararlı sapmalar (ör. disk alanı) settings.install_deviations_json'dadır.",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plugin-root", required=True)
    ap.add_argument("--results-dir")
    ap.add_argument("--out")
    a = ap.parse_args()
    root = Path(a.plugin_root).resolve()
    m = build(root, Path(a.results_dir) if a.results_dir else None)
    out = Path(a.out) if a.out else root / "system_manifest.json"
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    tmp.replace(out)
    print(json.dumps({"out": str(out), "sha256": sha_file(out), "skills": len(m["skills"]), "agents": len(m["agents"]),
                      "commands": len(m["commands"]), "workflows": len(m["workflows"]), "ad_memory_tools": len(m["mcp_tools"]["ad-memory"]),
                      "live_checks": len(m["live_checks"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
