# sysmon-app

Dashboard systémových metrik pro Linux — jako okno i jako stránka na telefonu.
Druhý, samostatný produkt vedle `sysmon`; ten se nemění.

**Stav: fáze 1 (démon) hotová. Fáze 2 (React frontend) je implementovaná;
zbývá její závěrečné end-to-end ověření.** Tauri okno, balení a měření paměti
(fáze 3–4) jsou zatím jen v návrhu. Návrhy:
`docs/superpowers/specs/2026-10-15-sysmon-app-design.md` a
`docs/superpowers/specs/2026-10-16-faze-2-frontend-design.md`.

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

Sada má **156 testů** a nepotřebuje volný port 8430 — projde i s běžícím
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
