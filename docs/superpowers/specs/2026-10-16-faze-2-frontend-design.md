# Fáze 2: Frontend (React + TS + Vite) — návrh

Navazuje na `2026-10-15-sysmon-app-design.md` (kapitola „Frontend"), který
stanoví React + TypeScript + Vite, port vzhledu bez předělávání, žádný Tailwind
a žádný Recharts. Tenhle dokument rozhoduje, **jak** se to udělá, a co je na
konci fáze 2 ověřitelné.

## Cíl a rozsah

Přenést dnešní frontend (kopie ze `sysmonu`, byte-identická s
`../sysmon/templates/index.html` + `../sysmon/static/`) do Reactu tak, aby:

- vzhled zůstal **1:1** — 9 karet (CPU s mřížkou jader, GPU, RAM+swap, baterie
  s canvas grafem, síť, disk, služby, procesy, Docker), 585 řádků CSS se
  přenáší, ne přepisuje;
- data tekla **přes SSE** (`/events`), ne pollingem jako dnes;
- mrtvá tlačítka a token zmizely z UI **i z kódu**;
- typy popisovaly kontrakt snapshotu a **něco je pinovalo** proti Pythonu;
- build byl **soběstačný** — dnešní CSS nemá ani `@import`, ani `@font-face`
  (ověřeno), takže ani build nesmí tahat nic z internetu.

## Rozhodnutí

1. **Idiomatický React s `React.memo` na kartách** (varianta A). Stav v `App`,
   každá karta dostane svůj řez a je obalená `memo`, seznamy mají **stabilní
   `key`**, graf baterie zůstává imperativní canvas v `useEffect`. Zamítnutý
   port 1:1 (React jen jako obal) i externí store s granulárními subskripcemi
   (víc konceptů, než 9 karet za 1,5 s potřebuje).
2. **Build se necommituje.** Zdroják v `frontend/`, výstup do `sysmon_app/web/`,
   ten je v `.gitignore`. Repo zůstane zdrojové a diffy čisté; cena je, že
   `python3 -m sysmon_app` bez buildu nefunguje — a proto to musí **říct
   česky**, ne prázdnou stránkou.
3. **Vite dostane dev server s proxy** na `/stats` a `/events` na běžícího
   démona (8430). Produkt se staví pořád jen `npm run build`.
4. **Typy kontraktu se pinují proti Pythonu** — fixture generovaná Pythonem
   a TS soubor s `satisfies`, aby rozejití typů s kontraktem shodil typecheck.
5. **Stabilita DOM se měří** — počet uzlů v seznamech nesmí růst s počtem tiků.
   Dnešní frontend měl naměřeno ~90 přebudovaných prvků každý tik.

## Struktura repa

```
frontend/
  package.json          # vite, react, typescript; žádné runtime CDN
  tsconfig.json
  vite.config.ts        # outDir ../sysmon_app/web, assetsDir static/assets, proxy
  index.html            # vstupní HTML pro Vite (dnešní index.html se neopisuje)
  public/static/icon.svg
  src/
    main.tsx
    App.tsx
    types/snapshot.ts            # kontrakt snapshotu
    types/snapshot.contract.ts   # `satisfies Snapshot` proti fixtures/snapshot.json
    data/useSnapshot.ts          # /stats + EventSource
    lib/format.ts                # fmt, formatUptime, formatPorts
    components/…                 # jedna karta = jeden soubor
    styles/style.css             # dnešní CSS, bez stylů mrtvých tlačítek
sysmon_app/web/         # build, v .gitignore
tests/fixtures/snapshot.json     # generuje Python test (viz Testy)
```

Dnešní `sysmon_app/web/` (kopie ze `sysmonu`) se **smaže** z repa. Reference
zůstává v `../sysmon`, a to je dost: `diff` proti ní se v taskách dá použít jako
předloha portu.

## Architektura frontendu

**Tok dat** (`useSnapshot`):

1. první vykreslení z `GET /stats` — karty mají data dřív, než se SSE stihne
   připojit (a když `/stats` selže, karta to řekne, nezůstane viset);
2. pak `EventSource('/events')`, každý rámec `data:` = celý snapshot;
3. když rámec nedorazí do ~3 tiků, přepne se na polling `/stats` a stavová
   tečka v hlavičce to ukáže; jakmile SSE zase mluví, polling se vypne.
   (`EventSource` si reconnect řeší sám — fallback je pojistka na to, že proud
   tiše zamrzne, což je přesně ta vada, kterou má `net` kolektor zděděnou.)
   Frontend k tomu potřebuje dvě konstanty — periodu pollingu (1,5 s) a práh
   ticha (~4,5 s); `TICK_SEC` je dnes jen v Pythonu, takže se hodnota ve
   frontendu **duplikuje jako pojmenovaná konstanta** v `useSnapshot.ts`.
   Je to vědomá mez: kdyby se tik v Pythonu změnil, tohle je druhé místo.

**Komponenty:** `Header` (hostname, uptime, stavová tečka), `CpuCard` (+ mřížka
jader), `GpuCard`, `MemCard` (RAM + swap), `BatteryCard` (+ `BatteryChart` na
canvasu), `NetworkCard`, `DiskCard`, `ServicesCard`, `ProcessesCard`,
`DockerCard`. Každá karta si bere z snapshotu jen svůj řez, takže se tik
nedotkne karty, jejíž data se nezměnila.

**Co se z dnešního kódu zachovává jako pravidlo, ne jako náhoda:**

- karty se **nepřebudovávají**; mění se jen text, šířka pruhu a barva;
- na prvcích, které se mění každý tik, se **neanimuje** `width`, `height` ani
  `box-shadow`;
- degradované tvary: `available: false` + `error`, ale i `null` a částečné
  dicty (`system` a `processes` konvenci **nedodržují** — ověřeno v Tasku 7);
- `window.gc` hack z `app.js` (patřil k měření paměti ve starém webview) mizí.

**Prázdné `watch_ports`** se musí vykreslit jako **„nesleduji žádné porty"**, ne
jako „0 / 0" se smazaným placeholdrem „Načítání…" — to druhé čte jako výpadek
všech služeb. Port znamená „nesleduji ho", ne „neběží".

**Typy:** `snapshot.ts` popisuje všech 16 vždy přítomných klíčů a `cpu_temp`
jako volitelný; typy hodnot musí unést `null` tam, kde ho kolektory legitimně
vrací (`loadavg`, `cpu_temp`).

## Server (Python) — co se mění

Routy zůstávají `GET /` a `GET /static/*` (kontrakt ze spec se nemění), ale:

- Vite se konfiguruje tak, aby assety padaly pod **`/static/assets/…`**
  (`assetsDir: "static/assets"`), takže `/static/` musí umět **podadresář** —
  dnes to `realpath` kontrola dovolí, ověřit a pinovat;
- allow-list přípon (`STATIC_TYPES`) musí krýt to, co build skutečně vydá;
- **cache hlavičky:** hashované assety `Cache-Control: public, max-age=31536000,
  immutable`, ale `index.html` (a `icon.svg`) **`no-store`** — jinak by telefon
  po rebuildu držel starý `index.html` odkazující na soubory, které už neexistují;
- **chybějící build:** `__main__` to odmítne českou větou s cestou a s přesným
  příkazem (`npm ci && npm run build` v `frontend/`), rc=2, bez tracebacku;
  a když build zmizí za běhu, `GET /` odpoví **503** s českou větou v
  `text/plain`, ne tracebackem.

**README se musí aktualizovat** — dnes říká, že `sysmon_app/web/` je kopie ze
`sysmonu`, a popisuje spouštění bez buildu. Po fázi 2 musí uvádět `npm ci &&
npm run build` jako krok před spuštěním, jinak první věta, kterou uživatel
udělá, skončí na chybějícím buildu.

## Testy

**Python sada se musí odpoutat od buildu** — dnes čte skutečné soubory
z `web/` (`load_index()`, `icon.svg`) a pinuje, že `index.html` nemá inline
`<style>`/`<script>`. Po zgitignoreování buildu by v čerstvém klonu spadla.
Proto:

- testy indexu a assetů čtou **fixture adresář** (vzor `mock.patch.object(server,
  "STATIC_DIR", …)` už v `test_server.py` je), ne build;
- pin na index se **přeformuluje**: zakázaný je *spustitelný inline kód* (tělo
  `<script>`, `on…=` atributy) — `<script type="module" src=…>` je legitimní
  součást Vite buildu. Case-insensitive, jak učil Task 9.
- Testy, které **build potřebují** (asset po drátě, privacy pin, stabilita DOM),
  se bez buildu **přeskočí** (`skipUnless`) — sada musí zůstat zelená i v čerstvém
  klonu. Je to vědomá mez: pin běží jen tam, kde build je, a plán proto u tasků
  s buildem nařizuje buildit před Verify.

**Nové piny:**

- **kontrakt:** Python test vygeneruje `tests/fixtures/snapshot.json` z fake
  monitoru a tvrdí, že soubor na disku je **shodný s čerstvě vygenerovaným**
  (fixture nemůže tiše zestárnout); `snapshot.contract.ts` ho naimportuje
  a `satisfies Snapshot` — takže přidání klíče v Pythonu rozbije typecheck.
  Soubor je **jen pro typecheck a záměrně ho nic neimportuje** z aplikace:
  `tsc` v `noEmit` režimu ho zkontroluje, ale Vite ho nezabundluje (jinak by
  fixture putovala do buildu);
- **asset po drátě:** `/static/assets/<hash>.js` se stáhne přes HTTP (ne jen
  `load_static`), protože „test, který neteče po drátě, nepinuje trasu";
- **soukromí:** `index.html` ani CSS nesmí obsahovat cizí origin (`http://`,
  `https://`, `//`) — build se nesmí rozejít s tím, že produkt nic netahá z netu;
- **chybějící build:** démon to řekne českou větou, ne tracebackem;
- **stabilita DOM:** headless Chrome (`--virtual-time-budget`) vykreslí stránku
  s **konstantním** snapshotem a změří, co se v seznamech (`#cores`,
  `#services-list`, `#proc-list`, `#docker-containers`) děje: **počet childList
  mutací** musí být po ~80 ticích nula a první řádek každého seznamu musí být
  **tyž objekt**. Měří se mutace a identita, ne počet uzlů — dnešní frontend
  přebudovává seznamy přes `replaceChildren`, takže počet uzlů zůstává stejný
  a pin na počty by prošel i proti starému kódu (přišlo se na to až při psaní
  plánu). Měření jde bez CDP: stránka, kterou server servíruje, je náš harness,
  který si `MutationObserver` nasadí sám a výsledek zapíše do DOM. Přeskočí se,
  když není chrome nebo build.

**Frontend:** `npm run build` (obsahuje `tsc`) a `npm run typecheck` pro
kontraktní soubor. Rendering se netestuje (YAGNI, jak říká spec) — kromě toho
jednoho pinu na stabilitu DOM, který měří produkt, ne komponentu.

## Co fáze 2 nedělá

Tauri okno, tray, autostart, balení, měření paměti okna (fáze 3 a 4), nové
metriky, změny kontraktu snapshotu i změny chování démona nad rámec servírování
SPA. `vue`/`svelte`/Tailwind/Recharts nejsou ve hře; graf zůstává na canvasu.

## Hotovo znamená

1. `cd frontend && npm ci && npm run build` projde a vznikne `sysmon_app/web/`
   s `index.html` a `/static/assets/…`; build sám nikam netahá.
2. `python3 -m unittest discover -s tests -t .` je zelené **s buildem i bez
   něj** (bez buildu se build-závislé piny přeskočí, nic nespadne).
3. `python3 -m sysmon_app` servíruje React UI na 8430 a karty odpovídají
   `sysmonu` na 8420 (porovnáno screenshotem/DOM, jako v Tasku 12).
4. Na telefonu se data aktualizují **bez obnovení stránky** (SSE), a když proud
   umlkne, UI to ukáže místo aby tiše zamrzlo.
5. Mrtvá tlačítka a token nejsou v UI ani v kódu frontendu.
6. Prázdné `watch_ports` se čte jako „nesleduji žádné porty", ne jako výpadek.
7. Počet DOM uzlů v seznamech se s počtem tiků nemění (změřeno).
8. Odebrání klíče z kontraktu v Pythonu rozbije `npm run typecheck`.
9. `sysmon` je nedotčený (`git -C ../sysmon status --short` čistý).
