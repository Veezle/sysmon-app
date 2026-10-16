"""HTTP server - routy, SPA a SSE proud.

Routy:
    GET /              -> web/index.html
    GET /static/<soubor> -> web/static/style.css, app.js, icon.svg
    GET /stats         -> JSON snapshot
    GET /events        -> SSE proud snapshotu

Zadna autentizace a zadne POST routy: produkt nic nemeni, takze neni co
chranit. Pozor ale, ze server defaultne posloucha na vsech rozhranich -
kdokoli v siti vidi seznam procesu a portu. Je to vedome, kvuli telefonu.
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from sysmon_app.config import DEFAULT_HOST, DEFAULT_PORT, SSE_KEEPALIVE_SEC

WEB_DIR = Path(__file__).resolve().parent / "web"
STATIC_DIR = WEB_DIR / "static"
INDEX_NAME = "index.html"

STATIC_PREFIX = "/static/"

# Povolene pripony pro /static/ -> content-type
STATIC_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}


def load_index():
    """Nacte web/index.html (UTF-8)."""
    with open(WEB_DIR / INDEX_NAME, encoding="utf-8") as f:
        return f.read()


def load_static(name):
    """Nacte soubor z web/static/. Vraci (bytes, content-type) nebo None.

    Allow-list pripon drzi soubory mimo frontend mimo hru (config.py,
    index.html) a kontrola realpath drzi obsah uvnitr static/ - bez ni by
    `../cosi.css` vyslo z adresare. Cesta se porovnava po rozreseni symlinku:
    `realpath` na obou stranach, aby ani symlink v static/ nevedl ven.
    """
    ctype = STATIC_TYPES.get(os.path.splitext(name)[1])
    if ctype is None:
        return None
    real = os.path.realpath(os.path.join(STATIC_DIR, name))
    root = os.path.realpath(STATIC_DIR) + os.sep
    if not real.startswith(root):  # ochrana proti vyskoku z adresare pres ".."
        return None
    try:
        with open(real, "rb") as f:
            return f.read(), ctype
    except OSError:
        return None


class Handler(BaseHTTPRequestHandler):
    # HTTP/1.1 kvuli SSE: u HTTP/1.0 klient nepozna konec tela jinak nez
    # zavrenim spojeni, takze by se EventSource porad pripojoval znovu.
    protocol_version = "HTTP/1.1"

    def _path(self):
        """Cesta bez query stringu - routy se porovnavaji presne."""
        return self.path.partition("?")[0]

    def _send(self, body, ctype, status=200):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, obj, status=200):
        self._send(json.dumps(obj), "application/json; charset=utf-8", status=status)

    def _send_empty(self, status):
        """Odpoved bez tela. Content-Length 0 je nutny: s HTTP/1.1 by klient
        jinak cekal na telo, ktere neprijde."""
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        path = self._path()
        if path == "/stats":
            self._send_json(self._snapshot_now())
        elif path in ("/", "/index.html"):
            self._send(load_index(), "text/html; charset=utf-8")
        elif path.startswith(STATIC_PREFIX):
            asset = load_static(path[len(STATIC_PREFIX):])
            if asset is None:
                self._send_empty(404)
            else:
                self._send(asset[0], asset[1])
        else:
            self._send_empty(404)

    def _snapshot_now(self):
        """Snapshot z feedu; dokud zadny nema, sebere se naprimo.

        Podminka neni "feed bezi", ale "feed uz ma snapshot": mezi
        `feed.start()` a prvnim tikem je `latest()` jeste None, takze /stats
        v tom okne kolektory cte - a to soubezne s tikem. Jakmile feed prvni
        snapshot ma, /stats uz jen serializuje, a teprve tim se rate-based
        kolektory (sit, disk) prestanou rozbijet soubeznym ctenim.

        Snapshot se jen serializuje. Feed vraci tyz dict vsem odberatelum,
        takze pridat do nej klic nebo ho prepsat znamena otravit stav vsem
        ostatnim - a tise.
        """
        snapshot = self.server.feed.latest()
        if snapshot is None:
            snapshot = self.server.monitor.snapshot()
        return snapshot

    def log_message(self, *args):
        pass


def serve(monitor, feed, host=DEFAULT_HOST, port=DEFAULT_PORT):
    """Vytvori server s predanym Monitorem a feedem (zadne globalni promenne).

    Monitor a feed sedi na serveru, ne na tride Handler: stav na tride je
    spolecny pro vsechny servery v procesu, takze druhe `serve()` by tise
    prepsalo feed i prvnimu serveru.
    """
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.monitor = monitor
    srv.feed = feed
    # SSE spoje drzi vlakno kazdy. Bez daemon_threads by ukonceni serveru
    # cekalo na ne, dokud je klient nezatvori.
    srv.daemon_threads = True
    return srv
