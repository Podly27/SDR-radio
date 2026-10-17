# Konfigurace a provoz

## Autoritativní nastavení

Web: `/control/settings/`. Soubor: `/var/lib/radio-center/station.json`.
Obsahuje souřadnice, značku, místo, nadmořskou výšku, časové pásmo,
identifikátor SDR, zisk, ppm a společné limity elevace.

- `moon_minimum_elevation`: limit EME. Automatický start přičítá hysterezi
  z EME konfigurace; zastavení používá samotný limit.
- `satellite_minimum_elevation`: společný limit ISS a Meteoru.
- Změna limitů se projeví při dalším vyhodnocení automatiky. Může vyvolat
  start nebo zastavení příjmu.
- Hystereze, režimy, pásma a frekvence zůstávají specifické pro aplikaci.
- Parametry SDR se načítají při startu přijímače. Při změně zisku/ppm restartuj
  příslušný příjem; kvůli nastavení se samočinně nerestartuje OpenWebRX.
- Ukládání společných hodnot spouští `radio-station-sync.service` pro OpenWebRX.

Aktuální hodnoty pro zálohované stanoviště jsou v
`configuration/var/lib/radio-center/station.json`. Nejsou univerzální doporučení.

## Konfigurační soubory

| Soubor v `/var/lib/radio-center` | Účel |
|---|---|
| `station.json` | Společné stanoviště, SDR a elevace |
| `dashboard-layout.json` | Pořadí a viditelnost panelů |
| `eme-config.json` | Pásmo, podrežimy, strategie, hystereze a automatika EME |
| `meteo-config.json` | Družice, frekvence, symbolová rychlost a režim |
| `iss-auto-config.json` | Profil ISS a Doppler |
| `adsb-config.json` | Volitelný ADS-B gain override; bez souboru platí výchozí adaptive |
| `*-tuning.json` | Poslední volba pásma/profilu ostatních dekodérů |
| `*.sqlite` | Historie; není v Gitu |

`*-state.json`, `meteo-run.json` a `radio-lease.json` jsou provozní stav,
nikoli konfigurace pro spuštění na jiném serveru. Při obnově nové instalace
je automaticky nepřenášej.

## Ovládání a automatika

Všechny dostupné aplikace mají Start / Stop / Restart. Spuštění jednoho
přijímače uvolňuje SDR od ostatních. Skrytí karty aplikaci nezastaví.
U automatických příjmů probíhající relace vítězí; po dokončení se obnoví
předchozí přijímač, pokud uživatel mezitím ručně nezvolil jiný.
Viz [AUTOMATION.md](../radio-center/AUTOMATION.md).

ISS profily vybírají **jeden** příjem během přeletu: SSTV 437,550 / 145,800 MHz,
hlas 145,800 MHz, převaděč downlink 437,800 MHz nebo AFSK1200 packet
145,825 / 437,825 MHz. Přelet neznamená, že ISS právě vysílá SSTV.

Meteor M2-4 je v uložené konfiguraci 137,900 MHz, LRPT 72k. Družice může měnit
provozní frekvenci/režim; před příjmem ověř aktuální provoz. Původní default
ve starších skriptech byl 137,100 MHz, proto při obnově použij aktuální export.

## Diagnostika

```bash
systemctl list-units 'radio-*' --all
journalctl -u radio-center -u radio-return -n 100 --no-pager
journalctl -u radio-meteo -u radio-meteo-rx -n 100 --no-pager
journalctl -u radio-eme -u radio-eme-rx -n 100 --no-pager
```

Backend vystavuje místní `/control/api/status`; odpověď obsahuje ovládací token,
proto její celé znění nikam veřejně nevkládej. Změny přes API ověřují token
a původ požadavku. Aplikace nepoužívá účet `rpodolsky` k ovládání služeb;
samostatný `radio-center` má přesně vyjmenované povolené příkazy.
Plné administrátorské NOPASSWD uživatele není podmínkou běhu webu.
