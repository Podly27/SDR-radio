#!/bin/bash
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
backup_dir="/opt/radio-center/backups/iss-receiving-$(date -u +%Y%m%d-%H%M%S)"
install -d -m 755 "$backup_dir"
auto_active=0
manual_active=0
systemctl is-active --quiet radio-iss-auto.service && auto_active=1
if systemctl is-active --quiet radio-iss.service; then
    if ! runuser -u radio-center -- /usr/bin/python3 -c "import sys;sys.path.insert(0,'/opt/radio-center');import radio_lease;sys.exit(0 if radio_lease.owns('iss') else 1)"; then manual_active=1; fi
fi
systemctl stop radio-iss-auto.service
if [ "$manual_active" = 1 ]; then systemctl stop radio-iss.service; fi
for name in iss_receiver.py iss_dsp.py iss_worker.py iss_auto.py server.py dashboard_activity.py; do
    if [ -e "/opt/radio-center/$name" ]; then cp -a "/opt/radio-center/$name" "$backup_dir/$name"; fi
    install -o root -g root -m 644 "$source_dir/$name" "/opt/radio-center/$name"
done
for name in radio-iss.service radio-iss-auto.service; do
    cp -a "/etc/systemd/system/$name" "$backup_dir/$name"
    install -o root -g root -m 644 "$source_dir/$name" "/etc/systemd/system/$name"
done
runuser -u radio-center -- /usr/bin/python3 - <<'PY'
import sys
sys.path.insert(0,'/opt/radio-center')
import iss_auto,aprs_worker
iss_auto.common.atomic('iss-auto-config.json',iss_auto.load_config())
aprs_worker.connect('iss-packet').close()
PY
install -o root -g root -m 644 "$source_dir/ISS-RECEIVING.md" /opt/radio-center/ISS-RECEIVING.md
systemctl daemon-reload
bash "$source_dir/deploy-dashboard.sh"
if [ "$manual_active" = 1 ]; then systemctl start radio-iss.service; fi
if [ "$auto_active" = 1 ]; then systemctl start radio-iss-auto.service; fi
printf 'ISS receiving installed; backup: %s\n' "$backup_dir"
