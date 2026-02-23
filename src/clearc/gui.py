# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
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
        self.root.geometry("1100x820")

        self.drive_var = tk.StringVar(value="C:")
        self.older_days_var = tk.StringVar(value="7")
        self.top_var = tk.StringVar(value="20")
        self.dir_depth_var = tk.StringVar(value="2")
        self.top_dirs_var = tk.StringVar(value="20")
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

        self._build_layout()
        self._refresh_dism_controls()

    def _build_layout(self) -> None:
        controls = ttk.LabelFrame(self.root, text="扫描/清理参数")
        controls.pack(fill=tk.X, padx=10, pady=8)

        ttk.Label(controls, text="盘符：").grid(row=0, column=0, sticky=tk.W, padx=6, pady=6)
        ttk.Entry(controls, textvariable=self.drive_var, width=8).grid(row=0, column=1, sticky=tk.W, padx=6)
        ttk.Label(controls, text="临时文件最小天数：").grid(row=0, column=2, sticky=tk.W, padx=6)
        ttk.Entry(controls, textvariable=self.older_days_var, width=8).grid(row=0, column=3, sticky=tk.W, padx=6)
        ttk.Label(controls, text="Top 数量：").grid(row=0, column=4, sticky=tk.W, padx=6)
        ttk.Entry(controls, textvariable=self.top_var, width=8).grid(row=0, column=5, sticky=tk.W, padx=6)

        ttk.Checkbutton(controls, text="清理模式（--clean --yes）", variable=self.clean_var).grid(row=0, column=6, sticky=tk.W, padx=6)
        ttk.Checkbutton(controls, text="永久删除（高风险）", variable=self.permanent_var).grid(row=0, column=7, sticky=tk.W, padx=6)

        target_frame = ttk.LabelFrame(self.root, text="清理目标（多选）")
        target_frame.pack(fill=tk.X, padx=10, pady=8)

        col = 0
        row = 0
        for target, var in self.target_vars.items():
            ttk.Checkbutton(target_frame, text=target, variable=var).grid(row=row, column=col, sticky=tk.W, padx=10, pady=4)
            col += 1
            if col >= 4:
                row += 1
                col = 0

        button_frame = ttk.Frame(self.root)
        button_frame.pack(fill=tk.X, padx=10, pady=6)
        ttk.Button(button_frame, text="执行扫描（dry-run）", command=lambda: self._run_scan(clean=False)).pack(side=tk.LEFT, padx=6)
        ttk.Button(button_frame, text="执行清理（clean）", command=lambda: self._run_scan(clean=True)).pack(side=tk.LEFT, padx=6)

        # 仅扫描：大目录占用 Top
        top_dirs_frame = ttk.LabelFrame(self.root, text="仅扫描：大目录占用 Top")
        top_dirs_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=8)
        ttk.Label(top_dirs_frame, text="目录深度（--dir-depth）：").grid(row=0, column=0, sticky=tk.W, padx=6, pady=4)
        ttk.Entry(top_dirs_frame, textvariable=self.dir_depth_var, width=8).grid(row=0, column=1, sticky=tk.W, padx=6)
        ttk.Label(top_dirs_frame, text="输出数量（--top-dirs）：").grid(row=0, column=2, sticky=tk.W, padx=6, pady=4)
        ttk.Entry(top_dirs_frame, textvariable=self.top_dirs_var, width=8).grid(row=0, column=3, sticky=tk.W, padx=6)
        ttk.Button(top_dirs_frame, text="扫描大目录（仅扫描）", command=self._run_top_dirs_scan).grid(
            row=0, column=4, sticky=tk.W, padx=6
        )
        ttk.Button(top_dirs_frame, text="复制选中路径", command=self._copy_selected_top_path).grid(row=0, column=5, sticky=tk.W, padx=6)

        top_dir_cols = ("size", "files", "path")
        self.top_dirs_tree = ttk.Treeview(top_dirs_frame, columns=top_dir_cols, show="headings", height=6)
        self.top_dirs_tree.heading("size", text="大小")
        self.top_dirs_tree.heading("files", text="文件数")
        self.top_dirs_tree.heading("path", text="目录路径")
        self.top_dirs_tree.column("size", width=120)
        self.top_dirs_tree.column("files", width=120)
        self.top_dirs_tree.column("path", width=760)
        self.top_dirs_tree.grid(row=1, column=0, columnspan=6, sticky="nsew", padx=6, pady=6)
        top_dirs_frame.grid_columnconfigure(5, weight=1)

        dism_frame = ttk.LabelFrame(self.root, text="深度清理：组件存储（WinSxS / DISM）")
        dism_frame.pack(fill=tk.X, padx=10, pady=8)

        ttk.Label(dism_frame, text="当前管理员权限：").grid(row=0, column=0, sticky=tk.W, padx=6, pady=4)
        ttk.Label(dism_frame, textvariable=self.is_admin_var).grid(row=0, column=1, sticky=tk.W, padx=6, pady=4)
        self.admin_tip_label = ttk.Label(dism_frame, text="")
        self.admin_tip_label.grid(row=0, column=2, sticky=tk.W, padx=6)
        self.relaunch_button = ttk.Button(dism_frame, text="以管理员重新启动 GUI", command=self._relaunch_gui_as_admin)
        self.relaunch_button.grid(row=0, column=3, sticky=tk.W, padx=6)

        self.analyze_button = ttk.Button(dism_frame, text="分析 Analyze", command=self._run_analyze)
        self.analyze_button.grid(row=1, column=0, sticky=tk.W, padx=6, pady=4)
        self.clean_button = ttk.Button(dism_frame, text="清理 Clean（StartComponentCleanup）", command=self._run_clean)
        self.clean_button.grid(row=1, column=1, sticky=tk.W, padx=6, pady=4)
        self.resetbase_button = ttk.Button(dism_frame, text="ResetBase（不可逆）", command=self._run_resetbase)
        self.resetbase_button.grid(row=1, column=2, sticky=tk.W, padx=6, pady=4)

        ttk.Label(dism_frame, text="Clean：相对安全，但耗时较久，执行过程中请勿关机。", foreground="#b35a00").grid(
            row=2, column=0, columnspan=4, sticky=tk.W, padx=6
        )
        ttk.Label(
            dism_frame,
            text="ResetBase：不可逆，执行后将失去卸载当前已安装更新的能力。",
            foreground="#b35a00",
        ).grid(row=3, column=0, columnspan=4, sticky=tk.W, padx=6)

        ttk.Checkbutton(
            dism_frame,
            text="我已理解 ResetBase 不可逆风险",
            variable=self.resetbase_ack_var,
            command=self._refresh_dism_controls,
        ).grid(row=4, column=0, columnspan=2, sticky=tk.W, padx=6, pady=4)
        ttk.Label(dism_frame, text="请输入 RESETBASE：").grid(row=4, column=2, sticky=tk.E, padx=6)
        ttk.Entry(dism_frame, textvariable=self.resetbase_text_var, width=20).grid(row=4, column=3, sticky=tk.W, padx=6)
        self.resetbase_text_var.trace_add("write", lambda *_: self._refresh_dism_controls())

        analyze_result = ttk.LabelFrame(self.root, text="Analyze 结构化结果")
        analyze_result.pack(fill=tk.X, padx=10, pady=6)
        fields = [
            ("Windows 资源管理器报告的组件存储大小", "explorer_reported_size"),
            ("组件存储的实际大小", "actual_size"),
            ("已与 Windows 共享", "shared_with_windows"),
            ("备份和已禁用的功能", "backups_and_disabled_features"),
            ("缓存和临时数据", "cache_and_temp_data"),
            ("上次清理日期", "last_cleanup_date"),
            ("可回收的程序包数", "reclaimable_packages"),
            ("推荐使用组件存储清理", "cleanup_recommended_bool"),
        ]
        for idx, (label_text, key) in enumerate(fields):
            row = idx // 2
            col = (idx % 2) * 2
            ttk.Label(analyze_result, text=label_text + "：").grid(row=row, column=col, sticky=tk.W, padx=6, pady=3)
            ttk.Label(analyze_result, textvariable=self.dism_summary_vars[key]).grid(row=row, column=col + 1, sticky=tk.W, padx=6, pady=3)

        ttk.Checkbutton(
            self.root,
            text="显示 Analyze 原始输出",
            variable=self.show_raw_analyze_var,
            command=self._toggle_raw_analyze_output,
        ).pack(anchor=tk.W, padx=14)

        self.raw_output_frame = ttk.LabelFrame(self.root, text="Analyze 原始输出")
        self.raw_output_text = tk.Text(self.raw_output_frame, height=8)
        self.raw_output_text.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        summary_frame = ttk.LabelFrame(self.root, text="Target 汇总")
        summary_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=6)
        columns = ("target", "preview", "deleted", "skipped")
        self.summary_tree = ttk.Treeview(summary_frame, columns=columns, show="headings", height=6)
        self.summary_tree.heading("target", text="目标")
        self.summary_tree.heading("preview", text="预览")
        self.summary_tree.heading("deleted", text="已删")
        self.summary_tree.heading("skipped", text="跳过原因")
        self.summary_tree.column("target", width=120)
        self.summary_tree.column("preview", width=240)
        self.summary_tree.column("deleted", width=220)
        self.summary_tree.column("skipped", width=480)
        self.summary_tree.pack(fill=tk.X, padx=6, pady=6)

        top_frame = ttk.LabelFrame(self.root, text="Top 文件/目录列表")
        top_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
        top_cols = ("size", "target", "reason", "path")
        self.top_tree = ttk.Treeview(top_frame, columns=top_cols, show="headings")
        for col_name, title, width in [("size", "大小", 120), ("target", "目标", 100), ("reason", "原因", 180), ("path", "路径", 620)]:
            self.top_tree.heading(col_name, text=title)
            self.top_tree.column(col_name, width=width)
        top_scroll = ttk.Scrollbar(top_frame, orient=tk.VERTICAL, command=self.top_tree.yview)
        self.top_tree.configure(yscrollcommand=top_scroll.set)
        self.top_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0), pady=6)
        top_scroll.pack(side=tk.LEFT, fill=tk.Y, pady=6)

        log_frame = ttk.LabelFrame(self.root, text="日志窗口")
        log_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=6)
        self.log_text = tk.Text(log_frame, height=8)
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0), pady=6)
        log_scroll.pack(side=tk.LEFT, fill=tk.Y, pady=6)

    def _toggle_raw_analyze_output(self) -> None:
        if self.show_raw_analyze_var.get():
            self.raw_output_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=6)
        else:
            self.raw_output_frame.pack_forget()

    def _append_log(self, message: str) -> None:
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

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
        threading.Thread(target=self._run_cli, args=(["top_dirs"], False), daemon=True).start()

    def _copy_selected_top_path(self) -> None:
        selected = self.top_dirs_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先在大目录表格中选择一行。")
            return
        values = self.top_dirs_tree.item(selected[0], "values")
        if len(values) < 3:
            return
        path = values[2]
        self.root.clipboard_clear()
        self.root.clipboard_append(path)
        messagebox.showinfo("已复制", f"路径已复制：\n{path}")

    def _run_cli(self, targets: list[str], clean: bool) -> None:
        try:
            older_days = max(0, int(self.older_days_var.get().strip()))
            top_n = max(1, int(self.top_var.get().strip()))
            dir_depth = max(0, int(self.dir_depth_var.get().strip()))
            top_dirs = max(1, int(self.top_dirs_var.get().strip()))
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
                "--json",
                str(json_path),
            ]
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
                return

            try:
                report = json.loads(json_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                self.root.after(0, lambda: self._append_log(f"读取/解析 JSON 失败: {exc}"))
                return
            self.root.after(0, lambda: self._render_report(report))

    def _render_report(self, report: dict) -> None:
        for item in self.summary_tree.get_children():
            self.summary_tree.delete(item)
        for item in self.top_tree.get_children():
            self.top_tree.delete(item)
        for item in self.top_dirs_tree.get_children():
            self.top_dirs_tree.delete(item)

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
                self.top_dirs_tree.insert(
                    "",
                    tk.END,
                    values=(top_item.get("size_human", ""), top_item.get("file_count", ""), top_item.get("path", "")),
                )

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
