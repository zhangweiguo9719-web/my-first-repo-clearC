# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from .dism_component_store import (
    DISM_ANALYZE_ARGS,
    DISM_CLEAN_ARGS,
    DISM_RESETBASE_ARGS,
    is_admin,
    parse_analyze_output,
    relaunch_as_admin,
    run_dism_stream,
)
from .scanner import DEFAULT_TARGETS, SYSTEM_TARGETS, SUPPORTED_TARGETS


# ---------------------------------------------------------------------------
# 设计 token：统一配色与字体（来自 UI/UX Skill 的"语义色分层 + 统一 token"原则）
# 语义：danger=危险不可逆 / warning=需谨慎 / success=成功 / info=信息 / primary=主操作
# ---------------------------------------------------------------------------
COLOR = {
    "bg": "#f4f6fa",
    "surface": "#ffffff",
    "surface_alt": "#e9edf3",
    "border": "#d3d9e3",
    "text": "#1f2430",
    "text_muted": "#68738a",
    "primary": "#2456d6",
    "primary_hover": "#1b45b0",
    "success": "#0e7a4a",
    "success_bg": "#e6f6ee",
    "warning": "#b45309",
    "warning_bg": "#fdf0e0",
    "danger": "#c02c2c",
    "danger_bg": "#fdeaea",
    "info": "#0e7490",
    "info_bg": "#e4f4f8",
}
FONT = {
    "base": ("Microsoft YaHei UI", 10),
    "title": ("Microsoft YaHei UI", 12, "bold"),
    "small": ("Microsoft YaHei UI", 9),
    "mono": ("Consolas", 10),
}


class Tooltip:
    """悬浮提示组件：鼠标悬停控件显示一行说明，帮助理解按钮/参数含义。

    参考高星 UI Skill 的"每个可交互元素都要有可发现的说明"原则。
    """

    def __init__(self, widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.tip_window = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _show(self, _event) -> None:
        if self.tip_window is not None or not self.text:
            return
        x = self.widget.winfo_rootx() + 14
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)
        label = tk.Label(
            tw,
            text=self.text,
            justify=tk.LEFT,
            background="#252a36",
            foreground="#f2f4f8",
            relief=tk.SOLID,
            borderwidth=1,
            font=FONT["small"],
            padx=10,
            pady=6,
            wraplength=380,
        )
        label.pack()

    def _hide(self, _event) -> None:
        if self.tip_window is not None:
            self.tip_window.destroy()
            self.tip_window = None


class ClearCGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("clearc 图形界面")
        self.root.geometry("1240x880")
        self.root.minsize(1100, 780)

        self.drive_var = tk.StringVar(value="C:")
        self.older_days_var = tk.StringVar(value="7")
        self.top_var = tk.StringVar(value="20")
        self.dir_depth_var = tk.StringVar(value="2")
        self.top_dirs_var = tk.StringVar(value="20")
        self.drill_depth_var = tk.StringVar(value="2")
        self.include_dirs_var = tk.StringVar(value="")
        self.exclude_dirs_var = tk.StringVar(value="")
        self.min_dir_size_var = tk.StringVar(value="0")
        self.top_dirs_status_var = tk.StringVar(value="就绪")
        self.clean_var = tk.BooleanVar(value=False)
        self.permanent_var = tk.BooleanVar(value=False)

        self.is_admin_var = tk.StringVar(value="是" if is_admin() else "否")
        self.resetbase_ack_var = tk.BooleanVar(value=False)
        self.resetbase_text_var = tk.StringVar(value="")
        self.show_raw_analyze_var = tk.BooleanVar(value=False)

        self.dism_summary_vars: dict[str, tk.StringVar] = {
            "explorer_reported_size": tk.StringVar(value="-"),
            "actual_size": tk.StringVar(value="-"),
            "shared_with_windows": tk.StringVar(value="-"),
            "backups_and_disabled_features": tk.StringVar(value="-"),
            "cache_and_temp_data": tk.StringVar(value="-"),
            "last_cleanup_date": tk.StringVar(value="-"),
            "reclaimable_packages": tk.StringVar(value="-"),
            "cleanup_recommended_bool": tk.StringVar(value="-"),
        }

        self.target_vars: dict[str, tk.BooleanVar] = {
            target: tk.BooleanVar(value=target in DEFAULT_TARGETS) for target in sorted(SUPPORTED_TARGETS)
        }
        self.latest_report: dict = {}
        self.top_dirs_rows: list[dict] = []
        self.top_dirs_sort_state: dict[str, bool] = {}

        self._setup_style()
        self.status_var = tk.StringVar(value="就绪")
        self._build_layout()
        self._refresh_dism_controls()

    def _setup_style(self) -> None:
        """统一主题：把语义色 token 应用到 ttk 控件，让按钮/状态栏有明确层级。

        参考高星 UI Skill 原则：语义色分层（主操作/危险/警告）、统一字号、
        状态与颜色一一对应，避免默认灰蒙蒙的观感。
        """
        style = ttk.Style(self.root)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        style.configure(".", font=FONT["base"], background=COLOR["bg"], foreground=COLOR["text"])
        style.configure("TFrame", background=COLOR["bg"])
        style.configure("TLabel", background=COLOR["bg"], foreground=COLOR["text"])
        style.configure(
            "TLabelframe",
            background=COLOR["bg"],
            bordercolor=COLOR["border"],
            relief=tk.GROOVE,
        )
        style.configure("TLabelframe.Label", background=COLOR["bg"], foreground=COLOR["text"], font=FONT["title"])
        style.configure("TButton", padding=(10, 5), font=FONT["base"])
        style.map("TButton", background=[("active", COLOR["surface_alt"])])
        style.configure("Accent.TButton", background=COLOR["primary"], foreground="#ffffff")
        style.map("Accent.TButton", background=[("active", COLOR["primary_hover"]), ("disabled", "#9aa4b5")])
        style.configure("Danger.TButton", background=COLOR["danger"], foreground="#ffffff")
        style.map("Danger.TButton", background=[("active", "#991b1b"), ("disabled", "#d8a0a0")])
        style.configure(
            "Treeview",
            rowheight=26,
            font=FONT["base"],
            fieldbackground=COLOR["surface"],
            background=COLOR["surface"],
        )
        style.configure(
            "Treeview.Heading",
            font=FONT["small"],
            foreground=COLOR["text_muted"],
            background=COLOR["surface_alt"],
        )
        style.map("Treeview", background=[("selected", COLOR["info_bg"])], foreground=[("selected", COLOR["info"])])

    def _build_layout(self) -> None:
        # 主窗口采用 grid，确保 Notebook 与内部表格随窗口缩放。
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 4))

        # 底部状态栏：统一反馈执行状态（就绪/运行中/完成/失败）
        statusbar = tk.Frame(self.root, bg=COLOR["bg"])
        statusbar.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
        statusbar.columnconfigure(2, weight=1)
        self.status_dot = tk.Label(statusbar, text="●", font=FONT["small"], fg=COLOR["info"], bg=COLOR["bg"])
        self.status_dot.grid(row=0, column=0, sticky=tk.W, padx=(10, 4), pady=4)
        self.status_label = tk.Label(
            statusbar,
            textvariable=self.status_var,
            font=FONT["small"],
            fg=COLOR["text_muted"],
            bg=COLOR["bg"],
        )
        self.status_label.grid(row=0, column=1, sticky=tk.W, pady=4)
        ttk.Label(
            statusbar,
            text=f"盘符 {self.drive_var.get()}  ·  管理员: {'是' if is_admin() else '否'}  ·  提示：悬停按钮可查看说明",
            style="TLabel",
        ).grid(row=0, column=2, sticky=tk.E, padx=10)

        self.tab_quick = ttk.Frame(self.notebook)
        self.tab_top_dirs = ttk.Frame(self.notebook)
        self.tab_dism = ttk.Frame(self.notebook)
        self.tab_log = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_quick, text="快速清理")
        self.notebook.add(self.tab_top_dirs, text="大目录占用")
        self.notebook.add(self.tab_dism, text="深度清理")
        self.notebook.add(self.tab_log, text="日志")

        self._build_tab_quick()
        self._build_tab_top_dirs()
        self._build_tab_dism()
        self._build_tab_log()

    def _build_tab_quick(self) -> None:
        tab = self.tab_quick
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(4, weight=1)

        controls = ttk.LabelFrame(tab, text="扫描/清理参数")
        controls.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        for idx in range(6):
            controls.columnconfigure(idx, weight=1 if idx in (4, 5) else 0)

        ttk.Label(controls, text="盘符：").grid(row=0, column=0, sticky=tk.W, padx=6, pady=6)
        ttk.Entry(controls, textvariable=self.drive_var, width=8).grid(row=0, column=1, sticky=tk.W, padx=6)
        ttk.Label(controls, text="临时文件最小天数：").grid(row=0, column=2, sticky=tk.W, padx=6)
        ttk.Entry(controls, textvariable=self.older_days_var, width=8).grid(row=0, column=3, sticky=tk.W, padx=6)
        ttk.Label(controls, text="Top 数量：").grid(row=0, column=4, sticky=tk.W, padx=6)
        ttk.Entry(controls, textvariable=self.top_var, width=8).grid(row=0, column=5, sticky=tk.W, padx=6)

        mode_frame = ttk.Frame(controls)
        mode_frame.grid(row=1, column=0, columnspan=6, sticky=tk.W, padx=6, pady=(0, 6))
        ttk.Checkbutton(mode_frame, text="清理模式（--clean --yes）", variable=self.clean_var).pack(side=tk.LEFT, padx=(0, 16))
        self.permanent_check = ttk.Checkbutton(mode_frame, text="永久删除（高风险）", variable=self.permanent_var)
        self.permanent_check.pack(side=tk.LEFT)
        Tooltip(self.permanent_check, "勾选后删除的文件不进入回收站，直接永久删除、无法恢复。仅建议在确认无误时使用。")

        target_frame = ttk.LabelFrame(tab, text="清理目标（多选）")
        target_frame.grid(row=1, column=0, sticky="ew", padx=6, pady=6)
        # 3 列布局：兼顾名称完整显示与纵向空间利用（16 个目标 -> 6 行）
        for idx in range(3):
            target_frame.columnconfigure(idx, weight=1)

        col = 0
        row = 0
        for target, var in self.target_vars.items():
            ttk.Checkbutton(target_frame, text=target, variable=var).grid(row=row, column=col, sticky=tk.W, padx=10, pady=4)
            col += 1
            if col >= 3:
                row += 1
                col = 0

        button_frame = ttk.Frame(tab)
        button_frame.grid(row=2, column=0, sticky="ew", padx=6, pady=6)
        self.scan_button = ttk.Button(
            button_frame, text="执行扫描（dry-run）", style="Accent.TButton", command=lambda: self._run_scan(clean=False)
        )
        self.scan_button.pack(side=tk.LEFT, padx=6)
        Tooltip(self.scan_button, "仅预览将要删除的内容，不真正删除任何文件。首次使用建议先执行扫描，确认无误后再清理。")
        self.clean_scan_button = ttk.Button(
            button_frame, text="执行清理（clean）", style="Danger.TButton", command=lambda: self._run_scan(clean=True)
        )
        self.clean_scan_button.pack(side=tk.LEFT, padx=6)
        Tooltip(self.clean_scan_button, "真正删除所选目标中的缓存/临时文件（可再生，不含个人文档）。执行前会二次确认。")

        summary_frame = ttk.LabelFrame(tab, text="Target 汇总")
        summary_frame.grid(row=3, column=0, sticky="nsew", padx=6, pady=6)
        summary_frame.columnconfigure(0, weight=1)
        summary_frame.rowconfigure(0, weight=1)

        columns = ("target", "preview", "deleted", "skipped")
        self.summary_tree = ttk.Treeview(summary_frame, columns=columns, show="headings", height=8)
        self.summary_tree.heading("target", text="目标")
        self.summary_tree.heading("preview", text="预览")
        self.summary_tree.heading("deleted", text="已删")
        self.summary_tree.heading("skipped", text="跳过原因")
        self.summary_tree.column("target", width=120)
        self.summary_tree.column("preview", width=220)
        self.summary_tree.column("deleted", width=220)
        self.summary_tree.column("skipped", width=640)
        summary_scroll = ttk.Scrollbar(summary_frame, orient=tk.VERTICAL, command=self.summary_tree.yview)
        self.summary_tree.configure(yscrollcommand=summary_scroll.set)
        self.summary_tree.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        summary_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=6)
        self._bind_mousewheel(self.summary_tree)

        top_frame = ttk.LabelFrame(tab, text="Top 文件列表")
        top_frame.grid(row=4, column=0, sticky="nsew", padx=6, pady=6)
        top_frame.columnconfigure(0, weight=1)
        top_frame.rowconfigure(0, weight=1)

        top_cols = ("size", "target", "reason", "path")
        self.top_tree = ttk.Treeview(top_frame, columns=top_cols, show="headings")
        for col_name, title, width in [
            ("size", "大小", 120),
            ("target", "目标", 100),
            ("reason", "原因", 180),
            ("path", "路径", 760),
        ]:
            self.top_tree.heading(col_name, text=title)
            self.top_tree.column(col_name, width=width)

        top_scroll = ttk.Scrollbar(top_frame, orient=tk.VERTICAL, command=self.top_tree.yview)
        self.top_tree.configure(yscrollcommand=top_scroll.set)
        self.top_tree.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        top_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=6)
        self._bind_mousewheel(self.top_tree)
        self.top_tree.bind("<Double-1>", self._on_top_tree_double_click)

    def _build_tab_top_dirs(self) -> None:
        tab = self.tab_top_dirs
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

        ctrl = ttk.LabelFrame(tab, text="top_dirs 扫描参数")
        ctrl.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        ctrl.columnconfigure(7, weight=1)

        ttk.Label(ctrl, text="目录深度（--dir-depth）：").grid(row=0, column=0, sticky=tk.W, padx=6, pady=4)
        ttk.Entry(ctrl, textvariable=self.dir_depth_var, width=8).grid(row=0, column=1, sticky=tk.W, padx=6)
        ttk.Label(ctrl, text="输出数量（--top-dirs）：").grid(row=0, column=2, sticky=tk.W, padx=6, pady=4)
        ttk.Entry(ctrl, textvariable=self.top_dirs_var, width=8).grid(row=0, column=3, sticky=tk.W, padx=6)
        ttk.Label(ctrl, text="最小目录（MB）：").grid(row=0, column=4, sticky=tk.W, padx=6, pady=4)
        ttk.Entry(ctrl, textvariable=self.min_dir_size_var, width=8).grid(row=0, column=5, sticky=tk.W, padx=6)
        self.top_dirs_scan_button = ttk.Button(ctrl, text="扫描大目录（仅扫描）", command=self._run_top_dirs_scan)
        self.top_dirs_scan_button.grid(row=0, column=6, sticky=tk.W, padx=6)
        Tooltip(self.top_dirs_scan_button, "按目录深度统计磁盘占用，找出占用空间最大的目录（不删除任何内容）。")

        ttk.Label(ctrl, text="追加目录（逗号分隔）：").grid(row=1, column=0, sticky=tk.W, padx=6, pady=4)
        ttk.Entry(ctrl, textvariable=self.include_dirs_var).grid(row=1, column=1, columnspan=3, sticky="ew", padx=6)
        ttk.Label(ctrl, text="排除目录（逗号分隔）：").grid(row=1, column=4, sticky=tk.W, padx=6, pady=4)
        ttk.Entry(ctrl, textvariable=self.exclude_dirs_var).grid(row=1, column=5, columnspan=3, sticky="ew", padx=6)

        button_frame = ttk.Frame(ctrl)
        button_frame.grid(row=2, column=0, columnspan=8, sticky="ew", padx=6, pady=(4, 2))
        ttk.Label(button_frame, text="下钻深度：").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(button_frame, textvariable=self.drill_depth_var, width=8).pack(side=tk.LEFT, padx=(0, 10))
        self.drill_down_button = ttk.Button(button_frame, text="下钻扫描", command=self._run_drill_down_scan)
        self.drill_down_button.pack(side=tk.LEFT, padx=4)
        Tooltip(self.drill_down_button, "对当前选中目录做更深的子目录扫描，层层查看哪里占空间。")
        self.open_dir_button = ttk.Button(button_frame, text="打开目录", command=self._open_selected_top_path)
        self.open_dir_button.pack(side=tk.LEFT, padx=4)
        Tooltip(self.open_dir_button, "在文件资源管理器中打开当前选中的目录。")
        self.copy_path_button = ttk.Button(button_frame, text="复制选中路径", command=self._copy_selected_top_path)
        self.copy_path_button.pack(side=tk.LEFT, padx=4)
        Tooltip(self.copy_path_button, "把当前选中目录的完整路径复制到剪贴板。")
        self.export_json_button = ttk.Button(button_frame, text="导出报告（JSON）", command=self._export_top_dirs_json)
        self.export_json_button.pack(side=tk.LEFT, padx=4)
        Tooltip(self.export_json_button, "把当前大目录扫描结果导出为 JSON 文件，便于保存与分享。")
        ttk.Label(button_frame, textvariable=self.top_dirs_status_var, foreground="#245").pack(side=tk.RIGHT, padx=6)

        table_frame = ttk.LabelFrame(tab, text="大目录结果")
        table_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        top_dir_cols = ("size", "files", "path", "note")
        self.top_dirs_tree = ttk.Treeview(table_frame, columns=top_dir_cols, show="headings")
        self.top_dirs_tree.heading("size", text="大小", command=lambda: self._sort_top_dirs_table("size"))
        self.top_dirs_tree.heading("files", text="文件数", command=lambda: self._sort_top_dirs_table("files"))
        self.top_dirs_tree.heading("path", text="目录路径", command=lambda: self._sort_top_dirs_table("path"))
        self.top_dirs_tree.heading("note", text="提示")
        self.top_dirs_tree.column("size", width=130, anchor=tk.E)
        self.top_dirs_tree.column("files", width=90, anchor=tk.E)
        self.top_dirs_tree.column("path", width=620)
        self.top_dirs_tree.column("note", width=360)
        top_dirs_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.top_dirs_tree.yview)
        self.top_dirs_tree.configure(yscrollcommand=top_dirs_scroll.set)
        self.top_dirs_tree.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        top_dirs_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=6)
        self._bind_mousewheel(self.top_dirs_tree)
        self.top_dirs_tree.bind("<Double-1>", self._on_top_dirs_tree_double_click)


    def _build_tab_dism(self) -> None:
        tab = self.tab_dism
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)

        dism_frame = ttk.LabelFrame(tab, text="深度清理：组件存储（WinSxS / DISM）")
        dism_frame.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        dism_frame.columnconfigure(5, weight=1)

        ttk.Label(dism_frame, text="当前管理员权限：").grid(row=0, column=0, sticky=tk.W, padx=6, pady=4)
        ttk.Label(dism_frame, textvariable=self.is_admin_var, foreground="#0a7").grid(row=0, column=1, sticky=tk.W, padx=6)
        self.admin_tip_label = ttk.Label(dism_frame, text="", foreground="#b35")
        self.admin_tip_label.grid(row=0, column=2, columnspan=3, sticky=tk.W, padx=6)

        self.relaunch_button = ttk.Button(dism_frame, text="以管理员重新启动 GUI", command=self._relaunch_gui_as_admin)
        self.relaunch_button.grid(row=0, column=5, sticky=tk.E, padx=6)

        self.analyze_button = ttk.Button(dism_frame, text="Analyze（分析）", command=self._run_analyze)
        self.analyze_button.grid(row=1, column=0, sticky=tk.W, padx=6, pady=6)
        Tooltip(self.analyze_button, "分析 WinSxS 组件存储，评估可回收空间（只分析不删除）。")
        self.clean_button = ttk.Button(dism_frame, text="Clean（清理）", style="Danger.TButton", command=self._run_clean)
        self.clean_button.grid(row=1, column=1, sticky=tk.W, padx=6, pady=6)
        Tooltip(self.clean_button, "清理组件存储中已废弃的旧版本组件（需管理员权限）。")
        self.resetbase_button = ttk.Button(
            dism_frame, text="ResetBase（不可逆）", style="Danger.TButton", command=self._run_resetbase
        )
        self.resetbase_button.grid(row=1, column=2, sticky=tk.W, padx=6, pady=6)
        Tooltip(self.resetbase_button, "高风险的不可逆操作：合并更新基座，执行后将无法卸载当前已安装的更新。需勾选确认并输入 RESETBASE。")

        ttk.Checkbutton(dism_frame, text="我已理解 ResetBase 风险", variable=self.resetbase_ack_var).grid(
            row=2, column=0, columnspan=2, sticky=tk.W, padx=6, pady=4
        )
        ttk.Label(dism_frame, text="输入 RESETBASE 二次确认：").grid(row=2, column=2, sticky=tk.E, padx=6)
        ttk.Entry(dism_frame, textvariable=self.resetbase_text_var, width=18).grid(row=2, column=3, sticky=tk.W, padx=6)
        ttk.Label(
            dism_frame,
            text="风险说明：ResetBase 后无法卸载当前更新，建议先做系统备份。",
            foreground="#b35",
        ).grid(row=3, column=0, columnspan=6, sticky=tk.W, padx=6, pady=(2, 6))

        self.resetbase_ack_var.trace_add("write", lambda *_: self._refresh_dism_controls())
        self.resetbase_text_var.trace_add("write", lambda *_: self._refresh_dism_controls())

        analyze_result = ttk.LabelFrame(tab, text="Analyze 结构化结果")
        analyze_result.grid(row=1, column=0, sticky="ew", padx=6, pady=6)
        for idx in range(4):
            analyze_result.columnconfigure(idx, weight=1)

        fields = [
            ("资源管理器报告大小", "explorer_reported_size"),
            ("组件存储实际大小", "actual_size"),
            ("已与 Windows 共享", "shared_with_windows"),
            ("备份与禁用功能", "backups_and_disabled_features"),
            ("缓存与临时数据", "cache_and_temp_data"),
            ("上次清理日期", "last_cleanup_date"),
            ("可回收程序包数", "reclaimable_packages"),
            ("是否建议清理", "cleanup_recommended_bool"),
        ]
        for idx, (label_text, key) in enumerate(fields):
            row = idx // 2
            col = (idx % 2) * 2
            ttk.Label(analyze_result, text=label_text + "：").grid(row=row, column=col, sticky=tk.W, padx=6, pady=3)
            ttk.Label(analyze_result, textvariable=self.dism_summary_vars[key]).grid(row=row, column=col + 1, sticky=tk.W, padx=6, pady=3)

        raw_frame = ttk.LabelFrame(tab, text="Analyze 原始输出")
        raw_frame.grid(row=2, column=0, sticky="nsew", padx=6, pady=6)
        raw_frame.columnconfigure(0, weight=1)
        raw_frame.rowconfigure(1, weight=1)

        ttk.Checkbutton(
            raw_frame,
            text="显示 Analyze 原始输出",
            variable=self.show_raw_analyze_var,
            command=self._toggle_raw_analyze_output,
        ).grid(row=0, column=0, sticky=tk.W, padx=6, pady=6)

        self.raw_output_frame = ttk.Frame(raw_frame)
        self.raw_output_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        self.raw_output_frame.columnconfigure(0, weight=1)
        self.raw_output_frame.rowconfigure(0, weight=1)

        self.raw_output_text = tk.Text(self.raw_output_frame, wrap="none", height=12)
        raw_scroll = ttk.Scrollbar(self.raw_output_frame, orient=tk.VERTICAL, command=self.raw_output_text.yview)
        self.raw_output_text.configure(yscrollcommand=raw_scroll.set)
        self.raw_output_text.grid(row=0, column=0, sticky="nsew")
        raw_scroll.grid(row=0, column=1, sticky="ns")
        self._bind_mousewheel(self.raw_output_text)
        self._toggle_raw_analyze_output()

    def _build_tab_log(self) -> None:
        tab = self.tab_log
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

        ctrl = ttk.Frame(tab)
        ctrl.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        ttk.Label(ctrl, text="集中日志（stdout / stderr / DISM 输出）").pack(side=tk.LEFT)
        ttk.Button(ctrl, text="复制全部日志", command=self._copy_all_logs).pack(side=tk.RIGHT, padx=6)
        ttk.Button(ctrl, text="清空日志", command=self._clear_logs).pack(side=tk.RIGHT, padx=6)

        log_frame = ttk.LabelFrame(tab, text="日志窗口")
        log_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, wrap="none")
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        log_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=6)
        self._bind_mousewheel(self.log_text)

    def _bind_mousewheel(self, widget: tk.Widget) -> None:
        # Windows 鼠标滚轮绑定到当前表格/文本框，提升长内容可访问性。
        def _on_mousewheel(event: tk.Event) -> str:
            widget.yview_scroll(int(-event.delta / 120), "units")
            return "break"

        widget.bind("<MouseWheel>", _on_mousewheel)

    def _toggle_raw_analyze_output(self) -> None:
        if self.show_raw_analyze_var.get():
            self.raw_output_frame.grid()
        else:
            self.raw_output_frame.grid_remove()

    def _set_status(self, text: str, level: str = "info") -> None:
        """更新底部状态栏文字与颜色。

        level 取值：info / success / warning / error，与语义色一一对应。
        """
        colors = {
            "info": COLOR["info"],
            "success": COLOR["success"],
            "warning": COLOR["warning"],
            "error": COLOR["danger"],
        }
        color = colors.get(level, COLOR["info"])
        self.status_var.set(text)
        self.status_dot.configure(fg=color)
        self.status_label.configure(fg=color)

    def _append_log(self, message: str) -> None:
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def _clear_logs(self) -> None:
        self.log_text.delete("1.0", tk.END)

    def _copy_all_logs(self) -> None:
        content = self.log_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showinfo("提示", "当前没有可复制的日志。")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        messagebox.showinfo("已复制", "日志内容已复制到剪贴板。")

    def _refresh_dism_controls(self) -> None:
        admin = self.is_admin_var.get() == "是"
        can_resetbase = admin and self.resetbase_ack_var.get() and self.resetbase_text_var.get().strip() == "RESETBASE"
        self.analyze_button.configure(state=tk.NORMAL)
        self.clean_button.configure(state=tk.NORMAL if admin else tk.DISABLED)
        self.resetbase_button.configure(state=tk.NORMAL if can_resetbase else tk.DISABLED)
        if admin:
            self.admin_tip_label.configure(text="")
            self.relaunch_button.configure(state=tk.DISABLED)
        else:
            self.admin_tip_label.configure(text="当前非管理员：Analyze 可执行，Clean/ResetBase 需管理员")
            self.relaunch_button.configure(state=tk.NORMAL)

    def _set_dism_running(self, running: bool) -> None:
        state = tk.DISABLED if running else tk.NORMAL
        self.analyze_button.configure(state=state)
        self.clean_button.configure(state=state)
        self.resetbase_button.configure(state=state)

    def _set_cli_running(self, running: bool) -> None:
        state = tk.DISABLED if running else tk.NORMAL
        self.scan_button.configure(state=state)
        self.clean_scan_button.configure(state=state)
        self.top_dirs_scan_button.configure(state=state)
        self.drill_down_button.configure(state=state)
        if not running:
            self._refresh_dism_controls()

    def _relaunch_gui_as_admin(self) -> None:
        try:
            ok = relaunch_as_admin()
        except Exception as exc:
            messagebox.showerror("提权失败", f"无法触发管理员启动：{exc}")
            return
        if ok:
            self._append_log("已尝试以管理员权限启动新 GUI 实例，请在 UAC 弹窗确认。")
        else:
            messagebox.showwarning("提权未启动", "未能启动管理员实例，请手动以管理员身份运行。")

    def _run_analyze(self) -> None:
        if self.is_admin_var.get() != "是":
            messagebox.showinfo("权限提示", "当前为非管理员，Analyze 可执行，但部分操作建议管理员。")
        self._run_dism_action("Analyze", DISM_ANALYZE_ARGS)

    def _run_clean(self) -> None:
        if self.is_admin_var.get() != "是":
            messagebox.showwarning(
                "权限不足", "Clean 需要管理员权限。\n\n请关闭程序后右键“以管理员身份运行”，再执行此操作。"
            )
            return
        self._run_dism_action("Clean", DISM_CLEAN_ARGS)

    def _run_resetbase(self) -> None:
        if self.is_admin_var.get() != "是":
            messagebox.showwarning("权限不足", "ResetBase 需要管理员权限，请以管理员身份运行")
            return
        if not self.resetbase_ack_var.get() or self.resetbase_text_var.get().strip() != "RESETBASE":
            messagebox.showwarning(
                "二次确认未完成",
                "请先勾选“我已理解 ResetBase 风险”，并在输入框中输入 RESETBASE（需与提示完全一致）。",
            )
            return
        if not messagebox.askyesno(
            "最终确认",
            "ResetBase 是不可逆操作：执行后将无法卸载当前已安装的更新。\n\n建议先做系统备份。确定继续？",
        ):
            return
        self._run_dism_action("ResetBase", DISM_RESETBASE_ARGS)

    def _run_dism_action(self, action_name: str, args: list[str]) -> None:
        self._append_log("=" * 72)
        self._append_log(f"[DISM] 开始执行 {action_name}: DISM {' '.join(args)}")
        self._set_dism_running(True)

        # 所有耗时命令均在线程中运行，避免 Tk 主线程卡死。
        def _worker() -> None:
            output_text = ""
            try:
                code, output_text = run_dism_stream(args, lambda line: self.root.after(0, self._append_log, line))
            except Exception as exc:
                self.root.after(0, lambda: messagebox.showerror("DISM 执行失败", str(exc)))
                self.root.after(0, self._set_dism_running, False)
                return

            def _finish() -> None:
                self._append_log(f"[DISM] {action_name} 退出码: {code}")
                if action_name == "Analyze":
                    self._render_analyze_result(output_text)
                if code == 0:
                    messagebox.showinfo("DISM", f"{action_name} 执行完成")
                else:
                    messagebox.showerror("DISM 执行失败", f"{action_name} 执行失败，退出码: {code}")
                self._set_dism_running(False)

            self.root.after(0, _finish)

        threading.Thread(target=_worker, daemon=True).start()

    def _render_analyze_result(self, output_text: str) -> None:
        parsed = parse_analyze_output(output_text)
        for key, var in self.dism_summary_vars.items():
            var.set(parsed.get(key, "").strip() or "-")

        self.raw_output_text.delete("1.0", tk.END)
        self.raw_output_text.insert("1.0", parsed.get("raw_output", ""))

    def _selected_targets(self) -> list[str]:
        return [name for name, var in self.target_vars.items() if var.get()]

    def _run_scan(self, clean: bool) -> None:
        targets = self._selected_targets()
        if not targets:
            messagebox.showwarning("未选择清理目标", "请至少勾选一个清理目标（如 temp、browser_cache 等），再执行扫描或清理。")
            return

        if clean and "top_dirs" in targets:
            messagebox.showwarning("参数冲突", "top_dirs 仅用于查看大目录占用，不支持清理。请取消勾选后重试。")
            return

        if clean and any(t in SYSTEM_TARGETS for t in targets) and self.is_admin_var.get() != "是":
            messagebox.showwarning(
                "权限不足",
                "所选目标（dumps / do_cache / update_cache）在清理模式下需要管理员权限。\n\n"
                "请以管理员身份重新运行本程序（或点击上方提示操作）。",
            )
            return

        if clean:
            mode_tip = "（注意：已勾选“永久删除”，文件不进入回收站，无法恢复）" if self.permanent_var.get() else "（默认进入回收站，可恢复）"
            if not messagebox.askyesno(
                "确认清理",
                f"即将删除所选目标的缓存/临时文件（可再生，不含个人文档）。\n\n{mode_tip}\n\n是否继续？",
            ):
                return

        self._append_log("=" * 72)
        self._append_log(f"开始执行: {'clean' if clean else 'dry-run'}")
        self._set_cli_running(True)
        self._set_status("任务执行中，请稍候…", "warning")
        self.top_dirs_status_var.set("任务执行中，请稍候…")
        threading.Thread(target=self._run_cli, args=(targets, clean), daemon=True).start()

    def _run_top_dirs_scan(self) -> None:
        self._set_cli_running(True)
        self._set_status("正在扫描大目录，请稍候…", "warning")
        self.top_dirs_status_var.set("正在扫描大目录，请稍候…")
        threading.Thread(target=self._run_cli, args=(['top_dirs'], False), daemon=True).start()

    def _run_drill_down_scan(self) -> None:
        path = self._get_selected_top_path()
        if not path:
            messagebox.showinfo("提示", "请先在大目录表格中选择一行。")
            return
        self._set_cli_running(True)
        self._set_status(f"正在下钻扫描：{path}", "warning")
        self.top_dirs_status_var.set(f"正在下钻扫描：{path}")
        threading.Thread(target=self._run_cli, args=(['top_dirs'], False, path), daemon=True).start()

    def _get_selected_top_path(self) -> str:
        selected = self.top_dirs_tree.selection()
        if not selected:
            return ""
        values = self.top_dirs_tree.item(selected[0], "values")
        if len(values) < 3:
            return ""
        return str(values[2])

    def _copy_selected_top_path(self) -> None:
        path = self._get_selected_top_path()
        if not path:
            messagebox.showinfo("提示", "请先在大目录表格中选择一行。")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(path)
        messagebox.showinfo("已复制", f"路径已复制：\n{path}")

    def _open_selected_top_path(self) -> None:
        path = self._get_selected_top_path()
        if not path:
            messagebox.showinfo("提示", "请先在大目录表格中选择一行。")
            return
        self._open_path_in_explorer(path, select_file=False)

    def _open_path_in_explorer(self, path: str, select_file: bool) -> bool:
        # 双击表格后快速跳转，帮助用户直接定位到占用空间的目录/文件。
        target = Path(path)
        if not target.exists():
            messagebox.showwarning("路径不存在", "路径不存在/已删除")
            return False

        # 优先使用 subprocess 参数列表调用 explorer，避免空格和中文路径被错误拆分。
        try:
            if os.name == "nt":
                if select_file and target.is_file():
                    subprocess.Popen(["explorer", f"/select,{str(target)}"])
                else:
                    subprocess.Popen(["explorer", str(target)])
            else:
                os.startfile(str(target))
        except AttributeError:
            messagebox.showwarning("平台限制", "当前平台不支持 os.startfile，仅 Windows 可直接打开目录。")
            return False
        except OSError as exc:
            # 对异常场景统一提示，避免双击无反馈导致误判为程序卡死。
            messagebox.showerror("打开失败", f"无法打开路径：{exc}")
            return False

        self._append_log(f"已打开：{target}")
        return True

    def _on_top_dirs_tree_double_click(self, event: tk.Event) -> str | None:
        row_id = self.top_dirs_tree.identify_row(event.y)
        if not row_id:
            return "break"
        values = self.top_dirs_tree.item(row_id, "values")
        if len(values) < 3:
            return "break"
        self._open_path_in_explorer(str(values[2]), select_file=False)
        return "break"

    def _on_top_tree_double_click(self, event: tk.Event) -> str | None:
        row_id = self.top_tree.identify_row(event.y)
        if not row_id:
            return "break"
        values = self.top_tree.item(row_id, "values")
        if len(values) < 4:
            return "break"
        path = str(values[3])
        target = Path(path)
        if not target.exists():
            messagebox.showwarning("路径不存在", "路径不存在/已删除")
            return "break"
        self._open_path_in_explorer(path, select_file=target.is_file())
        return "break"

    def _export_top_dirs_json(self) -> None:
        if not self.top_dirs_rows:
            messagebox.showinfo("提示", "当前没有可导出的大目录结果。")
            return
        out = Path.cwd() / f"top_dirs_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        out.write_text(json.dumps(self.top_dirs_rows, ensure_ascii=False, indent=2), encoding="utf-8")
        self._append_log(f"大目录报告已导出: {out}")
        messagebox.showinfo("导出完成", f"已导出到：\n{out}")

    def _sort_top_dirs_table(self, column: str) -> None:
        reverse = not self.top_dirs_sort_state.get(column, False)
        self.top_dirs_sort_state[column] = reverse

        def _key(row: dict) -> tuple:
            if column == "size":
                return (int(row.get("size_bytes", 0)),)
            if column == "files":
                return (int(row.get("file_count", 0)),)
            return (str(row.get("path", "")),)

        self.top_dirs_rows.sort(key=_key, reverse=reverse)
        self._refresh_top_dirs_table()

    def _refresh_top_dirs_table(self) -> None:
        for item in self.top_dirs_tree.get_children():
            self.top_dirs_tree.delete(item)
        for row in self.top_dirs_rows:
            self.top_dirs_tree.insert(
                "",
                tk.END,
                values=(
                    row.get("size_human", ""),
                    row.get("file_count", ""),
                    row.get("path", ""),
                    row.get("note", ""),
                ),
            )


    def _run_cli(self, targets: list[str], clean: bool, drill_root: str = "") -> None:
        try:
            older_days = max(0, int(self.older_days_var.get().strip()))
            top_n = max(1, int(self.top_var.get().strip()))
            dir_depth = max(0, int(self.drill_depth_var.get().strip())) if drill_root else max(0, int(self.dir_depth_var.get().strip()))
            top_dirs = max(1, int(self.top_dirs_var.get().strip()))
            min_dir_size_mb = max(0, int(self.min_dir_size_var.get().strip()))
        except ValueError:
            self.root.after(0, lambda: messagebox.showerror("参数错误", "数值参数必须是整数"))
            self.root.after(0, self._set_cli_running, False)
            return

        drive = self.drive_var.get().strip() or "C:"
        try:
            with tempfile.TemporaryDirectory(prefix="clearc_gui_") as tmp_dir:
                json_path = Path(tmp_dir) / "report.json"
                clearc_cli_args = [
                "--drive",
                drive,
                "--targets",
                ",".join(targets),
                "--older-than-days",
                str(older_days),
                "--top",
                str(top_n),
                "--dir-depth",
                str(dir_depth),
                "--top-dirs",
                str(top_dirs),
                "--min-dir-size-mb",
                str(min_dir_size_mb),
                "--json",
                str(json_path),
            ]
                include_dirs = self.include_dirs_var.get().strip()
                exclude_dirs = self.exclude_dirs_var.get().strip()
                if drill_root:
                    include_dirs = drill_root
                if include_dirs:
                    clearc_cli_args.extend(["--include-dirs", include_dirs])
                if exclude_dirs:
                    clearc_cli_args.extend(["--exclude-dirs", exclude_dirs])
                if clean:
                    clearc_cli_args.extend(["--clean", "--yes"])
                else:
                    clearc_cli_args.append("--dry-run")
                if self.permanent_var.get() and clean:
                    clearc_cli_args.append("--permanent-delete")

                if getattr(sys, "frozen", False):
                    # onefile exe 内部调用自身时，必须显式走 --_cli 分支；
                    # 否则会再次启动 GUI，形成“点击按钮不断弹新窗口”的递归自调用。
                    cmd = [sys.executable, "--_cli", *clearc_cli_args]
                else:
                    cmd = [sys.executable, "-m", "clearc", *clearc_cli_args]

                env = os.environ.copy()
                env["PYTHONUTF8"] = "1"
                env["PYTHONIOENCODING"] = "utf-8"
                popen_kwargs: dict = {}
                if getattr(sys, "frozen", False):
                    popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                else:
                    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
                completed = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=env,
                    cwd=str(Path(__file__).resolve().parents[2]),
                    check=False,
                    **popen_kwargs,
                )

                def _update_log() -> None:
                    self._append_log("命令: " + " ".join(cmd))
                    if completed.stdout.strip():
                        self._append_log("[stdout]\n" + completed.stdout.strip())
                    if completed.stderr.strip():
                        self._append_log("[stderr]\n" + completed.stderr.strip())
                    self._append_log(f"退出码: {completed.returncode}")

                self.root.after(0, _update_log)
                if completed.returncode != 0:
                    self.root.after(0, lambda: self.top_dirs_status_var.set("扫描失败，请检查日志"))
                    self.root.after(0, lambda: self._set_status("扫描失败，请查看日志", "error"))
                    return

                try:
                    report = json.loads(json_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    self.root.after(0, lambda: self._append_log(f"读取/解析 JSON 失败: {exc}"))
                    return
                self.root.after(0, lambda: self._render_report(report))
                self.root.after(0, lambda: self.top_dirs_status_var.set("扫描完成"))
                self.root.after(0, lambda: self._set_status("扫描完成", "success"))
        except Exception as exc:
            self.root.after(0, lambda: self._append_log(f"执行失败: {exc}"))
            self.root.after(0, lambda: self.top_dirs_status_var.set("扫描失败，请检查日志"))
            self.root.after(0, lambda: self._set_status("扫描失败，请查看日志", "error"))
        finally:
            self.root.after(0, self._set_cli_running, False)

    def _render_report(self, report: dict) -> None:
        self.latest_report = report
        self.top_dirs_rows = []
        for item in self.summary_tree.get_children():
            self.summary_tree.delete(item)
        for item in self.top_tree.get_children():
            self.top_tree.delete(item)

        summary = report.get("summary", {})
        for target_item in summary.get("targets", []):
            skipped = target_item.get("skipped", {})
            target_name = target_item.get("target", "")
            extra_tip = ""
            if target_name == "do_cache" and skipped.get("not_found", 0) > 0:
                extra_tip = "；未检测到 Delivery Optimization 缓存目录（系统未生成或功能关闭），无需清理。"

            skipped_text = (
                f"权限不足={skipped.get('permission_denied', 0)}，"
                f"被占用={skipped.get('in_use', 0)}，"
                f"未找到={skipped.get('not_found', 0)}"
                f"{extra_tip}"
            )
            self.summary_tree.insert(
                "",
                tk.END,
                values=(
                    target_name,
                    f"{target_item.get('preview_files', 0)} / {target_item.get('preview_size_human', '-')}",
                    f"{target_item.get('deleted_files', 0)} / {target_item.get('deleted_size_human', '-')}",
                    skipped_text,
                ),
            )

        for top_item in report.get("top_files", []):
            self.top_tree.insert(
                "",
                tk.END,
                values=(
                    top_item.get("size_human", ""),
                    top_item.get("target", ""),
                    top_item.get("reason", ""),
                    top_item.get("path", ""),
                ),
            )
            if top_item.get("target") == "top_dirs":
                self.top_dirs_rows.append(top_item)

        self._refresh_top_dirs_table()

        if self.top_dirs_rows:
            top3 = self.top_dirs_rows[:3]
            top3_text = "；".join(f"{item.get('path', '')} ({item.get('size_human', '-')})" for item in top3)
            self._append_log("最大目录 Top 3: " + top3_text)

        self._append_log(
            "汇总: preview={0} files ({1}), deleted={2} files ({3})".format(
                summary.get("preview_files", 0),
                summary.get("preview_size_human", "-"),
                summary.get("deleted_files", 0),
                summary.get("deleted_size_human", "-"),
            )
        )



def main() -> int:
    root = tk.Tk()
    try:
        # 适配高分屏/系统缩放，保证文字清晰
        root.tk.call("tk", "scaling", 1.25)
    except tk.TclError:
        pass
    ClearCGUI(root)
    root.update_idletasks()
    w = root.winfo_width()
    h = root.winfo_height()
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"+{x}+{y}")
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
