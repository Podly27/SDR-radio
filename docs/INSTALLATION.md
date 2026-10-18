# Instalace na Raspberry Pi

## Předpoklady

Referenční systém je Debian GNU/Linux 13 (trixie), arm64, Raspberry Pi 3,
RTL-SDR.COM v3. Přesný model a verze jsou v `inventory/`.
Projekt předpokládá již funkční OpenWebRX+ a nginx s konfigurací
`/etc/nginx/sites-available/openwebrx`. Samotný `install.sh` neinstaluje OS ani
všechny dekodéry a není určen pro čisté Ubuntu/Windows.

Balíčky OpenWebRX+ a některých dekodérů jsou na tomto serveru z repozitáře
`https://luarvique.github.io/ppa/trixie/`. Při nové instalaci použij pokyny
[správce OpenWebRX+](https://github.com/luarvique/openwebrx), včetně ověření
podpisového klíče. Nepřidávej neověřený klíč a nekopíruj staré repozitáře pro
jinou distribuci. Dostupnost a verze ověř proti `inventory/packages.tsv`.

## Balíčky

Po konfiguraci příslušných APT repozitářů:

```bash
sudo apt update
sudo apt install git nginx sudo rtl-sdr rtl-433 wsjtx direwolf \
  python3 python3-numpy python3-scipy python3-pil python3-ephem python3-csdr \
  dxlaprs-lora sonde-decoders dumpvdl2 dump1090-fa-minimal satdump \
  libfftw3-single3 libgfortran5
```

Samotný balíček OpenWebRX+ je na referenčním systému pojmenován `openwebrx`.
Názvy některých balíčků jsou specifické pro použitý repozitář.
Node.js je potřeba pouze pro testy JavaScriptu, nikoli pro běh webu.

Základní kontrola bez obsazení přijímače:

```bash
python3 -c 'import PIL,numpy,scipy,ephem; from pycsdr.modules import SstvDecoder'
command -v rtl_sdr rtl_fm rtl_433 jt9 direwolf lorarx rs41mod dumpvdl2 dump1090-fa satdump
lsusb
```

Skutečný test `rtl_test` prováděj až po zastavení všech aplikací používajících
RTL-SDR. Přijímač nemohou současně otevřít dva procesy. Ověř přístup přes skupinu
`plugdev`/udev a případnou kolizi s DVB ovladačem; místní diagnostická záloha
obsahuje `/etc/udev/rules.d` a `/etc/modprobe.d`.

## Stažení a instalace projektu

```bash
git clone https://github.com/Podly27/SDR-radio.git
cd SDR-radio
chmod +x radio-center/eme-native/eme-m65
sudo bash radio-center/install.sh
```

Instalátor vytváří účet `radio-center`, kopíruje program do `/opt/radio-center`,
instaluje systemd služby a omezené sudoers pro webovou aplikaci. Upravuje nginx,
kontroluje jeho syntaxi a spouští související nasazovací skripty.
Může restartovat monitory a OpenWebRX při instalaci jeho rozšíření metrik;
instalaci proto prováděj mimo důležitý příjem.

Než zapneš automatiku na jiném stanovišti, uprav souřadnice a identifikaci.
`eme-initial-config.json` je historická konfigurace tohoto stanoviště a není
automatické zjištění tvé polohy. Obnova přesné konfigurace je popsána samostatně
v [BACKUP-RESTORE.md](BACKUP-RESTORE.md).

## Nativní EME dekodér

Přiložená binárka je aarch64. Obnova stejné architektury ji může použít;
jiná architektura vyžaduje kompilaci. Sestavovací skript potřebuje GCC/Fortran 13:

```bash
sudo apt install gcc-13 gfortran-13 cmake ninja-build libfftw3-dev
python3 radio-center/eme-native/build.py "$PWD/.cache/eme-build"
```

Výsledný soubor najdeš v `.cache/eme-build/build/eme-m65`; před instalací ho
zkopíruj do `radio-center/eme-native/eme-m65`. Podrobnosti a omezení:
[EME.md](../radio-center/EME.md).

## Ověření po instalaci

Místní mapu ADSBexchange (tar1090) nainstaluj podle
[ADSBEXCHANGE.md](../radio-center/ADSBEXCHANGE.md). Tento krok je nutný
před použitím nového odkazu ADS-B v radiovém centru.

```bash
sudo nginx -t
sudo visudo -cf /etc/sudoers.d/radio-center
systemctl status radio-center.service --no-pager
systemctl status radio-return.service radio-meteo-tle.timer --no-pager
curl -fsS http://127.0.0.1:8090/control/api/status > /tmp/radio-status.json
```

Otevři IP adresu RPi v prohlížeči. Přístupové rozsahy nginx jsou v exportu
nastavené na `192.168.1.0/24` a loopback; pro jinou LAN je změň.
Výchozí služby po restartu ověř podle `inventory/radio-services.json` a nastav
záměrně. Nezapínej současně více výchozích vlastníků SDR. Monitory jsou oddělené
od vlastních přijímacích procesů a mohou čekat bez obsazení USB.
