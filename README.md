# sysmon-app

Dashboard systémových metrik pro Linux — jako okno i jako stránka na telefonu.
Druhý, samostatný produkt vedle `sysmon`; ten se nemění.

**Stav: fáze 1 (démon), fáze 2 (React frontend), fáze 3 (Tauri okno) i fáze 4
(balení a měření paměti) hotové.** Fáze 4 je ověřená end-to-end — `.deb`,
`.rpm`, AppImage, `PKGBUILD`, instalovaný layout, migrace autostartu
a 60minutové měření paměti okna s 20minutovým warmupem (ploché: slope `web`
−7,31 MB/h, delta −3,18 MB). Návrhy:
`docs/superpowers/specs/2026-10-15-sysmon-app-design.md`,
`docs/superpowers/specs/2026-10-16-faze-2-frontend-design.md`,
`docs/superpowers/specs/2026-10-17-faze-3-tauri-design.md` a
`docs/superpowers/specs/2026-10-17-faze-4-baleni-design.md`.

## Spuštění démona

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
Ukončuje se `Ctrl+C`.

`--host` a `--port` přebijí konfiguraci; `python3 -m sysmon_app --help` vypíše
oba přepínače i s výchozími hodnotami. Když je port obsazený, démon to napíše
česky a skončí — ne tracebackem.

## Okno (Tauri)

Nativní okno je Tauri 2 obal; ukazuje na běžícího démona na 8430, takže
dashboard v okně i v prohlížeči je tentýž. Pokud na 8430 nic neposlouchá,
aplikace démona spustí sama a při ukončení ho zastaví; cizího démona nechá běžet.

Prerekvizita (Arch): `sudo pacman -S webkit2gtk-4.1`. Potřebuje Rust 1.90
a novější (`rust-version` v `src-tauri/Cargo.toml`).

    cargo build --manifest-path src-tauri/Cargo.toml
    cargo run --manifest-path src-tauri/Cargo.toml

Zavřením okna aplikace neskončí — jen se schová do traye. Tray menu má
„Otevřít dashboard“ a „Ukončit“. V prostředí bez StatusNotifier watchera se
tray nevytvoří a zavření okna aplikaci ukončí. Spuštění s `--hidden` začne jen
v trayi (bez traye se okno ukáže); tuhle volbu používá autostart, který se
nabídne při prvním spuštění. Instalovaná aplikace při prvním běhu tiše
přepíše `.desktop` z vývojové cesty (`src-tauri/target/…`) na
`/usr/bin/sysmon-app`, takže po přihlášení najde bundled démona i bez
otevřeného terminálu. Vývojový běh naopak instalovaný autostart nepřepisuje.

Vývojový režim zůstává: `cargo run` z kořene repa spustí démona ze zdrojů
(`python3 -m sysmon_app`), pokud na 8430 nic neposlouchá. Nainstalovaná
aplikace naproti tomu používá bundled démona
z `/usr/lib/sysmon-app/daemon/` a žádný systémový Python nepotřebuje.

## Instalace

Balíčky vyrábí Tauri bundler z kořene repa:

    cargo install tauri-cli --version "^2" --locked   # jen buildový nástroj
    cargo tauri build --bundles deb,rpm,appimage

Výsledky jsou v `src-tauri/target/release/bundle/`. Runtime závislost je jen
WebKitGTK a GTK; `depends` v `src-tauri/tauri.conf.json` je deklaruje pro deb
i rpm.

`.deb` nainstaluj `sudo apt install ./sysmon-app_*.deb` a `.rpm`
`sudo dnf install ./sysmon-app-*.rpm`. WebKitGTK se tím dotáhne sám; ručně
stačí `sudo pacman -S webkit2gtk-4.1` na Archu, `libwebkit2gtk-4.1-0` na
Debianu a `webkit2gtk4.1` na Fedoru.

AppImage je jeden soubor, ale **WebKitGTK si nenese** — bez `webkit2gtk-4.1`
se nespustí. Po `chmod +x` ho jde spustit dvojklikem i z terminálu.

Pro Arch je v `packaging/arch/PKGBUILD` zdrojový build bez Dockeru:

    git archive --prefix=sysmon-app-0.1.0/ \
        -o packaging/arch/sysmon-app-0.1.0.tar.gz HEAD
    cd packaging/arch && makepkg -si

Build potřebuje síť: `npm ci`, `cargo` a `pip install pyinstaller`
(PyInstaller žije v `packaging/.venv`, který je v `.gitignore`). `makepkg`
síť nezakazuje; je to vědomá vlastnost zdrojového buildu. `cargo install
tauri-cli` je jen buildový nástroj, ne závislost produktu.

Všechny čtyři cesty mají stejný layout:

    /usr/bin/sysmon-app
    /usr/lib/sysmon-app/daemon/sysmon-app-daemon
    /usr/lib/sysmon-app/daemon/_internal/…
    /usr/share/applications/sysmon-app.desktop
    /usr/share/icons/hicolor/{32x32,128x128}/apps/sysmon-app.png

Démon je součástí balíčku (PyInstaller onedir), takže instalace
**nepotřebuje systémový Python ani `psutil`**. Minimální glibc je 2.39:
Debian 13+, Ubuntu 24.04+, Fedora 42+. Debian 12 a starší nejsou podporované.

## Paměť

Měření je součást akceptace fáze 4: 60 minut v reálném okně, prvních 20 minut
se zahřívá a do trendu nevstupuje. Ploché znamená lineární trend RSS
`WebKitWebProcess` ≤ 5 MB/h a rozdíl mediánů prvních a posledních 10 minut
≤ 15 MB.

    python3 tools/measure_memory.py --pid <PID> --duration 3600 --interval 10 \
        --warmup 1200 --csv /tmp/sysmon-memory.csv

Nástroj je jen stdlib, čte `/proc`, sčítá RSS stromu potomků do kategorií
`app`, `web`, `network`, `daemon` a `other`; bez `--pid` najde proces
s exe `sysmon-app`. Návratový kód 0 = ploché, 1 = práh překročen,
2 = měření nešlo (málo vzorků nebo proces zmizel). `--warmup` má výchozí
1200 s (20 min).

Naměřeno 2026-10-25 (běh 60 min, 18:42–19:42, 361 vzorků, 241 po warmupu):
slope `web` **−7,31 MB/h** (limit 5), medián prvních 10 min po warmupu
343,0 MB, medián posledních 10 min 339,9 MB (delta **−3,18 MB**, limit 15).
Celková RSS na konci 701,6 MB, RSS démona 30,0 MB, `web` 339,9 MB.
**Verdikt: ploché.**

Původní protokol s 5minutovým warmupem dal slope `web` **15,39 MB/h**
(mediány 335,0 → 339,9 MB, delta +4,8 MB) a práh nesplnil. Data ukázala
náběh WebKit heapu: lineární model přes celý běh vysvětlil jen 31 % rozptylu
(R² ≈ 0,31) a největší skoky byly záporné (až −22,9 MB), takže růst nebyl
trvalý trend. Proto se warmup prodlužuje na 20 minut; na stejném běhu se
delším warmupem je slope −7,31 MB/h a delta −3,18 MB (rozdíl proti
zaokrouhleným mediánům 343,0 − 339,9 = −3,0 MB je zaokrouhlením). Původní
číslo nezastíráme — je součástí vysvětlení změny protokolu.

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

## Soukromí

Server poslouchá na všech rozhraních, aby dashboard fungoval z telefonu.
**Kdokoli v té síti vidí seznam tvých procesů a portů.** Na domácí LAN je to
v pořádku; v cizí síti nastav `host = "127.0.0.1"` a o telefon přijdeš.

Autentizace tu žádná není a ani být nemá — není co chránit: produkt nemá
žádné akce, jen zobrazuje.

## Testy

    python3 -m unittest discover -s tests -t .

Sada má **173 testů** a nepotřebuje volný port 8430 — projde i s běžícím
démonem na 8430. Bez buildu je zelená (`OK (skipped=5)`): piny závislé na
buildu se přeskočí. Piny v `tests/test_frontend_build.py` potřebují build
a dva z nich navíc headless Chrome (`google-chrome-stable` nebo `chromium`).

## Frontend

Zdroj je ve `frontend/` (Vite 8.3.4, React 19.3.1, TypeScript 5.9.3) a build
jde do `sysmon_app/web/`, který je v `.gitignore`. `sysmon_app/web/` je tedy
výstup buildu, ne zdroj.

Pro vývoj běží démon na 8430 a vedle něj Vite dev server:

    cd frontend
    npm run dev

Dev server proxyuje `/stats` a `/events` na démona, takže se po každé změně
nemusí buildit. Frontend jen zobrazuje data a žádné akce neposílá.
