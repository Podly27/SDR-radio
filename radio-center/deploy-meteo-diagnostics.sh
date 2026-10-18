#!/bin/bash
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
if systemctl is-active --quiet radio-meteo-rx.service; then
 echo 'Wait for the current Meteor reception to finish before deploying.' >&2
 exit 1
fi
backup_dir="/opt/radio-center/backups/meteo-diagnostics-$(date -u +%Y%m%d-%H%M%S)"
install -d "$backup_dir"
for name in meteo_common.py meteo_worker.py meteo_processing.py meteo_diagnostics.py; do
 if [ -f "/opt/radio-center/$name" ]; then cp -a "/opt/radio-center/$name" "$backup_dir/$name"; fi
 install -o root -g root -m 644 "$source_dir/$name" "/opt/radio-center/$name"
done
for name in radio-meteo-process.service radio-meteo-process.path; do
 install -o root -g root -m 644 "$source_dir/$name" "/etc/systemd/system/$name"
done
install -d -o radio-center -g radio-center -m 750 /var/lib/radio-center/meteo-process /var/lib/radio-center/meteo-reports /var/lib/radio-center/meteo-diagnostics
systemctl daemon-reload
systemctl enable --now radio-meteo-process.path
systemctl is-active radio-meteo-process.path
