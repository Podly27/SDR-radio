# ISS receiving

`/control/iss/` nyní poskytuje SSTV, příjem packet a živý hlasový poslech.
Všechny profily jsou pouze pro příjem, bez vysílacího zařízení a bez APRS-IS.

| Profil | Downlink | Zpracování |
|---|---|---|
| SSTV UHF | 437,550 MHz | Robot36 a ostatní podporované VIS režimy |
| SSTV VHF | 145,800 MHz | SSTV podle VIS |
| Voice VHF | 145,800 MHz | FM hlas, poslech ve webu |
| Voice repeater UHF | 437,800 MHz | FM downlink převaděče |
| Packet VHF | 145,825 MHz | AFSK 1200 / AX.25 / APRS |
| Packet UHF | 437,825 MHz | AFSK 1200 / AX.25 / APRS |

Packet 9600 baud není zahrnut. Jeden RTL-SDR v této aplikaci přijímá jeden
vybraný profil; neprobíhá současné dekódování VHF a UHF ani skenování mezi nimi.
Profily odpovídají ARISS: https://www.ariss.org/contact-the-iss.html

## Ovládání a přelety

Vyber profil a Doppler ve formuláři a ulož jej. Použije se pro ruční start
i příští automatický přelet. Při změně již běžícího příjmu použij Restartovat.
Automatický monitor zůstává samostatný: přebírá SDR pouze při vhodném přeletu,
pak obnoví předchozí aplikaci. Probíhající automatický příjem má přednost.
Ruční nová volba zruší starý automatický návrat (viz AUTOMATION.md).

Tlačítko Poslouchat zvuk spouští Web Audio po výslovném kliknutí uživatele.
Zvuk je dostupný ve všech profilech; hlasový profil má FM deemfázi. Server
nepotřebuje zvukovou kartu ani otevřený prohlížeč. Neukládá hlasové nahrávky;
RAM okno obsahuje pouze poslední 2 s PCM. Bez vysílání bude slyšet také šum.

SSTV galerie a její historie zůstaly zachované. Packet má samostatnou historii
`iss-packet.sqlite` (30 dní / 100 000 paketů), s časem, zdrojem, původní zprávou
a frekvencí v metadatech. Hlavní panel přizpůsobuje statistiky vybranému režimu.
Samotný příjem na frekvenci ISS nedokazuje původ signálu ani retranslaci přes ISS.

## Doppler

Poloha a výška stanoviště jsou ze společného nastavení, ISS TLE ze společného
časovače. PyEphem poskytuje radiální rychlost `range_velocity` v m/s.
Přijímaný posun je `−f × v / c`: při přibližování kladný, při vzdalování záporný.
SDR zůstává na nominálním středu; CSDR Shift ladí v IQ signálu opačný posun
každou sekundu. Dekodér, audio i rozpracovaný obrázek zůstávají v chodu.

Zpracování: RTL-SDR IQ 240 kS/s → nativní Convert → Shift → FirDecimate ×10
→ FmDemod → DcBlock → 24 kHz PCM. SSTV používá existující SstvDecoder,
packet Dire Wolf. Nevznikl vlastní SSTV, FM ani AX.25 dekodér.

Korekce ppm SDR zůstává nezávislá na Doppleru. Při starém/chybějícím TLE
Doppler nepoužije odhad a zobrazí důvod. Automatický start vyžaduje čerstvé TLE
a NTP; ruční příjem může pokračovat bez Doppleru, s uvedeným upozorněním.
Výpočet radiální rychlosti: https://rhodesmill.org/pyephem/quick.html

## ARISS Series 34

K ověření 17. 10. 2026 ARISS uvádí 22.–25. října, 437,550 MHz, Robot36,
36 s vysílání a dvě minuty pauzy. Přesné začátky/konce zatím nejsou stanovené.
Aplikace podle těchto neúplných časů neslibuje vysílání při každém přeletu.
https://www.ariss.org/upcoming-sstv-events.html

## Nasazení a testy

`sudo bash radio-center/deploy-iss-receiving.sh` zálohuje nahrazované soubory,
aktualizuje jednotku a zachová spuštění monitoru i existující historii.
Konfigurace staré volby frekvence se převádí na příslušný SSTV profil.

Jednotkové testy pokrývají profily, Dopplerovo znaménko a škálování, výpočet
ze skutečných TLE rovnic, odmítnutí starého TLE a formát/velikost audio okna.
Node test pokrývá výběr profilu, hlasové ovládání, Doppler a historii packet.

Samostatný syntetický test přes kompletní FM cestu a proměnný Doppler
(+9 kHz přes nulu do záporné hodnoty) nativně dekódoval celý Robot36 320×240.
Další umělý IQ test s +10 kHz dekódoval AX.25 zprávu přes Dire Wolf.
Testovací obrázek a pakety nejsou v produkční galerii/databázi a nejsou
potvrzením reálného vysílání ISS.

Prošlo 51 Python testů a tři Node testy. V provozním testu byly postupně
spuštěny všechny profily; každá cesta otevřela skutečný RTL-SDR, poskytla
PCM audio a aktuální Doppler podle TLE bez chyby. Nominální frekvence
a režimy odpovídaly profilům. Pak byl obnoven předchozí ADS-B a monitor ISS.
Žádná tato zkouška nepotvrzuje příjem komunikace skutečně vyslané z ISS.
