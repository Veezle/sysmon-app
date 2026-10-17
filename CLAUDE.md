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

**Fáze 1 (démon) hotová** — všech 12 tasků, sada tehdy 141 testů, `README.md` je
v repu. Návrh je v `docs/superpowers/specs/2026-10-15-sysmon-app-design.md`, plán
po úlohách v `docs/superpowers/plans/2026-10-15-faze-1-demon.md`, naměřená čísla
k ověření fáze 1 v uzavření Tasku 12. Task 1 (skelet + `config.py`), Task 2
(`system`, `processes`), Task 3 (`net`, `disk`), Task 4 (`ports`), Task 5 (`gpu`,
`battery`), Task 6 (`docker`), Task 7 (`monitor` + kontrakt snapshotu), Task 7b
(doplnění pokrytí kolektorů), Task 8 (`feed` — jeden sběrný cyklus pro N
odběratelů), Task 9 (`server` — SPA a `/stats`), Task 10 (SSE proud na
`/events`), Task 11 (`__main__` — spustitelný démon), Task 12 (`README`
a end-to-end ověření).

**Fáze 2 (React frontend) běží.** Návrh v
`docs/superpowers/specs/2026-10-16-faze-2-frontend-design.md`, plán po úlohách
v `docs/superpowers/plans/2026-10-16-faze-2-frontend.md`, průběh v `.tasks.json`
vedle plánu, pravidla pro tasky v plánu („Pravidla pro každý task"). Pracuje se
na větvi **`faze-2-frontend`**; `faze-1-demon` zůstává jako záchranná síť.
Hotový **Task 1** — sada se odpoutala od buildu: testy indexu a assetů čtou
fixture adresář, sada má **143 testů** a projde i bez `sysmon_app/web/` (tehdy
se build-závislé piny přeskočí). Hotový **Task 2** — `frontend/` (Vite 8.3.4 +
React 19.3.1 + TS 5.9.3) se buildí do `sysmon_app/web/`, který je v
`.gitignore`; stará kopie frontendu je z repa smazaná (`../sysmon` zůstává
referencí). Build servíruje démon beze změny rout (`/`, `/static/*`), dev
server proxyuje `/stats` a `/events` na 8430. **Další na řadě je Task 3:**
cache hlavičky (immutable pro hashované assety, no-store pro index) a hlášení
chybějícího buildu. Python závislost je pořád jen `psutil`; JS závislosti žijí
jen ve `frontend/package.json` a lockfile se commituje.

Task 7b, Task 8, Task 9, Task 10, Task 11 i Task 12 měly v plánu **hotovou
předlohu**,
a všechny se ukázaly být **výchozím bodem, ne spec**: u 7b v ní recenzenti
naměřili tři vadné piny, u Tasku 8 předloha nepinovala vlastní acceptance
kritéria (dvanáct mutovaných vlastností přežilo) a její časové piny tiše držely,
jen dokud bylo `TICK_SEC` vyrazně nad prahem, u Tasku 9 nechalo devět plánových
testů projít sedm mutantů (dva z nich přitom porušovaly acceptance kritéria)
a trasu `/static/` netestovalo po drátě vůbec, u Tasku 10 nechala předloha ve
smyčce chybějící výstup po `stop()` (past, kterou přitom sama popsala jako
závaznou) a její tři testy nepokrývaly dvě ze čtyř kritérií, u Tasku 11 pinoval
předepsaný `Verify` jen předpoklad jednoho kritéria ze čtyř (a `--port` mimo
rozsah končil tracebackem), a u Tasku 12 byla **rozbitá ukázka `config.toml`**,
kterou měl README učit (a ověření fáze 1 zůstalo jen v hlášení, ne v repu).
Opsaný kód se recenzuje jako nový.

Fáze 3–4 (Tauri obal, balení a měření paměti) jsou zatím jen v návrhu.

## Jak se tady pracuje

Práce jde **po taskách z plánu** a **po každém tasku se zastavuje** — shrnutí a
čekání na pokyn. Pokračuje se jen na vyžádání („pokračuj na task N"), i když je
další krok zřejmý.

Postup u jednoho tasku:

1. Vzít zadání tasku z plánu a poslat **čerstvého subagenta** jako implementátora.
   Dostat má **plné znění svého tasku**, ne celý plán — a nesmí si ho číst sám.
2. **Ověřit výsledek sám proti repu** — `git log`, `diff` proti `../sysmon`,
   spuštěné testy. Nikdy ne podle toho, co subagent napíše do hlášení.
3. **Recenze zadání** (jiný subagent): odpovídá kód přesně zadání? Nic navíc,
   nic míň? Recenzent má dostat výslovný pokyn nevěřit hlášení implementátora.
4. **Recenze kvality** (další subagent) — až po té první.
5. Nálezy buď zadat k opravě, nebo **odůvodnit, proč se zamítají**. Nikdy tiše.
   Opravy dělá tentýž implementátor, a po opravách se recenze opakuje.
6. Označit task v `.tasks.json` jako `completed`, aktualizovat „Stav" tady.
7. Shrnutí a pauza.

**Zásady pro zadání každého subagenta:**

- Nikdy necommituj na `main`; pracuje se na větvi `faze-2-frontend` (fáze 1
  měla `faze-1-demon`, ta zůstává jako záchranná síť).
- **Nikdy nesahat do `../sysmon`** — čte se z něj, nepíše.
- `git add` **jen s explicitními cestami**, nikdy `-A` ani `.`. V stromu bývají
  necommitnuté dokumenty, které do cizího commitu nepatří.
- Implementátor needituje nic pod `docs/` ani soubory z jiných tasků.
- Žádné nové **Python** závislosti a žádný `pyproject.toml`. Build step existuje
  od fáze 2 jen ve `frontend/` (Vite) — nové závislosti smějí být pouze tam,
  a žádná z nich nesmí být runtime závislost stažená z CDN: build musí zůstat
  soběstačný.

**Co se osvědčilo:**

- U **přenosových** tasků (2, 3, 5, 6) stačí jedno kolo recenzí. Tam, kde se mění
  tvar nebo přidává logika (1, 4), se vyplatí počítat s víc.
- Model: mechanická kopie zvládne levný model, recenze a integrace potřebují
  silnější.
- Recenzenti mají dostat **konkrétní seznam tvrzení k vyvrácení**, ne „zkontroluj
  to". Nejcennější nálezy vznikly tak, že recenzent něco přeměřil, přepsal nebo
  zfalšoval a tvrzení vyvrátil — ne že si kód přečetl.
- **Vzorec, na který se vyplatí čekat:** „tohle bylo v pořádku, dokud byla
  konfigurace naše; teď je uživatelova, a je to bug." Tak se našly `KNOWN_PORTS`
  i překryv `watch_ports` s `ignored_ports`. Přenos ze `sysmonu` nese předpoklady
  platné jen pro jeden stroj.
- **Falešný vstup musí umět selhat stejně jako skutečný.** Fixtura baterie
  psala hodnoty bez koncového `\n` a modelovala jediné AC napájení, takže
  obrany v kódu (`strip()`, slévání zdrojů přes `or`) nebyly nikdy zatížené
  a mutanty procházely. Otázka k čekání: „co na tomhle stroji vypadá jinak než
  ve fixtuře?" — v Tasku 5 to bylo `\n` a tři napájecí zdroje místo jednoho.
- **Když obal polyká výjimky, jméno se v něm nesmí vyhodnocovat.** `_safe(lambda:
  get_top_processes(...), …)` v `Monitoru` spolkne i `NameError` z překlepu:
  karta zůstane prázdná navždy a sada je zelená. `functools.partial` vyhodnotí
  jméno v argumentu, tedy mimo obal, a překlep je hlasitý (31 chyb). Totéž
  platí pro tabulku náhradních tvarů klíčovanou jmény — nic ji s klíči neváže,
  takže `loadavg` s `{}` projde testy a rozbije render.
- **`assertIs` nepinuje nezměněnost.** Test na identitu objektu vypadá, že brání
  přepsání sdíleného stavu, ale propustí právě to: `Monitor` může `groups`
  otraviť na místě a `assertIs` projde, protože je to pořád týž objekt — a naopak
  shodí neškodný `deepcopy`. Kde je nebezpečím modifikace, pinuje se **obsah**
  (kopie před voláním + `assertEqual`), ne identita. Naměřeno v Tasku 7b: obě
  asserce zabíjejí jinou mutantu, každá sama je poloviční.
- **Test, jehož smyčku ukončuje mock, se při mutantovi zacyklí místo aby spadl.**
  Když `_loop` končí jen výjimkou z podstrčeného `time.sleep`, mutant bez spánku
  sadu roztočí navěky (`timeout` místo `FAILED`) — a visící test vypadá jako
  běžící. Terminátor patří na volání uvnitř těla a musí to být `BaseException`
  (`SystemExit`), protože `except Exception` ho nespolkne; spánek se pinuje
  zvlášť. Záložní brzda z mockovaného spánku funguje jen proto, že `sleep` leží
  vně `try` — přesun dovnitř z ní udělá věčné točení.
- **Test, který pinuje obsah, nepinuje vlastnost.** `assertEqual(snapshot["n"], 2)`
  projde i proti mutantovi, který odběratele neprobudí (`wait_for` se dobere po
  timeoutu a vrátí správná data), i proti mutantovi se dvěma sběry za tik. Široký
  timeout to schová: `interval=0.01` proti `timeout=5` je 500× rezerva, takže
  časový pin nic neměří. Kde kritérium říká „hned" nebo „jakmile", patří do testu
  `assertLess` s prahem blízkým pinované veličině — a **vazba na tu veličinu se má
  tvrdit**: v Tasku 8 piny držely, jen dokud bylo `TICK_SEC` vyrazně nad prahem,
  a při jeho zkrácení se tiše vypnuly (odhaleno až měřením s jinou hodnotou).
- **Předloha v plánu je výchozí bod, ne spec.** Tasky 7b, 8 i 9 měly v plánu
  hotový kód, a všechny tři předlohy nepinovaly, co slibovaly — u Tasku 8 přežilo
  dvanáct mutovaných vlastností, u Tasku 9 sedm (dvě z nich přitom porušovaly
  acceptance kritéria). Recenzent se proto nemá ptát „odpovídá to zadání?", ale
  **„které kritérium to vlastně pinuje?"** — a měřit to mutantami, ne čtením.
- **Recenzní smyčka se musí zastavit.** Task 8 měl tři kola recenzí a čtyři
  opravné commity; poslední kola už přinášela jednořádkovky. Stop pravidlo, které
  se osvědčilo: poslední kolo ověřuje **jen deltu**, opravují se **jen blokující**
  nálezy a všechno ostatní se zapíše do plánu jako vědomá mez. Bez toho se smyčka
  nezastaví, protože každé kolo něco najde.
- **Test, který neteče po drátě, nepinuje trasu.** V Tasku 9 volaly všechny testy
  `/static/` jen `load_static()` napřímo, takže sada zůstala zelená i s přejmenovaným
  prefixem, s rozbitým odřezem cesty a s trasou, která asset **nikdy nepošle** —
  a stránka se přitom načetla bez CSS i bez JS, prázdná. Jednotková pojistka
  (`realpath`, allow-list) byla naměřeně nosná; chyběl pin na to, co produkt
  skutečně dělá. Otázka: **stahuje to test po drátě, nebo jen volá funkci, kterou
  trasa používá?** Totéž platí pro vstupy, které prohlížeč normalizuje: názvy HTML
  značek jsou case-insensitive, takže `assertNotIn("<script>", index)` a
  `re.findall` bez `re.I` nechaly projít `<SCRIPT>alert(1)</SCRIPT>` — pin vypadal,
  že brání vkládání kódu, a přitom ho pustil.
- **Stav na třídě handleru je stav celého procesu, ne serveru.** Předloha Tasku 9
  věšela `monitor`/`feed` na třídu `Handler`, a to ještě **před** bindem. Naměřeno:
  druhé `serve()` na obsazeném portu (scénář Tasku 11) přepsalo stav serveru, který
  už běžel, a ten pak odpovídal cizími daty. Vypadá to jako neměnná konfigurace
  procesu; je to ale stav, který patří instanci — a test, který oba servery staví,
  to odhalí jen tehdy, když je v obou něco k vidění (prázdný feed spadne do
  fallbacku a rozdíl se schová).
- **Obal, který má výjimku spolknout, musí začít před hlavičkami.** V Tasku 10
  začínalo `try:` až za `end_headers()`, takže `ConnectionResetError` z hlaviček
  vyletělo do `socketserver.handle_error` a nechalo na stderr traceback —
  naměřeno **394 z 400** spojení, když klient poslal `GET` a hned RST, a to
  i přesto, že komentář o tři řádky níž sliboval opak. Test, který si odpověď
  **nejdřív přečte**, to okno nikdy netrefí (0 z 400) — proto to předchozí testy
  neviděly. Okno se pinuje tak, že klient pošle požadavek a **hned** zavře
  (RST přes `SO_LINGER 0`), bez čtení, a `handle_error` se podstrčí.
- **Pinuj vazbu, ne naměřenou latenci.** Keep-alive v Tasku 10 se pinoval
  wall-clock oknem kolem `SSE_KEEPALIVE_SEC`. Jenže horní mez je měření na
  **klientovi** a pod vyhladověním CPU roste bez hranice — naměřeno **1,37×–2,49×**
  podstrčené hodnoty (`nice -n 19` proti procesům na `nice 0`), takže test padal
  falešně (12 běhů: 4 selhání s oknem `(0.8k, 1.25k)`, 1 s `(0.5k, 1.6k)`).
  Rozšířit ho přitom nejde: aby zůstal zabitý mutant s napevno zadrátovaným
  timeoutem, musí horní mez zůstat pod ním. Řešení: podstrčit volanou funkci
  obalem, který si poznamená **argument**, a tvrdit rovnost s konstantou. Je to
  přísnější (zabilo i `k*1.5`, které okno pouštělo) a nezávislé na plánování
  (10/10 pod zátěží, kde okno padalo). Obecně: **kde jde pinovat argument místo
  následku, pinuj argument** — čas je šum, hodnota ne.
- **Chunk framing není event framing.** Testy Tasku 10 pinovaly chunk (hex
  velikost + CRLF), ale ne obálku události `data: …\n\n` — mutant, který pošle
  jen jedno `\n`, prošel **všemi 120 testy**, a přitom by `EventSource`
  nevyvolal ani jednu událost. Když test skládá rámec z prefixu a parsovaného
  obsahu, kontroluj i **oddělovač**: přesně tam se ta chyba schová.
- **Měření na izolované funkci není měření produktu.** Předletová kontrola pro
  Task 11 tvrdila (a já ji tak zapsal do plánu), že `feed.stop()` ukončí otevřené
  SSE proudy čistě — „naměřeno curlem, `exit 0`". Měření ale běželo na handleru
  v **izolaci, s procesem, který žil dál**; na skutečné výstupní cestě démona se
  proud usekne (`curl` rc 18, ukoncovací chunk nedorazí, 5/5 běhů), protože
  `sys.exit` zabije daemon vlákna handlerů. Než něco prohlásím za změřené, ptám
  se: **běželo to na té cestě, kterou používá produkt, nebo jen na té funkci?**
  Do plánu patří jen to druhé jako „změřeno v izolaci".
- **`server_close()` na daemon vlákna nečeká — a „zjevná oprava" je past.**
  `ThreadingMixIn._Threads.append` daemon vlákna **zahazuje**, takže `_threads`
  zůstane prázdné a `server_close()` se vrátí za 0,000 s i s handlerem
  zaseknutým v zápisu (naměřeno). Přepnout `daemon_threads` na `False` join
  zapne — a `Ctrl+C` pak neukončí proces, protože handler zaseknutý u odběratele,
  který nečte, visí neomezeně (>60 s, naměřeno). Když ukončení démona potřebuje
  milost, musí být **ohraničená deadline**, ne `join` bez ní.
- **Dvě pasti v měřicím harnessu, které vypadají jako nález.** (a) Kopíruješ-li
  repo do `/tmp` a mutuješ **řádky** (ne tvar), smaž `__pycache__` a použij
  `PYTHONDONTWRITEBYTECODE=1` — mutant se stejnou velikostí souboru si vezme
  zastaralý `.pyc` a „přežije", i když je zabitý (naměřeno u mutantu, který jen
  prohazoval pořadí). (b) Substring aserce propustí víc, než si myslíš:
  `assertIn("konec", stdout)` přežije i `konecX`; kde jde o text hlášky, pinuj
  přesnou hodnotu.
- **Ukázka z dokumentace se ověřuje extrakcí ze souboru, ne přepisem.** Naivní
  „ber odsazené řádky, dokud to jde" se v Tasku 12 zastavilo na **prázdném řádku
  uvnitř bloku** a vrátilo podvýřez `config.toml` bez `[watch_ports]` — tedy bez
  přesně toho místa, kde chyba byla, a takový výřez projde. Kdo opisuje správnou
  verzi ručně, stejně tak nedokáže nic: dokument a realita se rozejdou znovu.
- **Tvrzení o chování frontendu se ověřuje i v cestě, kterou dokumentace sama
  nabízí.** V Tasku 12 byla výchozí cesta (bez tokenu) pravdivá a ležela ta
  druhá: README citoval hlášku odkazující na `?token=…`, takže čtenář, který ji
  poslechne, pošle POST (`captureToken()` token z URL vezme) a dostane syrovou
  `SyntaxError` místo slibovaného „nic se nestane". Věty typu „to se nikdy
  neodešle" potřebují pin i na okrajový vstup, který sám dokument zmiňuje.
- **Když task slibuje „ověřit", musí ověření skončit v repu.** Task 12 měl za cíl
  ověřit, že démon dává stejná data jako `sysmon`; kdyby ta čísla zůstala jen
  v hlášení subagenta, nedá se z repa zjistit, co a kdy se měřilo. Naměřené
  hodnoty patří do uzavření tasku v plánu.
- **`kill -INT` na proces z neinteraktivního shellu je tichý no-op.** Bash dá
  background úloze (bez job control) `SIGINT` i `SIGQUIT` na **ignorováno**
  a Python zděděné `SIG_IGN` neruší — vlastní handler pro `SIGINT` si
  nenainstaluje. Naměřeno při ověřování mergi Tasku 12: `python3 -m sysmon_app`
  spuštěný jako `(setsid nohup … &)` měl v `/proc/PID/status` `SigIgn` s bitem
  pro SIGINT, takže „Ctrl+C démona neukončí" vypadalo jako nález, ačkoli šlo
  o měření. Kdo ukončení měří signálem, ať si **nejdřív přečte
  `/proc/PID/status`**, nebo proces spustí pod pty (`script -qec "…" /dev/null`);
  pod pty naměřeno: `SIGINT` → `konec`, `COMMAND_EXIT_CODE=0`, port uvolněný.
- **Pin, který měří vlastní konstantu, neměří produkt.** V Tasku 1 fáze 2
  kontroloval pin na `index.html` čtyři vlastnosti **fixture, kterou si test sám
  napsal** — a nic víc; mutant, kdy trasa `/` vůbec nezavolá `load_index()`
  a pošle konstantní HTML, přežil **všech 141 testů**. Co chybělo: dvojče pinu
  nad **skutečným buildem** (`skipUnless` na existenci `web/index.html`)
  a **negativní kontrola**, že pin umí spadnout (`test_pin_fires_on_inline_script`)
  — bez ní je pin, který nikdy nezapálí, nerozeznatelný od žádného pinu.
  Otázka pro každý nový pin: **kterou mutantu by zabil?** Když žádnou, měří sebe.
- **Když aserci vyřídí allow-list, cesta zůstane nepinovaná.** `assertIsNone(
  load_static("../config.py"))` projde i s implementací, která kontrolu cesty
  **vůbec nemá** — `.py` není v allow-listu přípon, takže `None` přijde dřív, než
  se na cestu někdo podívá (naměřeno mutantem). Pin na cestu musí mířit na
  soubor, který **existuje a má povolenou příponu**; jinak se dvakrát testuje
  allow-list a cesta nikdy. Platí to i na testy, které vypadají, že „něco
  kontrolují", protože vracejí `None`.
- **Skener pinuje jen to, co skener opravdu vidí.** `re.findall(r"\son[a-z]+\s*=")`
  nad celým dokumentem zapálí na běžné próze (` text only = 5 ` vypadá jako
  `on…=` atribut). Atributy se hledají **uvnitř značek** (`<[a-z][^>]*>`), ne
  v textu — jinak si pin vynutí přepisování nevinných slov místo kódu.
- **Kontrola, která si URL skládá z grepu, musí ověřit, že URL vznikla.** Kostra
  v Tasku 2 neměla žádný import CSS, takže Vite `.css` asset nevyrobil; smyčka
  `url=$(… grep …); curl "localhost:8430$url"` s prázdnou URL poslala požadavek
  na `/`, dostala `200 text/html` a vypsala „css -> 200“ — chybějící stylesheet
  vypadal jako úspěch, přičemž kritérium „oba assety → 200“ platilo. Prázdný
  výsledek grepu musí být tvrdá chyba a asset musí existovat ve výstupu buildu.
- **`emptyOutDir` smaže i trackované soubory v cíli buildu.** Task 2 buildil do
  `sysmon_app/web/`, kde ležela stará kopie frontendu; build ji smazal z disku
  dřív, než přišlo `git rm`. Mazání z indexu proto musí být naistagované
  **před** buildem, jinak „`git status` je po buildu čistý“ neplatí.

**Ověřovací příkazy** jsou u každého tasku v plánu. Celá sada je
`python3 -m unittest discover -s tests -t .`.

## Commands

```bash
python3 -m unittest discover -s tests -t . -v   # celá sada
python3 -m unittest tests.test_rates -v         # jeden modul

python3 -m sysmon_app                           # démon na 8430 (--host/--port přebijí config)
```

Python závislost je **jen `psutil`** (`pacman -S python-psutil`). Žádný
`pyproject.toml`, žádné Python závislosti navíc. Build step existuje jen ve
`frontend/` (Vite); `sysmon_app/web/` se necommituje. Testy jsou stdlib
`unittest` — pytest je vynechaný záměrně, aby Python strana zůstala bez
závislostí.

```bash
cd frontend && npm ci && npm run build   # build do sysmon_app/web/
cd frontend && npm run dev               # dev server s proxy na 8430
```

## Architektura

Balíček `sysmon_app/`:

| Soubor | Role |
|---|---|
| `config.py` | konstanty, `Settings`, načtení `config.toml` |
| `collectors/` | jeden modul na **oblast**, ne na metriku |
| `feed.py` | `SnapshotFeed` — jeden sběrný cyklus pro N odběratelů *(Task 8)* |
| `monitor.py` | `Monitor.snapshot()` — kontrakt *(Task 7)* |
| `server.py` | HTTP: SPA, `/stats`, `/events` (SSE) |
| `__main__.py` | vstupní bod — `python3 -m sysmon_app` |
| `web/` | build z `frontend/` (ignorovaný gitem); servíruje ho `server.py` |

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
