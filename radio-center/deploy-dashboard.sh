#!/bin/bash
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
backup_dir="/opt/radio-center/backups/dashboard-$(date -u +%Y%m%d-%H%M%S)"
python3 -m py_compile "$source_dir/server.py"
install -d -m 755 "$backup_dir/static"
cp -a /opt/radio-center/server.py "$backup_dir/server.py"
for source_file in "$source_dir"/static/*; do
    name=$(basename -- "$source_file")
    if [ -e "/opt/radio-center/static/$name" ]; then cp -a "/opt/radio-center/static/$name" "$backup_dir/static/$name"; fi
    install -o root -g root -m 644 "$source_dir/static/$name" "/opt/radio-center/static/$name"
done
install -o root -g root -m 644 "$source_dir/server.py" /opt/radio-center/server.py
install -o root -g root -m 644 "$source_dir/dashboard_activity.py" /opt/radio-center/dashboard_activity.py
runuser -u radio-center -- /usr/bin/python3 /opt/radio-center/dashboard_activity.py --index
python3 "$source_dir/install-openwebrx-activity.py"
systemctl restart radio-center.service
systemctl is-active radio-center.service
printf 'Dashboard updated; backup: %s\n' "$backup_dir"
