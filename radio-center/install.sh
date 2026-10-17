#!/bin/bash
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
python3 -c 'import PIL,numpy; from pycsdr.modules import SstvDecoder'
getent passwd radio-center >/dev/null || useradd --system --home-dir /nonexistent --shell /usr/sbin/nologin radio-center
install -d -o root -g root -m 755 /opt/radio-center /opt/radio-center/static
for module in station_common.py dashboard_layout.py adsb_worker.py iss_receiver.py iss_dsp.py; do
    install -o root -g root -m 644 "$source_dir/$module" "/opt/radio-center/$module"
done
for module in radio_lease.py iss_auto.py meteo_common.py; do
    install -o root -g root -m 644 "$source_dir/$module" "/opt/radio-center/$module"
done
install -o root -g root -m 644 "$source_dir/server.py" /opt/radio-center/server.py
install -o root -g root -m 644 "$source_dir/dashboard_activity.py" /opt/radio-center/dashboard_activity.py
install -o root -g root -m 644 "$source_dir/ism_worker.py" /opt/radio-center/ism_worker.py
install -o root -g root -m 644 "$source_dir/radio-ism.service" /etc/systemd/system/radio-ism.service
install -o root -g root -m 644 "$source_dir/iss_worker.py" /opt/radio-center/iss_worker.py
install -o root -g root -m 644 "$source_dir/radio-iss.service" /etc/systemd/system/radio-iss.service
install -o root -g root -m 644 "$source_dir/aprs_worker.py" /opt/radio-center/aprs_worker.py
install -o root -g root -m 644 "$source_dir/radio-aprs.service" /etc/systemd/system/radio-aprs.service
install -o root -g root -m 644 "$source_dir/ft_worker.py" /opt/radio-center/ft_worker.py
install -o root -g root -m 644 "$source_dir/ft_profiles.py" /opt/radio-center/ft_profiles.py
install -o root -g root -m 644 "$source_dir/sdr_calibration.py" /opt/radio-center/sdr_calibration.py
install -o root -g root -m 644 "$source_dir/weak_profiles.py" /opt/radio-center/weak_profiles.py
for profile in $(PYTHONPATH="$source_dir" python3 -c 'from weak_profiles import PROFILES; print(" ".join(PROFILES))'); do
    install -o root -g root -m 644 "$source_dir/radio-weak@$profile.service" "/etc/systemd/system/radio-weak@$profile.service"
done
for profile in $(PYTHONPATH="$source_dir" python3 -c 'from ft_profiles import PROFILES; print(" ".join(PROFILES))'); do
    install -o root -g root -m 644 "$source_dir/radio-ft@$profile.service" "/etc/systemd/system/radio-ft@$profile.service"
done
install -o root -g root -m 644 "$source_dir/msk_worker.py" /opt/radio-center/msk_worker.py
for profile in 2m-msk144 70cm-msk144; do
    install -o root -g root -m 644 "$source_dir/radio-msk@$profile.service" "/etc/systemd/system/radio-msk@$profile.service"
done
install -o root -g root -m 644 "$source_dir/lora_worker.py" /opt/radio-center/lora_worker.py
install -o root -g root -m 644 "$source_dir/radio-lora.service" /etc/systemd/system/radio-lora.service
install -o root -g root -m 644 "$source_dir/vdl2_worker.py" /opt/radio-center/vdl2_worker.py
install -o root -g root -m 644 "$source_dir/radio-vdl2.service" /etc/systemd/system/radio-vdl2.service
install -o root -g root -m 644 "$source_dir/sonde_worker.py" /opt/radio-center/sonde_worker.py
install -o root -g root -m 644 "$source_dir/radio-sonde.service" /etc/systemd/system/radio-sonde.service
install -d -o radio-center -g radio-center -m 750 /var/lib/radio-center
for module in eme_common.py eme_scheduler.py eme_worker.py; do
    install -o root -g root -m 644 "$source_dir/$module" "/opt/radio-center/$module"
done
if [ ! -x "$source_dir/eme-native/eme-m65" ]; then
    echo 'Missing native decoder: run eme-native/build.py and copy its eme-m65 output into eme-native/.' >&2
    exit 1
fi
install -o root -g root -m 755 "$source_dir/eme-native/eme-m65" /opt/radio-center/eme-m65
install -o root -g root -m 644 "$source_dir/eme-native/COPYING" /opt/radio-center/eme-m65-COPYING
for unit in radio-eme.service radio-eme-rx.service; do
    install -o root -g root -m 644 "$source_dir/$unit" "/etc/systemd/system/$unit"
done
if [ ! -e /var/lib/radio-center/eme-config.json ]; then
    install -o radio-center -g radio-center -m 600 "$source_dir/eme-initial-config.json" /var/lib/radio-center/eme-config.json
fi
install -o root -g root -m 644 "$source_dir/static/"* /opt/radio-center/static/
visudo -cf "$source_dir/radio-center.sudoers"
install -o root -g root -m 440 "$source_dir/radio-center.sudoers" /etc/sudoers.d/radio-center
install -o root -g root -m 644 "$source_dir/radio-center.service" /etc/systemd/system/radio-center.service
config=/etc/nginx/sites-available/openwebrx
backup="$config.backup-$(date +%Y%m%d-%H%M%S)"
cp -a "$config" "$backup"
python3 - <<'PY'
from pathlib import Path
p=Path('/etc/nginx/sites-available/openwebrx')
s=p.read_text()
if '# Radio center routes' not in s:
 routes='''
    # Radio center routes: other OpenWebRX paths keep their existing proxy.
    location = / {
        allow 127.0.0.1;
        allow 192.168.1.0/24;
        deny all;
        proxy_pass http://127.0.0.1:8090;
        proxy_set_header Host $http_host;
    }
    location /control/ {
        allow 127.0.0.1;
        allow 192.168.1.0/24;
        deny all;
        proxy_pass http://127.0.0.1:8090;
        proxy_set_header Host $http_host;
        proxy_read_timeout 50s;
    }
'''
 s=s.replace('\tlocation / {',routes+'\n\tlocation / {',1)
 p.write_text(s)
PY
if ! nginx -t; then cp -a "$backup" "$config"; exit 1; fi
runuser -u radio-center -- /usr/bin/python3 /opt/radio-center/dashboard_activity.py --index
python3 - <<'PY'
from pathlib import Path
for p in Path("/etc/systemd/system").glob("radio-*.service"):
 s=p.read_text()
 if p.name!="radio-iss.service" and "Conflicts=" in s:
  p.write_text("\n".join(line+" radio-iss.service" if line.startswith(("Conflicts=","After=")) and "radio-iss.service" not in line else line for line in s.splitlines())+"\n")
PY
systemctl daemon-reload
systemctl enable radio-center
systemctl restart radio-center
systemctl reload nginx
systemctl enable radio-eme
systemctl restart radio-eme
systemctl is-enabled radio-eme
systemctl is-active radio-center radio-eme
printf 'Installed. Nginx backup: %s\n' "$backup"

# Meteor LRPT: install the Debian satdump package before this step.
bash "$source_dir/deploy-meteo.sh"

bash "$source_dir/deploy-automation.sh"

bash "$source_dir/deploy-center-enhancements.sh"
