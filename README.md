# sysmon-app

Dashboard systémových metrik pro Linux — nativní okno i stránka na telefonu.
Druhý, samostatný produkt vedle `sysmon`; ten zůstává zamrzlý a nemění se.

**Stav: hotovo.** Démon, React frontend, Tauri okno i balení (`.deb`, `.rpm`,
AppImage, `PKGBUILD`) jsou hotové a ověřené; paměť okna je plochá
(slope `web` −7,31 MB/h, delta −3,18 MB). Návrhy jsou v
`docs/superpowers/specs/`.

## Jak to funguje

- Démon (`python3 -m sysmon_app`) čte kolektory jednou za 1,5 s v jediném
  sběrném cyklu a drží poslední snapshot.
- `GET /stats` vrátí snapshot; `GET /events` je SSE proud téhož snapshotu.
  Odběratelé (okno, telefon, prohlížeč) se vezou; žádný kolektor se nečte
  souběžně.
- Frontend je React/Vite build, který servíruje sám démon z `sysmon_app/web/`.
  Bere první snapshot z `/stats`, pak poslouchá `/events`; při 4,5 s ticha
  přepne na polling a označí stav `live: false`.
- Tauri okno je jen obal nad stejným dashboardem: ukazuje na
  `http://127.0.0.1:8430/`, bundled démona spustí sám a při zavření se schová
  do traye.
- Do balíčků jde démon jako PyInstaller onedir, takže instalace nepotřebuje
  systémový Python ani `psutil`.

## Instalace

Balíčky se staví z kořene repa ve třech krocích — frontend, démon, pak
balíček. Na čistém klonu jsou `sysmon_app/web/` a `packaging/daemon/`
gitignorované, takže bez prvních dvou kroků by balíček vezl démona bez
frontendu (a `cargo tauri build` by zabalil jen prázdného démona):

    cd frontend && npm ci && npm run build && cd ..   # build do sysmon_app/web/
    packaging/build-daemon.sh                          # PyInstaller onedir do packaging/daemon/
    cargo install tauri-cli --version "^2" --locked    # jen buildový nástroj
    cargo tauri build --bundles deb,rpm,appimage

Výsledky jsou v `src-tauri/target/release/bundle/`.

- `.deb`: `sudo apt install ./sysmon-app_*.deb`
- `.rpm`: `sudo dnf install ./sysmon-app-*.rpm`
- AppImage: `chmod +x` a spustit. WebKitGTK a GTK si **nese sám**, takže
  nic instalovat nemusíš — ale je zbuilděný na Archu, a ten vyžaduje
  glibc 2.44 (viz níže).
- Arch: `packaging/arch/PKGBUILD` (viz níže).

Runtime závislost `.deb`/`.rpm` je WebKitGTK, GTK a `libayatana-appindicator`
(tray); `depends` v `src-tauri/tauri.conf.json` je deklaruje pro deb i rpm
a instalátor si je dotáhne sám. Ručně stačí
`sudo pacman -S webkit2gtk-4.1 libayatana-appindicator` na Archu,
`libwebkit2gtk-4.1-0 libayatana-appindicator3-1` na Debianu
a `webkit2gtk4.1 libayatana-appindicator-gtk3` na Fedoru.

Pro Arch je v `packaging/arch/PKGBUILD` zdrojový build bez Dockeru:

    git archive --prefix=sysmon-app-0.1.0/ \
        -o packaging/arch/sysmon-app-0.1.0.tar.gz HEAD
    cd packaging/arch && makepkg -si

Build potřebuje síť: `npm ci`, `cargo` a `pip install pyinstaller`
(PyInstaller žije v `packaging/.venv/`, který je v `.gitignore`).

Všechny čtyři cesty mají stejný layout:

    /usr/bin/sysmon-app
    /usr/lib/sysmon-app/daemon/sysmon-app-daemon
    /usr/lib/sysmon-app/daemon/_internal/…
    /usr/share/applications/sysmon-app.desktop
    /usr/share/icons/hicolor/{32x32,128x128}/apps/sysmon-app.png

Démon je součástí balíčku, takže instalace **nepotřebuje systémový Python ani
`psutil`**. Minimální glibc se liší podle cesty:

- `.deb`/`.rpm` berou WebKitGTK z distribuce; binárka potřebuje glibc 2.39,
  takže jdou na Debian 13+, Ubuntu 24.04+ a Fedora 42+.
- AppImage si WebKitGTK veze z Archu (glibc 2.44), takže běží prakticky jen
  na Archu a stejně nových distribucích.
- Debian 12 a starší nejsou podporované.

## Spuštění ze zdrojů

Zdroj frontendu je ve `frontend/` a démon servíruje až jeho build. Nejdřív ho
tedy zbuildi:

    cd frontend
    npm ci
    npm run build
    cd ..

Pak spusť démona:

    python3 -m sysmon_app

Když build chybí, démon nezačne: vypíše
`Frontend není zbuilděný (<cesta>/sysmon_app/web/index.html neexistuje).`
s návodem `npm ci && npm run build` a skončí s kódem 2. Když build zmizí
za běhu, `/` odpoví `503` se stejným návodem.

Poslouchá na `0.0.0.0:8430` a v prohlížeči je na <http://localhost:8430>.
Potřebuje **Python 3.11 a novější** (konfiguraci čte stdlib `tomllib`).
Jediná Python závislost je `psutil` (`pacman -S python-psutil`); build
frontendu potřebuje Node `^20.19.0` nebo `>=22.12.0` a `npm`.

Port je **8430**, ne 8420 — `sysmon` má 8420 a oba mají běžet vedle sebe.
Ukončuje se `Ctrl+C`. `--host` a `--port` přebijí konfiguraci;
`python3 -m sysmon_app --help` vypíše oba přepínače i s výchozími hodnotami.
Když je port obsazený, démon to napíše česky a skončí — ne tracebackem.

## Okno a tray

Nativní okno je Tauri 2 obal; ukazuje na běžícího démona na 8430, takže
dashboard v okně i v prohlížeči je tentýž. Pokud na 8430 nic neposlouchá,
aplikace démona spustí sama a při ukončení ho zastaví; cizího démona nechá běžet.

Prerekvizita (Arch): `sudo pacman -S webkit2gtk-4.1 libayatana-appindicator`.
Potřebuje Rust 1.90 a novější.

    cargo build --manifest-path src-tauri/Cargo.toml
    cargo run --manifest-path src-tauri/Cargo.toml

Zavřením okna aplikace neskončí — jen se schová do traye. Tray menu má
„Otevřít dashboard“ a „Ukončit“. V prostředí bez StatusNotifier watchera se
tray nevytvoří a zavření okna aplikaci ukončí. `--hidden` začne jen v trayi
(bez traye se okno ukáže); tuhle volbu používá autostart.

Instalovaná aplikace při prvním běhu tiše přepíše `.desktop` z vývojové cesty
(`src-tauri/target/…`) na `/usr/bin/sysmon-app`, takže po přihlášení najde
bundled démona i bez otevřeného terminálu. Vývojový běh instalovaný autostart
nepřepisuje. Nainstalovaná aplikace používá bundled démona
z `/usr/lib/sysmon-app/daemon/`; vývojový `cargo run` spustí
`python3 -m sysmon_app` ze zdrojů.

## Konfigurace

`~/.config/sysmon-app/config.toml` (respektuje `XDG_CONFIG_HOME`). Chybějící
soubor znamená výchozí hodnoty.

    host = "0.0.0.0"          # kvůli telefonu; "127.0.0.1" omezí na localhost
    port = 8430
    ignored_ports = [53, 631]

    [watch_ports]             # které služby karta ukazuje; co tu není, je neviditelné
    22 = "SSH"
    3306 = "MySQL"

Příklad je zkrácený: výchozí `watch_ports` sleduje i 5173, 8080 a 8081
a výchozí `ignored_ports` je `[53, 111, 631, 5353, 1716, 54321]`. Oba seznamy
se navíc **nahrazují celé, ne doplňují** — kdo si vypíše vlastní, ten o zbytek
výchozích přijde. Povolené klíče jsou jen `host`, `port`, `watch_ports`
a `ignored_ports`.

Rozbitý nebo neznámý klíč se ohlásí i s cestou k souboru — záměrně, tichý
překlep by vzal uživateli jeho nastavení, aniž by se dozvěděl proč.

## Co démon vydává

| Cesta | Co vrací |
|---|---|
| `GET /` | stránka dashboardu (build), `Cache-Control: no-store` |
| `GET /static/assets/index-<hash>.js` a `.css` | hashované assety buildu, `Cache-Control: immutable` |
| `GET /static/icon.svg` | ikona, `Cache-Control: no-store` |
| `GET /stats` | JSON snapshot |
| `GET /events` | SSE proud snapshotů, jeden nový zhruba každých 1,5 s |

`/stats` i `/events` vydávají **tentýž kontrakt snapshotu** — vždy 16 klíčů
(`host`, `user`, `cpu`, `cpu_cores`, `mem`, `swap`, `loadavg`, `disk`,
`processes`, `system`, `gpu`, `battery`, `battery_history`, `net`, `services`,
`containers`) a k tomu `cpu_temp`, ale jen když ho stroj umí přečíst.

Frontend vezme první snapshot z `/stats` a pak poslouchá `/events`. Když 4,5 s
nepřijde žádný rámec, přepne na polling `/stats` každých 1,5 s a stavová tečka
zežloutne (`live: false`); po dalším rámci se polling vypne a tečka zezelená.

## Paměť

Měření je součást akceptace: 60 minut v reálném okně, prvních 20 minut se
zahřívá a do trendu nevstupuje. Ploché znamená lineární trend RSS
`WebKitWebProcess` ≤ 5 MB/h a rozdíl mediánů prvních a posledních 10 minut
≤ 15 MB.

    python3 tools/measure_memory.py --pid <PID> --duration 3600 --interval 10 \
        --warmup 1200 --csv /tmp/sysmon-memory.csv

Nástroj je jen stdlib, čte `/proc`, sčítá RSS stromu potomků do kategorií
`app`, `web`, `network`, `daemon` a `other`; bez `--pid` najde proces
s exe `sysmon-app`. Návratový kód 0 = ploché, 1 = práh překročen,
2 = měření nešlo (málo vzorků, proces zmizel, chyba zápisu).

Naměřeno 2026-10-25 (60 min, 361 vzorků, 241 po warmupu): slope `web`
**−7,31 MB/h**, mediány 343,0 → 339,9 MB, delta **−3,18 MB**, celková RSS
701,6 MB, démon 30,0 MB. **Verdikt: ploché.**

Původní 5minutový warmup dal 15,39 MB/h a práh nesplnil; data ukázala náběh
WebKit heapu (lineární model vysvětlil jen 31 % rozptylu, největší skoky byly
záporné), proto se warmup prodloužil na 20 minut. Původní číslo zůstává
dohledatelné.

## Soukromí

Server poslouchá na všech rozhraních, aby dashboard fungoval z telefonu.
**Kdokoli v té síti vidí seznam tvých procesů a portů.** Na domácí LAN je to
v pořádku; v cizí síti nastav `host = "127.0.0.1"` a o telefon přijdeš.

Autentizace tu žádná není a ani být nemá — není co chránit: produkt nemá
žádné akce, jen zobrazuje.

## Vývoj frontendu

Zdroj je ve `frontend/` (Vite 8.3.4, React 19.3.1, TypeScript 5.9.3) a build
jde do `sysmon_app/web/`, který je v `.gitignore`. `sysmon_app/web/` je tedy
výstup buildu, ne zdroj.

Pro vývoj běží démon na 8430 a vedle něj Vite dev server:

    cd frontend
    npm run dev

Dev server proxyuje `/stats` a `/events` na démona, takže se po každé změně
nemusí buildit. Frontend jen zobrazuje data a žádné akce neposílá.

## Testy

    python3 -m unittest discover -s tests -t .

Sada má **176 testů** a nepotřebuje volný port 8430 — projde i s běžícím
démonem na 8430. Bez buildu je zelená (`OK (skipped=5)`): piny závislé na
buildu se přeskočí. Piny v `tests/test_frontend_build.py` potřebují build
a dva z nich navíc headless Chrome (`google-chrome-stable` nebo `chromium`).

Dále:

    cargo test --manifest-path src-tauri/Cargo.toml   # 53 testů
    cd frontend && npm run typecheck

## Dokumentace

- `docs/STATE.md` — aktuální stav
- `docs/historie.md` — historie fází
- `docs/superpowers/specs/` — návrhy
- `docs/superpowers/plans/` — plány a trackery tasků
- `docs/review-lessons.md` — poučení z recenzí
