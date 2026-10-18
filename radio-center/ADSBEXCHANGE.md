# Místní rozhraní ADSBexchange

Hlavní ADS-B aplikaci nahrazuje tar1090, které používá také oficiální
[instalátor místního rozhraní ADSBexchange](https://github.com/ADSBexchange/feedclient/blob/master/install-or-update-interface.sh).
Příjem z RTL-SDR nadále zajišťuje dump1090-fa spuštěný službou radio-adsb.
tar1090 čte `/run/radio-adsb`, nepřebírá USB a zobrazuje místní data.
Není to celosvětová mapa ani instalace služby pro odesílání dat ADSBexchange.

## Volitelné odesílání do ADSBexchange a Flightradar24

```bash
sudo bash radio-center/deploy-adsb-feeders.sh
```

Skript nainstaluje oficiální síťový klient ADSBexchange a balíček FR24 pro
arm64/armhf. Zpřístupní Beast výstup dekodéru pouze na `127.0.0.1:30005`;
ostatní vstupní i výstupní porty dekodéru jsou vypnuté. Feedery nemají vlastní
SDR dekodér. Při přepnutí přijímače na jinou aplikaci nemají nová data a při
návratu ADS-B se znovu připojí.

Sharing key Flightradar24 se zadává skrytě v terminálu a ukládá pouze do
`/etc/fr24feed.ini` s právy 640 (root:fr24). Klíč se nezobrazuje ve webu ani výstupu.
Existující klíč se zachová. Varianta `--prepare` provede instalaci bez zadání
klíče a nechá FR24 zastavený; dokončení se provede stejným příkazem bez volby.
FR24 webová administrace je přístupná jen na loopbacku (port 8754).

MLAT je pro nové konfigurace vypnuté v obou sítích; nastavení ADSBexchange
neodesílá přesnou polohu antény. Existující konfigurace ADSBexchange se
nepřepisuje. FR24 má MLAT vypnuté podle doporučení provozovatele pro souběžné
sdílení do více sítí. Zapnutí MLAT ADSBexchange později vyžaduje přesnou
polohu a výšku antény.

Stav ověř pomocí `systemctl status adsbexchange-feed fr24feed` a
`journalctl -u adsbexchange-feed -u fr24feed --since '5 minutes ago'`.
Aktivní služba sama o sobě nepotvrzuje přijetí dat vzdáleným serverem:
zkontroluj také [ADSBexchange myip](https://www.adsbexchange.com/myip/)
a svůj [FR24 účet](https://www.flightradar24.com/account/data-sharing).
Feeder lze vypnout pomocí `sudo systemctl disable --now adsbexchange-feed`
nebo `sudo systemctl disable --now fr24feed`. Zálohy konfigurací v adresáři
`/opt/radio-center/backups/feeders-*` jsou soukromé a mohou obsahovat klíč.

## Nasazení

Na stávajícím Debian/RPi s nainstalovaným radiovým centrem:

```bash
sudo bash radio-center/deploy-adsbx.sh
```

Skript stáhne upstream instalátor a ověří jeho SHA256. Ten stáhne aktuální
tar1090 a databázi letadel, vytvoří účet a službu `tar1090-adsbx` pro historii
a může doinstalovat git, jq a curl. Na systémech s lighttpd může upravit také
jeho konfiguraci. Instalaci prováděj se souhlasem k těmto systémovým změnám.
Změní-li se hash upstream instalátoru, nejprve zkontroluj jeho změny; kontrolu
nevynechávej.

Nasazovací skript přidá místní mapu do nginx se stejným omezením na loopback
a LAN `192.168.1.0/24` jako radiové centrum. Pro jinou LAN uprav pravidla
v tomto skriptu i stávající konfiguraci radiového centra. Před zveřejněním
odkazu ověří nginx a dostupnost mapy. Zálohy jsou v
`/opt/radio-center/backups/adsbx-<UTC čas>`.

- `/control/adsb/` přesměruje na místní mapu `/adsbx/`.
- `/control/adsb/receiver/` zachovává zisk, diagnostiku a původní SQL historii.
- Start/stop/restart na hlavní stránce stále ovládá `radio-adsb.service`.
- `tar1090-adsbx.service` udržuje mapovou historii bez přístupu k RTL-SDR.

Po instalaci ověř `systemctl status tar1090-adsbx radio-center`, otevři mapu,
spusť příjem z hlavní stránky a ověř `/adsbx/data/aircraft.json` a
`/adsbx/data/receiver.json`. Test příjmu vyžaduje dostupný RTL-SDR a provoz
v dosahu. Mapové podklady vyžadují internet. Při zastavení příjmu se živá
data přestanou obnovovat; historii tar1090 nemaže zastavení dekodéru.

## Návrat

Z příslušné zálohy obnov `server.py` a oba soubory v `static/` do
`/opt/radio-center`, soubor `nginx-openwebrx` do
`/etc/nginx/sites-available/openwebrx`. Ověř `nginx -t`, restartuj
`radio-center` a načti znovu nginx. Volitelně zastav a zakaž službu
`tar1090-adsbx`. Příjem a uložená SQL historie se při migraci nemění.

## Webový přehled sdílení

`/control/adsb/sharing/` nahrazuje odkaz „Nastavení příjmu“ na hlavní stránce.
Ukazuje stav služeb i spojení, identifikaci radaru FR24, poslední odeslání,
stav uloženého klíče a odkazy na ověření v obou sítích. Stav ADSBexchange
pochází z čerstvých metrik jeho síťových konektorů; stav FR24 z místního
`monitor.json`. Syrové FR24 API obsahuje klíč, proto backend vrací výhradně
vybrané provozní údaje a informaci, zda je klíč uložený.

Nasazení přehledu bez rozšíření oprávnění:

```bash
sudo bash radio-center/deploy-adsb-sharing.sh --read-only
```

Změny klíče a povolení služeb jsou v této variantě neaktivní. Po výslovném
schválení správy z webu lze spustit stejný skript bez `--read-only`.
Vytvoří pravidlo `/etc/sudoers.d/radio-adsb-sharing`, které dovoluje účtu
`radio-center` spustit pouze pevný pomocný program
`/usr/bin/python3 /opt/radio-center/feeder_control.py` jako root bez hesla.
Ten přijímá JSON přes stdin, ověřuje klíč a pracuje jen se dvěma pevnými
službami a konfigurací FR24. Klíč nevypisuje a ponechává soubor root:fr24 640.
Přehled ani nasazení nevyvolají změnu klíče nebo odesílání bez uložení formuláře.

## Statistiky a MLAT ADSBexchange

Přehled sdílení ukazuje existující Feed UID, samostatný stav statistické služby
aby bylo zřejmé, zda je balíček instalovaný, a přímý odkaz na statistiky tohoto
přijímače. Stav „Služba běží“ nepotvrzuje registraci ani MLAT synchronizaci.

Oficiální uploader statistik lze po výslovném souhlasu s dodatečným odesíláním
nainstalovat pomocí `sudo bash radio-center/deploy-adsbx-stats.sh`.
Používá prověřenou revizi upstream balíčku a zachovává stávající UUID.
Odesílá JSON letadel z feederu, identifikátor a stav throttlingu Raspberry Pi
na `https://adsbexchange.com/api/receive/`.

MLAT lze zapnout skriptem `enable-adsbx-mlat.py` nainstalovaným vedle
`station_common.py` v `/opt/radio-center` a spuštěným jako root. Přebírá
souřadnice a výšku antény z globálního nastavení. Při pozdější změně polohy
nebo výšky je nutné tento skript znovu spustit; synchronizace není automatická.
Flightradar24 zůstává bez MLAT. Vypnutí odesílání ADSBexchange ve webu vypne
rovněž nainstalované služby statistik a MLAT; zapnutí je obnoví, pokud je
MLAT nakonfigurované. Serverová synchronizace závisí i na kvalitě příjmu a
okolních přijímačích.
