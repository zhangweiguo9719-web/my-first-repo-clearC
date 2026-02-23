import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from clearc.dism_component_store import parse_analyze_output


class TestDismAnalyzeParse(unittest.TestCase):
    def test_parse_zh_cn_output(self) -> None:
        sample = """
部署映像服务和管理工具
版本: 10.0.22621.1

映像版本: 10.0.22631.3007

[==========================100.0%==========================]
组件存储信息:

Windows 资源管理器报告的组件存储大小 : 8.12 GB
组件存储的实际大小 : 7.95 GB
    已与 Windows 共享 : 5.10 GB
    备份和已禁用的功能 : 2.30 GB
    缓存和临时数据 : 0.55 GB
上次清理日期 : 2026-02-01 10:30:00
可回收的程序包数 : 3
推荐使用组件存储清理 : 是
""".strip()

        parsed = parse_analyze_output(sample)

        self.assertEqual(parsed["explorer_reported_size"], "8.12 GB")
        self.assertEqual(parsed["actual_size"], "7.95 GB")
        self.assertEqual(parsed["shared_with_windows"], "5.10 GB")
        self.assertEqual(parsed["backups_and_disabled_features"], "2.30 GB")
        self.assertEqual(parsed["cache_and_temp_data"], "0.55 GB")
        self.assertEqual(parsed["last_cleanup_date"], "2026-02-01 10:30:00")
        self.assertEqual(parsed["reclaimable_packages"], "3")
        self.assertEqual(parsed["cleanup_recommended"], "是")
        self.assertEqual(parsed["cleanup_recommended_bool"], "是")
        self.assertIn("组件存储信息", parsed["raw_output"])


if __name__ == "__main__":
    unittest.main()
