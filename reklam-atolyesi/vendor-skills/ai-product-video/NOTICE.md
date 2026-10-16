# NOTICE

**ai-product-video** is a derivative work of the open-source project
**video-shotcraft**.

- Upstream: https://github.com/Vincentwei1021/video-shotcraft
- Upstream license: Apache License 2.0 (full text in [LICENSE](LICENSE))
- Upstream author: Wei Yihao

The shot recipe cards, demo implementations, reusable Remotion components,
production pipeline, aesthetic rules, sound-design methodology and the Ink Press
reference film were all created upstream. This repository re-points the
asset/model layer at the [dlazy](https://dlazy.com) CLI and removes material that
is not ours to redistribute.

As required by Apache-2.0 §4(b), the modifications are listed below.

## Removed

| Content | Reason |
| --- | --- |
| `assets/audio/bgm/` (5 tracks, 24 MB) | Music now comes from `dlazy search_audio` on demand |
| `template/public/` (7.6 MB) | Real page screenshots of a third-party product — not ours to redistribute |
| `jianying-export/` and `references/jianying-export.md` | JianYing (CapCut CN) draft export, outside the dlazy tool chain |
| `assets/brand/` (upstream logo, wordmark, brand board) | Apache-2.0 §6 grants no trademark rights; upstream's "镜刻 / Frame Chisel" identity is its own |
| `gallery/` (static preview site, its 152 mirrored card copies and 68 posters) | Its 209 preview clips exist only on the upstream `gallery-media` release and the site was never deployed; `references/shots/` is now the single source for shot cards |
| `.github/workflows/` | Both workflows depend on the upstream release assets and Pages setup |
| Third-party social badges and star-history in the READMEs | They point at the upstream repository |

## Changed

| File | Change |
| --- | --- |
| `SKILL.md` | Skill renamed to `ai-product-video`; added the `## dlazy 工具链` section (CLI setup, tool cheat sheet, optional voiceover flow); BGM sourcing moved to `dlazy search_audio`; JianYing steps removed |
| `references/pipeline.md` | Stage 6 sources BGM and extra SFX through dlazy and defers the optional voiceover flow to the `## dlazy 工具链` section in `SKILL.md`; JianYing hand-off removed |
| `references/sound-design.md` | BGM selection is now a `dlazy search_audio` query with the upstream selection criteria kept as calibration; `bgm/` directory references removed |
| `assets/audio/ATTRIBUTION.md` | Notes that music is no longer bundled; upstream's music sourcing table retained for provenance |
| `template/TEMPLATE.md` | States that the reference film's assets are not bundled and points at the capture step |
| `references/final-review.md`, `references/guided-free-creation.md` | Shot-name resolution and QA key off `references/shots/` and the demo TSX instead of the removed Gallery index and preview clips |
| `README.md` / `README_CN.md` / `README_JA.md` | dlazy branding, dlazy CLI setup section, updated asset notes and repository tree |
| `.claude-plugin/plugin.json`, `agents/openai.yaml` | dlazy name, author, and icon |

## Unchanged

The 152 shot recipe cards (`references/shots/`), `references/aesthetic-rules.md`,
`references/final-review.md`, `references/guided-free-creation.md`,
`references/music-beat-sync.md`, `references/sequences/`, the 202 demo
implementations (`demos/`), the reusable components (`assets/lib/`), the capture
script (`assets/scripts/`), the 149 bundled SFX (`assets/audio/sfx/`) and the
Ink Press scene sources (`template/src/`) are upstream work,
carried over as-is apart from the naming changes listed above.

## Third-party assets

The SFX under `assets/audio/sfx/` come mainly from [Mixkit](https://mixkit.co/)
(free for commercial use, no attribution required); per-file provenance is in
[assets/audio/ATTRIBUTION.md](assets/audio/ATTRIBUTION.md). Entries marked
**"无法反查，商用前须确认"** were already unresolved upstream — verify them before
shipping a commercial film.

## Trademarks

"dlazy" is a trademark of its owner. This repository does not use the upstream
project's logo, wordmark, or brand identity; Apache-2.0 grants no trademark
rights, and none is claimed here.
