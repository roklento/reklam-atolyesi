export const meta = {
  name: 'render-variants',
  description: 'reklam-atolyesi S12: format/varyasyon başına editor ajanıyla final render ve öz denetim; render işçi bütçesine göre partiler halinde; kapısız, ücretsiz, yerel.',
}

// Spec 5.16, 5.21, 13.2. Kullanıcı girdisi almaz; onay ve kayıt (creative_register) ana oturumdadır. Ücretli üretim yapılmaz.
// Toplam render işçi bütçesi max(1, floor(CPU/2)); dışarıda J paralel render varsa her birinin concurrency'si floor(bütçe/J), J <= bütçe.
// args: { profile_id, campaign_id, cycle_id, plugin_root, data_dir, py, project, cpu_count, parallel_jobs, now_iso,
//         jobs: [{ key, plan_path, format, out, style, scene_map, captions, quality }] }
const a = args || {}
const missing = ['profile_id', 'campaign_id', 'cycle_id', 'plugin_root', 'data_dir', 'py', 'project']
  .filter(k => a[k] === undefined || a[k] === null || a[k] === '')
if (missing.length || !Array.isArray(a.jobs) || a.jobs.length === 0) {
  return { ok: false, path: 'workflow', error: 'args eksik: ' + missing.concat(Array.isArray(a.jobs) && a.jobs.length ? [] : ['jobs']).join(', ') }
}

const budget = Math.max(1, Math.floor((Number(a.cpu_count) || 2) / 2))
const J = Math.max(1, Math.min(budget, Number(a.parallel_jobs) || 1))
const perRender = Math.max(1, Math.floor(budget / J))

const RESULT = {
  type: 'object',
  required: ['key', 'format', 'status'],
  properties: {
    key: { type: 'string' },
    format: { type: 'string' },
    status: { type: 'string', enum: ['done', 'already_done', 'failed'] },
    out: { type: ['string', 'null'] },
    sha256: { type: ['string', 'null'] },
    self_review_rounds: { type: ['number', 'null'] },
    remaining_issues: { type: 'array', items: { type: 'string' } },
    render_seconds: { type: ['number', 'null'] },
    note: { type: 'string' },
  },
}

const promptFor = job => [
  'reklam-atolyesi S12 render (görev: render_job). Kullanıcıya soru sorma; veritabanına yazma; ücretli araç çağırma.',
  `Önce ${a.plugin_root}/skills/variants/SKILL.md ve ${a.plugin_root}/skills/ref-remotion-components/SKILL.md dosyalarını oku.`,
  `profile_id=${a.profile_id} campaign_id=${a.campaign_id} cycle_id=${a.cycle_id}`,
  `anahtar=${job.key} format=${job.format} kalite=${job.quality ?? 'final'}`,
  `plan=${job.plan_path} stil=${job.style ?? ''} sahne_haritası=${job.scene_map ?? ''} altyazı=${job.captions ?? ''}`,
  `çıktı=${job.out}`,
  `proje=${a.project} plugin_root=${a.plugin_root} data_dir=${a.data_dir} python=${a.py}`,
  `Komut: python ${a.plugin_root}/scripts/render/render.py plan --data-dir <data_dir> --project <proje> --plan <plan> --out <çıktı> --style <stil> --scene-map <sahne_haritası> --captions <altyazı> --quality ${job.quality ?? 'final'} --parallel-jobs ${J}`,
  `Bu render'ın Remotion concurrency değeri en fazla ${perRender} olmalı (toplam bütçe ${budget}, paralel ${J}).`,
  'Çıktı dosyası zaten var ve hash doğrulanıyorsa yeniden render etme (status=already_done).',
  `Sonra öz denetim: python ${a.plugin_root}/scripts/render/self_review.py --video <çıktı> --plan <plan> --out-dir <kampanya>/analysis/review_${job.key}_${job.format} --style <stil> --captions <altyazı> --project <proje> --data-dir <data_dir> --round <n>.`,
  'Kontak sayfasına ve yazı şeritlerine (text_bands_<n>.jpg, küçültmeden) gerçekten bak; font_glyph/font_load bulgusu düzeltilmeden teslim etme; en fazla 3 düzeltme turu; kalan sorunları remaining_issues içinde yaz.',
].join('\n')

log(`render-variants: ${a.jobs.length} iş · bütçe ${budget} · paralel ${J} · render başına concurrency ${perRender} · ${a.now_iso ?? ''}`)
phase('Render')
const results = []
for (let i = 0; i < a.jobs.length; i += J) {
  const batch = a.jobs.slice(i, i + J)
  const out = await parallel(batch.map(job => () =>
    agent(promptFor(job), {
      label: `${job.key} · ${job.format}`,
      phase: 'Render',
      agentType: 'reklam-atolyesi:editor',
      schema: RESULT,
    }),
  ))
  results.push(...out)
}

const ok = results.filter(Boolean)
const failed = a.jobs.filter((j, i) => !results[i] || results[i].status === 'failed').map(j => `${j.key}/${j.format}`)
return {
  ok: failed.length === 0,
  path: 'workflow',
  budget,
  parallel_jobs: J,
  results: ok,
  failed,
  note: failed.length ? 'Eksik render işleri ana oturumda yedek yolla (editor alt ajanı) aynı paralellik sınırıyla tamamlanır.' : '',
}
