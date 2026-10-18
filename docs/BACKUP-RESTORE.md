# Záloha a obnova

## Co je na GitHubu

- Všechny místní zdrojové soubory projektu, web, testy a nativní EME adaptér.
- Instalační a nasazovací skripty, jednotky a dokumentace.
- Export aktuální konfigurace, včetně OpenWebRX profilů a záložek.
- Seznam systémových balíčků a výchozího nastavení systemd služeb.

Přístupové údaje OpenWebRX, API klíče, SSH klíče, přihlášení GitHub,
TLS privátní klíče, databáze historie a dekódované obrázky nejsou v Gitu.
Konfigurace obsahuje polohu stanoviště a značku na výslovné zadání vlastníka.

## Místní úplná provozní záloha

Skript nevypíná příjem. SQLite kopíruje pomocí `Connection.backup`, takže
zahrnuje i potvrzené změny z WAL. Ostatní soubory kopíruje za běhu; nejde
o transakční obraz všech služeb ve stejném okamžiku ani o obraz SD karty.

```bash
sudo python3 tools/backup-project.py \
  --public-dir "$PWD/github-backup" --private-dir "$PWD/backups"
```

Soubor `backups/radio-center-private-<UTC>.tar.gz` má oprávnění 600, adresář 700.
Obsahuje nasazený `/opt/radio-center`, historii, galerie, konfiguraci OpenWebRX
včetně účtů, nginx a provozní nastavení systému. **Obsahuje přihlašovací údaje**;
nepatří do veřejného repozitáře. Ulož ho na bezpečné oddělené úložiště.
Nepřenáší klíče SSH, přihlášení GitHub ani osobní admin sudoers.
Dočasné IQ/pracovní soubory Meteoru, mezipaměť a SQLite lock/shm se vynechávají.

Ověření integrity:

```bash
cd backups
sha256sum -c radio-center-private-<UTC>.tar.gz.sha256
tar -tzf radio-center-private-<UTC>.tar.gz | head
```

## Obnova z veřejného repozitáře

1. Připrav odpovídající OS, OpenWebRX+, nginx a dekodéry podle
   [INSTALLATION.md](INSTALLATION.md).
2. Nainstaluj projekt mimo důležitý příjem. Poté zastav přijímače a monitory,
   aby se konfigurace během obnovy neměnila.
3. Zkopíruj vybrané JSON z `configuration/var/lib/radio-center/` do
   `/var/lib/radio-center/`, vlastník `radio-center:radio-center`, režim 600.
   Před přepsáním existující konfiguraci zazálohuj. Pro jiné stanoviště nejdřív
   uprav polohu, značku a serial SDR.
4. OpenWebRX `settings.json` a `bookmarks.json` obnov při zastaveném OpenWebRX,
   zachovej jeho vlastnictví. Prázdné API klíče/přihlašovací údaje doplň ručně;
   uživatelské účty nejsou ve veřejném exportu.
5. Exportované jednotky v `configuration/etc/systemd/system/` zachycují skutečně
   nasazené konflikty všech rádiových služeb. Lze je obnovit po kontrole cest.
6. Zkontroluj LAN omezení nginx a sudoers, potom `systemctl daemon-reload`.
   Spusť `radio-center.service`, `radio-return.service` a požadované monitory.
   Zapnutí při bootu nastav podle vlastního záměru a exportu `inventory/`.
7. Ověř API, web, skutečné otevření SDR a předávání/vracení přijímače.

Současný export není automatická bezobslužná obnova celého systému. Nekopíruj
veřejný strom `configuration/etc` do `/etc` bez kontroly na jiném stroji.

## Obnova místní zálohy

Nejprve ověř checksum a rozbal archiv **do pracovního adresáře**, například
`/tmp/radio-restore`; ne rovnou do `/`. Vyber odpovídající aplikaci, nastavení,
databáze a galerie. Při kopírování databází musí být příjem i backend zastavený;
neobnovuj staré `-wal`/`-shm` soubory. Provozní lease a stavové JSON obnovuj pouze
pro diagnostiku, nikdy pro automatické obnovení cizí/ukončené relace.
Ponech správné vlastníky, aplikuj `daemon-reload`, ověř služby a nginx.

Záloha obsahuje citlivé soubory; i pracovní adresář obnovy nastav na režim 700.

## Aktualizace 18. 10. 2026 — ADS-B

Veřejná záloha obsahuje tar1090 integraci, instalátory feederů, webové sdílení
s bezpečnou změnou FR24 klíče a nastavení MLAT z globálních údajů. Soubor
`configuration/feeders.json` exportuje pouze povolené provozní hodnoty;
sharing key FR24 a UUID přijímače se do Gitu neexportují.

Soukromý archiv navíc obsahuje `/etc/fr24feed.ini`, konfigurace ADSBexchange,
tar1090 a jejich instalované soubory i systemd jednotky. Je určený pro obnovu
původního stanoviště; FR24 klíč nepoužívej souběžně na druhém přijímači.
Statistický balíček ADSBexchange je v záloze pouze tehdy, pokud byl skutečně
nainstalován. Jeho připravený instalační skript neznamená aktivní odesílání.
