#!/bin/bash
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
for module in station_common.py dashboard_layout.py adsb_worker.py iss_receiver.py iss_dsp.py; do
    install -o root -g root -m 644 "$source_dir/$module" "/opt/radio-center/$module"
done
python3 -c 'import PIL,numpy,ephem'
dpkg-query -W -f='${Status}\n' satdump | /usr/bin/grep -q 'install ok installed'
backup_dir="/opt/radio-center/backups/meteo-$(date -u +%Y%m%d-%H%M%S)"
install -d -m 755 "$backup_dir"
export METEO_SOURCE_DIR="$source_dir" METEO_BACKUP_DIR="$backup_dir"
python3 - <<'PY'
import os,pathlib,re,shutil,subprocess
src=pathlib.Path(os.environ['METEO_SOURCE_DIR']);backup=pathlib.Path(os.environ['METEO_BACKUP_DIR']);dst=pathlib.Path('/opt/radio-center')
for name in ('meteo_common.py','meteo_worker.py','meteo_processing.py','meteo_diagnostics.py','meteo_scheduler.py','eme_scheduler.py','radio_lease.py','iss_auto.py'):
 target=dst/name
 if target.exists():shutil.copy2(target,backup/name)
 shutil.copyfile(src/name,target);target.chmod(0o644)
for target in pathlib.Path('/etc/systemd/system').glob('radio-*.service'):
 text=target.read_text()
 if 'Conflicts=' not in text or target.name=='radio-meteo-rx.service':continue
 updated='\n'.join(line+' radio-meteo-rx.service' if line.startswith(('Conflicts=','After=')) and 'radio-meteo-rx.service' not in line else line for line in text.splitlines())+'\n'
 if text!=updated:shutil.copy2(target,backup/target.name);target.write_text(updated)
for name in ('radio-meteo.service','radio-meteo-rx.service','radio-meteo-tle.service','radio-meteo-tle.timer','radio-meteo-process.service','radio-meteo-process.path'):
 target=pathlib.Path('/etc/systemd/system')/name
 if target.exists():shutil.copy2(target,backup/name)
 shutil.copyfile(src/name,target)
p=pathlib.Path('/etc/sudoers.d/radio-center');text=p.read_text();updated=text
for unit in ('radio-meteo.service','radio-meteo-rx.service'):
 rule='radio-center ALL=(root) NOPASSWD: '+', '.join('/usr/bin/systemctl '+verb+' '+unit for verb in ('start','stop','restart'))
 if rule not in updated:updated+='\n'+rule+'\n'
if updated!=text:
 candidate=backup/'sudoers-new';candidate.write_text(updated);subprocess.run(['visudo','-cf',str(candidate)],check=True);shutil.copy2(p,backup/'radio-center.sudoers');shutil.copyfile(candidate,p);p.chmod(0o440)
# SatDump's per-capture config avoids writing /nonexistent and expensive composite processing.
settings=pathlib.Path('/var/lib/radio-center/meteo-satdump');settings.mkdir(parents=True,exist_ok=True)
s=pathlib.Path('/usr/share/satdump/satdump_cfg.json').read_text()
for key,old,new in [('log_to_file','true','false'),('auto_process_products','true','false')]:
 s,n=re.subn(r'("'+key+r'"\s*:\s*\{[^{}]*?"value"\s*:\s*)'+old,r'\g<1>'+new,s,count=1)
 if n!=1:raise RuntimeError('Unsupported SatDump config: '+key)
s=re.sub(r'("log_level"\s*:\s*\{[^{}]*?"value"\s*:\s*)"trace"',r'\1"info"',s,count=1)
(settings/'satdump_cfg.json').write_text(s)
shutil.chown(settings,user='radio-center',group='radio-center');shutil.chown(settings/'satdump_cfg.json',user='radio-center',group='radio-center')
PY
runuser -u radio-center -- /usr/bin/python3 - <<'PY'
import sys
sys.path.insert(0,'/opt/radio-center')
import meteo_common as c
c.DATA.mkdir(parents=True,exist_ok=True)
if not (c.DATA/'meteo-config.json').exists():c.atomic('meteo-config.json',c.DEFAULT)
c.connect().close();(c.DATA/'meteo-images').mkdir(exist_ok=True);(c.DATA/'meteo-work').mkdir(exist_ok=True);(c.DATA/'meteo-process').mkdir(exist_ok=True)
print('TLE update:',c.update_tles())
print('Upcoming passes:',len(c.position_and_passes(c.load_config())['passes']))
PY
systemctl daemon-reload
systemctl enable --now radio-meteo-tle.timer radio-meteo-process.path
systemctl restart radio-eme.service
bash "$source_dir/deploy-dashboard.sh"
printf 'Meteo installed; backup: %s\n' "$backup_dir"
