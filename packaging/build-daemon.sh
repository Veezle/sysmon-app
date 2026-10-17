#!/usr/bin/env bash
# Zbuildi demona jako PyInstaller onedir do packaging/daemon/.
# Vychozi rezim buildi v debian:13 kontejneru (portabilni artefakt).
# --host dela nativni build pro Arch (PKGBUILD); ten neni portabilni.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MODE=container
case "${1:-}" in
    --host) MODE=host ;;
    "") ;;
    *) echo "Neznámý argument: $1 (povoleno: --host)" >&2; exit 2 ;;
esac

if [ ! -f sysmon_app/web/index.html ]; then
    echo "Frontend není zbuilděný (sysmon_app/web/index.html neexistuje)." >&2
    echo "Spusť v adresáři frontend:" >&2
    echo "    npm ci && npm run build" >&2
    exit 2
fi

PYINSTALLER_VERSION="$(sed -n 's/^pyinstaller==//p' packaging/requirements-build.txt)"
if [ -z "$PYINSTALLER_VERSION" ]; then
    echo "V packaging/requirements-build.txt chybí pin pyinstaller==…" >&2
    exit 2
fi

rm -rf packaging/build packaging/daemon-build packaging/daemon
mkdir -p packaging/build

if [ "$MODE" = host ]; then
    if [ ! -x packaging/.venv/bin/python ] || \
       ! packaging/.venv/bin/python -c 'import psutil' >/dev/null 2>&1; then
        rm -rf packaging/.venv
        python3 -m venv --system-site-packages packaging/.venv
    fi
    packaging/.venv/bin/python -m pip install --quiet --disable-pip-version-check \
        -r packaging/requirements-build.txt
    PYTHON=packaging/.venv/bin/python
    PATHS="$ROOT"
    DATA="$ROOT/sysmon_app/web:sysmon_app/web"
    DIST=packaging/daemon-build
    WORK=packaging/build
else
    if ! command -v docker >/dev/null 2>&1; then
        echo "Docker není k dispozici. Pro nativní build na Archu použij --host." >&2
        exit 2
    fi
    IMAGE="sysmon-app-daemon-build:debian13-py${PYINSTALLER_VERSION}"
    if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
        docker build --quiet \
            --build-arg "PYINSTALLER_VERSION=$PYINSTALLER_VERSION" \
            -t "$IMAGE" -f packaging/Dockerfile.daemon packaging
    fi
    PYTHON=/opt/pyinstaller/bin/python
    PATHS=/src
    DATA=/src/sysmon_app/web:sysmon_app/web
    DIST=/src/packaging/daemon-build
    WORK=/src/packaging/build
fi

if [ "$MODE" = host ]; then
    "$PYTHON" -m PyInstaller \
        --noconfirm --clean --onedir \
        --name sysmon-app-daemon \
        --distpath "$DIST" --workpath "$WORK" --specpath "$WORK" \
        --paths "$PATHS" --add-data "$DATA" \
        sysmon_app/__main__.py
else
    docker run --rm \
        --user "$(id -u):$(id -g)" \
        -e HOME=/tmp \
        -v "$ROOT:/src" -w /src \
        "$IMAGE" \
        "$PYTHON" -m PyInstaller \
            --noconfirm --clean --onedir \
            --name sysmon-app-daemon \
            --distpath "$DIST" --workpath "$WORK" --specpath "$WORK" \
            --paths "$PATHS" --add-data "$DATA" \
            sysmon_app/__main__.py
fi

mv packaging/daemon-build/sysmon-app-daemon packaging/daemon
rmdir packaging/daemon-build
test -x packaging/daemon/sysmon-app-daemon
echo "Hotovo: packaging/daemon/sysmon-app-daemon ($MODE)"
