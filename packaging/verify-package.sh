#!/usr/bin/env bash
# Ověří nainstalovaný balíček v čistém kontejneru.
# Použití: packaging/verify-package.sh deb <cesta>.deb
#         packaging/verify-package.sh rpm <cesta>.rpm
set -euo pipefail

fmt="${1:?formát: deb nebo rpm}"
pkg="$(realpath "${2:?cesta k balíčku}")"
port=18430

# GNU realpath vrati rc 0 i pro neexistujici posledni komponentu; bez teto
# kontroly by `docker run -v` na hostiteli vytvoril root-owned adresar.
[ -f "$pkg" ] || { echo "balíček není regulérní soubor: $pkg" >&2; exit 2; }

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    echo "Docker není k dispozici (nebo neběží docker daemon)." >&2
    echo "Ověření balíčků vyžaduje Docker." >&2
    exit 2
fi

case "$fmt" in
    deb)
        image=debian:13
        # curl neni v zakladnim obrazu; daemon se pres nej dotazuje na /stats.
        install='export DEBIAN_FRONTEND=noninteractive; apt-get update -qq; apt-get install -y -qq curl /pkg.deb'
        ;;
    rpm)
        image=fedora:42
        # curl obraz obsahuje, ale explicitni instalace drzi stejny kontrakt.
        install='dnf install -y -q /pkg.rpm curl'
        ;;
    *)
        echo "neznámý formát: $fmt" >&2
        exit 2
        ;;
esac

cid="sysmon-verify-$fmt-$$"
# Bez -p: daemon zustava jen v siti kontejneru, /stats se neobjevuje na LAN
# a ověření nekoliduje s obsazeným portem na hostiteli.
docker run --rm -d --name "$cid" \
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
    if docker exec "$cid" curl -fsS --connect-timeout 1 --max-time 2 \
        "http://127.0.0.1:$port/stats" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done
docker exec "$cid" curl -fsS --connect-timeout 1 --max-time 2 \
    "http://127.0.0.1:$port/stats" >/dev/null
# SSE: timeout 28 je ocekavany, ale aspon jeden bajt udalosti dorazit musi.
docker exec "$cid" curl -fsS -N --connect-timeout 1 --max-time 3 \
    -o /tmp/events.out "http://127.0.0.1:$port/events" 2>/dev/null || true
docker exec "$cid" test -s /tmp/events.out
echo "OK: $fmt"
