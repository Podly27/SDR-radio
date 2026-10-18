#!/bin/bash
# Run only after approving installation of the upstream tar1090 system service.
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
[[ $EUID == 0 ]] || { echo 'Run with sudo bash radio-center/deploy-adsbx.sh' >&2; exit 1; }
config=/etc/nginx/sites-available/openwebrx
test -f "$config"
test -f /opt/radio-center/server.py
command -v dump1090-fa >/dev/null
command -v curl >/dev/null
backup_dir="/opt/radio-center/backups/adsbx-$(date -u +%Y%m%d-%H%M%S)"
install -d -m 755 "$backup_dir/static"
cp -a "$config" "$backup_dir/nginx-openwebrx"
cp -a /opt/radio-center/server.py "$backup_dir/server.py"
for name in index.html adsb.html; do
    cp -a "/opt/radio-center/static/$name" "$backup_dir/static/$name"
done
printf 'Backup: %s\n' "$backup_dir"
if [[ ${1:-} != --finish ]]; then
installer="$backup_dir/tar1090-install.sh"
curl -fsSL https://raw.githubusercontent.com/wiedehopf/tar1090/master/install.sh -o "$installer"
printf '%s  %s\n' 5f1cbfa1561e709f66c29bb1bf18794eb9b1fcfdcf1b00df9f3d97bc2ab9a95f "$installer" | sha256sum -c -
# Same interface used by ADSBexchange, reading only this receiver's JSON.
# The upstream installer fetches tar1090 and its aircraft database and adds
# the tar1090-adsbx history service. It does not install a network feeder.
bash "$installer" /run/radio-adsb adsbx
fi
export RADIO_ADSBX_NGINX="$config"
python3 - <<'PY'
import os,re
from pathlib import Path
upstream=Path('/usr/local/share/tar1090/nginx-tar1090-adsbx.conf')
# Match the existing radio center LAN restriction in every location, including
# nested data locations. Keep this in a separate file across upstream updates.
text=re.sub(r'(location[^\n]*\{)', r'\1\n  allow 127.0.0.1;\n  allow 192.168.1.0/24;\n  deny all;', upstream.read_text())
Path('/etc/nginx/snippets/radio-adsbx.conf').write_text(text)
p=Path(os.environ['RADIO_ADSBX_NGINX']);text=p.read_text()
include='include /etc/nginx/snippets/radio-adsbx.conf;'
if include not in text:
    marker='    # Radio center routes'
    if marker not in text: raise SystemExit('Radio center nginx marker not found')
    text=text.replace(marker, '    '+include+'\n\n'+marker, 1)
    p.write_text(text)
PY
if ! nginx -t; then
    cp -a "$backup_dir/nginx-openwebrx" "$config"
    echo "Nginx configuration restored; tar1090 remains installed. Backup: $backup_dir" >&2
    exit 1
fi
# Publish the link only once the local map is configured and can be served.
systemctl reload nginx
curl --noproxy '*' -fsS http://127.0.0.1/adsbx/ -o /dev/null
install -o root -g root -m 644 "$source_dir/server.py" /opt/radio-center/server.py
for name in index.html adsb.html; do
    install -o root -g root -m 644 "$source_dir/static/$name" "/opt/radio-center/static/$name"
done
systemctl restart radio-center.service
systemctl is-active tar1090-adsbx.service radio-center.service
printf 'Local ADSBexchange interface ready at /adsbx/; receiver controls: /control/adsb/receiver/\n'
