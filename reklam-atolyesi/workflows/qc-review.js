export const meta = {
  name: 'qc-review',
  description: 'reklam-atolyesi S13: kreatif başına bağımsız qc-reviewer ajanı (paralel) — teknik, görsel ve yasal inceleme; üretim bağlamı verilmez; kapısız, ücretsiz.',
}

// Spec bölüm 10, 13.2. qc-reviewer üretimi görmemiş gözle bakar: prompt'a üretim konuşması ya da gerekçesi KONMAZ.
// Kullanıcı girdisi almaz; QC durumu (creative_set_qc) ve kapı ana oturumdadır. Zaman bilgisi args ile gelir.
// args: { profile_id, campaign_id, cycle_id, campaign_dir, plugin_root, data_dir, py, now_iso,
//         creatives: [{ creative_id, file, plan_path, format, expect_duration, tech_report }] }
const a = args || {}
const missing = ['profile_id', 'campaign_id', 'campaign_dir', 'plugin_root', 'data_dir', 'py']
  .filter(k => a[k] === undefined || a[k] === null || a[k] === '')
if (missing.length || !Array.isArray(a.creatives) || a.creatives.length === 0) {
  return { ok: false, path: 'workflow', error: 'args eksik: ' + missing.concat(Array.isArray(a.creatives) && a.creatives.length ? [] : ['creatives']).join(', ') }
}

const RESULT = {
  type: 'object',
  required: ['creative_id', 'verdict', 'report'],
  properties: {
    creative_id: { type: ['string', 'number'] },
    verdict: { type: 'string', enum: ['passed', 'failed', 'pending'] },
    report: { type: 'string' },
    human_check_required: { type: 'array', items: { type: 'string' } },
    legal_blockers: { type: 'array', items: { type: 'string' } },
    fixes: { type: 'array', items: { type: 'string' } },
  },
}

const promptFor = c => [
  'reklam-atolyesi S13 bağımsız kalite kontrol. Yalnızca aşağıdaki dosya ve kayıtlara bak; kullanıcıya soru sorma; veritabanına yazma.',
  `Önce ${a.plugin_root}/skills/qc/SKILL.md ve ${a.plugin_root}/skills/ref-legal-tr-meta/SKILL.md dosyalarını oku.`,
  `profile_id=${a.profile_id} campaign_id=${a.campaign_id} creative_id=${c.creative_id}`,
  `teslim_dosyası=${c.file} plan=${c.plan_path} format=${c.format ?? ''} beklenen_süre=${c.expect_duration ?? ''}`,
  `teknik_rapor=${c.tech_report ?? 'yok — checks.py tech ile üret'}`,
  `plugin_root=${a.plugin_root} data_dir=${a.data_dir} python=${a.py}`,
  `Rapor: ${a.campaign_dir}/reports/qc/${c.creative_id}.json (geçici ad → atomik).`,
  'Yorum ve kişi izinlerini review_query / consent_query ile eşle; eşleşmeyen ReviewCard ya da izinsiz kişili klip = failed.',
  'Seyrek karelerden hareket akıcılığı, kısa ürün bozulması ve ses için onay verme: human_check_required içine yaz.',
].join('\n')

log(`qc-review: ${a.creatives.length} kreatif · ${a.now_iso ?? ''}`)
phase('Bağımsız QC')
const results = await pipeline(a.creatives, c =>
  agent(promptFor(c), {
    label: `QC ${c.creative_id}`,
    phase: 'Bağımsız QC',
    agentType: 'reklam-atolyesi:qc-reviewer',
    schema: RESULT,
  }),
)

const ok = results.filter(Boolean)
const missingReviews = a.creatives.filter((c, i) => !results[i]).map(c => c.creative_id)
return {
  ok: missingReviews.length === 0,
  path: 'workflow',
  results: ok,
  not_reviewed: missingReviews,
  note: missingReviews.length ? 'İncelenmemiş kreatifler ana oturumda yedek yolla (qc-reviewer alt ajanı) incelenir; incelenmiş olanlar tekrar incelenmez.' : '',
}
