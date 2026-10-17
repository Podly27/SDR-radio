# Automatické převzetí a návrat RTL-SDR

EME, meteosatelity a ISS mohou ve svém automatickém režimu dočasně pozastavit
jinou přijímací aplikaci. Po skončení okna obnoví předchozí službu včetně
konkrétního profilu FT8/FT4, MSK144 nebo Q65/JT65. Nastavení frekvence zůstává
v uložených souborech aplikací. Pokud před převzetím nic neběželo, nic se
poté nespouští. OpenWebRX po návratu znovu přijímá připojení; existující
websocket/audio relace posluchačů se restartem služby přeruší.

**Probíhající automatický příjem má přednost.** Další automatika čeká a může
začít, pokud po jeho skončení ještě trvá její vlastní okno. Převzetí se
nezanořují. Při současném požadavku rozhodne první získaný společný zámek.

Ruční spuštění nebo restart jiné přijímací aplikace z webu zruší naplánovaný
návrat. Automatika již nezasáhne v aktuálním okně; nové okno nebo výslovné
opětovné zapnutí automatiky ji znovu povolí. Zastavení automatického monitoru
ukončí jeho příjem a vrátí předchozí aplikaci.

## Ovládání

- Meteosatelity: Spustit na hlavním panelu zapne automatické přelety.
- EME: automatický režim v nastavení; start 17°, stop 15° při současném
  nastavení. Ruční start obchází elevaci. Výpočet vychází z uloženého stanoviště.
- ISS: na `/control/iss/` tlačítko pro automatické přelety; samostatná tlačítka
  přijímače spouštějí ruční příjem. Nastavitelná minimální elevace, výchozí 10°.
  Frekvence 145,800 nebo 437,550 MHz podle konkrétní akce ARISS. Přelet je pouze
  příležitost k poslechu, **nezaručuje vysílání SSTV**. Doppler se automaticky
  neladí. Aktualizace TLE používá společný šestihodinový časovač.

Na hlavní stránce se dočasně uvolněná aplikace označí „Pozastaveno“ a ukáže,
na který automatický příjem čeká. Ruční Spustit umožňuje převzít ovládání.

## Provoz a obnova

`radio_lease.py` ukládá vlastníka, konec okna a původní systemd jednotku do
`/var/lib/radio-center/radio-lease.json`, používá procesový `flock` a atomickou
výměnu souboru. `radio-return.service` běží po restartu a kontroluje stav každé
2 sekundy. Vrací přijímač také při pádu dekodéru nebo zastavení monitoru;
pokud obnova selže, ponechá záznam pro další pokus. Novou ruční volbu nepřepisuje.

EME monitor zůstává povolený po bootu. Monitory Meteor a ISS se ve výchozím
stavu zapínají ručně; ochranná služba návratu a aktualizace TLE běží po bootu.
Monitory i příjem pracují bez otevřeného prohlížeče.

Nasazení: `sudo bash radio-center/deploy-automation.sh`. Skript zálohuje
nahrazované soubory a zachová spuštění existujících monitorů. Jednotkové testy:
`python3 -m unittest discover -s radio-center/tests -p 'test_*.py'`.

Testy koordinátoru simulují systemd, překryvy, chyby a ruční přepnutí.
Zkouška převzetí skutečných služeb s umělým časovým oknem je odlišná od
příjmu reálného satelitního nebo EME signálu.
