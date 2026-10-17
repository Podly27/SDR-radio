> Aktuální rozšíření voice / packet / Doppler: viz [ISS-RECEIVING.md](ISS-RECEIVING.md).

# ISS SSTV

`radio-iss.service` receives 145.800 MHz FM through the shared RTL-SDR. It feeds
24 kHz mono audio into the installed `pycsdr.modules.SstvDecoder`, the same native
VIS-driven decoder used by OpenWebRX. It recognizes PD120/PD180 and other native
SSTV modes without manual selection. No desktop, browser, sound card, transmitting
component, Internet audio feed or new SSTV DSP implementation is involved.

Open `/control/iss/` for Start/Stop/Restart, decoded mode/line progress, live PNG
preview, gallery pagination, PNG downloads and diagnostics. Dashboard cards show
last-hour image count and last reception. Starting another radio app stops SSTV;
The optional radio-iss-auto.service listens during predicted passes, temporarily
borrows SDR and restores the previous app (see AUTOMATION.md). SSTV never starts
itself just because a browser was opened. The systemd unit is installed for use
after reboot, but is deliberately not enabled to seize the single SDR at boot.

Audio: `rtl_fm -M fm -s 48000 -r 24000`, gain 40.2 dB, shared -7 ppm calibration,
no squelch (SSTV headers must not be clipped). The capture bandwidth also covers
normal ISS VHF Doppler shifts; this implementation does not track satellite
retune for Doppler; the pass monitor does track visibility from TLEs. The frequency alone cannot prove that a signal came
from ISS. SSTV events are intermittent; see the primary ARISS event page:
https://www.ariss.org/upcoming-sstv-events.html

Files: `/var/lib/radio-center/iss-images/*.png`, transient `preview.png`, state
`iss-state.json`, SQLite metadata `iss.sqlite`. Retention: 90 days / 500 gallery
images. Metadata and gallery survive service/server restarts. Frames interrupted
by stopping are padded for PNG storage and labelled interrupted; a completed
frame means the decoder supplied all image lines, not error-free RF reception.
The native decoder itself can pad missing rows, so black rows are possible even
in a completed frame. There is no image integrity checksum or authenticated ISS
identity in this UI.

Install dependencies `python3-pil`, `python3-numpy` and the existing OpenWebRX
`pycsdr` package, then `sudo bash radio-center/deploy-iss.sh`. Deployment backs up
changed files, installs the unit and restricted sudo rules, reloads systemd and
updates the web dashboard. No receiver is automatically started. Check logs with
`journalctl -u radio-iss.service`; audio level is shown in diagnostics as RMS,
not calibrated RF signal strength.

Tests: `python3 -m unittest discover -s radio-center/tests -p test_iss.py` covers
fragmented BMP framing, image colour, malformed data and partial-frame persistence.
`test_eme_scheduler.py` includes SSTV occupancy. Audio replay uses mono 16-bit
24 kHz PCM WAV: `python3 radio-center/iss_worker.py --replay sample.wav --data
/tmp/iss-replay`. Replay runs at real-time speed: the native csdr ring buffer does
not implement producer backpressure, so accelerated writes can overwrite samples.
Synthetic colour bars encoded as PD120 test the native audio decoder, image
geometry, colours and storage; these are not evidence of live ISS reception.

Validation on 2026-10-17: synthetic PySSTV PD120 colour bars decoded through the
native float-audio pipeline into a 640×496 PNG with 496/496 lines. Mean absolute
RGB errors measured inside the eight bars ranged from 2.91 to 11.21 on a 0–255
scale. The image stayed in `/tmp/iss-realtime-validation`, outside the live
gallery. Live RTL-SDR audio acquisition and API Start/Restart/Stop were tested
separately; no actual ISS SSTV image has been received during this validation.

To reproduce the full synthetic test, use the test-only venv Python with
`tests/iss_native_replay_test.py --data /tmp/new-isolated-iss-test-directory`.
It generates its own colour bars/WAV and checks native mode, all 496 rows, geometry
and RGB errors. It refuses to use an existing directory.
