#!/bin/bash
# Adds the official statistics uploader; requires consent to this extra upload.
set -euo pipefail
[[ $EUID == 0 ]] || exit 1
command -v git >/dev/null
test -x /usr/local/share/adsbexchange/feed-adsbx
test -f /usr/local/share/adsbexchange/adsbx-uuid
backup_dir="/opt/radio-center/backups/adsbx-stats-$(date -u +%Y%m%d-%H%M%S)"
install -d -m 700 "$backup_dir"
cp -a /usr/local/share/adsbexchange/adsbx-uuid "$backup_dir/adsbx-uuid"
if [[ -d /usr/local/share/adsbexchange-stats ]]; then
    cp -a /usr/local/share/adsbexchange-stats "$backup_dir/previous-stats"
fi
git clone https://github.com/ADSBexchange/adsbexchange-stats.git "$backup_dir/source"
git -C "$backup_dir/source" checkout --detach 11647f27de3eef51fb19bcb39f0dc0b8500a6671
cd "$backup_dir/source"
bash install.sh
systemctl is-active adsbexchange-stats.service
printf 'Statistics uploader installed; Feed UID preserved. Backup: %s\n' "$backup_dir"
