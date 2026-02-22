from __future__ import annotations

import argparse
import json
from pathlib import Path

from .scanner import format_size, process_temp_dirs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clearc",
        description="Windows C盘清理小助手（V2）- 默认安全预览，支持确认后清理。",
    )
    parser.add_argument("--drive", default="C:", help="目标盘符（默认: C:）")
    parser.add_argument("--top", type=int, default=20, help="展示Top文件数量（默认: 20）")
    parser.add_argument("--json", dest="json_path", help="可选：将报告输出为JSON文件")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dry-run", action="store_true", help="仅预览候选文件（默认开启）")
    mode_group.add_argument("--clean", action="store_true", help="执行清理动作")
    parser.set_defaults(dry_run=True, clean=False)

    parser.add_argument("--yes", action="store_true", help="确认删除；若未提供则 --clean 直接退出")
    parser.add_argument(
        "--older-than-days",
        type=int,
        default=7,
        help="仅处理修改时间早于N天的文件（默认: 7）",
    )
    parser.add_argument(
        "--use-recycle-bin",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="删除时是否优先移入回收站（默认: True）",
    )
    return parser


def run(args: argparse.Namespace) -> int:
    top_n = max(1, args.top)
    dry_run = not args.clean

    if args.clean and not args.yes:
        print("Refusing to clean without --yes confirmation. Use --clean --yes to continue.")
        return 2

    result = process_temp_dirs(
        drive=args.drive,
        top_n=top_n,
        dry_run=dry_run,
        older_than_days=max(0, args.older_than_days),
        use_recycle_bin=args.use_recycle_bin,
    )

    report = {
        "drive": args.drive,
        "dry_run": dry_run,
        "clean": args.clean,
        "older_than_days": max(0, args.older_than_days),
        "use_recycle_bin": args.use_recycle_bin,
        "scanned_dirs": result.scanned_dirs,
        "summary": {
            "preview_files": result.preview_files,
            "preview_size_bytes": result.preview_size_bytes,
            "preview_size_human": format_size(result.preview_size_bytes),
            "deleted_files": result.deleted_files,
            "deleted_size_bytes": result.deleted_size_bytes,
            "deleted_size_human": format_size(result.deleted_size_bytes),
            "skipped_reasons": result.skipped_reasons,
        },
        "top_files": result.top_files,
    }

    print("=== clearc safe-clean report ===")
    print(f"drive: {args.drive}")
    print(f"mode: {'dry-run' if dry_run else 'clean'}")
    print(f"older_than_days: {report['older_than_days']}")
    print(f"use_recycle_bin: {args.use_recycle_bin}")
    print(
        f"preview: {result.preview_files} files, "
        f"{report['summary']['preview_size_human']} ({result.preview_size_bytes} bytes)"
    )
    print(
        f"deleted: {result.deleted_files} files, "
        f"{report['summary']['deleted_size_human']} ({result.deleted_size_bytes} bytes)"
    )

    print("\n[Directories]")
    for item in result.scanned_dirs:
        print(
            "- "
            f"{item['path']} | status={item['status']} | "
            f"preview={item['preview_files']} ({item['preview_size_human']}) | "
            f"deleted={item['deleted_files']} ({item['deleted_size_human']})"
        )

    print(f"\n[Top {top_n} candidate files]")
    if not result.top_files:
        print("(no candidate files found)")
    else:
        for idx, item in enumerate(result.top_files, start=1):
            print(f"{idx:>2}. {item['size_human']:>10} | {item['reason']:<24} | {item['path']}")

    print("\n[Skipped reasons]")
    if not result.skipped_reasons:
        print("(none)")
    else:
        for reason, count in sorted(result.skipped_reasons.items()):
            print(f"- {reason}: {count}")

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
