"""Vstupni bod: `python3 -m sysmon_app`.

Spousti demona - sberny cyklus, HTTP server a SSE. Okno (faze 3) se pak
pripoji na http://127.0.0.1:<port>; tenhle proces o okne nic nevi.

Zadny token se nevypisuje, protoze zadny neni: na rozdil od sysmonu tu nejsou
akce, takze neni co chranit - a cely start je tim kratsi.

Kazda chyba, kterou uzivatel muze zpusobit sam (rozbita konfigurace, obsazeny
port, spatny argument), konci vetou v cestine. Appku pouzivaji i lide, kteri
traceback nectou.
"""

import argparse
import errno
import socket
import sys

from sysmon_app import server as server_modul
from sysmon_app.config import Settings, load_settings
from sysmon_app.feed import SnapshotFeed
from sysmon_app.monitor import Monitor
from sysmon_app.server import load_index, serve


def _port_number(text):
    """Port z prikazove radky - vcetne rozsahu, ktery argparse sam nehlida.

    Rozsah se kontroluje tady, ne az v socketu: `socket.bind` na portu mimo
    rozsah vyhodi OverflowError, a ten neni OSError, takze by uzivatel dostal
    traceback. Konfiguracni cesta rozsah validuje (config.py), CLI musi taky.

    Nula se odmita stejne jako v config.py: bind by uspel, ale server by
    poslouchal na nahodnem portu a vypsana URL by byla lez.
    """
    try:
        port = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' není číslo portu") from None
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError(f"port {port} je mimo rozsah 1-65535")
    return port


def parse_args(argv=None, settings=None):
    """Argumenty prikazove radky. `settings` je zaklad, ktery argumenty prebijejí."""
    settings = settings or load_settings()
    ap = argparse.ArgumentParser(
        prog="sysmon_app",
        description="Dashboard systémových metrik pro okno i telefon.",
    )
    # V napovede je platna vychozi hodnota, tedy ta z config.toml - jinak by
    # uzivatel s `port = 9100` v konfiguraci cetl, ze vychozi je 8430.
    ap.add_argument("--host", default=settings.host,
                    help=f"na jakém rozhraní poslouchat (výchozí {settings.host})")
    ap.add_argument("--port", type=_port_number, default=settings.port,
                    help=f"na jakém portu poslouchat (výchozí {settings.port})")
    return ap.parse_args(argv)


def report_bind_error(exc, host, port):
    """Pricinu bind selhani pojmenuje podle errno.

    Rict u vsech selhani "port je obsazeny" je lez a uzivatel se podle ni
    vyda spatnym smerem: EACCES (port pod 1024 bez roota), EADDRNOTAVAIL
    (adresa na stroji neni) i neznamy hostitel (gaierror) vypadaji v jeho
    konfiguraci stejne pravdepodobne a rada "zvol jiny port" u nich k nicemu
    nevede. Mereno: `--port 80` i `--host 10.1.2.3` na tomhle stroji.
    """
    if exc.errno == errno.EADDRINUSE:
        print(
            f"Port {port} je obsazený. Pravděpodobně už sysmon-app běží — "
            f"otevři http://127.0.0.1:{port}. "
            f"Nebo zvol jiný port přes --port.",
            file=sys.stderr,
        )
    elif exc.errno == errno.EACCES:
        print(
            f"Na portu {port} nelze poslouchat: chybí oprávnění. Porty pod 1024 "
            f"patří systémovému uživateli root — zvol port vyšší, například "
            f"--port 8430.",
            file=sys.stderr,
        )
    elif exc.errno == errno.EADDRNOTAVAIL:
        print(
            f"Adresa {host} na tomhle stroji neexistuje, nedá se na ní poslouchat "
            f"— zkontroluj host v config.toml nebo v --host.",
            file=sys.stderr,
        )
    elif isinstance(exc, socket.gaierror):
        # Sem pada preklep v hostiteli. errno je tu zaporne EAI_*, takze se
        # pozna podle typu vyjimky, ne podle cisla.
        print(
            f"Hostitel {host} se nepodařilo přeložit na adresu "
            f"({exc.strerror or exc}) — zkontroluj host v config.toml "
            f"nebo v --host.",
            file=sys.stderr,
        )
    else:
        print(
            f"Na {host}:{port} se nepodařilo poslouchat: {exc.strerror or exc}.",
            file=sys.stderr,
        )


def report_missing_build(web_dir):
    """Chybejici build je uzivatelova situace - hlasi se vetou, ne tracebackem."""
    print(
        f"Frontend není zbuilděný ({web_dir / 'index.html'} neexistuje).\n"
        f"Spusť v adresáři frontend:\n"
        f"    npm ci && npm run build",
        file=sys.stderr,
    )


def main(argv=None):
    try:
        settings = load_settings()
        config_error = None
    except ValueError as exc:
        # Rozbita konfigurace se hlasi vetou (a s cestou k souboru, kterou
        # ValueError ve sobe nese), ne tracebackem. Hlasi se ale az po
        # argumentech: `--help` je jedine, co na konfiguraci zaviset nema,
        # a uzivatel ho potrebuje prave tehdy, kdyz si ji rozbil preklepem.
        # Vychozi Settings tu slouzi jen k postaveni parseru.
        settings = Settings()
        config_error = exc

    args = parse_args(argv, settings)

    if config_error is not None:
        print(f"Chyba v konfiguraci: {config_error}", file=sys.stderr)
        return 2

    if load_index() is None:
        report_missing_build(server_modul.WEB_DIR)
        return 2

    monitor = Monitor(settings)
    monitor.prime()             # baseline pro rate-based metriky
    monitor.start_background()  # docker + historie baterie

    feed = SnapshotFeed(monitor)
    # Snapshot se publikuje synchronne jeste pred serverem. `start()` jen
    # zvedne vlakno, takze mezi nim a prvnim tikem je `latest()` jeste None -
    # a /stats v tom okne sbira naprimo, soubezne s tikem, coz u rate
    # kolektoru (sit, disk) prepise baseline. Takze: publikovat, pak startovat.
    feed.publish_once()
    feed.start()

    try:
        srv = serve(monitor, feed, args.host, args.port)
    except OSError as exc:
        report_bind_error(exc, args.host, args.port)
        feed.stop()
        return 2

    print(f"sysmon-app bezi na http://{args.host}:{args.port}")
    print(f"  v prohlizeci: http://localhost:{args.port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nkonec")
    finally:
        feed.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
