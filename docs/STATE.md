# Aktuální stav

- **Fáze 3 (Tauri obal) běží** na větvi `faze-3-tauri`.
- **Poslední hotový task:** Task 7 (README po fázi 3), commity `0fb719a`
  a `de19213` — README popisuje okno, tray, autostart, vědomé meze
  a oddělení fáze 3/4.
- **Další task:** Task 8 (end-to-end ověření fáze 3). Zadání je v plánu
  `docs/superpowers/plans/2026-10-17-faze-3-tauri.md`; stav tasků (zdroj
  pravdy) v `2026-10-17-faze-3-tauri.md.tasks.json` vedle plánu.
- **Otevřený problém (vědomá mez):** `.desktop` z autostartu nemá `Path=`,
  takže po přihlášení aplikace nenajde démona ze zdrojů, pokud už neběží.
  README to přiznává; náprava vyžaduje změnu `autostart.rs` mimo Task 7.
- **Fáze 1 (démon) a fáze 2 (frontend) jsou hotové**; detaily v
  `docs/historie.md`.
- **Titulek je rozhodnutý ve fázi 3:** uživatelský název zůstává `Sysmon`
  (menu i titulek stránky), `sysmon-app` je technický název binárky a balíčku;
  `frontend/index.html` se nemění.
- **Fáze 4 (balení a měření paměti)** je zatím jen v návrhu.
