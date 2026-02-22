import os
import subprocess
import sys
import unittest


class TestHelpCommand(unittest.TestCase):
    def test_module_help_runs(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = "src"

        result = subprocess.run(
            [sys.executable, "-m", "clearc", "--help"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--drive", result.stdout)
        self.assertIn("--top", result.stdout)
        self.assertIn("--json", result.stdout)


if __name__ == "__main__":
    unittest.main()
