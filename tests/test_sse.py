"""SSE proud na /events: hlavicky, chunked framing, keep-alive a odchody.

Vsechno se cte syrovym socketem - `http.client` si telo precte podle
Content-Length, takze u proudu, ktery ji mit nesmi, nema co cist.

Kazdy cekaci krok ma vlastni casovou pojistku (timeout socketu, deadline ve
smycce). Test, ktery se pri mutantovi zacykli, vypada jako bezici - a to je
horsi nez cervena: sada se pak neda verit.
"""

import copy
import json
import socket
import socketserver
import struct
import threading
import time
import unittest
from unittest import mock

from sysmon_app import server
from sysmon_app.feed import SnapshotFeed

HOST = "127.0.0.1"

SOCKET_TIMEOUT = 3.0         # nad kazdym prahem nize, aby chybejici ramec spadl
WAIT_TIMEOUT = 2.0           # deadline pro "neco se stane do..." smycky
KEEPALIVE_VALUES = (0.15, 0.5)   # podstrcena SSE_KEEPALIVE_SEC: 20 s by test zabilo


class FakeMonitor:
    """Kazdy sber vrati jiny snapshot - z dat je videt, ktery tik to byl."""

    def __init__(self):
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        return {"host": "test", "n": self.calls}


class FrozenMonitor:
    """Snapshot se nemeni a vraci se porad tyz objekt.

    Otrava sdileneho snapshotu (pridany klic) se tak neztrati dalsim tikem:
    s novym dictem na kazdy sber by ji pristi tik prepsal a test by mlcel.
    """

    def __init__(self):
        self.calls = 0
        self.snapshot_dict = {"host": "test", "n": 1}

    def snapshot(self):
        self.calls += 1
        return self.snapshot_dict


def read_head(f):
    """Precte status line a hlavicky. Vraci (status, {hlavicka: hodnota})."""
    status = f.readline().decode("latin-1").strip()
    headers = {}
    while True:
        line = f.readline()
        if line in (b"", b"\r\n", b"\n"):
            break
        name, _, value = line.decode("latin-1").partition(":")
        headers[name.strip().lower()] = value.strip()
    return status, headers


def read_chunk(f):
    """Precte jedno chunked telo. None znamena, ze spojeni skoncilo.

    Velikost se parsuje z hlavicky chunku, takze se tim zaroven pinuje
    framing: telo psane naprimo (bez "delka CRLF") tady spadne na int(...).
    """
    line = f.readline()
    if not line:
        return None
    size = int(line.split(b";")[0].strip(), 16)
    data = f.read(size)
    f.read(2)  # CRLF za telem chunku
    return data


def data_payload(frame):
    """Obsah ramce `data: ...` jako JSON. Jiny tvar ramce je chyba testu.

    Pinuje se cely tvar udalosti: `data: ` + JSON + prazdny radek. Chunk
    framing spravny byt muze a udalost presto nedorazi - `EventSource`
    vyvola udalost az po prazdnem radku, takze `\\n` misto `\\n\\n` (nebo
    zadny oddelovac) znamena data, ktera zustanou v bufferu klienta viset
    a v renderu se nikdy neobjevi.
    """
    if not frame.startswith(b"data: "):
        raise AssertionError(f"ramec neni data: {frame!r}")
    payload = json.loads(frame[len(b"data: "):].decode("utf-8"))
    expected = b"data: " + json.dumps(payload).encode("utf-8") + b"\n\n"
    if frame != expected:
        raise AssertionError(f"ramec nema tvar SSE udalosti: {frame!r} != {expected!r}")
    return payload


class SseTestCase(unittest.TestCase):
    def setUp(self):
        # Vychozi feed tika casto: vetsina testu chce data hned po pripojeni.
        self.start_server(interval=0.05)

    def start_server(self, monitor=None, interval=0.05):
        """Zvedne server s vlastnim feedem a registruje uklid."""
        self.monitor = monitor or FakeMonitor()
        self.feed = SnapshotFeed(self.monitor, interval=interval)
        self.feed.start()
        srv = server.serve(self.monitor, self.feed, HOST, 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        # LIFO: feed se zastavi a dobehne, pak se zavre server; socket
        # odberatele je zaregistrovany pozdeji, takze se zavre prvni.
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        self.addCleanup(self.feed.join, WAIT_TIMEOUT)
        self.addCleanup(self.feed.stop)
        self.port = srv.server_address[1]
        return srv, self.port

    def open_stream(self, timeout=SOCKET_TIMEOUT):
        """Posle GET /events syrovym socketem. Vraci (socket, soubor)."""
        sock = socket.create_connection((HOST, self.port), timeout=timeout)
        self.addCleanup(sock.close)
        sock.sendall(b"GET /events HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
        return sock, sock.makefile("rb")

    def close_hard(self, sock, f=None):
        """Zavre odberatele tvrde (RST), jako kdyz zmizi okno prohlizece.

        `sock.close()` samo fd nezavre - `makefile` drzi referenci, takze by
        se zavrelo az s `f`. Bez SO_LINGER by navic sel FIN a server by prvni
        zapis jeste provedl; s RST selze hned ten prvni.
        """
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                        struct.pack("ii", 1, 0))
        if f is not None:
            f.close()
        sock.close()

    def wait_seq(self, count, timeout=WAIT_TIMEOUT):
        """Pocka, az feed publikuje aspon `count` snapshotu."""
        deadline = time.monotonic() + timeout
        while self.feed.snapshot_seq() < count:
            if time.monotonic() > deadline:
                self.fail(f"feed nepublikoval {count} snapshotu do {timeout} s")
            time.sleep(0.01)

    def drain_frames(self, f, timeout=WAIT_TIMEOUT, limit=200000):
        """Precte ramce, dokud spojeni neskonci.

        Vraci `(posledni_ramec, pocet_ramcu_s_datama)`, nebo None kdyz se
        spojeni nezavrelo. `limit` je druha brzda vedle casu: smycka, ktera
        ramce sype porad, by jinak rostla v pameti (i kdyz je casova brzda
        kratka, nektera vlakna stihnou miliony ramcu za sekundu).
        """
        last = None
        count = 0
        data_frames = 0
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and count < limit:
            frame = read_chunk(f)
            if frame is None:
                return last, data_frames
            if frame.startswith(b"data: "):
                data_frames += 1
            last = frame
            count += 1
        return None

    def wait_threads_gone(self, before, timeout=WAIT_TIMEOUT):
        """Ceka, az vlakna vznikla po snimku `before` skonci. Vraci zbytek."""
        deadline = time.monotonic() + timeout
        while True:
            extra = [t for t in threading.enumerate() if t not in before]
            if not extra or time.monotonic() > deadline:
                return extra
            time.sleep(0.02)

    def stats_status(self):
        """Klasicky GET /stats - odpovida server jeste?"""
        with socket.create_connection((HOST, self.port), timeout=SOCKET_TIMEOUT) as s:
            s.sendall(b"GET /stats HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                      b"Connection: close\r\n\r\n")
            head = b""
            while b"\r\n\r\n" not in head:
                chunk = s.recv(4096)
                if not chunk:
                    break
                head += chunk
        return int(head.split(b" ")[1])


class HeadersTest(SseTestCase):
    def test_headers_announce_sse_and_chunked(self):
        """K1: bez techhle hlavicek klient proud nepozna jako proud."""
        _, f = self.open_stream()
        status, headers = read_head(f)

        self.assertIn(" 200 ", status, status)
        self.assertEqual(headers.get("content-type"), "text/event-stream; charset=utf-8")
        self.assertEqual(headers.get("transfer-encoding"), "chunked")
        # `no-store` k proudu patri: bez nej si ho muze prohlizec nebo
        # prostrednik drzet a druhy odberatel dostane stary snapshot.
        self.assertEqual(headers.get("cache-control"), "no-store")
        # Content-Length u proudu nema co delat: telo nema konec, takze by
        # klient cekal na bajty, ktere nikdy neprijdou.
        self.assertNotIn("content-length", headers)


class AbortedRequestTest(SseTestCase):
    def test_request_aborted_before_headers_does_not_reach_handle_error(self):
        """K3 plati i pro klienta, ktery odejde jeste behem hlavicek.

        `end_headers()` pise do socketu, ktery uz muze byt mrtvy (klient
        poslal RST hned po pozadavku). Kdyz `try` zacina az za hlavickami,
        vyleti odtud ConnectionResetError do `socketserver.handle_error`
        a na stderr zustane plny traceback - tise, protoze odpoved uz je
        rozepsana.

        Je to zavod: jednim pokusem se okno trefi jen nekdy (RST i hlavicky
        jsou na drate v mikrosekundach), proto se jich dela vic.
        """
        attempts = 30
        threads_before = set(threading.enumerate())
        errors = []

        with mock.patch.object(
            socketserver.BaseServer, "handle_error",
            lambda srv, request, client_address: errors.append(client_address),
        ):
            for _ in range(attempts):
                sock = socket.create_connection((HOST, self.port),
                                                timeout=SOCKET_TIMEOUT)
                sock.sendall(b"GET /events HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
                self.close_hard(sock)     # RST hned, bez cteni odpovedi

            # Nez se vyhodnoti, musi vsechny handlery dobehnout - jinak by
            # pozdejsi zavolani handle_error prislo az po aserci.
            self.assertEqual(self.wait_threads_gone(threads_before), [],
                             "handlery zrusenych pozadavku nedobehly")

        self.assertEqual(errors, [],
                         f"vyjimka prosla do handle_error ({attempts} pokusu)")


class StreamTest(SseTestCase):
    def test_first_chunk_is_a_json_snapshot(self):
        """K2: prvni ramec je snapshot, ne prazdno ani hlavicka."""
        _, f = self.open_stream()
        read_head(f)

        frame = read_chunk(f)
        self.assertIsNotNone(frame, "proud skoncil bez jedineho ramce")
        payload = data_payload(frame)

        self.assertEqual(payload["host"], "test")
        self.assertIsInstance(payload["n"], int)

    def test_next_snapshot_arrives_on_the_same_connection(self):
        """Druhy snapshot prijde po tomtez spojeni - jinak by to nebyl proud.

        `EventSource` si spojeni neobnovuje po kazdem snimku; kdyby handler po
        prvnim ramci skoncil, dostal by klient data jednou a pak uz jen
        reconnecty.
        """
        _, f = self.open_stream()
        read_head(f)

        first = read_chunk(f)
        started = time.monotonic()
        second = read_chunk(f)
        elapsed = time.monotonic() - started

        self.assertEqual(data_payload(second)["n"], data_payload(first)["n"] + 1)
        # Tik je 0.05 s; prah je 20x tolik, ale ne 500x - siroky timeout by
        # propustil i smycku, ktera data posle az za vtertinu.
        self.assertLess(elapsed, 1.0)

    def test_stream_does_not_mutate_the_shared_snapshot(self):
        """Feed vraci tyz dict /stats i vsem odberatelum.

        Pridat do nej klic znamena otravit stav vsem ostatnim - a tise:
        nikdo ho nekopiruje, takze se to projevi az v renderu.
        """
        monitor = FrozenMonitor()
        self.start_server(monitor=monitor)
        self.wait_seq(1)
        before = copy.deepcopy(self.feed.latest())

        _, f = self.open_stream()
        read_head(f)
        sent = data_payload(read_chunk(f))

        self.assertEqual(sent, before, "odeslany snapshot neni ten ze feedu")
        self.assertEqual(self.feed.latest(), before,
                         "handler prepsal sdileny snapshot")

    def test_subscriber_starts_from_the_current_seq(self):
        """Odberatel zacina na soucasnem cislu, ne na nule.

        Feed s dlouhym intervalem po prvnim sberu ztichne. Kdo zacne na nule,
        dostane okamzite stary snapshot a teprve pak novy - spravny odberatel
        ceka na dalsi zmenu a do te doby posle jen keep-alive.
        """
        self.start_server(interval=60)
        self.wait_seq(1)

        with mock.patch.object(server, "SSE_KEEPALIVE_SEC", KEEPALIVE_VALUES[0]):
            _, f = self.open_stream()
            read_head(f)
            frame = read_chunk(f)

        self.assertIsNotNone(frame, "proud skoncil misto keep-alive")
        self.assertTrue(frame.startswith(b":"),
                        f"prvni ramec neni keep-alive: {frame!r}")
        self.assertEqual(self.monitor.calls, 1,
                         "odberatel si snapshot sebral sam, mimo feed")


class KeepaliveTest(SseTestCase):
    def test_keepalive_after_silence_is_a_comment_frame(self):
        """K4: po dobe ticha prijde komentar, ne zavreni spojeni.

        Feed ma dlouhy interval a v prubehu testu se sbere rucne: po tom
        snimku ztichne, takze keep-alive skutecne nastane. Pri bezicich
        datech (interval 0.05) by komentar nikdy neprisel a test by pinoval
        jen to, ze data tecou.
        """
        # Dve ruzne hodnoty: okno se pocita z podstrcene konstanty, takze
        # mutant s napevno zadratovanym timeoutem padne aspon na jedne z nich.
        for keepalive in KEEPALIVE_VALUES:
            with self.subTest(keepalive=keepalive):
                self.check_keepalive(keepalive)

    def check_keepalive(self, keepalive):
        self.start_server(interval=60)
        self.wait_seq(1)

        with mock.patch.object(server, "SSE_KEEPALIVE_SEC", keepalive):
            sock, f = self.open_stream()
            read_head(f)
            self.feed.publish_once()          # jeden snapshot, pak ticho
            self.assertEqual(data_payload(read_chunk(f))["n"], 2)

            started = time.monotonic()
            frame = read_chunk(f)
            elapsed = time.monotonic() - started
            again = read_chunk(f)
            # Spojeni zavrit hned: tenhle handler uz jen posila keep-alive
            # a v sade by zbytecne zil dal.
            f.close()
            sock.close()

        self.assertIsNotNone(frame, "spojeni se zavrelo misto keep-alive")
        self.assertTrue(frame.startswith(b":"), f"ramec neni komentar: {frame!r}")
        # Prahy v nasobcich podstrcene hodnoty, a tesne: namereny rozptyl je
        # pod 1 % (25 behu na hodnotu: 0,1502-0,1514 pri 0,15 a 0,5001-0,5013
        # pri 0,5), takze siroke okno nic neospravedlnuje - propustilo by
        # timeout zadratovany napevno.
        self.assertGreater(elapsed, keepalive * 0.8, "keep-alive prisel pred timeoutem")
        self.assertLess(elapsed, keepalive * 1.25, "keep-alive nedorazil vcas")
        # A po komentari spojeni zije dal - jinak by ho klient bral jako konec.
        self.assertIsNotNone(again, "po prvnim keep-alive se spojeni zavrelo")
        self.assertTrue(again.startswith(b":"), f"ramec neni komentar: {again!r}")


class StopTest(SseTestCase):
    def test_stream_ends_when_feed_stops(self):
        """Po `feed.stop()` musi handler ze smycky vyskočit.

        `wait_for` vraci po stopu `(last_seq, None)` okamzite - pro volajiciho
        nerozlisitelne od timeoutu. Smycka, ktera na None posle keep-alive a
        pokracuje, se pak roztočí na plny plyn (naměřeno 2 143 000 ramcu/s)
        a spojeni se nikdy neukonci - ani kdyz klient odejde.
        """
        self.start_server(interval=60)
        self.wait_seq(1)
        sock, f = self.open_stream()
        read_head(f)

        self.feed.stop()

        drained = self.drain_frames(f)
        self.assertIsNotNone(drained, "spojeni po zastaveni feedu neskoncilo")
        last, data_frames = drained
        # Konec tela je prazdny chunk: bez nej je to useknuty prenos a klient
        # (curl, prohlizec) ho hlasi jako chybu, ne jako konec proudu.
        self.assertEqual(last, b"", "proud neskoncil ukoncovacim chunkem")
        # Po stopu uz nemuze vzniknout novy snapshot - data by znamenala, ze
        # handler neco posila odjinud nez z feedu.
        self.assertEqual(data_frames, 0, "po zastaveni feedu prisla jeste data")


class SubscriberLeavingTest(SseTestCase):
    def test_leaving_subscriber_does_not_stop_feed_or_server(self):
        """K3: zavrene okno nesmi zastavit feed ani server.

        Pinuji se tri veci zvlast: feed tika dal, handler po odchodu skonci
        (a jeho vyjimka se polkne - jinak prosla do `handle_error` a nechala
        na stderr traceback), a server odpovida na jinem spojeni.
        """
        threads_before = set(threading.enumerate())
        errors = []

        with mock.patch.object(
            socketserver.BaseServer, "handle_error",
            lambda srv, request, client_address: errors.append(client_address),
        ):
            sock, f = self.open_stream()
            read_head(f)
            self.assertIsInstance(data_payload(read_chunk(f)), dict)
            seq_before = self.feed.snapshot_seq()

            self.close_hard(sock, f)

            # Novy handler po odchodu klienta skonci - jinak by tu zustavalo
            # vlakno, ktere pise do mrtveho spoje.
            self.assertEqual(self.wait_threads_gone(threads_before), [],
                             "handler po odchodu odberatele neskoncil")
            self.assertTrue(self.feed.is_running(), "feed prestal tikat")
            self.assertGreater(self.feed.snapshot_seq(), seq_before,
                               "feed dal netiknul")
            self.assertEqual(self.stats_status(), 200, "server prestal odpovidat")

        self.assertEqual(errors, [], "vyjimka z odchoziho klienta prosla do handle_error")


if __name__ == "__main__":
    unittest.main()
