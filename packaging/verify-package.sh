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
        # curl není v zakladnim obrazu; daemon se pres nej dotazuje na /stats.
        install='export DEBIAN_FRONTEND=noninteractive; apt-get update -qq; apt-get install -y -qq curl /pkg.deb'
        ;;
    rpm)
        image=fedora:42
        install='dnf install -y -q /pkg.rpm curl'
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
# Start PyInstaller onedir není okamžitý; čekej na odpověď, ne na pevný sleep.
for _ in $(seq 1 15); do
    if curl -fsS "http://127.0.0.1:$port/stats" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done
curl -fsS "http://127.0.0.1:$port/stats" >/dev/null
curl -fsS -N -m 3 "http://127.0.0.1:$port/events" >/dev/null || true
echo "OK: $fmt"
