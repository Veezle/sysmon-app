#!/usr/bin/env bash
# Zbuildi demona jako PyInstaller onedir do packaging/daemon/.
# Vychozi rezim buildi v debian:13 kontejneru (portabilni artefakt).
# --host dela nativni build pro Arch (PKGBUILD); ten neni portabilni.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# --- preflight: nic destruktivniho, dokud nejsou vsechny kontroly hotove ---

if [ "$#" -gt 1 ]; then
    echo "Příliš mnoho argumentů (povoleno: žádný argument nebo --host)." >&2
    exit 2
fi

MODE=container
case "${1:-}" in
    --host) MODE=host ;;
    "") ;;
    *) echo "Neznámý argument: $1 (povoleno: žádný argument nebo --host)" >&2
       exit 2 ;;
esac

if [ "$(id -u)" -eq 0 ]; then
    echo "Build nesmí běžet jako root." >&2
    exit 2
fi

if [ ! -f sysmon_app/web/index.html ]; then
    echo "Frontend není zbuilděný (sysmon_app/web/index.html neexistuje)." >&2
    echo "Spusť v adresáři frontend:" >&2
    echo "    npm ci && npm run build" >&2
    exit 2
fi

if [ ! -f packaging/requirements-build.txt ]; then
    echo "Chybí packaging/requirements-build.txt s pinem PyInstalleru." >&2
    exit 2
fi
PYINSTALLER_VERSION="$(sed -n 's/^pyinstaller==//p' packaging/requirements-build.txt)"
if [ -z "$PYINSTALLER_VERSION" ]; then
    echo "V packaging/requirements-build.txt chybí pin pyinstaller==…" >&2
    exit 2
fi

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
    if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
        echo "Docker není k dispozici (nebo neběží docker daemon)." >&2
        echo "Pro nativní build na Archu použij --host." >&2
        exit 2
    fi
    DOCKERFILE_HASH="$(sha256sum packaging/Dockerfile.daemon | cut -c1-12)"
    IMAGE="sysmon-app-daemon-build:debian13-py${PYINSTALLER_VERSION}-${DOCKERFILE_HASH}"
    if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
        docker build --quiet \
            --build-arg "PYINSTALLER_VERSION=$PYINSTALLER_VERSION" \
            -t "$IMAGE" -f packaging/Dockerfile.daemon packaging
    fi
    IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$IMAGE")"
    PYTHON=/opt/pyinstaller/bin/python
    PATHS=/src
    DATA=/src/sysmon_app/web:sysmon_app/web
    DIST=/src/packaging/daemon-build
    WORK=/src/packaging/build
fi

# --- build: stare build adresare, ale posledni dobry packaging/daemon zustava ---
rm -rf packaging/build packaging/daemon-build
mkdir -p packaging/build

if [ "$MODE" = host ]; then
    PYTHONHASHSEED=0 PYI_LOG_LEVEL=WARN "$PYTHON" -m PyInstaller \
        --noconfirm --clean --onedir --log-level WARN \
        --name sysmon-app-daemon \
        --distpath "$DIST" --workpath "$WORK" --specpath "$WORK" \
        --paths "$PATHS" --add-data "$DATA" \
        sysmon_app/__main__.py
else
    docker run --rm \
        --network none \
        --user "$(id -u):$(id -g)" \
        -e HOME=/tmp \
        -e PYTHONHASHSEED=0 \
        -e PYI_LOG_LEVEL=WARN \
        -v "$ROOT:/src" -w /src \
        "$IMAGE" \
        "$PYTHON" -m PyInstaller \
            --noconfirm --clean --onedir --log-level WARN \
            --name sysmon-app-daemon \
            --distpath "$DIST" --workpath "$WORK" --specpath "$WORK" \
            --paths "$PATHS" --add-data "$DATA" \
            sysmon_app/__main__.py
fi

test -x packaging/daemon-build/sysmon-app-daemon/sysmon-app-daemon
test -d packaging/daemon-build/sysmon-app-daemon/_internal

# Teprve ted, po uspesnem buildu, nahrad posledni dobry artefakt.
rm -rf packaging/daemon
mv packaging/daemon-build/sysmon-app-daemon packaging/daemon
rmdir packaging/daemon-build

BUILT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
COMMIT="$(git rev-parse --short HEAD)"
{
    echo "mode=$MODE"
    echo "pyinstaller=$PYINSTALLER_VERSION"
    echo "commit=$COMMIT"
    if [ "$MODE" = container ]; then
        echo "image=$IMAGE $IMAGE_ID"
    fi
    echo "built=$BUILT_UTC"
} > packaging/daemon/BUILD-INFO

echo "Hotovo: packaging/daemon/sysmon-app-daemon ($MODE)"
