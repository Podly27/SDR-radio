#!/bin/bash
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
backup_dir="/opt/radio-center/backups/radio-center-$(date -u +%Y%m%d-%H%M%S)"
install -d -m 755 "$backup_dir/static"
command -v dump1090-fa >/dev/null
monitors=()
for unit in radio-eme.service radio-meteo.service radio-iss-auto.service; do
    if systemctl is-active --quiet "$unit"; then monitors+=("$unit"); fi
done
if [ ${#monitors[@]} -gt 0 ]; then systemctl stop "${monitors[@]}"; fi
systemctl stop radio-return.service
for name in iss_receiver.py iss_dsp.py station_common.py dashboard_layout.py adsb_worker.py station_sync.py server.py dashboard_activity.py sdr_calibration.py eme_common.py eme_scheduler.py meteo_common.py meteo_worker.py meteo_scheduler.py iss_auto.py radio_lease.py aprs_worker.py lora_worker.py vdl2_worker.py sonde_worker.py ism_worker.py ft_worker.py msk_worker.py iss_worker.py; do
    if [ -e "/opt/radio-center/$name" ]; then cp -a "/opt/radio-center/$name" "$backup_dir/$name"; fi
    install -o root -g root -m 644 "$source_dir/$name" "/opt/radio-center/$name"
done
for name in radio-adsb.service radio-station-sync.service; do
    install -o root -g root -m 644 "$source_dir/$name" "/etc/systemd/system/$name"
done
cp -a /etc/sudoers.d/radio-center "$backup_dir/sudoers-old"
export RADIO_ENHANCEMENT_BACKUP="$backup_dir"
python3 - <<'PY'
import os,pathlib,shutil,subprocess
p=pathlib.Path('/etc/sudoers.d/radio-center');text=p.read_text()
for unit,verbs in [('radio-adsb.service',('start','stop','restart')),('radio-station-sync.service',('start',))]:
 rule='radio-center ALL=(root) NOPASSWD: '+', '.join('/usr/bin/systemctl '+v+' '+unit for v in verbs)
 if rule not in text:text+='\n'+rule+'\n'
candidate=pathlib.Path(os.environ['RADIO_ENHANCEMENT_BACKUP'])/'sudoers-new';candidate.write_text(text);subprocess.run(['visudo','-cf',str(candidate)],check=True);shutil.copyfile(candidate,p);p.chmod(0o440)
PY
runuser -u radio-center -- /usr/bin/python3 - <<'PY'
import sys
sys.path.insert(0,'/opt/radio-center')
import station_common as s,dashboard_layout,adsb_worker
if not (s.DATA/'station.json').exists():s.atomic('station.json',s.load())
if not (s.DATA/'dashboard-layout.json').exists():s.atomic('dashboard-layout.json',dashboard_layout.load())
adsb_worker.connect().close()
print('Shared station:',s.home())
PY
for name in RADIO-CENTER.md AUTOMATION.md; do
    install -o root -g root -m 644 "$source_dir/$name" "/opt/radio-center/$name"
done
systemctl daemon-reload
systemctl start radio-station-sync.service
systemctl enable --now radio-return.service
if [ ${#monitors[@]} -gt 0 ]; then systemctl start "${monitors[@]}"; fi
bash "$source_dir/deploy-dashboard.sh"
printf 'Radiové centrum installed; backup: %s\n' "$backup_dir"
