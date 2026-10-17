# Fáze 3: Obal (Tauri) — návrh

Navazuje na `2026-10-15-sysmon-app-design.md`, kapitoly „Fáze", „Architektura"
a „Životní cyklus". Ten dokument stanoví, že obal je Tauri 2 kvůli instalátorům,
trayi a dozoru nad sidecarem — ne kvůli webview — a že okno nemá vlastní
frontend. Tenhle dokument rozhoduje, **jak** se to udělá a co je na konci fáze 3
ověřitelné.

## Cíl a rozsah

Postavit kolem hotového démona (fáze 1) a frontendu (fáze 2) nativní obal:

- **okno** Tauri 2 ukazuje na `http://127.0.0.1:8430/`, žádné IPC, žádné
  `@tauri-apps/api`, žádné capabilities;
- **tray** drží aplikaci naživu po zavření okna; menu „Otevřít dashboard"
  a „Ukončit";
- **dozor nad démonem** — spuštění, čekání na port, omezený restart, ukončení;
- **osiřelý démon** nesmí zůstat viset, když Tauri spadne;
- **autostart** se nabídne při prvním spuštění a startuje skrytě do traye;
- druhé spuštění jen zviditelní existující okno.

Démon zůstává zdrojový (`python3 -m sysmon_app`). PyInstaller binárka,
instalátory a měření paměti patří do fáze 4.

## Rozhodnutí

1. **Tauri 2 bez vlastního frontendu.** Okno má `url` na běžícího démona;
   `frontendDist` míří na minimální placeholder, který se nikdy nezobrazí.
   Odpadá CSP, capabilities i bundlování Reactu do obalu. Data si webview tahá
   přímo z démona přes HTTP/SSE.
2. **Zdrojový démon jako potomek.** Tauri spouští `python3 -m sysmon_app`
   s `cwd` = kořen repa. `__main__.py` se nemění — démon o okně dál nic neví.
3. **Osiřelý démon se řeší `PR_SET_PDEATHSIG`.** Návrh původně říkal „démon
   skončí, když se zavře stdout"; to nefunguje, protože démon po startu nic
   nepíše a na zavřenou rouru nenarazí. Rust při spawnu v `pre_exec` nastaví
   `PR_SET_PDEATHSIG = SIGTERM`; když Tauri zemře (i `SIGKILL`), kernel pošle
   démonovi SIGTERM. Závod mezi forknem a `prctl` se ošetří kontrolou
   `getppid()`.
4. **Omezený restart.** Vlastněný démon, který skončí nenulově, dostane max
   3 pokusy s prodlevou 1/2/4 s; pak nativní dialog s posledními řádky stderr
   a volbami „Zkusit znovu" / „Ukončit". Exit code 2 (chybějící build, rozbitá
   konfigurace, bind error) se **nerestartuje** — uživatelská chyba se ukáže
   hned.
5. **Jedna instance.** `tauri-plugin-single-instance`: druhé spuštění zviditelní
   a fokusne existující okno a skončí. Jeden tray, jeden démon.
6. **Autostart se nabídne dialogem.** Nativní GTK `MessageDialog` při prvním
   spuštění s viditelným oknem; Ano zapíše `.desktop`, obě odpovědi zapíšou
   marker. `--hidden` startuje jen do traye a na nic se neptá.
7. **Uživatelský název zůstává „Sysmon".** Tím se uzavírá odložená věc z fáze 2:
   titulek stránky `Sysmon` není chyba, protože `sysmon-app` je technický název
   binárky a balíčku. Menu, titulek okna i titulek stránky používají „Sysmon";
   žádná změna `frontend/index.html`.
8. **Build bez `@tauri-apps/cli`.** Fáze 3 staví `cargo build --manifest-path
   src-tauri/Cargo.toml` a spouští `cargo run`. CLI, bundler a instalátory
   přijdou ve fázi 4. Nevzniká nová JS ani Python závislost.

## Struktura repa

```
src-tauri/
  Cargo.toml            # tauri 2 (tray-icon, image-png), single-instance, libc, gtk
  build.rs              # tauri_build::build()
  tauri.conf.json       # okno, URL démona, identifier, ikony, placeholder
  icons/                # 32x32.png, 128x128.png — generované z icon.svg
  placeholder/
    index.html          # nikdy se nezobrazí; jen aby config měl frontendDist
  src/
    main.rs             # setup, tray, okno, event loop, orchestrace
    sidecar.rs          # spawn, PDEATHSIG, readiness, dozor, restart, ukončení
    autostart.rs        # čisté funkce: cesty, obsah .desktop, marker, --hidden
    ui.rs               # nativní dialogy, tray menu, zobrazení okna
```

Ikony se vygenerují z `frontend/public/static/icon.svg` přes `rsvg-convert`
(nainstalovaný) a commitnou se; SVG zůstává jediným zdrojem.

## Architektura a procesy

```
Tauri (Rust) ──spawn──> python3 -m sysmon_app (dítě, cwd = kořen repa)
     │                         │
     └── WebKitGTK okno ──HTTP/SSE──> 127.0.0.1:8430
```

### Start

1. Tauri zkusí TCP connect na `127.0.0.1:8430`.
   - **Uspěje:** démon už běží (spuštěný ručně nebo jinou instancí). Tauri nic
     nespouští a démona **nevlastní**.
   - **Neuspěje:** ověří, že v aktuálním adresáři existuje
     `sysmon_app/__main__.py`; když ne, ukáže dialog s očekávanou cestou.
     Pak spustí `python3 -m sysmon_app` s `cwd` = aktuální adresář, stdin
     a stdout na `null` a stderr pipovaný do kruhového bufferu (posledních
     ~40 řádků). Nastaví PDEATHSIG.
2. Počká na otevření portu: poll `connect_timeout` po 50 ms, max 10 s.
3. Teprve pak vytvoří/ukáže okno. Tím odpadá „connection refused" při prvním
   vykreslení.
4. Když se port do 10 s neotevře nebo spawn selže, ukáže nativní dialog
   s posledními řádky stderr a volbami „Zkusit znovu" / „Ukončit".

Vlastnictví je jediný stav, který rozhoduje o ukončení a restartu: vlastněný
démon se při ukončení aplikace zastaví, cizí ne.

### Dozor

- Vlastněný démon se sleduje ve vlákně (`Child::wait`); událost jde na hlavní
  vlákno.
- Jakýkoli exit mimo ukončení aplikace, **kromě `rc=2`**, spustí restart
  s prodlevou 1 s, 2 s, 4 s (i `rc=0` je nečekaný konec). Po 60 s úspěšného
  běhu se počet pokusů resetuje, aby tři pády za týden nevyčerpaly rozpočet.
- Exit code 2 → žádný restart; dialog se stderr. Pokud v tu chvíli port 8430
  poslouchá, považuje se to za cizího démona a jen se otevře okno.
- Během ukončení aplikace se nerestartuje.
- Cizí démon se nesleduje; když zmizí, okno ukáže chybu webview a aplikace
  zůstane běžet. Je to vědomá mez fáze 3.

### Ukončení

- Zavření okna (`CloseRequested`) → `prevent_close`, `hide()`. Aplikace žije
  dál v trayi.
- Tray → „Ukončit“ → vlastněnému démonovi SIGTERM, čekat max 5 s, pak SIGKILL;
  cizímu démonovi nic. Potom `app.exit(0)`.
- `SIGTERM`/`SIGKILL` na Tauri: dítě dostane SIGTERM přes PDEATHSIG (backstop
  pro crashe, ne pro běžné ukončení).

### Osiřelý démon — jak se to ověří

`kill -9` na PID Tauri; do 5 s musí zmizet proces `sysmon_app` a port 8430 musí
být volný. Test se dělá opakovaně (5×), protože závod mezi forknem a `prctl`
se nemusí trefit napoprvé.

### Druhá instance

`tauri-plugin-single-instance` v `setup` zaregistruje callback, který zavolá
`show()` + `set_focus()` na existujícím okně. Druhý proces skončí. Démon se
nespouští podruhé, protože port už poslouchá.

## Okno a tray

- **Okno:** 1180×820, min 360×560 — stejné hodnoty jako `sysmon/desktop.py`.
  Nativní titulek `uzivatel@host — Sysmon`; když uživatel nejde zjistit, jen
  host; když ani host, `Sysmon`. Titulek se nastaví při vytvoření okna
  (Rust: `$USER` + `gethostname`).
- **Zavření** jen schová okno; proces i tray zůstávají. **Když se tray
  nepodaří vytvořit** (prostředí bez StatusNotifier hosta), okno se při
  zavření ukončí místo schování — jinak by aplikace zmizela bez cesty zpět.
  Ze stejného důvodu se `--hidden` v takovém prostředí ignoruje a okno se
  ukáže.
- **Tray:** ikona z `src-tauri/icons/`, tooltip „Sysmon", levý klik otevře
  dashboard, menu „Otevřít dashboard" a „Ukončit". Žádné další položky (YAGNI).
- Ikony: `rsvg-convert -w 32 -h 32 … -o icons/32x32.png` a totéž pro 128;
  stejná ikona pro okno i tray.

## Autostart

- Cesty respektují XDG: `$XDG_CONFIG_HOME` jen když je absolutní, jinak
  `~/.config` (stejné pravidlo jako démon).
- Marker: `<config>/sysmon-app/autostart-asked`.
- Soubor: `<config>/autostart/sysmon-app.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=Sysmon
Comment=Dashboard systémových metrik
Exec="<cesta k aktuální binárce>" --hidden
Terminal=false
X-GNOME-Autostart-enabled=true
```

- Dialog se ukáže jen když **neexistuje marker ani `.desktop`** a aplikace
  neběží s `--hidden`. „Ano" zapíše `.desktop`, „Ne" nic; obě volby zapíšou
  marker. Když `.desktop` existuje, dialog se neukáže a marker se doplní.
- `--hidden` = okno se vytvoří neviditelné, aplikace žije v trayi. Používá ho
  autostart.
- **Vědomá mez:** v `Exec` je cesta k vývojové binárce (`target/debug/…`).
  Instalovaná cesta a regenerace `.desktop` patří do fáze 4.

## Závislosti

- **Systém:** chybí jen `webkit2gtk-4.1` (`sudo pacman -S webkit2gtk-4.1`).
  `gtk3`, `libayatana-appindicator`, `librsvg`, `base-devel` a `openssl` už
  nainstalované jsou (ověřeno 2026-10-17).
- **Rust:** `tauri` 2 s features `tray-icon` a `image-png`, `tauri-build` 2,
  `tauri-plugin-single-instance` 2, `libc` 0.2 a `gtk` 0.18 (verze, kterou
  používá Tauri 2). Žádný HTTP klient — readiness je TCP connect, data tahá
  webview.
- **Python a JS:** žádná nová závislost. Build obalu je `cargo`, ne npm.

## Spuštění

```bash
sudo pacman -S webkit2gtk-4.1        # jednorázově
cd frontend && npm ci && npm run build
cargo run --manifest-path src-tauri/Cargo.toml
# skrytě (autostart): … -- --hidden
```

Démon potřebuje build frontendu; bez něj skončí českou větou a rc=2, což obal
ukáže v dialogu.

## Testy a ověření

**Rust unit testy** (`cargo test --manifest-path src-tauri/Cargo.toml`) pokryjí
čistou logiku bez GUI:

- cesta k markeru a `.desktop` včetně relativního `XDG_CONFIG_HOME`;
- obsah `.desktop` a quoting `Exec` (mezery, uvozovky, backslash);
- parsing `--hidden`;
- titulek okna (`user@host`, jen host, ani jedno);
- plán backoffu 1/2/4 s a rozhodnutí „restartovat / nerestartovat" pro kódy
  0, 2 a ostatní.

**Skriptované lifecycle kontroly** (měřené, ne čtené):

1. Aplikace startuje vlastního démona: `ss -ltnp` ukáže 8430, `ps --ppid
   <tauri>` ukáže `python3 -m sysmon_app`.
2. `kill -9 <tauri>` → do 5 s je 8430 volný a žádný `sysmon_app` neběží (5×).
3. Ručně spuštěný démon + aplikace → na 8430 je jediný listener; ukončení
   aplikace cizího démona nezabije.
4. Druhé spuštění → druhý proces skončí a nevznikne druhý `sysmon_app`.
5. Zabití vlastněného démona (`SIGKILL`) → do ~2 s běží nový a port je zpět.
6. `cargo build` a `cargo test` projdou.

**GUI kontroly** (ručně na KDE Wayland, screenshot přes `spectacle`):

- okno se otevře a ukazuje 9 karet; screenshot porovnaný s prohlížečem na 8430;
- zavření okna → okno zmizí, proces žije, tray ikona zůstává;
- tray „Otevřít dashboard" → okno zpět; „Ukončit" → proces i démon skončí;
- první spuštění s prázdným `XDG_CONFIG_HOME` → dialog autostartu; „Ano" zapíše
  `.desktop` se správným obsahem; druhé spuštění se neptá;
- `--hidden` → žádné okno, jen tray;
- chybový dialog: spustit aplikaci s rozbitým buildem (přesunutý
  `sysmon_app/web/`) → dialog s českou větou démona, ne tichý pád.

**Regrese:** `python3 -m unittest discover -s tests -t .` zůstává **156 testů
OK** (s buildem), `npm run typecheck` projde, `git -C ../sysmon status --short`
je čistý.

## Rizika

- **PDEATHSIG závod.** Kdyby Tauri zemřel mezi forknem a `prctl`, dítě by
  osiřelo. Proto se po `prctl` kontroluje `getppid()`; test se opakuje 5×.
- **Tray bez StatusNotifier hosta.** V prostředí bez panelu (headless, holý
  Wayland) se ikona neukáže. KDE panel na vývojovém stroji je; ověření je
  ruční a je to vědomá mez, ne skrytá vada.
- **WebKitGTK vs Chromium.** Chování a paměť webview se mohou lišit. Fáze 3
  ověřuje jen to, že okno funguje; paměť měří až fáze 4 v reálném okně.
- **Port 8430 obsazený cizí službou.** Aplikace ji považuje za démona a ukáže
  její stránku. Detekce cizí služby je mimo rozsah; 8430 je rezervovaný tomuto
  produktu.
- **Vývojové cesty.** `Exec` v autostartu a `cwd` sidecaru míří do repa. Po
  `cargo clean` autostart nefunguje; fáze 4 to nahradí instalovanými cestami.
- **Jedna instance potřebuje session DBus.** `tauri-plugin-single-instance`
  na Linuxu komunikuje přes DBus; v běžné KDE session je k dispozici, ale
  headless testy musí běžet pod `dbus-run-session`.

## Co fáze 3 nedělá

PyInstaller binárku, `.deb`/`.rpm`/AppImage/PKGBUILD, instalované cesty,
měření paměti okna (fáze 4), Windows a macOS, akce a token, změny kolektorů
nebo chování frontendu. Žádné nové routy — démon zůstává jen GET `/`,
`/static/*`, `/stats` a `/events`.

## Hotovo znamená

1. `cargo build --manifest-path src-tauri/Cargo.toml` projde.
2. `cargo run …` otevře okno s dashboardem; screenshot ukazuje **9 karet**
   shodných s prohlížečem na 8430.
3. Zavření okna aplikaci neukončí; tray ikona zůstává a „Otevřít dashboard"
   okno vrátí.
4. Tray „Ukončit" ukončí aplikaci i vlastněného démona; 8430 je volný.
5. `kill -9` na Tauri ukončí i démona (PDEATHSIG); 8430 je volný — opakovaně.
6. Ručně spuštěný démon zůstane po ukončení aplikace běžet a aplikace
   nespustí druhý.
7. Pád vlastněného démona → max 3 restarty s 1/2/4 s, pak dialog; exit code 2
   se nerestartuje a ukáže stderr.
8. První spuštění nabídne autostart; „Ano" zapíše `.desktop` s `--hidden`;
   marker zabrání opakování; `--hidden` startuje bez okna.
9. Druhé spuštění jen zviditelní existující okno a skončí.
10. `cargo test` projde; `python3 -m unittest discover -s tests -t .` zůstává
    156 testů OK; `npm run typecheck` projde.
11. `sysmon` je nedotčený (`git -C ../sysmon status --short` čistý).
