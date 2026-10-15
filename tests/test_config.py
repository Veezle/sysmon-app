"""Konfigurace: vychozi hodnoty a nacteni config.toml."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sysmon_app.config import (
    DEFAULT_PORT, DEFAULT_WATCH_PORTS, config_path, load_settings,
)


class TempConfigTest(unittest.TestCase):
    """Zaklad pro testy, ktere potrebuji config.toml na disku."""

    def write_config(self, text):
        """Zapise TOML do docasneho souboru a vrati jeho cestu.

        Soubor se po testu uklidi - jinak by /tmp rostl s kazdym spustenim.
        """
        tmp = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False, encoding="utf-8")
        tmp.write(text)
        tmp.close()
        self.addCleanup(os.unlink, tmp.name)
        return tmp.name


class ConfigPathTest(unittest.TestCase):
    def test_uses_xdg_config_home(self):
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/tmp/xdgtest"}):
            self.assertEqual(config_path(), Path("/tmp/xdgtest/sysmon-app/config.toml"))

    def test_relative_xdg_is_ignored(self):
        """XDG basedir spec: relativni cesta se zahazuje."""
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "relativni"}):
            self.assertTrue(config_path().is_absolute())


class LoadSettingsTest(TempConfigTest):
    def test_missing_file_gives_defaults(self):
        s = load_settings("/tmp/sysmon-app-neexistuje.toml")
        self.assertEqual(s.port, DEFAULT_PORT)
        self.assertEqual(s.watch_ports, DEFAULT_WATCH_PORTS)

    def test_loads_from_config_path(self):
        """Cela cesta: XDG_CONFIG_HOME -> config_path() -> load_settings()."""
        with tempfile.TemporaryDirectory() as base:
            path = Path(base) / "sysmon-app" / "config.toml"
            path.parent.mkdir()
            path.write_text("port = 9100\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": base}):
                s = load_settings()
            self.assertEqual(s.port, 9100)

    def test_reads_host_and_port(self):
        s = load_settings(self.write_config('host = "127.0.0.1"\nport = 9000\n'))
        self.assertEqual(s.host, "127.0.0.1")
        self.assertEqual(s.port, 9000)

    def test_watch_ports_keys_become_ints(self):
        s = load_settings(self.write_config('[watch_ports]\n22 = "SSH"\n8080 = "Backend"\n'))
        self.assertEqual(s.watch_ports, {22: "SSH", 8080: "Backend"})

    def test_ignored_ports_become_ints(self):
        s = load_settings(self.write_config("ignored_ports = [53, 631]\n"))
        self.assertEqual(s.ignored_ports, {53, 631})

    def test_unknown_key_is_an_error(self):
        """Preklep v klíči nesmi tise nic nedelat."""
        path = self.write_config("prot = 9000\n")
        with self.assertRaises(ValueError) as ctx:
            load_settings(path)
        self.assertIn("prot", str(ctx.exception))
        self.assertIn(path, str(ctx.exception))

    def test_broken_toml_names_the_path(self):
        path = self.write_config("port = \n")
        with self.assertRaises(ValueError) as ctx:
            load_settings(path)
        self.assertIn(path, str(ctx.exception))

    def test_watch_ports_must_be_a_table(self):
        path = self.write_config("watch_ports = [22, 3306]\n")
        with self.assertRaises(ValueError) as ctx:
            load_settings(path)
        self.assertIn("watch_ports", str(ctx.exception))

    def test_ignored_ports_must_be_a_list(self):
        """Tabulka, retezec i skalár jsou chyba - "53" by se rozpadlo na {3, 5}."""
        for text in ('[ignored_ports]\n53 = "DNS"\n',
                     'ignored_ports = "53"\n',
                     "ignored_ports = 53\n"):
            with self.subTest(text=text):
                path = self.write_config(text)
                with self.assertRaises(ValueError) as ctx:
                    load_settings(path)
                self.assertIn("ignored_ports", str(ctx.exception))
                self.assertIn(path, str(ctx.exception))

    def test_bool_is_not_a_port(self):
        """true je platne TOML; chytit to musi az guard, ne parser."""
        for text in ("port = true\n", "ignored_ports = [true]\n"):
            with self.subTest(text=text):
                path = self.write_config(text)
                with self.assertRaises(ValueError) as ctx:
                    load_settings(path)
                self.assertIn(path, str(ctx.exception))

    def test_infinity_is_not_a_port(self):
        """inf je platne TOML, ale int(inf) vyhodi OverflowError."""
        for text in ("port = inf\n", "port = -inf\n", "ignored_ports = [inf]\n"):
            with self.subTest(text=text):
                path = self.write_config(text)
                with self.assertRaises(ValueError) as ctx:
                    load_settings(path)
                self.assertIn(path, str(ctx.exception))

    def test_port_out_of_range_names_the_range(self):
        path = self.write_config("port = 70000\n")
        with self.assertRaises(ValueError) as ctx:
            load_settings(path)
        self.assertIn("70000", str(ctx.exception))
        self.assertIn("1-65535", str(ctx.exception))
        self.assertIn(path, str(ctx.exception))

    def test_watch_port_out_of_range_names_the_key(self):
        path = self.write_config('[watch_ports]\n70000 = "X"\n')
        with self.assertRaises(ValueError) as ctx:
            load_settings(path)
        self.assertIn("watch_ports.70000", str(ctx.exception))
        self.assertIn(path, str(ctx.exception))

    def test_port_must_be_a_number(self):
        for text in ('port = "abc"\n', "port = []\n"):
            with self.subTest(text=text):
                path = self.write_config(text)
                with self.assertRaises(ValueError) as ctx:
                    load_settings(path)
                self.assertIn("port", str(ctx.exception))
                self.assertIn(path, str(ctx.exception))

    def test_host_must_be_a_string(self):
        """host = true by se tise stal "True" a spadl by az v socketu."""
        for text in ("host = true\n", "host = 5\n"):
            with self.subTest(text=text):
                path = self.write_config(text)
                with self.assertRaises(ValueError) as ctx:
                    load_settings(path)
                self.assertIn("host", str(ctx.exception))
                self.assertIn(path, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
