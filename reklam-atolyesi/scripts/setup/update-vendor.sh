#!/usr/bin/env bash
# reklam-atolyesi — tek bir vendor repo'sunu yeni commit'e taşımadan ÖNCE farkı gösterir (spec 12.5/7).
#
# Kullanım:
#   update-vendor.sh <plugin-kökü> <owner/repo> <yeni-commit>            → yalnızca farkı gösterir (hiçbir şey değiştirmez)
#   update-vendor.sh <plugin-kökü> <owner/repo> <yeni-commit> --apply    → insan onayından SONRA: vendor-skills.sh içindeki pin'i
#                                                                          günceller ve vendoring'i yeniden çalıştırır
# Kurallar: güncelleme insan onayı ister; OVERRIDES.md korunur ve fark incelendikten sonra elle güncellenir;
# lisans değişmişse kopyalama yapılmaz (vendor-skills.sh lisansı yeniden doğrular).
set -euo pipefail
PLUGIN_ROOT="${1:?plugin kökü}"; REPO="${2:?owner/repo}"; NEW="${3:?yeni commit}"; MODE="${4:-}"
SCRIPT="$PLUGIN_ROOT/scripts/setup/vendor-skills.sh"
LINE=$(grep -n "\"$REPO|" "$SCRIPT" | head -1 | cut -d: -f1) || true
[ -n "$LINE" ] || { echo "Repo vendor listesinde yok: $REPO" >&2; exit 1; }
OLD=$(sed -n "${LINE}p" "$SCRIPT" | cut -d'|' -f2)
PARTS=$(sed -n "${LINE}p" "$SCRIPT" | cut -d'|' -f4 | tr -d '"')
WORK="${TMPDIR:-${TEMP:-/tmp}}/ra-vendor-update-$$"
git clone --quiet --filter=blob:none --no-checkout "https://github.com/$REPO.git" "$WORK"
echo "== $REPO: $OLD → $NEW"
IFS=';' read -ra plist <<< "$PARTS"
paths=(); for p in "${plist[@]}"; do paths+=("${p%%=>*}"); done
git -C "$WORK" diff --stat "$OLD" "$NEW" -- "${paths[@]}" LICENSE LICENSE.md NOTICE NOTICE.md || true
git -C "$WORK" diff "$OLD" "$NEW" -- LICENSE LICENSE.md NOTICE NOTICE.md || true
if [ "$MODE" = "--apply" ]; then
  sed -i "${LINE}s/|$OLD|/|$NEW|/" "$SCRIPT"
  bash "$SCRIPT" "$PLUGIN_ROOT"
  echo "Uygulandı. OVERRIDES.md dosyalarını farka göre gözden geçirin; ardından testler, nötrlük denetimi ve doctor."
else
  echo "Yalnızca fark gösterildi. Onaydan sonra aynı komutu --apply ile çalıştırın."
fi
