#!/usr/bin/env bash
# reklam-atolyesi — hazır skill'leri pinlenmiş commit'ten seçici olarak kopyalar (spec 12.4–12.5).
#
# Kullanım: vendor-skills.sh <plugin-kökü> [geçici-klasör]
#   - Her repo, pinlenmiş commit'te geçici klasöre klonlanır (yalnızca okunur; hiçbir dosya çalıştırılmaz).
#   - Yalnızca tablodaki parçalar DÜZ yapıda vendor-skills/<skill-adı>/ altına kopyalanır.
#   - LICENSE/NOTICE korunur, her skill'e UPSTREAM.md yazılır, THIRD_PARTY_NOTICES.md üretilir.
#   - Lisansı belirsiz repo kopyalanmaz (12.5/6); sonucu vendor-skills/vendor.lock.json'a yazılır.
#   - OVERRIDES.md dosyaları bu script tarafından ÜRETİLMEZ: kod incelemesinden sonra elle yazılır ve korunur.
set -euo pipefail

PLUGIN_ROOT="${1:?plugin kökü gerekli}"
WORK="${2:-${TMPDIR:-${TEMP:-/tmp}}/ra-vendor-$$}"
VENDOR="$PLUGIN_ROOT/vendor-skills"
mkdir -p "$VENDOR" "$WORK"

# repo|pin|beklenen lisans|kaynak-yolu=>hedef-skill-adı;...
REPOS=(
  "remotion-dev/skills|0b5db9daae40|verify|skills/remotion-best-practices=>remotion-best-practices;skills/remotion-create=>remotion-create;skills/remotion-render=>remotion-render;skills/remotion-markup=>remotion-markup;skills/remotion-multimedia=>remotion-multimedia;skills/remotion-captions=>remotion-captions;skills/remotion-studio=>remotion-studio;skills/remotion-docs=>remotion-docs;skills/remotion-upgrade=>remotion-upgrade"
  "elevenlabs/skills|81f1eafc65c9|MIT|text-to-speech=>text-to-speech;music=>music;sound-effects=>sound-effects;voice-isolator=>voice-isolator;speech-to-text=>speech-to-text;setup-api-key=>setup-api-key;mcp.json=>elevenlabs-mcp/mcp.json"
  "iart-ai/ad-video-skills|0de0f2a1c1f4|MIT|skills/ad-creative-video=>ad-creative-video;skills/launch-video=>launch-video;skills/testimonial-video=>testimonial-video;scripts=>ad-video-scripts"
  "dlazy-ai/ai-product-video|55501b4f2e74|Apache-2.0|SKILL.md=>ai-product-video/SKILL.md;references=>ai-product-video/references;template=>ai-product-video/template;agents=>ai-product-video/agents;assets/audio=>ai-product-video/assets/audio"
  "smit-vanani/claude-promo-video|4f175c71619e|MIT|skills/promo-video=>promo-video"
  "howseen-ai/claude-motion-design|3d90d349ef3f|MIT|skill/motion-design=>motion-design"
  "Kianzzz/xilo-opus-video|f2cd828e2692|MIT|skills/xilo-opus-video=>xilo-opus-video"
  "crimeacs/product-demo-director|a610beee453d|MIT|SKILL.md=>product-demo-director/SKILL.md;criteria=>product-demo-director/criteria;motion=>product-demo-director/motion;engine=>product-demo-director/engine"
  "digitalsamba/claude-code-video-toolkit|2c99460a5d0c|MIT|.claude/skills/ffmpeg=>ffmpeg"
)

detect_license() { # $1 = repo klasörü → SPDX tahmini ya da NONE
  local d="$1" f
  for f in LICENSE LICENSE.md LICENSE.txt license LICENCE COPYING; do
    if [ -f "$d/$f" ]; then
      if grep -qi "MIT License\|Permission is hereby granted, free of charge" "$d/$f"; then echo MIT; return; fi
      if grep -qi "Apache License" "$d/$f"; then echo Apache-2.0; return; fi
      if grep -qi "Remotion License\|remotion.dev/license" "$d/$f"; then echo Remotion-License; return; fi
      echo "OTHER:$f"; return
    fi
  done
  echo NONE
}

LOCK="$VENDOR/vendor.lock.json"
NOTICES="$VENDOR/THIRD_PARTY_NOTICES.md"
echo "[" > "$LOCK.tmp"
{
  echo "# THIRD_PARTY_NOTICES"
  echo
  echo "reklam-atolyesi plugin'inin \`vendor-skills/\` altına seçici olarak kopyaladığı üçüncü taraf içerik (spec 12.4–12.5)."
  echo "Bu dosyalar Claude Code'a skill olarak kaydedilmez; aşama skill'leri onları \`OVERRIDES.md\`'den sonra dosya olarak okur (5.22)."
  echo "Upstream \`SKILL.md\` dosyaları değiştirilmemiştir. Lisansı belirsiz repo kopyalanmamıştır."
  echo
  echo "| Repo | Commit | Lisans | Alınan parçalar | Durum |"
  echo "|---|---|---|---|---|"
} > "$NOTICES.tmp"

first=1
for entry in "${REPOS[@]}"; do
  IFS='|' read -r repo pin expected parts <<< "$entry"
  name="${repo//\//__}"
  dir="$WORK/$name"
  if [ ! -d "$dir/.git" ]; then
    git clone --quiet --filter=blob:none --no-checkout "https://github.com/$repo.git" "$dir"
  fi
  git -C "$dir" -c advice.detachedHead=false checkout --quiet "$pin"
  full=$(git -C "$dir" rev-parse HEAD)
  lic=$(detect_license "$dir")
  status="vendored"
  if [ "$expected" = "verify" ]; then
    case "$lic" in MIT|Apache-2.0) ;; *) status="not_copied_license_unverified";; esac
  elif [ "$lic" != "$expected" ]; then
    status="not_copied_license_mismatch($lic)"
  fi
  copied=()
  if [ "$status" = "vendored" ]; then
    IFS=';' read -ra plist <<< "$parts"
    for p in "${plist[@]}"; do
      src="${p%%=>*}"; dst="${p##*=>}"
      [ -e "$dir/$src" ] || { echo "UYARI: $repo içinde $src yok" >&2; continue; }
      target="$VENDOR/$dst"
      mkdir -p "$(dirname "$target")"
      rm -rf "$target.tmp-copy"
      cp -r "$dir/$src" "$target.tmp-copy"
      # önceki kopya varsa (güncelleme) OVERRIDES.md korunur
      if [ -d "$target" ] && [ -f "$target/OVERRIDES.md" ]; then cp "$target/OVERRIDES.md" "$target.tmp-copy/OVERRIDES.md"; fi
      rm -rf "$target"; mv "$target.tmp-copy" "$target"
      skill_dir="$VENDOR/${dst%%/*}"
      for lf in LICENSE LICENSE.md LICENSE.txt NOTICE NOTICE.md; do
        [ -f "$dir/$lf" ] && cp "$dir/$lf" "$skill_dir/$lf"
      done
      cat > "$skill_dir/UPSTREAM.md" <<EOF
# UPSTREAM

- Repo: https://github.com/$repo
- Commit: $full (pin \`$pin\`)
- Lisans: $lic
- Alınan parça(lar): bkz. \`vendor-skills/vendor.lock.json\`
- Yerel değişiklik: yok (upstream dosyalar değiştirilmez). Devre dışı kısımlar \`OVERRIDES.md\`'de.
EOF
      copied+=("$src")
    done
  fi
  [ $first -eq 1 ] || echo "," >> "$LOCK.tmp"; first=0
  printf '  {"repo": "%s", "pin": "%s", "commit": "%s", "license": "%s", "status": "%s", "parts": "%s"}' \
    "$repo" "$pin" "$full" "$lic" "$status" "$parts" >> "$LOCK.tmp"
  echo "| [$repo](https://github.com/$repo) | \`$full\` | $lic | ${copied[*]:-—} | $status |" >> "$NOTICES.tmp"
  echo "$repo@$pin -> $status ($lic)"
done
echo "" >> "$LOCK.tmp"; echo "]" >> "$LOCK.tmp"
mv "$LOCK.tmp" "$LOCK"; mv "$NOTICES.tmp" "$NOTICES"
echo "Geçici klonlar: $WORK (inceleme sonrası silinebilir)"
