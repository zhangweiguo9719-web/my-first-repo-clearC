# -*- coding: utf-8 -*-
from __future__ import annotations

import ctypes
import re
import subprocess
import sys
from typing import Callable


DISM_ANALYZE_ARGS = ["/Online", "/Cleanup-Image", "/AnalyzeComponentStore"]
DISM_CLEAN_ARGS = ["/Online", "/Cleanup-Image", "/StartComponentCleanup"]
DISM_RESETBASE_ARGS = ["/Online", "/Cleanup-Image", "/StartComponentCleanup", "/ResetBase"]


def is_admin() -> bool:
    """检测当前进程是否为管理员权限。"""
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

    params = "-m clearc.gui"
    # 使用 runas 触发 UAC；返回值 > 32 通常表示启动成功。
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
    return int(result) > 32


def run_dism_stream(
    args: list[str],
    on_output: Callable[[str], None],
) -> tuple[int, str]:
    """
    流式执行 DISM，并把每一行实时回调给 GUI。

    设计说明：
    - GUI 主线程不能阻塞，否则会“卡死”；因此由外层线程调用本函数。
    - 使用逐行读取，让用户看到实时进度，便于判断是否长时间无响应。
    - stderr 合并到 stdout，确保日志完整保留，排障时不丢信息。
    """
    cmd = ["DISM"] + args
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    lines: list[str] = []
    assert process.stdout is not None

    for raw_line in process.stdout:
        line = raw_line.rstrip("\r\n")
        lines.append(line)
        on_output(line)

    process.wait()
    output = "\n".join(lines)
    return process.returncode, output


def parse_analyze_output(text: str) -> dict[str, str]:
    """解析 DISM AnalyzeComponentStore 输出（中英兼容，优先覆盖中文系统）。"""

    def _pick(patterns: list[str]) -> str:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group(1).strip()
        return ""

    # 使用多语言模式匹配：中文标签和英文标签都支持。
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
                r"上次清理日期\s*:\s*(.+)$",
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
