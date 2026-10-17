# Komponenty a licence

Repozitář propojuje existující dekodéry; jejich zdroje, názvy a licence zůstávají
u původních autorů. Není stanovena nová společná licence, která by měnila licence
vložených komponent.

| Komponenta | Zdroj / informace |
|---|---|
| OpenWebRX+ | https://github.com/luarvique/openwebrx |
| rtl-sdr | https://osmocom.org/projects/rtl-sdr/wiki |
| rtl_433 | https://github.com/merbanan/rtl_433 |
| WSJT-X / MAP65 | https://wsjt.sourceforge.io/ a https://github.com/WSJTX/wsjtx |
| Dire Wolf | https://github.com/wb2osz/direwolf |
| dxlAPRS / LoRa | https://github.com/oe5hpm/dxlAPRS |
| SatDump | https://github.com/SatDump/SatDump |
| dump1090-fa | https://github.com/flightaware/dump1090 |
| dumpvdl2 | https://github.com/szpajder/dumpvdl2 |
| Dekodéry radiosond | https://github.com/rs1729/RS |
| pycsdr | https://github.com/luarvique/pycsdr |
| Leaflet | https://leafletjs.com/ a https://github.com/Leaflet/Leaflet/blob/main/LICENSE |
| Mapové dlaždice | https://www.openstreetmap.org/copyright |

V `radio-center/static/` je distribuován Leaflet; licenční hlavičky jsou zachované.
Přibalený `radio-center/eme-native/eme-m65` je přijímací adaptér MAP65/WSJT-X pro
Linux aarch64. Je přiložena GPL licence `radio-center/eme-native/COPYING` a
reprodukovatelný sestavovací skript `build.py`, který používá zdrojový archiv
WSJT-X v2.7.0 ověřený SHA256 a provádí úpravy ovladače dekodéru.
Na jiných architekturách je nutné binární soubor znovu sestavit.
