import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


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
        self.assertIn("--clean", result.stdout)
        self.assertIn("--older-than-days", result.stdout)


class TestSafeCleanV2(unittest.TestCase):
    def test_clean_requires_yes_confirmation(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = "src"

        result = subprocess.run(
            [sys.executable, "-m", "clearc", "--clean"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("without --yes", result.stdout)

    def test_dry_run_default_and_old_file_match(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = "src"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            old_tmp = tmp_path / "old.tmp"
            old_tmp.write_text("abc", encoding="utf-8")
            old_ts = time.time() - 10 * 24 * 60 * 60
            os.utime(old_tmp, (old_ts, old_ts))

            env["TEMP"] = tmpdir
            env["TMP"] = tmpdir

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "clearc",
                    "--older-than-days",
                    "7",
                    "--top",
                    "5",
                ],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("mode: dry-run", result.stdout)
            self.assertIn("preview: 1 files", result.stdout)
            self.assertTrue(old_tmp.exists())


if __name__ == "__main__":
    unittest.main()
