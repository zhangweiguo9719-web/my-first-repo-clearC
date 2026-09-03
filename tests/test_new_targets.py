import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from clearc.scanner import (
    SUPPORTED_TARGETS,
    SYSTEM_TARGETS,
    _send_to_trash,
    format_size,
    get_target_roots,
    parse_targets,
    process_targets,
)


class TestNewTargets(unittest.TestCase):
    def test_new_targets_registered(self) -> None:
        for target in (
            "pip_cache",
            "npm_cache",
            "thumbnail_cache",
            "recent",
            "prefetch",
            "cbs_logs",
            "huggingface_cache",
            "codex_cache",
            "poetry_cache",
        ):
            self.assertIn(target, SUPPORTED_TARGETS)

    def test_system_targets_extended(self) -> None:
        self.assertIn("prefetch", SYSTEM_TARGETS)
        self.assertIn("cbs_logs", SYSTEM_TARGETS)

    def test_pip_cache_root(self) -> None:
        roots = get_target_roots("pip_cache", drive="C:")
        self.assertTrue(any("pip" in str(r) and "Cache" in str(r) for r in roots))

    def test_thumbnail_cache_root(self) -> None:
        roots = get_target_roots("thumbnail_cache", drive="C:")
        self.assertTrue(any("Explorer" in str(r) for r in roots))

    def test_recent_root(self) -> None:
        roots = get_target_roots("recent", drive="C:")
        self.assertTrue(any("Recent" in str(r) for r in roots))

    def test_prefetch_root(self) -> None:
        roots = get_target_roots("prefetch", drive="C:")
        self.assertTrue(any("Prefetch" in str(r) for r in roots))

    def test_cbs_logs_root(self) -> None:
        roots = get_target_roots("cbs_logs", drive="C:")
        self.assertTrue(any("Logs" in str(r) for r in roots))

    def test_huggingface_cache_root(self) -> None:
        roots = get_target_roots("huggingface_cache", drive="C:")
        self.assertTrue(any("huggingface" in str(r) for r in roots))

    def test_codex_cache_root(self) -> None:
        roots = get_target_roots("codex_cache", drive="C:")
        self.assertTrue(any("codex" in str(r) for r in roots))

    def test_poetry_cache_root(self) -> None:
        roots = get_target_roots("poetry_cache", drive="C:")
        self.assertTrue(any("pypoetry" in str(r) for r in roots))
        # 必须包含 artifacts 子目录，且不包含 virtualenvs
        self.assertTrue(any("artifacts" in str(r) for r in roots))
        self.assertFalse(any("virtualenvs" in str(r) for r in roots))


class TestDiskTracking(unittest.TestCase):
    def test_process_targets_reports_disk_free(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_tmp = root / "old.tmp"
            old_tmp.write_text("x" * 1024, encoding="utf-8")
            old_ts = __import__("time").time() - 10 * 24 * 60 * 60
            os.utime(old_tmp, (old_ts, old_ts))

            with mock.patch.dict(os.environ, {"TEMP": tmp, "TMP": tmp}):
                result = process_targets(["temp"], dry_run=True, older_than_days=7)

            self.assertGreater(result.disk_free_before_bytes, 0)
            self.assertGreaterEqual(result.disk_free_after_bytes, 0)


class TestSendToTrashSafety(unittest.TestCase):
    def test_send_to_trash_uses_package_when_available(self) -> None:
        with mock.patch("clearc.scanner.send2trash") as mock_pkg:
            _send_to_trash("C:/fake/path.tmp")
            mock_pkg.assert_called_once_with("C:/fake/path.tmp")

    def test_send_to_trash_falls_back_to_shell_on_windows(self) -> None:
        # 模拟 send2trash 包不可用：应调用 Shell API，而不是静默永久删除
        with mock.patch("clearc.scanner.send2trash", None), \
                mock.patch("clearc.scanner.os.name", "nt"), \
                mock.patch("clearc.scanner._shell_recycle") as mock_shell:
            _send_to_trash("C:/fake/path.tmp")
            mock_shell.assert_called_once_with("C:/fake/path.tmp")

    def test_send_to_trash_raises_when_no_fallback(self) -> None:
        with mock.patch("clearc.scanner.send2trash", None), \
                mock.patch("clearc.scanner.os.name", "posix"):
            with self.assertRaises(RuntimeError):
                _send_to_trash("C:/fake/path.tmp")


class TestFormatSize(unittest.TestCase):
    def test_format_size(self) -> None:
        self.assertEqual(format_size(0), "0.00 B")
        self.assertEqual(format_size(1024), "1.00 KB")
        self.assertEqual(format_size(1024 * 1024), "1.00 MB")


if __name__ == "__main__":
    unittest.main()
