# -*- coding: utf-8 -*-
from __future__ import annotations

import ctypes
import locale
import re
import subprocess
import sys
from typing import Callable


DISM_ANALYZE_ARGS = ["/Online", "/Cleanup-Image", "/AnalyzeComponentStore"]
DISM_CLEAN_ARGS = ["/Online", "/Cleanup-Image", "/StartComponentCleanup"]
DISM_RESETBASE_ARGS = ["/Online", "/Cleanup-Image", "/StartComponentCleanup", "/ResetBase"]


def get_admin_relaunch_command() -> tuple[str, str]:
    """返回用于 ShellExecuteW(runas) 的可执行文件与参数。"""
    if getattr(sys, "frozen", False):
        # PyInstaller onefile/windowed: 直接重启当前 exe。
        return sys.executable, ""
    return sys.executable, "-m clearc.gui"


def is_admin() -> bool:
    """检测当前进程是否为管理员权限（仅 Windows）。"""
    if sys.platform != "win32":
        return False

    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def relaunch_as_admin() -> bool:
    """以管理员身份重新启动当前 GUI 进程（Windows runas/UAC）。"""
    if sys.platform != "win32":
        raise RuntimeError("仅 Windows 支持管理员提权启动")

    executable, params = get_admin_relaunch_command()
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, None, 1)
    return int(result) > 32


def _decode_line(raw: bytes) -> str:
    preferred = locale.getpreferredencoding(False) or "gbk"
    for enc in (preferred, "gbk", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def run_dism_stream(args: list[str], on_line: Callable[[str], None]) -> tuple[int, str]:
    """
    流式执行 DISM，并把每一行实时回调给 GUI。

    说明：
    - 使用 bytes 模式读取，优先按系统首选编码解码（兼容中文 Windows GBK 输出）；
    - 解码失败时回退 utf-8，尽量保留可读日志；
    - 由调用方在后台线程执行，避免 GUI 卡死。
    """
    cmd = ["DISM"] + args
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    lines: list[str] = []
    assert process.stdout is not None

    for raw_line in iter(process.stdout.readline, b""):
        line = _decode_line(raw_line).rstrip("\r\n")
        lines.append(line)
        on_line(line)

    process.wait()
    return process.returncode, "\n".join(lines)


def parse_analyze_output(text: str) -> dict[str, str]:
    """解析 DISM AnalyzeComponentStore 输出（中英兼容）。"""

    def _pick(patterns: list[str]) -> str:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group(1).strip()
        return ""

    parsed = {
        "explorer_reported_size": _pick(
            [
                r"Windows\s*资源管理器报告的组件存储大小\s*:\s*(.+)$",
                r"Windows Explorer Reported Size of Component Store\s*:\s*(.+)$",
            ]
        ),
        "actual_size": _pick(
            [
                r"组件存储的实际大小\s*:\s*(.+)$",
                r"Actual Size of Component Store\s*:\s*(.+)$",
            ]
        ),
        "shared_with_windows": _pick(
            [
                r"已与\s*Windows\s*共享\s*:\s*(.+)$",
                r"Shared with Windows\s*:\s*(.+)$",
            ]
        ),
        "backups_and_disabled_features": _pick(
            [
                r"备份和已禁用的功能\s*:\s*(.+)$",
                r"Backups and Disabled Features\s*:\s*(.+)$",
            ]
        ),
        "cache_and_temp_data": _pick(
            [
                r"缓存和临时数据\s*:\s*(.+)$",
                r"Cache and Temporary Data\s*:\s*(.+)$",
            ]
        ),
        "last_cleanup_date": _pick(
            [
                r"上次清理(?:的)?日期\s*:\s*(.+)$",
                r"Date of Last Cleanup\s*:\s*(.+)$",
            ]
        ),
        "reclaimable_packages": _pick(
            [
                r"可回收的程序包数\s*:\s*(.+)$",
                r"Number of Reclaimable Packages\s*:\s*(.+)$",
            ]
        ),
        "cleanup_recommended": _pick(
            [
                r"推荐使用组件存储清理\s*:\s*(.+)$",
                r"Component Store Cleanup Recommended\s*:\s*(.+)$",
            ]
        ),
        "raw_output": text.strip(),
    }

    value = parsed["cleanup_recommended"].strip().lower()
    if value in {"yes", "是"}:
        parsed["cleanup_recommended_bool"] = "是"
    elif value in {"no", "否"}:
        parsed["cleanup_recommended_bool"] = "否"
    else:
        parsed["cleanup_recommended_bool"] = "未知"

    return parsed
