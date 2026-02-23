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
    local_app_data = Path.home() / "AppData" / "Local"
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


def process_targets(
    targets: list[str],
    drive: str = "C:",
    top_n: int = 20,
    dry_run: bool = True,
    older_than_days: int = 7,
    use_recycle_bin: bool = True,
) -> CleanResult:
    scanned_dirs: list[dict] = []
    candidates_for_top: list[tuple[int, str, str, str]] = []
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
                    candidates_for_top.append((size, _human_path(file_path), reason, target))

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

    candidates_for_top.sort(key=lambda item: item[0], reverse=True)
    top_files = [
        {
            "path": path,
            "size_bytes": size,
            "size_human": format_size(size),
            "reason": reason,
            "target": target,
        }
        for size, path, reason, target in candidates_for_top[: max(1, top_n)]
    ]

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
