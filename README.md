# sysmon-app

Dashboard systémových metrik pro Linux — jako okno i jako stránka na telefonu.
Druhý, samostatný produkt vedle `sysmon`; ten se nemění.

**Stav: fáze 1 (démon).** Okno, instalátory a nový frontend přijdou v dalších
fázích. Návrh je v `docs/superpowers/specs/2026-10-15-sysmon-app-design.md`.

## Spuštění démona

    python3 -m sysmon_app

Poslouchá na `0.0.0.0:8430` a v prohlížeči je na <http://localhost:8430>.
Potřebuje **Python 3.11 a novější** (konfiguraci čte stdlib `tomllib`).
Závislost je jen `psutil` (`pacman -S python-psutil`).

Port je **8430**, ne 8420 — `sysmon` má 8420 a oba mají běžet vedle sebe.
Ukončuje se `Ctrl+C`.

`--host` a `--port` přebijí konfiguraci. Když je port obsazený, démon to napíše
česky a skončí — ne tracebackem.

## Co démon vydává

| Cesta | Co vrací |
|---|---|
| `GET /` | stránka dashboardu |
| `GET /static/<soubor>` | `style.css`, `app.js`, `icon.svg` |
| `GET /stats` | JSON snapshot |
| `GET /events` | SSE proud snapshotů, jeden nový zhruba každých 1,5 s |

`/stats` i `/events` vydávají **tentýž kontrakt snapshotu** — vždy 16 klíčů
(`host`, `cpu`, `mem`, `swap`, `disk`, `net`, `processes`, `services`,
`containers`, …) a k tomu `cpu_temp`, ale jen když ho stroj umí přečíst.
Dnešní frontend odebírá `/stats` každých 1,5 s; proud `/events` je hotový
a připravený pro fázi 2.

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

    python3 -m unittest discover -s tests -t . -v

Sada má **141 testů** a nepotřebuje volný port 8430 — projde i s běžícím
démonem na 8430 i na 8420.

## Dočasný frontend

`sysmon_app/web/` je **kopie dnešního frontendu ze `sysmonu`** a slouží jen
k ověření démona — kontrakt snapshotu se nemění, takže stará UI musí fungovat
proti novému démonu. Fáze 2 ji nahradí Reactem.

Pozor: tlačítka na ukončení procesu a restart kontejneru v téhle kopii jsou
**mrtvá**. `sysmon-app` nemá routy `/action/*` a nemá ani token, ze kterého
`app.js` skládá hlavičku. Bez tokenu se požadavek vůbec neodešle a kliknutí
skončí jen hláškou:

> Chybí token — otevři dashboard s ?token=… (token je v ~/.config/sysmon/token).

To je odkaz na soubor i na funkci, které tu záměrně nejsou — a kdo ho poslechne
a otevře stránku s `?token=…` (třeba tím ze `sysmonu`), tomu si `app.js` token
uloží a `POST /action/kill` **odešle**: server odpoví `501 Unsupported method`
(nemá `do_POST`) a tělo odpovědi není JSON, takže `await r.json()` spadne
a uživatel uvidí „Chyba: …". Ať se klikne jakkoli, nic se neprovede — je to
očekávané, ne chyba; fáze 2 ta tlačítka odstraní.
