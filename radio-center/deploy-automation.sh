#!/bin/bash
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
for module in station_common.py dashboard_layout.py adsb_worker.py iss_receiver.py iss_dsp.py; do
    install -o root -g root -m 644 "$source_dir/$module" "/opt/radio-center/$module"
done
backup_dir="/opt/radio-center/backups/automation-$(date -u +%Y%m%d-%H%M%S)"
install -d -m 755 "$backup_dir"
meteo_active=0
iss_auto_active=0
systemctl is-active --quiet radio-meteo.service && meteo_active=1
systemctl is-active --quiet radio-iss-auto.service && iss_auto_active=1
systemctl list-units --all --type=service --output=json > "$backup_dir/services.json"
# Stop monitors before replacing their implementation; they return any borrowed SDR.
systemctl stop radio-meteo.service radio-eme.service
if [ "$iss_auto_active" = 1 ]; then systemctl stop radio-iss-auto.service; fi
for name in radio_lease.py iss_auto.py meteo_common.py meteo_scheduler.py eme_scheduler.py iss_worker.py; do
    if [ -e "/opt/radio-center/$name" ]; then cp -a "/opt/radio-center/$name" "$backup_dir/$name"; fi
    install -o root -g root -m 644 "$source_dir/$name" "/opt/radio-center/$name"
done
for name in radio-iss-auto.service radio-return.service; do
    if [ -e "/etc/systemd/system/$name" ]; then cp -a "/etc/systemd/system/$name" "$backup_dir/$name"; fi
    install -o root -g root -m 644 "$source_dir/$name" "/etc/systemd/system/$name"
done
for name in AUTOMATION.md EME.md ISS-SSTV.md METEOR.md; do
    install -o root -g root -m 644 "$source_dir/$name" "/opt/radio-center/$name"
done
export AUTOMATION_BACKUP_DIR="$backup_dir"
python3 - <<'PY'
import os,pathlib,shutil,subprocess
p=pathlib.Path('/etc/sudoers.d/radio-center');text=p.read_text()
rule='radio-center ALL=(root) NOPASSWD: '+', '.join('/usr/bin/systemctl '+v+' radio-iss-auto.service' for v in ('start','stop','restart'))
if rule not in text:
 candidate=pathlib.Path(os.environ['AUTOMATION_BACKUP_DIR'])/'sudoers-new';candidate.write_text(text+'\n'+rule+'\n');subprocess.run(['visudo','-cf',str(candidate)],check=True);shutil.copy2(p,candidate.parent/'sudoers-old');shutil.copyfile(candidate,p);p.chmod(0o440)
PY
runuser -u radio-center -- /usr/bin/python3 - <<'PY'
import sys
sys.path.insert(0,'/opt/radio-center')
import iss_auto,meteo_common
if not (meteo_common.DATA/'iss-auto-config.json').exists():meteo_common.atomic('iss-auto-config.json',iss_auto.DEFAULT)
print('TLE:',meteo_common.update_tles())
print('ISS passes:',len(iss_auto.orbit()['passes']))
PY
systemctl daemon-reload
systemctl enable --now radio-return.service
systemctl restart radio-eme.service
if [ "$meteo_active" = 1 ]; then systemctl start radio-meteo.service; fi
if [ "$iss_auto_active" = 1 ]; then systemctl start radio-iss-auto.service; fi
bash "$source_dir/deploy-dashboard.sh"
printf 'Automation installed; backup: %s\n' "$backup_dir"
