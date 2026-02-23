import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from clearc.scanner import scan_top_directories


class TestTopDirsScan(unittest.TestCase):
    def test_scan_top_directories_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "A"
            b = root / "B"
            a.mkdir()
            b.mkdir()
            (a / "a.bin").write_bytes(b"a" * 100)
            (b / "b.bin").write_bytes(b"b" * 40)
            (b / "c.bin").write_bytes(b"c" * 20)

            rows, skipped = scan_top_directories([root], dir_depth=2, top_dirs=10)

            self.assertEqual(skipped, {})
            row_map = {item["path"]: item for item in rows}
            self.assertEqual(row_map[str(a)]["size_bytes"], 100)
            self.assertEqual(row_map[str(a)]["file_count"], 1)
            self.assertEqual(row_map[str(a)]["depth_used"], 1)
            self.assertEqual(row_map[str(b)]["size_bytes"], 60)
            self.assertEqual(row_map[str(b)]["file_count"], 2)

    def test_scan_supports_include_exclude_and_min_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            include_root = root / "include"
            include_root.mkdir()
            excluded = include_root / "excluded"
            excluded.mkdir()
            kept = include_root / "kept"
            kept.mkdir()

            (excluded / "x.bin").write_bytes(b"x" * 1024)
            (kept / "k.bin").write_bytes(b"k" * 2 * 1024 * 1024)

            rows, skipped = scan_top_directories(
                roots=[],
                include_dirs=[include_root],
                exclude_dirs=[excluded],
                dir_depth=2,
                top_dirs=5,
                min_dir_size_mb=1,
            )

            self.assertEqual(skipped.get("not_found", 0), 0)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["path"], str(kept))
            self.assertEqual(rows[0]["file_count"], 1)
            self.assertTrue(rows[0]["size_bytes"] >= 2 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
