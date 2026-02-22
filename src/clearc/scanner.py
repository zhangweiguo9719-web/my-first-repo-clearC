from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from send2trash import send2trash

TEMP_SUFFIXES = {".tmp", ".log", ".bak", ".old", ".temp"}
NO_SUFFIX_LARGE_FILE_BYTES = 100 * 1024 * 1024


@dataclass
class CleanResult:
    scanned_dirs: list[dict]
    top_files: list[dict]
    skipped_reasons: dict[str, int]
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


def get_candidate_temp_dirs(drive: str = "C:") -> list[Path]:
    drive = drive.rstrip("\\/")
    candidates: list[Path] = []

    env_temp = os.environ.get("TEMP")
    env_tmp = os.environ.get("TMP")
    if env_temp:
        candidates.append(Path(env_temp))
    if env_tmp:
        candidates.append(Path(env_tmp))

    windows_temp = Path(f"{drive}\\Windows\\Temp")
    user_temp = Path.home() / "AppData" / "Local" / "Temp"
    candidates.extend([windows_temp, user_temp])

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def iter_files(root: Path) -> Iterable[Path]:
    for current_root, _, files in os.walk(root, topdown=True, followlinks=False):
        for name in files:
            yield Path(current_root) / name


def _skip_reason(exc: OSError) -> str:
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


def process_temp_dirs(
    drive: str = "C:",
    top_n: int = 20,
    dry_run: bool = True,
    older_than_days: int = 7,
    use_recycle_bin: bool = True,
) -> CleanResult:
    scanned_dirs: list[dict] = []
    candidates_for_top: list[tuple[int, str, str]] = []
    skipped_reasons: dict[str, int] = {}

    preview_files = 0
    preview_size = 0
    deleted_files = 0
    deleted_size = 0

    now_ts = time.time()

    for candidate in get_candidate_temp_dirs(drive=drive):
        dir_preview = 0
        dir_preview_size = 0
        dir_deleted = 0
        dir_deleted_size = 0
        status = "ok"
        error = ""

        if not candidate.exists():
            status = "missing"
            scanned_dirs.append(
                {
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
                    continue

                suffix = file_path.suffix.lower()
                size = stat.st_size

                if suffix not in TEMP_SUFFIXES:
                    if dry_run and suffix == "" and size >= NO_SUFFIX_LARGE_FILE_BYTES:
                        preview_files += 1
                        preview_size += size
                        dir_preview += 1
                        dir_preview_size += size
                        candidates_for_top.append((size, _human_path(file_path), "no_suffix_large_preview"))
                    continue

                if not _is_older_than(file_path=file_path, older_than_days=older_than_days, now_ts=now_ts):
                    continue

                preview_files += 1
                preview_size += size
                dir_preview += 1
                dir_preview_size += size
                candidates_for_top.append((size, _human_path(file_path), "temp_suffix_eligible"))

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
                except OSError as exc:
                    reason = _skip_reason(exc)
                    skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
        except OSError as exc:
            status = "error"
            error = str(exc)

        scanned_dirs.append(
            {
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
        }
        for size, path, reason in candidates_for_top[: max(1, top_n)]
    ]

    return CleanResult(
        scanned_dirs=scanned_dirs,
        top_files=top_files,
        skipped_reasons=skipped_reasons,
        preview_files=preview_files,
        preview_size_bytes=preview_size,
        deleted_files=deleted_files,
        deleted_size_bytes=deleted_size,
    )
