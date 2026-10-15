# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Zabalená desktopová aplikace se systémovými metrikami pro Linux — okno i telefon.
Vzniká jako **druhý, samostatný produkt vedle `sysmon`**, který zůstává zamrzlý
a funkční. Rozdíl je v publiku, ne v tom, co se měří: `sysmon` je pro vývojáře
(vlastní stroj, akce, token), `sysmon-app` je pro lidi, kteří si to nainstalují
dvojklikem.

**Do `../sysmon` se nesahá.** Je to zároveň reference i záchranná síť, a několik
modulů se z něj přenáší bajt po bajtu (viz „Přenos ze sysmonu" níže).

Všechny uživatelské texty, komentáře a docstringy jsou **česky**; uživatelské
hlášky s diakritikou, komentáře bez (zděděný styl).

## Stav

Fáze 1 (démon) rozpracovaná. Návrh je v
`docs/superpowers/specs/2026-10-15-sysmon-app-design.md`, plán po úlohách v
`docs/superpowers/plans/2026-10-15-faze-1-demon.md`, průběh v `.tasks.json` vedle
plánu. Hotové: Task 1 (skelet + `config.py`), Task 2 (`system`, `processes`),
Task 3 (`net`, `disk`), Task 4 (`ports`). Zbývá `gpu`, `battery`, `docker`, pak
`feed`, `monitor`, `server`, `__main__` a ověření.

Fáze 2–4 (React frontend, Tauri obal, balení a měření paměti) jsou zatím jen
v návrhu.

## Commands

```bash
python3 -m unittest discover -s tests -t . -v   # celá sada
python3 -m unittest tests.test_rates -v         # jeden modul

python3 -m sysmon_app                           # až vznikne v Tasku 11
```

Závislost je **jen `psutil`** (`pacman -S python-psutil`). Žádný build step,
žádný `pyproject.toml`, žádné závislosti navíc. Testy jsou stdlib `unittest` —
pytest je vynechaný záměrně, aby projekt zůstal bez závislostí.

## Architektura

Balíček `sysmon_app/`:

| Soubor | Role |
|---|---|
| `config.py` | konstanty, `Settings`, načtení `config.toml` |
| `collectors/` | jeden modul na **oblast**, ne na metriku |
| `feed.py` | `SnapshotFeed` — jeden sběrný cyklus pro N odběratelů *(Task 8)* |
| `monitor.py` | `Monitor.snapshot()` — kontrakt *(Task 7)* |
| `server.py` | HTTP: SPA, `/stats`, `/events` (SSE) *(Task 9, 10)* |
| `__main__.py` | vstupní bod *(Task 11)* |
| `web/` | dočasný frontend, kopie ze `sysmonu`; fáze 2 ho nahradí |

### Jeden sběrný cyklus, ne jeden na klienta

`sysmon` čte kolektory v každém HTTP požadavku z vlastního vlákna, což je race,
kterou jeho `CLAUDE.md` vede jako „přijaté, ne opravované". Tady to zmizí:
`SnapshotFeed` tiká jednou za `TICK_SEC` a odběratelé (okno, telefon) se vezou.
Kolektory s rate stavem (`net`, `disk`) se tak nemůžou rozbít souběžným čtením.

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

## Přenos ze sysmonu

Kolektory se **kopírují, nepřepisují** — jsou odladěné proti skutečnému
hardwaru (klíče teplotních čidel se liší stroj od stroje, AMD a NVIDIA mají
různé cesty, `/proc/net/tcp` má LISTEN ve sloupci 4 jako `0A`). Kopie musí být
**byte-identická**; ověřuje se `diff` a `sha256sum` proti `../sysmon`.

Jediné povolené úpravy jsou odstranění akcí (`terminate()`, `restart()`,
`validate_container_name`) a přepsání importů na `sysmon_app.*`.

### Na co si dát pozor — zděděné pasti

Tyhle věci v kódu nevypadají špatně, ale při zapojení do dashboardu kousnou.
Nejsou to chyby k opravě, jsou to vlastnosti k zapamatování:

- **`system` a `processes` nedodržují konvenci `available: False`.** Vrací
  `None`, částečný dict, nebo rovnou seznam. Indexovat na nich `['available']`
  nejde a render musí počítat s `null` i s chybějícím klíčem.
- **`net` nemá degradační cestu vůbec.** `psutil.net_io_counters()` volá bez
  `try` — kdežto `disk.py` chrání to samé volání. Až `feed._loop` spolkne
  výjimku, `_seq` přestane růst a všichni klienti vidí **zamrzlá čísla tiše**.
  Task 7 to musí vyřešit (dvě možné cesty má zapsané v plánu).
- **`psutil.boot_time()` v `get_system_info()` není obalené `try`**, takže
  výpadek uptime proteče až do `snapshot()`.
- **`disk.py` po výpadku `disk_io_counters` neposune baseline** (`_prev_t` a
  čítače se aktualizují jen v úspěšné větvi). Další úspěšné čtení tedy průměruje
  přes celou mezeru místo aby hlásilo špičku. Vypadá to zamýšleně.
- **`cpu_percent(interval=None)` a rate kolektory potřebují protočení.**
  `Monitor.prime()` musí zavolat `psutil.cpu_percent`, `net.read()`,
  `disk.read()` **a `get_top_processes()`** — jinak je první `/stats` samá nula
  a seznam procesů nesetříděný. Prime se musí volat na **těch samých instancích**,
  které pak čte `snapshot()`; stav je v instanci, ne v modulu.

### Jediné místo, kde se tvar kopie mění: `ports.py`

Seznam sledovaných portů je stroj-specifický, takže patří do konfigurace a obě
funkce ho berou **argumentem** — `listening_ports(ignored_ports)` a
`get_services(watch_ports, ignored_ports)`. Modul proto nemá **ani jeden import**,
což je mechanický důkaz, že v něm nic stroj-specifického nezůstalo.

`TCP_FILES` zůstává modulová proměnná čtená **až při volání**, ne default
argument — testy ji monkeypatchují, aby šlo parsování zkoušet bez `/proc`.
„Vylepšit" ji na parametr znamená rozbít testy.

`KNOWN_PORTS` ze `sysmonu` se **nepřenáší a nemá se vracet.** Byl to
`{**WATCH_PORTS, 80: "HTTP", 443: "HTTPS", 5432: "Postgres"}` používaný jako
`KNOWN_PORTS.get(port) or label`; protože je nadmnožinou `WATCH_PORTS`, pro
sledovaný port vracel vždy přesně ten label, který už byl po ruce — mrtvý kód.

Tady by ale nebyl jen zbytečný, byl by to **bug**: `watch_ports` je teď od
uživatele, takže kdo si napíše `80 = "MujWeb"`, dostal by s ním tiše `"HTTP"`.
Ověřeno i měřením — seznamy výstupů starého a nového modulu jsou na stejném
vstupu shodné.

## Konfigurace

`$XDG_CONFIG_HOME/sysmon-app/config.toml` (fallback `~/.config`), stdlib
`tomllib`. Relativní `XDG_CONFIG_HOME` se ignoruje podle XDG basedir spec.

Povolené klíče jsou **jen** `host`, `port`, `watch_ports`, `ignored_ports`.
Neznámý klíč je **tvrdá chyba** s cestou k souboru — tichý překlep by uživateli
vzal nastavení, aniž by se dozvěděl proč. Intervaly konfigurovatelné nejsou
(záměrně, nikdo je nepotřeboval měnit).

Rozbitá konfigurace se **nepolyká**: `load_settings` vyhazuje `ValueError`
s cestou v hlášce, a to i pro špatný *typ* hodnoty (`ignored_ports = "53"` by se
jinak tiše rozpadlo na `{3, 5}`, `port = inf` by uniklo jako `OverflowError`,
`host = true` by se stal řetězcem `"True"` a spadl až v socketu jako
`gaierror` — což **je** `OSError`, takže by to Task 11 nahlásil jako „port
obsazený"). `__main__` proto chytá `ValueError` a tiskne větu, ne traceback.

## Bezpečnost a soukromí

**Žádná autentizace, žádné akce, žádné POST routy.** Token, validátory a routy
`/action/*` existují v `sysmonu` jen kvůli akcím; tady není co chránit.

Server ale defaultně poslouchá na `0.0.0.0`, aby dashboard fungoval z telefonu —
**kdokoli v té síti vidí seznam procesů a portů**. Na domácí LAN je to vědomá
volba; v cizí síti patří do konfigurace `host = "127.0.0.1"`.

Port je **8430**, ne 8420 — `sysmon` má 8420 a oba poběží na jednom stroji.
Port je stabilní, ne náhodný: telefon má uloženou URL.

## Testy

Stdlib `unittest`, spouští se `python3 -m unittest discover -s tests -t .`.
Pokrývají hlavně to, co se dá ověřit bez hardwaru: parsování `/proc/net/tcp`
(přes monkeypatch `TCP_FILES`), rate matematiku (mockované `psutil` a hodiny),
seskupování kontejnerů podle Compose projektu (včetně čárky uvnitř hodnoty
labelu), validaci konfigurace a kontrakt snapshotu.

Co se **nepřenáší** ze `sysmonu`: testy tokenu a akcí. Patří k funkcím, které
tenhle produkt nemá.

Frontend se netestuje (YAGNI) — fáze 2 k tomu přidá aspoň typy.
