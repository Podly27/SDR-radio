# ADS-B: rozložení a optimalizace 17. 10. 2026

## Web

Desktop má dva sloupce 1:2: vlevo stav a ovládání, tři statistiky pod sebou,
seznam letadel; vpravo mapa. Na mobilu jsou sloupce pod sebou. Historie je
samostatná rozbalovací sekce pod hlavním přehledem.

Živá data se obnovují každé 2 s, obecný stav serveru se sdílí z pětisekundové
cache. Historie SQL se načítá až po otevření a pak nejvýše jednou za 15 s.
Markery se aktualizují na místě; nepřekresluje se celá vrstva při každém dotazu.
ResizeObserver přizpůsobuje Leaflet při změně rozměrů. Zachována povolená
adresa dlaždic `https://tile.openstreetmap.org`, odpovídající CSP.

Dříve byly skryté letouny i polohy starší 60 s. Nově seznam obsahuje příjem
do 5 minut a zvlášť uvádí počet s příjmem do 60 s. Čerstvé polohy do 60 s
jsou zelené; poslední známé polohy do 5 minut oranžové, s uvedeným stářím.
Jejich pohyb se neextrapoluje. Pokud dekodér přestane polohu uvádět, může se
zobrazit pouze skutečná uložená místní poloha do tohoto limitu. Čas cache je
`native_now - seen_pos`, nikoli čas poslední jiné zprávy. Bez dekódované
polohy letadlo zůstává pouze v seznamu. Historie při zastaveném přijímači je
jasně oddělená od živého provozu. Žádné polohy druhého přijímače se nepřebírají.

## Příjem

Stávající dump1090-fa zůstává nativním dekodérem. Je explicitně povolena
jednobitová CRC korekce; dvoubitová není přidána. Nativní automatický zisk
podle dynamického rozsahu je nově výchozí, s limity 20,7–49,6 dB podle
podporovaných kroků tuneru a duty-cycle 20 % pro Pi. Reálný horní krok
na tomto přijímači je 48 dB. Pevný zisk lze vybrat v Nastavení příjmu.

Soubor `adsb-config.json` se týká jen ADS-B. Prázdný počáteční/pevný zisk
použije společnou hodnotu stanoviště. Společné nastavení ani zisk ostatních
aplikací se nemění. Pro změnu již běžícího přijímače je nutný restart ADS-B.
Nový soubor není nutný: při jeho absenci platí adaptivní výchozí nastavení.

RF přehled ukazuje skutečné platné zprávy/s, polohy/min, zisk, šum a ztráty
vzorků. Počet potenciálních preambulí nebo CRC chyb není vydáván za počet
zpráv. Nativní JSON statistiky jsou aktualizovány každých 5 s; rychlost je
průměr z uvedeného statistického intervalu, obvykle poslední celé minuty.

Dokumentace výrobce dekodéru:
https://github.com/flightaware/dump1090/blob/master/README.adaptive-gain.md

## Provozní měření a omezení

Byla pouze čtením prohlédnuta místní mapa druhého přijímače na
`http://192.168.1.40/tar1090/`; nebylo měněno jeho nastavení.
Při souběžném měření asi 60 s přibyly zde 3 zprávy (0,05/s) a na druhém
5 505 zpráv (91,6/s). Druhý měl 9–11 letadel a v tomto vzorku žádné z jejich
poloh nebyly z MLAT. Zde ztráty USB/CPU vzorků byly nulové; samotné zobrazení
ani přetížení Pi proto rozdíl nevysvětluje.

Pětisekundový skutečný IQ záznam při 48 dB zpracovaly dump1090-fa i readsb:
oba 0 platných rámců. ADC měl směrodatnou odchylku přibližně 0,825 z 256 úrovní.
Druhý skutečný vzorek s automatickým zesílením tuneru měl odchylku 2,40 a oba
dekodéry opět 0 rámců. Pozitivní kontrola: oba přečetly stejný syntetický
soubor a každý dekódoval 640 platných ukázkových rámců. readsb byl jen
rozbalen v /tmp pro offline test, nebyla instalována ani spuštěna další služba.
Změna dekodéru tedy na těchto skutečných záznamech neprokázala přínos.

Uživatel potvrdil anténu Diamond X200. Výrobce specifikuje 144/430 MHz:
https://www.diamond-ant.co.jp/english/amateur/antenna/ante_2base/ante_base3.html
Na 1090 MHz není její zisk a směrový diagram tímto údajem garantován.
15 cm drát na druhém přijímači je délkou blízko půlvlně na 1090 MHz
(asi 13,75 cm) a může tam být účinnější. Anténa/přívod je hlavní podezření,
nikoli změřená jednotlivá příčina. Rozliší to prohození antén či vyzkoušení
stejné krátké antény přímo na tomto RTL-SDR. Bez tohoto fyzického ověření
nelze slíbit srovnatelný příjem ani určit přesnou ztrátu antény nebo kabelu.

Příjem zůstává výrazně slabší než na druhém zařízení. Optimalizace softwaru
nejsou vydávány za vyřešení rozdílu v RF příjmu.

## Ověření a nasazení

Prošlo 55 Python testů, včetně cache polohy se skutečným časem, omezení
stáří, lokální volby zisku a výpočtu statistik. Node test ověřuje čerstvé a
staré markery, zachování jejich identity, cache stavu a formulář zisku.
Ověřena dostupnost živého API a platný mapový zdroj.

Změny: `adsb_worker.py`, `server.py`, `static/adsb.html`, `static/adsb.js`,
`static/style.css`. Zálohy nasazení jsou v `/opt/radio-center/backups/`.
Po změně workeru se obnoví běžící ADS-B a po změně serveru jen webová služba.
Nativní přijímač zůstává používán přes stávající konflikt a mechanismus návratu.
