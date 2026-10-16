"""SnapshotFeed: jeden sberny cyklus, N odberatelu."""

import threading
import time
import unittest

from sysmon_app.config import TICK_SEC
from sysmon_app.feed import SnapshotFeed


class FakeMonitor:
    """Pocita, kolikrat se snapshot skutecne sebral."""

    def __init__(self):
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        return {"host": "test", "n": self.calls}


class FlakyMonitor:
    """Prvni sber vyhodi, dalsi projdou - kolektor se muze vzpamatovat."""

    def __init__(self):
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("kolektor selhal")
        return {"host": "test", "n": self.calls}


class SnapshotFeedTest(unittest.TestCase):
    def test_starts_empty(self):
        feed = SnapshotFeed(FakeMonitor())
        self.assertIsNone(feed.latest())
        self.assertEqual(feed.snapshot_seq(), 0)

    def test_publish_once_collects_one_snapshot(self):
        monitor = FakeMonitor()
        feed = SnapshotFeed(monitor)
        feed.publish_once()
        self.assertEqual(monitor.calls, 1)
        self.assertEqual(feed.latest()["n"], 1)
        self.assertEqual(feed.snapshot_seq(), 1)

    def test_two_subscribers_share_one_collection(self):
        """O tohle cele SSE jde: kolektory tikaji jednou, ne jednou na klienta."""
        monitor = FakeMonitor()
        feed = SnapshotFeed(monitor)
        received = []

        def subscribe():
            seq, snapshot = feed.wait_for(0, timeout=5)
            received.append((seq, snapshot))

        subscribers = [threading.Thread(target=subscribe) for _ in range(2)]
        for t in subscribers:
            t.start()
        feed.publish_once()
        for t in subscribers:
            t.join(timeout=5)

        self.assertEqual(monitor.calls, 1)
        self.assertEqual(len(received), 2)
        self.assertTrue(all(snapshot["host"] == "test" for _, snapshot in received))
        # Vsichni dostanou tyz objekt - kopie pro kazdeho by se nasobila
        # s poctem odberatelu a tikem.
        self.assertIs(received[0][1], received[1][1])
        self.assertIs(received[0][1], feed.latest())

    def test_wait_for_returns_after_new_snapshot(self):
        feed = SnapshotFeed(FakeMonitor())
        feed.publish_once()
        old_seq = feed.snapshot_seq()
        timer = threading.Timer(0.05, feed.publish_once)
        timer.daemon = True
        self.addCleanup(timer.cancel)
        timer.start()

        started = time.monotonic()
        seq, snapshot = feed.wait_for(old_seq, timeout=5)
        elapsed = time.monotonic() - started

        self.assertGreater(seq, old_seq)
        self.assertEqual(snapshot["n"], 2)
        # "jakmile" - ne az po timeoutu: bez notify_all by se vracel za 5 s.
        self.assertLess(elapsed, 1.0)

    def test_wait_for_timeout_returns_none_not_raises(self):
        feed = SnapshotFeed(FakeMonitor())
        seq, snapshot = feed.wait_for(0, timeout=0.05)
        self.assertEqual(seq, 0)
        self.assertIsNone(snapshot)

        # A po timeoutu se nesmi vratit stary snapshot: "nic noveho" a "nova
        # data" by pak vypadaly stejne a Task 10 by posilal duplicity.
        feed.publish_once()
        current = feed.snapshot_seq()
        seq, snapshot = feed.wait_for(current, timeout=0.05)
        self.assertEqual(seq, current)
        self.assertIsNone(snapshot)

    def test_loop_publishes_and_stop_ends_it(self):
        monitor = FakeMonitor()
        feed = SnapshotFeed(monitor, interval=TICK_SEC)
        feed.start()
        # Uklid i kdyz assertion spadne - jinak by vlakno tocilo do konce sady.
        self.addCleanup(feed.join, 5)
        self.addCleanup(feed.stop)

        started = time.monotonic()
        self.assertTrue(feed.wait_for(0, timeout=5)[1] is not None)
        # Prvni sber hned, ne az za TICK_SEC.
        self.assertLess(time.monotonic() - started, 1.0)

        # A za tik se sbira prave jednou: druha perioda jeste neuplynula.
        self.assertEqual(monitor.calls, 1)

        feed.stop()
        feed.join(timeout=5)
        self.assertFalse(feed.is_running())

    def test_stop_releases_a_waiting_subscriber(self):
        """Stop musi probudit odberatele visiciho ve wait_for.

        V Tasku 10 na tom stoji ukoncovani SSE proudu: bez probuzeni by kazdy
        handler visel az do sveho keep-alive timeoutu.
        """
        feed = SnapshotFeed(FakeMonitor())
        parked = threading.Event()
        released = []

        def wait_forever():
            parked.set()
            started = time.monotonic()
            result = feed.wait_for(0, timeout=30)
            released.append((result, time.monotonic() - started))

        waiter = threading.Thread(target=wait_forever, daemon=True)
        waiter.start()
        self.assertTrue(parked.wait(5))
        time.sleep(0.05)  # at odberatel stihne vejit do wait_for

        feed.stop()
        waiter.join(timeout=5)

        self.assertEqual(released[0][0], (0, None))
        self.assertLess(released[0][1], 1.0)

    def test_loop_survives_a_failing_collector(self):
        """Vyjimka ze sberu nesmi zabit sberne vlakno.

        Kdyby vlakno umrelo, `_seq` by prestal rust a vsichni klienti by
        videli zamrzla cisla - tise a bez chyby kdekoli (vzorec, pred kterym
        varuje CLAUDE.md u net.py).
        """
        feed = SnapshotFeed(FlakyMonitor(), interval=0.01)
        feed.start()
        self.addCleanup(feed.join, 5)
        self.addCleanup(feed.stop)

        self.assertIsNotNone(feed.wait_for(0, timeout=5)[1])
        self.assertTrue(feed.is_running())

    def test_sampling_does_not_block_subscribers(self):
        """Sber se nesmi drzet zamek, jinak /stats i novy odberatel cekaji na kolektor."""
        entered = threading.Event()
        release = threading.Event()

        class SlowMonitor:
            def snapshot(self):
                entered.set()
                release.wait(5)
                return {"host": "test"}

        feed = SnapshotFeed(SlowMonitor(), interval=0.01)
        publisher = threading.Thread(target=feed.publish_once, daemon=True)
        self.addCleanup(release.set)
        publisher.start()
        self.assertTrue(entered.wait(5), "sber vubec nezacal")

        started = time.monotonic()
        self.assertIsNone(feed.latest())
        self.assertLess(time.monotonic() - started, 1.0)

        release.set()
        publisher.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
