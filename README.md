# clearc（Windows 清理工具，CLI + Tkinter GUI）

clearc 是一个偏安全的清理/扫描工具，支持：
- 常见清理目标（temp/recycle/wer/dumps/do_cache/update_cache/browser_cache/pip_cache/npm_cache/thumbnail_cache/recent/prefetch/cbs_logs/huggingface_cache/codex_cache/poetry_cache）；
- **深度清理：WinSxS 组件存储（DISM）**（GUI 独立区域）；
- **仅扫描：大目录占用 Top（top_dirs）**，只统计不删除；
- **磁盘空间统计**：报告清理前后盘符可用空间与真实释放量（dry-run 与 clean 均输出）。

> 版本：`1.4.0`（GUI 界面全面优化：统一主题配色、底部状态栏、悬浮提示 Tooltip、危险操作高亮与二次确认；CLI 提示词完善）。
>
> 历史：`1.3.0` 新增目标、磁盘统计、回收站兜底安全修复。

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
  - targets 多选（含新增 pip_cache/npm_cache/thumbnail_cache/recent/prefetch/cbs_logs/huggingface_cache/codex_cache/poetry_cache）、`dry-run/clean` 按钮；
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

### GUI 交互优化（v1.4.0）
- **统一主题配色**：语义色分层（主操作=蓝、危险=红、警告=橙、成功=绿），告别默认灰白界面；
- **底部状态栏**：实时显示「就绪 / 任务执行中 / 扫描完成 / 扫描失败」，颜色随状态变化；
- **悬浮提示（Tooltip）**：鼠标悬停任意按钮/危险选项，即可看到该操作的作用与风险说明；
- **危险操作高亮**：清理（clean）、永久删除、ResetBase 等高风险按钮使用红色样式，并在执行前二次确认；
- **失败与空状态引导**：错误弹窗会给出具体解决方式（如“请以管理员身份运行”），不再只报错不指引。

## 安全修复说明
- 已删除会遮蔽真实 `send2trash` 包的 `src/send2trash.py` 兜底模块（其实现为**静默永久删除**）。
- 现改为：优先使用 `send2trash` 包（回收站）；未安装时回退到 Windows Shell API
  （`SHFileOperationW` + `FOF_ALLOWUNDO`）同样进回收站，**绝不静默永久删除**。
- 新增 `--version` 参数。

## CLI 提示词（v1.4.0）
- `--help` 末尾附“安全说明”总结（默认 dry-run / 回收站可恢复 / 系统级需管理员 / top_dirs 只读）；
- 错误信息统一为中文并给出解决方式（如“请修正 --targets 参数”“请以管理员身份重新运行”）；
- 报告输出增加“模式 / 删除方式 / 安全提示”，dry-run 结尾提醒“确认无误后加 --clean --yes 执行”。

## 管理员运行方式
- 命令行：请在“以管理员身份运行”的终端中执行。
- GUI：可在界面中点击“以管理员重新启动 GUI”（触发 UAC runas）。
- GUI 的 WinSxS 深度清理页中：Analyze 非管理员可执行；Clean/ResetBase 需要管理员权限。

> 系统级目标（`dumps/do_cache/update_cache/prefetch/cbs_logs`）在 `--clean` 模式下必须管理员；非管理员仅允许 dry-run。

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


## 打包为 Windows `.exe`（PyInstaller）
> 说明：PyInstaller 不能在 Linux/macOS 上直接产出可运行的 Windows `.exe`，请在 Windows 环境执行以下步骤。

### 一键打包（推荐）
```bat
scripts\build_windows_exe.bat
```

### 手动打包命令
```bat
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean packaging\clearc-gui.spec
```

产物路径：`dist\clearc.exe`

## 下载 exe（无需 Python）
你可以通过以下两种方式获取 `clearc.exe`：

1. **Actions Artifacts（每次 push main / 手动触发）**
   - 打开仓库 **Actions** 页面；
   - 进入 `Build Windows EXE` 工作流对应的运行记录；
   - 在 **Artifacts** 中下载 `clearc-windows-exe`，解压后得到 `clearc.exe`。

2. **Releases（打 tag 或手动选择发布时）**
   - 打开仓库 **Releases** 页面；
   - 下载对应版本的 `clearc.exe` 资源文件。

### Windows SmartScreen 提示
首次运行时，Windows 可能提示“未知发布者”，可按以下步骤继续：
- 点击“更多信息”；
- 再点击“仍要运行”。

### 管理员权限提示
涉及深度清理（如 WinSxS / DISM Clean/ResetBase）时，请右键 `clearc.exe` 并选择“**以管理员身份运行**”。


### exe 内部 CLI 模式
打包后的可执行程序支持内部 CLI 模式：

```bat
dist\clearc.exe --_cli --dry-run --targets temp,recycle --drive C:
```

该参数主要供 GUI 内部调用，普通用户也可手动使用；在 onefile 模式下可避免 exe 自调用时再次进入 GUI。

说明：`packaging/run_clearc_gui.py` 作为 exe 入口，不再直接把 `gui.py` 当脚本执行，
而是使用“GUI/CLI 双模式分流”：
- 默认无特殊参数时，执行 `runpy.run_module("clearc.gui", run_name="__main__")` 启动 GUI；
- 传入 `--_cli` 时，执行 `runpy.run_module("clearc", run_name="__main__")` 启动 CLI（等价 `python -m clearc`）。

这样可确保：
- `clearc.gui` 内部相对导入在打包后仍有父包上下文，避免
  `attempted relative import with no known parent package`；
- GUI 在 exe 环境下点击扫描/清理按钮时，会内部调用 `clearc.exe --_cli <args>` 执行 CLI，
  不会再弹出新的 GUI 窗口。

该构建配置已满足：
- `--onefile`：单文件可执行程序；
- `--windowed`：无命令行窗口；
- 图标：若仓库根目录存在 `your_icon.ico`，自动写入图标；否则忽略；
- `uac_admin=True`：启动时由 UAC 提示管理员权限，满足需要管理员权限的场景；
- 打包后可在无 Python 环境的 Windows 机器上运行（依赖随 exe 一并封装）。

注意：GUI 内“以管理员重新启动 GUI”在源码模式与 PyInstaller 打包模式均可用。

提示：涉及系统级深度清理（尤其 DISM Clean/ResetBase）时，请在管理员权限下执行。

## 测试
```bash
python -m unittest tests/test_help.py tests/test_dism_parse.py tests/test_top_dirs.py
```
