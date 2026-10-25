# Aktuální stav

- **Fáze 4 běží** na větvi `faze-4-baleni`; hotové Tasky 1–3.
- **Task 3 hotový** (commity `b22aed3`, `d798b13`): `cargo tauri build`
  vyrobil `.deb`, `.rpm` a AppImage; `packaging/verify-package.sh` je
  nainstaluje v `debian:13`/`fedora:42`, ověří strom i `Name=Sysmon`
  a spustí bundled démona na `/stats`; AppImage ověřen extrakcí.
- **Rozhodnutí:** ověřování běží celé uvnitř kontejneru (`docker exec curl`,
  bez `-p`), takže se `/stats` nevystavuje na LAN a nekoliduje s host
  portem; vstup se kontroluje `[ -f ]` před `docker -v`; neblokující
  nálezy recenzí jsou v uzavření Tasku 3 v plánu.
- **Otevřené problémy:** na hostiteli zůstal root-owned prázdný
  `/nonexistent.deb` z testu recenzenta — smazat `sudo rmdir
  /nonexistent.deb`.
- **Další task:** Task 4 (PKGBUILD). Plán a tracker:
  `docs/superpowers/plans/2026-10-17-faze-4-baleni.md` (+ `.tasks.json`;
  Tasky 1–3 `completed`, 4 `pending`).
- **Fáze 1–3 hotové** a mergnuté do `main`; detaily v `docs/historie.md`.
