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
