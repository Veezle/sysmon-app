"""Konfigurace: vychozi hodnoty a nacteni config.toml."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sysmon_app.config import (
    DEFAULT_PORT, DEFAULT_WATCH_PORTS, config_path, load_settings,
)


def write_config(text):
    """Zapise TOML do docasneho souboru a vrati jeho cestu."""
    tmp = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False, encoding="utf-8")
    tmp.write(text)
    tmp.close()
    return tmp.name


class ConfigPathTest(unittest.TestCase):
    def test_uses_xdg_config_home(self):
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/tmp/xdgtest"}):
            self.assertEqual(config_path(), Path("/tmp/xdgtest/sysmon-app/config.toml"))

    def test_relative_xdg_is_ignored(self):
        """XDG basedir spec: relativni cesta se zahazuje."""
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "relativni"}):
            self.assertTrue(config_path().is_absolute())


class LoadSettingsTest(unittest.TestCase):
    def test_missing_file_gives_defaults(self):
        s = load_settings("/tmp/sysmon-app-neexistuje.toml")
        self.assertEqual(s.port, DEFAULT_PORT)
        self.assertEqual(s.watch_ports, DEFAULT_WATCH_PORTS)

    def test_reads_host_and_port(self):
        s = load_settings(write_config('host = "127.0.0.1"\nport = 9000\n'))
        self.assertEqual(s.host, "127.0.0.1")
        self.assertEqual(s.port, 9000)

    def test_watch_ports_keys_become_ints(self):
        s = load_settings(write_config('[watch_ports]\n22 = "SSH"\n8080 = "Backend"\n'))
        self.assertEqual(s.watch_ports, {22: "SSH", 8080: "Backend"})

    def test_ignored_ports_become_ints(self):
        s = load_settings(write_config("ignored_ports = [53, 631]\n"))
        self.assertEqual(s.ignored_ports, {53, 631})

    def test_unknown_key_is_an_error(self):
        """Preklep v klíči nesmi tise nic nedelat."""
        path = write_config("prot = 9000\n")
        with self.assertRaises(ValueError) as ctx:
            load_settings(path)
        self.assertIn("prot", str(ctx.exception))
        self.assertIn(path, str(ctx.exception))

    def test_broken_toml_names_the_path(self):
        path = write_config("port = \n")
        with self.assertRaises(ValueError) as ctx:
            load_settings(path)
        self.assertIn(path, str(ctx.exception))

    def test_watch_ports_must_be_a_table(self):
        path = write_config("watch_ports = [22, 3306]\n")
        with self.assertRaises(ValueError) as ctx:
            load_settings(path)
        self.assertIn("watch_ports", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
