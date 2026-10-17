# Historie fází

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

**Fáze 2 (React frontend) hotová.** Návrh v
`docs/superpowers/specs/2026-10-16-faze-2-frontend-design.md`, plán po úlohách
v `docs/superpowers/plans/2026-10-16-faze-2-frontend.md`, průběh v `.tasks.json`
vedle plánu, pravidla pro tasky v plánu („Pravidla pro každý task"). Fáze 2 je
mergnutá do **`main`**; větve `faze-1-demon` a `faze-2-frontend` zůstávají jako
záchranná síť.
Hotový **Task 1** — sada se odpoutala od buildu: testy indexu a assetů čtou
fixture adresář, sada má **143 testů** a projde i bez `sysmon_app/web/` (tehdy
se build-závislé piny přeskočí). Hotový **Task 2** — `frontend/` (Vite 8.3.4 +
React 19.3.1 + TS 5.9.3) se buildí do `sysmon_app/web/`, který je v
`.gitignore`; stará kopie frontendu je z repa smazaná (`../sysmon` zůstává
referencí). Build servíruje démon beze změny rout (`/`, `/static/*`), dev
server proxyuje `/stats` a `/events` na 8430. Hotový **Task 3** — hashované
assety mají `immutable`, index a ikona `no-store`; chybějící build se hlásí
česky při startu (`rc=2`) i za běhu (503) a sada má **151 testů** a projde
i bez buildu (`OK (skipped=2)`). Hotový **Task 4** — `frontend/src/types/snapshot.ts`
popisuje kontrakt a `snapshot.contract.ts` ho pinuje proti fixture generované
Pythonem; sada má **153 testů** a `npm run typecheck` hlídá tvary (keyof
assertiony + degradovaný vzorek). Hotový **Task 5** — `useSnapshot` drží
snapshot: první data z `/stats`, pak SSE; po 4,5 s ticha přepne na polling
každých 1,5 s a stav `live: false`; `format.ts` portuje formátovací helpery.
Hotový **Task 6** — CSS ze `sysmonu` přenesené beze změny až na styly mrtvých
tlačítek (diff má přesně 5 hunků), hlavička a karty CPU/GPU/RAM jsou
`memo`ované a dostávají jen svůj řez; naměřeno **0 childList mutací** za 6 s
živého SSE. Mount point `#root` má `display: contents`, protože mřížka je na
`body`; bez toho by karty byly 1/12 široké. Hotový **Task 7** — karty baterie
(imperativní canvas mimo React render), sítě a disku. Recenze odhalila
**zděděnou vadu z `sysmonu`**: klíč překreslení grafu obsahoval jen délku
a relativní čas, takže po naplnění 24h historie (720 vzorků) se přestal měnit
a graf tiše zamrzl; opraveno podpisem hodnot (`902af03`). Naměřeno: 8
identických pollů → 1 kreslení, 7 různých historií → 7 kreslení, 0 DOM mutací
mezi snapshoty. Hotový **Task 8** — služby, procesy a Docker; token, akční
hlavičky a `/action/` z frontendu zmizely a v celém UI nejsou žádná tlačítka
(na 8420 jich `sysmon` má 8). Prázdné `watch_ports` se čte jako „Nesleduji
žádné porty“ s `#svc-count` = „—“; naměřeno 9 karet, 0 konzolových warningů
a 0 DOM mutací za 10 s konstantního snapshotu. Hotový **Task 9** —
`tests/test_frontend_build.py` pinuje build bez cizích originů, stabilitu
seznamů (0 childList mutací, tytéž uzly) a aktualizaci bez SSE; sada má
**156 testů** (3 piny běží s buildem a Chromem, bez nich se přeskočí).
Recenze odhalila, že fallback pin porovnával **dva samostatné běhy Chroma**,
takže prošel i s vypnutým pollingem; opraveno měřením v rámci jednoho
načtení (`first`/`later` + počet pollů). Hotový **Task 10** — README po fázi 2:
build (`npm ci && npm run build`) jako krok před spuštěním, chování bez buildu
(rc=2 i 503), SSE s pollingovou pojistkou, zdroj ve `frontend/`, build
v `.gitignore`, verze Node `^20.19.0 || >=22.12.0`; každý příkaz z README byl
spuštěn doslova. Hotový **Task 11** — end-to-end ověření fáze 2: sada
**156 testů** zelená s buildem (0 skipped, tři piny Tasku 9 běžely) i bez něj
(`OK (skipped=5)`); screenshoty obou portů (1400×2257, 9 karet) mají shodné
popisky, pořadí i geometrii a liší se jen živými hodnotami a akčními tlačítky
(záměr Tasku 8); `/stats` i první rámec `/events` vydávají stejných 17 klíčů
jako 8420; živá aktualizace bez obnovení naměřena v jedné CDP session přes LAN
(`esFrames` 4 → 11, `statsFetches` zůstal 1). Skutečný telefon nebyl po ruce —
LAN cesta je změřená jen z téhož stroje. **Fáze 2 je hotová.**

## Fáze 3 (Tauri obal) — průběh

**Fáze 3 (Tauri obal) běží.** Návrh v
`docs/superpowers/specs/2026-10-17-faze-3-tauri-design.md`, plán po úlohách
v `docs/superpowers/plans/2026-10-17-faze-3-tauri.md`, průběh v `.tasks.json`
vedle plánu. Pracuje se na větvi **`faze-3-tauri`**. Hotový **Task 1** —
`src-tauri/` (Tauri 2 bez vlastního frontendu, okno ukazuje na 8430) se
zbuildí a otevře dashboard; 5 testů titulku, `Cargo.lock` verzovaný,
`src-tauri/target/` a `src-tauri/gen/` ignorované. Hotový **Task 2** —
sidecar: aplikace spustí démona, jen když 8430 neposlouchá, předá mu
explicitní `--port 8430`, čeká na readiness TCP connectem a vlastněného
démona drží přes `PR_SET_PDEATHSIG` (kontrola proti PIDu rodiče, ne
proti 1 — `systemd --user` je subreaper); 10 testů, 5/5 `kill -9` → port
volný, cizí démon přežije. Hotový **Task 3** — dozor: pád vlastněného
démona restartuje po 1/2/4 s, čtvrtý pád otevře dialog „Zkusit znovu /
Ukončit“, `rc=2` se nerestartuje a ukáže stderr; neodpovězený dialog po
300 s proces ukončí; 12 testů, restart naměřen za 1,1–4,2 s podle pokusu.
Hotový **Task 4** — tray (SNI `Title="Sysmon"`, menu „Otevřít dashboard“ /
„Ukončit“), zavření okna schová do traye a „Ukončit“ zastaví aplikaci
i vlastněného démona; v prostředí bez StatusNotifier watchera se tray
nevytvoří a zavření okna aplikaci ukončí; 13 testů, build bez warningů.
Hotový **Task 5** — autostart: první běh nabídne „Spouštět Sysmon při
přihlášení?“ (Ano/Ne), „Ano“ zapíše `.desktop` s `--hidden` a marker
zabrání opakování; `--hidden` startuje bez okna (bez traye se okno ukáže);
dvouvrstvý escape cest ověřen GLibem, selhání zápisu marker nezapíše
a nabídka se zopakuje; **33 testů**, build i clippy čisté.
Hotový **Task 6** — jedna instance: `tauri-plugin-single-instance` je první
v řetězu, druhé spuštění předá argumenty existující instanci, ta zviditelní okno
a druhá skončí (rc=0 za 56–65 ms); naměřeno 1 proces, 1 listener, 1 démon,
`--hidden` okno se po druhém spuštění objeví v KWin; mutant bez pluginu
nekončí (2 procesy). Vědomá mez: druhá instance spuštěná během startu první
(okno ještě neexistuje) tiše nic nezviditelní. **33 testů**, build i clippy
čisté. **Další na řadě je Task 7:** README po fázi 3.

## Poučení o předlohách v plánu

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
