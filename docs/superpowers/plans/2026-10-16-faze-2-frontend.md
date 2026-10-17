# Fáze 2: Frontend (React + TS + Vite) — implementační plán

> **Pro pracovníky-agenty:** povinný sub-skill:
> `superpowers-extended-cc:subagent-driven-development` (doporučeno), nebo
> `superpowers-extended-cc:executing-plans`. Kroky mají zaškrtávátka (`- [ ]`).

**Goal:** Přenést dnešní frontend (kopie ze `sysmonu`) do Reactu + TypeScriptu +
Vite tak, aby ho servíroval démon, data tekla přes SSE a kontrakt snapshotu byl
pinovaný typy — a aby se to dalo ověřit proti `sysmonu` na 8420.

**Architecture:** Frontend žije v `frontend/` a staví se do `sysmon_app/web/`
(ignorováno gitem). Démon servíruje build stejnými dvěma routami jako dnes
(`/` a `/static/*`), takže kontrakt ze spec se nemění. Stav snapshotu drží
`App`, každá karta dostane svůj řez a je `memo`ovaná; canvas graf baterie
zůstává imperativní.

**Tech Stack:** React 18.3.1, TypeScript 5.6, Vite 5.4 (build i dev server
s proxy na 8430). Python strana zůstává stdlib + `psutil` — žádná nová Python
závislost. Testy frontendu: `tsc` (typy a kontrakt) a měření produktu headless
Chromem; rendering se netestuje (YAGNI, viz spec).

**Zdroje, ze kterých se portuje:** `../sysmon/templates/index.html` (121 řádků),
`../sysmon/static/app.js` (630 řádků), `../sysmon/static/style.css` (585 řádků),
`../sysmon/static/icon.svg`. Dnešní `sysmon_app/web/` je s nimi byte-identická
(ověřeno v Tasku 12 fáze 1) — než se smaže, je to pohodlná lokální reference.

---

## Předletová kontrola (2026-10-16, po dokončení fáze 1)

Naměřeno na tomhle stroji, ať plán nestojí na předpokladech:

- **Sada má 141 testů a je zelená**; `sysmon_app/web/` je byte-identická kopie
  `../sysmon/templates/index.html` + `../sysmon/static/`.
- **Node v22.23.2, npm 10.9.8, registry dostupná** (`npm ping` → PONG 298 ms).
  Build step je tedy proveditelný; `npm ci` v taskách ověří, že verze
  v `package.json` opravdu existují.
- **CSS je soběstačné**: `grep -n "@import\|@font-face\|url(\|http" style.css`
  → nic. Build nesmí tuhle vlastnost ztratit (pin v Tasku 9).
- **`_send()` v `server.py:72-79` posílá vždy `Cache-Control: no-store`** —
  cache hlavičky pro hashované assety se musí přidat **parametrem**, ne
  přepsáním.
- **`load_index()` (`server.py:35-38`) otevírá soubor bez `try`** → chybějící
  build dnes znamená `FileNotFoundError` v handleru, tedy traceback na stderr
  a prázdnou stránku. Task 3 to mění.
- **`load_static()` (`server.py:41-60`) pouští podadresář** jen díky `realpath`
  kontrole; allow-list kryje `.css`, `.js`, `.svg`. Pin na
  `/static/assets/index-<hash>.js` v Tasku 1 to ověří po drátě.
- **Které testy dnes čtou skutečný `web/`** (a proto musí do fixture):
  `LoadStaticTest.test_serves_css_and_js`, `LoadStaticTest.test_serves_icon`,
  `LoadIndexTest.test_index_has_no_inline_style_or_script`,
  `LoadIndexTest.test_index_references_static_assets`,
  `StatsTest.test_static_assets_are_served_over_http`. `tests/test_sse.py` na
  `web/` nesahá.
- **Mrtvá tlačítka v CSS:** `.proc-kill` (`style.css:499-511`), `.ctr-action`
  (`:387-406`). Po jejich odstranění se musejí zúžit mřížky:
  `.ctr-row` (`:338`, `10px 1fr auto auto` → `10px 1fr auto`) a `.proc-row`
  (`:469`, `1fr 54px 70px 28px` → `1fr 54px 70px`; responzivní `:569`,
  `1fr 54px 28px` → `1fr 54px`).
- **`window.gc` hack** (`app.js:630`) patřil k měření paměti ve starém webview —
  do Reactu se **nepřenáší**.
- **Chrome je na stroji** (`/usr/bin/google-chrome-stable`) a umí
  `--headless --dump-dom` i `--screenshot`; fáze 1 to použila k ověření karet.
  Task 9 na tom staví piny na build a na přebudovávání seznamů.
- **Past, na kterou se přišlo až při psaní plánu:** dnešní frontend přebudovává
  seznamy přes `replaceChildren`, takže **počet DOM uzlů zůstává stejný**
  (rostla paměť Blinku, naměřeno ~15 MB/min) — pin na počty by tedy prošel
  i proti starému kódu a nic by neměřil. Task 9 proto měří **childList mutace
  a identitu uzlů** přes harness stránku, kterou server servíruje.

## Pravidla pro každý task

- Pracuje se na větvi **`faze-2-frontend`**; **nikdy se necommituje na `main`**.
- **Do `../sysmon` se nezasahuje** — jen čte.
- `git add` **jen s explicitními cestami**, nikdy `-A` ani `.`.
- Implementátor needituje nic pod `docs/` ani soubory z jiných tasků.
- **Python zůstává bez nových závislostí**; nové závislosti smějí být jen ve
  `frontend/package.json`, a žádná z nich nesmí být runtime závislost stažená
  z CDN (build musí být soběstačný).
- `node_modules/` a `sysmon_app/web/` jsou v `.gitignore`; `frontend/package-lock.json`
  se **commituje** (jinak `npm ci` nemá co dělat).
- Než se spustí Verify u tasku, který potřebuje build, **musí se buildit**
  (`cd frontend && npm ci && npm run build`) — jinak se build-závislé piny tiše
  přeskočí a task vypadá zeleně, aniž by něco změřil.

---

### Task 1: Sada se odpoutá od buildu

**Goal:** Testy indexu a assetů čtou fixture adresář místo repo `web/`, takže
sada projde i v čerstvém klonu bez buildu; piny na index se přeformulují pro
Vite build.

**Files:**
- Create: `tests/web_fixture.py`
- Modify: `tests/test_server.py` (třídy `LoadStaticTest`, `LoadIndexTest`,
  `StatsTest.test_static_assets_are_served_over_http`, a navíc
  `StatsTest.test_index_is_served_at_root` — ten v předloze chyběl a bez jeho
  úpravy kritérium „sada projde bez `web/`" neplatí, protože je to jediný test,
  který čte `index.html` po drátě)

**Acceptance Criteria:**
- [ ] Sada projde i s přesunutým `sysmon_app/web/` (žádný test ho nepotřebuje)
- [ ] `LoadStaticTest` a `LoadIndexTest` čtou fixture adresář přes
      `mock.patch.object(server, "WEB_DIR"/"STATIC_DIR", …)`
- [ ] Pin na index zakazuje **spustitelný inline kód** (tělo `<script>`,
      atributy `on…=`), ne každý výskyt slova `script`; case-insensitive
- [ ] `/static/assets/index-abc123.js` jde stáhnout **po drátě** z fixture
- [ ] Kontrola, že fixture adresář je opravdu ten použitý (jinak by testy
      prošly i s rozbitou cestou)

**Verify:** `python3 -m unittest discover -s tests -t .` → `OK`;
`mv sysmon_app/web /tmp/web-off && python3 -m unittest discover -s tests -t .`
→ `OK` (a `mv` zpět)

**Steps:**

- [ ] **Step 1: Fixture web adresáře**

`tests/web_fixture.py`:

```python
"""Docasny web/ adresar pro testy - ve tvaru, jaky vydava Vite build.

Testy se nesmi opirat o `sysmon_app/web/` v repu: ten je od faze 2 build
a v .gitignore, takze v cerstvem klonu neexistuje. Tvar index.html je tu
zamerne co nejblizsi realnemu Vite vystupu (hashovany asset pod
/static/assets/), aby pin na "zadny spustitelny inline kod" netestoval
neco, co build nikdy nevyrobi.
"""

import contextlib
from pathlib import Path
from tempfile import TemporaryDirectory

# Vite hashuje nazvy; tvar je assets/index-<hash>.js
ASSET_NAME = "assets/index-abc123.js"
INDEX_HTML = """<!doctype html>
<html lang="cs">
  <head>
    <meta charset="utf-8" />
    <link rel="icon" href="/static/icon.svg" />
    <title>Sysmon</title>
    <script type="module" crossorigin src="/static/assets/index-abc123.js"></script>
    <link rel="stylesheet" crossorigin href="/static/assets/index-def456.css">
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>
"""


@contextlib.contextmanager
def fake_web(index=INDEX_HTML):
    """Vytvori docasny web/ s index.html, static/ a hashovanym assetem.

    Vraci (root, static, index_path) a po skonceni bloku uklidi.
    """
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        static = root / "static"
        (static / "assets").mkdir(parents=True)
        (static / ASSET_NAME).write_text("console.log(1);\n", encoding="utf-8")
        (static / "style.css").write_text(".a{color:red}\n", encoding="utf-8")
        (static / "icon.svg").write_text("<svg/>\n", encoding="utf-8")
        (root / "index.html").write_text(index, encoding="utf-8")
        yield root, static, root / "index.html"
```

- [ ] **Step 2: Přepsat `LoadStaticTest` a `LoadIndexTest` na fixture**

V `tests/test_server.py` nahraď obě třídy tímhle (importy `web_fixture` přidej
k ostatním):

```python
from tests import web_fixture


class LoadStaticTest(unittest.TestCase):
    def test_serves_css_and_js(self):
        # I obsah typu: tabulka pripon a content-type k sobe nic mechanicky
        # nevaze, takze prohozene hodnoty projdou pres "neni None".
        expected = {
            "style.css": "text/css; charset=utf-8",
            "assets/index-abc123.js": "application/javascript; charset=utf-8",
        }
        with web_fixture.fake_web() as (_root, static, _index):
            with mock.patch.object(server, "STATIC_DIR", static):
                for name, ctype in expected.items():
                    asset = server.load_static(name)
                    self.assertIsNotNone(asset, name)
                    self.assertEqual(asset[1], ctype, name)
                    # Nacteny soubor je skutecne ten soubor, ne prazdne bajty.
                    self.assertGreater(len(asset[0]), 0, name)

    def test_serves_icon(self):
        with web_fixture.fake_web() as (_root, static, _index):
            with mock.patch.object(server, "STATIC_DIR", static):
                asset = server.load_static("icon.svg")
                self.assertIsNotNone(asset)
                self.assertEqual(asset[1], "image/svg+xml")

    def test_rejects_traversal(self):
        with web_fixture.fake_web() as (_root, static, _index):
            with mock.patch.object(server, "STATIC_DIR", static):
                self.assertIsNone(server.load_static("../config.py"))
                # Cil existuje a ma povolenou priponu, takze ho odmitne jen
                # kontrola cesty - ne chybejici soubor.
                (static.parent / "secret.css").write_text("x", encoding="utf-8")
                self.assertIsNone(server.load_static("../secret.css"))

    # test_rejects_paths_outside_static a test_rejects_disallowed_extension*
    # zustavaji beze zmeny - uz dnes si fixture adresar vyrabi samy.


class LoadIndexTest(unittest.TestCase):
    def test_index_has_no_executable_inline_code(self):
        """Zakazany je spustitelny inline kod, ne kazda zminka o scriptu.

        Vite build ma `<script type="module" src="/static/assets/...">` a to
        je legitimni - kod je v souboru, ne v HTML. Co v HTML byt nesmi, je
        kod zapsany v tele znacky nebo v `on...=` atributech.

        Vsechno se porovnava nad malymi pismeny: nazvy HTML znacek jsou
        case-insensitive, takze `<SCRIPT>alert(1)</SCRIPT>` je stejny inline
        skript jako `<script>` a na holem podtrzeni by prosel.
        """
        with web_fixture.fake_web() as (_root, _static, index):
            with mock.patch.object(server, "WEB_DIR", index.parent):
                text = server.load_index()
        lower = text.lower()
        self.assertNotIn("<style", lower)          # CSS patri do static/
        for tag in re.findall(r"<script\b[^>]*>(.*?)</script>", lower, re.S):
            self.assertEqual(tag.strip(), "", f"inline skript: {tag!r}")
        for tag in re.findall(r"<script\b[^>]*>", lower):
            self.assertIn("src=", tag, f"skript bez src: {tag}")
        for handler in re.findall(r"\son[a-z]+\s*=", lower):
            self.fail(f"inline obsluha udalosti: {handler!r}")

    def test_index_references_hashed_static_assets(self):
        """Kdyz uz je CSS a JS mimo HTML, musi na ne HTML odkazovat."""
        with web_fixture.fake_web() as (_root, _static, index):
            with mock.patch.object(server, "WEB_DIR", index.parent):
                text = server.load_index()
        self.assertIn('src="/static/assets/', text)
        self.assertIn('href="/static/assets/', text)
```

- [ ] **Step 3: Spustit sadu a ověřit, že prochází**

Run: `python3 -m unittest tests.test_server -v`
Expected: PASS (počet testů v `test_server` zůstává stejný)

- [ ] **Step 4: Přepnout `test_static_assets_are_served_over_http` na fixture**

Ten test dnes čte `server.STATIC_DIR / name`. Nahraď tělo tak, aby server
startoval s podstrčeným `STATIC_DIR`:

```python
    def test_static_assets_are_served_over_http(self):
        """Asset musi jit stahnout i po drate - ne jen z `load_static`.

        Ostatni testy /static/ volaji `load_static` naprimo, takze je
        nezajima, jestli na tu funkci vubec vede routa: prejmenovany
        `STATIC_PREFIX`, `load_static(path[1:])` nebo `_send(asset...)`
        nahrazene za `_send_empty(404)` projdou celou sadou a pritom vraci
        prazdnou stranku bez CSS i bez JS.

        Podadresar `assets/` je tu proto, ze ho Vite build pouziva: trasa
        musi umet i vnorenou cestu, ne jen soubor v koreni static/.
        """
        with web_fixture.fake_web() as (_root, static, _index):
            with mock.patch.object(server, "STATIC_DIR", static):
                srv, port = start_server()
                self.addCleanup(srv.shutdown)
                self.addCleanup(srv.server_close)
                expected = {
                    "/static/style.css": (
                        "style.css", "text/css; charset=utf-8"),
                    "/static/assets/index-abc123.js": (
                        web_fixture.ASSET_NAME,
                        "application/javascript; charset=utf-8"),
                }
                for path, (name, ctype) in expected.items():
                    with self.subTest(path=path):
                        response = self.get(path, port=port)
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.getheader("Content-Type"), ctype)
                        # Bajt po bajtu proti souboru na disku: telo jine
                        # delky nebo jineho souboru by pres "neni to prazdne"
                        # proslo.
                        self.assertEqual(response.read(), (static / name).read_bytes())
```

- [ ] **Step 5: Dokázat, že sada build nepotřebuje**

Run:
```bash
mv sysmon_app/web /tmp/web-off
python3 -m unittest discover -s tests -t .
mv /tmp/web-off sysmon_app/web
```
Expected: `OK` i s přesunutým adresářem. **Kdyby sada spadla, je někde
zapomenutý test, který na `web/` pořád sahá** — dohnat, ne obcházet.

- [ ] **Step 6: Commit**

```bash
git add tests/web_fixture.py tests/test_server.py
git commit -m "testy: sada se odpouta od buildu, index se pinuje na inline kod

Frontend se ve fazi 2 buildi do sysmon_app/web/ a ten je v .gitignore, takze
v cerstvem klonu neexistuje. Testy indexu a assetu proto ctou fixture adresar
a pin na index zakazuje spustitelny inline kod (telo scriptu, on...= atributy)
misto kazdeho vyskytu slova script - Vite tam dava <script type=module src=...>.
Nove se po drate pinuje i vnorena cesta /static/assets/."
```

---

> **Uzavření Tasku 1 (2026-10-17) — hotovo, tři commity:** `ffd8619` (sada se
> odpoutala od buildu), `8cc9e17` (pin měří i produkt, mrtvé aserce pryč)
> a `10f9636` (komentář u `data:`). Sada má **143 testů** (`test_server` 20)
> a **projde i bez `sysmon_app/web/`** — tehdy se přeskočí jediný
> build-závislý pin a výsledek je `OK (skipped=1)`, přesně jak má.
>
> **Co se změnilo proti předloze (a proč):**
> - **Předloha v `Files:` neuvedla `StatsTest.test_index_is_served_at_root`.**
>   Bez jeho úpravy kritérium „sada projde bez `web/`" neplatí — je to jediný
>   test, který čte `index.html` po drátě (naměřeno: `FileNotFoundError`).
> - **`assertIsNone(load_static("../config.py"))` nic nepinuovalo** (`.py` není
>   v allow-listu, takže `None` přijde dřív, než se řeší cesta; mutant bez
>   kontroly `realpath` ho nechal projít). Smazáno, cestu pinuje `../secret.css`.
> - **`test_rejects_disallowed_extension` byl mrtvý** — s otevřeným allow-listem
>   prošel (soubory v repo `static/` nejsou, `None` přišel z chybějícího
>   souboru). Smazán; jeho soused to dělá přísněji (vytváří soubory a má
>   kladnou kontrolu).
> - **Pin na inline kód měřil jen vlastní konstantu ve fixture.** Naměřeno:
>   `javascript:` a `data:` odkazy ve fixture **přežily všech 141 testů**
>   a mutant, kdy trasa `/` vůbec nezavolá `load_index()` a pošle konstantní
>   HTML, taky. Oprava: sdílená funkce `check_no_executable_inline_code`,
>   negativní kontrola `test_pin_fires_on_inline_script` (pin musí umět
>   spadnout) a build-podmíněné dvojče
>   `test_real_build_index_has_no_executable_inline_code` (`skipUnless`; dnes
>   běží proti staré kopii ze `sysmonu`, po Tasku 2 poprvé změří skutečný build).
>   `test_index_is_served_at_root` teď porovnává tělo **přesně** proti
>   `server.load_index()`.
> - **Fixture odkazovala na `index-def456.css`, který nikdy nevytvořila**, a nic
>   nevázalo odkazy indexu na soubory. Oprava: `HASH` jako jeden zdroj pravdy,
>   `fake_web` vytváří `.js` i `.css`, a nový
>   `test_every_static_reference_in_index_is_served` stahuje **každý** odkaz
>   pod `/static/` po drátě (dnes 3: ikona, `.js`, `.css`).
> - **Wire test stavěl druhý server zbytečně** — `load_static` čte modulovou
>   `STATIC_DIR` až v době volání, takže patch platí i pro server ze `setUp`
>   (ověřeno: stejné mutanty zabity).
>
> **Vědomé meze:** `data:`/`javascript:` jsou v `src`/`href` zakázané záměrně;
> **plánovaný** tvar indexu žádné `data:` nevyrobí (ikona jde přes `public/`,
> root-absolutní odkazy se neinlinují; `link rel=icon/stylesheet/...` taky ne —
> naměřeno na Vite 8.3.4), ale relativně odkazovaný drobný obrázek přes `<img>`
> by Vite inlinoval. Kdyby pin na buildu zapálil, je to hlasité a vyšetřuje se
> to — nerozšiřuje se pin. Skener značek utne značku na prvním `>` uvnitř
> hodnoty atributu (není to well-formed HTML, prohlížeč se chová stejně).
> Build-závislé piny se bez buildu přeskočí (vědomá mez, viz spec).
>
> **Poučení:** pin, který měří vlastní konstantu, neměří produkt — a bez
> negativní kontroly je nerozeznatelný od žádného pinu. Aserce, kterou vyřídí
> allow-list, nepinuje cestu. Skenovat se mají značky, ne text (próza
> „ text only = 5 " vypadá jako `on…=`). Zapsáno v `CLAUDE.md`.

---

### Task 2: Skelet frontendu a build do `sysmon_app/web/`

**Goal:** `frontend/` s Vite + React + TS, který se buildí do `sysmon_app/web/`;
dnešní kopie frontendu se z repa smaže.

**Files:**
- Create: `frontend/package.json`, `frontend/tsconfig.json`,
  `frontend/vite.config.ts`, `frontend/index.html`, `frontend/src/main.tsx`,
  `frontend/src/App.tsx`, `frontend/public/static/icon.svg`
- Create (generated, commitnout): `frontend/package-lock.json`
- Modify: `.gitignore`
- Delete: `sysmon_app/web/index.html`, `sysmon_app/web/static/app.js`,
  `sysmon_app/web/static/style.css`, `sysmon_app/web/static/icon.svg`

**Acceptance Criteria:**
- [ ] `cd frontend && npm ci && npm run build` projde a vytvoří
      `sysmon_app/web/index.html` a `sysmon_app/web/static/assets/index-<hash>.js`
- [ ] `python3 -m sysmon_app` ten build servíruje: `GET /` → 200 `text/html`,
      `GET /static/assets/index-<hash>.js` → 200 `application/javascript`
- [ ] `git status` je po buildu **čistý** (build je ignorovaný, ne untracked)
- [ ] Stará kopie frontendu je z repa smazaná a `diff` proti `../sysmon` už
      nemá co srovnávat (reference zůstává tam)
- [ ] `npm run dev` nastartuje dev server s proxy na 8430 (démon běží)

**Verify:** build + `curl` po drátě (viz Step 6)

**Steps:**

- [ ] **Step 1: `frontend/package.json`**

```json
{
  "name": "sysmon-app-frontend",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "react": "19.3.1",
    "react-dom": "19.3.1"
  },
  "devDependencies": {
    "@types/react": "19.3.0",
    "@types/react-dom": "19.3.0",
    "@vitejs/plugin-react": "6.1.2",
    "typescript": "5.9.3",
    "vite": "8.3.4"
  }
}
```

Verze jsou záměrně zafixované (žádné `^`): `npm ci` musí být reprodukovatelné.
Vybrané **2026-10-17** dotazem na registry (rozhodnutí: aktuální stable majors):
`vite@8.3.4`, `react@19.3.1`, `@vitejs/plugin-react@6.1.2`, `@types/*@19.3.0`.
**TypeScript zůstává na poslední 5.x (`5.9.3`)** — `7.0.2` je první vydání
přepsaného překladače a `npm run typecheck` je u nás pin kontraktu, takže na
něm nechceme ladit. Vite 8 vyžaduje Node `^20.19` nebo `>=22.12`; na stroji je
**22.23.2** (ověřeno). Kdyby některá verze neexistovala, `npm ci` to řekne
hlasitě — pak zvol nejbližší vyšší a **zapiš to do hlášení**.

- [ ] **Step 2: `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noEmit": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "skipLibCheck": true,
    "types": []
  },
  "include": ["src"]
}
```

`noEmit` je důležité: build dělá Vite, `tsc` jen kontroluje typy. `types: []`
brání tomu, aby do projektu vlezly typy z `node_modules/@types`, které
nepoužíváme.

- [ ] **Step 3: `frontend/vite.config.ts`**

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build jde do sysmon_app/web/ a assety pod static/assets/, takže je servíruje
// dnešní démon beze změny kontraktu: GET / a GET /static/*.
// Dev server proxyuje /stats a /events na běžícího démona (8430), aby se
// nemuselo po každé změně buildit.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../sysmon_app/web",
    emptyOutDir: true,
    assetsDir: "static/assets",
    sourcemap: false,
  },
  server: {
    proxy: {
      "/stats": "http://127.0.0.1:8430",
      "/events": "http://127.0.0.1:8430",
    },
  },
});
```

- [ ] **Step 4: Vstupní HTML a minimální aplikace**

`frontend/index.html`:

```html
<!doctype html>
<html lang="cs">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="icon" href="/static/icon.svg" />
    <title>Sysmon</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`frontend/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

const root = document.getElementById("root");
if (root === null) throw new Error("chybí #root v index.html");
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

`frontend/src/App.tsx` (v tomhle tasku jen kostra, karty přijdou v Tasku 6+):

```tsx
export default function App() {
  return <main id="dashboard">Sysmon</main>;
}
```

- [ ] **Step 5: Ikona a build**

```bash
cp ../sysmon/static/icon.svg frontend/public/static/icon.svg
cd frontend && npm install && npm run build
```

`npm install` vygeneruje `package-lock.json` — ten se commituje.
Zkontroluj, že vznikly přesně tyhle cesty:

```bash
ls ../sysmon_app/web/index.html ../sysmon_app/web/static/assets/
grep -o 'src="[^"]*"' ../sysmon_app/web/index.html
```
Expected: `index.html` existuje, `assets/` obsahuje `index-<hash>.js`
(a `index-<hash>.css`), a `grep` vypíše `src="/static/assets/index-<hash>.js"`.

- [ ] **Step 6: Ověřit po drátě a přes `.gitignore`**

`.gitignore` (přidej k existujícím řádkům):

```
node_modules/
sysmon_app/web/
```

Pak:

```bash
python3 -m sysmon_app &
sleep 3
curl -s -o /dev/null -w "GET / -> %{http_code} %{content_type}\n" localhost:8430/
curl -s localhost:8430/ | grep -o '/static/assets/[^"]*'
for kind in js css; do
  url=$(curl -s localhost:8430/ | grep -o "/static/assets/[^\"]*\.$kind" | head -1)
  curl -s -o /dev/null -w "$kind -> %{http_code} %{content_type}\n" "localhost:8430$url"
done
git status --short
kill %1
```
Expected: `GET /` → 200 `text/html`; **oba** assety (`.js` i `.css`) → 200 se
správným content-type (`application/javascript`, `text/css`) — kdyby `.css`
nevracelo 200, chybí v allow-listu přípon a stránka se načte bez vzhledu;
`git status --short` **prázdný** (build je ignorovaný).

- [ ] **Step 7: Smazat starou kopii frontendu**

```bash
git rm -r --cached sysmon_app/web >/dev/null 2>&1 || true
git rm sysmon_app/web/index.html sysmon_app/web/static/app.js sysmon_app/web/static/style.css sysmon_app/web/static/icon.svg
```

Pozor: `git rm` soubory smaže i z disku — build v `sysmon_app/web/` je ale
ignorovaný, takže o něj nepřijdeš; po commitu si build znovu vygeneruj
(`npm run build`).

- [ ] **Step 8: Dev server s proxy (ověřit, že běží)**

```bash
python3 -m sysmon_app &
cd frontend && npm run dev &
sleep 3
curl -s -o /dev/null -w "dev / -> %{http_code}\n" localhost:5173/
curl -s -o /dev/null -w "dev /stats proxy -> %{http_code}\n" localhost:5173/stats
kill %1 %2
```
Expected: dev server odpovídá na `/`, a `/stats` přes proxy vrací **200** od
démona (ne 404) — tím je proxy ověřená, ne jen nakonfigurovaná.

- [ ] **Step 9: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/tsconfig.json \
        frontend/vite.config.ts frontend/index.html frontend/src/main.tsx \
        frontend/src/App.tsx frontend/public/static/icon.svg .gitignore \
        sysmon_app/web
git commit -m "frontend: skelet Vite + React + TS, build do sysmon_app/web/

Build se necommituje (sysmon_app/web/ je v .gitignore) - zdrojak je ve
frontend/. Assety padaji pod /static/assets/, takže je servíruje dnešní démon
beze změny kontraktu. Dev server proxyuje /stats a /events na 8430.
Stara kopie frontendu ze sysmonu je z repa smazana; reference zustava
v ../sysmon."
```

---

> **Uzavření Tasku 2 (2026-10-17) — hotovo, dva commity:** `36ca792` (skelet
> Vite + React + TS, build do `sysmon_app/web/`, smazaná stará kopie) a
> `b5ddaa2` (komentáře ve `vite.config.ts` bez diakritiky). Spec recenze
> ✅, kvalitativní recenze ⚠️ se dvěma minor nálezy (jeden opraven, druhý
> odložen do Tasku 3 — viz níže).
>
> **Naměřená čísla:** `npm ci` z čisté extrakce commitu (`git archive`) → 25
> balíčků, 0 vulnerabilities; build je deterministický (dva běhy i dvě nezávislé
> extrakce daly stejné hashe): `index.html` 451 B (`4a6a5933…`),
> `static/assets/index-DwUz2KZ4.js` 219 637 B (`c32b5e13…`),
> `static/assets/index-TZrNw7dA.css` 15 B (`6d606818…`),
> `static/icon.svg` 309 B (`3e8d64f0…`, byte-identická s `../sysmon`).
> Po drátě: `/` → 200 `text/html`, `.js` → 200 `application/javascript`
> (Content-Length 219 637, sha256 shodný s diskem), `.css` → 200 `text/css`,
> ikona → 200 `image/svg+xml`, `/stats` → 200. Dev server: `/` → 200,
> `/stats` přes proxy → 200 `application/json` s `host` i `user`,
> `/events` přes proxy → 200 `text/event-stream` s daty. Headless Chrome
> `--dump-dom` → `<div id="root"><main id="dashboard">Sysmon</main></div>`.
> Sada: **143 testů, OK**; v čistém klonu bez buildu `OK (skipped=1)`.
> `git status` po buildu prázdný, `../sysmon` nedotčen.
>
> **Co se změnilo proti předloze (a proč):**
> - **Předloha nechala kostru bez jakéhokoli CSS**, takže Vite `.css` asset
>   nevyrobil — a kontrola v Step 6 by s prázdnou URL z grepu poslala curl na
>   `/`, dostala 200 `text/html` a tvářila se jako úspěch. Přidán minimální
>   `frontend/src/styles/style.css` (reset `body { margin: 0; }`) importovaný
>   v `main.tsx`; Task 6 jen přepíše jeho obsah, `main.tsx` už měnit nemusí.
> - **`emptyOutDir: true` smaže z disku i staré trackované soubory** v
>   `sysmon_app/web/`, takže „`git status` po buildu čistý“ vyžaduje
>   naistagovat mazání **před** buildem (`git rm --cached` čtyř explicitních
>   cest). Pořadí kroků v předloze to nemohlo splnit.
> - **`git add sysmon_app/web` v Step 9 je zakázaný** — adresář je ignorovaný;
>   mazání už je naistagované. Použity jen explicitní cesty.
>
> **Vědomé meze:**
> - `tsconfig.json` má `include: ["src"]`, takže `npm run typecheck`
>   nekontroluje `vite.config.ts` (naměřeno: `const bad: string = 42` tam
>   projde, v `src/App.tsx` selže `TS2322`, rc=2). Vite config načítá při
>   buildu/devu, takže skutečná chyba je hlasitá; plán tsconfig předepisuje
>   přesně takto.
> - `package.json` nemá `engines`; Vite 8 vyžaduje Node `^20.19 || >=22.12`.
>   Na Node 20.18 build jen varuje a projde; na stroji je 22.23.2. README
>   v Tasku 10 má verzi Node uvést.
> - **Odložený nález (MINOR 2):** docstring `sysmon_app/server.py` na řádku 5
>   ještě jmenuje `web/static/style.css`, `app.js`, `icon.svg`; build už vydává
>   `static/assets/index-<hash>.{js,css}`. Opravit v Tasku 3, který `server.py`
>   stejně otevírá (chování se nemění). Zapsáno i v zadání Tasku 3.
> - Komentáře ve `vite.config.ts` měly v předloze diakritiku; po recenzi
>   převedeny do ASCII podle konvence „komentáře bez diakritiky“.

---

### Task 3: Démon umí servírovat build (cache hlavičky, chybějící build)

**Goal:** Hashované assety se cachují `immutable`, `index.html` naopak
`no-store`; chybějící build se hlásí česky při startu i za běhu.

**Files:**
- Modify: `sysmon_app/server.py` (`_send`, `load_index`, `do_GET`)
- Modify: `sysmon_app/__main__.py` (`main`)
- Test: `tests/test_server.py`, `tests/test_main.py`

> **Poznámka z recenze Tasku 2:** docstring `server.py` (řádek 5) ještě
> jmenuje `web/static/style.css`, `app.js` a `icon.svg`; build už vydává
> `static/assets/index-<hash>.{js,css}`. Při této tasku docstring aktualizuj —
> jinak kdo podle něj ladí `/static/`, zkusí smazané cesty a dostane 404.
> Chování se nemění.

**Acceptance Criteria:**
- [ ] `GET /static/assets/index-<hash>.js` má
      `Cache-Control: public, max-age=31536000, immutable`
- [ ] `GET /` má `Cache-Control: no-store` (jinak telefon po rebuildu drží
      starý index odkazující na smazané hashe)
- [ ] `GET /static/icon.svg` má `no-store` (nemá hash v názvu)
- [ ] Bez buildu: `python3 -m sysmon_app` vypíše českou větu s cestou
      a s příkazem, `rc=2`, žádný traceback
- [ ] Když build zmizí za běhu: `GET /` → **503** s českou větou v `text/plain`
      (žádný traceback na stderr)
- [ ] Chování `/stats`, `/events` a 404 se nemění

**Verify:** `python3 -m unittest tests.test_server tests.test_main -v` → PASS;
plus živý běh s přesunutým buildem (Step 6)

**Steps:**

- [ ] **Step 1: Testy cache hlaviček a chybějícího indexu**

Do `tests/test_server.py` přidej (za `StatsTest`):

```python
class CacheHeadersTest(unittest.TestCase):
    """Hashovany asset se muze cachovat navzdy, index nikdy.

    Telefon si stranku drzi otevřenou a po rebuildu by z cache vzal stary
    index.html, ktery odkazuje na assety s jinym hashem - tedy na soubory,
    ktere uz neexistuji. Proto index no-store a hashovane assety immutable.
    """

    def setUp(self):
        self.web = web_fixture.fake_web()
        root, static, _index = self.web.__enter__()
        self.addCleanup(self.web.__exit__, None, None, None)
        self.patch_web = mock.patch.object(server, "WEB_DIR", root)
        self.patch_static = mock.patch.object(server, "STATIC_DIR", static)
        self.patch_web.start()
        self.patch_static.start()
        self.addCleanup(self.patch_web.stop)
        self.addCleanup(self.patch_static.stop)
        self.server, self.port = start_server()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)

    def get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(conn.close)
        conn.request("GET", path)
        return conn.getresponse()

    def test_hashed_asset_is_immutable(self):
        response = self.get(f"/static/{web_fixture.ASSET_NAME}")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Cache-Control"),
                         "public, max-age=31536000, immutable")

    def test_index_and_unhashed_asset_are_no_store(self):
        for path in ("/", "/static/icon.svg", "/static/style.css"):
            with self.subTest(path=path):
                self.assertEqual(self.get(path).getheader("Cache-Control"),
                                 "no-store")


class MissingBuildTest(unittest.TestCase):
    def setUp(self):
        self.empty = tempfile.TemporaryDirectory()
        self.addCleanup(self.empty.cleanup)
        self.patch_web = mock.patch.object(server, "WEB_DIR",
                                           Path(self.empty.name))
        self.patch_web.start()
        self.addCleanup(self.patch_web.stop)
        self.server, self.port = start_server()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)

    def test_root_says_it_in_czech_instead_of_traceback(self):
        """Chybejici build je uzivatelova situace, ne havarie serveru."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(conn.close)
        conn.request("GET", "/")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        self.assertEqual(response.status, 503)
        self.assertEqual(response.getheader("Content-Type"),
                         "text/plain; charset=utf-8")
        self.assertIn("frontend", body)
        self.assertIn("npm ci", body)
```

Do `tests/test_main.py` přidej do existující třídy s hláškami (vedle
`test_broken_config_ends_with_a_sentence_and_the_path`):

```python
    def test_missing_build_ends_with_a_sentence_and_the_command(self):
        """Bez buildu nema smysl startovat - a nesmi to byt traceback."""
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(vstupni_bod, "load_settings",
                                   return_value=Settings()), \
                 mock.patch.object(vstupni_bod.server, "WEB_DIR", Path(tmp)):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    rc = vstupni_bod.main([])
        self.assertEqual(rc, 2)
        out = stderr.getvalue()
        self.assertIn("frontend", out)
        self.assertIn("npm ci && npm run build", out)
        self.assertNotIn("Traceback", out)
```

(Pokud `tests/test_main.py` importuje `server` jinak, použij stejný způsob
přístupu, jaký soubor už používá — hlavně ať se patchuje **ten modul, který
`__main__` opravdu volá**.)

- [ ] **Step 2: Ověřit, že testy padají**

Run: `python3 -m unittest tests.test_server.CacheHeadersTest tests.test_server.MissingBuildTest tests.test_main -v`
Expected: FAIL — hlavičky jsou dnes `no-store` všude a `/` dnes vyhazuje
`FileNotFoundError` (případně 500).

- [ ] **Step 3: Implementace v `server.py`**

`load_index()` nahraď:

```python
def load_index():
    """Nacte web/index.html (UTF-8), nebo None kdyz build chybi."""
    try:
        with open(WEB_DIR / INDEX_NAME, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None
```

`_send()` dostane parametr pro cache (výchozí chování zůstává `no-store`):

```python
    def _send(self, body, ctype, status=200, cache="no-store"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(data)
```

Přidej konstantu a helper hned pod `STATIC_TYPES`:

```python
# Hashovane assety z Vite buildu se nikdy nemeni pod svym jmenem, takze se
# mohou cachovat navzdy. Vsechno ostatni (index.html, ikona, style.css) jmeno
# nemeni, ale obsah ano - tam cache znamena starou verzi po rebuildu.
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
HASHED_ASSET_DIR = "assets/"


def cache_for(name):
    """Cache-Control pro soubor z /static/ podle toho, jestli ma hash v ceste."""
    return IMMUTABLE_CACHE if name.startswith(HASHED_ASSET_DIR) else "no-store"
```

Větev `/` v `do_GET` nahraď:

```python
        elif path in ("/", "/index.html"):
            index = load_index()
            if index is None:
                self._send(
                    "Frontend není zbuilděný. Spusť v adresáři frontend:\n"
                    "    npm ci && npm run build\n",
                    "text/plain; charset=utf-8",
                    status=503,
                )
            else:
                self._send(index, "text/html; charset=utf-8")
```

a větev `/static/` tak, aby použila cache:

```python
        elif path.startswith(STATIC_PREFIX):
            name = path[len(STATIC_PREFIX):]
            asset = load_static(name)
            if asset is None:
                self._send_empty(404)
            else:
                self._send(asset[0], asset[1], cache=cache_for(name))
```

- [ ] **Step 4: Implementace v `__main__.py`**

Přidej kontrolu buildu mezi `parse_args` a start (a import `load_index`):

```python
from sysmon_app.server import load_index, serve
```

```python
def report_missing_build(web_dir):
    """Chybejici build je uzivatelova situace - hlasi se vetou, ne tracebackem."""
    print(
        f"Frontend není zbuilděný ({web_dir / 'index.html'} neexistuje).\n"
        f"Spusť v adresáři frontend:\n"
        f"    npm ci && npm run build",
        file=sys.stderr,
    )
```

a v `main()` hned po kontrole `config_error`:

```python
    if load_index() is None:
        report_missing_build(server_modul.WEB_DIR)
        return 2
```

(Použij ten modul, který v `__main__.py` zastupuje `sysmon_app.server`;
v dnešním souboru se importuje `serve` napřímo, takže přidej
`from sysmon_app import server as server_modul` — ať je cesta k `WEB_DIR`
patchovatelná v testu.)

- [ ] **Step 5: Spustit testy**

Run: `python3 -m unittest tests.test_server tests.test_main -v`
Expected: PASS

- [ ] **Step 6: Ověřit naživo s přesunutým buildem**

```bash
mv sysmon_app/web /tmp/web-off
python3 -m sysmon_app; echo "rc=$?"
mv /tmp/web-off sysmon_app/web
```
Expected: česká věta s cestou a s `npm ci && npm run build`, `rc=2`, žádný
`Traceback`. Pak s buildem na místě:

```bash
python3 -m sysmon_app &
sleep 3
curl -s -D - -o /dev/null localhost:8430/ | grep -i "cache-control"
curl -s -D - -o /dev/null "localhost:8430$(curl -s localhost:8430/ | grep -o '/static/assets/[^"]*\.js' | head -1)" | grep -i "cache-control"
kill %1
```
Expected: první `no-store`, druhá `public, max-age=31536000, immutable`.

- [ ] **Step 7: Commit**

```bash
git add sysmon_app/server.py sysmon_app/__main__.py tests/test_server.py tests/test_main.py
git commit -m "server: cache hlavicky pro build a cestina kdyz build chybi

Hashovane assety immutable, index.html no-store - jinak by telefon po rebuildu
drzel stary index odkazujici na smazane hashe. Chybejici build se hlasi vetou
pri startu (rc=2) i za behu (503), ne tracebackem."
```

---

> **Uzavření Tasku 3 (2026-10-17) — hotovo, čtyři commity:** `bd2647a` (cache
> hlavičky + hlášení chybějícího buildu), `421a2c7` (testy čtou těla odpovědí —
> jinak keep-alive RST tracebacky), `42dfd55` (izolace brány buildu
> v `MainTestCase`/`SIGINT_SCRIPT`, `/stats` pin) a `e307004` (normalizace
> cesty v `cache_for`, pin 503 `no-store`). Spec recenze ✅ (10/10 mutantů),
> kvalitativní ⚠️ se čtyřmi minor (tři opraveny, jeden vědomá mez), delta
> recenze ✅.
>
> **Naměřená čísla:** sada **151 testů** s buildem → `OK`; **bez buildu**
> (přesunutý `sysmon_app/web`) → `OK (skipped=2)`, rc=0, v obou bězích
> **0 tracebacků** na stderr. Skip jsou `RealBuildCacheHeadersTest`
> a Task 1 build-závislý pin. Po drátě na skutečném buildu: `/` →
> `no-store`, `index-DwUz2KZ4.js` → `public, max-age=31536000, immutable`,
> `index-TZrNw7dA.css` → totéž, `/static/icon.svg` → `no-store`, `/stats` →
> 200 JSON `no-store`, `/events` → 200 `text/event-stream` `no-store`, 404
> beze změny. `curl --path-as-is /static/assets/../icon.svg` → `no-store`
> (dřív immutable). Bez buildu: `rc=2`, stdout prázdný, stderr česká věta
> s přesnou cestou `.../sysmon_app/web/index.html` a `npm ci && npm run build`,
> 0 tracebacků. Za běhu po odebrání `index.html`: `/` → 503
> `text/plain; charset=utf-8`, `no-store`, česká věta; `/stats` dál 200;
> `handle_error` nevolán. Mutanty: 10/10 zabito (cache vždy `no-store`, jen
> `.js`, vždy immutable, default immutable, `load_index` bez `try`, 200 místo
> 503, brána po `Monitor`, hláška bez cesty, rc 0, špatný content-type) + další
> (503 immutable, zdvojená hlavička, prázdný index).
>
> **Co se změnilo proti předloze (a proč):**
> - **Startovní test nesmí volat `main()` napřímo.** Předloha by před
>   implementací spustila skutečný `Monitor` a server a mohla zavěsit; test
>   používá `self.run_main([])` z `MainTestCase` (podstrčené
>   `Monitor`/`Feed`/`serve`).
> - **Brána `load_index() is None` v `main()` je stav celé sady.** Po jejím
>   zavedení spadlo bez buildu 11 testů v `test_main.py`; `MainTestCase.setUp`
>   proto podstrkuje temp `WEB_DIR` s `index.html` a `SIGINT_SCRIPT` patchuje
>   `load_index`. Invariant „sada projde bez buildu“ je znovu pinovaný
>   (`OK (skipped=2)`).
> - **Přidány testy, které předloha neměla:** `BuildDisappearsTest` (skutečné
>   zmizení buildu za běhu + `/stats` dál 200), `RealBuildCacheHeadersTest`
>   (build-závislý pin nad skutečným buildem), immutable pro hashovaný `.css`
>   (mutant „jen `.js`“), `no-store` pro `/stats` a pro 503.
> - **`cache_for` rozhoduje podle normalizované cesty.** Syrové jméno
>   `assets/../icon.svg` prošlo prefixem a nehashovaná ikona dostala
>   `immutable`; `os.path.normpath` to zavírá a test to pinuje.
> - **Testy čtou těla odpovědí.** Nepřečtené tělo při `conn.close()` pošle RST,
>   server v keep-alive skončí `ConnectionResetError` a vytiskne traceback,
>   i když sada hlásí OK (naměřeno 6×). Opraveno v nových i jednom starším
>   testu.
>
> **Vědomé meze:**
> - `load_index()` chytá jen `FileNotFoundError`. Když `index.html` existuje,
>   ale je to adresář nebo je nečitelný (práva 000), start skončí tracebackem
>   a za běhu klient dostane spadlé spojení místo 503 (naměřeno). Mimo literální
>   AC Tasku 3; kandidát na hardening v některém z dalších tasků.
> - Abort požadavku klientem (RST, `SO_LINGER 0`) pořád vede na `handle_error`
>   a traceback na stderr — chování před Taskem 3, netýká se chybějícího buildu.
>   Řeší se až s SSE v Tasku 10 (obal před hlavičkami).
> - `404` neposílá `Cache-Control` (předchozí chování; 404 není v AC).
> - Dva importy téhož modulu v `__main__.py` (`serve`/`load_index` napřímo kvůli
>   testovacímu seamu + `server_modul` kvůli `WEB_DIR`) jsou okomentované;
>   refaktor by rozbil `run_main` patchování.
>
> **Poučení:** (1) vstupní brána v `main()` musí být v testech izolovaná, jinak
> se rozbije invariant „sada bez buildu“; (2) cache rozhodnutí podle syrové URL
> cesty jde obejít `..` — normalizovat; (3) nepřečtené tělo odpovědi dělá
> z keep-alive RST traceback, zelená sada to neskryje. Zapsáno v `CLAUDE.md`.

---

### Task 4: Typy kontraktu a fixture, která nemůže zestárnout

**Goal:** `snapshot.ts` popisuje kontrakt a `snapshot.contract.ts` ho pinuje
proti fixture generované Pythonem, takže rozejití typů s kontraktem shodí
`npm run typecheck`.

**Files:**
- Create: `tests/fixtures/snapshot.json` (generovaný, commitnutý)
- Modify: `tests/test_snapshot_contract.py` (nový test)
- Create: `frontend/src/types/snapshot.ts`, `frontend/src/types/snapshot.contract.ts`

**Acceptance Criteria:**
- [ ] Fixture je **stabilní** (žádné časy, procenta ani PIDy z tohoto stroje)
      a její klíčová sada odpovídá kontraktu, který pinuje už dnešní test
- [ ] Test porovnává fixture na disku s čerstvě vygenerovanou → ruční editace
      fixture test shodí; přegeneruje se jen `UPDATE_FIXTURE=1`
- [ ] `npm run typecheck` projde
- [ ] Když se z `snapshot.ts` odebere povinný klíč, který fixture má,
      typecheck **nespadne** (extra klíče JSON nehlídá) — ale když se odebere
      klíč, který fixture **nemá**, spadne. Obojí je potřeba ověřit a hranice
      je vědomá: klíčovou sadu pinuje Python test, tvary pinuje TS
- [ ] `snapshot.contract.ts` není importovaný z aplikace (jinak by fixture
      putovala do buildu — ověř `grep -rn "snapshot.contract" frontend/src`
      kromě sebe sama)

**Verify:** `cd frontend && npm run typecheck` → bez chyb;
`python3 -m unittest tests.test_snapshot_contract -v` → PASS

**Steps:**

- [ ] **Step 1: Test, který fixture hlídá**

Do `tests/test_snapshot_contract.py` přidej (a doplň potřebné importy —
`json`, `os`, `Path`):

```python
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "snapshot.json"


def stable_snapshot():
    """Snapshot pro frontendovou fixture: stejny tvar jako kontrakt, ale
    zmrazeny hodnoty.

    Nesmi tu byt nic, co se meni samo (cas, procenta, PIDy): fixture se
    commituje a porovnava, takze volatilni hodnota by rozbila kazdy druhy beh.
    Tvary jsou zamerne vcetne degradovanych pripadu - `loadavg: None`,
    `battery.available: False`, chybejici `cpu_temp` ve druhem vzorku - protoze
    presne ty musi TypeScript unest.
    """
    return {
        "host": "stroj",
        "user": "clovek",
        "cpu": 12.5,
        "cpu_cores": [1.0, 2.0, 3.0, 4.0],
        "cpu_temp": 55.0,
        "mem": {"available": True, "total": 1000, "used": 500, "percent": 50.0},
        "swap": {"available": True, "total": 1000, "used": 0, "percent": 0.0},
        "loadavg": {"1m": 0.5, "5m": 0.4, "15m": 0.3},
        "disk": {"available": True, "percent": 66.0, "used": 100, "total": 200,
                 "read_rate": 0.0, "write_rate": 0.0},
        "processes": [{"pid": 1, "name": "init", "cpu": 1.0, "mem": 10}],
        "system": {"kernel": "6.0", "uptime_seconds": 3600, "nvme_temp": None},
        "gpu": {"available": False, "error": "zadna GPU"},
        "battery": {"available": True, "percent": 80, "status": "Discharging",
                    "time_remaining_minutes": None},
        "battery_history": [{"t": 0, "v": 80}, {"t": 120, "v": 79}],
        "net": {"down": 0.0, "up": 0.0, "total_recv": 1, "total_sent": 2},
        "services": [{"port": 22, "label": "SSH", "on": True}],
        "containers": {"groups": [], "running": 0},
    }


class FrontendFixtureTest(unittest.TestCase):
    """Fixture pro TypeScript musi odpovidat kontraktu a nemuze zestarnout.

    Kontraktni test vyse pinuje, ktere klice `Monitor.snapshot()` vraci; tenhle
    test pinuje, ze fixture ma presne tyz klice - a ze se soubor na disku
    nerozesel s tim, co by vygeneroval ted.
    """

    def test_fixture_has_the_same_keys_as_contract(self):
        contract_keys = set(self.contract_keys())   # viz Step 2
        self.assertEqual(set(stable_snapshot()), contract_keys)

    def test_file_on_disk_matches_generated(self):
        text = json.dumps(stable_snapshot(), ensure_ascii=False,
                          indent=2, sort_keys=True) + "\n"
        if os.environ.get("UPDATE_FIXTURE") == "1":
            FIXTURE.parent.mkdir(parents=True, exist_ok=True)
            FIXTURE.write_text(text, encoding="utf-8")
            self.skipTest("fixture pregenerovana (UPDATE_FIXTURE=1)")
        self.assertTrue(FIXTURE.exists(), f"chybí {FIXTURE}; spusť s UPDATE_FIXTURE=1")
        self.assertEqual(FIXTURE.read_text(encoding="utf-8"), text,
                         "fixture zestárla - spusť s UPDATE_FIXTURE=1")
```

- [ ] **Step 2: `contract_keys()` — jedna pravda o klíčích**

Aby se seznam klíčů neopisoval na dvou místech, vytáhni v tomtéž modulu klíče
z **téže tabulky, kterou používá dnešní kontraktní test** (v souboru je tabulka
„16 klíčů, které musí být ve snapshotu vždy" plus `cpu_temp` navíc). Přidej:

```python
    def contract_keys(self):
        """Klice kontraktu - z tabulky, kterou pinuje kontraktni test vyse."""
        return set(CONTRACT_KEYS) | {"cpu_temp"}
```

kde `CONTRACT_KEYS` je jméno, pod kterým ta tabulka v souboru už je (ověř si
ho; kdyby tam byla anonymně, pojmenuj ji a použij ji i v dnešním testu — dvě
kopie seznamu by se rozešly).

- [ ] **Step 3: Vygenerovat fixture a ověřit pin**

```bash
UPDATE_FIXTURE=1 python3 -m unittest tests.test_snapshot_contract -v
python3 -m unittest tests.test_snapshot_contract -v
```
Expected: první běh `OK (skipped=1)`, druhý `OK`. Pak zkus fixture ručně
rozbít (smaž v ní klíč) a spusť znovu — **musí spadnout**.

- [ ] **Step 4: Typy kontraktu**

`frontend/src/types/snapshot.ts` — piš podle skutečných tvarů z
`sysmon_app/collectors/*.py` (ne podle dojmu); tady je kostra, kterou musíš
naplnit přesně:

```ts
// Kontrakt snapshotu. Klice a tvary musi odpovidat Monitor.snapshot() v Pythonu;
// drzi to fixture tests/fixtures/snapshot.json a snapshot.contract.ts.
//
// Pozor na dve veci, ktere v Pythonu nedodrzuji konvence:
//  - `system` a `processes` neznaji `available: false` - vraceji null,
//    castecny dict, nebo rovnou seznam;
//  - `loadavg` a `cpu_temp` legitimne byvaji null (stroj bez cidel).

export type CoreLoad = number;

export interface MemInfo { available: boolean; total: number; used: number; percent: number; }
export interface SwapInfo { available: boolean; total: number; used: number; percent: number; }
export interface LoadAvg { "1m": number; "5m": number; "15m": number; }
export interface DiskInfo {
  available: boolean; percent: number; used: number; total: number;
  read_rate: number; write_rate: number; error?: string;
}
export interface ProcessInfo { pid: number; name: string; cpu: number; mem: number; }
export interface SystemInfo { kernel: string | null; uptime_seconds: number | null; nvme_temp?: number | null; }
export interface GpuInfo {
  available: boolean; vendor?: string; percent?: number; mem_used?: number;
  mem_total?: number; temp?: number; error?: string;
}
export interface BatterySample { t: number; v: number; }
export interface BatteryInfo {
  available: boolean; percent?: number; status?: string;
  time_remaining_minutes?: number | null; error?: string;
}
export interface NetInfo { down: number; up: number; total_recv: number; total_sent: number; }
export interface ServiceInfo { port: number; label: string; on: boolean; }
export interface ContainerInfo { name: string; cpu: number; mem: number; project: string; }
export interface ContainerGroups { groups: { name: string; items: ContainerInfo[] }[]; running: number; }

export interface Snapshot {
  host: string;
  user: string;
  cpu: number;
  cpu_cores: CoreLoad[];
  cpu_temp?: number | null;
  mem: MemInfo;
  swap: SwapInfo;
  loadavg: LoadAvg | null;
  disk: DiskInfo;
  processes: ProcessInfo[] | null;
  system: SystemInfo | null;
  gpu: GpuInfo;
  battery: BatteryInfo;
  battery_history: BatterySample[];
  net: NetInfo;
  services: ServiceInfo[];
  containers: ContainerGroups | { available: false; error: string };
}
```

**Tvary ber z kolektorů, ne z téhle kostry** — kostra je orientační a je
potřeba ji srovnat s `collectors/*.py` (hlavně `containers`, `gpu`, `system`).

- [ ] **Step 5: Kontraktní soubor**

`frontend/src/types/snapshot.contract.ts`:

```ts
// Jen pro `npm run typecheck` - aplikace tenhle soubor NEIMPORTUJE, aby se
// fixture nezbundlovala do buildu. Kdyz Python zmeni kontrakt a typy se
// neupravi, spadne typecheck.
import fixture from "../../../tests/fixtures/snapshot.json";
import type { Snapshot } from "./snapshot";

// `satisfies` je prisnejsi nez `as`: kdyz fixture nema klic, ktery typ
// vyzaduje, nebo ma hodnotu jineho typu, je to chyba prekladu.
export const contractFixture = fixture satisfies Snapshot;
```

- [ ] **Step 6: Ověřit, že pin opravdu pinuje**

```bash
cd frontend
npm run typecheck                      # Expected: bez chyb
# 1. pridej do snapshot.ts povinny klic, ktery fixture nema:
#    do interface Snapshot pridej "nova_metrika: number;"
npm run typecheck                      # Expected: CHYBA (fixture ho nema)
# 2. vrat zmenu a over, ze je zase zeleno
npm run typecheck
```

Zapiš do hlášení oba výstupy (i ten chybový) — je to důkaz, že pin něco měří.

- [ ] **Step 7: Commit**

```bash
git add tests/fixtures/snapshot.json tests/test_snapshot_contract.py \
        frontend/src/types/snapshot.ts frontend/src/types/snapshot.contract.ts
git commit -m "typy: kontrakt snapshotu v TS a fixture, ktera nemuze zestarnout

Fixture generuje Python test a porovnava ji s tim, co je na disku - rucni
editace ani tichy drift neprojdou. snapshot.contract.ts ji typecheckuje pres
`satisfies Snapshot`, takze rozejiti typu s kontraktem shodi npm run typecheck.
Soubor aplikace neimportuje, aby fixture neputovala do buildu."
```

---

> **Uzavření Tasku 4 (2026-10-17) — hotovo, dva commity:** `326fbf2` (typy
> kontraktu + fixture) a `1b80912` (keyof assertiony, degradovaný vzorek,
> zúžení `cpu_temp`, poctivé komentáře). Spec recenze ✅; kvalitativní ⚠️ se
> dvěma important (oba opraveny) a třemi minor (dva opraveny, jeden vědomá
> mez); delta recenze ✅.
>
> **Naměřená čísla:** sada **153 testů** (`test_snapshot_contract` 20),
> 0 tracebacků. Fixture `tests/fixtures/snapshot.json` má sha256
> `829bc269…c15d` a po `UPDATE_FIXTURE=1` je bajtově identická (17 top-level
> klíčů = 16 z `ALWAYS_PRESENT` + `cpu_temp`). `npm run typecheck` OK;
> `npm run build` OK; v `sysmon_app/web/static/assets/` nejsou `stroj`,
> `clovek`, `contractFixture` ani `contractDegraded` — fixture se do buildu
> nezbundluje. Mutanty: přidání povinného `nova_metrika` (který fixture nemá)
> → `TS1360`; odebrání `host` z typu → typecheck projde (extra JSON klíč
> `satisfies` nehlídá); `cpu: number`→`string` i změna hodnoty ve fixture na
> `"12.5"` → `TS1360`; přejmenování `util`→`percent`, `status_label`→
> `statusLabel`, `Names`→`NamesX`, `cpu_temp`→`cpuTemp` → `TS2344` (keyof
> assertiony); `vendor`/`kernel`/`disk.percent` na povinné → `TS1360`
> (degradovaný vzorek); `groups: []` místo objektu → `TS1360`.
>
> **Co se změnilo proti předloze (a proč):**
> - **Kostra typů lhala o skutečných tvarech.** Ověřeno proti
>   `collectors/*.py` a `monitor.py`: `net` má `total_up` (ne `total_sent`),
>   `gpu` má `util` (ne `percent`) a fallback `{available: false}` bez
>   `error`, `mem`/`swap` nemají `available`, `battery` má `status_label`
>   a `ac_online`, `system` padá na `{}` (všechna pole volitelná), `processes`
>   je vždy pole, `containers` je
>   `{available, error, groups: Record<string, ContainerInfo[]>}` (ne
>   `{groups: [], running}`). Fixture i typy používají tyto tvary.
> - **`satisfies` sám nestačí.** Extra klíče JSON nehlídá a názvy volitelných
>   polí nepinuovuje; přidány `keyof` assertiony a `contractDegraded`
>   s fallbackovými tvary, takže přejmenování `util` nebo zesílení `vendor`
>   na povinné typecheck shodí.
> - **`cpu_temp?: number`**, ne `number | null` — produkt klíč buď nepřidá,
>   nebo pošle číslo.
> - **Komentáře v `snapshot.contract.ts` a `snapshot.ts` zpřesněny**
>   (podmnožina Docker polí, stabilita fixture, kdo padá na `{}`).
>
> **Vědomé meze:**
> - `satisfies` nehlídá extra klíče ani názvy volitelných polí; kryjí to
>   keyof assertiony pro pole, která UI používá, a degradovaný vzorek. Nové
>   volitelné pole musí přidat do obou míst, jinak ho pin nechrání.
> - Fixture je ručně zmrazený reprezentant, ne mechanicky odvozený
>   z kolektorů; nested tvary nejsou s Pythonem svázané. Top-level klíčovou
>   sadu pinuje Python test, tvary TS.
> - `npm run typecheck` není součástí Python sady; kdo běží jen `unittest`,
>   drift typů neuvidí.
> - **Neblokující nález z delta recenze:** komentář u `contractDegraded` říká
>   „Presne tyhle tvary vraceji fallbacky z `Monitor.snapshot()`“, ale objekt
>   je `{...fixture, ...overrides}` a obsahuje i klíče z fixture, které
>   fallbacky nejsou (`mem`, `swap`, `cpu_temp`, …). Tvary jsou správné
>   a pinované; text zpřesnit při příštím dotyku `snapshot.contract.ts`.
>
> **Poučení:** (1) kontrakt na dvou jazycích se pinuje ze dvou stran — Python
> klíčovou sadu a stabilitu fixture, TS tvary; `satisfies` nehlídá extra klíče
> ani volitelné názvy, proto keyof assertiony a degradovaný vzorek; (2) plánová
> kostra typů není spec — tvary se berou z kolektorů (`util`, `total_up`,
> `groups` jako objekt); (3) fixture generovaná kódem musí být stabilní
> a přegenerovatelná jen explicitním příznakem, jinak zestárne tiše. Zapsáno
> v `CLAUDE.md`.

---

### Task 5: Datová vrstva — `/stats`, SSE proud a pojistka proti zamrznutí

**Goal:** Jeden hook, který drží snapshot: první vykreslení z `/stats`, pak
`EventSource('/events')`, a když proud umlkne, přepne na polling a dá to
najevo.

**Files:**
- Create: `frontend/src/data/useSnapshot.ts`, `frontend/src/lib/format.ts`
- Modify: `frontend/src/App.tsx`

**Acceptance Criteria:**
- [ ] První vykreslení je z `/stats` (karty nemusí čekat na SSE)
- [ ] Rámce z `/events` aktualizují snapshot; `EventSource` se reconnectuje sám
- [ ] Když rámec nedorazí do `STALE_MS`, hook polluje `/stats` každých
      `POLL_MS` a stav je `live: false`; po dalším rámci se polling vypne
- [ ] Po odmountování nezůstane otevřený `EventSource` ani timer
- [ ] Konstanty `POLL_MS`/`STALE_MS` jsou pojmenované a okomentované jako
      duplikát `TICK_SEC` z Pythonu

**Verify:** živý démon + headless Chrome se dvěma různými
`--virtual-time-budget` → vykreslená hodnota CPU se mezi běhy liší (data
tečou); `--dump-dom` neobsahuje `–` na místě hodnoty

**Steps:**

- [ ] **Step 1: `format.ts` (port z `app.js`)**

Přenese se z `../sysmon/static/app.js`: `fmt` (bajty a rychlosti, v `app.js`
jako pomocné funkce kolem řádku 88-115), `formatUptime` (:88) a `formatPorts`
(:98). Zkopíruj je **beze změny chování** a přidej typy:

```ts
export function formatUptime(sec: number): string { /* port z app.js:88 */ }
export function formatPorts(raw: number[]): string { /* port z app.js:98 */ }
export function fmt(bytes: number): string { /* port z app.js */ }
```

Kdyby v `app.js` nějaká z nich chyběla pod tím jménem, použij tu, kterou
karta skutečně volá, a jméno sjednoť (nikdy neopisuj dvakrát).

- [ ] **Step 2: Hook**

`frontend/src/data/useSnapshot.ts`:

```ts
import { useEffect, useRef, useState } from "react";
import type { Snapshot } from "../types/snapshot";

// TICK_SEC z Pythonu (config.py) je 1,5 s. Frontend ho potrebuje pro dve veci
// a Python ho nesdeli, takze se hodnota duplikuje VEDOME: kdyby se tik zmenil,
// je to druhe misto k uprave.
export const POLL_MS = 1500;   // perioda pollingu, kdyz proud mrtvi
export const STALE_MS = 4500;  // ~3 tiky ticha = proud zamrzl

export interface SnapshotState {
  snapshot: Snapshot | null;
  live: boolean;      // false = data jdou z pollingu, ne z proudu
  error: string | null;
}

export function useSnapshot(): SnapshotState {
  const [state, setState] = useState<SnapshotState>({
    snapshot: null, live: true, error: null,
  });
  const lastFrame = useRef(0);

  useEffect(() => {
    let cancelled = false;

    const take = (data: Snapshot, live: boolean) => {
      if (cancelled) return;
      lastFrame.current = Date.now();
      setState({ snapshot: data, live, error: null });
    };

    // 1) prvni vykresleni z /stats - karty maji data driv, nez se SSE chyti
    fetch("/stats")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((data: Snapshot) => take(data, false))
      .catch((e: unknown) => {
        if (!cancelled) setState((s) => ({ ...s, error: String(e) }));
      });

    // 2) proud; EventSource si reconnect resi sam
    const source = new EventSource("/events");
    source.onmessage = (event: MessageEvent<string>) => {
      take(JSON.parse(event.data) as Snapshot, true);
    };

    // 3) pojistka: kdyz proud umlkne, tlacit data aspon pollingem - tise
    //    zamrzly dashboard je presne ta vada, kterou ma `net` kolektor
    const timer = window.setInterval(() => {
      if (Date.now() - lastFrame.current < STALE_MS) return;
      void fetch("/stats")
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
        .then((data: Snapshot) => take(data, false))
        .catch((e: unknown) => {
          if (!cancelled) setState((s) => ({ ...s, error: String(e) }));
        });
    }, POLL_MS);

    return () => {
      cancelled = true;
      source.close();
      window.clearInterval(timer);
    };
  }, []);

  return state;
}
```

- [ ] **Step 3: `App.tsx` — kostra, na které je vidět, že data tečou**

```tsx
import { useSnapshot } from "./data/useSnapshot";

export default function App() {
  const { snapshot, live, error } = useSnapshot();
  if (error !== null && snapshot === null) {
    return <main id="dashboard">Chyba: {error}</main>;
  }
  if (snapshot === null) {
    return <main id="dashboard">Načítání…</main>;
  }
  return (
    <main id="dashboard">
      <p id="hostname">{snapshot.host}</p>
      <p id="cpu">{snapshot.cpu.toFixed(0)}</p>
      <p id="live">{live ? "SSE" : "poll"}</p>
    </main>
  );
}
```

(Karty a hlavička přijdou v Tasku 6; tenhle krok je jen to, co jde změřit.)

- [ ] **Step 4: Změřit, že data opravdu tečou**

```bash
cd frontend && npm run build
cd .. && python3 -m sysmon_app &
sleep 3
for budget in 3000 12000; do
  google-chrome-stable --headless --disable-gpu --no-sandbox \
    --virtual-time-budget=$budget --dump-dom http://localhost:8430/ \
    | grep -o '<p id="cpu">[^<]*' 
done
kill %1
```
Expected: dva různé běhy dají **různé** hodnoty CPU (data se aktualizují) a ani
jeden neobsahuje `–`. Kdyby byly stejné, je to podezřelé — změř to víckrát
a zapiš, co jsi viděl.

> **Poznámka po uzavření:** tento příkaz proti **živému** SSE visí
> (`--virtual-time-budget` čeká na otevřený fetch; naměřeno `rc=124`).
> Živá cesta se měřila přes CDP v reálném čase; mrtvá SSE větev a první
> vykreslení flagem prošly. Viz uzavření Tasku 5.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/data/useSnapshot.ts frontend/src/lib/format.ts frontend/src/App.tsx
git commit -m "frontend: data z /stats a SSE proudu, s pojistkou proti zamrznuti

Prvni vykresleni jde z /stats, pak zivi EventSource; kdyz ramec nedorazi do
STALE_MS, prepne se na polling a stav to prizna. Tise zamrzly dashboard je
vada, kterou ma net kolektor zdedenou - tady se na ni ceka."
```

---

> **Uzavření Tasku 5 (2026-10-17) — hotovo, dva commity:** `258dd4e` (data
> z `/stats` + SSE + fallback) a `70d2af5` (`live:false` při vypršení staleness
> i při selhávajícím pollu; monotónní `performance.now()`). Spec recenze ✅;
> kvalitativní ⚠️ s 1 important (opraven) a 4 minor (1 opraven, 2 odloženy do
> Tasku 6, 1 zapsán zde); delta recenze ✅.
>
> **Naměřená čísla:** sada **153 testů** OK, 0 tracebacků. Živé SSE: různé CPU
> mezi čteními (např. 3 → 1), `live:"SSE"`, jediný úvodní `/stats`;
> auto-reconnect (harness zavíral spojení) → 6× `events-open`, rámce zase
> tekly, jediný `/stats`. Mrtvé SSE: první vykreslení z `/stats`
> (`host=harness`, `live=poll`), polling **4,5 s** po mountu a pak každých
> **1,5 s** (naměřeno `+4.50 +1.50 +1.50 +1.50`). Rozbitá varianta (poll
> posouvá `lastFrame`) dala `+6.00` a výrazně méně requestů (2 vs 6). Po rámci
> uprostřed fallbacku: polling se zastavil, do 5,5 s (> `STALE_MS`) žádný
> `/stats`, `live:"SSE"`; zpožděná `/stats` odpověď po rámci se zahodila
> (guard `lastFrame`/`appliedSeq`; mutant bez obou ukázal stará data). Unmount
> (dočasný build s `root.unmount()`): po 4,5 s žádný poll, `EventSource`
> zavřený. `format.ts`: 0 neshod proti `app.js` na desítkách vstupů
> (uptime/ports/bytes, včetně `undefined`, `NaN`, `±Infinity`, duplicit, IPv6).
>
> **Oprava IMPORTANTu:** scénář „živé SSE 3 s → proud utne + `/stats` 500“
> dával na starém buildu v 8,2 s i 13,2 s `live:"SSE"` se zamrzlými čísly;
> nový build `live:"poll"`. Clock skew −5 min: starý build polling zastavil
> (3 → 3), nový pokračoval (3 → 8). Oprava `live` nepřerenderovává každý tik:
> build s čítačem renderů 3 → 3 vs mutant 6 → 7.
>
> **Co se změnilo proti předloze (a proč):**
> - **Polling cadence v předloze byla chybná.** `take()` posouval `lastFrame`
>   i při pollu, takže po prvním pollu se další odložil o `STALE_MS`
>   (naměřeno 6,0 s místo 1,5 s). `lastFrame` se nyní posouvá jen při SSE
>   rámci; polling response ho nemění.
> - **`formatPorts` bere string, ne `number[]`.** Předloha měla špatný typ;
>   v `app.js` je to raw Docker `Ports` string (`raw.split(",")`).
>   `formatUptime` bere `number | undefined` (`system.uptime_seconds` je
>   volitelné).
> - **Přidány guardy proti starší odpovědi** (`lastFrame` + `appliedSeq`)
>   a try/catch kolem `JSON.parse`; bez nich mohl pozdní `/stats` přepsat
>   novější SSE rámec.
> - **`live` se překlápí už při vypršení staleness**, ne až při úspěšném
>   pollu; jinak mrtvý proud + selhávající poll ukazoval `SSE` a zamrzlá
>   čísla.
> - **Staleness používá `performance.now()`**, ne `Date.now()`; posun
>   systémových hodin zpět jinak fallback vypne.
> - **Plánový Verify (`--virtual-time-budget`) proti živému SSE visí**
>   (Chrome čeká na otevřený fetch; `timeout 20` → rc=124). Měřeno přes CDP
>   v reálném čase; mrtvá SSE větev a první vykreslení šly flagem.
>
> **Vědomé meze:**
> - `App.tsx` je jen kostra: chybu zobrazí jen když `snapshot === null`, takže
>   selhání pollu při existujícím snapshotu není vidět; texty jsou `String(e)`
>   („Chyba: Error: 500“). Patří do Tasku 6, kde vzniká skutečné UI.
> - Bez `AbortController`: po unmountu už odeslaný fetch doběhne, ale
>   `cancelled` zabrání `setState`. Naměřeno, že nové polly po unmountu
>   nevznikají.
> - Poškozený `data:` rámec se tiše zahodí (poslední dobrý snapshot zůstává);
>   syntakticky platný, ale neúplný rámec by mohl shodit render — server je
>   same-origin a tvar garantuje kontrakt.
> - `setInterval` tiká každých 1,5 s i při živém SSE (jeden levný callback);
>   při `live:false` vrací `setState` stejný objekt, takže žádný re-render.
> - Přímé odmountování není v repu testované (bez frontendové testovací
>   knihovny); ověřeno dočasným buildem s `root.unmount()`, ne trvalým pinem.
>
> **Poučení:** (1) fallback, který při pollu posouvá stale timestamp, polluje
> každých `STALE_MS`, ne `POLL_MS`; (2) staleness se měří monotónním časem —
> `Date.now()` a posun hodin zpět fallback vypne; (3) `live:false` patří
> k vypršení staleness, ne k úspěchu pollu, jinak mrtvý proud se selhávajícím
> pollem lže „SSE“; (4) `--virtual-time-budget` proti otevřenému SSE visí —
> měř reálným časem. Zapsáno v `CLAUDE.md`.

---

### Task 6: Vzhled — CSS, hlavička a karty CPU, GPU, RAM

**Goal:** Port vzhledu začíná: CSS ze `sysmonu` (bez stylů mrtvých tlačítek),
hlavička a tři karty, které se aktualizují tik po tiku.

**Files:**
- Create: `frontend/src/styles/style.css` (port `../sysmon/static/style.css`)
- Create: `frontend/src/components/Header.tsx`, `CpuCard.tsx`,
  `Cores.tsx`, `GpuCard.tsx`, `MemCard.tsx`, `Bar.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/main.tsx` (import CSS)

> **Poznámky z uzavření Tasku 5 (závazné pro tento task):**
> - `frontend/src/main.tsx` už `import "./styles/style.css";` obsahuje
>   z Tasku 2 — neduplikuj ho; pokud import zůstane, `main.tsx` se nemění.
> - `frontend/src/lib/format.ts` je hotový, ale `coreColor(v)` (port `color`
>   z `app.js`) v něm chybí; přidej ho tam. `Bar` musí kromě `width`
>   nastavovat i `background` podle prahu (jinak se barva pruhu nikdy
>   nezmění) — použij stejnou funkci jako `Cores`.
> - `Snapshot.gpu` **nemá `error`** (kolektor ho nevrací); degradovaný stav
>   vykresli jako dnešní `app.js` („nedetekováno“ v `#gpu-sub`), ne přes
>   `gpu.error`.
> - Odložené minor nálezy z Tasku 5: `App.tsx` má zobrazit `error` i tehdy,
>   když už `snapshot` existuje (např. „poslední data před …“), a chybové
>   texty mapovat na češtinu místo `String(e)` („Chyba: Error: 500“).
> - **`--virtual-time-budget` proti živému SSE visí** (Task 5, naměřeno
>   rc=124). Pro screenshot 8430 použij CDP (`Page.captureScreenshot` po
>   reálném čekání) nebo dočasný harness s mrtvým `/events`; 8420 (sysmon)
>   používá polling, takže flagem projde. Procesy uklízej explicitními PID,
>   ne `%1 %2`.

**Acceptance Criteria:**
- [ ] Vzhled je **1:1**: CSS se přenáší beze změny až na odstraněné styly
      mrtvých tlačítek (`.proc-kill`, `.ctr-action` včetně `:hover`/`:disabled`)
      a zúžené mřížky, které na ně odkazovaly
- [ ] Karty se **nepřebudovávají**: mění se jen text, šířka pruhu a barva;
      seznamy mají stabilní `key` (jádra podle indexu)
- [ ] Na prvcích, které se mění každý tik, není animace `width`/`height`/
      `box-shadow` (dnešní CSS to dodržuje — port to nesmí zavléct)
- [ ] Karty jsou `memo`ované a dostávají jen svůj řez snapshotu
- [ ] Hodnoty odpovídají `sysmonu` na 8420 (porovnat screenshotem)

**Verify:** build + démon + screenshot obou portů vedle sebe (Step 5)

**Steps:**

- [ ] **Step 1: CSS**

```bash
mkdir -p frontend/src/styles
cp ../sysmon/static/style.css frontend/src/styles/style.css
```
Pak v `frontend/src/styles/style.css` **smaž** bloky mrtvých tlačítek a zúž
mřížky (řádky podle `../sysmon/static/style.css`, ověř si je):

| Co | Kde | Změna |
|---|---|---|
| `.ctr-action`, `:hover:not(:disabled)`, `:disabled` | 387–406 | smazat |
| `.ctr-row` | 338 | `10px 1fr auto auto` → `10px 1fr auto` |
| `.proc-kill`, `:hover`, `:disabled` | 499–511 | smazat |
| `.proc-row` | 469 | `1fr 54px 70px 28px` → `1fr 54px 70px` |
| `.proc-row` (responziv) | 569 | `1fr 54px 28px` → `1fr 54px` |

`diff ../sysmon/static/style.css frontend/src/styles/style.css` musí ukázat
**jen** tyhle změny — nic víc. Do `main.tsx` přidej `import "./styles/style.css";`
(uprostřed `src/` to Vite zpracuje a vydá jako hashovaný `.css`).

- [ ] **Step 2: `Bar.tsx` — pruh, který se jen aktualizuje**

```tsx
import { memo } from "react";

// Pruh se nemeni prestavbou, jen se posune hodnota - proto `transform`/`width`
// menime pres style a nic neanimujeme (dnesni CSS to dodrzuje).
export const Bar = memo(function Bar(props: { percent: number; id?: string }) {
  return (
    <div className="bar">
      <div className="fill" id={props.id} style={{ width: `${props.percent}%` }} />
    </div>
  );
});
```

- [ ] **Step 3: `Cores.tsx` — mřížka jader bez přebudování**

```tsx
import { memo } from "react";

// Jadra musi mit stabilni key (index), aby React menil jen text a vysku
// pruhu. Prebuildovani ~90 prvku kazdy tik bylo to, co driv rostlo v pameti.
export const Cores = memo(function Cores({ values }: { values: number[] }) {
  return (
    <div className="cores" id="cores">
      {values.map((v, i) => (
        <div className="core" key={i} title={`Jádro ${i}: ${v.toFixed(0)}%`}>
          <div className="cfill" style={{ height: `${v}%` }} />
          <span>{v.toFixed(0)}</span>
        </div>
      ))}
    </div>
  );
});
```

Barvu pruhu řeší dnešní `color(v)` z `app.js` — přenes ji do `lib/format.ts`
jako `coreColor(v)` a použij v `style={{ background: coreColor(v) }}`.

- [ ] **Step 4: `Header`, `CpuCard`, `GpuCard`, `MemCard`**

Portuj z `../sysmon/static/app.js` **funkci po funkci**; tady je mapa, co kam
patří (řádky jsou orientační, ověř si je):

| Dnešní kód (`app.js`) | Kam | Co zapisuje |
|---|---|---|
| `tick()` hlavička | `Header.tsx` | `#hostname`, `#uptime` (`formatUptime`), `#dot` (třída podle `live`/stale) |
| `tick()` CPU + `renderCores` | `CpuCard.tsx` | `#cpu`, `#cpu-bar`, `#cpu-meta` (load + `cpu_temp`), `#cores` |
| `tick()` GPU (~:523–533) | `GpuCard.tsx` | `#gpu-label`, `#gpu`, `#gpu-unit`, `#gpu-bar`, `#gpu-sub` |
| `tick()` RAM/swap | `MemCard.tsx` | `#mem`, `#mem-bar`, `#mem-sub`, `#swap-sub` |

Struktura komponenty musí odpovídat `index.html` ze `sysmonu` **do tvaru**
(stejné třídy a id), protože na nich stojí CSS: karta je
`<div className="card" id="cpu-card">` s `.card-head` (`.label`, `.val`) a pak
tělem. Opiš to z `../sysmon/templates/index.html` (řádky 24–51 pro CPU/GPU/RAM).

Degradované tvary: `cpu_temp` může chybět, `loadavg` může být `null`,
`gpu.available === false` znamená kartu s `error` (dnešní kód to tak vykresluje
— zachovej to).

- [ ] **Step 5: Porovnat se `sysmonem` okem**

```bash
cd frontend && npm run build && cd ..
python3 ../sysmon/sysmon.py &
python3 -m sysmon_app &
sleep 3
for port in 8420 8430; do
  google-chrome-stable --headless --disable-gpu --no-sandbox --hide-scrollbars \
    --window-size=1400,1200 --virtual-time-budget=6000 \
    --screenshot=/tmp/f2-$port.png http://localhost:$port/
done
kill %1 %2
```
Pak si oba screenshoty prohlédni (ne jen `ls`): karty CPU, GPU a RAM musí mít
stejné rozměry, stejné popisky a stejné rozložení; lišit se smí jen čísla
a počet dlaždic jader (na obou portech stejný).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/styles/style.css frontend/src/components/Header.tsx \
        frontend/src/components/CpuCard.tsx frontend/src/components/Cores.tsx \
        frontend/src/components/GpuCard.tsx frontend/src/components/MemCard.tsx \
        frontend/src/components/Bar.tsx frontend/src/App.tsx frontend/src/main.tsx
git commit -m "frontend: vzhled a karty CPU, GPU, RAM (port 1:1)

CSS se prenasi beze zmeny az na styly mrtvych tlacitek; karty jsou memoovane,
seznamy maji stabilni key a meni se jen text, sirka pruhu a barva."
```

> **Uzavření Tasku 6 (2026-10-17) — hotovo, commit `a0b385c`:** CSS port,
> hlavička a karty CPU/GPU/RAM. Spec recenze ✅ (0 blokujících); kvalitativní
> ✅ (0 blokujících, 5 minor zapsáno níže jako vědomé meze).
>
> **Naměřená čísla:** sada **153 testů** OK; `npm run build` i `npm run
> typecheck` rc 0 (CSS 9,89 kB, JS 224,87 kB). CSS diff proti
> `../sysmon/static/style.css` má přesně 5 hunků a aplikace jen povolených
> změn dala **byte-identický** soubor
> (`sha256 fdfd5a6c1ba1049168f779d597a094c36b4d2db2ac8404267850ebe70d273f80`).
> Markup: každé id (`cpu`, `cpu-bar`, `cpu-meta`, `cores`, `gpu*`, `mem*`,
> `swap-sub`, `hostname`, `uptime`, `dot`) právě jednou, struktura shodná
> s `../sysmon/templates/index.html`. Živé SSE 6 s: **0 childList mutací**,
> `#cores` stále 16 dětí, první `.core` i `#cpu-card` tytéž objekty; mutace
> jen `title`/`style`/text. Změna 1 → 6 jader: stávající uzel zůstal, přibylo
> 5. `display: contents` na `#root`: computed `contents`; přepnutí na `block`
> zhroutilo layout (topbar 1340 → 97 px). Mobil 375 px bez vodorovného
> přetečení. Degradované tvary ověřeny znak po znaku (U+2014 „—“ vs U+2013
> „–“, dvě mezery u `swap  —` i `  ·  ` u GPU). Chyba `/stats` 500 se starým
> snapshotem: „poslední známá data · server vrátil 500“, karty zůstanou; po
> návratu 200 text zmizí.
>
> **Co se změnilo proti předloze (a proč):**
> - **`#root` vs mřížka `body`.** Vite mount point by byl jediný grid item
>   a karty by byly 1/12 široké; `root.style.display = "contents"` v
>   `main.tsx` to řeší bez nového pravidla v CSS (to by porušilo „diff jen
>   s povolenými změnami“).
> - **Markup používá `.row`, ne `.card-head`.** Předloha v plánu byla
>   zastaralá; rozhoduje `../sysmon/templates/index.html` a CSS.
> - **GPU nedostupné = „nedetekováno“**, ne `gpu.error` (kolektor `error`
>   nevrací); `gpu.util == null` = „–“, nedostupné = „—“.
> - **Chybové texty se mapují do češtiny** (`describeError`) místo `String(e)`;
>   chyba se ukáže i se starým snapshotem.
>
> **Vědomé meze:**
> - `memo` na kartách je dnes fakticky dekorativní: snapshot z `JSON.parse` má
>   každý tik nové identity objektů, takže shallow compare neprojde. Kritérium
>   „nepřebudovávají se“ je splněné na DOM (0 childList mutací); custom
>   comparator by ušetřil jen práci nad ~16 prvky.
> - `GPU · undefined`, pokud by `available: true` přišlo bez `vendor`; dnešní
>   kolektor `vendor` v úspěšné větvi vždy nastaví a `app.js` se chová stejně.
>   Hardening (`gpu.vendor ? … : "GPU"`) patří sem, až by tvar mohl nastat.
> - `document.title` zůstává statické „Sysmon“; `app.js` ho přepisoval na
>   `user@host — Sysmon`. Task 6 ho v mapě neměl (jen `#hostname`, `#uptime`,
>   `#dot`) a název produktu se rozhoduje až s README/titulekem.
> - `describeError` slévá všechny ne-HTTP chyby do „spojení se serverem
>   selhalo“, i `SyntaxError` z `r.json()`. Uživatelsky přijatelné,
>   diagnosticky chudší.
> - Hlavička karty (`.row`/`.label`/`.val`) se opakuje ve třech komponentách;
>   abstrahovat se vyplatí, až Task 7–8 přidají další karty — teď by to byla
>   předčasná abstrakce a markup se musí držet 1:1.
>
> **Poučení:** (1) CSS, které počítá s přímými potomky `body`, se pod React
> mount pointem tiše rozbije (karty 1/12 šířky) — `display: contents` na
> mount pointu to řeší bez zásahu do portovaného CSS; (2) „karty se
> nepřebudovávají“ se měří childList mutacemi a identitou uzlů, ne počtem
> React renderů ani přítomností `memo`; (3) screenshot se srovnává při
> přirozené výšce obsahu — v širokém viewportu s málo kartami `body` grid
> roztahuje řádky a geometrie se rozejde bez zásahu do kódu.
> Zapsáno v `CLAUDE.md`.

---

### Task 7: Baterie (canvas), síť a disk

**Goal:** Tři karty, z toho jedna s imperativním canvas grafem, který nesmí
projít React renderem.

**Files:**
- Create: `frontend/src/components/BatteryCard.tsx`,
  `frontend/src/components/BatteryChart.tsx`, `NetworkCard.tsx`, `DiskCard.tsx`
- Modify: `frontend/src/App.tsx`

**Acceptance Criteria:**
- [ ] Graf baterie kreslí **imperativně** do canvasu (`useRef` + `useEffect`),
      ne přes React elementy — při 1,5s intervalu by SVG/DOM bod pro každý bod
      byl přesně to, co se jednou muselo odstraňovat
- [ ] Graf se překresluje jen když se změní historie (ne každý tik)
- [ ] `battery.available === false` vykreslí dnešní text, ne prázdnou kartu
- [ ] Karty sítě a disku odpovídají `sysmonu` (screenshot)

**Verify:** build + screenshot obou portů (jako Task 6) a kontrola, že se graf
baterie vykreslil (`--dump-dom` obsahuje `<canvas class="battery-chart"`)

**Steps:**

- [ ] **Step 1: `BatteryChart.tsx`**

`drawBatteryChart(data)` z `../sysmon/static/app.js:119-198` se přenese
**beze změny výpočtů** do komponenty:

```tsx
import { memo, useEffect, useRef } from "react";
import type { BatterySample } from "../types/snapshot";

// Kresleni je imperativni schvalne: pri 1,5s tiku by graf z React elementu
// znamenal prvek na kazdy bod historie. Canvas je mimo React render - meni se
// jen jeho obsah, a to pouze kdyz se zmeni historie.
export const BatteryChart = memo(function BatteryChart(
  { history }: { history: BatterySample[] },
) {
  const ref = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (canvas === null) return;
    drawBatteryChart(canvas, history);
  }, [history]);

  return <canvas className="battery-chart" id="battery-chart" ref={ref} />;
});
```

`drawBatteryChart(canvas, history)` je port z `app.js` (včetně práce s
`devicePixelRatio` a s barvami z CSS proměnných — dnešní kód si je čte přes
`getComputedStyle`, přenes to taky).

- [ ] **Step 2: `BatteryCard.tsx`**

Mapa z `app.js` (řádky orientační): `#battery-percent`, `#battery-bar`,
`#battery-status`, `#battery-power`, a `#battery-chart-wrap` s `display:none`,
když historie nemá dost bodů (dnešní chování — ověř v `app.js`, za jakých
podmínek se wrap zobrazuje).

- [ ] **Step 3: `NetworkCard.tsx` a `DiskCard.tsx`**

| Dnešní kód | Kam | Co zapisuje |
|---|---|---|
| `tick()` NET (~:586) | `NetworkCard.tsx` | `#net-down`, `#net-up`, `#net-sub` |
| `tick()` DISK (~:595–597) | `DiskCard.tsx` | `#disk-pct`, `#disk-bar`, `#disk-sub`, `#disk-io` |

- [ ] **Step 4: Přidat karty do `App.tsx` a změřit**

Karty jdou do `App` ve stejném pořadí jako v `../sysmon/templates/index.html`,
protože na pořadí stojí mřížka (`grid-column: span N`).

Run: build + oba démoni + screenshoty (postup jako Task 6, Step 5)
Expected: baterie, síť a disk vypadají jako na 8420; graf baterie je vidět tam,
kde je vidět na 8420.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/BatteryCard.tsx \
        frontend/src/components/BatteryChart.tsx \
        frontend/src/components/NetworkCard.tsx \
        frontend/src/components/DiskCard.tsx frontend/src/App.tsx
git commit -m "frontend: karty baterie (canvas), site a disku"
```

---

### Task 8: Služby, procesy, Docker — a konec mrtvých tlačítek

**Goal:** Zbylé tři karty, včetně opravy prázdné konfigurace portů, a úplné
odstranění akcí a tokenu z frontendu.

**Files:**
- Create: `frontend/src/components/ServicesCard.tsx`, `ProcessesCard.tsx`,
  `DockerCard.tsx`
- Modify: `frontend/src/App.tsx`

**Acceptance Criteria:**
- [ ] Prázdné `watch_ports` (tj. `services === []`) se čte jako **„Nesleduji
      žádné porty"** — ne jako „0 / 0" po smazaném placeholdru „Načítání…",
      což čte jako výpadek všech služeb
- [ ] Služeb bez konfigurace se to týká i počtu v hlavičce karty (`#svc-count`)
- [ ] V celém `frontend/src` není ani zmínka o tokenu, `actionHeaders`,
      `missingTokenMessage` ani o `/action/` (pin v Tasku 9)
- [ ] Žádné tlačítko ✕ ani ↻ se nevykresluje
- [ ] Seznamy (služby, procesy, kontejnery) mají **stabilní `key`** — port →
      služba, PID → proces, jméno skupiny + jméno kontejneru → řádek
- [ ] Docker zobrazuje skupiny podle Compose projektu a `Ostatní` jako
      poslední (chování `group_by_project` v Pythonu, dnešní render to respektuje)

**Verify:** build + oba démoni + `--dump-dom` na 8430: `#svc-count` odpovídá
8420 a seznam služeb sedí položku po položce; s prázdným `[watch_ports]`
(v `/tmp` configu přes `XDG_CONFIG_HOME`) karta hlásí „Nesleduji žádné porty"

**Steps:**

- [ ] **Step 1: `ServicesCard.tsx` (včetně prázdného stavu)**

Port `renderServices` (`app.js:232-255`). Navíc:

```tsx
// Prazdny seznam neni "vsechno je dole", ale "nic se nesleduje": kdyz uzivatel
// nema ve watch_ports ani jeden port, vraci get_services prazdny seznam a karta
// s "0 / 0" by lhala o vypadku. Port znamena "nesleduji ho", ne "nebezi".
const empty = items.length === 0;
```
Text `#svc-count`: `empty ? "—" : \`${on} / ${items.length}\`` a místo seznamu
hláška `Nesleduji žádné porty — nastav [watch_ports] v config.toml`.

- [ ] **Step 2: `ProcessesCard.tsx`**

Port `procRow` (`app.js:256-271`) a `renderProcesses` (`:272-297`) **bez**
tlačítka ✕. `key` je `pid`. Počet v hlavičce zůstává `top N` (dnešní text
`#proc-count`), barvu CPU (proti počtu jader) přenes z `color(v)`.

- [ ] **Step 3: `DockerCard.tsx`**

Port `dockerRow` (`:305-327`, **bez** `ctr-action`), `showDockerMessage`
(`:328-336`) a `renderDocker` (`:337-428`). Zprávy zůstávají české a stejné
jako dnes („Žádné běžící kontejnery", hláška o nedostupném Dockeru).

- [ ] **Step 4: Dokázat, že token a akce nikde nejsou**

```bash
grep -rniE "token|actionHeaders|missingTokenMessage|/action/" frontend/src/ ; echo "rc=$?"
```
Expected: **žádný výskyt** (`rc=1`). Kdyby něco našel, je to zbytek portu.

- [ ] **Step 5: Prázdné `watch_ports` naživo**

```bash
mkdir -p /tmp/f2-empty/sysmon-app
printf 'port = 8443\n[watch_ports]\n' > /tmp/f2-empty/sysmon-app/config.toml
cd frontend && npm run build && cd ..
XDG_CONFIG_HOME=/tmp/f2-empty python3 -m sysmon_app &
sleep 3
google-chrome-stable --headless --disable-gpu --no-sandbox \
  --virtual-time-budget=6000 --dump-dom http://localhost:8443/ | grep -o 'Nesleduji žádné porty' | head -1
kill %1
```
Expected: hláška se vypíše. (A na 8430 s výchozí konfigurací tam naopak být
nesmí.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ServicesCard.tsx \
        frontend/src/components/ProcessesCard.tsx \
        frontend/src/components/DockerCard.tsx frontend/src/App.tsx
git commit -m "frontend: karty sluzeb, procesu a dockeru; konec mrtvych tlacitek

Prazdne watch_ports se cte jako 'Nesleduji zadne porty', ne jako vypadek vsech
sluzeb. Token, akcni hlavicky a /action/ routy z frontendu zmizely - produkt
zadne akce nema."
```

---

### Task 9: Piny, které měří produkt, ne komponenty

**Goal:** Tři piny na to, co dnešní sada neumí: build netahá nic z internetu,
DOM se s tiky nerozrůstá, a když proud umlkne, stránka se přesto aktualizuje.

**Files:**
- Create: `tests/test_frontend_build.py`
- Modify: `tests/test_sse.py` (jen pokud je potřeba společný helper pro stub
  server — jinak nic)

**Acceptance Criteria:**
- [ ] Privacy pin: build neobsahuje odkaz na cizí origin
      (`href="http`, `src="http`, `url(http` v CSS) — dnešní CSS nic netahá
      a build to nesmí změnit
- [ ] Rebuild pin: po ~80 ticích s **konstantním** snapshotem je v kontejnerech
      seznamů **nula** childList mutací a první řádek každého seznamu je **tyž
      objekt** (pin se ptá na přebudovávání, ne na počet uzlů — ten zůstává
      stejný i když se seznam přebuduje, takže by nic neměřil)
- [ ] Fallback pin: se serverem, který na `/events` odpovídá chybou a na
      `/stats` vydává **měnící se** hodnotu, se stránka přesto aktualizuje
- [ ] Všechny tři piny se **přeskočí** (`skipUnless`), když není build nebo
      chrome — a v hlášení tasku musí být vidět, jestli opravdu běžely
- [ ] Když se pin pustí proti dnešnímu (`sysmon`) frontendu, rebuild pin
      **spadne** — je to důkaz, že měří něco skutečného

**Verify:** `python3 -m unittest tests.test_frontend_build -v` → 3 testy PASS
(ne skipped) s buildem a Chromem

**Steps:**

- [ ] **Step 1: Společný helper na spuštění Chroma**

`tests/test_frontend_build.py`:

```python
"""Piny, ktere meri produkt: build, chovani v prohlizeci a prebuildovavani.

Vsechny tri potrebuji build v `sysmon_app/web/` a `google-chrome-stable`.
Bez nich se preskakuji - sada musi zustat zelena i v cerstvem klonu, ale
v hlaseni tasku musi byt videt, jestli pin opravdu bezel.
"""

import json
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from sysmon_app import server
from sysmon_app.feed import SnapshotFeed

CHROME = shutil.which("google-chrome-stable") or shutil.which("chromium")
BUILD_INDEX = server.WEB_DIR / "index.html"
NEEDS_BUILD = unittest.skipUnless(BUILD_INDEX.exists(),
                                  "chybí build (npm run build ve frontend/)")
NEEDS_CHROME = unittest.skipUnless(CHROME, "chybí headless Chrome")


class ConstantMonitor:
    """Porad stejny snapshot - pin meri prebuildovavani, ne zmenu dat."""

    def __init__(self, snapshot):
        self._snapshot = snapshot

    def snapshot(self):
        return self._snapshot


def dump_dom(port, budget_ms):
    """Vrati serializovane DOM po `budget_ms` virtualniho casu.

    Virtualni cas je tu klicovy: 1,5s tik appky utece v virtualnim case
    okamzite, takze 80 tiku se stihne v sekundach realneho casu.
    """
    out = subprocess.run(
        [CHROME, "--headless", "--disable-gpu", "--no-sandbox",
         f"--virtual-time-budget={budget_ms}", "--dump-dom",
         f"http://127.0.0.1:{port}/"],
        capture_output=True, text=True, timeout=180, check=True,
    )
    return out.stdout


def _cpu_value(html):
    found = re.search(r'id="cpu"[^>]*>([^<]*)', html)
    return found.group(1) if found else None
```

- [ ] **Step 2: Privacy pin**

```python
class BuildPrivacyTest(unittest.TestCase):
    """Build nesmi tahat nic z internetu - dnesni CSS nic netaha."""

    @NEEDS_BUILD
    def test_build_has_no_external_origins(self):
        index = BUILD_INDEX.read_text(encoding="utf-8")
        for pattern in ('href="http', 'src="http', 'href="//', 'src="//'):
            self.assertNotIn(pattern, index.lower(), pattern)
        for css in (server.WEB_DIR / "static" / "assets").glob("*.css"):
            text = css.read_text(encoding="utf-8")
            self.assertNotIn("url(http", text, css.name)
            self.assertNotIn("@import", text, css.name)
```

- [ ] **Step 3: Pin na přebudovávání seznamů (mutace + identita uzlů)**

**Pozor, tohle je past, na kterou se přišlo až při psaní plánu:** počítat DOM
uzly **nestačí**. Dnešní frontend přebudovává seznamy přes `replaceChildren`,
takže počet uzlů zůstává stejný — rostla paměť Blinku (naměřeno ~15 MB/min),
ne počet elementů. Test na počty by prošel i proti starému kódu, tedy by
vypadal, že něco měří, a neměřil by nic.

Co rebuild opravdu chytí: **počet childList mutací** v kontejnerech seznamů
a **identita uzlů** (je první řádek po N ticích pořád týž objekt?). Obojí jde
změřit bez CDP — stránka, kterou server servíruje, je náš harness: spustí
bundl, nasadí `MutationObserver` a výsledek **zapíše do DOM**, odkud ho
`--dump-dom` přečte.

```python
HARNESS = """<!doctype html>
<html lang="cs"><head><meta charset="utf-8"><title>harness</title></head>
<body>
<div id="root"></div>
<div id="result">pending</div>
<script type="module">
  // Harness se servíruje ze stejného originu jako appka, takže vidí do jejího
  // DOMu. Appka je jen bundle v /static/assets/ - import spustí main.tsx.
  const LISTS = ["cores", "services-list", "proc-list", "docker-containers"];
  await import("%(bundle)s");
  await new Promise((r) => setTimeout(r, 300));   // prvni vykresleni
  const seen = LISTS.map((id) => document.getElementById(id)?.firstElementChild ?? null);
  let mutations = 0;
  const observer = new MutationObserver((records) => { mutations += records.length; });
  for (const id of LISTS) {
    const el = document.getElementById(id);
    if (el !== null) observer.observe(el, { childList: true, subtree: true });
  }
  // Virtualni cas bezi rychle: 80 tiku appky (1,5 s) je tu par sekund.
  await new Promise((r) => setTimeout(r, 120000));
  const same = LISTS.map((id, i) => {
    const el = document.getElementById(id)?.firstElementChild ?? null;
    return seen[i] === null ? "n/a" : String(el === seen[i]);
  });
  document.getElementById("result").textContent =
    "mutations=" + mutations + " same=" + same.join(",");
</script></body></html>
"""


class ListRebuildTest(unittest.TestCase):
    """Seznamy se nesmi prebuildovavat kazdy tik.

    Meri se pocet mutation zaznamu v kontejnerech seznamu a to, jestli prvni
    radek zustal tyz objekt. Konstantni snapshot => spravne chovani znamena
    nula mutaci po prvnim vykresleni; kde se objevi, tam se prebuildovava.
    """

    @NEEDS_BUILD
    @NEEDS_CHROME
    def test_lists_are_not_rebuilt_every_tick(self):
        bundle = next((server.WEB_DIR / "static" / "assets").glob("index-*.js"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "static" / "assets").mkdir(parents=True)
            shutil.copy(bundle, root / "static" / "assets" / bundle.name)
            (root / "index.html").write_text(
                HARNESS % {"bundle": f"/static/assets/{bundle.name}"},
                encoding="utf-8")
            snapshot = json.loads(
                (Path(__file__).parent / "fixtures" / "snapshot.json").read_text("utf-8"))
            monitor = ConstantMonitor(snapshot)
            feed = SnapshotFeed(monitor)
            with mock.patch.object(server, "WEB_DIR", root), \
                 mock.patch.object(server, "STATIC_DIR", root / "static"):
                srv = server.serve(monitor, feed, "127.0.0.1", 0)
                self.addCleanup(srv.server_close)
                threading.Thread(target=srv.serve_forever, daemon=True).start()
                html = dump_dom(srv.server_address[1], 200000)
                srv.shutdown()

        result = re.search(r'id="result"[^>]*>([^<]*)<', html)
        self.assertIsNotNone(result, "harness nedobehl - viz vystup vyse")
        text = result.group(1)
        # `n/a` znamena, ze se seznam vubec nevykreslil (prazdny snapshot) -
        # to je chyba fixture, ne chvalitebny vysledek.
        self.assertNotIn("n/a", text, text)
        self.assertIn("same=True,True,True,True", text, text)
        self.assertEqual(re.search(r"mutations=(\d+)", text).group(1), "0",
                         f"seznamy se prebuildovavaji: {text}")
```

Fixture v tomhle testu **musí mít neprázdné seznamy** (alespoň jedno jádro,
jednu službu, jeden proces, jednu skupinu kontejnerů) — jinak by `same` bylo
`n/a` a test neměl co měřit. Ověř, že `tests/fixtures/snapshot.json` to splňuje;
když ne, rozšiř fixture v Tasku 4 (a přegeneruj ji).

- [ ] **Step 4: Fallback pin (proud umlkl, data musí téct dál)**

```python
class BrokenEventsHandler(server.Handler):
    """Server, ktery na /events odpovi chybou - maji nastoupit polling."""

    def do_GET(self):
        if self._path() == "/events":
            self._send_empty(500)
            return
        super().do_GET()


class PollingFallbackTest(unittest.TestCase):
    """Kdyz proud umlkne, dashboard nesmi tise zamrznout."""

    @NEEDS_BUILD
    @NEEDS_CHROME
    def test_page_still_updates_without_sse(self):
        base = json.loads(
            (Path(__file__).parent / "fixtures" / "snapshot.json").read_text("utf-8"))
        counter = {"n": 0}

        class CountingMonitor:
            def snapshot(self):
                counter["n"] += 1
                # Cely snapshot z fixture, meni se jen cpu - castecny dict by
                # shodil render z jineho duvodu, nez ktery test meri.
                return {**base, "cpu": float(counter["n"])}

        monitor = CountingMonitor()
        feed = SnapshotFeed(monitor)
        with mock.patch.object(server, "Handler", BrokenEventsHandler):
            srv = server.serve(monitor, feed, "127.0.0.1", 0)
        self.addCleanup(srv.server_close)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        port = srv.server_address[1]

        first = dump_dom(port, 4000)
        later = dump_dom(port, 20000)
        self.assertNotEqual(_cpu_value(first), _cpu_value(later),
                            "stranka se bez /events neaktualizovala")
        srv.shutdown()
```

`_cpu_value(html)` = `re.search(r'id="cpu"[^>]*>([^<]*)', html)` a vrátí
skupinu 1 (nebo `None`).

**Ovšem pozor:** `mock.patch.object(server, "Handler", …)` působí jen na
`server.serve()` v době volání — a ta `Handler` čte z modulu, takže patch
**před** `serve()` zabere. Ověř to měřením (test musí být zelený, a když
patch odstraníš, musí spadnout), a co jsi naměřil, napiš do hlášení. Kdyby
`serve()` handler bral jinak, uprav `serve()` v `server.py` tak, aby šel
handler předat parametrem — ne obcházet testem.

- [ ] **Step 5: Změřit, že piny běží (a že měří)**

```bash
cd frontend && npm run build && cd ..
python3 -m unittest tests.test_frontend_build -v
```
Expected: 3 testy `ok` (**ne** `skipped`).

A důkaz, že rebuild pin něco měří: spusť tentýž test proti **dnešnímu**
`sysmon` frontendu (dočasně zkopíruj `../sysmon/static/*` +
`../sysmon/templates/index.html` do `sysmon_app/web/` — a po měření je zase
přepiš buildem). Očekávej **FAIL** na `mutations=` s nenulovým číslem, protože
starý frontend seznamy každý tik přebudovává. Výstup zapiš do hlášení — je to
jediný důkaz, že pin není planý.

- [ ] **Step 6: Commit**

```bash
git add tests/test_frontend_build.py
git commit -m "testy: piny na build bez internetu, prebuildovavani seznamu a fallback bez SSE

Tri veci, ktere jednotkove testy neumi: build netahne nic z internetu, seznamy
se s tiky neprebuildovavaji (meri se childList mutace a identita uzlu pres
harness stranku - pocet uzlu by zustal stejny i pri prebuildovani, proto se
nemeri), a kdyz /events umlkne, stranka se aktualizuje pollingem. Bez buildu
nebo Chromu se pin preskoci - a v hlaseni je videt, jestli bezel."
```

---

### Task 10: README po fázi 2

**Goal:** README nelže: build je krok před spuštěním, frontend už není kopie ze
`sysmonu` a mrtvá tlačítka neexistují.

**Files:**
- Modify: `README.md`

**Acceptance Criteria:**
- [ ] Sekce o spuštění uvádí **`npm ci && npm run build` ve `frontend/`** jako
      krok před `python3 -m sysmon_app`, a co se stane, když se vynechá
      (česká věta s návodem)
- [ ] Sekce o dočasném frontendu je přepsaná: `web/` je **build** (v
      `.gitignore`), zdroj je ve `frontend/`, nikoli kopie ze `sysmonu`
- [ ] Věty o mrtvých tlačítkách a o titulku „Sysmon" jsou pryč (už neplatí)
- [ ] Přibyla zmínka o tom, že data tečou přes `/events` a že UI má pojistku
- [ ] Žádné tvrzení v README se nedá vyvrátit (každé ověř spuštěním)
- [ ] Odkaz na `docs/superpowers/specs/2026-10-16-faze-2-frontend-design.md`

**Verify:** každý příkaz z README spuštěný doslova projde; `grep -n "kopie"
README.md` a `grep -n "mrtvá\|token" README.md` → jen to, co pořád platí

**Steps:**

- [ ] **Step 1: Přepsat sekce „Spuštění démona", „Testy" a „Dočasný frontend"**

Dnešní text (viz `README.md:9-20`, `:69-99`) mluví o kopii ze `sysmonu`.
Nová podoba musí odpovídat tomu, co produkt opravdu dělá — včetně toho, že bez
buildu démon skončí větou (Task 3) a že `--help` funguje dál.

- [ ] **Step 2: Ověřit každý příkaz doslova**

```bash
cd frontend && npm ci && npm run build && cd ..
python3 -m unittest discover -s tests -t .
python3 -m sysmon_app & sleep 3
curl -s -o /dev/null -w "%{http_code}\n" localhost:8430/
kill %1
```
Expected: vše projde tak, jak README tvrdí. Co neprojde, přepiš v README
(nepřepisuj realitu).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README po fazi 2 - build, zdrojak frontendu a co uz neplati"
```

---

### Task 11: End-to-end ověření fáze 2

**Goal:** Ověřit, že React frontend dává stejné karty jako `sysmon`, že telefon
se aktualizuje bez obnovení stránky, a naměřená čísla zapsat do plánu.

**Files:**
- Modify: `docs/superpowers/plans/2026-10-16-faze-2-frontend.md` (uzavření —
  **tenhle jeden soubor smí implementátor editovat**, protože je to jeho
  vlastní plán; nic jiného pod `docs/` ne)

**Acceptance Criteria:**
- [ ] `python3 -m unittest discover -s tests -t .` zelené **s buildem** (a testy
      z Tasku 9 opravdu běžely, ne skipped)
- [ ] Sada zelená **i bez buildu** (`mv sysmon_app/web /tmp/web-off`) — a je
      vidět, které testy se přeskočily
- [ ] Karty na 8430 odpovídají 8420 (screenshoty obou, prohlédnuté)
- [ ] `/stats` i `/events` na 8430 vydávají těchž 17 klíčů jako 8420
- [ ] Telefon (nebo `curl` z jiného stroje): stránka se aktualizuje bez
      obnovení a bez ručního zásahu
- [ ] Naměřená čísla a nálezy jsou v uzavření v plánu (commitem), ne jen
      v hlášení

**Verify:** příkazy níže + uzavření v plánu

**Steps:**

- [ ] **Step 1: Sada s buildem i bez**

```bash
python3 -m unittest discover -s tests -t . -v | tail -5
mv sysmon_app/web /tmp/web-off
python3 -m unittest discover -s tests -t . -v | tail -5
mv /tmp/web-off sysmon_app/web
```

- [ ] **Step 2: Oba produkty vedle sebe a screenshoty**

```bash
python3 ../sysmon/sysmon.py & python3 -m sysmon_app & sleep 3
for port in 8420 8430; do
  google-chrome-stable --headless --disable-gpu --no-sandbox --hide-scrollbars \
    --window-size=1400,2400 --virtual-time-budget=8000 \
    --screenshot=/tmp/f2-final-$port.png http://localhost:$port/
done
```
Screenshoty **prohlédnout** (karty, jejich pořadí, rozměry, popisky) a zapsat,
co se liší a proč (smí se lišit jen živé hodnoty).

- [ ] **Step 3: Kontrakt a proud**

```bash
curl -s localhost:8420/stats | python3 -c "import json,sys; print(sorted(json.load(sys.stdin)))"
curl -s localhost:8430/stats | python3 -c "import json,sys; print(sorted(json.load(sys.stdin)))"
curl -N --max-time 5 localhost:8430/events | grep -c "^data: "
```
Expected: shodné sady klíčů; proud vydá ~3 rámce za 5 s.

- [ ] **Step 4: Telefon**

Z jiného stroje v síti (nebo aspoň z `curl` proti LAN adrese):
`curl -s -o /dev/null -w "%{http_code}\n" http://<IP>:8430/` → 200.
V prohlížeči telefonu nechat stránku otevřenou a sledovat, že se čísla mění
**bez obnovení**.

- [ ] **Step 5: Ukončit a zapsat uzavření**

```bash
kill %1 %2
git add docs/superpowers/plans/2026-10-16-faze-2-frontend.md
git commit -m "plán: uzavření fáze 2 s naměřenými čísly"
```

Do uzavření patří: počet testů, výsledek screenshotového srovnání, co se
lišilo a proč, jestli Task 9 piny běžely, a co zůstalo jako vědomá mez.

---

## Hotovo znamená

1. `cd frontend && npm ci && npm run build` projde a vznikne `sysmon_app/web/`
   s `index.html` a `/static/assets/…`; build sám nikam netahá.
2. `python3 -m unittest discover -s tests -t .` je zelené **s buildem i bez
   něj** (bez buildu se build-závislé piny přeskočí, nic nespadne).
3. `python3 -m sysmon_app` servíruje React UI na 8430 a karty odpovídají
   `sysmonu` na 8420 (porovnáno screenshotem/DOM).
4. Na telefonu se data aktualizují **bez obnovení stránky** (SSE), a když proud
   umlkne, UI to ukáže místo aby tiše zamrzlo.
5. Mrtvá tlačítka a token nejsou v UI ani v kódu frontendu.
6. Prázdné `watch_ports` se čte jako „nesleduji žádné porty", ne jako výpadek.
7. Počet DOM uzlů v seznamech se s počtem tiků nemění (změřeno).
8. Odebrání klíče z kontraktu v Pythonu rozbije `npm run typecheck`.
9. `sysmon` je nedotčený (`git -C ../sysmon status --short` čistý).


