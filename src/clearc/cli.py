from __future__ import annotations

import argparse
import json
from pathlib import Path

from .scanner import format_size, scan_temp_dirs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clearc",
        description="Windows C盘清理小助手（MVP）- 仅扫描，不执行删除。",
    )
    parser.add_argument("--drive", default="C:", help="目标盘符（默认: C:）")
    parser.add_argument("--top", type=int, default=20, help="展示Top文件数量（默认: 20）")
    parser.add_argument("--json", dest="json_path", help="可选：将扫描报告输出为JSON文件")
    return parser


def run(args: argparse.Namespace) -> int:
    top_n = max(1, args.top)
    result = scan_temp_dirs(drive=args.drive, top_n=top_n)

    report = {
        "drive": args.drive,
        "scan_only": True,
        "scanned_dirs": result.scanned_dirs,
        "summary": {
            "total_size_bytes": result.total_size_bytes,
            "total_size_human": format_size(result.total_size_bytes),
            "total_files": result.total_files,
        },
        "top_files": result.top_files,
    }

    print("=== clearc scan-only report ===")
    print(f"drive: {args.drive}")
    print(f"total size: {report['summary']['total_size_human']} ({result.total_size_bytes} bytes)")
    print(f"total files: {result.total_files}")
    print("\n[Directories]")
    for item in result.scanned_dirs:
        print(
            f"- {item['path']} | status={item['status']} | files={item['files']} | size={item['size_human']}"
        )

    print(f"\n[Top {top_n} files by size]")
    if not result.top_files:
        print("(no files found)")
    else:
        for idx, item in enumerate(result.top_files, start=1):
            print(f"{idx:>2}. {item['size_human']:>10} | {item['path']}")

    if args.json_path:
        out = Path(args.json_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON report written to: {out}")

    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return run(args)
