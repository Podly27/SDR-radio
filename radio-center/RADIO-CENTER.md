# Radiové centrum: společné nastavení, panely a ADS-B

Hlavní stránka `/` má nadpis Radiové centrum. Nabídka **⚙ Nastavení** je
v záhlaví hlavní stránky i jednotlivých aplikací, adresa `/control/settings/`.

## Společné nastavení

`/var/lib/radio-center/station.json` je autoritativní zdroj souřadnic, místa,
značky, výšky pro výpočty, časového pásma a identifikátoru/zisku/ppm RTL-SDR.
První instalace převezme existující údaje EME; nevyměňuje uživatelskou polohu
za jinou. Volitelný Maidenhead lokátor má při ukládání přednost před souřadnicemi.
Výchozí výška 0 m je zjednodušení, lze ji upravit.

EME, předpovědi Meteor/ISS, ADS-B a mapy APRS/LoRa/sond čtou tutéž polohu.
EME zobrazuje společná pole pouze pro přehled; mění se v Nastavení. Specifické
parametry jako hystereze, režimy a frekvence zůstávají v aplikacích,
na které společná stránka odkazuje. Minimální elevace Měsíce a družic jsou nyní společné položky v globálním nastavení. Parametry SDR se načtou při spuštění
přijímače; běžící příjem pro jejich použití restartuj. Změna polohy se projeví
při následujícím výpočtu/obnovení.

`radio-station-sync.service` je omezená root oneshot jednotka: po uložení
zrcadlí validovanou polohu, značku a RTL-SDR parametry do OpenWebRX settings.json,
před změnou zálohuje původní soubor a zachová jeho vlastnictví. OpenWebRX
se kvůli uložení samovolně nerestartuje. `rtl_433` používá pro sériové číslo
odlišný formát `:00000001`, ostatní nástroje přijímají samotné sériové číslo.

## Rozložení panelů

Pořadí a skrytí se ukládá do `dashboard-layout.json`; nastavení je společné
všem prohlížečům. Šipky posouvají panel, zaškrtnutí určuje viditelnost.
Skrytí aplikace nemění její běh ani automatiku. Výchozí rozložení se připraví
příslušným tlačítkem a uloží potvrzením. Validace přijímá jen známé identifikátory,
nově doplněné aplikace automaticky přidává na konec staršího rozložení.

## ISS předpověď

Hlavní panel SSTV z ISS obsahuje současnou elevaci/azimut, odpočet do přeletu,
jeho maximum a konec příjmového okna. Používá společné stanoviště a čerstvé TLE,
výpočet běží nezávisle na otevření prohlížeče. Přelet nezaručuje vysílání SSTV.
Automatické převzetí a návrat popisuje `AUTOMATION.md`.

## ADS-B

`/control/adsb/`, jednotka `radio-adsb.service`, používá již instalovaný
FlightAware dump1090-fa 8.2-1 na 1090 MHz. Pracuje bez síťových vstupů,
feedů, vysílání a bez otevřeného desktopu/prohlížeče. RF jednotka má konflikty
s ostatními přijímači a je zahrnuta do společného mechanismu návratu.

Nativní JSON výstup je v RAM `/run/radio-adsb`; vzorky změněných údajů se
ukládají každých 5 s do `adsb.sqlite`. Web ukazuje mapu, značku/ICAO, výšku,
rychlost, kurz a orientační RSSI sloupce v dBFS (nejde o SNR). Letadla bez
polohy zůstávají v tabulce. Aktuální data jsou odlišena od historie; po zastavení
jsou zobrazeny poslední známé údaje za 24 h. Historie: 7 dní / 100 000 snímků.
Počet zpráv je součet přijatých Mode S rámců, nikoli počet snímků historie.
Oficiální formát: https://github.com/flightaware/dump1090/blob/master/README-json.md

## Nasazení a ověření 17. 10. 2026

`sudo bash radio-center/deploy-center-enhancements.sh` zachová spuštěné
monitory a existující konfiguraci; soubory zálohuje do `/opt/radio-center/backups/`.
ADS-B se po instalaci ani bootu samovolně nespouští, lze jej ovládat z webu.

Prošlo 46 Python testů a oba Node testy ovládání, rozložení a formuláře.
Ukládání rozložení, validace a společné nastavení byly ověřeny také přes živé
HTTP API; původní rozložení bylo po testu vráceno. Mapové endpointy používají
souřadnice z centrálního nastavení. Ověřená synchronizace OpenWebRX.

Skutečný ADS-B přijímač úspěšně otevřel RTL-SDR sériového čísla 00000001,
použil 40,2 dB a −7 ppm a běžel po dobu krátkého testu. V tomto testu nebyla
zachycena letadla; skutečný ADS-B příjem tedy nebyl potvrzen. Samostatný
syntetický IQ test nativního dekodéru rozpoznal platné ukázkové rámce a skončil
řízeně s kódem 0; testovací rámce nejsou vloženy do produkční historie.
ISM byl poté obnoven a ověřen i podle nových skutečně dekódovaných zpráv.

Testy spouštěj s prázdným dočasným datovým adresářem, aby nečetly provozní
nastavení: `RADIO_DATA=/tmp/radio-empty-tests python3 -m unittest discover -s radio-center/tests`.
Dále `node radio-center/tests/test_dashboard_controls.js`,
`node radio-center/tests/test_settings_controls.js` a volitelně
`python3 radio-center/tests/validate_adsb_native.py` (umělý IQ soubor v /tmp,
bez přístupu k SDR).
