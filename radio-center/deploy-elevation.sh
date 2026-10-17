#!/bin/bash
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
backup_dir="/opt/radio-center/backups/elevation-$(date -u +%Y%m%d-%H%M%S)"
install -d "$backup_dir/static"
for name in station_common.py eme_common.py meteo_common.py iss_auto.py; do
 cp -a "/opt/radio-center/$name" "$backup_dir/$name"
 install -o root -g root -m 644 "$source_dir/$name" "/opt/radio-center/$name"
done
for name in settings.html settings.js eme.html meteo.html iss.html; do
 cp -a "/opt/radio-center/static/$name" "$backup_dir/static/$name"
 install -o root -g root -m 644 "$source_dir/static/$name" "/opt/radio-center/static/$name"
done
# Preserve existing thresholds when adding shared settings, and leave reception uninterrupted.
runuser -u radio-center -- /usr/bin/python3 - <<'PY'
import sys
sys.path.insert(0,'/opt/radio-center')
import station_common as s,eme_common,meteo_common
c=s.load();c['moon_minimum_elevation']=eme_common.load_config()['minimum_elevation'];c['satellite_minimum_elevation']=meteo_common.load_config()['minimum_elevation'];s.atomic('station.json',s.validate(c))
PY
systemctl restart radio-center.service
# Reload monitor code only when idle; never interrupt an active automatic reception.
for unit in radio-eme radio-meteo radio-iss-auto; do
 if systemctl is-active --quiet "$unit.service"; then
  if systemctl is-active --quiet radio-eme-rx.service || systemctl is-active --quiet radio-meteo-rx.service || systemctl is-active --quiet radio-iss.service; then
   echo "Monitor $unit needs restart after current reception."
  else systemctl restart "$unit.service"; fi
 fi
done
