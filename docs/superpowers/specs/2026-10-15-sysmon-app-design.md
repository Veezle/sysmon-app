# sysmon-app — desktopová podoba sysmonu pro ostatní

Datum: 2026-10-15
Stav: k implementaci
Projekt: `sysmon-app` — nový samostatný repozitář vedle `sysmon`

## Cíl

Zabalená desktopová aplikace, kterou jde dát člověku, jenž nepoužívá terminál.
Nainstaluje ji dvojklikem, dostane ikonu do menu, a vidí na svém stroji tytéž
metriky, jaké dnes ukazuje `sysmon` — v okně i na telefonu.

Existující `sysmon` se **nemění**. Běží dál tak, jak je, včetně ukončování
procesů a restartu kontejnerů. Toto je druhý, samostatný produkt; rozdíl je
v publiku, ne v tom, co měří.

## Mimo rozsah

| Věc | Proč |
|---|---|
| Akce (ukončit proces, restart kontejneru) | Aplikace pro cizí lidi jen zobrazuje. Zásah do cizí rozpracované práce je zodpovědnost, kterou nechceme. |
| Token a autentizace | Token, validátory a routy `/action/*` existují **jen** kvůli akcím. Bez akcí není co chránit. |
| Windows a macOS | Kolektory čtou `/proc` a `/sys`. Na Windows by šlo o přepis sběru dat, ne o balení. |
| Redesign vzhledu | Současný vzhled je odladěný. Výměna technologie a výměna designu jsou dvě různé práce; děláme jen tu první. |
| Změny v repu `sysmon` | Oba produkty žijí vedle sebe. `sysmon` je referencí i záchrannou sítí. |

## Rozhodnutí

| Otázka | Volba | Proč |
|---|---|---|
| Platforma | Jen Linux | Kolektory zůstávají bez přepisu. |
| Instalace | Dvojklik, bez terminálu | `.deb`/`.rpm` přes Tauri bundler; AppImage s přiznanou prerekvizitou. |
| Telefon | Musí zůstat klientem | UI servíruje démon, ne aplikace. Jeden Vite build, jedna cesta doručení. |
| Topologie | Každý sám sebe | Jeden proces, jeden stroj, jeden dashboard. |
| Akce | Žádné | Viz „Mimo rozsah". |
| Backend | Python zůstává (sidecar) | 700 řádků odladěných kolektorů a jejich testů se nepřepisuje. |
| Přenos dat | SSE, ne WebSocket | Display-only je jednosměrné. Navíc jeden sběrný cyklus pro N klientů místo čtení kolektorů na každý požadavek. |
| Obal okna | Tauri 2 | Kvůli instalátorům, trayi a dozoru nad sidecarem — ne kvůli webview. |
| Vzhled | Port současného | Odladěný; redesign je jiná práce. |
| Výchozí port | 8430 | `sysmon` má 8420 a oba poběží na jednom stroji. |
| Názvy | binárka `sysmon-app`, v menu „Sysmon" | `sysmon` je v menu schovaný (`NoDisplay=true`), takže si nekonkurují. |

## Fáze

Není to jeden plán. Jsou to čtyři celky, z nichž každý má smysl ověřit zvlášť
a každý dostane vlastní spec → plán → implementaci.

1. **Démon** — převzít kolektory, postavit SSE, konfigurace, kontrakt, testy.
2. **Frontend** — React + TS + Vite, port současného vzhledu.
3. **Obal** — Tauri: okno, tray, dozor nad sidecarem, nabídka autostartu.
4. **Balení a měření** — `.deb`/`.rpm`/AppImage/PKGBUILD a měření paměti.

Pořadí není libovolné: fáze 1 jde ověřit **dnešním frontendem** z `sysmonu`,
protože kontrakt se nemění. Když proti novému démonu funguje stará UI, je
hotová fáze 1 správně — a to je ověření, které nic nestojí. Fáze 4 je poslední
i proto, že měření paměti má smysl až na hotovém okně.

## Architektura

Tři části. Každá má jednu zodpovědnost a je nahraditelná zvlášť.

**Démon** — Python, PyInstaller. Sbírá metriky, drží HTTP server a **veze v sobě
Vite build** (`dist/`). Servíruje ho oknu i telefonu. Tohle je jediná část, která
něco ví o hardwaru.

**Okno** — Tauri. Nemá vlastní frontend, ukazuje na `http://127.0.0.1:8430`.
Žádné IPC, žádné `@tauri-apps/api`, takže odpadá konfigurace capabilities i CSP.
Tauri tu není kvůli webview (to dnes dělá pywebview) — je tu kvůli instalátorům,
trayi a dozoru nad procesem démona. Kdybychom ty tři věci nepotřebovali, byl by
Tauri dražší pywebview.

**Tray** — drží aplikaci naživu po zavření okna. Menu: otevřít dashboard, ukončit.

### Kontrakt

Jediné rozhraní mezi démonem a UI. Musí být popsané a testované nezávisle na
jazyce — kdyby se někdy démon přepsal do Rustu, je to výměna motoru, ne přepis
projektu.

| Routa | Význam |
|---|---|
| `GET /` a `/static/*` | SPA (Vite build z démona) |
| `GET /stats` | Plný snapshot. První vykreslení a fallback. |
| `GET /events` | SSE proud snapshotů |

Žádné POST routy, žádná autentizace. To je celý server.

**Snapshot** je dnešní tvar z `Monitor.snapshot()`, beze změny. Vždy přítomné
klíče (16): `host`, `user`, `cpu`, `cpu_cores`, `mem`, `swap`, `loadavg`, `disk`,
`processes`, `system`, `gpu`, `battery`, `battery_history`, `net`, `services`,
`containers`. Sedmnáctý, `cpu_temp`, se přidává **jen když ho stroj umí přečíst**
— jeho nepřítomnost je platný stav, ne chyba.

Kolektory si drží svou obrannou konvenci: při selhání vrací `available: false`
s `error`, nikdy nevyhazují výjimku. Na cizích strojích (bez Dockeru, bez
NVIDIA, bez baterie) je to právě to, co dělá instalaci snesitelnou.

### SSE místo WebSocketu

`GET /events` drží spojení otevřené a posílá `data: <snapshot>\n\n` v jednom
tiku. Prohlížeč si reconnect řeší sám přes `EventSource`.

Přínos není jen ušetřená závislost (FastAPI + uvicorn + pydantic by WebSocket
stály). Hlavní přínos je, že **kolektory tikají jednou pro všechny klienty**.
Dnes čte každý HTTP požadavek kolektory z vlastního vlákna, což je race
zapsaná v `CLAUDE.md` jako „přijaté, ne opravované". Tímhle zmizí.

### Životní cyklus

- Démon binduje **8430**; když je obsazený, okno se připojí k běžícímu démonu
  místo druhého bindnutí. Stejné pravidlo, jaké zná launcher `sysmonu`.
- Port je **stabilní, ne náhodný**: telefon má uloženou URL a náhodný port by ji
  rozbil při každém restartu.
- Zavření okna aplikaci neukončí, jen schová do traye.
- **Autostart se nabídne při prvním spuštění** a appka si sama zapíše
  `~/.config/autostart`. Potichu nastartovat monitor, který nikdo nechtěl, je
  nepříjemné; z balíčku to neděláme.
- Spuštění aplikky dvakrát = druhé okno se připojí k prvnímu démonu.

## Rizika

**Paměť v okně — jediné neověřené riziko.** Tauri na Linuxu je WebKitGTK, tedy
JavaScriptCore: `--js-flags` ani `window.gc()` tam neexistují. Fix, který
u `sysmonu` srazil růst z ~3 GB/hod na plocho, na této platformě **není
k dispozici**, a přibývá React, který při každém tiku alokuje.

Netvrdíme, že to bude zlobit — WebKit má jiný a agresivnější GC než Blink. Ale
je to nezměřené a je to přesně vada, kterou tento projekt už jednou měl. Proto:

> **Acceptance criterion:** paměť okna změřená v reálném okně při 1,5s intervalu
> musí být plochá. Dokud není, není hotovo. Offscreen rig nedokáže nic — u
> `sysmonu` dával úplně jiná čísla a obě jeho tvrzení byla špatná.

**AppImage má prerekvizitu.** Ověřeno na vývojovém stroji: `webkit2gtk-4.1`
tam **není nainstalovaný**. AppImage si systémový webview nést neumí, takže na
stroji bez WebKitGTK nefunguje. Necháváme ho, ale s přiznanou prerekvizitou
v dokumentaci; pro Debian a Fedoru jsou `.deb`/`.rpm` hlavní cesta, protože si
závislost deklarují samy.

**Osiřelý sidecar.** Když Tauri spadne, démon může zůstat viset. Mitigace:
démon skončí, když se zavře jeho stdout. Musí být otestované, ne předpokládané.

**Soukromí při výchozím nastavení.** Aby telefon fungoval, démon poslouchá na
`0.0.0.0`, takže **kdokoli v té síti vidí seznam procesů a portů**. U `sysmonu`
na domácí LAN je to v pořádku; u aplikace, kterou dáš někomu jinému, je to
vědomá volba, ne detail. Konfigurace umí omezit na `127.0.0.1`; dokumentace to
musí říct nahlas.

## Frontend

**React + TypeScript + Vite.** Ne Tailwind — současný vzhled je 585 řádků CSS,
který funguje. Ne Recharts — grafy zůstávají na canvasu; SVG graf stavějící
elementy pro každý bod při 1,5s intervalu je přesně ta věc, kterou jsme jednou
museli odstraňovat.

Vzhled se **portuje**, ne předělává. `tick()` se rozpadne na komponenty, ale
pravidla zůstávají: karty se nepřebudovávají, zapisuje se jen to, co se změnilo,
a na prvcích, které se mění každý tik, se neanimuje `width`, `height` ani
`box-shadow`.

Typy popíšou kontrakt snapshotu, takže „přidání metriky znamená tři místa" se
aspoň zkontroluje překladačem.

## Konfigurace

`$XDG_CONFIG_HOME/sysmon-app/config.toml` (stdlib `tomllib`, žádná závislost).
Patří tam stroj-specifické věci, které dnes žijí v `config.py`:

- `watch_ports` — seznam sledovaných služeb. Dnes je to seznam vývojářova
  notebooku; na cizím stroji je nesmysl.
- `host` — výchozí `0.0.0.0` kvůli telefonu, jde omezit na `127.0.0.1`.
- `ignored_ports`, intervaly.

## Testy

Python zůstává **stdlib `unittest`** — kolektory, SSE, kontrakt snapshotu.
Přebírá se, co dává smysl: parsování portů z `/proc/net/tcp`, seskupování
kontejnerů podle Compose projektu (včetně čárky uvnitř hodnoty labelu), rate
matematika, obsluha statických souborů. Testy tokenu a akcí se **nepřebírají** —
ty patří k funkci, kterou tento produkt nemá.

Frontend: typy a build. Rendering netestujeme (YAGNI).

## Hotovo znamená

1. Aplikace se nainstaluje z `.deb` dvojklikem a objeví se v menu.
2. Okno ukazuje stejné metriky jako `sysmon`, včetně degradovaných karet na
   stroji bez Dockeru, NVIDIA a baterie.
3. Telefon se na dashboard připojí a data se aktualizují bez obnovování stránky.
4. Paměť okna je při 1,5s intervalu plochá (změřeno v reálném okně).
5. Zavření okna telefon neodpojí; ukončení z traye po sobě uklidí démona.
6. `sysmon` se přitom nijak nezměnil.
