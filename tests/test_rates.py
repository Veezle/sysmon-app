"""Testy rate-based kolektoru - s podvrzenymi citaci, bez site.

Nedá se to overovat pres localhost: na loopbacku je kazdy odeslany bajt
zaroven prijaty, takze up a down vyjdou nutne stejne. Proto se psutil
i hodiny patchuji a hodnoty se pocitaji rucne.
"""

import unittest
from types import SimpleNamespace
from unittest import mock

from sysmon_app.collectors import disk, net

TWO_SECONDS = 2.0


class NetCollectorTest(unittest.TestCase):
    def _collector(self, samples):
        patched = mock.patch.object(net.psutil, "net_io_counters", side_effect=samples)
        patched.start()
        self.addCleanup(patched.stop)
        clock = mock.patch.object(net.time, "monotonic", side_effect=[100.0, 100.0 + TWO_SECONDS])
        clock.start()
        self.addCleanup(clock.stop)
        return net.NetCollector()

    def test_first_read_is_zero_baseline(self):
        c = self._collector([
            SimpleNamespace(bytes_sent=1000, bytes_recv=2000),
            SimpleNamespace(bytes_sent=3000, bytes_recv=2500),
        ])
        self.assertEqual(c.read(), {"up": 0.0, "down": 0.0, "total_up": 1000, "total_recv": 2000})

    def test_up_and_down_come_from_separate_counters(self):
        c = self._collector([
            SimpleNamespace(bytes_sent=1000, bytes_recv=2000),
            SimpleNamespace(bytes_sent=3000, bytes_recv=2500),
        ])
        c.read()  # baseline
        out = c.read()
        # up = (3000-1000)/2 = 1000 B/s, down = (2500-2000)/2 = 250 B/s
        self.assertAlmostEqual(out["up"], 1000.0)
        self.assertAlmostEqual(out["down"], 250.0)
        self.assertEqual(out["total_up"], 3000)
        self.assertEqual(out["total_recv"], 2500)

    def test_asymmetric_traffic_stays_asymmetric(self):
        """Kdyby kod omylem pouzil stejny citac pro oba smery, tenhle test padne."""
        c = self._collector([
            SimpleNamespace(bytes_sent=0, bytes_recv=0),
            SimpleNamespace(bytes_sent=1_000_000, bytes_recv=0),
        ])
        c.read()
        out = c.read()
        self.assertGreater(out["up"], 0)
        self.assertEqual(out["down"], 0.0)

    def test_two_collectors_have_separate_state(self):
        """Stav je v instanci - druhy kolektor nesmi videt baseline prvniho.

        Kdyby byl stav modulovy (jak to bylo v predchozim produktu), druhy
        kolektor by pocital z baseline toho prvniho a vratil by nenulovou
        rychlost. Modulovy stav zabije i kontraktni test prime(); tenhle to
        ale pozna primo z read().
        """
        samples = [
            SimpleNamespace(bytes_sent=1000, bytes_recv=2000),
            SimpleNamespace(bytes_sent=5000, bytes_recv=9000),
        ]
        io = mock.patch.object(net.psutil, "net_io_counters", side_effect=samples)
        io.start()
        self.addCleanup(io.stop)
        clock = mock.patch.object(net.time, "monotonic", side_effect=[100.0, 102.0])
        clock.start()
        self.addCleanup(clock.stop)

        first = net.NetCollector()
        second = net.NetCollector()
        first.read()
        self.assertEqual(
            second.read(),
            {"up": 0.0, "down": 0.0, "total_up": 5000, "total_recv": 9000},
        )


class DiskCollectorTest(unittest.TestCase):
    def test_first_read_is_zero_baseline(self):
        usage = mock.patch.object(disk.psutil, "disk_usage",
                                  return_value=SimpleNamespace(percent=42.0, used=10, total=100))
        usage.start()
        self.addCleanup(usage.stop)
        io = mock.patch.object(disk.psutil, "disk_io_counters",
                               side_effect=[SimpleNamespace(read_bytes=100, write_bytes=200),
                                            SimpleNamespace(read_bytes=300, write_bytes=300)])
        io.start()
        self.addCleanup(io.stop)
        clock = mock.patch.object(disk.time, "monotonic", side_effect=[0.0, TWO_SECONDS])
        clock.start()
        self.addCleanup(clock.stop)

        c = disk.DiskCollector()
        first = c.read()
        self.assertEqual((first["read_rate"], first["write_rate"]), (0.0, 0.0))
        second = c.read()
        self.assertAlmostEqual(second["read_rate"], 100.0)   # (300-100)/2
        self.assertAlmostEqual(second["write_rate"], 50.0)   # (300-200)/2
        self.assertEqual(second["percent"], 42.0)

    def test_unreadable_usage_is_the_only_unavailable_path(self):
        """`available: False` dava jen selhani disk_usage, ne citacu.

        Spletlo by se to snadno: kdyz selze `disk_io_counters`, karta zustava
        dostupna a jen rychlosti jsou nulove.
        """
        usage = mock.patch.object(disk.psutil, "disk_usage", side_effect=OSError("x"))
        usage.start()
        self.addCleanup(usage.stop)

        self.assertEqual(disk.DiskCollector().read(), {"available": False})

    def test_unreadable_io_counters_zeroes_rates_without_moving_baseline(self):
        """Po vypadku citacu se baseline neposune - dalsi cteni prumeruje pres celou mezeru.

        Vypada to zamyslene a je to zdokumentovane v CLAUDE.md jako vlastnost,
        ne bug. Test to pinuje, aby se to nezmenilo mimochodem: druha rychlost
        se pocita z casu 0.0 -> 2.0 (celkem), ne z 1.0 -> 2.0.
        """
        usage = mock.patch.object(disk.psutil, "disk_usage",
                                  return_value=SimpleNamespace(percent=42.0, used=10, total=100))
        usage.start()
        self.addCleanup(usage.stop)
        io = mock.patch.object(disk.psutil, "disk_io_counters",
                               side_effect=[SimpleNamespace(read_bytes=0, write_bytes=0),
                                            OSError("vypadek"),
                                            SimpleNamespace(read_bytes=300, write_bytes=400)])
        io.start()
        self.addCleanup(io.stop)
        clock = mock.patch.object(disk.time, "monotonic", side_effect=[0.0, 1.0, 2.0])
        clock.start()
        self.addCleanup(clock.stop)

        c = disk.DiskCollector()
        c.read()
        during_outage = c.read()
        after_outage = c.read()

        self.assertEqual(
            (during_outage["available"], during_outage["read_rate"], during_outage["write_rate"]),
            (True, 0.0, 0.0),
        )
        # 300 B / 2.0 s, ne 300 B / 1.0 s: mezera se prumeruje, protoze se
        # baseline v chybove vetvi neposunula.
        self.assertAlmostEqual(after_outage["read_rate"], 150.0)
        self.assertAlmostEqual(after_outage["write_rate"], 200.0)
