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

if [ ! -x packaging/.venv/bin/python ] || \
   ! packaging/.venv/bin/python -c 'import psutil' >/dev/null 2>&1; then
    # psutil je systémová závislost (pacman), ne pip balíček produktu;
    # venv ji musí vidět, jinak PyInstaller zabalí démona bez ní.
    rm -rf packaging/.venv
    python3 -m venv --system-site-packages packaging/.venv
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
    --add-data "$ROOT/sysmon_app/web:sysmon_app/web" \
    sysmon_app/__main__.py

mv packaging/daemon-build/sysmon-app-daemon packaging/daemon
rmdir packaging/daemon-build
test -x packaging/daemon/sysmon-app-daemon
echo "Hotovo: packaging/daemon/sysmon-app-daemon"
