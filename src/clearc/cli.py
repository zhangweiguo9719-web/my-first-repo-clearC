from __future__ import annotations

import argparse
import json
from pathlib import Path

from .scanner import (
    SYSTEM_TARGETS,
    format_size,
    invalid_targets,
    is_admin,
    parse_dir_list,
    parse_targets,
    process_targets,
)

__version__ = "1.4.0"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clearc",
        description="clearc：Windows 清理与扫描工具（默认仅预览，安全优先）",
        epilog=(
            "安全说明：\n"
            "  · 默认 dry-run（仅预览），只有显式加 --clean --yes 才会真正删除。\n"
            "  · 默认删除进回收站（可恢复）；--permanent-delete 为永久删除，请谨慎。\n"
            "  · 系统级目标（dumps/do_cache/update_cache/prefetch/cbs_logs）clean 需管理员。\n"
            "  · top_dirs 仅统计不删除，永远安全。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"clearc {__version__}")
    parser.add_argument("--drive", default="C:", help="目标盘符（默认: C:）")
    parser.add_argument("--top", type=int, default=20, help="展示 Top 结果数量（默认: 20）")
    parser.add_argument("--json", dest="json_path", help="可选：将报告输出为 JSON 文件")
    parser.add_argument(
        "--targets",
        help=(
            "目标列表，逗号分隔："
            "temp,recycle,wer,dumps,do_cache,update_cache,browser_cache,"
            "pip_cache,npm_cache,thumbnail_cache,recent,prefetch,cbs_logs,"
            "huggingface_cache,codex_cache,poetry_cache,top_dirs；"
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
    parser.add_argument("--include-dirs", help="top_dirs 追加扫描目录，逗号分隔")
    parser.add_argument("--exclude-dirs", help="top_dirs 排除目录，逗号分隔")
    parser.add_argument("--min-dir-size-mb", type=int, default=0, help="top_dirs 最小目录体积（MB，默认: 0）")
    return parser


def run(args: argparse.Namespace) -> int:
    top_n = max(1, args.top)
    dry_run = not args.clean
    targets = parse_targets(args.targets)
    bad_targets = invalid_targets(targets)

    if bad_targets:
        print("错误：包含不支持的清理目标 -> " + ", ".join(sorted(bad_targets)))
        print(
            "支持列表: temp,recycle,wer,dumps,do_cache,update_cache,browser_cache,"
            "pip_cache,npm_cache,thumbnail_cache,recent,prefetch,cbs_logs,"
            "huggingface_cache,codex_cache,poetry_cache,top_dirs"
        )
        print("请修正 --targets 参数后重试。")
        return 2

    if args.clean and not args.yes:
        print("错误：--clean 必须与 --yes 同时使用（安全保护）。")
        print("示例：clearc --clean --yes --targets temp,recycle")
        return 2

    if args.clean and "top_dirs" in targets:
        print("错误：top_dirs 是只读统计目标，不支持 clean。请改用 --dry-run。")
        return 2

    admin_mode = is_admin()
    requested_system_targets = [target for target in targets if target in SYSTEM_TARGETS]
    if args.clean and requested_system_targets and not admin_mode:
        print("错误：以下系统级目标在 clean 模式下需要管理员权限。")
        print("受影响 targets: " + ", ".join(requested_system_targets))
        print("解决方式：请以管理员身份重新运行，或改为 --dry-run（仅预览）。")
        return 2

    use_recycle_bin = not args.permanent_delete
    include_dirs = parse_dir_list(args.include_dirs)
    exclude_dirs = parse_dir_list(args.exclude_dirs)
    result = process_targets(
        targets=targets,
        drive=args.drive,
        top_n=top_n,
        dry_run=dry_run,
        older_than_days=max(0, args.older_than_days),
        use_recycle_bin=use_recycle_bin,
        dir_depth=max(0, args.dir_depth),
        top_dirs=max(1, args.top_dirs),
        include_dirs=include_dirs,
        exclude_dirs=exclude_dirs,
        min_dir_size_mb=max(0, args.min_dir_size_mb),
    )

    report = {
        "drive": args.drive,
        "targets": targets,
        "dry_run": dry_run,
        "clean": args.clean,
        "older_than_days": max(0, args.older_than_days),
        "dir_depth": max(0, args.dir_depth),
        "top_dirs": max(1, args.top_dirs),
        "include_dirs": [str(item) for item in include_dirs],
        "exclude_dirs": [str(item) for item in exclude_dirs],
        "min_dir_size_mb": max(0, args.min_dir_size_mb),
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
        "disk": {
            "drive": args.drive,
            "free_before_bytes": result.disk_free_before_bytes,
            "free_before_human": format_size(result.disk_free_before_bytes),
            "free_after_bytes": result.disk_free_after_bytes,
            "free_after_human": format_size(result.disk_free_after_bytes),
            "freed_bytes": max(0, result.disk_free_after_bytes - result.disk_free_before_bytes),
            "freed_human": format_size(max(0, result.disk_free_after_bytes - result.disk_free_before_bytes)),
        },
        "top_files": result.top_files,
    }

    mode_label = "仅预览（dry-run）" if dry_run else "清理（clean）"
    print("=" * 50)
    print("clearc 报告")
    print("=" * 50)
    print(f"盘符      : {args.drive}")
    print(f"目标      : {','.join(targets)}")
    print(f"模式      : {mode_label}")
    print(f"预览      : {result.preview_files} 个文件, {report['summary']['preview_size_human']}")
    print(f"已删除    : {result.deleted_files} 个文件, {report['summary']['deleted_size_human']}")
    print(
        "磁盘空间  : 清理前可用 {0} -> 清理后可用 {1}（释放 {2}）".format(
            report["disk"]["free_before_human"],
            report["disk"]["free_after_human"],
            report["disk"]["freed_human"],
        )
    )
    if dry_run:
        print("安全提示  : 本次为预览，未删除任何文件。确认无误后请加 --clean --yes 执行清理。")
    else:
        recycle_note = "（进回收站，可恢复）" if use_recycle_bin else "（永久删除，不可恢复！）"
        print(f"删除方式  : {recycle_note}")

    if args.json_path:
        out = Path(args.json_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON 报告  : 已写入 {out}")

    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
