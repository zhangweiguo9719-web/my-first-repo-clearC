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

        self.target_vars: dict[str, tk.BooleanVar] = {
            target: tk.BooleanVar(value=target in DEFAULT_TARGETS) for target in sorted(SUPPORTED_TARGETS)
        }

        self._build_layout()

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
