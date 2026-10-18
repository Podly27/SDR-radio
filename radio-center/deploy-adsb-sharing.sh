#!/bin/bash
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
[[ $EUID == 0 ]] || exit 1
backup_dir="/opt/radio-center/backups/sharing-$(date -u +%Y%m%d-%H%M%S)"
install -d -m 700 "$backup_dir/static"
for name in server.py feeder_control.py configure-fr24.py; do
    if [[ -f /opt/radio-center/$name ]]; then cp -a "/opt/radio-center/$name" "$backup_dir/$name"; fi
    install -o root -g root -m 644 "$source_dir/$name" "/opt/radio-center/$name"
done
for name in index.html adsb-sharing.html adsb-sharing.js; do
    if [[ -f /opt/radio-center/static/$name ]]; then cp -a "/opt/radio-center/static/$name" "$backup_dir/static/$name"; fi
    install -o root -g root -m 644 "$source_dir/static/$name" "/opt/radio-center/static/$name"
done
if [[ ${1:-} != --read-only ]]; then
rule='radio-center ALL=(root) NOPASSWD: /usr/bin/python3 /opt/radio-center/feeder_control.py'
printf '%s\n' "$rule" > "$backup_dir/sudoers"
visudo -cf "$backup_dir/sudoers"
install -o root -g root -m 440 "$backup_dir/sudoers" /etc/sudoers.d/radio-adsb-sharing
install -o root -g root -m 644 /dev/null /opt/radio-center/feeder-edit-enabled
fi
systemctl restart radio-center.service
systemctl is-active radio-center.service
printf 'Sharing settings deployed. Backup: %s\n' "$backup_dir"
