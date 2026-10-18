# Meteor LRPT meteosatellite receiver

Open `/control/meteo/`. The dashboard Start button arms automatic passes;
Stop disarms the monitor and stops its receiver. The page also offers an explicit
manual capture (confirmation before taking the SDR), Restart, satellite/frequency/
72k or 80k selection, gain, minimum elevation and manual capture duration.

Defaults: Meteor-M2-4 / NORAD 59051, 137.100 MHz, LRPT 72 ksym/s, 10° elevation,
40.2 dB gain, manual duration 600 seconds. These frequency/modulation settings
are configurable, not a claim that the spacecraft is currently transmitting.
M2-3 / NORAD 57166 is selectable, but its transmission must be checked separately.
The station is shared with EME: latitude, longitude, place and callsign from
`eme-config.json`, currently OK2IKT / Lichnov. No position is guessed from IP.

The installed native SatDump decoder does demodulation, Viterbi/Reed–Solomon and
MSU-MR decoding; this application does not implement its own LRPT DSP. Debian's
arm64 SatDump 1.2.2 replaced an unmanaged build that failed with SIGILL on this
Cortex-A53. The old installation was archived under
`/opt/radio-center/backups/satdump-before-meteo-20261017-083651/`.

## Services and arbitration

- `radio-meteo.service`: user-started pass monitor. It can wait while another app
  owns RTL-SDR; at a suitable pass it temporarily pauses that app and restores
  it afterward through the shared coordinator (see AUTOMATION.md). An ongoing
  automatic reception has priority. No more than one
  automatic capture is attempted per pass. Unsynchronized time or TLE epochs
  older than seven days block automatic capture. Manual mode is one capture and
  does not retake the receiver after the user switches to another app.
- `radio-meteo-rx.service`: exclusive SatDump receiver, conflicts with other RF
  receivers and is PartOf the monitor. EME also recognizes it as an occupied SDR.
- `radio-meteo-tle.timer`: enabled at boot, refreshes orbit data every six hours.
  TLE checks verify the NORAD ID and checksum through PyEphem and reject stale
  downloaded elements. CelesTrak is primary, SatNOGS is fallback.

The monitor runs without a browser/desktop. It is not enabled at boot by default:
start automatic monitoring from the web after a server restart. The TLE timer
runs independently even when the monitor is stopped. Waiting monitoring does not
reserve the receiver. `PartOf` and finally cleanup stop the receiver with the
monitor. Manual duration and automatic pass windows are bounded to 15 minutes.

Capture is `satdump live meteor_m2-x_lrpt ... --source rtlsdr --samplerate 1000000`.
80k uses the corresponding `_80k` pipeline. The receiver applies shared -7 ppm via
SatDump's **`ppm_correction`** parameter, DC blocking, manual gain and forced
satellite identity. Native metrics listen only on loopback port 8092 `/api`.
The frontend shows real SNR, Viterbi BER/lock and deframer lock, without inventing
packets or interpreting unlocked RS values as valid data. There is no waterfall.

## Images, disk and limitations

After capture/postprocessing, nonempty MSU-MR PNG products are imported into
`meteo-images/` and `meteo.sqlite`. Display previews stretch 16-bit contrast and
limit pixel dimensions; original SatDump PNGs remain available for download.
Image metadata contains capture ID, satellite, actual configured frequency,
dimensions and saved UTC time. Current worker/scheduler state and native logs are
shown separately. Image counts are channel images, not whole satellite passes.

Gallery images/history are retained. New reception is blocked below 600 MiB free
disk space; reclaim space manually when required. Temporary working datasets are
limited separately to three captures / 512 MiB and empty captures are removed.
The importer copies original images before cleaning temporary work. SatDump
automatic composite/projection processing is disabled to bound work on this Pi;
the gallery initially contains individual MSU-MR channels. A valid pass prediction
is not proof of an LRPT broadcast or adequate antenna reception. No local terrain
mask, rotator control, orbit map or automatic TLE Doppler tuning is implemented.

## Install and verification

Install Debian `satdump satdump-data python3-pil python3-numpy python3-ephem`, then
`sudo bash radio-center/deploy-meteo.sh`. Deployment backs up changed files,
installs units and exact sudo permissions, initializes data and TLEs, enables only
the TLE timer, and updates the web UI. It does not automatically arm RF reception.

`python3 -m unittest discover -s radio-center/tests -p test_meteo.py` checks
orbit crossing times, stale TLE gates, occupied receivers, NTP gating, argument
validation and empty/16-bit image imports. `test_eme_scheduler.py` tests arbitration
with all RF applications. Dashboard JavaScript controls and live HTTP endpoints
are checked separately.

On 2026-10-17, native SatDump decoded three MSU-MR image channels from a synthetic
CADU fixture produced by an independent LRPT encoder:
https://github.com/ktauchathuranga/lrpt-encoder/blob/main/satdumped/meteor_m2-x_lrpt.cadu
Fixture: 1,092,608 bytes, SHA-256
`9748bd4446f48aabfe3cb50a19a68b835fa8e0f3f85248870d7d400698b97482`.
Decoded dimensions were 1568×1552, 1568×1560 and 1568×1552; gallery import preserved
three original PNGs and produced RGB previews. Test data stayed in
`/tmp/meteo-cadu-validation`, outside the production gallery. A separate live SDR
check verified acquisition and native metrics. This does not establish live
reception of a meteorological image from a satellite over Lichnov.

A complete 30-second live capture also finished and stopped both worker and manual
monitor cleanly. Native RSS was about 312 MiB and CPU about 59% of one core during
the noise/no-lock test. Production image count remained zero and ISM was restored.
Automatic monitoring was separately started with ISM active and waited without
taking the SDR. These tests do not prove weak-signal performance during a pass.

## Diagnostika přeletů a oprava dokončovací fáze (18. 10. 2026)

Živý profil SatDump 1.2.2 `meteor_m2-x_lrpt` zpracovává demodulaci a CADU,
ale bez dalšího kroku nevytváří produkty MSU-MR. Pracovní proces nyní
zachová neprázdné CADU a předá je do `meteo-process/`. Jednotka
`radio-meteo-process.path` spouští samostatný přijímačům nekonfliktní
`radio-meteo-process.service`, který offline vytvoří obrázky a importuje je
do galerie. SDR se mezitím může vrátit původní aplikaci.

Pro tři vyžádané přelety 18. 10. je v `meteo-diagnostic-plan.json` časově
omezený plán. Používá stejný mechanismus vlastnictví SDR jako normální Meteor:
probíhající jiný automatický příjem nepřeruší a ruční volby respektuje.
Místo trvalého živého dekódování se během těchto oken pořídí nejvýše devět
12sekundových úseků na přelet, se středem 137,5 MHz a 2,048 MS/s, takže
zahrnují současně 137,1 i 137,9 MHz. Zisky 29,7 / 40,2 / 49,6 dB se střídají;
proto je nutné při porovnání zohlednit různou polohu družice.
Každý záznam se frekvenčně posune, filtruje a převzorkuje na 256 kS/s pro
porovnání 72k a 80k nativním SatDump. Vzniká PSD a orientační poměr výkonu
v kanálu vůči okolí; není to kalibrované SNR ani potvrzení LRPT.

Pořízené originály a podrobné výsledky jsou v `/var/lib/radio-center/meteo-diagnostics/`
a `meteo-reports/`. Souhrn `meteo-diagnostic-summary.json` se zobrazuje v aplikaci.
Při rezervě menší než 2 GiB se další záznamy nepořizují. Originály se automaticky
nesmažou; plán po posledním okně vyprší a další přelety použijí běžný živý příjem.
Frekvence/režim se mohou automaticky změnit pouze na základě skutečně vytvořených
obrázků a jen pokud uživatel mezitím nezměnil původní profil. Globální zisk se
samotným experimentem nemění.

Nasazení bez přerušení ostatních přijímačů:
`sudo bash radio-center/deploy-meteo-diagnostics.sh`. Skript odmítne nasazení
během aktivního příjmu Meteoru. Plán konkrétní noci není součástí výchozí instalace.

Ověření před reálným přeletem: 60 Python testů,
syntetický šum nevytvořil rámce ani obrázky; známý kontrolní CADU vytvořil tři
obrázky. Syntetický OQPSK soubor vytvořený z kontrolních CADU prošel
demodulací/Viterbi/RS a vytvořil 100 rámců a tři obrázky. Tyto laboratorní testy jsou
v odděleném adresáři a nejsou skutečným příjmem družice.

Kontrolní data: https://github.com/ktauchathuranga/lrpt-encoder ,
`meteor_m2-x_lrpt.cadu` SHA256
`9748bd4446f48aabfe3cb50a19a68b835fa8e0f3f85248870d7d400698b97482`.
Oficiální chování živé fáze:
https://github.com/SatDump/SatDump/blob/1.2.2/src-cli/live.cpp .

### Skutečný příjem obnoven při následné analýze 18. 10.

Z reálného IQ při 137,9 MHz se změnou PLL z 0,002 na 0,008 podařilo
obnovit 38 CADU a tři částečné obrázky MSU-MR (1568 × 32). Stejný
signál po našem převzorkování poskytl 36 CADU a tři proužky; převzorkování
tedy signál nezničilo. OQPSK a NRZ-M jsou potvrzené obnovenými daty.
Společná konstanta `meteo_common.LRPT_PLL_BW=0.008` se používá pro 72k
živý příjem i offline processing. Parametry 80k nebyly touto změnou upravené.
Celý následující živý přelet s novým nastavením zatím ověřený není.
Detaily a grafy jsou v `analysis/meteor-20261018/` pracovního projektu.

Po dokončení replay devíti záznamů se ziskem 49,6 dB: celkem 59 CADU a
šest skutečných proužků ze dvou přeletů (38 + 21 rámců). Uložené originály
zůstávají zachované, příjem dalšího celého přeletu s PLL 0,008 je nutné
ověřit samostatně.
