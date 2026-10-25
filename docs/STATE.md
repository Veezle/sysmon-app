# Aktuální stav

- **Fáze 4 běží** na větvi `faze-4-baleni`; hotové Tasky 1–4.
- **Task 4 hotový** (commity `808eff0`, `5d43531`): `packaging/arch/PKGBUILD`
  vyrobí `sysmon-app-0.1.0-1-x86_64.pkg.tar.zst` s binárkou, bundled
  démonem, desktopem (`Name=Sysmon`, `StartupWMClass`) a ikonami; `depends`
  obsahují `webkit2gtk-4.1`, `gtk3` a `libayatana-appindicator`; démon
  z rozbaleného balíčku odpoví na `/stats`.
- **Rozhodnutí:** build je soběstačný — `build-daemon.sh` snese chybějící
  git (`commit=unknown`) a izolovaný `BUILDDIR` build prošel; tarball se
  generuje ručně s výlukami (`.claude`, `__pycache__`, `sysmon_app/web`,
  balíčky); zásah do `build-daemon.sh` byla výjimka vynucená nálezem.
- **Otevřené problémy:** před publikací doplnit `sha256sums`
  (`makepkg -g`); `license=custom` bez licenčního souboru; tarball není
  v repu, takže z čistého klonu `makepkg` neproběhne; na hostiteli zůstává
  root-owned `/nonexistent.deb` (`sudo rmdir /nonexistent.deb`).
- **Další task:** Task 5 (měření paměti, README, end-to-end). Plán a
  tracker: `docs/superpowers/plans/2026-10-17-faze-4-baleni.md`
  (+ `.tasks.json`; Tasky 1–4 `completed`, 5 `pending`).
- **Fáze 1–3 hotové** a mergnuté do `main`; detaily v `docs/historie.md`.
