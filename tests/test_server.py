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
from tests import web_fixture


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
            "assets/index-abc123.js": "application/javascript; charset=utf-8",
        }
        with web_fixture.fake_web() as (_root, static, _index):
            with mock.patch.object(server, "STATIC_DIR", static):
                for name, ctype in expected.items():
                    asset = server.load_static(name)
                    self.assertIsNotNone(asset, name)
                    self.assertEqual(asset[1], ctype, name)
                    # Nacteny soubor je skutecne ten soubor, ne prazdne bajty.
                    self.assertGreater(len(asset[0]), 0, name)

    def test_serves_icon(self):
        with web_fixture.fake_web() as (_root, static, _index):
            with mock.patch.object(server, "STATIC_DIR", static):
                asset = server.load_static("icon.svg")
                self.assertIsNotNone(asset)
                self.assertEqual(asset[1], "image/svg+xml")

    def test_rejects_traversal(self):
        """Cil existuje a ma povolenou priponu - odmitne ho jen kontrola cesty.

        Varianta s `../config.py` tu drive byla a nepinovala nic: `.py` neni
        v allow-listu pripon, takze None prijde driv, nez se vubec resi cesta.
        """
        with web_fixture.fake_web() as (_root, static, _index):
            with mock.patch.object(server, "STATIC_DIR", static):
                (static.parent / "secret.css").write_text("x", encoding="utf-8")
                self.assertIsNone(server.load_static("../secret.css"))

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


def check_no_executable_inline_code(case, html):
    """Vsechny kontroly inline kodu na jednom miste.

    Pouziva ji fixture i realny build - bez toho by pin po vzniku buildu
    meril jen nas vlastni literál ve fixture, ne to, co produkt servíruje.

    Zakazany je spustitelny inline kod, ne kazda zminka o scriptu: Vite ma
    `<script type="module" src="/static/assets/...">` a to je legitimni -
    kod je v souboru, ne v HTML.

    Hleda se ve skutecnych znackach: skenovat cely text znamena falesny
    poplach na bezne prose (" text only = 5 " vypada jako on...= atribut).

    Vsechno se porovnava nad malymi pismeny: nazvy HTML znacek jsou
    case-insensitive, takze `<SCRIPT>alert(1)</SCRIPT>` je stejny inline
    skript jako `<script>` a na holem podtrzeni by prosel.
    """
    lower = html.lower()
    case.assertNotIn("<style", lower, "CSS patri do static/")
    for body in re.findall(r"<script\b[^>]*>(.*?)</script>", lower, re.S):
        case.assertEqual(body.strip(), "", f"inline skript: {body!r}")
    for tag in re.findall(r"<script\b[^>]*>", lower):
        case.assertIn("src=", tag, f"skript bez src: {tag}")
    for tag in re.findall(r"<[a-z][^>]*>", lower):
        if re.search(r"\son[a-z]+\s*=", tag):
            case.fail(f"inline obsluha udalosti: {tag!r}")
        for ref in re.findall(r'(?:src|href)\s*=\s*"([^"]*)"', tag):
            # javascript: a data: jsou v src/href zakazane zamerne: je to
            # spustitelny kod v odkazu a pin na "telo znacky" by je pustil.
            #
            # Planovany tvar indexu zadne data: nevyrobi. Ikona jde pres
            # public/, a root-absolutni odkaz Vite neinlinuje nikdy; `link`
            # s rel ze seznamu noInlineLinkRels (icon, stylesheet, preload,
            # ...) se neinlinuje taky.
            #
            # Obecne to ale neplati: relativne odkazany obrazek pod inline
            # limitem (~4 kB) Vite vlozi do <img src="data:..."> - namereno
            # na Vite 8.3.4. Kdyby pin na buildu zapalil, je to hlasite
            # a ma se to vysetrit, ne rozsirit pin.
            for scheme in ("javascript:", "data:"):
                case.assertFalse(ref.startswith(scheme),
                                 f"spustitelny odkaz {ref!r} v {tag!r}")


class LoadIndexTest(unittest.TestCase):
    def test_fixture_index_has_no_executable_inline_code(self):
        """Tvar, ktery vydava Vite build, nesmi mit spustitelny inline kod.

        Test se jmenuje podle fixture zamerne: meri nas literál. Ze pin ma
        zuby, dokazuje `test_pin_fires_on_inline_script`, a ze plati i pro
        produkt, `test_real_build_index_has_no_executable_inline_code`.
        """
        with web_fixture.fake_web() as (_root, _static, index):
            with mock.patch.object(server, "WEB_DIR", index.parent):
                text = server.load_index()
        check_no_executable_inline_code(self, text)

    def test_pin_fires_on_inline_script(self):
        """Pin musi umet spadnout - jinak nic nemeri."""
        bad = '<!doctype html><html><body><script>alert(1)</script></body></html>'
        with web_fixture.fake_web(index=bad) as (_root, _static, index):
            with mock.patch.object(server, "WEB_DIR", index.parent):
                text = server.load_index()
        with self.assertRaises(AssertionError):
            check_no_executable_inline_code(self, text)

    @unittest.skipUnless((server.WEB_DIR / "index.html").exists(),
                         "chybi build (npm run build ve frontend/)")
    def test_real_build_index_has_no_executable_inline_code(self):
        check_no_executable_inline_code(self, server.load_index())

    def test_index_references_hashed_static_assets(self):
        """Kdyz uz je CSS a JS mimo HTML, musi na ne HTML odkazovat."""
        with web_fixture.fake_web() as (_root, _static, index):
            with mock.patch.object(server, "WEB_DIR", index.parent):
                text = server.load_index()
        self.assertIn('src="/static/assets/', text)
        self.assertIn('href="/static/assets/', text)


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
        """Trasa / posle presne to, co je na disku - ne jen nejake HTML.

        I tahle trasa cte fixture, ne repo web/ - jinak by testy drzely build.
        Pin na doctype sam by ale prosla konstanta `<!doctype html><html>`:
        trasa, ktera `load_index()` nikdy nezavola, musi spadnout.
        """
        with web_fixture.fake_web() as (_root, _static, index):
            with mock.patch.object(server, "WEB_DIR", index.parent):
                expected = server.load_index()
                response = self.get("/")
        self.assertEqual(response.status, 200)
        self.assertIn("text/html", response.getheader("Content-Type"))
        self.assertEqual(response.read().decode(), expected)

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

        Podadresar `assets/` je tu proto, ze ho Vite build pouziva: trasa
        musi umet i vnorenou cestu, ne jen soubor v koreni static/.

        Server ze `setUp` staci: `load_static` cte modulovou `STATIC_DIR` az
        v dobe volani, takze patch plati i pro uz bezici server. Kdyby ji
        nekdo presunul na instanci, test spadne hlasite - a to je dobre.
        """
        with web_fixture.fake_web() as (_root, static, _index):
            with mock.patch.object(server, "STATIC_DIR", static):
                expected = {
                    "/static/style.css": (
                        "style.css", "text/css; charset=utf-8"),
                    "/static/assets/index-abc123.js": (
                        web_fixture.ASSET_NAME,
                        "application/javascript; charset=utf-8"),
                }
                for path, (name, ctype) in expected.items():
                    with self.subTest(path=path):
                        response = self.get(path)
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.getheader("Content-Type"), ctype)
                        # Bajt po bajtu proti souboru na disku: telo jine
                        # delky nebo jineho souboru by pres "neni to prazdne"
                        # proslo.
                        self.assertEqual(response.read(),
                                         (static / name).read_bytes())

    def test_every_static_reference_in_index_is_served(self):
        """Vse, na co index odkazuje pod /static/, musi jit stahnout.

        Tohle pinuje allow-list pripon a vnorenou cestu na skutecnych odkazech
        indexu: kdyby build odkazoval na .css, ktere trasa nevyda, stranka se
        nacte bez vzhledu a jednotkove testy by mlcely.
        """
        with web_fixture.fake_web() as (_root, static, index):
            with mock.patch.object(server, "WEB_DIR", index.parent), \
                 mock.patch.object(server, "STATIC_DIR", static):
                html = server.load_index()
                refs = re.findall(r'(?:src|href)="(/static/[^"]+)"', html)
                self.assertTrue(refs, "index na nic pod /static/ neodkazuje")
                for ref in refs:
                    with self.subTest(ref=ref):
                        response = self.get(ref)
                        self.assertEqual(response.status, 200, ref)
                        # Neprectene telo pri zavreni spoje posle RST; server
                        # pak v keep-alive smycce skonci tracebackem na stderr.
                        response.read()

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


class CacheHeadersTest(unittest.TestCase):
    """Hashovany asset se muze cachovat navzdy, index ne."""

    def setUp(self):
        self.web = web_fixture.fake_web()
        root, static, _index = self.web.__enter__()
        self.addCleanup(self.web.__exit__, None, None, None)
        self.patch_web = mock.patch.object(server, "WEB_DIR", root)
        self.patch_static = mock.patch.object(server, "STATIC_DIR", static)
        self.patch_web.start()
        self.patch_static.start()
        self.addCleanup(self.patch_web.stop)
        self.addCleanup(self.patch_static.stop)
        self.server, self.port = start_server()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)

    def get(self, path):
        """Precte i telo: neprectene telo pri zavreni spoje posle RST.

        Server po odpovedi zustava v keep-alive a ceka na dalsi request line;
        RST z nej udela ConnectionResetError, ktery socketserver vytiskne jako
        traceback. Testy kontroluji jen hlavicky, takze telo staci precist
        a zahodit - ale precist se musi.
        """
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(conn.close)
        conn.request("GET", path)
        response = conn.getresponse()
        response.read()
        return response

    def test_hashed_asset_is_immutable(self):
        response = self.get(f"/static/{web_fixture.ASSET_NAME}")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Cache-Control"),
                         "public, max-age=31536000, immutable")

    def test_hashed_css_asset_is_immutable(self):
        """i CSS: mutant, ktery cacheuje immutable jen podle pripony .js, jinak projde."""
        response = self.get(f"/static/{web_fixture.STYLE_NAME}")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Cache-Control"),
                         "public, max-age=31536000, immutable")

    def test_index_and_unhashed_asset_are_no_store(self):
        for path in ("/", "/static/icon.svg", "/static/style.css", "/stats"):
            with self.subTest(path=path):
                self.assertEqual(self.get(path).getheader("Cache-Control"),
                                 "no-store")


class MissingBuildTest(unittest.TestCase):
    """Server startovany bez buildu: / rekne proc, misto aby spadl."""

    def setUp(self):
        self.empty = tempfile.TemporaryDirectory()
        self.addCleanup(self.empty.cleanup)
        self.patch_web = mock.patch.object(server, "WEB_DIR",
                                           Path(self.empty.name))
        self.patch_web.start()
        self.addCleanup(self.patch_web.stop)
        self.server, self.port = start_server()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)

    def test_root_says_it_in_czech_instead_of_traceback(self):
        with mock.patch.object(self.server, "handle_error") as handle_error:
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
            self.addCleanup(conn.close)
            conn.request("GET", "/")
            response = conn.getresponse()
            body = response.read().decode("utf-8")
        self.assertEqual(response.status, 503)
        self.assertEqual(response.getheader("Content-Type"),
                         "text/plain; charset=utf-8")
        self.assertIn("zbuilděný", body)
        self.assertIn("npm ci && npm run build", body)
        # Traceback na stderr znamena, ze vyjimka prosla do socketserveru.
        handle_error.assert_not_called()


class BuildDisappearsTest(unittest.TestCase):
    """Build zmizi za behu: / to rekne vetou, /stats funguje dal."""

    def setUp(self):
        self.web = web_fixture.fake_web()
        root, static, self.index = self.web.__enter__()
        self.addCleanup(self.web.__exit__, None, None, None)
        self.patch_web = mock.patch.object(server, "WEB_DIR", root)
        self.patch_static = mock.patch.object(server, "STATIC_DIR", static)
        self.patch_web.start()
        self.patch_static.start()
        self.addCleanup(self.patch_web.stop)
        self.addCleanup(self.patch_static.stop)
        self.server, self.port = start_server()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)

    def get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(conn.close)
        conn.request("GET", path)
        return conn.getresponse()

    def test_root_explains_the_missing_build_and_stats_still_work(self):
        with mock.patch.object(self.server, "handle_error") as handle_error:
            first = self.get("/")
            self.assertEqual(first.status, 200)
            # Telo se musi precist i u odpovedi, kterou test jinak nezkouma:
            # neprectene telo pri zavreni spoje posle RST a ten skonci jako
            # traceback z keep-alive smycky serveru.
            first.read()

            self.index.unlink()

            response = self.get("/")
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 503)
            self.assertEqual(response.getheader("Content-Type"),
                             "text/plain; charset=utf-8")
            self.assertIn("zbuilděný", body)
            self.assertIn("npm ci && npm run build", body)

            # Chovani /stats se tim nemění.
            stats = self.get("/stats")
            self.assertEqual(stats.status, 200)
            self.assertEqual(json.loads(stats.read())["host"], "test")

        handle_error.assert_not_called()


@unittest.skipUnless((server.WEB_DIR / "index.html").exists(),
                     "chybi build (npm run build ve frontend/)")
class RealBuildCacheHeadersTest(unittest.TestCase):
    """Pin nad skutecnym buildem, ne jen nad fixture, kterou si test pise sam."""

    def setUp(self):
        self.server, self.port = start_server()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)

    def get(self, path):
        """Precte i telo - neprectene telo pri zavreni spoje posle RST."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(conn.close)
        conn.request("GET", path)
        response = conn.getresponse()
        response.read()
        return response

    def test_real_build_serves_cache_headers_over_http(self):
        html = server.load_index()
        js = re.search(r'src="(/static/assets/[^"]+\.js)"', html)
        css = re.search(r'href="(/static/assets/[^"]+\.css)"', html)
        self.assertIsNotNone(js, "build neodkazuje na hashovany .js")
        self.assertIsNotNone(css, "build neodkazuje na hashovany .css")

        expected = {
            "/": "no-store",
            js.group(1): "public, max-age=31536000, immutable",
            css.group(1): "public, max-age=31536000, immutable",
            "/static/icon.svg": "no-store",
        }
        for path, cache in expected.items():
            with self.subTest(path=path):
                response = self.get(path)
                self.assertEqual(response.status, 200, path)
                self.assertEqual(response.getheader("Cache-Control"), cache, path)


class BusyPortTest(unittest.TestCase):
    def test_busy_port_raises_oserror(self):
        """Druhy bind na temz portu musi selhat - na tom stoji hlaska v __main__."""
        first, port = start_server()
        self.addCleanup(first.shutdown)
        self.addCleanup(first.server_close)
        monitor = FakeMonitor()
        feed = SnapshotFeed(monitor)
        with self.assertRaises(OSError):
            server.serve(monitor, feed, "127.0.0.1", port)


if __name__ == "__main__":
    unittest.main()
