from __future__ import annotations

import ctypes
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from send2trash import send2trash

TEMP_SUFFIXES = {".tmp", ".log", ".bak", ".old", ".temp"}
NO_SUFFIX_LARGE_FILE_BYTES = 100 * 1024 * 1024
DEFAULT_TARGETS = ["temp", "recycle", "wer"]
SYSTEM_TARGETS = {"do_cache", "update_cache", "dumps"}
SUPPORTED_TARGETS = {
    "temp",
    "recycle",
    "wer",
    "dumps",
    "do_cache",
    "update_cache",
    "browser_cache",
    "top_dirs",
}


@dataclass
class CleanResult:
    scanned_dirs: list[dict]
    top_files: list[dict]
    skipped_reasons: dict[str, int]
    target_summaries: list[dict]
    preview_files: int
    preview_size_bytes: int
    deleted_files: int
    deleted_size_bytes: int


def _human_path(path: Path) -> str:
    try:
        return str(path.resolve())
    except OSError:
        return str(path)


def format_size(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{num_bytes} B"


def is_admin() -> bool:
    if os.name == "nt":
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except (AttributeError, OSError):
            return False
    return os.geteuid() == 0 if hasattr(os, "geteuid") else False


def parse_targets(raw_targets: str | None) -> list[str]:
    if not raw_targets:
        return list(DEFAULT_TARGETS)
    values = [item.strip().lower() for item in raw_targets.split(",") if item.strip()]
    unique: list[str] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique or list(DEFAULT_TARGETS)


def invalid_targets(targets: list[str]) -> list[str]:
    return [target for target in targets if target not in SUPPORTED_TARGETS]


def _expand_existing(candidates: Iterable[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def get_target_roots(target: str, drive: str = "C:") -> list[Path]:
    drive = drive.rstrip("\\/")
    user_home = Path.home()
    local_app_data = user_home / "AppData" / "Local"
    program_data = Path(f"{drive}\\ProgramData")
    windows_dir = Path(f"{drive}\\Windows")

    if target == "temp":
        env_temp = os.environ.get("TEMP")
        env_tmp = os.environ.get("TMP")
        return _expand_existing(
            [
                Path(env_temp) if env_temp else local_app_data / "Temp",
                Path(env_tmp) if env_tmp else local_app_data / "Temp",
                windows_dir / "Temp",
                local_app_data / "Temp",
            ]
        )

    if target == "recycle":
        return _expand_existing([Path(f"{drive}\\$Recycle.Bin")])

    if target == "wer":
        return _expand_existing(
            [
                program_data / "Microsoft" / "Windows" / "WER",
                local_app_data / "Microsoft" / "Windows" / "WER",
            ]
        )

    if target == "dumps":
        return _expand_existing(
            [
                windows_dir / "Minidump",
                windows_dir / "LiveKernelReports",
                local_app_data / "CrashDumps",
            ]
        )

    if target == "do_cache":
        return _expand_existing([program_data / "Microsoft" / "Windows" / "DeliveryOptimization" / "Cache"])

    if target == "update_cache":
        return _expand_existing([windows_dir / "SoftwareDistribution" / "Download"])

    if target == "browser_cache":
        return _expand_existing(
            [
                local_app_data / "Google" / "Chrome" / "User Data" / "Default" / "Cache",
                local_app_data / "Microsoft" / "Edge" / "User Data" / "Default" / "Cache",
                local_app_data / "Mozilla" / "Firefox" / "Profiles",
            ]
        )

    if target == "top_dirs":
        return _expand_existing(
            [
                user_home / "Downloads",
                user_home / "Desktop",
                user_home / "Documents",
                local_app_data,
                program_data,
                windows_dir / "Temp",
            ]
        )

    return []


def iter_files(root: Path) -> Iterable[Path]:
    for current_root, _, files in os.walk(root, topdown=True, followlinks=False):
        for name in files:
            yield Path(current_root) / name


def _skip_reason(exc: OSError) -> str:
    if isinstance(exc, FileNotFoundError):
        return "not_found"
    if isinstance(exc, PermissionError):
        return "permission_denied"
    if getattr(exc, "winerror", None) == 32:
        return "in_use"
    return "io_error"


def _is_older_than(file_path: Path, older_than_days: int, now_ts: float) -> bool:
    try:
        mtime = file_path.stat().st_mtime
    except OSError:
        return False
    cutoff = now_ts - max(0, older_than_days) * 24 * 60 * 60
    return mtime <= cutoff


def _is_candidate(file_path: Path, target: str, older_than_days: int, now_ts: float) -> tuple[bool, str]:
    suffix = file_path.suffix.lower()
    if target == "temp":
        if suffix in TEMP_SUFFIXES and _is_older_than(file_path=file_path, older_than_days=older_than_days, now_ts=now_ts):
            return True, "temp_suffix_eligible"
        if suffix == "" and file_path.stat().st_size >= NO_SUFFIX_LARGE_FILE_BYTES:
            return True, "no_suffix_large_preview"
        return False, ""

    return True, "target_file"


def _within_depth(base: Path, current: Path, depth_limit: int) -> bool:
    try:
        relative = current.relative_to(base)
    except ValueError:
        return False
    return len(relative.parts) <= depth_limit


def scan_top_directories(
    roots: list[Path],
    *,
    dir_depth: int = 2,
    top_dirs: int = 20,
    include_dirs: list[Path] | None = None,
    exclude_dirs: list[Path] | None = None,
    min_dir_size_mb: int = 0,
) -> tuple[list[dict], dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    skipped: dict[str, int] = {}
    depth_limit = max(0, dir_depth)
    min_size_bytes = max(0, min_dir_size_mb) * 1024 * 1024

    normalized_excludes: list[Path] = []
    for item in exclude_dirs or []:
        try:
            normalized_excludes.append(item.resolve())
        except OSError:
            normalized_excludes.append(item)

    scan_roots = list(roots)
    for extra_root in include_dirs or []:
        if extra_root not in scan_roots:
            scan_roots.append(extra_root)

    def _is_excluded(path: Path) -> bool:
        try:
            path_resolved = path.resolve()
        except OSError:
            path_resolved = path

        for excluded in normalized_excludes:
            if path_resolved == excluded:
                return True
            try:
                path_resolved.relative_to(excluded)
                return True
            except ValueError:
                continue
        return False

    def _dir_note(path: Path, size_bytes: int) -> str:
        hints = [
            ("logioptionsplus\\cache", "疑似缓存目录，删除后可重建，风险较低。"),
            ("mendeley\\updater", "疑似软件更新目录，建议先打开确认。"),
            ("nvidia corporation\\nsight", "疑似开发工具缓存/工作区，建议先打开确认。"),
            ("google\\chrome\\user data", "疑似浏览器缓存/用户数据目录，建议先在浏览器退出后再处理。"),
            ("microsoft\\edge\\user data", "疑似浏览器缓存/用户数据目录，建议先在浏览器退出后再处理。"),
            ("mozilla\\firefox\\profiles", "疑似浏览器配置/缓存目录，建议先确认是否为活跃配置。"),
            ("pip\\cache", "疑似 Python/pip 缓存目录，删除后通常可自动重建，风险较低。"),
            (".cache\\pip", "疑似 Python/pip 缓存目录，删除后通常可自动重建，风险较低。"),
            ("anaconda3\\pkgs", "疑似 conda 包缓存目录，删除后可能需要重新下载依赖。"),
            ("miniconda3\\pkgs", "疑似 conda 包缓存目录，删除后可能需要重新下载依赖。"),
        ]
        path_lower = str(path).lower().replace("/", "\\")
        for token, tip in hints:
            if token in path_lower:
                return tip
        if size_bytes >= 1024 * 1024 * 1024:
            return "来源不明，请先打开确认，避免误删。"
        return ""

    for root in scan_roots:
        if not root.exists():
            skipped["not_found"] = skipped.get("not_found", 0) + 1
            continue

        if _is_excluded(root):
            skipped["excluded"] = skipped.get("excluded", 0) + 1
            continue

        for current_root, dirs, files in os.walk(root, topdown=True, followlinks=False):
            current = Path(current_root)
            if _is_excluded(current):
                dirs[:] = []
                skipped["excluded"] = skipped.get("excluded", 0) + 1
                continue

            if not _within_depth(root, current, depth_limit):
                dirs[:] = []
                continue

            dirs[:] = [dir_name for dir_name in dirs if not _is_excluded(current / dir_name)]

            key = _human_path(current)
            info = stats.setdefault(key, {"size_bytes": 0, "file_count": 0, "depth_used": len(current.relative_to(root).parts)})

            for name in files:
                file_path = current / name
                try:
                    file_stat = file_path.stat()
                except OSError as exc:
                    reason = _skip_reason(exc)
                    skipped[reason] = skipped.get(reason, 0) + 1
                    continue
                info["size_bytes"] += file_stat.st_size
                info["file_count"] += 1

    rows = [
        {
            "path": path,
            "size_bytes": item["size_bytes"],
            "size_human": format_size(item["size_bytes"]),
            "file_count": item["file_count"],
            "depth_used": item["depth_used"],
            "note": _dir_note(Path(path), item["size_bytes"]),
            "target": "top_dirs",
            "reason": "dir_usage",
        }
        for path, item in stats.items()
        if item["size_bytes"] >= min_size_bytes
    ]
    rows.sort(key=lambda item: item["size_bytes"], reverse=True)
    return rows[: max(1, top_dirs)], skipped


def parse_dir_list(raw_dirs: str | None) -> list[Path]:
    if not raw_dirs:
        return []
    result: list[Path] = []
    seen: set[str] = set()
    for raw_item in raw_dirs.split(","):
        value = raw_item.strip()
        if not value:
            continue
        path_item = Path(value).expanduser()
        key = str(path_item).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(path_item)
    return result


def process_targets(
    targets: list[str],
    drive: str = "C:",
    top_n: int = 20,
    dry_run: bool = True,
    older_than_days: int = 7,
    use_recycle_bin: bool = True,
    dir_depth: int = 2,
    top_dirs: int = 20,
    include_dirs: list[Path] | None = None,
    exclude_dirs: list[Path] | None = None,
    min_dir_size_mb: int = 0,
) -> CleanResult:
    scanned_dirs: list[dict] = []
    candidates_for_top: list[dict] = []
    skipped_reasons: dict[str, int] = {}

    preview_files = 0
    preview_size = 0
    deleted_files = 0
    deleted_size = 0

    target_stats: dict[str, dict[str, int]] = {
        target: {
            "preview_files": 0,
            "preview_size_bytes": 0,
            "deleted_files": 0,
            "deleted_size_bytes": 0,
            "permission_denied": 0,
            "in_use": 0,
            "not_found": 0,
        }
        for target in targets
    }

    now_ts = time.time()

    for target in targets:
        if target == "top_dirs":
            # 安全约束：top_dirs 用于“定位大目录来源”，不是“删除候选”。
            # 即使调用方误传 clean 模式，这里也只做统计扫描，避免误删来源不明目录。
            top_rows, top_skipped = scan_top_directories(
                get_target_roots(target="top_dirs", drive=drive),
                dir_depth=dir_depth,
                top_dirs=top_dirs,
                include_dirs=include_dirs,
                exclude_dirs=exclude_dirs,
                min_dir_size_mb=min_dir_size_mb,
            )
            for reason, count in top_skipped.items():
                skipped_reasons[reason] = skipped_reasons.get(reason, 0) + count
                if reason in target_stats[target]:
                    target_stats[target][reason] += count

            for row in top_rows:
                preview_files += 1
                preview_size += row["size_bytes"]
                target_stats[target]["preview_files"] += 1
                target_stats[target]["preview_size_bytes"] += row["size_bytes"]
                candidates_for_top.append(
                    {
                        "path": row["path"],
                        "size_bytes": row["size_bytes"],
                        "size_human": row["size_human"],
                        "reason": row["reason"],
                        "target": target,
                        "file_count": row["file_count"],
                        "depth_used": row.get("depth_used", 0),
                        "note": row.get("note", ""),
                    }
                )

            scanned_dirs.append(
                {
                    "target": target,
                    "path": "内置目录集合",
                    "status": "ok",
                    "preview_files": len(top_rows),
                    "preview_size_bytes": sum(item["size_bytes"] for item in top_rows),
                    "preview_size_human": format_size(sum(item["size_bytes"] for item in top_rows)),
                    "deleted_files": 0,
                    "deleted_size_bytes": 0,
                    "deleted_size_human": format_size(0),
                    "error": "",
                }
            )
            continue

        for candidate in get_target_roots(target=target, drive=drive):
            dir_preview = 0
            dir_preview_size = 0
            dir_deleted = 0
            dir_deleted_size = 0
            status = "ok"
            error = ""

            if not candidate.exists():
                status = "missing"
                skipped_reasons["not_found"] = skipped_reasons.get("not_found", 0) + 1
                target_stats[target]["not_found"] += 1
                scanned_dirs.append(
                    {
                        "target": target,
                        "path": _human_path(candidate),
                        "status": status,
                        "preview_files": 0,
                        "preview_size_bytes": 0,
                        "preview_size_human": format_size(0),
                        "deleted_files": 0,
                        "deleted_size_bytes": 0,
                        "deleted_size_human": format_size(0),
                        "error": "directory does not exist",
                    }
                )
                continue

            try:
                for file_path in iter_files(candidate):
                    try:
                        stat = file_path.stat()
                    except OSError as exc:
                        reason = _skip_reason(exc)
                        skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
                        if reason in target_stats[target]:
                            target_stats[target][reason] += 1
                        continue

                    try:
                        is_candidate, reason = _is_candidate(file_path, target=target, older_than_days=older_than_days, now_ts=now_ts)
                    except OSError as exc:
                        skip_reason = _skip_reason(exc)
                        skipped_reasons[skip_reason] = skipped_reasons.get(skip_reason, 0) + 1
                        if skip_reason in target_stats[target]:
                            target_stats[target][skip_reason] += 1
                        continue

                    if not is_candidate:
                        continue

                    if target == "temp" and reason == "no_suffix_large_preview" and not dry_run:
                        continue

                    size = stat.st_size
                    preview_files += 1
                    preview_size += size
                    dir_preview += 1
                    dir_preview_size += size
                    target_stats[target]["preview_files"] += 1
                    target_stats[target]["preview_size_bytes"] += size
                    candidates_for_top.append(
                        {
                            "path": _human_path(file_path),
                            "size_bytes": size,
                            "size_human": format_size(size),
                            "reason": reason,
                            "target": target,
                            "file_count": None,
                            "depth_used": None,
                            "note": "",
                        }
                    )

                    if dry_run:
                        continue

                    try:
                        if use_recycle_bin:
                            send2trash(str(file_path))
                        else:
                            file_path.unlink()
                        deleted_files += 1
                        deleted_size += size
                        dir_deleted += 1
                        dir_deleted_size += size
                        target_stats[target]["deleted_files"] += 1
                        target_stats[target]["deleted_size_bytes"] += size
                    except OSError as exc:
                        skip_reason = _skip_reason(exc)
                        skipped_reasons[skip_reason] = skipped_reasons.get(skip_reason, 0) + 1
                        if skip_reason in target_stats[target]:
                            target_stats[target][skip_reason] += 1
            except OSError as exc:
                status = "error"
                error = str(exc)

            scanned_dirs.append(
                {
                    "target": target,
                    "path": _human_path(candidate),
                    "status": status,
                    "preview_files": dir_preview,
                    "preview_size_bytes": dir_preview_size,
                    "preview_size_human": format_size(dir_preview_size),
                    "deleted_files": dir_deleted,
                    "deleted_size_bytes": dir_deleted_size,
                    "deleted_size_human": format_size(dir_deleted_size),
                    "error": error,
                }
            )

    candidates_for_top.sort(key=lambda item: item["size_bytes"], reverse=True)
    top_files = candidates_for_top[: max(1, top_n)]

    target_summaries = [
        {
            "target": target,
            "preview_files": target_stats[target]["preview_files"],
            "preview_size_bytes": target_stats[target]["preview_size_bytes"],
            "preview_size_human": format_size(target_stats[target]["preview_size_bytes"]),
            "deleted_files": target_stats[target]["deleted_files"],
            "deleted_size_bytes": target_stats[target]["deleted_size_bytes"],
            "deleted_size_human": format_size(target_stats[target]["deleted_size_bytes"]),
            "skipped": {
                "permission_denied": target_stats[target]["permission_denied"],
                "in_use": target_stats[target]["in_use"],
                "not_found": target_stats[target]["not_found"],
            },
        }
        for target in targets
    ]

    return CleanResult(
        scanned_dirs=scanned_dirs,
        top_files=top_files,
        skipped_reasons=skipped_reasons,
        target_summaries=target_summaries,
        preview_files=preview_files,
        preview_size_bytes=preview_size,
        deleted_files=deleted_files,
        deleted_size_bytes=deleted_size,
    )
