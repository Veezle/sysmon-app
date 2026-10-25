# Aktuální stav

- **Fáze 4 hotová** na větvi `faze-4-baleni`; Tasky 1–5 `completed`.
- **Task 5 hotový** (commity `9d12f6c`, `ef1d6b1`, `6984731`, `9791443`):
  `tools/measure_memory.py` (stdlib), 20 testů (celkem 176), README,
  hodinové měření v reálném okně. Výsledek: slope `web` −7,31 MB/h
  a delta −3,18 MB → ploché; celková RSS 701,6 MB, démon 30,0 MB.
- **Rozhodnutí:** protokol měření má 20min warmup (původních 5 min dalo
  15,39 MB/h; data ukázala náběh WebKit heapu, ne leak). Uživatel schválil
  změnu 2026-10-25; prahy 5 MB/h a 15 MB zůstávají a původní číslo je
  v README, plánu i specu.
- **Otevřené meze:** měření je jeden ruční běh (Arch, KDE Wayland);
  krátké běhy mají překryv mediánových oken; PID reuse není pinovaný;
  testy nepinují CSV/rc/defaulty; souběžné CSV se přepisuje; tarball
  není v repu, `sha256sums=('SKIP')`, `license=custom`; hostitel má
  root-owned `/nonexistent.deb` (`sudo rmdir`).
- **Další krok:** sloučení `faze-4-baleni` do `main` (mimo task workflow).
- **Fáze 1–3 hotové** a mergnuté do `main`; detaily v `docs/historie.md`.
