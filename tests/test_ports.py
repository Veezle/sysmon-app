"""Porty: parsovani /proc/net/tcp a seznam sledovanych portu.

Nema to nic spolecneho se skutecnym systemem - /proc se predstira
monkeypatchi TCP_FILES.
"""

import os
import tempfile
import unittest

from sysmon_app.collectors import ports

# Jeden radek /proc/net/tcp: 0x0016 = 22, stav 0A = LISTEN
LISTEN_22 = ("   0: 0100007F:0016 00000000:0000 0A 00000000:00000000 00:00000000 "
             "00000000     0        0 0 1 0000000000000000 100 0 0 10 0\n")
# 0x1F90 = 8080, ale stav 01 (ESTABLISHED) -> nema se pocitat
ESTAB_8080 = ("   1: 0100007F:1F90 00000000:0000 01 00000000:00000000 00:00000000 "
              "00000000     0        0 0 1 0000000000000000 100 0 0 10 0\n")
# 0x0035 = 53 -> je v ignored_ports, zahodit
LISTEN_53 = ("   2: 00000000:0035 00000000:0000 0A 00000000:00000000 00:00000000 "
             "00000000     0        0 0 1 0000000000000000 100 0 0 10 0\n")
# Jen dva sloupce -> zahodi se jeste pred ctenim portu
SHORT_LINE = "   3: 0100007F:0016\n"
# Ctyri sloupce, ale local_address bez dvojtecky -> IndexError uvnitr smycky
NO_COLON_ADDR = ("   4: 0100007F0016 00000000:0000 0A 00000000:00000000 00:00000000 "
                 "00000000     0        0 0 1 0000000000000000 100 0 0 10 0\n")

WATCH = {22: "SSH", 3306: "MySQL", 5173: "Vite", 8080: "Backend", 8081: "Metro"}


class ListeningPortsTest(unittest.TestCase):
    def _fake_tcp(self, content, header=True):
        fd, path = tempfile.mkstemp(prefix="faketcp")
        with os.fdopen(fd, "w") as f:
            if header:
                f.write("  sl  local_address rem_address   st\n")
            f.write(content)
        self.addCleanup(os.unlink, path)
        orig = ports.TCP_FILES
        ports.TCP_FILES = (path,)
        self.addCleanup(setattr, ports, "TCP_FILES", orig)

    def test_parses_hex_port(self):
        self._fake_tcp(LISTEN_22)
        self.assertEqual(ports.listening_ports(set()), {22})

    def test_ignores_non_listen_states(self):
        self._fake_tcp(ESTAB_8080)
        self.assertEqual(ports.listening_ports(set()), set())

    def test_ignores_ignored_ports(self):
        self._fake_tcp(LISTEN_53)
        self.assertEqual(ports.listening_ports({53}), set())

    def test_malformed_lines_are_skipped(self):
        """Kratky radek i adresa bez dvojtecky: zahodit, ne spadnout.

        Vyjimka by tudy prosla az do snapshot(), ktery by spadl cely.
        """
        self._fake_tcp(SHORT_LINE + NO_COLON_ADDR)
        self.assertEqual(ports.listening_ports(set()), set())

    def test_missing_file_is_not_fatal(self):
        orig = ports.TCP_FILES
        ports.TCP_FILES = ("/neexistuje/tcp",)
        self.addCleanup(setattr, ports, "TCP_FILES", orig)
        self.assertEqual(ports.listening_ports(set()), set())

    def test_empty_and_header_only_files_are_not_fatal(self):
        """Prazdny soubor skonci na next(f), jen hlavicka na prazdne smycce."""
        self._fake_tcp("", header=False)
        self.assertEqual(ports.listening_ports(set()), set())
        self._fake_tcp("")
        self.assertEqual(ports.listening_ports(set()), set())


class GetServicesTest(unittest.TestCase):
    def test_running_first_then_by_port(self):
        orig = ports.listening_ports
        ports.listening_ports = lambda ignored: {8080, 22}
        self.addCleanup(setattr, ports, "listening_ports", orig)
        items = ports.get_services(WATCH, set())
        self.assertEqual([i["port"] for i in items], [22, 8080, 3306, 5173, 8081])
        self.assertEqual([i["on"] for i in items], [True, True, False, False, False])
        labels = {i["port"]: i["label"] for i in items}
        self.assertEqual(labels[22], "SSH")
        self.assertEqual(labels[8080], "Backend")

    def test_port_outside_watch_list_is_invisible(self):
        """Sledovany port projde, nesledovany 9999 se nezobrazi vubec."""
        orig = ports.listening_ports
        ports.listening_ports = lambda ignored: {9999, 22}
        self.addCleanup(setattr, ports, "listening_ports", orig)
        self.assertEqual(ports.get_services({22: "SSH"}, set()), [
            {"port": 22, "label": "SSH", "on": True},
        ])


if __name__ == "__main__":
    unittest.main()
