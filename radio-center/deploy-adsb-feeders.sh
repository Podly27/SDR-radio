#!/bin/bash
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
[[ $EUID == 0 ]] || { echo 'Run with sudo bash radio-center/deploy-adsb-feeders.sh' >&2; exit 1; }
command -v dump1090-fa >/dev/null
test -f /opt/radio-center/adsb_worker.py
backup_dir="/opt/radio-center/backups/feeders-$(date -u +%Y%m%d-%H%M%S)"
install -d -m 700 "$backup_dir"
cp -a /opt/radio-center/adsb_worker.py "$backup_dir/adsb_worker.py"
for name in /etc/default/adsbexchange /etc/fr24feed.ini; do
    if [[ -f $name ]]; then cp -a "$name" "$backup_dir/$(basename "$name")"; fi
done
printf 'Backup: %s\n' "$backup_dir"

# Both clients use the existing decoder; no feeder takes ownership of USB.
if ! cmp -s "$source_dir/adsb_worker.py" /opt/radio-center/adsb_worker.py; then
    install -o root -g root -m 644 "$source_dir/adsb_worker.py" /opt/radio-center/adsb_worker.py
    if systemctl is-active --quiet radio-adsb.service; then systemctl restart radio-adsb.service; fi
fi

if [[ ! -f /etc/default/adsbexchange ]]; then
    cat > /etc/default/adsbexchange <<'EOF'
INPUT="127.0.0.1:30005"
INPUT_TYPE="dump1090"
REDUCE_INTERVAL="0.5"
USER="0"
LATITUDE="0"
LONGITUDE="0"
ALTITUDE="0m"
UAT_INPUT="127.0.0.1:30978"
RESULTS=""
RESULTS2=""
RESULTS3=""
RESULTS4=""
PRIVACY="--privacy"
MLATSERVER="feed.adsbexchange.com:31090"
TARGET="--net-connector feed1.adsbexchange.com,30004,beast_reduce_out,feed2.adsbexchange.com,64004"
NET_OPTIONS="--net-heartbeat 60 --net-ro-size 1280 --net-ro-interval 0.2 --net-ro-port 0 --net-sbs-port 0 --net-bi-port 0 --net-bo-port 0 --net-ri-port 0 --net-bind-address 127.0.0.1 --write-json-every 1"
JSON_OPTIONS="--max-range 450 --json-location-accuracy 2 --range-outline-hours 24"
EOF
fi
if [[ ! -x /usr/local/share/adsbexchange/feed-adsbx ]]; then
    if ! command -v pkg-config >/dev/null; then apt-get install -y pkg-config; fi
    install -d -m 755 /usr/local/share/adsbexchange
    git clone --depth 1 https://github.com/ADSBexchange/feedclient.git "$backup_dir/feedclient"
    install -d -m 755 /usr/local/share/adsbexchange/git
    cp -a "$backup_dir/feedclient/." /usr/local/share/adsbexchange/git/
    # Official updater installs/builds the network-only client and service.
    bash /usr/local/share/adsbexchange/git/update.sh
fi
systemctl enable --now adsbexchange-feed.service

if ! command -v fr24feed >/dev/null; then
    case $(dpkg --print-architecture) in
        arm64|armhf) arch=$(dpkg --print-architecture) ;;
        *) echo 'This installer supports FR24 on arm64/armhf only.' >&2; exit 1 ;;
    esac
    package="$backup_dir/fr24feed.deb"
    curl -fsSL "https://repo-feed.flightradar24.com/rpi_binaries/fr24feed_1.0.57-1_${arch}.deb" -o "$package"
    # Keep package startup from selecting a bundled USB decoder.
    systemctl mask fr24feed.service
    apt-get install -y "$package"
fi
systemctl stop fr24feed.service || true
install -d -m 755 /etc/systemd/system/fr24feed.service.d
cat > /etc/systemd/system/fr24feed.service.d/radio-center.conf <<'EOF'
[Service]
# External Beast source: omit USB decoder installation and kernel-module hooks.
ExecStartPre=
ExecStartPre=-/usr/lib/fr24/create_missing_directories.sh
ExecStartPre=/usr/bin/fr24feed --validate-config --config-file=/etc/fr24feed.ini
EOF
systemctl daemon-reload
# The package creates a world-writable empty config; keep it private even
# while awaiting the user's key. The unprivileged fr24 service needs read access.
chown root:fr24 /etc/fr24feed.ini
chmod 640 /etc/fr24feed.ini
if [[ ${1:-} == --prepare ]]; then
    echo "FR24 installed; run this script without --prepare to enter the sharing key locally."
    exit 0
fi
python3 "$source_dir/configure-fr24.py"
systemctl unmask fr24feed.service
systemctl enable --now fr24feed.service
systemctl is-active adsbexchange-feed.service fr24feed.service
printf 'Feeders ready. They receive data while radio-adsb.service is running.\n'
