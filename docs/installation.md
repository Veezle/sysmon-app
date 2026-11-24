# Installation and packaging

This document describes how to build and install Sysmon App.

## Pre-built packages

Download a package from [GitHub Releases](https://github.com/Veezle/sysmon-app/releases), when published.

| Package | Install |
|---|---|
| Debian / Ubuntu | `sudo apt install ./sysmon-app_*.deb` |
| Fedora | `sudo dnf install ./sysmon-app-*.rpm` |
| Arch Linux | Download `PKGBUILD` and the matching source archive, then run `makepkg -si` |
| AppImage | Make the file executable and run it |

## Supported build targets

Release packages are built on Ubuntu 24.04. The bundled daemon is built separately in a Debian 13 container.

The Debian, RPM, and AppImage binaries require glibc 2.39 or newer. The Debian and RPM packages use system WebKitGTK and GTK libraries. The AppImage bundles its other application libraries.

Debian 12 and older are not supported by the current packages.

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

Download `PKGBUILD` and the matching `sysmon-app-<version>.tar.gz` asset from the same GitHub Release. Put both files in one directory and run:

```bash
makepkg -si
```

The release workflow includes the SHA-256 checksum of the source archive in the downloaded PKGBUILD.

## Create a release

The GitHub Actions workflow builds packages when a version tag is pushed.

Before a release, keep these version fields in sync:

- `src-tauri/tauri.conf.json`
- `src-tauri/Cargo.toml`
- `packaging/arch/PKGBUILD`

For example, after setting all three versions to `0.1.0`:

```bash
git switch main
git pull --ff-only
git tag -a v0.1.0 -m "Sysmon App v0.1.0"
git push origin v0.1.0
```

The tag starts the build and creates the GitHub Release after all build steps pass.

You can also run the workflow manually from the Actions tab. A manual run builds the packages and uploads them as a workflow artifact. It does not publish a release.
