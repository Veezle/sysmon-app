"""Server: servirovani assetu, /stats a pozdeji SSE."""

import copy
import http.client
import json
import re
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from sysmon_app import server
from sysmon_app.feed import SnapshotFeed


class FakeMonitor:
    def __init__(self, snapshot=None):
        self._snapshot = snapshot or {"host": "test", "cpu": 1.0}
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        return self._snapshot


class CountingMonitor:
    """Kazdy sber vrati jiny snapshot - z dat je videt, kdo ho vyrobil."""

    def __init__(self):
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        return {"host": "test", "n": self.calls}


def start_server(monitor=None, feed=None):
    """Nastartuje server na nahodnem portu a vrati (server, port)."""
    monitor = monitor or FakeMonitor()
    feed = feed or SnapshotFeed(monitor)
    srv = server.serve(monitor, feed, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


class LoadStaticTest(unittest.TestCase):
    def test_serves_css_and_js(self):
        # I obsah typu: tabulka pripon a content-type k sobe nic mechanicky
        # nevaze, takze prohozene hodnoty projdou pres "neni None".
        expected = {
            "style.css": "text/css; charset=utf-8",
            "app.js": "application/javascript; charset=utf-8",
        }
        for name, ctype in expected.items():
            asset = server.load_static(name)
            self.assertIsNotNone(asset, name)
            self.assertEqual(asset[1], ctype, name)
            # Nacteny soubor je skutecne ten soubor, ne prazdne bajty.
            self.assertGreater(len(asset[0]), 0, name)

    def test_serves_icon(self):
        asset = server.load_static("icon.svg")
        self.assertIsNotNone(asset)
        self.assertEqual(asset[1], "image/svg+xml")

    def test_rejects_traversal(self):
        self.assertIsNone(server.load_static("../sysmon_app/config.py"))
        self.assertIsNone(server.load_static("../../etc/passwd"))

    def test_rejects_paths_outside_static(self):
        """Ven se nesmi ani pres "..", ani pres absolutni cestu.

        Cile zamerne existuji a maji povolenou priponu: u neexistujici cesty
        (a `../sysmon_app/config.py` je presne ten pripad) vraci None i
        implementace bez kontroly cesty, protoze open() selze sam - test by
        tedy nepinoval nic.

        Absolutni cesta je v zadani proto, ze naivni pojistka `".." in name`
        ji propusti: `os.path.join` s absolutnim druhym argumentem prvni
        argument zahodi a zadne ".." v ni neni.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / "secret.css"
            outside.write_text("tajemstvi", encoding="utf-8")
            static = root / "static"
            static.mkdir()
            (static / "style.css").write_text("ok", encoding="utf-8")
            with mock.patch.object(server, "STATIC_DIR", static):
                # Kontrola, ze podstrcena cesta vubec funguje - jinak by test
                # prosel i s rozbitou cestou k adresari.
                self.assertIsNotNone(server.load_static("style.css"))
                self.assertIsNone(server.load_static("../secret.css"))
                self.assertIsNone(server.load_static(str(outside)))

    def test_rejects_disallowed_extension(self):
        self.assertIsNone(server.load_static("index.html"))
        self.assertIsNone(server.load_static("config.py"))

    def test_rejects_disallowed_extension_for_files_that_exist(self):
        """Allow-list plati i na soubory, ktere ve static/ opravdu lezi.

        `index.html` ani `config.py` ve static/ nejsou, takze je odmitne uz
        chybejici soubor - a allow-list by se pak dal zrusit, aniž by si toho
        sada vsimla. Teprve existujici soubor s nepovolenou priponou ukaze,
        k cemu tam ten seznam je.
        """
        with tempfile.TemporaryDirectory() as tmp:
            static = Path(tmp) / "static"
            static.mkdir()
            (static / "style.css").write_text("ok", encoding="utf-8")
            for name in ("index.html", "config.py", "notes.txt"):
                (static / name).write_text("tajemstvi", encoding="utf-8")
            with mock.patch.object(server, "STATIC_DIR", static):
                # Povolena pripona ve stejnem adresari projit musi - jinak by
                # test prosel i s load_static, ktery nevraci nikdy nic.
                self.assertIsNotNone(server.load_static("style.css"))
                for name in ("index.html", "config.py", "notes.txt"):
                    self.assertIsNone(server.load_static(name), name)


class LoadIndexTest(unittest.TestCase):
    def test_index_has_no_inline_style_or_script(self):
        """CSS a JS patri do static/ - jinak se to tise rozjede s sebou.

        Vsechno se porovnava nad malymi pismeny: nazvy HTML znacek jsou
        case-insensitive, takze `<SCRIPT>alert(1)</SCRIPT>` je stejny inline
        skript jako `<script>` a na holém podtrzeni by prosel.
        """
        lower = server.load_index().lower()
        self.assertNotIn("<style", lower)
        self.assertNotIn("<script>", lower)
        # A kazda znacka zvlast: `<script type="...">` obsahuje kod stejne
        # jako `<script>`, ale s atributy by pres holou kontrolu prosla.
        # `src=` je jediny pripad, kdy je znacka jen odkaz do static/.
        for tag in re.findall(r"<script\b[^>]*>", lower):
            self.assertIn("src=", tag, f"inline skript: {tag}")

    def test_index_references_static_assets(self):
        """Kdyz uz je CSS a JS mimo HTML, musi na ne HTML odkazovat."""
        index = server.load_index()
        self.assertIn('href="/static/style.css"', index)
        self.assertIn('src="/static/app.js"', index)


class StatsTest(unittest.TestCase):
    def setUp(self):
        self.server, self.port = start_server()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)

    def get(self, path, port=None):
        conn = http.client.HTTPConnection("127.0.0.1", port or self.port, timeout=5)
        self.addCleanup(conn.close)
        conn.request("GET", path)
        return conn.getresponse()

    def raw_get(self, path, port=None):
        """Posle GET syrovym socketem a vrati celou odpoved vcetne tela.

        `http.client` si telo precte podle Content-Length, takze telo navic
        (nebo chybejici hlavicku) pres nej videt neni.
        """
        request = (
            f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"
        ).encode()
        with socket.create_connection(("127.0.0.1", port or self.port),
                                      timeout=5) as sock:
            sock.sendall(request)
            chunks = []
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
        return b"".join(chunks)

    def test_stats_returns_json(self):
        response = self.get("/stats")
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.read())["host"], "test")

    def test_stats_takes_the_snapshot_from_the_feed(self):
        """Kdyz feed uz tiknul, /stats jen serializuje - nesbira znovu.

        Prime sebrani by znamenalo soubezne cteni kolektoru s tikem, presne ta
        race, kterou SnapshotFeed odstranuje. Testy nad prazdnym feedem tuhle
        chybu nechyti: do primeho sberu padaji zamerne.

        Dukazy jsou tri a kazdy zabira z jine strany: `n` v datech (druhy sber
        by vratil n=2), pocet sberu a nezmemeny snapshot ve feedu - ten by
        prepsal handler, ktery by si dict pujcil a upravil ho.
        """
        monitor = CountingMonitor()
        feed = SnapshotFeed(monitor)
        feed.publish_once()
        before = copy.deepcopy(feed.latest())
        srv, port = start_server(monitor=monitor, feed=feed)
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)

        payload = json.loads(self.get("/stats", port).read())

        self.assertEqual(payload, before)
        self.assertEqual(feed.latest(), before, "handler prepsal sdileny snapshot")
        self.assertEqual(monitor.calls, 1, "/stats si snapshot sebralo samo")

    def test_stats_falls_back_when_feed_is_empty(self):
        """Nez proběhne první tik, musí /stats sebrat snapshot napřímo."""
        monitor = FakeMonitor()
        server2, port = start_server(monitor=monitor)
        self.addCleanup(server2.shutdown)
        self.addCleanup(server2.server_close)
        self.assertEqual(json.loads(self.get("/stats", port).read())["host"], "test")
        self.assertEqual(monitor.calls, 1)

    def test_index_is_served_at_root(self):
        response = self.get("/")
        self.assertEqual(response.status, 200)
        self.assertIn("text/html", response.getheader("Content-Type"))
        self.assertIn("<!DOCTYPE html>", response.read().decode())

    def test_unknown_path_is_404_with_content_length(self):
        response = self.get("/neexistuje")
        self.assertEqual(response.status, 404)
        self.assertEqual(response.getheader("Content-Length"), "0")
        response.read()

    def test_two_servers_keep_their_own_feed(self):
        """Feed je na serveru, ne na tride Handler - jinak si ho servery vymeni.

        Feed musi mit co vracet: dokud je `latest()` None, `/stats` se na feed
        vubec nepodiva a vymena se schova za primy sber. Presne tudy prosla
        varianta se stavem na tride.

        Riziko je realne: kdo se zepta prvniho serveru, dostane data druheho.
        V teto sade to nikoho nezrani (kazdy test se pta jen sveho serveru),
        ale v Tasku 10 na tom stoji SSE proud.
        """
        monitor_a = FakeMonitor({"host": "prvni"})
        monitor_b = FakeMonitor({"host": "druhy"})
        feed_a = SnapshotFeed(monitor_a)
        feed_b = SnapshotFeed(monitor_b)
        feed_a.publish_once()
        feed_b.publish_once()
        srv_a, port_a = start_server(monitor=monitor_a, feed=feed_a)
        srv_b, port_b = start_server(monitor=monitor_b, feed=feed_b)
        for srv in (srv_a, srv_b):
            self.addCleanup(srv.shutdown)
            self.addCleanup(srv.server_close)

        # feed_b je ten, ktery `serve()` videl naposled.
        self.assertEqual(json.loads(self.get("/stats", port_a).read())["host"], "prvni")
        self.assertEqual(json.loads(self.get("/stats", port_b).read())["host"], "druhy")

    def test_two_servers_keep_their_own_monitor(self):
        """Monitor ze stejneho duvodu - pinuje se fallback nad prazdnym feedem.

        Feed se tu zamerne nespousti: prave tahle vetev se na feed nepodiva,
        takze jako jedina muze prozradit monitor sdileny pres tridu.
        """
        srv_a, port_a = start_server(monitor=FakeMonitor({"host": "prvni"}))
        srv_b, port_b = start_server(monitor=FakeMonitor({"host": "druhy"}))
        for srv in (srv_a, srv_b):
            self.addCleanup(srv.shutdown)
            self.addCleanup(srv.server_close)

        self.assertEqual(json.loads(self.get("/stats", port_a).read())["host"], "prvni")
        self.assertEqual(json.loads(self.get("/stats", port_b).read())["host"], "druhy")

    def test_static_assets_are_served_over_http(self):
        """Asset musi jit stahnout i po drate - ne jen z `load_static`.

        Ostatni testy /static/ volaji `load_static` naprimo, takze je
        nezajima, jestli na tu funkci vubec vede routa: prejmenovany
        `STATIC_PREFIX`, `load_static(path[1:])` nebo `_send(asset…)`
        nahrazene za `_send_empty(404)` projdou celou sadou a pritom vraci
        prazdnou stranku bez CSS i bez JS.
        """
        expected = {
            "/static/style.css": ("style.css", "text/css; charset=utf-8"),
            "/static/app.js": ("app.js", "application/javascript; charset=utf-8"),
        }
        for path, (name, ctype) in expected.items():
            with self.subTest(path=path):
                response = self.get(path)
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader("Content-Type"), ctype)
                # Bajt po bajtu proti souboru na disku: telo jine delky nebo
                # jineho souboru by pres "neni to prazdne" proslo.
                self.assertEqual(response.read(),
                                 (server.STATIC_DIR / name).read_bytes())

    def test_404_has_no_body_bytes(self):
        """`Content-Length: 0` musi byt pravda, ne jen hlavicka.

        Kdyby odpoved telo poslala a pritom ohlásila nulu, klient si ho precte
        jako zacatek dalsi odpovedi na tomtez spojeni - a HTTP/1.1 spojeni
        zustava otevrene, takze se rozjede framing vsech dalsich pozadavku.
        Syrovy socket to vidi; `http.client` ne.
        """
        for path in ("/neexistuje", "/static/nic.css"):
            with self.subTest(path=path):
                head, _, body = self.raw_get(path).partition(b"\r\n\r\n")
                self.assertIn(b" 404 ", head.split(b"\r\n")[0], head)
                self.assertIn(b"Content-Length: 0", head)
                self.assertEqual(body, b"")


if __name__ == "__main__":
    unittest.main()
