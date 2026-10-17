# Historické vývojové poznámky

Tento dokument zachycuje postupný vývoj. Některé popisy první etapy a dřívější výchozí hodnoty už neplatí. Aktuální popis je v kořenovém README a docs/.

# RADIO SERVER — Řídicí centrum

Lokální web na Raspberry Pi `192.168.1.39`, vzhled navazuje na HOME SERVER `192.168.1.30`.

## Nasazená první etapa

- Úvodní stránka: http://192.168.1.39/
- Samostatný přijímač: http://192.168.1.39:8073/
- Start, stop a restart OpenWebRX; automatické spouštění OpenWebRX při bootu se těmito tlačítky nemění.
- Stav služby a USB, uptime, load, RAM, teplota a disk; obnovení po 10 sekundách.
- Karty FT8/FT4, MSK144, APRS 2 m, LoRa APRS a ISM jsou zatím plánované; nedekódují ani neukládají historii.

## Provoz

Zdrojové soubory jsou v tomto adresáři. Instalace kopíruje aplikaci do `/opt/radio-center` a vytváří systemd službu `radio-center.service`. Backend poslouchá pouze na `127.0.0.1:8090`. Nginx předává přesné `/` a `/control/` této aplikaci; ostatní původní cesty nadále předává původnímu OpenWebRX upstreamu. Původní nginx konfigurace je zálohovaná vedle originálu.

Aplikace používá pouze standardní knihovnu Pythonu. Běží pod samostatným účtem `radio-center`. Sudoers povoluje jen tři přesné operace na `openwebrx.service`. Nginx omezuje přístup na loopback a `192.168.1.0/24`. V této první etapě jde o správu pro důvěryhodnou domácí síť bez přihlášení; zařízení v této síti mohou službu ovládat. POST vyžaduje token a ověřuje původ požadavku.

```bash
sudo bash /home/rpodolsky/OpenWebRX/radio-center/install.sh
sudo systemctl status radio-center
sudo journalctl -u radio-center
```

## Ověření nasazení

Ověřeny odpovědi HTTP, skutečný stop/start OpenWebRX přes API, dostupnost rozcestníku po zastavení OpenWebRX a odmítnutí požadavků bez tokenu, s cizím Origin a s nepovolenou operací. Syntaxe Python/JS, nginx konfigurace a sudoers prošly kontrolou. Vzhled nebyl automaticky ověřen prohlížečem.

## Další etapy

1. Společný správce RTL-SDR: jen jeden vlastník a naladěný úsek v čase. Přechod na samostatný dekodér musí řešit běžící OpenWebRX.
2. Jednotné ukládání dekódovaných událostí do SQLite: UTC čas, dekodér, pásmo/frekvence, stanice, obsah a původní payload. Retence, export a filtrování historie.
3. Připojit dekodéry postupně: FT8/FT4 a MSK144 z dostupných dekodérů, APRS audio/packet, ISM přes rtl_433; LoRa potřebuje ověřit kompatibilní SDR dekodér a parametry modulace.
4. Textové stránky budou zobrazovat skutečná data bez vodopádu, historii s stránkováním a jednoznačný stav příjmu.

Konkrétní pořadí dekodérů a retenci historie určí další zadání.

## ISM dekodér (druhá etapa)

Stránka `/control/ism/` používá samostatnou službu `radio-ism.service`: rtl_433 na 433,920 MHz, vzorkování 1,024 MS/s, zisk 40,2 dB, automatický detekční práh a výchozí sada dekodérů. JSON zprávy se ukládají do `/var/lib/radio-center/ism.sqlite` (SQLite WAL). Odesílají se jen dekódované zprávy s modelem zařízení. Testovací data se do živé historie nevkládají.

Prohlížeč nabízí hledání v obsahu zpráv, 100 záznamů na stránku, starší záznamy a export aktuální stránky JSON. Časy příjmu se ukládají v UTC a zobrazují v Europe/Prague. Retence je 30 dní / 100 000 záznamů, čištění při startu a během příjmu. Stop/start služby historii zachová.

Systemd `Conflicts=openwebrx.service` zajišťuje vzájemné vyloučení obou služeb i při spuštění mimo web. ISM se sám po bootu nespouští, aby nekolidoval s výchozím OpenWebRX. Spuštění ISM zastaví OpenWebRX; spuštění OpenWebRX zastaví ISM. Zastavení ISM ponechá přijímač volný. Při selhání dekodéru je chyba viditelná ve stavu a diagnostice; služba se nepokouší neustále resetovat USB.

Zdroj dekodéru a parametry: https://github.com/merbanan/rtl_433

## Ověření ISM po optimalizaci

Přidán `-Y autolevel` podle implementace dekodéru OpenWebRX. Příjem rozšířen na 1,024 MS/s a zisk zvýšen na 40,2 dB. Sběrač používá neblokující binární čtení `os.read` s vlastními řádkovými buffery, takže celá dávka zpráv nečeká v TextIO bufferu na další vstup. Test tří zpráv v jedné dávce ověřil uložení všech zpráv v dočasné databázi. RF statistiky se aktualizují po 30 s a jsou zobrazené v diagnostice. Ověřen živý příjem Nexus-TH, inFactory-TH a Bresser-3CH a dostupnost skutečných zpráv přes API.

## APRS 2 m a mapa

`/control/aprs/` a služba `radio-aprs.service`: `rtl_fm` přijímá 144,800 MHz (FM, audio 24 kHz, oversampling 4, zisk 40,2 dB, bez squelche), Dire Wolf dekóduje AFSK 1200, parser aprslib zpracovává polohy a obsah. Bez APRS-IS, beaconu, vysílání a síťových KISS/AGW portů. Příchozí rádiové pakety zůstávají uložené i při neznámém APRS formátu, bez vymyšlených souřadnic.

Historie: `/var/lib/radio-center/aprs.sqlite`, 30 dní / 100 000 paketů, vyhledávání a export stránky JSON. Mapa Leaflet (knihovna lokálně) používá podklad OpenStreetMap, který potřebuje připojení k internetu a zobrazuje předepsanou atribuci. Zobrazuje poslední platné pozice stanic či APRS objektů za 24 hodin, nejvýše 500. Poloha představuje obsah paketu, nikoli nutně polohu posledního vysílače; cesta přes digipeatery se zobrazuje zvlášť. Pakety bez souřadnic jsou pouze v historii.

Spuštění APRS zastaví ISM/OpenWebRX; jejich spuštění zastaví APRS přes systemd Conflicts. Po bootu zůstává výchozí OpenWebRX. APRS se spouští ručně přes web.

Instalace vyžaduje `direwolf`, `rtl-sdr`, `python3-aprslib` a stažené soubory Leaflet 1.9.4 ve `static/`. Zdroj knihovny: https://leafletjs.com ; Dire Wolf: https://github.com/wb2osz/direwolf .

Ověření APRS: generátor `gen_packets` vytvořil dočasné AFSK1200 audio se třemi pakety s platnou AX.25 značkou. Dire Wolf je dekódoval, sběrač je rozpoznal a parser zapsal očekávané souřadnice do dočasné SQLite databáze. Testovací pakety nebyly vysílány ani vloženy do živé historie. Ověřeny také filtry, stránkování, retence, zachování poslední známé polohy po status paketu a výlučné použití USB přijímače APRS službou. Při předání nebyl v živém příjmu zachycen skutečný APRS paket; mapa bez přijatých poloh je očekávaně prázdná kromě přijímače. Automatické ověření vzhledu v prohlížeči nebylo dostupné.

## FT8 / FT4

Stránka `/control/ft/` nabízí čtyři pevné přijímací profily: 2m-ft8 (144,174 MHz), 2m-ft4 (144,170 MHz), 70cm-ft8 (432,174 MHz), 70cm-ft4 (432,170 MHz). Frekvence dle https://ft8activity.eu/rules/ . Příjem je USB přes rtl_fm, audio 12 kHz / mono / 16 bit, zisk 40,2 dB. Časové intervaly FT8 15 s a FT4 7,5 s se dělí podle celočíselných audio vzorků a UTC. První neúplný interval po spuštění se vynechá. Vstupní audio nemá hardwarová časová razítka; počátek je odhadnutý z příchodu prvních vzorků. Systémový čas musí být synchronizovaný, stav je zobrazen na stránce.

Dekóduje instalovaný `jt9` z WSJT-X (stejné volby --ft8/--ft4 jako OpenWebRX), hloubka 2, jedno výpočetní vlákno. Oddělené čtení audia a dekódování; fronta maximálně dva intervaly. Přetížení nebo timeout 25 s se zaznamenají jako vynechané intervaly. Dočasné WAV soubory se po dekódování mažou.

Historie `/var/lib/radio-center/ft.sqlite`: UTC interval a čas uložení, pásmo, režim, dial frekvence, SNR, Δt, audio frekvence, text a původní řádek. Uchování 30 dní / 100 000 zpráv. Hledání, filtrování profilu, stránkování a JSON export aktuální stránky. Bez vysílání a reportování.

Čtyři konkrétní systemd jednotky `radio-ft@2m-ft8.service`, `radio-ft@2m-ft4.service`, `radio-ft@70cm-ft8.service`, `radio-ft@70cm-ft4.service` se navzájem vylučují a vylučují i OpenWebRX, ISM a APRS. Sudoers a API povolují pouze tyto pevné profily. Start po bootu se nemění: samostatné dekodéry se spouští ručně.

Ověření: dělení FT8/FT4 intervalů včetně lichých bajtových chunků a vynechání neúplného úvodního intervalu; parser, filtry a stránkování dočasné SQLite historie. Syntetické FT8 i FT4 WAV signály z generátorů WSJT-X dekódoval jt9 na známou zprávu CQ OK2TST JN99. Testovací zprávy nebyly vložené do živé historie. Živý FT8 příjem zpracoval intervaly bez zahlcení fronty; v době ověřování nebyla zachycena skutečná FT8/FT4 zpráva. Vizuální kontrola prohlížečem není automatizovaná.

## HF FT8/FT4

Společný modul `ft_profiles.py` deklaruje pásma 160, 80, 60, 40, 30, 20, 17, 15, 12, 10 m a původní 2 m / 70 cm, celkem 24 profilů. FT8 dial MHz: 1.840, 3.573, 5.357, 7.074, 10.136, 14.074, 18.100, 21.074, 24.915, 28.074. FT4 standardní HF dial MHz: 3.575, 7.0475, 10.140, 14.080, 18.104, 21.140, 24.919, 28.180. U FT4 na 160/60 m není deklarován standardní kanál: aplikace výslovně označuje tyto profily jako volitelnou frekvenci a předvyplňuje sdílený FT8 kanál. Uživatel může zadat frekvenci domluvené FT4 aktivity.

Vstup „Frekvence MHz“ umožňuje doladění v rámci vybraného pásma s 4 kHz rezervou pro USB signál. API kontroluje celé Hz proti povolenému rozsahu, konfigurace je atomicky uložená v `/var/lib/radio-center/ft-tuning.json`. Restart již aktivního profilu aplikuje změnu. Dial frekvence ve zprávě odpovídá skutečně použité frekvenci.

RTL-SDR v3 pod 24 MHz používá explicitně `rtl_fm -E direct2` (Q větev); od 24 MHz přijímá přes R820T tuner. Přímé vzorkování nemá regulaci zisku tuneru. Pro použitelný HF příjem je potřeba HF anténa, podle podmínek může pomoci preselektor / filtr; v přímém vzorkování mohou vznikat zrcadlové příjmy. V UI je vstupní režim uveden v diagnostice. Popis výrobce: https://www.rtl-sdr.com/rtl-sdr-blog-v-3-dongles-user-guide/ ; frekvence: https://www.g4ifb.com/FT8_Hinson_tips_for_HF_DXers.pdf a tabulka WSJT-X.

Status všech FT služeb se načítá jedním voláním systemctl. Jednotky i sudoers se generují pro pevně povolené profily; libovolný systemd příkaz API nepovoluje. Stávající historie zůstává zachována.

## MSK144

`/control/msk/` nabízí 2 m (144,360 MHz) a 70 cm (432,370 MHz), s doladěním v rámci pásma. `rtl_fm` produkuje USB audio 12 kHz / signed 16 bit / mono, které průběžně zpracovává instalovaný `/usr/local/bin/msk144decoder` (stejný dekodér jako v OpenWebRX), hloubka 3, audio střed 1500 Hz. Spot reporting i souborový log dekodéru jsou explicitně vypnuté. Zdroj a dokumentace: https://github.com/alexander-sholohov/msk144decoder . Frekvence: https://vhf-uhf.veron.nl/weak-signal-dx/meteor-scatter-ms/ .

Historie je samostatná `/var/lib/radio-center/msk.sqlite` (30 dní / 100 000 zpráv), obsahuje UTC čas, pásmo, skutečnou dial frekvenci, SNR, Δt, audio frekvenci, zprávu a původní řádek. Web nabízí hledání, filtr pásma, stránkování, export JSON a Clear s potvrzením; Clear se nedotkne FT8/FT4 historie. Zobrazuje orientační sloupky SNR, synchronizaci času, diagnostiku a počet zpráv v relaci.

Služby `radio-msk@2m-msk144.service` a `radio-msk@70cm-msk144.service` se vylučují navzájem a se všemi FT8/FT4, ISM, APRS a OpenWebRX službami. V Řídicím centru je běžící MSK144 označený na vlastní kartě. Po bootu zůstává výchozí OpenWebRX; samostatné dekodéry se spouští ručně.

Ověřeno: generátor `msk144sim` vytvořil testovací audio, streamový dekodér vypsal CQ OK2TST JN99 včetně SNR a parser zprávy rozpoznal. Ověřeny databáze, filtry, stránkování a Clear v dočasné databázi. Žádné testovací zprávy se nevysílaly ani nevložily do živé historie. Ověřeno spuštění na obou pásmech a výlučné vlastnictví přijímače; při předání běží 2 m a skutečná MSK144 zpráva dosud zachycena nebyla.

## LoRa APRS

`/control/lora/` a `radio-lora.service`: příjem RTL-SDR na 433,775 MHz, IQ u8 při 1 MS/s, zisk 40,2 dB. Instalovaný `lorarx` z dxlaprs-lora dekóduje BW 125 kHz, SF9 i SF12, explicitní LoRa hlavičku s automatickým kódovým poměrem, s autonotchem `-W 50`. Parametry odpovídají LoRa APRS řetězci instalovaného OpenWebRX. Obvyklá síť používá SF12 / CR4:5; viz https://lora-aprs.org/settings/ .

Pouze místní příjem, žádný UDP forwarding, APRS-IS ani vysílání. Do historie se přijímají jen JSON rámce s crc=1, platným base64 payloadem a APRS prefixem 3C FF 01. Pakety jiných LoRa sítí a chybné CRC se do APRS historie nevkládají. Metadata SF, BW, CR, SNR a další diagnostika dekodéru jsou uložené v `payload.radio`.

Samostatná historie `/var/lib/radio-center/lora.sqlite` (30 dní / 100 000 paketů), vyhledávání, stránkování a export aktuální stránky JSON. APRS parser a mapa se sdílí s APRS 2 m, data obou služeb jsou oddělená. Mapa ukazuje poslední platnou hlášenou polohu za 24 hodin, nikoli jistou polohu bezprostředního vysílače. OpenStreetMap podklad potřebuje internet. V rádiové kartě je orientační ukazatel SNR (prahy specifické pro LoRa), SF, BW, CR a CRC OK.

Služba se vylučuje se všemi ostatními vlastníky RTL-SDR; přepínání je dostupné z webu a běžící aplikace se zvýrazňuje v Řídicím centru. Samostatný dekodér se automaticky po bootu nespouští.

Ověření: `loratx` vytvořil dočasné IQ soubory APRS zprávy pro SF9 a SF12, `lorarx` je dekódoval, parser uložil správnou zprávu, radio metadata a souřadnice do dočasné SQLite databáze. Ověřeny filtry, samostatná databáze a odmítnutí chybného CRC i payloadu bez APRS prefixu. Testovací signály nebyly vysílány a nejsou v živé historii.

Při nasazení LoRa optimalizováno stavové API: jeden `systemctl list-units` a dotaz na PID pouze aktivních přijímacích služeb, společná cache 2 s. Tím se zabrání opakovanému načítání grafu všech neaktivních FT/MSK jednotek při každém obnovení stránky; po ovládací akci se cache okamžitě zneplatní. Ověřená odpověď stavového API po změně přibližně 0,11 s.

## ISM volba pásma a plánované aplikace

ISM stránka nabízí pevné volby 433,92 MHz a 868,000 MHz. Tlačítko Spustit aplikuje zvolenou frekvenci; změna pásma u běžícího ISM restartuje pouze tuto službu. Poslední volba je uložená v `/var/lib/radio-center/ism-tuning.json`, API a worker odmítají jiné frekvence. Původní příkaz bez frekvence respektuje poslední uloženou volbu. Vzorkování 1,024 MS/s, zisk a automatický práh jsou společné. Historie obou pásem je zachovaná v jedné databázi; nové zprávy obsahují `receiver_frequency` v Hz, zobrazené mezi technickými údaji.

V rozcestníku jsou přidané karty Meteorologické radiosondy a VDL2, označené Připravujeme. Nemají backend, příjem ani aktivní odkazy, dokud se nedoplní v další etapě.

## VDL2

`/control/vdl2/` a služba `radio-vdl2.service`: instalovaný dumpvdl2 2.6.0 přijímá přímo z RTL-SDR současně kanály 136,725 / 136,775 / 136,875 / 136,975 MHz. Zisk 40,2 dB, oversampling 10 (1,05 MS/s). JSON výstup, lokální rekonstrukce fragmentů, bez UDP/TCP forwardingu a bez reportování do internetu. Dokumentace dekodéru: https://github.com/szpajder/dumpvdl2 .

Ukládá se původní kompletní JSON a přehled adres zdroje/cíle, ICAO adresy letadla, registrace a letu, pokud je obsahuje ACARS zpráva, text ACARS, typ rámce, kanál a SNR (úroveň signálu minus šum). Registrační nebo letové údaje se nevymýšlejí, pokud v přijatých datech chybí. Protokolové rámce bez textu zůstávají v historii s rozbalitelným úplným JSON. Web odděluje dekódovanou komunikaci od RF údajů, používá orientační grafický ukazatel SNR.

Samostatná databáze `/var/lib/radio-center/vdl2.sqlite`, 30 dní / 100 000 rámců, hledání v původních datech, filtr kanálu, stránkování, export stránky JSON a Clear s potvrzením. VDL2 se systémově vylučuje se všemi ostatními vlastníky RTL-SDR. Karta VDL2 v Řídicím centru má stav běhu a aktivní odkaz na stránku. Radiosondy zůstávají připravované.

Ověřena extrakce adres/ACARS/RF údajů, samostatné ukládání, hledání, filtr kanálu, stránkování, retence a Clear na dočasných testovacích datech. Testovací zprávy nejsou v živé historii. Python a JavaScript prošly syntaktickou kontrolou. Nasazení vyžaduje administrátorské ověření sudo:

```bash
sudo bash /home/rpodolsky/OpenWebRX/radio-center/install.sh
sudo systemctl start radio-vdl2
```

Při přípravě této změny přístup sudo bez hesla vypršel. Služba ani živý VDL2 příjem proto v této etapě nebyly ověřeny a zdrojové změny zatím nejsou nasazené.

## Meteorologické radiosondy

`/control/sonde/` a služba `radio-sonde.service`: ručně zvolený typ RS41, DFM06/09, DFM17, M10, M20 nebo MTS01 a frekvence 400–406 MHz. Výchozí RS41 / 401,500 MHz je pouze úvodní nastavení, nikoli zjištěná místní frekvence. Automatické skenování není implementované. Parametry se ukládají atomicky do `/var/lib/radio-center/sonde-tuning.json`; opětovné spuštění aplikuje přeladění restartem. API a worker validují typ proti pevné nabídce a frekvenci proti rozsahu.

Řetězec: `rtl_fm -M raw` -> raw I/Q signed16 -> instalované RS dekodéry (stejné jako OpenWebRX). RS41/DFM/MTS01 při 48 kS/s, M10/M20 při 76,8 kS/s. PTU parametry odpovídají OpenWebRX. Žádné internetové reportování, SondeHub/APRS-IS upload ani vysílání.

Samostatná `/var/lib/radio-center/sonde.sqlite`: telemetrická historie 30 dní / 100 000 rámců. Ukládá sériové ID, model, číslo rámce, frekvenci, GPS, výšku (m), teplotu (°C), vlhkost (%), tlak (hPa), horizontální/vertikální rychlost (m/s), směr a původní JSON. Web zobrazuje horizontální rychlost v km/h. Duplicitní rámečky se nevkládají. Neplatné GPS a chybějící/nesmyslná měření jsou null, ne odhad. Non-finite JSON hodnoty se převádějí na null. RS41 bez barometru nemá vymyšlený tlak.

Mapa a trasy posledních 48 hodin, výběr až 50 nedávných sond, trasa nejvýše 2000 vzorkovaných bodů se zachováním prvního/posledního, graf výšky proti času příjmu. Podklad OpenStreetMap vyžaduje internet. Mapové značky používají textové DOM uzly. Trasa není předpověď dopadu. Historie vybrané sondy má filtr, stránkování, export aktuální stránky JSON a Clear s potvrzením pro celou radiosondovou historii.

Služba se systémově vylučuje se všemi ostatními aplikacemi RTL-SDR. Start po bootu zůstává OpenWebRX. Karta radiosond v Řídicím centru zobrazuje běh a odkaz na novou stránku.

Ověření: všechny podporované IQ vstupy přijaly raw formát, živě se spustily M20, DFM a RS41. Kontrolovány validace, jednotky, nulová/neplatná GPS, chybějící tlak, NaN měření, deduplikace, SQLite historie, filtry, stránkování, vzorkování trasy a Clear na dočasných datech. Testovací telemetrie není v živé historii. Nativní řetězec běží, ale v době předání nebyla zachycena skutečná sonda a nebyl použit známý zaznamenaný rádiový signál. První příjem proto vyžaduje zvolit správný kanál a typ sondy v dosahu.

Referenční dekodéry a podporované sondy: https://github.com/projecthorus/radiosonde_auto_rx .

### Kalibrace RTL-SDR

Korekce hodin je −7 ppm (odhad z posunu +1 kHz na 145,525 MHz, 16. 10. 2026).
Samostatné dekodéry používají `sdr_calibration.py: SDR_PPM`; OpenWebRX má stejnou
hodnotu v `/var/lib/openwebrx/settings.json`, `sdrs.rtlsdr.ppm`. Při další kalibraci
uprav obě místa a restartuj právě používaný přijímač. Jde o poměrnou korekci,
nikoli pevný posun 1 kHz ve všech pásmech.

### Původní úzkopásmový Q65 / JT65

Původní implementace (nahrazena EME monitorem v `/control/weak/`) používá WSJT-X `jt9` nad USB audiem 12 kHz.
Q65 na 2 m / 70 cm podporuje A/B a intervaly 15/30/60/120/300 s.
JT65A je k dispozici na HF 160–10 m kromě 60 m, na 2 m A/B a na 70 cm B/C.
VHF/UHF frekvence jsou upravitelné výchozí návrhy, ne záruka aktivity; EME
vyžaduje odpovídající anténu a domluvenou frekvenci/podrežim.
První neúplný interval po spuštění se zahodí. Korekce SDR zůstává −7 ppm.

Samostatné jednotky `radio-weak@<profile>.service` mají konflikty se všemi
rádiovými aplikacemi. Jednotky nejsou povolené pro automatický start.
Profily: `weak_profiles.py`; pracovní proces sdílí `ft_worker.py` přes
`RADIO_DECODER_KIND=weak`. Ladění, stav a historie mají předponu `weak`,
clear maže jen `weak.sqlite`. Retence 30 dní / 100 000 zpráv. Žádné vysílání
ani odesílání spotů. Lokální API má stejné ověření tokenu a původu jako FT8.

Nasazení: `sudo bash /home/rpodolsky/OpenWebRX/radio-center/install.sh`.
Instalátor restartuje jen řídicí centrum; právě běžící přijímač zachová.

Ověření Q65/JT65: `python3 -m unittest discover -s radio-center/tests -v`
a `python3 radio-center/tests/weak_integration.py`. Nativní test generuje
Q65 všech 10 kombinací a JT65 A/B/C pomocí WSJT-X simulátorů v dočasných
adresářích; nepřistupuje k SDR ani k provozní databázi.

### Širokopásmový EME monitor

Aktuální architektura, omezení, naměřený výkon a nasazení: [EME.md](EME.md).

OpenWebRX dashboard tuning: `openwebrx_activity.py` exports anonymous per-client
frequency, modulation, secondary decoder and filter width, plus active receiver
profiles. `install-openwebrx-activity.py` adds this snapshot to `/metrics.json`
only for loopback requests, backs up changed package files and restarts OpenWebRX
only when necessary. Dashboard deployment reapplies the extension after an
OpenWebRX package update; unsupported controller versions fail without patching.
No client IP addresses or names are exported. The panel lists separate tunings
for simultaneous listeners; without listeners it shows the SDR profile rather
than implying an active audio demodulation. Refresh interval is 10 seconds.

Společné nastavení stanoviště, rozložení panelů a ADS-B: viz [RADIO-CENTER.md](RADIO-CENTER.md).
