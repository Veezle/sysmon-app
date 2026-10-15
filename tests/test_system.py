"""Testy systemovych udaju do hlavicky - bez zavislosti na skutecnem stroji."""

import unittest
from unittest import mock

from sysmon_app.collectors import system


class GetUserTest(unittest.TestCase):
    def test_returns_login_name(self):
        with mock.patch.object(system.getpass, "getuser", return_value="veezle"):
            self.assertEqual(system.get_user(), "veezle")

    def test_missing_user_is_empty_and_not_a_crash(self):
        """Kdyz jmeno uzivatele nejde zjistit, hlavicka ukaze jen hostname.

        /stats se kvuli tomu nesmi rozbit - hostname je porad uzitecny.
        """
        with mock.patch.object(system.getpass, "getuser",
                               side_effect=OSError("bez prostredi")):
            self.assertEqual(system.get_user(), "")


if __name__ == "__main__":
    unittest.main()
