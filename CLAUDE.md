# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Zabalená desktopová aplikace se systémovými metrikami pro Linux — okno i telefon.
Druhý, samostatný produkt vedle `sysmon`, který zůstává zamrzlý a funkční.
`sysmon` je pro vývojáře (vlastní stroj, akce, token); `sysmon-app` je pro
lidi, kteří si to nainstalují dvojklikem.

**Do `../sysmon` se nesahá.** Je to zároveň reference i záchranná síť a některé
moduly se z něj přenášejí (viz „Kolektory" níže).

Všechny uživatelské texty, komentáře a docstringy jsou **česky**; uživatelské
hlášky s diakritikou, komentáře bez (zděděný styl).

Aktuální stav: `docs/STATE.md`. Historie fází: `docs/historie.md`. Návrhy:
`docs/superpowers/specs/`, plány a trackery: `docs/superpowers/plans/`.

## Jak se tady pracuje

Práce jde **po taskách z plánu** a **po jednom tasku se zastavuje**.

1. Vezmi první nedokončený task aktuální fáze z `*.tasks.json` vedle plánu.
2. Implementátor je **čerstvý subagent**; dostane **plné znění tasku**, ne celý
   plán, a plán si sám nečte.
3. Výsledek **ověř sám proti repu** — `git log`, `diff`, spuštěné testy. Nikdy
   ne podle toho, co subagent napíše do hlášení.
4. **Recenze zadání** (jiný subagent): odpovídá kód přesně zadání? Nic navíc,
   nic míň? Recenzent dostane `docs/review-lessons.md` a výslovný pokyn nevěřit
   hlášení implementátora. Implementátor ho nedostane.
5. **Recenze kvality** (další subagent) — až po té první; také dostane
   `docs/review-lessons.md`.
6. Nálezy buď zadej k opravě, nebo **odůvodni, proč se zamítají**. Nikdy tiše.
   Opravy dělá tentýž implementátor a po opravách se recenze opakuje.
7. Konec tasku: označ task v `.tasks.json` jako `completed`, přepiš
   `docs/STATE.md` (max 20 řádků), commitni s explicitními cestami a skonči.
   Nezačínej další task.

**Stop pravidlo recenzní smyčky:** maximálně **3 kola** recenzí na task.
Poslední kolo ověřuje **jen deltu**, opravují se **jen blokující nálezy**;
všechno ostatní se zapíše do plánu jako vědomá mez.

**Když testy selhávají nebo task nejde dokončit:** task **neoznačuj jako
`completed`**, zapiš problém do `docs/STATE.md` a skonči.

**Zásady pro zadání každého subagenta:**

- Nikdy necommituj na `main`; pracovní větev je v zadání fáze. Dokončené fáze
  zůstávají jako záchranná síť.
- **Nikdy nesahat do `../sysmon`** — čte se z něj, nepíše.
- `git add` **jen s explicitními cestami**, nikdy `-A` ani `.`.
- Implementátor needituje nic pod `docs/` ani soubory jiných tasků; výjimky
  stanoví zadání tasku.
- Žádné nové **Python** závislosti a žádný `pyproject.toml`. Build step
  existuje jen ve `frontend/` (Vite); nové JS závislosti smějí být jen tam
  a žádná nesmí být runtime závislost stažená z CDN — build musí zůstat
  soběstačný.
- Příkazy spouštěj s minimálním výstupem (`--quiet`, `| tail -n 40`); při
  chybě ukaž jen relevantní část.

## Commands

```bash
python3 -m unittest discover -s tests -t . -v   # celá sada (176 testů)
python3 -m unittest tests.test_rates -v         # jeden modul

python3 -m sysmon_app                           # démon na 8430 (--host/--port přebijí config)

cd frontend && npm ci && npm run build          # build do sysmon_app/web/
cd frontend && npm run dev                      # dev server s proxy na 8430

cargo test --manifest-path src-tauri/Cargo.toml
cargo run --manifest-path src-tauri/Cargo.toml
```

Python závislost je **jen `psutil`**. Testy jsou stdlib `unittest`; pytest je
vynechaný záměrně. JS závislosti žijí jen ve `frontend/package.json` a lockfile
se commituje. `sysmon_app/web/` je výstup buildu, ne zdroj.

## Architektura

### Balíček `sysmon_app/`

| Soubor | Role |
|---|---|
| `config.py` | konstanty, `Settings`, načtení `config.toml` |
| `collectors/` | jeden modul na **oblast**, ne na metriku |
| `feed.py` | `SnapshotFeed` — jeden sběrný cyklus pro N odběratelů |
| `monitor.py` | `Monitor.snapshot()` — kontrakt |
| `server.py` | HTTP: SPA, `/stats`, `/events` (SSE) |
| `__main__.py` | vstupní bod — `python3 -m sysmon_app` |
| `web/` | build z `frontend/` (ignorovaný gitem); servíruje `server.py` |

### Zbytek repa

| Soubor | Role |
|---|---|
| `frontend/` | React/Vite zdroj; build → `sysmon_app/web/` |
| `src-tauri/` | Tauri 2 obal: okno, tray, sidecar démona, autostart |
| `packaging/` | PyInstaller build démona, ověření balíčků, PKGBUILD |
| `tools/measure_memory.py` | hodinové měření paměti okna (stdlib) |
| `tests/` | stdlib unittest sada |

### Jeden sběrný cyklus, ne jeden na klienta

`sysmon` čte kolektory v každém HTTP požadavku z vlastního vlákna, což je race,
kterou jeho `CLAUDE.md` vede jako „přijaté, ne opravované". Tady to zmizí:
`SnapshotFeed` tiká jednou za `TICK_SEC` (1,5 s) a odběratelé (okno, telefon)
se vezou. Kolektory s rate stavem (`net`, `disk`) se tak nemůžou rozbít
souběžným čtením.

Přenos dat je **SSE, ne WebSocket** — produkt jen zobrazuje, tok je jednosměrný,
a `EventSource` si reconnect řeší sám. WebSocket by znamenal FastAPI + uvicorn.

### Kontrakt snapshotu

`Monitor.snapshot()` skládá jediný plochý dict, který jde na `GET /stats` i do
SSE. Vždy je v něm **16 klíčů**: `host`, `user`, `cpu`, `cpu_cores`, `mem`,
`swap`, `loadavg`, `disk`, `processes`, `system`, `gpu`, `battery`,
`battery_history`, `net`, `services`, `containers`. Sedmnáctý `cpu_temp` se
přidává **jen když ho stroj umí přečíst** — jeho nepřítomnost je platný stav.

Kontraktní test proto kontroluje **přítomnost klíčů, ne jejich typy**:
`loadavg` a `cpu_temp` legitimně bývají `null`. Kdyby se kontrolovaly typy,
test by na stroji bez teplotních čidel lhal.

### Kolektory zděděné ze sysmonu

Kolektory se **kopírují, nepřepisují** — jsou odladěné proti skutečnému
hardwaru (klíče teplotních čidel se liší stroj od stroje, AMD a NVIDIA mají
různé cesty, `/proc/net/tcp` má LISTEN ve sloupci 4 jako `0A`). Povolené
odchylky jsou jen: importy na `sysmon_app.*`, odstranění akcí (`terminate()`,
`restart()`, `validate_container_name`), předání portů argumentem a úpravy
komentářů/docstringů. Ověřuje se `diff`; `../sysmon` zůstává čistý.

**Na co si dát pozor — zděděné pasti:**

- **`system` a `processes` nedodržují konvenci `available: False`.** Vrací
  `None`, částečný dict, nebo rovnou seznam. Indexovat na nich `['available']`
  nejde a render musí počítat s `null` i s chybějícím klíčem.
- **`net` nemá vlastní `try`.** `Monitor.snapshot()` ho obaluje `_safe(...)`
  s fallbackem, takže výpadek síťových čítačů degraduje jen kartu a sběrný
  cyklus pokračuje. Stejně jsou obalené `system` a `processes`.
- **`disk.py` po výpadku `disk_io_counters` neposune baseline** (`_prev_t`
  a čítače se aktualizují jen v úspěšné větvi). Další úspěšné čtení tedy
  průměruje přes celou mezeru místo aby hlásilo špičku. Vypadá to zamýšleně.
- **`cpu_percent(interval=None)` a rate kolektory potřebují protočení.**
  `Monitor.prime()` musí zavolat `psutil.cpu_percent`, `net.read()`,
  `disk.read()` **a `get_top_processes()`** na **týchž instancích**, které pak
  čte `snapshot()`; stav je v instanci, ne v modulu.

### Jediné místo, kde se tvar kopie mění: `ports.py`

Seznam sledovaných portů je stroj-specifický, takže patří do konfigurace a obě
funkce ho berou **argumentem** — `listening_ports(ignored_ports)`
a `get_services(watch_ports, ignored_ports)`. Modul proto nemá **ani jeden
import**.

`TCP_FILES` zůstává modulová proměnná čtená **až při volání**, ne default
argument — testy ji monkeypatchují, aby šlo parsování zkoušet bez `/proc`.
„Vylepšit" ji na parametr znamená rozbít testy.

`KNOWN_PORTS` ze `sysmonu` se **nepřenáší a nemá se vracet.** `watch_ports` je
od uživatele; kdo si napíše `80 = "MujWeb"`, dostal by s ním tiše `"HTTP"`.

## Balení a instalace

Instalovaný layout je stejný pro `.deb`, `.rpm`, AppImage i `PKGBUILD`:

```
/usr/bin/sysmon-app
/usr/lib/sysmon-app/daemon/sysmon-app-daemon
/usr/lib/sysmon-app/daemon/_internal/…
/usr/share/applications/sysmon-app.desktop
/usr/share/icons/hicolor/{32x32,128x128}/apps/sysmon-app.png
```

- `packaging/build-daemon.sh` buildí démona PyInstallerem jako onedir. Výchozí
  režim v `debian:13` (portabilní, glibc 2.39), `--host` nativně pro Arch
  a PKGBUILD.
- `packaging/verify-package.sh deb|rpm <balíček>` nainstaluje balíček
  v `debian:13`/`fedora:42`, zkontroluje strom, desktop a ikonu a spustí
  bundled démona na `/stats` i `/events`; vše běží uvnitř kontejneru.
- `packaging/arch/PKGBUILD` staví stejný layout nativně; zdrojový tarball se
  generuje z commitu (`git archive … HEAD`, viz README).
- Obal hledá démona relativně ke své binárce, takže stejná cesta funguje ve
  všech balíčcích i v rozbaleném stromu. Vývojový režim zůstává
  `python3 -m sysmon_app`.
- Desktop šablona drží `Name=Sysmon` a `StartupWMClass=Sysmon`; instalovaná
  aplikace při prvním běhu tiše přepíše autostart z vývojové cesty a respektuje
  AppImage (`APPIMAGE`) i vypnutý autostart.
- Minimální glibc: `.deb`/`.rpm` potřebují 2.39 (Debian 13+, Ubuntu 24.04+,
  Fedora 42+). AppImage si WebKitGTK veze z Archu, takže vyžaduje glibc 2.44.

Build artefakty (`packaging/.venv/`, `packaging/build/`, `packaging/daemon/`,
`packaging/daemon-build/`, `packaging/arch/src/`, `packaging/arch/pkg/`,
`packaging/arch/*.pkg.tar.zst`, `src-tauri/target/`) nejsou v gitu.

## Měření paměti

`tools/measure_memory.py` (jen stdlib) měří 60 min v reálném okně, prvních
20 min je warmup. Ploché = lineární trend RSS `WebKitWebProcess` ≤ 5 MB/h
a rozdíl mediánů prvních a posledních 10 min ≤ 15 MB. Návratové kódy:
0 ploché, 1 překročený práh, 2 měření nešlo.

Naměřeno 2026-10-25: slope `web` −7,31 MB/h, delta −3,18 MB → ploché. Původní
5minutový warmup dal 15,39 MB/h; data ukázala náběh WebKit heapu, ne leak,
proto se warmup prodloužil na 20 min (schváleno uživatelem). Podrobnosti jsou
v README a v uzavření Tasku 5 v plánu fáze 4.

## Konfigurace

`$XDG_CONFIG_HOME/sysmon-app/config.toml` (fallback `~/.config`), stdlib
`tomllib`. Relativní `XDG_CONFIG_HOME` se ignoruje podle XDG basedir spec.

Povolené klíče jsou **jen** `host`, `port`, `watch_ports`, `ignored_ports`.
Neznámý klíč je **tvrdá chyba** s cestou k souboru — tichý překlep by uživateli
vzal nastavení, aniž by se dozvěděl proč. Rozbitá konfigurace se **nepolyká**:
`load_settings` vyhazuje `ValueError` s cestou v hlášce, a to i pro špatný
*typ* hodnoty. `__main__` chytá `ValueError` a tiskne větu, ne traceback.

## Bezpečnost a soukromí

**Žádná autentizace, žádné akce, žádné POST routy.** Token, validátory a routy
`/action/*` existují ve `sysmonu` jen kvůli akcím; tady není co chránit.

Server defaultně poslouchá na `0.0.0.0`, aby dashboard fungoval z telefonu —
**kdokoli v té síti vidí seznam procesů a portů**. Na domácí LAN je to vědomá
volba; v cizí síti patří do konfigurace `host = "127.0.0.1"`.

Port je **8430**, ne 8420 — `sysmon` má 8420 a oba poběží na jednom stroji.
Port je stabilní: telefon má uloženou URL.

## Testy

Stdlib `unittest`, `python3 -m unittest discover -s tests -t .` — **176 testů**.
Pokrývají parsování `/proc/net/tcp`, rate matematiku, seskupování kontejnerů,
validaci konfigurace, kontrakt snapshotu, frontend build a měření paměti.
Testy tokenu a akcí se ze `sysmonu` nepřenášejí.

Frontend nemá unit testy; hlídá ho `npm run typecheck` (a `npm run build`),
kontrakt v `frontend/src/types/snapshot.contract.ts` a
`tests/test_frontend_build.py` (build bez cizích originů, headless Chromium:
stabilita seznamů, polling fallback). Bez buildu nebo Chroma se piny přeskočí.

Rust testy: `cargo test --manifest-path src-tauri/Cargo.toml` (53 testů).
