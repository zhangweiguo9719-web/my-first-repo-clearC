from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class ScanResult:
    scanned_dirs: list[dict]
    total_size_bytes: int
    total_files: int
    top_files: list[dict]


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


def scan_temp_dirs(drive: str = "C:", top_n: int = 20) -> ScanResult:
    scanned_dirs: list[dict] = []
    top_candidates: list[tuple[int, str]] = []
    total_size = 0
    total_files = 0

    for candidate in get_candidate_temp_dirs(drive=drive):
        dir_size = 0
        dir_files = 0
        status = "ok"
        error = ""

        if not candidate.exists():
            status = "missing"
            scanned_dirs.append(
                {
                    "path": _human_path(candidate),
                    "status": status,
                    "files": 0,
                    "size_bytes": 0,
                    "size_human": format_size(0),
                    "error": "directory does not exist",
                }
            )
            continue

        try:
            for file_path in iter_files(candidate):
                try:
                    size = file_path.stat().st_size
                except (OSError, PermissionError):
                    continue

                dir_size += size
                dir_files += 1
                top_candidates.append((size, _human_path(file_path)))
        except (OSError, PermissionError) as exc:
            status = "error"
            error = str(exc)

        total_size += dir_size
        total_files += dir_files
        scanned_dirs.append(
            {
                "path": _human_path(candidate),
                "status": status,
                "files": dir_files,
                "size_bytes": dir_size,
                "size_human": format_size(dir_size),
                "error": error,
            }
        )

    top_candidates.sort(key=lambda item: item[0], reverse=True)
    top_files = [
        {
            "path": path,
            "size_bytes": size,
            "size_human": format_size(size),
        }
        for size, path in top_candidates[:top_n]
    ]

    return ScanResult(
        scanned_dirs=scanned_dirs,
        total_size_bytes=total_size,
        total_files=total_files,
        top_files=top_files,
    )
