#!/bin/bash
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
for module in station_common.py dashboard_layout.py adsb_worker.py iss_receiver.py iss_dsp.py; do
    install -o root -g root -m 644 "$source_dir/$module" "/opt/radio-center/$module"
done
python3 -c 'import PIL,numpy; from pycsdr.modules import SstvDecoder'
backup_dir="/opt/radio-center/backups/iss-$(date -u +%Y%m%d-%H%M%S)"
install -d -m 755 "$backup_dir"
export ISS_SOURCE_DIR="$source_dir" ISS_BACKUP_DIR="$backup_dir"
python3 - <<'PY'
import os,pathlib,shutil,subprocess
src=pathlib.Path(os.environ['ISS_SOURCE_DIR']);backup=pathlib.Path(os.environ['ISS_BACKUP_DIR'])
for name in ('iss_worker.py','eme_scheduler.py'):
 target=pathlib.Path('/opt/radio-center')/name
 if target.exists():shutil.copy2(target,backup/name)
 shutil.copyfile(src/name,target);target.chmod(0o644)
for target in pathlib.Path('/etc/systemd/system').glob('radio-*.service'):
 text=target.read_text()
 if 'Conflicts=' not in text:continue
 updated='\n'.join(line+' radio-iss.service' if line.startswith(('Conflicts=','After=')) and 'radio-iss.service' not in line else line for line in text.splitlines())+'\n'
 if text!=updated:shutil.copy2(target,backup/target.name);target.write_text(updated)
shutil.copyfile(src/'radio-iss.service','/etc/systemd/system/radio-iss.service')
p=pathlib.Path('/etc/sudoers.d/radio-center');text=p.read_text();rule='radio-center ALL=(root) NOPASSWD: /usr/bin/systemctl start radio-iss.service, /usr/bin/systemctl stop radio-iss.service, /usr/bin/systemctl restart radio-iss.service'
if rule not in text:
 shutil.copy2(p,backup/'radio-center.sudoers');candidate=backup/'sudoers-new';candidate.write_text(text+'\n'+rule+'\n');subprocess.run(['visudo','-cf',str(candidate)],check=True);shutil.copyfile(candidate,p);p.chmod(0o440)
PY
runuser -u radio-center -- /usr/bin/python3 -c 'import sys; sys.path.insert(0,"/opt/radio-center"); import iss_worker; iss_worker.DATA.mkdir(parents=True,exist_ok=True); iss_worker.connect().close(); iss_worker.Frames()'
systemctl daemon-reload
systemctl restart radio-eme.service
bash "$source_dir/deploy-dashboard.sh"
printf 'ISS SSTV installed; backup: %s\n' "$backup_dir"
