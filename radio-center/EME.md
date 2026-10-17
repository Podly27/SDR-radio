# EME monitor Q65 / JT65

Stav k 16. 10. 2026: implementace a testy připravené. Nasazení a kontrola služby
po jejím restartu zatím čekají na oprávnění `sudo`. Skutečný EME příjem nebyl
potvrzen. Testovací data se nikdy neukládala do provozní historie.

## Nově ověřený server a stanoviště

- Raspberry Pi 3 B+ Rev 1.3, 4× Cortex-A53 do 1,4 GHz, 905 MiB RAM, Debian 13.7
  arm64, kernel 6.18.50+rpt-rpi-v8. NTP při kontrole synchronizované.
- RTL2838 USB `0bda:2838`, tuner R820T, serial `00000001`, USB 480 Mb/s.
  USB identifikace sama nepotvrzuje obchodní označení konkrétní revize donglu.
- Při první kontrole SDR volný; později byl spuštěn OpenWebRX. Automatika ho
  nebude přerušovat. Konečné vlastnictví přijímače ukazuje stav služeb.
- Krátký skutečný IQ záznam při 240 kS/s na 432,050 MHz se podařil. To potvrzuje
  přístup k zařízení a datovému proudu, ne příjem EME ani citlivost soustavy.
- Poloha a identifikace výslovně od uživatele: OK2IKT, 49,5622 N / 18,1746 E,
  vypočtený lokátor JN99CN. Soustava 2×17 prvků na 70 cm je údaj uživatele,
  nikoli měření. Výška stanoviště není zadaná: astronomický výpočet používá
  referenční výšku 0 m, ne domnělou skutečnou nadmořskou výšku.

## Možnosti existujících dekodérů

| Řešení | Šířka a protokoly | Podrežimy / omezení |
|---|---|---|
| WSJT-X `jt9` | Standardní úzkopásmové USB audio 12 kHz; Q65 i JT65 | Jeden zvolený protokol, podrežim a interval na spuštění. Není to přímý 90kHz IQ dekodér. |
| MAP65 | Až přibližně 90 kHz IQ; Q65 a JT65 | V každém průchodu konkrétní Q65-60 A–E a konkrétní JT65 A/B/C. Více průchodů nad záznamem je možné; nejde o automatické rozpoznání všech podrežimů. |
| QMAP | Přibližně 90 kHz; Q65 | Q65 30/60 s, nastavení základního podrežimu; související 30s podrežim je odvozen z 60s nastavení. JT65 nedekóduje. V lokálním balíku Debian WSJT-X 2.7.0 není jeho executable. |

Zdroje ověřené pro návrh:

- [Oficiální WSJT-X README](https://github.com/WSJTX/wsjtx/blob/master/README.md).
- [MAP65 3.0 Quick Start](https://wsjt.sourceforge.io/WSJTX_2.5.0_MAP65_3.0_Quick_Start.pdf)
  (příručka GUI Windows a doporučené EME podrežimy).
- [Oficiální souborový dekodér MAP65 m65, WSJT-X 2.7.0](https://github.com/WSJTX/wsjtx/blob/v2.7.0/map65/libm65/m65.f90).
- [Výběr podrežimů QMAP](https://github.com/WSJTX/wsjtx/blob/v2.7.0/qmap/libqmap/qmapa.f90).
- [IARU Region 1 VHF/UHF band plans](https://www.iaru-r1.org/about-us/committees-and-working-groups/vhf-uhf-shf-committee-c5/vhf-up-bandplanning/).

Použit je oficiální MAP65 zdroj z WSJT-X **v2.7.0**, spolu s lokálním Debian
WSJT-X `jt9` 2.7.0. Nejde o tvrzení, že 2.7.0 je nejnovější upstream verze.
`eme-native/build.py` stahuje oficiální archiv, kontroluje SHA256 a sestavuje
souborovou přijímací část bez Qt, zvukového výstupu, ovládání rádia a PTT.
Licence GPL je přiložená. Adaptér mění pevně zadané testovací parametry CLI,
využívá hotové symbolové spektrum pro více průchodů a exportuje kandidáty
z existujícího `wideband_sync`. Q65 codec zůstává upstreamový. Pro JT65 se
používá instalovaný `jt9` nad malými výřezy nalezených signálů; starý MAP65
JT65 průchod nebyl při lokálním testu dostatečně ověřený, proto se nepoužívá.
Žádný vlastní protokolový dekodér nebyl napsán.

## Pokrytí a skutečná omezení

Výchozí 70 cm: **432,000–432,090 MHz**; 2 m: **144,100–144,190 MHz**.
Začátek obou úseků lze změnit v celých kHz. Přijímá se vždy jedno pásmo.
RTL-SDR dodává 240kHz IQ proud, FIR převod jej převede na 96 kS/s pro MAP65;
využitelný sledovaný úsek má 90 kHz. Nejde o pokrytí celých 430–440 MHz ani
144–146 MHz. Skenování se nepoužívá: přerušovalo by minutové EME relace.

Tento RPi **nezvládá garantovat všechny podrežimy v každé minutě**:

- Původní širokopásmový test MAP65 se třemi Q65 a dvěma JT65 průchody trval
  98,12 s. Dekódoval Q65 A/B/C; JT65 se následně převedlo na ověřený `jt9`.
- Q65-60B s exportem JT65 kandidátů na smíšeném syntetickém záznamu trval
  50,63 s; maximální RSS přibližně 327 MiB. Konečná samostatná fáze Q65
  bez nepotřebného exportu kandidátů prošla za **46,59 s**.
- Samostatná fáze JT65B včetně širokopásmového vyhledání dvou signálů,
  výřezů a dekódování trvala 37,42 s; maximum přibližně 255 MiB.
- Q65 a následné JT65 nad stejnou minutou dohromady 80,59 s. Výkon závisí
  na počtu signálů, zvolených režimech, rušení a další zátěži serveru.

Výchozí strategie proto střídá **protokoly a podrežimy po celých minutách**:
Q65-60B → JT65B → Q65-60C → JT65C → Q65-60A → JT65B → …
Jde o automatické střídání, nikoli souběžný příjem všech podrežimů každou
minutu. Q65 A/B/C má při tomto nastavení pokrytí jednou za šest minut;
JT65 B/C se střídají v každé druhé minutě. Tyto mezery nelze na tomto
nastavení odstranit tvrzením, že jde o širokopásmový dekodér.

Strategie „Všechny“ postupně zkouší všechny zvolené podrežimy nad stejným
záznamem, ale po 55 s ukončí rozpracované dekódování. Není doporučeným
řešením pro úplné nepřetržité pokrytí na Pi 3. Fronta má nejvýše jeden
záznam; přetížení, nedokončené průchody a vynechané intervaly jsou v diagnostice.
JT65 má nastavitelný limit 1–5 nejsilnějších synchronizačních kandidátů
(výchozí 3), nikoli záruku dekódování neomezeného počtu stanic.

Q65 širokopásmový monitor používá pouze **60s intervaly**; 15/30/120/300 s
nejsou zahrnuté. A/B/C prošly syntetickým testem; D/E jsou volitelné možnosti
upstream dekodéru, jejich citlivost a výkon v této soustavě nebyly měřeny.
Jednokanálový RTL-SDR neposkytuje adaptivní příjem dvou polarizací.
Automatická Dopplerova kompenzace pro každou vzdálenou stanici není zapnutá.
Frekvence je USB dial podle reference MAP65 (sync −1270,46 Hz), nikoli
vysílací/sked frekvence vzdálené stanice. Příjem signálu neprokazuje EME cestu.

Zisk 40,2 dB je upravitelná výchozí hodnota, ne změřené optimum pro LNA/anténu.
Korekce −7 ppm je konfigurovaný odhad, nikoli nová EME kalibrace stabilním
referenčním signálem. Přesnost frekvence a skutečná citlivost soustavy vyžadují
ověření na známém signálu; případný předzesilovač, filtry a natočení antén
tato aplikace neovládá.

## Automatika a web

`radio-eme.service` běží po startu systému. Bez prohlížeče počítá topocentrický
azimut a geometrickou elevaci Měsíce pomocí PyEphem. Referenční tlak je 0,
tedy bez atmosférické refrakce. Start od **17°**, zastavení pod **15°**;
hystereze 2° a minimum jsou nastavitelné. Volba souřadnic nebo Maidenhead
lokátoru (střed pole). Aktuální UTC čas musí být synchronizovaný přes NTP.

`radio-eme-rx.service` vlastní SDR pouze při povoleném příjmu. Má konflikty
se všemi existujícími přijímacími aplikacemi, paměťový limit 650 MiB a jeden
nativní dekodér současně. Automatika dočasně převezme SDR od běžné aplikace
a po skončení ji obnoví; probíhající automatický příjem má přednost
(viz AUTOMATION.md). Ruční spuštění v EME stránce jej může převzít. Ruční režim obchází elevaci,
nikoli kontrolu synchronizace času. Ostatní aplikace mohou přijímač převzít;
ruční režim bez nového požadavku nezačne SDR znovu násilně přebírat.

Stávající `/control/weak/` je nahrazena EME stránkou; alias `/control/eme/`.
Web ukazuje stav služeb, stáří stavu, Měsíc, plán daného intervalu, výsledky
průchodů, zátěžové limity, chyby, historii, SNR ikony, filtr, export a Clear.
Historie má vlastní `eme.sqlite`, retenci 30 dní / 100 000 zpráv. Časy zpráv
jsou UTC. Nastavení a ovládání mají stávající kontrolu tokenu/původu a nginx
omezení na domácí síť. Nic se nevysílá a neposílají se spoty do internetu.

## Nasazení a ověření

Závislosti byly na tomto serveru nainstalované při přípravě:
`python3-numpy`, `python3-scipy`, `python3-ephem`, `wsjtx`, `rtl-sdr`.
Pro opakovatelnou kompilaci navíc `gfortran-13`, `gcc-13`, `cmake`,
`ninja-build`, `libfftw3-dev`. GCC/Fortran 14 při místním překladu padal
interní chybou; sestavení proto explicitně používá verzi 13.

```bash
# Případné opětovné sestavení; použij disk, /tmp je zde RAM-backed 453 MiB.
python3 /home/rpodolsky/OpenWebRX/radio-center/eme-native/build.py \
  /home/rpodolsky/OpenWebRX/.cache/eme-build

# Nasazení připraveného binárního souboru i webu:
sudo bash /home/rpodolsky/OpenWebRX/radio-center/install.sh

systemctl is-enabled radio-eme.service
systemctl is-active radio-center.service radio-eme.service
journalctl -u radio-eme.service -u radio-eme-rx.service -n 40 --no-pager
```

Instalátor povolí automatiku po restartu, zachová existující konfiguraci EME,
pokud už existuje, a na prvním nasazení použije potvrzené údaje OK2IKT.
Restartuje řídicí centrum a scheduler; převzetí ostatních služeb
řídí automatický režim a podmínky uvedené v AUTOMATION.md. Přímý automatický boot jednotky přijímače se nezapíná:
rozhoduje scheduler a elevace. Před odchodem ověř aktivní scheduler a web,
při Měsíci pod limitem má být přijímač neaktivní. Restart scheduleru je
ověření běhu služby, nikoli důkaz provedeného fyzického restartu celého RPi.

```bash
OPENBLAS_NUM_THREADS=1 python3 -m unittest discover \
  -s /home/rpodolsky/OpenWebRX/radio-center/tests -v
```

Testy ověřují lokátor/polohu Měsíce, hysterezi, validaci, streaming FIR a IQ
orientaci, časové bloky, výřezy pro JT65, parser a izolovanou databázi.
Dočasný HTTP test ověřil obě stránky, konfiguraci, historii, Clear a CSRF.
Syntetický smíšený záznam vznikl oficiálním `mapsim`: tři Q65 a dva JT65
signály v různých částech 90kHz úseku. Správně byly dekódované Q65 A/B/C a
JT65 B/C; výsledky a naměřené časy jsou v `eme-validation.json`.
Opakování integrovaného testu s uchovaným syntetickým IQ souborem (bez SDR,
bez produkční databáze; může trvat přes minutu):

```bash
OPENBLAS_NUM_THREADS=1 python3 /home/rpodolsky/OpenWebRX/radio-center/tests/eme_replay_test.py \
  /home/rpodolsky/OpenWebRX/.cache/eme/mixed/261016_1200.iq
```

Původní `weak_integration.py` testuje historickou úzkopásmovou implementaci,
není důkazem širokopásmového EME příjmu.

**Zbývá po obnovení sudo:** nasadit, ověřit restart/enable scheduleru,
provést minutový skutečný příjem kompletního nového pipeline a sledovat
živé EME stanice při vhodné elevaci a natočení antén. Nebyl proveden
fyzický restart RPi ani potvrzen živý EME decode. To se nesmí zaměnit
s úspěšným dekódováním syntetického záznamu.
