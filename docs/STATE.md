# Aktuální stav

- **Fáze 4 běží** na větvi `faze-4-baleni`; hotové Tasky 1–2. Task 1
  (commity `598852e`, `4b5cec3`, `bda3541`): PyInstaller onedir démona,
  výchozí build v `debian:13`, `--host` pro Arch, deterministický výstup,
  `BUILD-INFO`, chybový běh nezničí poslední artefakt.
- **Task 2 hotový** (commity `29a7cd5`, `09db118`): bundled démon relativně
  k binárce, `productName = sysmon-app`, šablona drží `Name=Sysmon`,
  autostart se tiše přepíše z instalované cesty, respektuje AppImage
  (`APPIMAGE`) i vypnutý autostart; 53 Rust testů zelených.
- **Rozhodnutí fáze 4:** démon v kontejneru kvůli `GLIBC_2.44`; menu
  `Name=Sysmon`; paměť 60 min, slope ≤ 5 MB/h, delta ≤ 15 MB.
- **Další task:** Task 3 (`.deb`/`.rpm`/AppImage, Docker ověření).
  Plán a tracker: `docs/superpowers/plans/2026-10-17-faze-4-baleni.md`
  (+ `.tasks.json`; Tasky 1–2 `completed`, 3 `pending`).
- **Otevřené meze Tasku 2:** `Hidden = true` s mezerami se nerozpozná;
  migrovaný `.desktop` nemá `StartupWMClass`; `is_executable` kontroluje
  libovolný `x` bit; reálný bundling a asociace okna až v Tasku 3/5.
- **Fáze 1–3 hotové** a mergnuté do `main`; detaily v `docs/historie.md`.
