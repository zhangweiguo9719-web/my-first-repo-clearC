# clearc（Windows 清理工具，CLI + Tkinter GUI）

clearc 是一个偏安全的清理/扫描工具，支持：
- 常见清理目标（temp/recycle/wer/dumps/do_cache/update_cache/browser_cache）；
- **深度清理：WinSxS 组件存储（DISM）**（GUI 独立区域）；
- **仅扫描：大目录占用 Top（top_dirs）**，只统计不删除。

## 快速开始

### 安装
```bash
set PYTHONUTF8=1
python -m pip install -r requirements.txt
```

### CLI 启动（默认 dry-run）
```bash
PYTHONPATH=src python -m clearc
```

### GUI 启动
```bash
set PYTHONUTF8=1
PYTHONPATH=src python -m clearc.gui
```

## GUI 分页结构（可访问长内容）
GUI 已重构为 `ttk.Notebook` 四个分页，避免单页过长导致底部区域不可达：

- **Tab1：快速清理**
  - targets 多选、`dry-run/clean` 按钮；
  - Target 汇总表格；
  - Top 文件列表。
- **Tab2：大目录占用**
  - `top_dirs` 专用参数（`--dir-depth` / `--top-dirs` / `--include-dirs` / `--exclude-dirs` / `--min-dir-size-mb`）；
  - 扫描大目录 + 下钻扫描（仅扫描，不删除）；
  - 结果表格（大小可排序，支持复制/打开路径、导出 JSON 报告）。
- **Tab3：深度清理**
  - WinSxS / DISM：Analyze / Clean / ResetBase；
  - 风险提示与 ResetBase 双重确认；
  - Analyze 结构化结果与“原始输出开关”。
- **Tab4：日志**
  - 集中展示 stdout/stderr/DISM 日志；
  - 支持一键清空、一键复制。

说明：各分页主表格/文本框均提供垂直滚动条、鼠标滚轮滚动，且支持窗口缩放。

## 管理员运行方式
- 命令行：请在“以管理员身份运行”的终端中执行。
- GUI：可在界面中点击“以管理员重新启动 GUI”（触发 UAC runas）。
- GUI 的 WinSxS 深度清理页中：Analyze 非管理员可执行；Clean/ResetBase 需要管理员权限。

> 系统级目标（`dumps/do_cache/update_cache`）在 `--clean` 模式下必须管理员；非管理员仅允许 dry-run。

## 深度清理：WinSxS（DISM）
GUI 中提供独立模块“深度清理：组件存储（WinSxS / DISM）”：
- **Analyze**：`DISM /Online /Cleanup-Image /AnalyzeComponentStore`（非管理员也可执行）；
- **Clean**：`DISM /Online /Cleanup-Image /StartComponentCleanup`（管理员）；
- **ResetBase**：`DISM /Online /Cleanup-Image /StartComponentCleanup /ResetBase`（管理员 + 双重确认）。

风险提示：
- Clean：相对安全，但耗时，执行期间不要关机；
- ResetBase：**不可逆**，会失去卸载当前已安装更新的能力。

Analyze 执行后会结构化展示关键字段，并保留可展开的原始输出。

## 仅扫描：大目录占用 Top（top_dirs）
- `top_dirs` 是专门用于定位空间占用来源的 target，**仅允许 dry-run，不允许 clean**；
- 默认扫描目录：
  - `C:\Users\<user>\Downloads`
  - `C:\Users\<user>\Desktop`
  - `C:\Users\<user>\Documents`
  - `C:\Users\<user>\AppData\Local`
  - `C:\ProgramData`
  - `C:\Windows\Temp`
- 支持参数：
  - `--dir-depth`（默认 2）：递归深度限制；
  - `--top-dirs`（默认 20）：返回目录数量；
  - `--include-dirs`：追加扫描目录（逗号分隔）；
  - `--exclude-dirs`：排除目录（逗号分隔）；
  - `--min-dir-size-mb`（默认 0）：过滤过小目录。

示例（全量 Top）：
```bash
PYTHONPATH=src python -m clearc --targets top_dirs --dry-run --dir-depth 2 --top-dirs 20 --min-dir-size-mb 100
```

示例（下钻某个目录）：
```bash
PYTHONPATH=src python -m clearc --targets top_dirs --dry-run --include-dirs "C:\Users\you\Downloads\big-project" --dir-depth 2 --top-dirs 20
```

### 下钻扫描说明与风险提示
- GUI 在 Tab2 支持“下钻扫描”：先选中一行目录，再点击“下钻扫描”，只分析该目录内部 Top 子目录；
- 结果中的“提示（note）”会识别常见缓存目录（如浏览器缓存、pip/conda 缓存等），并给出“低风险可重建”或“建议先确认”的中文建议；
- 对来源不明的大目录会明确标记“来源不明，请先打开确认，避免误删”；
- **重要：top_dirs 永远只做扫描与提示，不会自动删除目录。请先打开目录确认后再手动处理。**

## 系统目录“跳过原因”中文提示
GUI 汇总中对 `permission_denied / in_use / not_found` 使用中文解释显示。
其中 `do_cache` 的 `not_found` 会额外提示：
“未检测到 Delivery Optimization 缓存目录（系统未生成或功能关闭），无需清理。”

## 测试
```bash
python -m unittest tests/test_help.py tests/test_dism_parse.py tests/test_top_dirs.py
```
