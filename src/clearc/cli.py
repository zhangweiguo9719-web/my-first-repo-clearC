from __future__ import annotations

import argparse
import json
from pathlib import Path

from .scanner import (
    SYSTEM_TARGETS,
    format_size,
    invalid_targets,
    is_admin,
    parse_targets,
    process_targets,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="clearc：Windows 清理与扫描工具")
    parser.add_argument("--drive", default="C:", help="目标盘符（默认: C:）")
    parser.add_argument("--top", type=int, default=20, help="展示 Top 结果数量（默认: 20）")
    parser.add_argument("--json", dest="json_path", help="可选：将报告输出为 JSON 文件")
    parser.add_argument(
        "--targets",
        help=(
            "目标列表，逗号分隔："
            "temp,recycle,wer,dumps,do_cache,update_cache,browser_cache,top_dirs；"
            "默认: temp,recycle,wer"
        ),
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dry-run", action="store_true", help="仅扫描/预览（默认开启）")
    mode_group.add_argument("--clean", action="store_true", help="执行清理动作（需配合 --yes）")
    parser.set_defaults(dry_run=True, clean=False)

    parser.add_argument("--yes", action="store_true", help="确认执行清理；未提供则 --clean 直接退出")
    parser.add_argument("--older-than-days", type=int, default=7, help="temp 目标的时间阈值，默认 7 天")
    parser.add_argument(
        "--permanent-delete",
        action="store_true",
        help="危险：直接删除文件；默认使用回收站（send2trash）",
    )
    parser.add_argument("--dir-depth", type=int, default=2, help="top_dirs 扫描目录深度（默认: 2）")
    parser.add_argument("--top-dirs", type=int, default=20, help="top_dirs 返回数量（默认: 20）")
    return parser


def run(args: argparse.Namespace) -> int:
    top_n = max(1, args.top)
    dry_run = not args.clean
    targets = parse_targets(args.targets)
    bad_targets = invalid_targets(targets)

    if bad_targets:
        print("Unsupported targets: " + ", ".join(sorted(bad_targets)))
        print("支持列表: temp,recycle,wer,dumps,do_cache,update_cache,browser_cache,top_dirs")
        return 2

    if args.clean and not args.yes:
        print("Refusing to clean without --yes confirmation.")
        print("拒绝执行：--clean 必须与 --yes 同时使用。")
        return 2

    if args.clean and "top_dirs" in targets:
        print("top_dirs 仅支持扫描（dry-run），不支持 clean。")
        return 2

    admin_mode = is_admin()
    requested_system_targets = [target for target in targets if target in SYSTEM_TARGETS]
    if args.clean and requested_system_targets and not admin_mode:
        print("系统级目标在 clean 模式下需要管理员权限。")
        print("请以管理员身份运行，或改为 --dry-run。")
        print("受影响 targets: " + ", ".join(requested_system_targets))
        return 2

    use_recycle_bin = not args.permanent_delete
    result = process_targets(
        targets=targets,
        drive=args.drive,
        top_n=top_n,
        dry_run=dry_run,
        older_than_days=max(0, args.older_than_days),
        use_recycle_bin=use_recycle_bin,
        dir_depth=max(0, args.dir_depth),
        top_dirs=max(1, args.top_dirs),
    )

    report = {
        "drive": args.drive,
        "targets": targets,
        "dry_run": dry_run,
        "clean": args.clean,
        "older_than_days": max(0, args.older_than_days),
        "dir_depth": max(0, args.dir_depth),
        "top_dirs": max(1, args.top_dirs),
        "permanent_delete": args.permanent_delete,
        "use_recycle_bin": use_recycle_bin,
        "is_admin": admin_mode,
        "scanned_dirs": result.scanned_dirs,
        "summary": {
            "preview_files": result.preview_files,
            "preview_size_bytes": result.preview_size_bytes,
            "preview_size_human": format_size(result.preview_size_bytes),
            "deleted_files": result.deleted_files,
            "deleted_size_bytes": result.deleted_size_bytes,
            "deleted_size_human": format_size(result.deleted_size_bytes),
            "skipped_reasons": result.skipped_reasons,
            "targets": result.target_summaries,
        },
        "top_files": result.top_files,
    }

    print("=== clearc 报告 ===")
    print(f"drive: {args.drive}")
    print(f"targets: {','.join(targets)}")
    print(f"mode: {'dry-run' if dry_run else 'clean'}")
    print(f"preview: {result.preview_files} files, {report['summary']['preview_size_human']}")
    print(f"deleted: {result.deleted_files} files, {report['summary']['deleted_size_human']}")

    if args.json_path:
        out = Path(args.json_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON report written to: {out}")

    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
