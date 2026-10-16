export const meta = {
  name: 'analyze-footage',
  description: 'reklam-atolyesi S07: her klip için footage-analyst ajanı (paralel) — ölçüm, kontak sayfası, çekim menüsü eşlemesi ve puan; kapısız, ücretsiz, yerel.',
}

// Spec 5.5, 13.2. Kullanıcı girdisi almaz; onay ve kayıt (asset_register) ana oturumdadır.
// Zaman bilgisi args ile gelir (betikte saat ve rastgelelik kullanılmaz). Ücretli üretim yapılmaz.
// args: { profile_id, campaign_id, cycle_id, campaign_dir, plugin_root, data_dir, py, shoot_menu_path, now_iso,
//         clips: [{ asset_id, proxy, wav, shake_permille, shot_hint }] }
const a = args || {}
const missing = ['profile_id', 'campaign_id', 'campaign_dir', 'plugin_root', 'data_dir', 'py', 'shoot_menu_path']
  .filter(k => a[k] === undefined || a[k] === null || a[k] === '')
if (missing.length || !Array.isArray(a.clips) || a.clips.length === 0) {
  return { ok: false, path: 'workflow', error: 'args eksik: ' + missing.concat(Array.isArray(a.clips) && a.clips.length ? [] : ['clips']).join(', ') }
}

const RESULT = {
  type: 'object',
  required: ['asset_id', 'clip_json', 'status'],
  properties: {
    asset_id: { type: ['string', 'number'] },
    clip_json: { type: 'string' },
    status: { type: 'string', enum: ['done', 'already_done', 'failed'] },
    shot_no: { type: ['string', 'null'] },
    overall: { type: ['number', 'null'] },
    speaking_on_camera: { type: ['boolean', 'null'] },
    people_detected: { type: ['boolean', 'null'] },
    note: { type: 'string' },
  },
}

const promptFor = clip => [
  'reklam-atolyesi S07 klip analizi. Tek bir klibi analiz et; kullanıcıya soru sorma, veritabanına yazma, ücretli araç çağırma.',
  `Önce ${a.plugin_root}/skills/analyze/SKILL.md dosyasını oku.`,
  `profile_id=${a.profile_id} campaign_id=${a.campaign_id} cycle_id=${a.cycle_id ?? 'null'}`,
  `asset_id=${clip.asset_id}`,
  `proxy=${clip.proxy}`,
  `wav=${clip.wav ?? 'yok'}`,
  `shake_permille=${clip.shake_permille ?? 'bilinmiyor'}`,
  `shot_hint=${clip.shot_hint ?? 'yok'}`,
  `shoot_menu_path=${a.shoot_menu_path}`,
  `campaign_dir=${a.campaign_dir}`,
  `plugin_root=${a.plugin_root}`,
  `data_dir=${a.data_dir}`,
  `python=${a.py}`,
  `Çıktı: ${a.campaign_dir}/analysis/clips/clip_${clip.asset_id}.json (zaten varsa ve girdiyle uyumluysa yeniden işleme, status=already_done).`,
  'Kontak sayfasına gerçekten bak; görmediğin içeriği "belirsiz" yaz.',
].join('\n')

log(`analyze-footage: ${a.clips.length} klip · ${a.now_iso ?? ''}`)
phase('Klip analizi')
const results = await pipeline(a.clips, clip =>
  agent(promptFor(clip), {
    label: `klip ${clip.asset_id}`,
    phase: 'Klip analizi',
    agentType: 'reklam-atolyesi:footage-analyst',
    schema: RESULT,
  }),
)

const ok = results.filter(Boolean)
const failed = a.clips.filter((c, i) => !results[i] || results[i].status === 'failed').map(c => c.asset_id)
return {
  ok: failed.length === 0,
  path: 'workflow',
  results: ok,
  failed,
  note: failed.length ? 'Eksik klipler ana oturumda yedek yolla (footage-analyst alt ajanı) tamamlanır; tamamlananlar tekrar işlenmez.' : '',
}
