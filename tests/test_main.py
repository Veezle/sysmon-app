"""Vstupni bod `python3 -m sysmon_app`: argumenty, hlaseni chyb, poradi startu.

Zadny test tu nespousti demona a zadny nebinduje 8430: na stroji muze bezet
sysmon (8420) i uzivatelova konfigurace s jinym portem. `serve` je proto
podstrceny obalem, ktery si poznamena, s cim byl zavolany. Vyjimkou je
`BusyPortTest`, ktery se na skutecne obsazeny port bindnout pokusi - ale na
nahodnem.
"""

import contextlib
import errno
import http.client
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from sysmon_app import __main__ as vstupni_bod
from sysmon_app import server as server_modul
from sysmon_app.config import DEFAULT_HOST, DEFAULT_PORT
from sysmon_app.feed import SnapshotFeed


class FakeMonitor:
    """Monitor bez hardwaru: pocita, kolikrat se snapshot opravdu sebral.

    Pocet sberu je tu hlavni dukaz - `prime()` ani kontrakt snapshotu se
    neresi, jen to, jestli se kolektory cetly jednou, nebo dvakrat.
    """

    def __init__(self, settings=None, log=None):
        self.settings = settings
        self.log = log if log is not None else []
        self.snapshots = 0
        self.primed = 0

    def prime(self):
        self.primed += 1
        self.log.append("prime")

    def start_background(self):
        self.log.append("start_background")

    def snapshot(self):
        self.snapshots += 1
        self.log.append("snapshot")
        return {"host": "test", "n": self.snapshots}


class FakeFeed:
    """Feed bez vlakna: tik se deje jen tehdy, kdyz ho nekdo zavola.

    Diky tomu je pocet sberu dany poradim volani v `main()`, ne casovanim -
    soubezny tik by jinak test na "prvni /stats nesbira samo" udelal
    nedeterministickym.
    """

    def __init__(self, monitor, interval=None):
        self._monitor = monitor
        self._snapshot = None
        self.publish_calls = 0
        self.started = False
        self.stopped = False

    def publish_once(self):
        self.publish_calls += 1
        self._snapshot = self._monitor.snapshot()

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def latest(self):
        return self._snapshot

    def snapshot_seq(self):
        return self.publish_calls

    def is_running(self):
        return self.started and not self.stopped


class IdleServer:
    """Nahrada serveru: `serve_forever()` se vrati hned, misto aby blokoval."""

    def __init__(self):
        self.forever_calls = 0

    def serve_forever(self):
        self.forever_calls += 1


class MainTestCase(unittest.TestCase):
    def setUp(self):
        # Uzivatelova ~/.config by jinak rozhodovala o vysledku testu.
        self.config_home = tempfile.TemporaryDirectory()
        self.addCleanup(self.config_home.cleanup)
        env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.config_home.name})
        env.start()
        self.addCleanup(env.stop)

        # main() ma branu `load_index() is None -> rc 2`. Bez podstrzeneho
        # WEB_DIR by v cerstvem klonu (bez buildu) spadlo 11 testu startu;
        # obsah indexu je tu jen aby brana prosla, tvary se netestuji.
        self.web = tempfile.TemporaryDirectory()
        self.addCleanup(self.web.cleanup)
        (Path(self.web.name) / "index.html").write_text(
            "<!doctype html><html></html>", encoding="utf-8")
        web_patch = mock.patch.object(server_modul, "WEB_DIR", Path(self.web.name))
        web_patch.start()
        self.addCleanup(web_patch.stop)

        self.serve_calls = []       # (host, port), se kterymi main zavolal serve()
        self.servers = []           # to, co main dostal ze serve()
        self.monitors = []
        self.feeds = []
        self.live_servers = []      # skutecne servery, ktere je treba uklidit
        self.order = []             # poradi kroku startu
        self.out, self.err = io.StringIO(), io.StringIO()
        self.addCleanup(self._close_servers)

    def _close_servers(self):
        for srv in self.live_servers:
            srv.shutdown()
            srv.server_close()

    def write_config(self, text):
        path = Path(self.config_home.name) / "sysmon-app" / "config.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def run_main(self, argv, serve=None, feed_cls=FakeFeed):
        """Zavola main() s podstrcenym Monitorem, feedem a serve().

        Vraci (navratovy_kod, stdout, stderr). Kdyz main() vyhodi (argparse
        u spatneho argumentu), texty zustanou v self.out/self.err.
        """
        self.out, self.err = io.StringIO(), io.StringIO()

        def make_monitor(settings=None):
            self.order.append("monitor")
            monitor = FakeMonitor(settings, self.order)
            self.monitors.append(monitor)
            return monitor

        def make_feed(monitor, interval=None):
            feed = feed_cls(monitor)
            self.feeds.append(feed)
            return feed

        with mock.patch.object(vstupni_bod, "Monitor", make_monitor), \
             mock.patch.object(vstupni_bod, "SnapshotFeed", make_feed), \
             mock.patch.object(vstupni_bod, "serve", serve or self.stand_in_serve), \
             contextlib.redirect_stdout(self.out), \
             contextlib.redirect_stderr(self.err):
            code = vstupni_bod.main(argv)
        return code, self.out.getvalue(), self.err.getvalue()

    def stand_in_serve(self, monitor, feed, host, port):
        """Zaznamena argumenty a vrati server, ktery hned skonci."""
        self.serve_calls.append((host, port))
        self.order.append("serve")
        server = IdleServer()
        self.servers.append(server)
        return server

    def live_bind_serve(self, monitor, feed, host, port):
        """Skutecny bind na pozadovany port - bez `serve_forever`.

        Bind musi byt opravdovy (na tom stoji errno), ale blokovat se nesmi:
        kdyby mutant poslal bind na volny port, `serve_forever()` by se
        rozbehl a test by visel, misto aby spadl. Visici test vypada jako
        bezici - a to je horsi nez selhani.
        """
        srv = server_modul.serve(monitor, feed, host, port)
        # Uklizi se jen `server_close()`: `shutdown()` ceka na dokonceni
        # `serve_forever()`, ktere tu nikdy nebezi - a viselo by to tu stejne
        # jako samotny mutant.
        self.addCleanup(srv.server_close)
        srv.serve_forever = lambda: None
        return srv

    def live_serve(self, monitor, feed, host, port):
        """Skutecny server na nahodnem portu - jen `serve_forever` neblokuje.

        Port z argumentu se jen poznamena; binduje se na nulu, aby test
        nesahal na port z konfigurace (a uz vubec ne na 8430). Route
        /stats se tim probere po drate, coz podstrceny IdleServer neumi.
        """
        self.serve_calls.append((host, port))
        self.order.append("serve")
        srv = server_modul.serve(monitor, feed, "127.0.0.1", 0)
        self.live_servers.append(srv)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        server = IdleServer()
        self.servers.append(server)
        return server


class StartTest(MainTestCase):
    """Kriteria 1 a 2: vychozi port, vypsana URL, prebiti konfigurace."""

    def test_starts_on_8430_and_prints_the_url(self):
        code, out, err = self.run_main([])

        self.assertEqual(code, 0)
        # Hodnota je tu dvakrat: jednou jako literál (to je to, co kritérium
        # pojmenovava) a jednou pres konstanty (aby bylo videt, odkud je).
        self.assertEqual(self.serve_calls, [("0.0.0.0", 8430)])
        self.assertEqual(self.serve_calls, [(DEFAULT_HOST, DEFAULT_PORT)])
        self.assertIn("http://0.0.0.0:8430", out)
        self.assertIn("http://localhost:8430", out)
        self.assertEqual(err, "")
        # A hlavne: server opravdu obsluhuje. Bez `serve_forever()` by se
        # vypsala URL a proces by hned skoncil.
        self.assertEqual(self.servers[0].forever_calls, 1)

    def test_config_file_decides_what_is_used(self):
        """Bez argumentu plati config.toml - jinak by --port byl jedina cesta."""
        self.write_config('host = "192.168.1.5"\nport = 9100\n')

        code, out, _ = self.run_main([])

        self.assertEqual(code, 0)
        self.assertEqual(self.serve_calls, [("192.168.1.5", 9100)])
        self.assertIn("http://192.168.1.5:9100", out)

    def test_cli_flags_override_the_config_file(self):
        self.write_config('host = "192.168.1.5"\nport = 9100\n')

        code, out, _ = self.run_main(["--host", "127.0.0.1", "--port", "9101"])

        self.assertEqual(code, 0)
        self.assertEqual(self.serve_calls, [("127.0.0.1", 9101)])
        # URL musi odpovidat tomu, na cem se opravdu posloucha. Kdyby se
        # vypsala hodnota z konfigurace, sel by uzivatel na nespravny port.
        self.assertIn("http://127.0.0.1:9101", out)
        self.assertNotIn("9100", out)


class BusyPortTest(MainTestCase):
    """Kriterium 3: obsazeny port konci vetou, ktera port pojmenuje."""

    def test_busy_port_ends_with_a_sentence_naming_the_port(self):
        """Bind se zkousi doopravdy - zadna podstrcena vynimka.

        Hlaska se rozhoduje podle `errno`, takze test s `OSError("neco")`
        by prosel i tehdy, kdyby skutecny bind vracel errno jine (nebo zadne)
        a uzivatel by dostal vetu o necem jinem, nez co se stalo.
        """
        listener = socket.socket()
        self.addCleanup(listener.close)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        code, out, err = self.run_main(
            ["--host", "127.0.0.1", "--port", str(port)], serve=self.live_bind_serve,
        )

        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        # Port musi byt ve vete sam, ne jen v URL za ni: "Port je obsazeny"
        # uzivateli nerekne, ktery port.
        self.assertIn(f"Port {port} je obsazený", err)
        self.assertNotIn("Traceback", err)
        # Vlakno feedu po chybe nezustane bezet.
        self.assertTrue(self.feeds[0].stopped)

    def test_real_busy_bind_carries_addrinuse(self):
        """Predpoklad vetve v `report_bind_error`: skutecny bind da EADDRINUSE.

        Bez tohohle pinu by stacilo, aby skutecny bind vracel errno None,
        a uzivatel by u obsazeneho portu dostal vetu "nepodařilo se
        poslouchat" - testy nad podstrcenou vynimkou to nepoznaji.
        """
        listener = socket.socket()
        self.addCleanup(listener.close)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        with self.assertRaises(OSError) as caught:
            server_modul.serve(FakeMonitor(), FakeFeed(None), "127.0.0.1", port)

        self.assertEqual(caught.exception.errno, errno.EADDRINUSE)


class BindErrorMessageTest(MainTestCase):
    """Kazda pricina selhani bindu dostane vlastni vetu.

    Hlaska brani `errno`, takze sama vetev "obsazeny port" nic nepinuuje:
    kdyby vsechno koncilo vetou o obsazenem portu, uzivatel s `--port 80`
    (EACCES) nebo s neexistujici adresou by se vydal spatnym smerem.
    `report_bind_error` je proto testovany naprimo - vyvolat EACCES nebo
    EADDRNOTAVAIL skutecnym bindem jde jen na stroji, kde ta podminka
    zrovna plati (a root EACCES nevyvola vubec).
    """

    def message_for(self, exc, host="127.0.0.1", port=8430):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            vstupni_bod.report_bind_error(exc, host, port)
        return err.getvalue()

    def test_busy_port_is_the_only_one_about_being_busy(self):
        """Veta "port je obsazeny" se nesmi objevit u jinych pricin."""
        others = {
            "EACCES": PermissionError(errno.EACCES, "Permission denied"),
            "EADDRNOTAVAIL": OSError(errno.EADDRNOTAVAIL, "Cannot assign requested address"),
            "gaierror": socket.gaierror(-2, "Name or service not known"),
            "jina": OSError(errno.EINVAL, "Invalid argument"),
        }
        for label, exc in others.items():
            with self.subTest(cause=label):
                message = self.message_for(exc, host="10.1.2.3")
                self.assertNotIn("obsazen", message)
                self.assertNotIn("Traceback", message)

    def test_each_cause_names_what_actually_happened(self):
        """Veta musi pojmenovat to, co je spatne.

        U obsazeneho portu a u chybejiciho opravneni je to port; u adresy,
        ktera na stroji neni, je spatne jmeno hostitele - a veta o portu by
        uzivatele poslala menit neco, co je v poradku.
        """
        cases = {
            errno.EADDRINUSE: (
                OSError(errno.EADDRINUSE, "Address already in use"),
                "obsazen", {"port": "9101"},
            ),
            errno.EACCES: (
                PermissionError(errno.EACCES, "Permission denied"),
                "oprávnění", {"port": "9101"},
            ),
            errno.EADDRNOTAVAIL: (
                OSError(errno.EADDRNOTAVAIL, "Cannot assign requested address"),
                "neexistuje", {"host": "10.1.2.3"},
            ),
        }
        for code, (exc, expected, named) in cases.items():
            with self.subTest(errno=code):
                message = self.message_for(exc, host="10.1.2.3", port=9101)
                self.assertIn(expected, message)
                for what, value in named.items():
                    self.assertIn(value, message, what)

    def test_unresolvable_host_names_the_host(self):
        """Preklep v hostiteli ma vetu o hostiteli, ne o portu.

        `gaierror` ma errno zaporne (EAI_*), takze se pozna podle typu
        vyjimky - a veta o portu by tu byla vedle.
        """
        message = self.message_for(
            socket.gaierror(-2, "Name or service not known"), host="preklep.invalid",
        )
        self.assertIn("preklep.invalid", message)
        self.assertIn("přeložit", message)
        self.assertNotIn("8430", message)

    def test_unknown_cause_still_says_something(self):
        """I nezname errno musi dat vetu s hostem, portem a vtipem OS.

        Sem pada i `gaierror` s jinym EAI kodem - kdyby tahle vetev chybela,
        vyjimka by prosla do tracebacku.
        """
        message = self.message_for(
            OSError(errno.EINVAL, "Invalid argument"), host="10.1.2.3", port=9101,
        )
        self.assertIn("10.1.2.3", message)
        self.assertIn("9101", message)
        self.assertIn("Invalid argument", message)


class BrokenConfigTest(MainTestCase):
    """Kriterium 4: rozbita konfigurace konci vetou s cestou k souboru."""

    def test_broken_config_ends_with_a_sentence_and_the_path(self):
        cases = {
            "spatny typ": 'port = "nic"\n',
            "mimo rozsah": "port = 99999\n",
            "neznamy klic": "napis = 1\n",
            "rozjete TOML": "port = \n",
        }
        for label, text in cases.items():
            with self.subTest(label=label):
                path = self.write_config(text)

                code, out, err = self.run_main([])

                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertIn(str(path), err)
                self.assertIn("Chyba v konfiguraci", err)
                self.assertNotIn("Traceback", err)
                # Nic se nesmi rozjet: kontrola je pred stavbou monitoru.
                self.assertEqual(self.serve_calls, [])
                self.assertEqual(self.monitors, [])

    def test_missing_build_ends_with_a_sentence_and_the_command(self):
        """Bez buildu nema smysl startovat - a nesmi to byt traceback."""
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(server_modul, "WEB_DIR", Path(tmp)):
                code, out, err = self.run_main([])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn(str(Path(tmp) / "index.html"), err)
        self.assertIn("npm ci && npm run build", err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(self.serve_calls, [])
        self.assertEqual(self.monitors, [])


class PortArgumentTest(MainTestCase):
    """`--port` je uzivatelsky vstup, takze konci vetou jako vsechno ostatni."""

    def test_invalid_port_is_a_czech_sentence(self):
        """Rozsah hlida uz argparse - `socket.bind` by jinak vyhodil OverflowError.

        OverflowError neni OSError, takze by ho `except OSError` v main()
        nechytil a uzivatel by dostal traceback. Mereno na `--port 70000`
        a `--port -1` jeste pred touhle opravou.
        """
        cases = {
            "70000": "1-65535",
            "-1": "1-65535",
            # Nula: bind by uspel, ale na nahodnem portu - vypsana URL by lhala.
            "0": "1-65535",
            "abc": "číslo portu",
        }
        for text, expected in cases.items():
            with self.subTest(port=text):
                with self.assertRaises(SystemExit) as caught:
                    self.run_main(["--port", text])

                err = self.err.getvalue()
                self.assertEqual(caught.exception.code, 2)
                self.assertIn(expected, err)
                self.assertNotIn("Traceback", err)
                self.assertEqual(self.serve_calls, [])


class StartupOrderTest(MainTestCase):
    """Poradi startu: prime i prvni snapshot musi byt hotovy pred serverem."""

    def test_rates_are_primed_before_the_server_starts(self):
        """Bez prime() je prvni /stats sama nula - u rate metrik vzdy.

        Pinuje se poradi, ne hodnoty: ty zavisí na tom, co stroj prave dela,
        a na tom, jestli vubec ma sitove rozhrani. Vlastnost, ktera se da
        tvrdit vzdy, je "prime probehl pred serve" - a to je presne to, co
        vypnuti prime() v main() rozbije.
        """
        code, _, _ = self.run_main([])

        self.assertEqual(code, 0)
        self.assertEqual(self.monitors[0].primed, 1)
        self.assertLess(self.order.index("prime"), self.order.index("serve"))

    def test_slow_collectors_are_started_and_feed_keeps_ticking(self):
        """Bez `start_background()` by docker a baterie zustaly prazdne,
        bez `start()` by se po prvnim snapshotu uz nikdy netiklo - a cisla
        v okne by zamrzla. Ani jedno se nijak jinak neprojevi."""
        code, _, _ = self.run_main([])

        self.assertEqual(code, 0)
        self.assertIn("start_background", self.order)
        self.assertTrue(self.feeds[0].started, "feed se nerozjede")

    def test_snapshot_is_published_before_the_feed_thread_starts(self):
        """Poradi `publish_once()` a `start()`, ne jen existence snapshotu.

        `start()` zvedne vlakno, ktere publikuje samo - jestli stihne tiknout
        pred `serve()`, je casovani, ne garance. S bezicim vlaknem je test na
        "snapshot existuje pred serve" jen pravdepodobnostni, takze se pinuje
        poradi volani: synchronni publikovani musi byt prvni.
        """
        log = []

        class OrderFeed(SnapshotFeed):
            def publish_once(self):
                log.append("publish_once")
                return super().publish_once()

            def start(self):
                log.append("start")
                return super().start()

        code, _, _ = self.run_main(["--port", "9104"], feed_cls=OrderFeed)

        self.assertEqual(code, 0)
        # Dalsi `publish_once` uz patri tikajicimu vlaknu - tvrdi se jen
        # prvni dve volani.
        self.assertEqual(log[:2], ["publish_once", "start"])

    def test_first_snapshot_exists_before_the_server_starts(self):
        """`start()` snapshot nezaruci - jen zvedne vlakno.

        Mezi `start()` a prvnim tikem je `latest()` jeste None a /stats v tom
        okne sbira naprimo, soubezne s tikem. Synchronni `publish_once()`
        pred `serve()` to okno zavira: snapshot je hotovy driv, nez server
        zacne poslouchat.
        """
        code, _, _ = self.run_main([])

        self.assertEqual(code, 0)
        self.assertLess(self.order.index("snapshot"), self.order.index("serve"))
        self.assertEqual(self.monitors[0].snapshots, 1)


class FirstStatsTest(MainTestCase):
    def test_first_stats_only_serializes_the_feed_snapshot(self):
        """Prvni /stats po startu nesmi kolektory precist znovu.

        `_snapshot_now()` pada na primy sber, kdyz `latest()` je None. Kdyby
        v main() `publish_once()` chybelo, nebo bezelo az po `serve()`, prvni
        /stats by si snapshot sebralo samo - a to soubezne s tikem feedu.
        Pocet sberu to pozna; test se ptá po drate, ne na feed naprimo.
        """
        code, _, err = self.run_main(
            ["--host", "127.0.0.1", "--port", "9102"], serve=self.live_serve,
        )
        self.assertEqual(code, 0, err)

        monitor = self.monitors[0]
        self.assertEqual(monitor.snapshots, 1, "prvni snapshot nevznikl prave jednou")

        port = self.live_servers[0].server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        self.addCleanup(conn.close)
        conn.request("GET", "/stats")
        response = conn.getresponse()
        payload = json.loads(response.read())

        self.assertEqual(response.status, 200)
        # Data jsou ta z feedu, ne z noveho sberu.
        self.assertEqual(payload, {"host": "test", "n": 1})
        self.assertEqual(monitor.snapshots, 1, "/stats si snapshot sebralo samo")


# Skript pro podproces v InterruptTest. `KeyboardInterrupt` uvnitr testovaciho
# procesu unittest zamerne nechyta (aby slo testy preusit Ctrl+C), takze by
# srazil cely test runner - a to presne ve chvili, kdy se `except
# KeyboardInterrupt` rozbije. Podproces umre sam, runner zustane.
SIGINT_SCRIPT = """
import sys
from unittest import mock

from sysmon_app import __main__ as vstupni_bod


class Monitor:
    def __init__(self, settings=None):
        pass

    def prime(self):
        pass

    def start_background(self):
        pass

    def snapshot(self):
        return {"host": "test"}


class Feed:
    def __init__(self, monitor, interval=None):
        pass

    def publish_once(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def latest(self):
        return {"host": "test"}

    def snapshot_seq(self):
        return 1

    def is_running(self):
        return False


class Server:
    def serve_forever(self):
        raise KeyboardInterrupt


with mock.patch.object(vstupni_bod, "Monitor", Monitor), \\
        mock.patch.object(vstupni_bod, "SnapshotFeed", Feed), \\
        mock.patch.object(vstupni_bod, "load_index",
                          lambda: "<!doctype html><html></html>"), \\
        mock.patch.object(vstupni_bod, "serve", lambda *args: Server()):
    sys.exit(vstupni_bod.main([]))
"""


class InterruptTest(MainTestCase):
    """Kriterium 3 a 4 plati i pro Ctrl+C: veta a navratovy kod 0."""

    def test_ctrl_c_ends_cleanly(self):
        """Zkousi se v cistem procesu, aby se pinovalo i to, jak proces skonci.

        Uvnitr testovaciho procesu by `KeyboardInterrupt` prosla az ven
        (unittest ji zamerne nechytá) a srazila by celou sadu - presne to je
        ale chovani, ktere ma tenhle test odhalit, takze se pousti stranou.
        """
        repo = Path(__file__).resolve().parent.parent
        # Podprocesu se XDG_CONFIG_HOME predava zvlast: `mock.patch.dict`
        # v setUp plati jen pro tenhle proces, a bez nej by si podproces
        # precetl konfiguraci uzivatele - a s rozbitou by sada padala podle
        # toho, na jakem stroji se pousti.
        env = dict(os.environ, XDG_CONFIG_HOME=self.config_home.name)
        proc = subprocess.run(
            [sys.executable, "-c", SIGINT_SCRIPT],
            cwd=repo, env=env, capture_output=True, text=True, timeout=30,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("konec", proc.stdout)
        self.assertNotIn("Traceback", proc.stderr)


class HelpTest(MainTestCase):
    def test_help_works_with_a_broken_config(self):
        """Napoveda je jedine, co na konfiguraci zaviset nema.

        Uzivatel si ji rozbije preklepem (cilova skupina jsou lidi, kteri si
        appku nainstaluji dvojklikem) a prave tehdy potrebuje zjistit, jak se
        to pousti. Kdyby `load_settings()` spadlo driv nez argparse, dostal by
        misto napovedi jen vetu o konfiguraci.
        """
        cases = {
            "neznamy klic": "napis = 1\n",
            "rozjete TOML": "port = \n",
            "spatny typ": 'port = "nic"\n',
        }
        for label, text in cases.items():
            with self.subTest(label=label):
                self.write_config(text)

                with self.assertRaises(SystemExit) as caught:
                    self.run_main(["--help"])

                self.assertEqual(caught.exception.code, 0)
                self.assertIn("usage:", self.out.getvalue())
                self.assertIn("--port", self.out.getvalue())
                # V napovede se konfigurace nehlasi - hlasi se az pri startu.
                self.assertNotIn("Chyba v konfiguraci", self.err.getvalue())
                self.assertEqual(self.serve_calls, [])
                self.assertEqual(self.monitors, [])


class ShutdownTest(MainTestCase):
    def test_feed_thread_is_stopped_when_main_returns(self):
        """Po navratu z main() nesmi zustat bezet vlakno feedu.

        Pouziva se skutecny SnapshotFeed (ne FakeFeed) - jen ten ma vlakno,
        ktere muze zustat viset. Monitor je podstrceny, aby se nic necetlo
        z hardwaru.
        """
        code, _, _ = self.run_main(["--port", "9103"], feed_cls=SnapshotFeed)

        self.assertEqual(code, 0)
        feed = self.feeds[0]
        feed.join(3)
        self.assertFalse(feed.is_running(), "vlakno feedu po stop() stale bezi")
        self.assertIsNotNone(feed.latest())


if __name__ == "__main__":
    unittest.main()
