import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from clearc.dism_component_store import get_admin_relaunch_command


class TestAdminRelaunchCommand(unittest.TestCase):
    def test_source_mode_uses_python_module_entry(self) -> None:
        with mock.patch.object(sys, "frozen", False, create=True):
            executable, params = get_admin_relaunch_command()

        self.assertEqual(executable, sys.executable)
        self.assertEqual(params, "-m clearc.gui")

    def test_pyinstaller_mode_relaunches_current_exe(self) -> None:
        with mock.patch.object(sys, "frozen", True, create=True):
            executable, params = get_admin_relaunch_command()

        self.assertEqual(executable, sys.executable)
        self.assertEqual(params, "")


if __name__ == "__main__":
    unittest.main()
