# Ověření a známá omezení

Záloha zachycuje existující projekt k 17. 10. 2026. Testy používají oddělené
dočasné databáze; syntetické zprávy se nevkládají do produkční historie.
Výsledek testů v tomto exportu je v `inventory/validation.txt`.

## Ověřeno

- Python testy parsování, konfigurace, historie, validace a předávání SDR.
- JavaScript testy ovládání, panelů, konfigurace, ISS a ADS-B.
- Skutečný příjem ISM a ukládání zpráv; v ADS-B také místní zprávy, ale výrazně
  slabší příjem než na druhém místním přijímači.
- Automatické převzetí a návrat po příjmu Meteoru, návrat předchozí aplikace.
- Nativní dekodéry byly testovány syntetickými nebo testovacími záznamy;
  podrobnosti jsou v dokumentaci jednotlivých aplikací.

## Omezení

- **Meteor M2-4:** příjem 17. 10. 2026 na 137,900 MHz / 72k skutečně běžel,
  ale nesynchronizoval se a nevznikly obrázky. SNR z dekodéru dosáhlo špičkově
  4,1 dB; to samo nepotvrzuje identifikaci signálu družice. Skutečný úspěšný
  LRPT příjem této sestavy není doložen.
- **EME:** spuštění řetězce a testovací dekódování není potvrzení skutečného
  odrazu od Měsíce. Jedno pásmo v čase, 90 kHz; nejde o celé pásmo 430–440 MHz.
  Souběžné dekódování všech podrežimů není zaručené a může přetížit RPi.
- **ISS:** testy Robot36 a AFSK1200 zahrnují syntetický signál a Doppler;
  nezaručují aktivní vysílání při konkrétním přeletu. Packet nepokrývá 9600 baud.
- **ADS-B:** seznam zahrnuje i letadla bez polohy. Panel počítá zprávy za
  posledních 60 s a letadla zachycená v posledních 60 s. Anténa Diamond X200
  a přívod jsou podezřelé pro slabý příjem 1090 MHz; příčina není izolována.
- Web funguje bez otevřeného prohlížeče; mapové podklady potřebují internet,
  předpovědi potřebují čerstvá TLE a digitální režimy synchronizovaný čas.
- Obnova zatím nebyla provedena na nové čisté SD kartě. Dokumentace uvádí
  předpoklady a odděluje opakované nasazení od plného bootstrapu OS.
