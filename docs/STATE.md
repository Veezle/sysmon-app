# Aktuální stav

- **Fáze 4 (balení a měření paměti) je hotová a mergnutá do `main`** —
  všech 5 tasků `completed`, end-to-end ověřeno a uzavřeno v plánu.
  Větev `faze-4-baleni` zůstává jako záchranná síť.
- **Výsledky fáze 4:** `.deb`, `.rpm`, AppImage i PKGBUILD s bundled
  démonem; instalovaná aplikace má `Name=Sysmon`, migruje autostart.
  Paměť okna: slope `web` −7,31 MB/h, delta −3,18 MB → ploché (60min běh,
  20min warmup; původní 5min protokol dal 15,39 MB/h). Celková RSS
  701,6 MB, démon 30,0 MB.
- **Rozhodnutí:** warmup 20 min schválen uživatelem 2026-10-25 (náběh
  WebKit heapu, ne leak); prahy 5 MB/h a 15 MB zůstávají.
- **Otevřené meze:** měření je jeden ruční běh (Arch, KDE Wayland);
  krátké běhy mají překryv mediánových oken; PID reuse není pinovaný;
  testy nepinují CSV hlavičku, návratové kódy ani zbývající defaulty
  (interval, duration, limity — warmup ano); souběžné CSV se přepisuje;
  tarball není v repu, `sha256sums=('SKIP')`, `license=custom`.
- **Další krok:** žádný; fáze 4 uzavřená. Nová práce začne novou větví.
- **Fáze 1–3 hotové** a mergnuté do `main`; detaily v `docs/historie.md`.
