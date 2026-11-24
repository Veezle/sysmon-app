# Development

## Requirements

- Python 3.11+
- Node.js 20.19+ or 22.12+
- npm
- Rust 1.90+ for the Tauri desktop application

## Run the daemon

Build the frontend first:

```bash
cd frontend
npm ci
npm run build
cd ..
```

Start the daemon from the repository root:

```bash
python3 -m sysmon_app
```

The dashboard is available at `http://localhost:8430`.

## Frontend development

Keep the daemon running. Start Vite in another terminal:

```bash
cd frontend
npm run dev
```

Vite proxies `/stats` and `/events` to the daemon.

The production frontend build is written to `sysmon_app/web/`. This directory is generated and is not committed to Git.

## Desktop development

Install the system dependencies for Tauri and WebKitGTK.

On Arch Linux:

```bash
sudo pacman -S webkit2gtk-4.1 libayatana-appindicator
```

Build or run the desktop application:

```bash
cargo build --manifest-path src-tauri/Cargo.toml
cargo run --manifest-path src-tauri/Cargo.toml
```

## Tests

Python:

```bash
python3 -m unittest discover -s tests -t .
```

Rust:

```bash
cargo test --manifest-path src-tauri/Cargo.toml
```

Frontend type checking:

```bash
cd frontend
npm run typecheck
```

Some Python tests depend on a frontend build. A subset of browser tests also requires headless Chrome or Chromium.

## Configuration

The daemon reads:

```text
~/.config/sysmon-app/config.toml
```

The path respects `XDG_CONFIG_HOME`. See the main README for a configuration example.
