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
from .scanner import DEFAULT_TARGETS, SUPPORTED_TARGETS


class ClearCGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("clearc GUI (Windows 优先)")
        self.root.geometry("980x680")

        self.drive_var = tk.StringVar(value="C:")
        self.older_days_var = tk.StringVar(value="7")
        self.top_var = tk.StringVar(value="20")
        self.clean_var = tk.BooleanVar(value=False)
        self.permanent_var = tk.BooleanVar(value=False)
        self.is_admin_var = tk.StringVar(value="是" if is_admin() else "否")
        self.resetbase_ack_var = tk.BooleanVar(value=False)
        self.resetbase_text_var = tk.StringVar(value="")
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

        ttk.Label(controls, text="Drive:").grid(row=0, column=0, sticky=tk.W, padx=6, pady=6)
        ttk.Entry(controls, textvariable=self.drive_var, width=8).grid(row=0, column=1, sticky=tk.W, padx=6)

        ttk.Label(controls, text="Older-than-days:").grid(row=0, column=2, sticky=tk.W, padx=6)
        ttk.Entry(controls, textvariable=self.older_days_var, width=8).grid(row=0, column=3, sticky=tk.W, padx=6)

        ttk.Label(controls, text="Top N:").grid(row=0, column=4, sticky=tk.W, padx=6)
        ttk.Entry(controls, textvariable=self.top_var, width=8).grid(row=0, column=5, sticky=tk.W, padx=6)

        ttk.Checkbutton(controls, text="Clean mode (--clean --yes)", variable=self.clean_var).grid(
            row=0, column=6, sticky=tk.W, padx=6
        )
        ttk.Checkbutton(controls, text="Permanent delete", variable=self.permanent_var).grid(
            row=0, column=7, sticky=tk.W, padx=6
        )

        target_frame = ttk.LabelFrame(self.root, text="Targets（多选）")
        target_frame.pack(fill=tk.X, padx=10, pady=8)

        col = 0
        row = 0
        for target, var in self.target_vars.items():
            ttk.Checkbutton(target_frame, text=target, variable=var).grid(
                row=row, column=col, sticky=tk.W, padx=10, pady=4
            )
            col += 1
            if col >= 4:
                row += 1
                col = 0

        button_frame = ttk.Frame(self.root)
        button_frame.pack(fill=tk.X, padx=10, pady=6)

        ttk.Button(button_frame, text="扫描（dry-run）", command=lambda: self._run_scan(clean=False)).pack(
            side=tk.LEFT, padx=6
        )
        ttk.Button(button_frame, text="清理（clean）", command=lambda: self._run_scan(clean=True)).pack(
            side=tk.LEFT, padx=6
        )

        dism_frame = ttk.LabelFrame(self.root, text="组件存储（WinSxS / DISM）")
        dism_frame.pack(fill=tk.X, padx=10, pady=8)

        ttk.Label(dism_frame, text="当前权限（管理员）:").grid(row=0, column=0, sticky=tk.W, padx=6, pady=4)
        ttk.Label(dism_frame, textvariable=self.is_admin_var).grid(row=0, column=1, sticky=tk.W, padx=6, pady=4)

        self.admin_tip_label = ttk.Label(dism_frame, text="")
        self.admin_tip_label.grid(row=0, column=2, sticky=tk.W, padx=6, pady=4)

        self.relaunch_button = ttk.Button(dism_frame, text="以管理员重新启动 GUI", command=self._relaunch_gui_as_admin)
        self.relaunch_button.grid(row=0, column=3, sticky=tk.W, padx=6, pady=4)

        self.analyze_button = ttk.Button(dism_frame, text="Analyze（分析）", command=self._run_analyze)
        self.analyze_button.grid(row=1, column=0, sticky=tk.W, padx=6, pady=4)

        self.clean_button = ttk.Button(dism_frame, text="Clean（StartComponentCleanup）", command=self._run_clean)
        self.clean_button.grid(row=1, column=1, sticky=tk.W, padx=6, pady=4)

        self.resetbase_button = ttk.Button(dism_frame, text="ResetBase（不可逆）", command=self._run_resetbase)
        self.resetbase_button.grid(row=1, column=2, sticky=tk.W, padx=6, pady=4)

        ttk.Label(
            dism_frame,
            text="风险说明：Clean 通常相对安全；ResetBase 不可逆，会失去卸载现有更新能力。",
            foreground="#b35a00",
        ).grid(row=2, column=0, columnspan=4, sticky=tk.W, padx=6, pady=(6, 2))

        ttk.Checkbutton(
            dism_frame,
            text="我已理解 ResetBase 不可逆风险",
            variable=self.resetbase_ack_var,
            command=self._refresh_dism_controls,
        ).grid(row=3, column=0, columnspan=2, sticky=tk.W, padx=6, pady=4)

        ttk.Label(dism_frame, text="请输入 RESETBASE：").grid(row=3, column=2, sticky=tk.E, padx=6, pady=4)
        resetbase_entry = ttk.Entry(dism_frame, textvariable=self.resetbase_text_var, width=20)
        resetbase_entry.grid(row=3, column=3, sticky=tk.W, padx=6, pady=4)
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
            ttk.Label(analyze_result, textvariable=self.dism_summary_vars[key]).grid(
                row=row, column=col + 1, sticky=tk.W, padx=6, pady=3
            )

        summary_frame = ttk.LabelFrame(self.root, text="Target 汇总")
        summary_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=6)

        columns = ("target", "preview", "deleted", "skipped")
        self.summary_tree = ttk.Treeview(summary_frame, columns=columns, show="headings", height=6)
        self.summary_tree.heading("target", text="target")
        self.summary_tree.heading("preview", text="preview")
        self.summary_tree.heading("deleted", text="deleted")
        self.summary_tree.heading("skipped", text="skipped")
        self.summary_tree.column("target", width=120)
        self.summary_tree.column("preview", width=220)
        self.summary_tree.column("deleted", width=220)
        self.summary_tree.column("skipped", width=320)
        self.summary_tree.pack(fill=tk.X, padx=6, pady=6)

        top_frame = ttk.LabelFrame(self.root, text="Top 文件列表")
        top_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)

        top_cols = ("size", "target", "reason", "path")
        self.top_tree = ttk.Treeview(top_frame, columns=top_cols, show="headings")
        for col_name, title, width in [
            ("size", "size", 120),
            ("target", "target", 100),
            ("reason", "reason", 180),
            ("path", "path", 520),
        ]:
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
            self.admin_tip_label.configure(text="请以管理员身份运行")
            self.relaunch_button.configure(state=tk.NORMAL)

    def _set_dism_running(self, running: bool) -> None:
        # 执行 DISM 时禁用按钮，避免并发操作导致日志混乱或误触发高风险命令。
        state = tk.DISABLED if running else tk.NORMAL
        self.analyze_button.configure(state=state)
        self.clean_button.configure(state=state)
        self.resetbase_button.configure(state=state)
        self.relaunch_button.configure(state=tk.DISABLED if running else self.relaunch_button.cget("state"))
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
                if code != 0:
                    messagebox.showerror("DISM 执行失败", f"{action_name} 执行失败，退出码: {code}")
                self._set_dism_running(False)

            self.root.after(0, _finish)

        threading.Thread(target=_worker, daemon=True).start()

    def _render_analyze_result(self, output_text: str) -> None:
        parsed = parse_analyze_output(output_text)
        for key, var in self.dism_summary_vars.items():
            value = parsed.get(key, "").strip() or "-"
            var.set(value)

        if all(parsed.get(k, "").strip() == "" for k in parsed if k not in {"raw_output", "cleanup_recommended_bool"}):
            self._append_log("[DISM] Analyze 结构化解析失败，以下保留原始输出：")
            self._append_log(parsed.get("raw_output", "(无输出)"))

    def _selected_targets(self) -> list[str]:
        return [name for name, var in self.target_vars.items() if var.get()]

    def _run_scan(self, clean: bool) -> None:
        targets = self._selected_targets()
        if not targets:
            messagebox.showwarning("clearc GUI", "请至少选择一个 target")
            return

        if clean and not messagebox.askyesno("确认", "将执行清理操作（--clean --yes），是否继续？"):
            return

        self._append_log("=" * 72)
        self._append_log(f"开始执行: {'clean' if clean else 'dry-run'}")
        threading.Thread(target=self._run_cli, args=(targets, clean), daemon=True).start()

    def _run_cli(self, targets: list[str], clean: bool) -> None:
        try:
            older_days = max(0, int(self.older_days_var.get().strip()))
            top_n = max(1, int(self.top_var.get().strip()))
        except ValueError:
            self.root.after(0, lambda: messagebox.showerror("参数错误", "older-than-days 与 top 必须是整数"))
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
                "--json",
                str(json_path),
            ]

            if clean:
                cmd.extend(["--clean", "--yes"])
            else:
                cmd.append("--dry-run")

            if self.permanent_var.get():
                cmd.append("--permanent-delete")

            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"

            try:
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
            except OSError as exc:
                self.root.after(0, lambda: self._append_log(f"命令执行失败: {exc}"))
                return

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

        summary = report.get("summary", {})
        for target_item in summary.get("targets", []):
            skipped = target_item.get("skipped", {})
            self.summary_tree.insert(
                "",
                tk.END,
                values=(
                    target_item.get("target", ""),
                    f"{target_item.get('preview_files', 0)} / {target_item.get('preview_size_human', '-')}",
                    f"{target_item.get('deleted_files', 0)} / {target_item.get('deleted_size_human', '-')}",
                    (
                        f"perm={skipped.get('permission_denied', 0)}, "
                        f"in_use={skipped.get('in_use', 0)}, "
                        f"not_found={skipped.get('not_found', 0)}"
                    ),
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
    app = ClearCGUI(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
