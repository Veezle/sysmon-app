# Aktuální stav

- **Fáze 4 běží** na větvi `faze-4-baleni`; Task 1 hotový (commity
  `598852e`, `4b5cec3`, `bda3541`): PyInstaller onedir démona. Výchozí build
  v `debian:13` (portabilní), `--host` nativně pro Arch; deterministický
  výstup, `BUILD-INFO`, chybový běh nezničí poslední artefakt. V `debian:13`
  bez Pythonu `/stats` funguje.
- **Rozhodnutí fáze 4:** `productName = sysmon-app` (balíček i resource
  adresář), menu `Name=Sysmon` přes desktop šablonu; démon se hledá relativně
  k binárce (`<exe>/../lib/sysmon-app/daemon/`); build démona v kontejneru
  kvůli `GLIBC_2.44`; autostart se tiše přepíše jen z instalované cesty;
  paměť 60 min, slope ≤ 5 MB/h, delta ≤ 15 MB.
- **Další task:** Task 2 (bundled démon, bundle config, migrace autostartu).
  Plán a tracker: `docs/superpowers/plans/2026-10-17-faze-4-baleni.md`
  (+ `.tasks.json`; Task 1 `completed`, 4 `pending`).
- **Otevřené meze Tasku 1:** souběžné buildy, čerstvost Vite buildu,
  hash-pin PyPI a digest `debian:13`; `BUILD-INFO` může nést commit
  předchozího buildu.
- **Fáze 1–3 hotové** a mergnuté do `main`; detaily v `docs/historie.md`.
