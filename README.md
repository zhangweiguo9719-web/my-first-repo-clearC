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

## 管理员运行方式
- 命令行：请在“以管理员身份运行”的终端中执行。
- GUI：可在界面中点击“以管理员重新启动 GUI”（触发 UAC runas）。

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
- `top_dirs` 是新 target，**仅允许 dry-run，不允许 clean**；
- 默认扫描目录：
  - `C:\Users\<user>\Downloads`
  - `C:\Users\<user>\Desktop`
  - `C:\Users\<user>\Documents`
  - `C:\Users\<user>\AppData\Local`
  - `C:\ProgramData`
  - `C:\Windows\Temp`
- 支持参数：
  - `--dir-depth`（默认 2）：递归深度限制；
  - `--top-dirs`（默认 20）：返回目录数量。

示例：
```bash
PYTHONPATH=src python -m clearc --targets top_dirs --dry-run --dir-depth 2 --top-dirs 20
```

## 系统目录“跳过原因”中文提示
GUI 汇总中对 `permission_denied / in_use / not_found` 使用中文解释显示。
其中 `do_cache` 的 `not_found` 会额外提示：
“未检测到 Delivery Optimization 缓存目录（系统未生成或功能关闭），无需清理。”

## 测试
```bash
python -m unittest tests/test_help.py tests/test_dism_parse.py tests/test_top_dirs.py
```
