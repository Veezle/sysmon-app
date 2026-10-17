# Aktuální stav

- **Fáze 3 (Tauri obal) je hotová** — všech 8 tasků `completed`, end-to-end
  ověřeno a uzavřeno v plánu (commity `ae95b2d` + `d6224e2`).
- **Další krok:** fáze 4 (balení a měření paměti) — zatím jen v návrhu,
  žádné tasky v trackeru. Plán fáze 3:
  `docs/superpowers/plans/2026-10-17-faze-3-tauri.md`; stav tasků
  v `2026-10-17-faze-3-tauri.md.tasks.json` vedle plánu.
- **Otevřené vědomé meze fáze 3:** autostart `.desktop` míří na vývojovou
  cestu `target/debug/sysmon-app` a nemá `Path=`, takže po přihlášení
  nenajde démona ze zdrojů, pokud už neběží; fyzický levý klik na tray
  a fokus po druhé instanci nebyly změřené (ručně ověří uživatel); bez
  StatusNotifier hosta se tray nevytvoří a zavření okna aplikaci ukončí.
- **Fáze 1 (démon) a fáze 2 (frontend) jsou hotové**; detaily v
  `docs/historie.md`.
- **Titulek je rozhodnutý ve fázi 3:** uživatelský název zůstává `Sysmon`
  (menu i titulek stránky), `sysmon-app` je technický název binárky a balíčku;
  `frontend/index.html` se nemění.
