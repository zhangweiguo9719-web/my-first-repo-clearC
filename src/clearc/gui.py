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


class ClearCGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("clearc 图形界面")
        self.root.geometry("1180x860")

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

        self._build_layout()
        self._refresh_dism_controls()

    def _build_layout(self) -> None:
        # 主窗口采用 grid，确保 Notebook 与内部表格随窗口缩放。
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

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
        for idx in range(8):
            controls.columnconfigure(idx, weight=1 if idx in (6, 7) else 0)

        ttk.Label(controls, text="盘符：").grid(row=0, column=0, sticky=tk.W, padx=6, pady=6)
        ttk.Entry(controls, textvariable=self.drive_var, width=8).grid(row=0, column=1, sticky=tk.W, padx=6)
        ttk.Label(controls, text="临时文件最小天数：").grid(row=0, column=2, sticky=tk.W, padx=6)
        ttk.Entry(controls, textvariable=self.older_days_var, width=8).grid(row=0, column=3, sticky=tk.W, padx=6)
        ttk.Label(controls, text="Top 数量：").grid(row=0, column=4, sticky=tk.W, padx=6)
        ttk.Entry(controls, textvariable=self.top_var, width=8).grid(row=0, column=5, sticky=tk.W, padx=6)

        ttk.Checkbutton(controls, text="清理模式（--clean --yes）", variable=self.clean_var).grid(
            row=0, column=6, sticky=tk.W, padx=6
        )
        ttk.Checkbutton(controls, text="永久删除（高风险）", variable=self.permanent_var).grid(
            row=0, column=7, sticky=tk.W, padx=6
        )

        target_frame = ttk.LabelFrame(tab, text="清理目标（多选）")
        target_frame.grid(row=1, column=0, sticky="ew", padx=6, pady=6)
        for idx in range(4):
            target_frame.columnconfigure(idx, weight=1)

        col = 0
        row = 0
        for target, var in self.target_vars.items():
            ttk.Checkbutton(target_frame, text=target, variable=var).grid(row=row, column=col, sticky=tk.W, padx=10, pady=4)
            col += 1
            if col >= 4:
                row += 1
                col = 0

        button_frame = ttk.Frame(tab)
        button_frame.grid(row=2, column=0, sticky="ew", padx=6, pady=6)
        ttk.Button(button_frame, text="执行扫描（dry-run）", command=lambda: self._run_scan(clean=False)).pack(side=tk.LEFT, padx=6)
        ttk.Button(button_frame, text="执行清理（clean）", command=lambda: self._run_scan(clean=True)).pack(side=tk.LEFT, padx=6)

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
        ttk.Button(ctrl, text="扫描大目录（仅扫描）", command=self._run_top_dirs_scan).grid(row=0, column=6, sticky=tk.W, padx=6)

        ttk.Label(ctrl, text="追加目录（逗号分隔）：").grid(row=1, column=0, sticky=tk.W, padx=6, pady=4)
        ttk.Entry(ctrl, textvariable=self.include_dirs_var).grid(row=1, column=1, columnspan=3, sticky="ew", padx=6)
        ttk.Label(ctrl, text="排除目录（逗号分隔）：").grid(row=1, column=4, sticky=tk.W, padx=6, pady=4)
        ttk.Entry(ctrl, textvariable=self.exclude_dirs_var).grid(row=1, column=5, columnspan=3, sticky="ew", padx=6)

        button_frame = ttk.Frame(ctrl)
        button_frame.grid(row=2, column=0, columnspan=8, sticky="ew", padx=6, pady=(4, 2))
        ttk.Label(button_frame, text="下钻深度：").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(button_frame, textvariable=self.drill_depth_var, width=8).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="下钻扫描", command=self._run_drill_down_scan).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_frame, text="打开目录", command=self._open_selected_top_path).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_frame, text="复制选中路径", command=self._copy_selected_top_path).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_frame, text="导出报告（JSON）", command=self._export_top_dirs_json).pack(side=tk.LEFT, padx=4)
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
        self.clean_button = ttk.Button(dism_frame, text="Clean（清理）", command=self._run_clean)
        self.clean_button.grid(row=1, column=1, sticky=tk.W, padx=6, pady=6)
        self.resetbase_button = ttk.Button(dism_frame, text="ResetBase（不可逆）", command=self._run_resetbase)
        self.resetbase_button.grid(row=1, column=2, sticky=tk.W, padx=6, pady=6)

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
            messagebox.showwarning("权限不足", "Clean 需要管理员权限，请以管理员身份运行")
            return
        self._run_dism_action("Clean", DISM_CLEAN_ARGS)

    def _run_resetbase(self) -> None:
        if self.is_admin_var.get() != "是":
            messagebox.showwarning("权限不足", "ResetBase 需要管理员权限，请以管理员身份运行")
            return
        if not self.resetbase_ack_var.get() or self.resetbase_text_var.get().strip() != "RESETBASE":
            messagebox.showwarning("二次确认未完成", "请勾选风险确认并输入 RESETBASE")
            return
        if not messagebox.askyesno("最终确认", "ResetBase 不可逆，执行后将失去卸载现有更新的能力，确定继续？"):
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
            messagebox.showwarning("clearc GUI", "请至少选择一个 target")
            return

        if clean and "top_dirs" in targets:
            messagebox.showwarning("参数冲突", "top_dirs 仅支持 dry-run，不支持 clean。")
            return

        if clean and any(t in SYSTEM_TARGETS for t in targets) and self.is_admin_var.get() != "是":
            messagebox.showwarning("权限不足", "dumps/do_cache/update_cache 在 clean 模式下需要管理员权限。")
            return

        if clean and not messagebox.askyesno("确认", "将执行清理操作（--clean --yes），是否继续？"):
            return

        self._append_log("=" * 72)
        self._append_log(f"开始执行: {'clean' if clean else 'dry-run'}")
        threading.Thread(target=self._run_cli, args=(targets, clean), daemon=True).start()

    def _run_top_dirs_scan(self) -> None:
        self.top_dirs_status_var.set("正在扫描大目录，请稍候…")
        threading.Thread(target=self._run_cli, args=(['top_dirs'], False), daemon=True).start()

    def _run_drill_down_scan(self) -> None:
        path = self._get_selected_top_path()
        if not path:
            messagebox.showinfo("提示", "请先在大目录表格中选择一行。")
            return
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
        if not Path(path).exists():
            messagebox.showwarning("路径不存在", f"目标路径不存在：\n{path}")
            return
        try:
            os.startfile(path)
        except AttributeError:
            messagebox.showwarning("平台限制", "当前平台不支持 os.startfile，仅 Windows 可直接打开目录。")
        except OSError as exc:
            messagebox.showerror("打开失败", f"无法打开目录：{exc}")

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
            return

        drive = self.drive_var.get().strip() or "C:"
        with tempfile.TemporaryDirectory(prefix="clearc_gui_") as tmp_dir:
            json_path = Path(tmp_dir) / "report.json"
            cmd = [
                sys.executable,
                "-m",
                "clearc",
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
                cmd.extend(["--include-dirs", include_dirs])
            if exclude_dirs:
                cmd.extend(["--exclude-dirs", exclude_dirs])
            if clean:
                cmd.extend(["--clean", "--yes"])
            else:
                cmd.append("--dry-run")
            if self.permanent_var.get() and clean:
                cmd.append("--permanent-delete")

            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                cwd=str(Path(__file__).resolve().parents[2]),
                check=False,
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
                return

            try:
                report = json.loads(json_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                self.root.after(0, lambda: self._append_log(f"读取/解析 JSON 失败: {exc}"))
                return
            self.root.after(0, lambda: self._render_report(report))
            self.root.after(0, lambda: self.top_dirs_status_var.set("扫描完成"))

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
    ClearCGUI(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
