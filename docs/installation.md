# Installation and packaging

This document describes how to build and install Sysmon App.

## Pre-built packages

Download a package from [GitHub Releases](https://github.com/Veezle/sysmon-app/releases), when published.

| Package | Install |
|---|---|
| Debian / Ubuntu | `sudo apt install ./sysmon-app_*.deb` |
| Fedora | `sudo dnf install ./sysmon-app-*.rpm` |
| Arch Linux | Build with `packaging/arch/PKGBUILD` |
| AppImage | Run after setting the executable bit |

## Runtime dependencies

The Debian and RPM packages use system libraries:

- WebKitGTK
- GTK
- Ayatana AppIndicator library for the system tray

Install the required packages with your distribution's package manager if the package manager does not install them automatically.

On Arch Linux:

```bash
sudo pacman -S webkit2gtk-4.1 libayatana-appindicator
```

On Debian-based systems:

```bash
sudo apt install libwebkit2gtk-4.1-0 libayatana-appindicator3-1
```

On Fedora:

```bash
sudo dnf install webkit2gtk4.1 libayatana-appindicator-gtk3
```

## Compatibility

The daemon is bundled with the application. A system-wide Python installation and `psutil` are not required for packaged builds.

The Debian and RPM binaries require glibc 2.39 or newer. The AppImage is built on Arch Linux and requires glibc 2.44 or newer.

Debian 12 and older are not supported by the current packages.

## Build from source

Build from the repository root.

### 1. Build the frontend

```bash
cd frontend
npm ci
npm run build
cd ..
```

The build output is written to `sysmon_app/web/`.

### 2. Build the daemon

```bash
packaging/build-daemon.sh
```

This creates the bundled PyInstaller application in `packaging/daemon/`.

### 3. Install the Tauri CLI

```bash
cargo install tauri-cli --version "^2" --locked
```

### 4. Build packages

```bash
cargo tauri build --bundles deb,rpm,appimage
```

Build artifacts are written to:

```text
src-tauri/target/release/bundle/
```

The build requires network access for npm, Cargo, and PyInstaller dependencies.

## Arch Linux package

Build the source archive and install the package:

```bash
git archive --prefix=sysmon-app-0.1.0/ \
    -o packaging/arch/sysmon-app-0.1.0.tar.gz HEAD

cd packaging/arch
makepkg -si
```
