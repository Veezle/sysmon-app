# Fáze 4: Balení a měření paměti — návrh

Navazuje na `2026-10-15-sysmon-app-design.md` (kapitoly „Fáze", „Rizika"
a „Hotovo znamená") a na hotovou fázi 3
(`2026-10-17-faze-3-tauri-design.md`). Ta končí u vývojového obalu: démon se
spouští ze zdrojů, `.desktop` míří do `target/debug` a paměť okna není
změřená. Tenhle dokument rozhoduje, **jak** se z toho stane nainstalovatelná
aplikace a co je na konci fáze 4 ověřitelné.

## Cíl a rozsah

Dodat čtyři věci:

1. **Démon jako samostatná binárka** — PyInstaller onedir, takže instalace
   nepotřebuje systémový Python ani `psutil`.
2. **Instalátory** — `.deb`, `.rpm`, AppImage přes Tauri bundler a `PKGBUILD`
   pro Arch. Instalované cesty nahradí vývojové.
3. **Migraci autostartu** — `.desktop` z fáze 3 se při prvním běhu instalované
   aplikace tiše přepíše na instalovanou binárku.
4. **Změřenou paměť okna** — 60 minut v reálném okně při tiku 1,5 s, s jasným
   prahem „plochá".

Mimo rozsah zůstává Windows a macOS, auto-update, podepisování, Flatpak, Snap,
systémová systemd služba a jakákoli změna kolektorů, frontendu nebo kontraktu
snapshotu.

## Rozhodnutí

1. **PyInstaller onedir, ne onefile.** Onedir startuje bez rozbalování do
   `/tmp` a chová se předvídatelně; onefile by při každém startu rozbaloval
   desítky MB. Build je samostatný skript, který předem vyžaduje hotový Vite
   build. **Portabilní artefakty se buildí v `debian:13` kontejneru**, protože
   build na Archu vloží do zamrzlých extension modulů `GLIBC_2.44` a binárka
   pak na Debianu 13 (glibc 2.41) neběží. `--host` přepínač dělá nativní build
   pro Arch (používá ho `PKGBUILD`).
2. **Démon se hledá relativně k binárce.** Instalovaný layout je
   `/usr/bin/sysmon-app` + `/usr/lib/sysmon-app/daemon/…`, takže
   `<exe>/../lib/sysmon-app/daemon/sysmon-app-daemon` funguje pro `.deb`,
   `.rpm`, AppImage mount i rozbalený strom a jde unit-testovat bez instalace.
   Pořadí hledání: běžící démon na 8430 → bundled daemon → vývojový
   `python3 -m sysmon_app` → česká chyba s oběma očekávanými cestami.
3. **`productName` je `sysmon-app`.** Tauri odvozuje jméno `.deb`/`.rpm`
   balíčku kebab-case z `productName`; s `Sysmon` by se balíček jmenoval
   `sysmon`, což odporuje rozhodnutí fáze 3 („`sysmon-app` je technický název
   balíčku"). Uživatelský název drží vlastní desktop šablona s `Name=Sysmon`;
   titulek okna i tray už mají „Sysmon" natvrdo v Rustu.
4. **AppImage používá stejnou desktop šablonu jako deb.** Ověřeno ve zdroji
   `tauri-bundler`: AppImage volá `debian::generate_data`, takže
   `bundle.linux.deb.desktopTemplate` se promítne i do AppImage.
5. **Závislosti se deklarují ručně.** Tauri 2 bundler už `ldd` neprochází
   (na rozdíl od v1); `depends` je prázdné, pokud se nenastaví. Deb dostane
   `libwebkit2gtk-4.1-0` a `libgtk-3-0t64`, RPM `webkit2gtk4.1` a `gtk3` —
   WebKit si transitivní závislosti dotáhne sám.
6. **Autostart se tiše přepíše, ale jen z instalované cesty.** Když `.desktop`
   existuje a jeho `Exec` míří jinam než aktuální binárka, přepíše se.
   Vývojový běh z `target/` autostart nepřepisuje zpět, aby si vývojář
   nerozbil instalovanou aplikaci.
7. **Měření paměti je součást akceptace, ne doplněk.** 60 min v reálném okně,
   prvních **20 min** se zahřívá a do trendu nevstupuje. Ploché = lineární
   trend RSS webview procesu ≤ **5 MB/h** a rozdíl mediánů prvních a
   posledních 10 min ≤ **15 MB**. Když to nevyjde, fáze 4 není hotová.
   > **Změna protokolu (2026-10-25):** první 60minutový běh s původním
   > 5minutovým warmupem dal slope `web` **15,39 MB/h**; data ale ukázala
   > náběh WebKit heapu, ne leak (lineární model vysvětlil jen 31 % rozptylu,
   > největší skoky byly záporné, Theil–Sen i mediány potvrdily náběh).
   > Se 20minutovým warmupem na témže běhu vychází slope **−7,31 MB/h**
   > a delta mediánů **−3,18 MB**. Warmup se proto prodlužuje na 20 min;
   > prahy 5 MB/h a 15 MB zůstávají.
8. **`cargo install tauri-cli` je buildový nástroj, ne závislost produktu.**
   Do repa se necommituje; README ho uvede jako prerekvizitu. Python strana
   zůstává bez nové runtime závislosti — PyInstaller žije v buildovém venv
   `packaging/.venv`, který je ignorovaný gitem.

## Architektura balení

### Instalovaný layout

Shodný pro všechny čtyři cesty:

```
/usr/bin/sysmon-app
/usr/lib/sysmon-app/daemon/sysmon-app-daemon
/usr/lib/sysmon-app/daemon/_internal/…          # PyInstaller onedir
/usr/share/applications/sysmon-app.desktop
/usr/share/icons/hicolor/{32x32,128x128}/apps/sysmon-app.png
```

Tauri resources jdou do `/usr/lib/<productName>/`, tedy
`/usr/lib/sysmon-app/`; mapování `packaging/daemon` → `daemon` dá zbytek.
AppImage má stejný strom pod `$APPDIR/usr/`.

### Build řetěz

```
frontend/  --npm run build-->  sysmon_app/web/
sysmon_app/ + web/  --PyInstaller onedir-->  packaging/daemon/sysmon-app-daemon
packaging/daemon/  --Tauri resources-->  src-tauri/target/release/bundle/{deb,rpm,appimage}/
```

`packaging/build-daemon.sh` je jediné místo, které zná PyInstaller. Ověří
existenci `sysmon_app/web/index.html` a podle režimu buď:

- **výchozí (portabilní):** zbuildí obraz z `packaging/Dockerfile.daemon`
  (`debian:13` + `python3-psutil` + pinovaný PyInstaller) a spustí v něm
  build jako uživatel hostitele; výstup jde do `packaging/daemon/`;
- **`--host` (nativní Arch):** použije venv s `--system-site-packages`, aby
  viděl systémový `psutil`, a zbuildí nativně. Tuhle cestu používá
  `PKGBUILD`.

Při chybějícím frontendu skončí stejnou českou větou jako démon (`rc=2`),
aby se chyba neprojevila až v instalátoru. Když výchozí režim nemá Docker,
skončí českou větou s návodem `--host`.

### Portabilita

Naměřeno na vývojovém stroji (`ldd 2.44`):

- Tauri binárka vyžaduje nejvýše `GLIBC_2.39`; Debian 13 i Fedora 42 (2.41)
  ji tedy unesou.
- **Hostitelský PyInstaller build na Archu v Debianu 13 selže**:
  bundlovaný `math.cpython-314-x86_64-linux-gnu.so` vyžaduje `GLIBC_2.44`
  a Debian 13 má 2.41. Naměřeno, ne odhadnuto. Proto se démon buildí
  v `debian:13` kontejneru.
- Démon z kontejneru vyžaduje glibc podle Debianu 13; Arch (2.44) i Fedora 42
  (2.41) jsou novější, takže ho unesou. Debian 12 (2.36) je mimo podporu
  a README to řekne.

Kontejnerové ověření je součást plánu, ne předpoklad. `--host` build je
určený jen pro Arch a `PKGBUILD`; neslibuje portabilitu.

### Co balíček neobsahuje

Žádný systémový Python, `psutil`, Node ani Rust. PyInstaller nese interpreter
i `psutil`; Tauri binárka je staticky sestavená Rust aplikace. Runtime
závislosti jsou jen sdílené knihovny WebKitGTK/GTK, které deklaruje balíček.

## Tauri bundler

`src-tauri/tauri.conf.json` se mění takto:

- `productName`: `sysmon-app`, `mainBinaryName` zůstává `sysmon-app`.
- `bundle.active`: `true`; `targets`: `["deb", "rpm", "appimage"]`.
- `bundle.resources`: mapování `../packaging/daemon` → `daemon`.
- `bundle.shortDescription`: „Dashboard systémových metrik".
- `bundle.linux.deb.desktopTemplate` a `bundle.linux.rpm.desktopTemplate`
  na `../packaging/sysmon-app.desktop.template`.
- `bundle.linux.deb.depends`: `["libwebkit2gtk-4.1-0", "libgtk-3-0t64"]`.
- `bundle.linux.rpm.depends`: `["webkit2gtk4.1", "gtk3"]`.
- `bundle.linux.appimage.bundleMediaFramework`: `false`.
- `frontendDist` zůstává `http://127.0.0.1:8430/` — do balíčku se žádný
  React nevkládá.

Desktop šablona (`packaging/sysmon-app.desktop.template`) je Handlebars:

```ini
[Desktop Entry]
Categories={{categories}}
{{#if comment}}
Comment={{comment}}
{{/if}}
Exec={{exec}}
Icon={{icon}}
Name=Sysmon
Terminal=false
Type=Application
```

`Name=Sysmon` je literál; `Exec`, `Icon` a `Comment` dodá bundler. Soubor se
jmenuje `sysmon-app.desktop`, protože jméno souboru určuje `productName`.

## Hledání démona a migrace autostartu

### Sidecar

`sidecar::daemon_command()` dostane cestu k aktuálnímu exe a `cwd` a vrátí
jednu z variant:

1. **Bundled** — `exe.parent().parent()/lib/sysmon-app/daemon/sysmon-app-daemon`
   existuje a je spustitelný. Spouští se přímo, bez Pythonu, `cwd` se
   nevyžaduje.
2. **Zdrojový** — `cwd/sysmon_app/__main__.py` existuje. Spouští se
   `python3 -m sysmon_app` jako dosud.
3. **Chyba** — česká věta vypíše obě očekávané cesty.

Bundled varianta má přednost: instalovaná aplikace nikdy nesáhne po náhodném
`sysmon_app` v aktuálním adresáři. `PDEATHSIG`, readiness, dozor i restart
zůstávají beze změny.

### Autostart

`autostart::desktop_entry()` zůstává. Přibude čistá funkce:

```rust
pub fn should_rewrite(
    desktop: Option<&str>,
    current_exe: &Path,
    installed: bool,
) -> bool
```

- `desktop` je `None` → `false` (řeší stávající nabídka).
- `installed == false` → `false` (vývojový běh nic nepřepisuje).
- `desktop` neobsahuje `Exec=` s aktuální cestou → `true`.
- jinak `false`.

`installed` se v `main.rs` určí jako „cesta k exe neobsahuje komponentu
`target`". Přepis zachová marker; když zápis selže, marker se nemění a chyba
se jen zaloguje — nabídka se neopakuje, protože uživatel už jednou odpověděl.

## PKGBUILD

`packaging/arch/PKGBUILD`:

- `pkgname=sysmon-app`, `pkgver=0.1.0`, `pkgrel=1`, `arch=('x86_64')`.
- `depends=('webkit2gtk-4.1' 'gtk3')`.
- `makedepends=('rust' 'cargo' 'nodejs' 'npm' 'python')`.
- `source=("$pkgname-$pkgver.tar.gz")`; tarball se vytváří před buildem
  pomocí `git archive --prefix=sysmon-app-$pkgver/`.
- `build()` spustí `npm ci && npm run build`, `packaging/build-daemon.sh
  --host` a `cargo build --release` (bez Tauri bundleru — Arch nepotřebuje
  .deb a nepotřebuje Docker).
- `package()` nainstaluje přesně layout výše, včetně desktop souboru
  a ikon.
- Síť je potřeba při `npm ci`, `cargo fetch` a `pip install pyinstaller`;
  `makepkg` ji nezakazuje. Je to vědomá vlastnost zdrojového buildu, README
  to řekne.

Ověření je `makepkg` a kontrola obsahu balíčku; systémová instalace
`makepkg -si` se nedělá, aby test nezasáhl stroj.

## Měření paměti

`tools/measure_memory.py`, pouze stdlib:

- Najde kořenový proces (argument `--pid`, jinak podle názvu binárky),
  každých 10 s projde `/proc` a posčítá RSS potomků.
- Kategorie: `app` (Tauri), `web` (`WebKitWebProcess`), `network`
  (`WebKitNetworkProcess`), `daemon` (`sysmon-app-daemon` nebo
  `python3 -m sysmon_app`), `other`.
- Zapíše CSV (mimo git) a na stdout souhrn: počet vzorků, medián prvních
  a posledních 10 min, lineární trend v MB/h pro `web`, celkovou RSS na
  konci.
- Prvních 20 min se do trendu nezapočítává (původně 5 min; změna
  protokolu 2026-10-25, viz kritérium 7 výše).
- Návratový kód `0` = ploché, `1` = práh překročen, `2` = měření nešlo
  (proces zmizel, málo vzorků).
- Volby `--duration`, `--interval`, `--warmup`, `--csv`, `--slope-limit`,
  `--delta-limit`; výchozí hodnoty odpovídají akceptaci.

Měření proběhne v reálném okně na KDE Waylandu s viditelným dashboardem.
Zdrojový démon (vývojový běh) i bundled démon musí dávat stejný závěr; měří
se okno, ne démon, ale celkový strom se reportuje taky.

## Testy a ověření

**Rust unit testy** (`cargo test --manifest-path src-tauri/Cargo.toml`):

- hledání bundled démona: existuje/neexistuje, cesta z `target/debug`
  i z `/usr/bin`;
- `should_rewrite` pro všech pět stavů (žádný soubor, vývojová cesta, stejná
  cesta, jiná cesta, poškozený obsah);
- stávající testy autostartu a sidecaru zůstávají zelené.

**Python testy** zůstávají `python3 -m unittest discover -s tests -t .` —
původních 156 testů se nemění, protože se nemění chování démona. Task 5
přidává 20 testů měřicího nástroje (`tests/test_measure_memory.py`): jde
spustit s `--help`, matematika trendu a mediánů sedí na syntetických datech
a klasifikace procesů je pinovaná; celkem je sada **176 testů**.

**Kontejnerové ověření:**

- `debian:13`: `dpkg -i` balíčku, `apt-get -f install` pro závislosti,
  kontrola cest a spuštění `sysmon-app-daemon --port 18430` bez Pythonu;
  `curl /stats` a `/events`.
- `fedora:42`: totéž s `dnf install`.
- AppImage: `--appimage-extract`, kontrola stromu; spuštění na hostiteli
  s WebKitGTK (AppImage prerekvizitu neodebírá).

**Regrese:** `cargo build`, `cargo test`, `npm run typecheck`, Python sada
176 testů, `git -C ../sysmon status --short` čistý.

## Rizika a vědomé meze

- **Stahování v Dockeru.** Obrazy i závislosti se tahají ze sítě. Když síť
  není, .deb/.rpm se ověří jen rozbalením a do uzavření se to zapíše jako
  vědomá mez; nesmí se to vydávat za instalaci.
- **AppImage si WebKitGTK veze sám** (linuxdeploy zabalí i webview), takže
  systémový `webkit2gtk-4.1` nepotřebuje; je ale zbuilděný na Archu, takže
  jeho knihovny vyžadují glibc 2.44 — na starších distribucích se nespustí.
- **GlIBC 2.39+ pro `.deb`/`.rpm`.** Debian 12 a starší nejsou podporované.
  Není to vada, je to hranice daná buildem Tauri binárky na Archu a démona
  v Debianu 13.
- **Docker je buildová prerekvizita portabilních balíčků.** Bez něj jde jen
  `--host` build pro Arch, který se na jiných distribucích nespustí. README
  to řekne; `PKGBUILD` Docker nepotřebuje.
- **PyInstaller a Python 3.14.** Pinovaná verze musí 3.14 podporovat; když
  ne, build skript to řekne hned na začátku, ne až u zákazníka.
- **Autostart přepisuje jen `.desktop`, který vypadá jako náš.** Cizí nebo
  ručně upravený soubor se přepíše taky — uživatel už jednou souhlasil
  a soubor patří produktu. Je to vědomá volba, ne přehlédnutí.
- **Změna `productName` mění jméno balíčku a resource adresáře.** Všechny
  cesty v kódu se odvozují od `productName`/exe, ne od starého `Sysmon`;
  testy to pinují.
- **Měření paměti je ruční a 60minutové.** Nedá se zrychlit bez ztráty
  vypovídací hodnoty. Opakuje se při regresi, nezkracuje se.

## Co fáze 4 nedělá

Windows, macOS, auto-update, podepisování balíčků, Flatpak, Snap, systémovou
systemd službu, změny kolektorů, změny kontraktu snapshotu, změny frontendu
a nové routy. Démon zůstává jen GET `/`, `/static/*`, `/stats` a `/events`.

## Hotovo znamená

1. `packaging/build-daemon.sh` zbuildí onedir démona, který v `debian:13`
   bez systémového Pythonu obslouží `/stats` i `/events`.
2. `cargo tauri build` vyrobí `.deb`, `.rpm` a AppImage; `.deb` se nainstaluje
   v čistém `debian:13` a `.rpm` v `fedora:42`.
3. Instalovaná aplikace spustí bundled démona, okno ukáže 9 karet a telefon
   se připojí na 8430.
4. Autostart z fáze 3 se při prvním běhu instalované aplikace přepíše na
   instalovanou binárku; vývojový běh ho nepřepíše zpět.
5. `PKGBUILD` projde `makepkg` a balíček obsahuje stejný layout.
6. Paměť okna je plochá podle prahu 5 MB/h / 15 MB při 60minutovém běhu
   s 20minutovým warmupem a čísla jsou zapsaná v plánu a README.
7. `cargo test`, Python sada (176 testů) a `npm run typecheck` projdou;
   `../sysmon` je čistý.
