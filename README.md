# SDR-radio · Radiové centrum

Webové řídicí centrum pro Raspberry Pi a RTL-SDR. Sdružuje OpenWebRX,
samostatné rádiové dekodéry, historii zpráv, mapy a automatický příjem při
přeletech družic nebo vhodné elevaci Měsíce. Projekt je určený **pouze pro příjem**.

Záloha stanice OK2IKT, Lichnov, stav k 17. 10. 2026. Jde o existující projekt
pro Debian 13 arm64 s OpenWebRX+, nikoli o obraz celé SD karty ani univerzální
instalační balíček pro libovolný systém.

## Aplikace

| Aplikace | Funkce |
|---|---|
| OpenWebRX | Poslech s vodopádem, pásmové profily a záložky; stav posluchačů a naladění |
| FT8 / FT4 | Textové dekódování HF, 2 m a 70 cm, historie, SNR |
| Q65 / JT65 · EME | 90kHz příjem jednoho pásma, monitor Měsíce, více podrežimů podle zvolené strategie |
| MSK144 | Meteor scatter na 2 m / 70 cm |
| APRS / LoRa APRS | Pakety, historie a mapa přijatých poloh |
| ISM | rtl_433 pro 433,92 nebo 868 MHz, měření čidel a historie |
| Radiosondy | Dekódování podporovaných sond, telemetrie a mapa |
| VDL2 | Letecké datové zprávy a mapa dostupných poloh |
| ADS-B | Místní příjem 1090 MHz, mapa, přehled letadel a RF statistiky |
| ISS receiving | SSTV VHF/UHF, hlas, AFSK 1200 packet, Doppler a předpověď přeletů |
| Meteosatelity | Meteor LRPT, plánování přeletů a galerie dekódovaných snímků |

Jeden RTL-SDR má v jednom okamžiku jediného vlastníka. Automatika ISS,
meteosatelitů a EME umí přijímač dočasně převzít a následně obnovit původní
aplikaci. **Probíhající automatický příjem má přednost** před další automatikou;
ruční volba uživatele ruší původní automatický návrat.

## Nastavení a provoz

- Rozcestník: `/`, nastavení: `/control/settings/`.
- Centrální poloha, značka, časové pásmo, SDR, zisk, ppm a minimální elevace
  Měsíce/družic; pořadí a skrytí panelů.
- Start, stop a restart přijímačů; průběžný stav a historie bez nutnosti desktopu.
- Backend `127.0.0.1:8090`, nginx pro web, OpenWebRX samostatně na portu 8073.
- Zdroj a web se instalují do `/opt/radio-center`; nastavení, SQLite a galerie
  jsou v `/var/lib/radio-center`.
- Služby běží pod samostatným účtem `radio-center`. Ovládání je určeno pro
  důvěryhodnou LAN; web bez další autentizace nevystavuj přímo do internetu.

## Instalace, obnova a dokumentace

1. [Instalace a závislosti](docs/INSTALLATION.md)
2. [Nastavení a provoz](docs/CONFIGURATION.md)
3. [Záloha a obnova](docs/BACKUP-RESTORE.md)
4. [Stav ověření a omezení](docs/VALIDATION.md)
5. [Automatické přebírání přijímače](radio-center/AUTOMATION.md)
6. [EME](radio-center/EME.md), [ISS](radio-center/ISS-RECEIVING.md),
   [Meteor](radio-center/METEOR.md), [ADS-B](radio-center/ADSB-OPTIMIZATION.md)
7. [Použité komponenty a licence](THIRD-PARTY.md)

`configuration/` obsahuje export aktuální konfigurace určený pro obnovu tohoto
stanoviště; **obsahuje jeho polohu a značku**. Přístupové údaje a API klíče jsou
vynechané nebo prázdné. `inventory/` zachycuje systém a verze balíčků.
Historie zpráv a soukromá záloha s přihlašovacími údaji nejsou součástí Gitu.

## Testy

Spouštěj z kořene projektu, s izolovanými daty:

```bash
mkdir -p /tmp/radio-empty-tests
RADIO_DATA=/tmp/radio-empty-tests python3 -m unittest discover -s radio-center/tests -p 'test_*.py'
node radio-center/tests/test_dashboard_controls.js
node radio-center/tests/test_settings_controls.js
node radio-center/tests/test_iss_ui.js
node radio-center/tests/test_adsb_ui.js
```

Testy nejsou důkazem skutečného příjmu všech podporovaných režimů. Příjem závisí
na anténě, signálu, frekvenci, času, kalibraci a konfiguraci daného dekodéru.
