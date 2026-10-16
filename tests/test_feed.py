"""SnapshotFeed: jeden sberny cyklus, N odberatelu."""

import threading
import unittest
from unittest import mock

from sysmon_app.config import TICK_SEC
from sysmon_app.feed import SnapshotFeed


class FakeMonitor:
    """Pocita, kolikrat se snapshot skutecne sebral."""

    def __init__(self):
        self.calls = 0

    def snapshot(self):
        self.calls += 1
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

    def test_wait_for_returns_after_new_snapshot(self):
        feed = SnapshotFeed(FakeMonitor())
        feed.publish_once()
        old_seq = feed.snapshot_seq()
        threading.Timer(0.05, feed.publish_once).start()
        seq, snapshot = feed.wait_for(old_seq, timeout=5)
        self.assertGreater(seq, old_seq)
        self.assertEqual(snapshot["n"], 2)

    def test_wait_for_timeout_returns_none_not_raises(self):
        feed = SnapshotFeed(FakeMonitor())
        seq, snapshot = feed.wait_for(0, timeout=0.05)
        self.assertEqual(seq, 0)
        self.assertIsNone(snapshot)

    def test_loop_publishes_and_stop_ends_it(self):
        monitor = FakeMonitor()
        feed = SnapshotFeed(monitor, interval=0.01)
        feed.start()
        self.assertTrue(feed.wait_for(0, timeout=5)[1] is not None)
        feed.stop()
        feed.join(timeout=5)
        self.assertFalse(feed.is_running())


if __name__ == "__main__":
    unittest.main()
