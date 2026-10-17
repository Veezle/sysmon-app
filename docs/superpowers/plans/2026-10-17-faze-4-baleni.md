# Fáze 4: Balení a měření paměti — implementační plán

> **Pro pracovníky-agenty:** povinný sub-skill:
> `superpowers-extended-cc:subagent-driven-development` (doporučeno), nebo
> `superpowers-extended-cc:executing-plans`. Kroky mají zaškrtávátka (`- [ ]`).

**Goal:** Zabalit hotový démon, frontend a Tauri obal do instalovatelné
aplikace (`.deb`, `.rpm`, AppImage, `PKGBUILD`), nahradit vývojové cesty
instalovanými a změřit paměť okna v reálném provozu.

**Architecture:** Démon se buildí PyInstallerem jako onedir do
`packaging/daemon/`; Tauri bundler ho zabalí jako resource do
`/usr/lib/sysmon-app/daemon/`. Obal ho hledá relativně ke své binárce
(`<exe>/../lib/sysmon-app/daemon/sysmon-app-daemon`), takže stejná cesta
funguje pro `.deb`, `.rpm`, AppImage i rozbalený strom. Vývojový režim
(`python3 -m sysmon_app` z kořene repa) zůstává záložní cestou.

**Tech Stack:** PyInstaller 6.22.3 (build venv), Tauri CLI 2 (build nástroj),
Tauri 2 bundler, Docker (`debian:13`, `fedora:42`), stdlib Python pro měření
paměti. Žádná nová runtime závislost Pythonu ani JS.

**Spec:** `docs/superpowers/specs/2026-10-17-faze-4-baleni-design.md`

**Tracker:** `2026-10-17-faze-4-baleni.md.tasks.json` vedle tohoto plánu.

---

## Předletová kontrola (2026-10-17)

Naměřeno na tomhle stroji, ať plán nestojí na předpokladech:

- **Python:** 3.14.8, `psutil` nainstalovaný, `pip` 26.2.1. PyInstaller
  v systému není — patří do `packaging/.venv`.
- **Node/npm:** Node 22.23.2; build frontendu funguje (fáze 2).
- **Rust:** cargo 1.95.0. `tauri-cli` není nainstalovaný; `cargo tauri`
  hlásí „no such command".
- **GUI:** KDE Wayland (`WAYLAND_DISPLAY=wayland-1`, `DISPLAY=:0`),
  `kwin_wayland` běží, `spectacle` je k dispozici.
- **WebKit:** `webkit2gtk-4.1 2.54.1` nainstalovaný (fáze 3).
- **Docker:** 29.9.1 běží. Obrazy `debian:13` a `fedora:42` se při prvním
  ověření stáhnou ze sítě.
- **glibc:** host 2.44; Tauri binárka vyžaduje nejvýše `GLIBC_2.39`,
  `libpython3.14` a `psutil` nejvýše `GLIBC_2.38`. Debian 13 i Fedora 42
  mají 2.41 → artefakty z Archu na nich poběží.
- **PyInstaller:** nejnovější 6.22.3; pinuje se v
  `packaging/requirements-build.txt`.
- **Démon:** `sysmon_app/web/` po fázi 2 existuje, Python sada je 156 testů
  OK, `../sysmon` je čistý.

### Prerekvizity před Taskem 1

```bash
cd frontend && npm ci && npm run build && cd ..
```

Build frontendu musí existovat dřív než PyInstaller; skript to kontroluje.

### Prerekvizita před Taskem 3

```bash
cargo install tauri-cli --version "^2" --locked
cargo tauri --version
```

Instalace trvá několik minut a potřebuje síť. Je to buildový nástroj, ne
závislost produktu; do repa se necommituje.

## Pravidla pro každý task

- Větev **`faze-4-baleni`**; nikdy se necommituje na `main`.
- Do `../sysmon` se nezasahuje — jen čte.
- `git add` **jen s explicitními cestami**, nikdy `-A` ani `.`.
- Implementátor needituje nic pod `docs/` (výjimka: Task 5 smí upravit
  `README.md` a připsat uzavření do tohoto plánu) ani soubory jiných tasků.
- **Žádné nové runtime závislosti.** PyInstaller jen do
  `packaging/.venv`; `tauri-cli` jen jako `cargo install`. Rust závislosti
  se nemění.
- `cargo` příkazy vždy s `--manifest-path src-tauri/Cargo.toml`.
- Příkazy spouštěj s minimálním výstupem (`--quiet`, `| tail -n 40`); při
  chybě ukaž jen relevantní část.
- Build artefakty (`packaging/.venv/`, `packaging/build/`,
  `packaging/daemon/`, `packaging/daemon-build/`, `packaging/arch/src/`,
  `packaging/arch/pkg/`, `src-tauri/target/`) nejsou v gitu.
- Docker ověření potřebuje síť. Když síť není, zapiš to jako vědomou mez
  a balíček ověř jen rozbalením; nevydávej to za instalaci.
- GUI a 60minutové měření patří až do Tasku 5.

---

### Task 1: PyInstaller onedir démona

**Goal:** `packaging/build-daemon.sh` zbuildí `sysmon-app-daemon` jako onedir
se zabudovaným Vite buildem, a ten funguje bez systémového Pythonu.

**Files:**
- Create: `packaging/requirements-build.txt`,
  `packaging/build-daemon.sh`
- Modify: `.gitignore`

**Acceptance Criteria:**
- [ ] `packaging/build-daemon.sh` skončí `0` a vytvoří
      `packaging/daemon/sysmon-app-daemon` + `packaging/daemon/_internal/`
- [ ] bez `sysmon_app/web/index.html` skript skončí `2` s českou větou
      a návodem `npm ci && npm run build`
- [ ] binárka obslouží `/stats` (16+ klíčů), `/` (SPA) i `/events`
- [ ] binárka běží v `debian:13` kontejneru, kde není žádný Python
- [ ] `packaging/.venv/`, `packaging/build/`, `packaging/daemon/`
      nejsou v gitu

**Verify:** `packaging/build-daemon.sh` + curl na 18430 + Docker bez Pythonu

**Steps:**

- [ ] **Step 1: Zapiš pinovanou verzi**

`packaging/requirements-build.txt`:

```text
pyinstaller==6.22.3
```

- [ ] **Step 2: Zapiš build skript**

`packaging/build-daemon.sh` (musí být spustitelný, `chmod +x`):

```bash
#!/usr/bin/env bash
# Zbuildi demona jako PyInstaller onedir do packaging/daemon/.
# Vyžaduje hotovy Vite build (sysmon_app/web/index.html); sit je potreba
# jen pri prvnim vytvoreni venv a instalaci pinovaneho PyInstalleru.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -f sysmon_app/web/index.html ]; then
    echo "Frontend není zbuilděný (sysmon_app/web/index.html neexistuje)." >&2
    echo "Spusť v adresáři frontend:" >&2
    echo "    npm ci && npm run build" >&2
    exit 2
fi

if [ ! -x packaging/.venv/bin/python ]; then
    python3 -m venv packaging/.venv
fi
packaging/.venv/bin/python -m pip install --quiet --disable-pip-version-check \
    -r packaging/requirements-build.txt

rm -rf packaging/build packaging/daemon-build packaging/daemon
mkdir -p packaging/build
packaging/.venv/bin/python -m PyInstaller \
    --noconfirm --clean --onedir \
    --name sysmon-app-daemon \
    --distpath packaging/daemon-build \
    --workpath packaging/build \
    --specpath packaging/build \
    --paths "$ROOT" \
    --add-data "sysmon_app/web:sysmon_app/web" \
    sysmon_app/__main__.py

mv packaging/daemon-build/sysmon-app-daemon packaging/daemon
rmdir packaging/daemon-build
test -x packaging/daemon/sysmon-app-daemon
echo "Hotovo: packaging/daemon/sysmon-app-daemon"
```

- [ ] **Step 3: Doplň `.gitignore`**

Na konec `.gitignore` přidej:

```text
packaging/.venv/
packaging/build/
packaging/daemon/
packaging/daemon-build/
packaging/arch/src/
packaging/arch/pkg/
packaging/arch/*.tar.gz
```

- [ ] **Step 4: Ověř chybovou cestu**

Dočasně přesuň build frontendu a spusť skript:

```bash
mv sysmon_app/web /tmp/web-backup
packaging/build-daemon.sh; echo "rc=$?"
mv /tmp/web-backup sysmon_app/web
```

Očekávej `rc=2` a větu `Frontend není zbuilděný …`.

- [ ] **Step 5: Zbuildi a ověř běžící démon**

```bash
packaging/build-daemon.sh
packaging/daemon/sysmon-app-daemon --port 18430 &
daemon_pid=$!
sleep 2
curl -fsS http://127.0.0.1:18430/stats | python3 -c '
import json, sys
d = json.load(sys.stdin)
keys = [k for k in d if k != "cpu_temp"]
assert len(keys) == 16, keys
print("stats OK:", len(keys), "klíčů")
'
curl -fsS http://127.0.0.1:18430/ | grep -q '<div id="root">' && echo "SPA OK"
asset=$(curl -fsS http://127.0.0.1:18430/ | grep -o '/static/assets/index-[^"]*\.js' | head -1)
test -n "$asset" && curl -fsS "http://127.0.0.1:18430$asset" >/dev/null && echo "asset OK"
curl -fsS -N -m 3 http://127.0.0.1:18430/events | head -c 20 || true
kill "$daemon_pid"
```

- [ ] **Step 6: Ověř, že nepotřebuje systémový Python**

```bash
docker run --rm -d --name sysmon-daemon-check \
  -p 18430:18430 \
  -v "$PWD/packaging/daemon:/daemon:ro" \
  debian:13 /daemon/sysmon-app-daemon --port 18430
sleep 2
docker exec sysmon-daemon-check sh -c 'command -v python3 || echo "python3 není"'
curl -fsS http://127.0.0.1:18430/stats >/dev/null && echo "debian:13 OK"
docker rm -f sysmon-daemon-check
```

Kontejner `debian:13` žádný Python nemá; přesto musí `/stats` odpovědět.

- [ ] **Step 7: Commitni**

```bash
git add packaging/requirements-build.txt packaging/build-daemon.sh .gitignore
git commit -m "fáze 4: PyInstaller onedir démona"
```

---

### Task 2: Bundled démon, bundle config a migrace autostartu

**Goal:** Obal najde zabaleného démona relativně ke své binárce, `tauri.conf`
umí bundling a instalovaná aplikace tiše přepíše zastaralý autostart.

**Files:**
- Modify: `src-tauri/tauri.conf.json`, `src-tauri/src/sidecar.rs`,
  `src-tauri/src/autostart.rs`, `src-tauri/src/main.rs`
- Create: `packaging/sysmon-app.desktop.template`

**Acceptance Criteria:**
- [ ] `cargo test --manifest-path src-tauri/Cargo.toml` projde; nové testy
      pinují hledání bundled démona i `should_rewrite`
- [ ] `cargo build --release --manifest-path src-tauri/Cargo.toml` projde
- [ ] z vývojového běhu (`cargo run`) se stále spouští
      `python3 -m sysmon_app`
- [ ] ze simulovaného instalovaného stromu
      (`/tmp/sysmon-install/usr/bin/sysmon-app` +
      `/tmp/sysmon-install/usr/lib/sysmon-app/daemon/`) se spustí
      **bundled** démon a `/stats` odpoví
- [ ] existující `.desktop` s vývojovou cestou se při běhu z instalované
      cesty přepíše; z `target/` se nepřepisuje
- [ ] `tauri.conf.json` má `productName: sysmon-app`, `bundle.active: true`,
      targets `deb`, `rpm`, `appimage` a resources na `packaging/daemon`

**Verify:** `cargo test` + `cargo build --release` + simulovaný instalovaný
strom + přepis `.desktop`

**Steps:**

- [ ] **Step 1: Uprav `src-tauri/tauri.conf.json`**

```json
{
  "$schema": "https://schema.tauri.app/config/2",
  "productName": "sysmon-app",
  "version": "0.1.0",
  "identifier": "cz.sysmonapp.desktop",
  "mainBinaryName": "sysmon-app",
  "build": {
    "frontendDist": "http://127.0.0.1:8430/"
  },
  "app": {
    "windows": [],
    "withGlobalTauri": false,
    "security": {
      "csp": null
    }
  },
  "bundle": {
    "active": true,
    "targets": ["deb", "rpm", "appimage"],
    "icon": [
      "icons/128x128.png",
      "icons/32x32.png"
    ],
    "shortDescription": "Dashboard systémových metrik",
    "resources": {
      "../packaging/daemon": "daemon"
    },
    "linux": {
      "deb": {
        "depends": ["libwebkit2gtk-4.1-0", "libgtk-3-0t64"],
        "desktopTemplate": "../packaging/sysmon-app.desktop.template"
      },
      "rpm": {
        "depends": ["webkit2gtk4.1", "gtk3"],
        "desktopTemplate": "../packaging/sysmon-app.desktop.template"
      },
      "appimage": {
        "bundleMediaFramework": false
      }
    }
  }
}
```

Poznámka: `productName` je záměrně `sysmon-app`, protože Tauri z něj dělá
kebab-case jméno `.deb`/`.rpm` balíčku i název resource adresáře
`/usr/lib/sysmon-app/`. Uživatelské jméno „Sysmon“ drží šablona níže.

- [ ] **Step 2: Zapiš desktop šablonu**

`packaging/sysmon-app.desktop.template`:

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

- [ ] **Step 3: Přepiš hledání démona v `sidecar.rs`**

Přidej nad `ensure_daemon` (a použij v `ensure_daemon` i v `supervise`):

```rust
/// Odkud se démon spustí. Rozhodnutí se dělá jednou při startu; respawn
/// po pádu musí použít stejný zdroj, ne hledat znovu.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DaemonSource {
    /// Instalovaný PyInstaller onedir vedle binárky.
    Bundled(PathBuf),
    /// Vývojový `python3 -m sysmon_app` z kořene repa.
    Source(PathBuf),
}

/// Instalovaný layout je `/usr/bin/sysmon-app` +
/// `/usr/lib/sysmon-app/daemon/sysmon-app-daemon`; stejný vztah platí
/// v AppImage mountu i v rozbaleném stromu.
pub fn bundled_daemon_path(exe: &Path) -> PathBuf {
    exe.parent()
        .unwrap_or_else(|| Path::new(""))
        .join("..")
        .join("lib")
        .join("sysmon-app")
        .join("daemon")
        .join("sysmon-app-daemon")
}

pub fn resolve_daemon(exe: &Path, cwd: &Path) -> Result<DaemonSource, String> {
    let bundled = bundled_daemon_path(exe);
    if bundled.is_file() {
        return Ok(DaemonSource::Bundled(bundled));
    }
    if daemon_dir_ok(cwd) {
        return Ok(DaemonSource::Source(cwd.to_path_buf()));
    }
    Err(format!(
        "Nenašel jsem démona.\n\
         Hledal jsem:\n  {}\n  {} (s sysmon_app/__main__.py)\n\
         Nainstaluj balíček, nebo spusť aplikaci z kořene repa sysmon-app.",
        bundled.display(),
        cwd.display()
    ))
}
```

`spawn_daemon` změň na:

```rust
fn spawn_daemon(
    source: &DaemonSource,
    stderr: &Arc<Mutex<VecDeque<String>>>,
) -> Result<Child, String> {
    let parent_pid = std::process::id() as libc::pid_t;
    let mut cmd = match source {
        DaemonSource::Bundled(path) => {
            let mut c = Command::new(path);
            c.args(["--port", &PORT.to_string()]);
            c
        }
        DaemonSource::Source(cwd) => {
            let mut c = Command::new("python3");
            c.args(daemon_args()).current_dir(cwd);
            c
        }
    };
    cmd.stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::piped());

    // ... zbytek (pre_exec, spawn, stderr vlákno) zůstává beze změny.
}
```

V `ensure_daemon` nahraď kontrolu `daemon_dir_ok(&cwd)` voláním
`resolve_daemon(&exe, &cwd)`; `exe` získej přes
`std::env::current_exe()`. Zdroj předej do `start_supervisor` jako
`Arc<DaemonSource>` a v `supervise` ho použij pro každý respawn
(`spawn_daemon(&source, &stderr)`).

- [ ] **Step 4: Přidej funkce pro autostart**

Do `autostart.rs` přidej:

```rust
/// Instalovaná cesta neleží pod `target/`; vývojový build ano.
pub fn installed_exe(path: &Path) -> bool {
    !path
        .components()
        .any(|c| c.as_os_str() == "target")
}

/// Přepsat `.desktop`, jen když jsme instalovaní a Exec míří jinam.
/// `None` znamená, že soubor neexistuje — o nabídku se stará `maybe_offer`.
pub fn should_rewrite(
    desktop: Option<&str>,
    current_exe: &Path,
    installed: bool,
) -> bool {
    if !installed {
        return false;
    }
    let Some(content) = desktop else {
        return false;
    };
    let expected = format!("Exec={} --hidden", quote_exec(current_exe));
    !content.lines().any(|line| line == expected)
}

/// Tiše přepíše zastaralý `.desktop` (z fáze 3 mířil na target/debug).
/// Marker se nemění: uživatel už jednou odpověděl a nabídka se neopakuje.
pub fn migrate_desktop(installed: bool) {
    if !installed {
        return;
    }
    let desktop = desktop_path();
    let Ok(content) = fs::read_to_string(&desktop) else {
        return;
    };
    let Ok(exe) = std::env::current_exe() else {
        return;
    };
    if !should_rewrite(Some(&content), &exe, installed) {
        return;
    }
    if let Err(err) = fs::write(&desktop, desktop_entry(&exe)) {
        eprintln!("Autostart: {} nelze přepsat: {err}", desktop.display());
    }
}
```

V `main.rs` v `.setup()` před `autostart::maybe_offer(...)` zavolej:

```rust
let installed = std::env::current_exe()
    .map(|exe| autostart::installed_exe(&exe))
    .unwrap_or(false);
autostart::migrate_desktop(installed);
```

Přepis se dělá i při `--hidden`, protože autostart startuje právě tak.

- [ ] **Step 5: Přidej unit testy**

Do `sidecar.rs` (`#[cfg(test)] mod tests`) přidej testy:

```rust
#[test]
fn bundled_path_is_relative_to_exe() {
    assert_eq!(
        bundled_daemon_path(Path::new("/usr/bin/sysmon-app")),
        PathBuf::from("/usr/bin/../lib/sysmon-app/daemon/sysmon-app-daemon")
    );
}

#[test]
fn bundled_daemon_wins_over_source() {
    let root = temp_dir("bundled");
    let exe = root.join("usr/bin/sysmon-app");
    let daemon = root.join("usr/lib/sysmon-app/daemon/sysmon-app-daemon");
    std::fs::create_dir_all(exe.parent().unwrap()).unwrap();
    std::fs::create_dir_all(daemon.parent().unwrap()).unwrap();
    std::fs::write(&exe, b"").unwrap();
    std::fs::write(&daemon, b"").unwrap();
    let cwd = root.join("repo");
    std::fs::create_dir_all(cwd.join("sysmon_app")).unwrap();
    std::fs::write(cwd.join("sysmon_app/__main__.py"), b"").unwrap();

    assert_eq!(
        resolve_daemon(&exe, &cwd).unwrap(),
        DaemonSource::Bundled(daemon)
    );
}

#[test]
fn source_is_used_when_no_bundle() {
    let root = temp_dir("source");
    let cwd = root.join("repo");
    std::fs::create_dir_all(cwd.join("sysmon_app")).unwrap();
    std::fs::write(cwd.join("sysmon_app/__main__.py"), b"").unwrap();
    let exe = root.join("usr/bin/sysmon-app");
    assert_eq!(
        resolve_daemon(&exe, &cwd).unwrap(),
        DaemonSource::Source(cwd)
    );
}

#[test]
fn missing_daemon_names_both_paths() {
    let root = temp_dir("missing");
    let exe = root.join("usr/bin/sysmon-app");
    let err = resolve_daemon(&exe, &root).unwrap_err();
    assert!(err.contains("sysmon-app-daemon"));
    assert!(err.contains("__main__.py"));
}
```

Do `autostart.rs` přidej:

```rust
#[test]
fn installed_exe_rejects_target() {
    assert!(installed_exe(Path::new("/usr/bin/sysmon-app")));
    assert!(!installed_exe(Path::new(
        "/home/u/repo/src-tauri/target/debug/sysmon-app"
    )));
    assert!(!installed_exe(Path::new(
        "/home/u/repo/src-tauri/target/release/sysmon-app"
    )));
}

#[test]
fn no_desktop_means_no_rewrite() {
    assert!(!should_rewrite(None, Path::new("/usr/bin/sysmon-app"), true));
}

#[test]
fn dev_run_never_rewrites() {
    let content = desktop_entry(Path::new("/usr/bin/sysmon-app"));
    assert!(!should_rewrite(
        Some(&content),
        Path::new("/home/u/repo/src-tauri/target/debug/sysmon-app"),
        false
    ));
}

#[test]
fn same_exe_is_left_alone() {
    let exe = Path::new("/usr/bin/sysmon-app");
    assert!(!should_rewrite(Some(&desktop_entry(exe)), exe, true));
}

#[test]
fn different_exe_is_rewritten() {
    let old = desktop_entry(Path::new("/home/u/repo/src-tauri/target/debug/sysmon-app"));
    assert!(should_rewrite(
        Some(&old),
        Path::new("/usr/bin/sysmon-app"),
        true
    ));
}

#[test]
fn garbage_is_rewritten() {
    assert!(should_rewrite(
        Some("tohle není .desktop\n"),
        Path::new("/usr/bin/sysmon-app"),
        true
    ));
}
```

Pomocnou `temp_dir(name)` už v `sidecar.rs` testech máš; pokud ne, zkopíruj
stejný tvar jako v `autostart.rs`.

- [ ] **Step 6: Ověř vývojový režim a simulovanou instalaci**

```bash
cargo test --manifest-path src-tauri/Cargo.toml
cargo build --release --manifest-path src-tauri/Cargo.toml

# simulovaný instalovaný strom
rm -rf /tmp/sysmon-install /tmp/sysmon-xdg
mkdir -p /tmp/sysmon-install/usr/bin /tmp/sysmon-install/usr/lib/sysmon-app
cp src-tauri/target/release/sysmon-app /tmp/sysmon-install/usr/bin/
cp -a packaging/daemon /tmp/sysmon-install/usr/lib/sysmon-app/daemon

cd /tmp
XDG_CONFIG_HOME=/tmp/sysmon-xdg /tmp/sysmon-install/usr/bin/sysmon-app --hidden &
app_pid=$!
sleep 4
ps -eo pid,ppid,cmd | grep 'sysmon-app-daemon' | grep -v grep
curl -fsS http://127.0.0.1:8430/stats >/dev/null && echo "bundled OK"
kill "$app_pid"
sleep 1
ss -ltn | grep ':8430' || echo "port volný"
```

Vývojový režim:

```bash
cd /home/veezle/Documents/GithubClones/sysmon-app
cargo run --manifest-path src-tauri/Cargo.toml &
app_pid=$!
sleep 4
ps -eo pid,ppid,cmd | grep 'python3 -m sysmon_app' | grep -v grep
kill "$app_pid"
```

- [ ] **Step 7: Ověř migraci autostartu**

```bash
mkdir -p /tmp/sysmon-xdg/autostart /tmp/sysmon-xdg/sysmon-app
touch /tmp/sysmon-xdg/sysmon-app/autostart-asked
cat > /tmp/sysmon-xdg/autostart/sysmon-app.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Sysmon
Comment=Dashboard systémových metrik
Exec=/home/veezle/Documents/GithubClones/sysmon-app/src-tauri/target/debug/sysmon-app --hidden
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
XDG_CONFIG_HOME=/tmp/sysmon-xdg /tmp/sysmon-install/usr/bin/sysmon-app --hidden &
app_pid=$!
sleep 4
kill "$app_pid"
grep -F 'Exec=/tmp/sysmon-install/usr/bin/sysmon-app --hidden' \
  /tmp/sysmon-xdg/autostart/sysmon-app.desktop
test -f /tmp/sysmon-xdg/sysmon-app/autostart-asked && echo "marker zůstal"
```

- [ ] **Step 8: Commitni**

```bash
git add src-tauri/tauri.conf.json src-tauri/src/sidecar.rs \
  src-tauri/src/autostart.rs src-tauri/src/main.rs \
  packaging/sysmon-app.desktop.template
git commit -m "fáze 4: bundle config, bundled démon a migrace autostartu"
```

---

### Task 3: Instalátory a kontejnerové ověření

**Goal:** `cargo tauri build` vyrobí `.deb`, `.rpm` a AppImage; `.deb`
a `.rpm` se nainstalují v čistých kontejnerech a jejich démon tam běží.

**Files:**
- Create: `packaging/verify-package.sh`
- Modify: `src-tauri/tauri.conf.json` (jen pokud bundler vyžaduje opravu
  resources nebo závislostí)
- Build outputs: `src-tauri/target/release/bundle/{deb,rpm,appimage}/`

**Acceptance Criteria:**
- [ ] `cargo tauri build --bundles deb,rpm,appimage` projde
- [ ] `.deb` se nainstaluje v `debian:13`; existuje
      `/usr/bin/sysmon-app`, `/usr/lib/sysmon-app/daemon/sysmon-app-daemon`,
      desktop soubor s `Name=Sysmon` a ikona
- [ ] `.rpm` se nainstaluje v `fedora:42` se stejnou kontrolou
- [ ] démon z nainstalovaného balíčku odpoví na `/stats` v obou kontejnerech
- [ ] AppImage po `--appimage-extract` obsahuje stejný strom a `Name=Sysmon`
- [ ] `packaging/verify-package.sh` je spustitelný a umí `deb` i `rpm`

**Verify:** `cargo tauri build` + `packaging/verify-package.sh deb …` +
`packaging/verify-package.sh rpm …` + AppImage extract

**Steps:**

- [ ] **Step 1: Nainstaluj Tauri CLI**

```bash
cargo install tauri-cli --version "^2" --locked
cargo tauri --version
```

Pokud instalace trvá nebo potřebuje síť, poznamenej to; je to jednorázový
build tool.

- [ ] **Step 2: Zapiš ověřovací skript**

`packaging/verify-package.sh` (`chmod +x`):

```bash
#!/usr/bin/env bash
# Ověří nainstalovaný balíček v čistém kontejneru.
# Použití: packaging/verify-package.sh deb <cesta>.deb
#         packaging/verify-package.sh rpm <cesta>.rpm
set -euo pipefail

fmt="${1:?formát: deb nebo rpm}"
pkg="$(realpath "${2:?cesta k balíčku}")"
port=18430

case "$fmt" in
    deb)
        image=debian:13
        install='export DEBIAN_FRONTEND=noninteractive; apt-get update -qq; apt-get install -y -qq /pkg.deb'
        ;;
    rpm)
        image=fedora:42
        install='dnf install -y -q /pkg.rpm'
        ;;
    *)
        echo "neznámý formát: $fmt" >&2
        exit 2
        ;;
esac

cid="sysmon-verify-$fmt-$$"
docker run --rm -d --name "$cid" -p "$port:$port" \
    -v "$pkg:/pkg.$fmt:ro" "$image" sleep infinity >/dev/null
trap 'docker rm -f "$cid" >/dev/null 2>&1 || true' EXIT

docker exec "$cid" bash -lc "$install" >/dev/null
docker exec "$cid" test -x /usr/bin/sysmon-app
docker exec "$cid" test -x /usr/lib/sysmon-app/daemon/sysmon-app-daemon
docker exec "$cid" grep -qx 'Name=Sysmon' /usr/share/applications/sysmon-app.desktop
docker exec "$cid" test -f /usr/share/icons/hicolor/128x128/apps/sysmon-app.png

docker exec -d "$cid" /usr/lib/sysmon-app/daemon/sysmon-app-daemon --port "$port"
sleep 3
curl -fsS "http://127.0.0.1:$port/stats" >/dev/null
curl -fsS -N -m 3 "http://127.0.0.1:$port/events" >/dev/null || true
echo "OK: $fmt"
```

- [ ] **Step 3: Zbuildi balíčky**

```bash
cd frontend && npm ci && npm run build && cd ..
packaging/build-daemon.sh
cargo tauri build --bundles deb,rpm,appimage
ls -lh src-tauri/target/release/bundle/*/
```

Když bundler ohlásí, že resource `packaging/daemon` neexistuje nebo že mapa
`resources` je neplatná, uprav mapu na glob
`"../packaging/daemon/**/*": "daemon"` a zapiš to do uzavření tasku.

- [ ] **Step 4: Ověř `.deb` a `.rpm`**

```bash
packaging/verify-package.sh deb src-tauri/target/release/bundle/deb/*.deb
packaging/verify-package.sh rpm src-tauri/target/release/bundle/rpm/*.rpm
```

Očekávej `OK: deb` a `OK: rpm`. Když kontejner nejde stáhnout, zapiš to jako
vědomou mez a balíčky ověř jen rozbalením (`ar p` / `rpm2cpio`); výsledek
nesmí být označen jako instalace.

- [ ] **Step 5: Ověř AppImage**

```bash
rm -rf /tmp/sysmon-appimage && mkdir /tmp/sysmon-appimage
cd /tmp/sysmon-appimage
"/home/veezle/Documents/GithubClones/sysmon-app/src-tauri/target/release/bundle/appimage/"*.AppImage \
  --appimage-extract >/dev/null
test -x squashfs-root/usr/bin/sysmon-app
test -x squashfs-root/usr/lib/sysmon-app/daemon/sysmon-app-daemon
grep -qx 'Name=Sysmon' squashfs-root/usr/share/applications/sysmon-app.desktop
test -f squashfs-root/usr/share/icons/hicolor/128x128/apps/sysmon-app.png
squashfs-root/usr/lib/sysmon-app/daemon/sysmon-app-daemon --port 18431 &
daemon_pid=$!
sleep 2
curl -fsS http://127.0.0.1:18431/stats >/dev/null && echo "AppImage daemon OK"
kill "$daemon_pid"
```

- [ ] **Step 6: Ověř metadata balíčků**

```bash
deb=$(ls src-tauri/target/release/bundle/deb/*.deb | head -1)
member=$(ar t "$deb" | grep '^control\.tar')
ar p "$deb" "$member" | tar -xJO ./control
docker run --rm -v "$PWD/src-tauri/target/release/bundle/rpm:/rpm:ro" \
    fedora:42 rpm -qip /rpm/*.rpm
```

Zkontroluj `Package: sysmon-app`, `Depends:` obsahující WebKit a GTK
a `Name=Sysmon` v desktop souboru.

- [ ] **Step 7: Commitni**

```bash
git add packaging/verify-package.sh src-tauri/tauri.conf.json
git commit -m "fáze 4: instalátory deb, rpm a AppImage"
```

Pokud se `tauri.conf.json` neměnil, vynech ho z `git add`.

---

### Task 4: PKGBUILD

**Goal:** `packaging/arch/PKGBUILD` zbuildí a zabalí stejný instalovaný
layout nativně pro Arch.

**Files:**
- Create: `packaging/arch/PKGBUILD`, `packaging/sysmon-app.desktop`
- Modify: `.gitignore` (pokud v Tasku 1 chybí `packaging/arch/*.tar.gz`,
  `packaging/arch/src/`, `packaging/arch/pkg/`)

**Acceptance Criteria:**
- [ ] `makepkg -f` v `packaging/arch/` vyrobí
      `sysmon-app-0.1.0-1-x86_64.pkg.tar.zst`
- [ ] balíček obsahuje `/usr/bin/sysmon-app`,
      `/usr/lib/sysmon-app/daemon/sysmon-app-daemon` (+ `_internal/`),
      `/usr/share/applications/sysmon-app.desktop` a obě ikony
- [ ] démon z rozbaleného balíčku odpoví na `/stats`
- [ ] `depends` obsahují `webkit2gtk-4.1` a `gtk3`
- [ ] build neinstaluje nic do systému (`makepkg -si` se nepoužívá)

**Verify:** `makepkg -f` + `bsdtar -tf` + spuštění démona z fake rootu

**Steps:**

- [ ] **Step 1: Zapiš desktop soubor pro PKGBUILD**

`packaging/sysmon-app.desktop` (literální, bez Handlebars):

```ini
[Desktop Entry]
Type=Application
Name=Sysmon
Comment=Dashboard systémových metrik
Exec=sysmon-app
Icon=sysmon-app
Terminal=false
Categories=System;Monitor;
```

- [ ] **Step 2: Zapiš PKGBUILD**

`packaging/arch/PKGBUILD`:

```bash
# Maintainer: Veezle
pkgname=sysmon-app
pkgver=0.1.0
pkgrel=1
pkgdesc="Dashboard systémových metrik pro Linux"
arch=('x86_64')
license=('custom')
depends=('webkit2gtk-4.1' 'gtk3')
makedepends=('rust' 'cargo' 'nodejs' 'npm' 'python')
source=("$pkgname-$pkgver.tar.gz")
sha256sums=('SKIP')

build() {
    cd "$pkgname-$pkgver"
    ( cd frontend && npm ci && npm run build )
    packaging/build-daemon.sh
    cargo build --release --manifest-path src-tauri/Cargo.toml
}

package() {
    cd "$pkgname-$pkgver"
    install -Dm755 src-tauri/target/release/sysmon-app \
        "$pkgdir/usr/bin/sysmon-app"
    install -d "$pkgdir/usr/lib/sysmon-app"
    cp -a packaging/daemon "$pkgdir/usr/lib/sysmon-app/daemon"
    install -Dm644 src-tauri/icons/32x32.png \
        "$pkgdir/usr/share/icons/hicolor/32x32/apps/sysmon-app.png"
    install -Dm644 src-tauri/icons/128x128.png \
        "$pkgdir/usr/share/icons/hicolor/128x128/apps/sysmon-app.png"
    install -Dm644 packaging/sysmon-app.desktop \
        "$pkgdir/usr/share/applications/sysmon-app.desktop"
}
```

`sha256sums=('SKIP')` je pro lokální build; v uzavření tasku poznamenej,
že před publikací balíčku se má doplnit skutečný součet (`makepkg -g`).

- [ ] **Step 3: Vytvoř zdrojový tarball**

Z kořene repa (tarball obsahuje working tree, ne jen commit):

```bash
cd /home/veezle/Documents/GithubClones/sysmon-app
tar --exclude-vcs --exclude=node_modules --exclude=target \
    --exclude=packaging/.venv --exclude=packaging/build \
    --exclude=packaging/daemon --exclude=packaging/daemon-build \
    --exclude=packaging/arch/src --exclude=packaging/arch/pkg \
    --exclude='packaging/arch/*.tar.gz' \
    --transform 's,^,sysmon-app-0.1.0/,' \
    -czf packaging/arch/sysmon-app-0.1.0.tar.gz .
```

Ověř, že v tarballu je `sysmon-app-0.1.0/frontend/package-lock.json`
a `sysmon-app-0.1.0/sysmon_app/__main__.py`, a že tam **není**
`node_modules`, `target` ani `packaging/.venv`.

- [ ] **Step 4: Zbuild a zkontroluj obsah**

```bash
cd packaging/arch
makepkg -f --noconfirm
bsdtar -tf sysmon-app-0.1.0-1-x86_64.pkg.tar.zst | sort | sed -n '1,40p'
```

- [ ] **Step 5: Ověř démona z balíčku bez instalace do systému**

```bash
rm -rf /tmp/sysmon-pkgroot && mkdir /tmp/sysmon-pkgroot
bsdtar -xf packaging/arch/sysmon-app-0.1.0-1-x86_64.pkg.tar.zst \
    -C /tmp/sysmon-pkgroot
/tmp/sysmon-pkgroot/usr/lib/sysmon-app/daemon/sysmon-app-daemon --port 18432 &
daemon_pid=$!
sleep 2
curl -fsS http://127.0.0.1:18432/stats >/dev/null && echo "PKGBUILD daemon OK"
kill "$daemon_pid"
test -x /tmp/sysmon-pkgroot/usr/bin/sysmon-app
grep -qx 'Name=Sysmon' \
    /tmp/sysmon-pkgroot/usr/share/applications/sysmon-app.desktop
```

- [ ] **Step 6: Commitni**

```bash
git add packaging/arch/PKGBUILD packaging/sysmon-app.desktop .gitignore
git commit -m "fáze 4: PKGBUILD pro Arch"
```

---

### Task 5: Měření paměti, README a end-to-end

**Goal:** Změřit paměť okna 60 min v reálném okně, zapsat čísla a dokončit
dokumentaci i závěrečné ověření.

**Files:**
- Create: `tools/__init__.py`, `tools/measure_memory.py`,
  `tests/test_measure_memory.py`
- Modify: `README.md`, tento plán (uzavření Tasku 5)

**Acceptance Criteria:**
- [ ] `python3 tools/measure_memory.py --help` projde bez importu
      nestandardní knihovny
- [ ] `python3 -m unittest tests.test_measure_memory -v` projde; testy
      pinují lineární trend, mediány a klasifikaci procesů
- [ ] 60minutové měření v reálném okně splní `web` slope ≤ 5 MB/h
      a delta ≤ 15 MB
- [ ] naměřená čísla (slope, mediány, celková RSS) jsou v tomto plánu
      a v README
- [ ] README popisuje instalaci, AppImage prerekvizitu, PKGBUILD,
      minimální glibc/distribuce a měření paměti
- [ ] `python3 -m unittest discover -s tests -t .` projde (156 + nové testy)
- [ ] `cargo test` a `npm run typecheck` projdou; `../sysmon` je čistý

**Verify:** unit testy + 60minutový běh + README příkazy doslova +
regresní sada

**Steps:**

- [ ] **Step 1: Zapiš měřicí nástroj**

`tools/__init__.py`: prázdný soubor.

`tools/measure_memory.py` — pouze stdlib. Musí umět:

- `--pid` (jinak najít proces s exe `sysmon-app`; při více kandidátech
  skončit kódem 2 s výpisem PIDů),
- `--duration` (výchozí 3600), `--interval` (10), `--warmup` (300),
  `--csv`, `--slope-limit` (5.0), `--delta-limit` (15.0),
- každý vzorek projít `/proc`, sestavit strom potomků a sečíst RSS
  z `/proc/<pid>/status` (`VmRSS`),
- kategorie `app`, `web` (WebKitWebProcess), `network`
  (WebKitNetworkProcess), `daemon` (`sysmon-app-daemon` nebo
  `python3 -m sysmon_app`) a `other`,
- lineární regresi nad `web` od konce warmupu, slope v MB/h,
- medián prvních a posledních 10 min po warmupu a jejich rozdíl,
- návratový kód `0` ploché, `1` překročený práh, `2` málo vzorků / proces
  zmizel,
- CSV hlavičku `elapsed_s,app_kb,web_kb,network_kb,daemon_kb,other_kb,total_kb`.

Matematiku drž v čistých funkcích (`slope_mb_per_hour`, `median_delta`),
aby šla testovat bez `/proc`.

- [ ] **Step 2: Zapiš testy**

`tests/test_measure_memory.py` (stdlib `unittest`, import
`from tools import measure_memory`):

- slope na syntetických datech: konstantní řada → ~0; řada +60 MB/h → 60;
- medián a delta na ručně spočítaných hodnotách;
- klasifikace cmdline pro `WebKitWebProcess`, `WebKitNetworkProcess`,
  `sysmon-app-daemon` a `python3 -m sysmon_app`;
- `--help` nepadá (spusť `python3 tools/measure_memory.py --help` jako
  subprocess).

- [ ] **Step 3: Připrav reálné okno**

Použij simulovaný instalovaný strom z Tasku 2 (stejný layout jako balíček):

```bash
pgrep -f 'sysmon-app|sysmon_app' | xargs -r kill 2>/dev/null || true
sleep 1
rm -rf /tmp/sysmon-install
mkdir -p /tmp/sysmon-install/usr/bin /tmp/sysmon-install/usr/lib/sysmon-app
cp src-tauri/target/release/sysmon-app /tmp/sysmon-install/usr/bin/
cp -a packaging/daemon /tmp/sysmon-install/usr/lib/sysmon-app/daemon
XDG_CONFIG_HOME=/tmp/sysmon-memory-xdg \
  /tmp/sysmon-install/usr/bin/sysmon-app >/tmp/sysmon-memory.log 2>&1 &
sleep 5
pgrep -af 'sysmon-app|WebKitWebProcess|sysmon-app-daemon'
```

Okno musí být viditelné a dashboard musí tiknout. Ověř screenshotem
`spectacle -b -n -a -o /tmp/sysmon-memory.png` a krátkým
`curl -fsS http://127.0.0.1:8430/stats`.

- [ ] **Step 4: Spusť 60minutové měření**

Najdi PID Tauri (`pgrep -f '/tmp/sysmon-install/usr/bin/sysmon-app'`) a spusť:

```bash
python3 tools/measure_memory.py \
  --pid <PID> --duration 3600 --interval 10 \
  --csv /tmp/sysmon-memory.csv
```

Měření běží hodinu; spusť ho na pozadí a pokračuj až po jeho skončení.
Okno nech otevřené, nic v něm neklikej a nespouštěj druhou instanci.
Když se proces ukončí nebo je vzorků málo, měření opakuj; nezkracuj ho.

- [ ] **Step 5: Zapiš výsledek**

Do README (sekce „Paměť“) a do uzavření tohoto tasku zapiš:

- datum a dobu běhu,
- slope `web` v MB/h a mediány prvních/posledních 10 min,
- celkovou RSS na konci a RSS démona,
- Verdikt `ploché` / `není ploché` podle prahů.

Když práh nevyjde, task **není hotový**: zapiš čísla, nech task otevřený
a předej orchestrátorovi.

- [ ] **Step 6: Uprav README**

Musí obsahovat:

- stav „fáze 4 hotová“ (po úspěšném měření),
- instalaci z `.deb`/`.rpm` a prerekvizitu WebKitGTK,
- AppImage a jeho prerekvizitu `webkit2gtk-4.1`,
- `PKGBUILD` a že build potřebuje síť (npm/cargo/pip),
- minimální glibc 2.39 → Debian 13+, Ubuntu 24.04+, Fedora 42+,
- instalovaný layout a že démon je součástí balíčku (žádný systémový
  Python),
- migraci autostartu z vývojové cesty,
- měření paměti: příkaz, práh a naměřená čísla,
- že vývojový režim (`python3 -m sysmon_app`) zůstává.

- [ ] **Step 7: Závěrečné ověření**

```bash
python3 -m unittest discover -s tests -t . | tail -3
cargo test --manifest-path src-tauri/Cargo.toml | tail -5
cd frontend && npm run typecheck && cd ..
git -C ../sysmon status --short
git status --short
```

Očekávej zelené testy, čistý `../sysmon` a žádné build artefakty v gitu.

- [ ] **Step 8: Commitni a předej orchestrátorovi**

```bash
git add tools/__init__.py tools/measure_memory.py \
  tests/test_measure_memory.py README.md \
  docs/superpowers/plans/2026-10-17-faze-4-baleni.md
git commit -m "fáze 4: měření paměti, README a uzavření"
```

Do plánu pod task přidej „Uzavření Tasku 5“ s naměřenými čísly a vědomými
mezemi. Orchestrátor pak označí tasky v trackeru a přepíše `docs/STATE.md`.

---

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
6. Paměť okna je plochá podle prahu 5 MB/h / 15 MB za 60 min a čísla jsou
   zapsaná v plánu a README.
7. `cargo test`, Python sada (156 testů + nové) a `npm run typecheck`
   projdou; `git -C ../sysmon status --short` je čistý.
