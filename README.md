# clearc（Windows 多目标清理助手 V3）

一个 **Python 清理助手（V3）**，主打“先预览、再确认、默认安全删除”：
- 默认 `--dry-run`，只预览不删除；
- 仅在 `--clean --yes` 时执行删除；
- 默认通过回收站删除（`send2trash`）；
- 只有显式 `--permanent-delete` 才允许永久删除。

## 可选清理目标（`--targets`）
`--targets` 支持逗号分隔，默认：`temp,recycle,wer`。

支持值：
- `temp`：用户/系统临时目录（包含后缀和老化规则）
- `recycle`：回收站目录（`$Recycle.Bin`）
- `wer`：Windows Error Reporting 相关目录
- `dumps`：崩溃转储目录（如 `Minidump/CrashDumps`）
- `do_cache`：Delivery Optimization 缓存
- `update_cache`：Windows Update 下载缓存
- `browser_cache`：常见浏览器缓存目录（Chrome/Edge/Firefox）

### 系统级目标权限要求
以下目标属于系统级：`do_cache` / `update_cache` / `dumps`。
- 非管理员：允许 `--dry-run` 预览；
- 非管理员 + `--clean`：程序会拒绝执行并提示“以管理员身份运行”。

## 安全与风险提示
- 默认模式使用回收站（`send2trash`），可回收；
- `--permanent-delete` 会直接删除文件，**高风险且不可恢复**；
- 始终建议先执行一次 `--dry-run`，确认 Top 文件列表和目标汇总。

## 统计与报告（V3）
报告包含：
- 总览：可释放空间、删除空间、跳过原因计数；
- 按 target 汇总：每个目标的 preview/deleted/skipped（`permission_denied` / `in_use` / `not_found`）；
- Top N 候选文件（含 target 归属和原因）；
- 可选 JSON 输出（`--json`）。

## 项目结构

```text
.
├── README.md
├── requirements.txt
├── src/
│   └── clearc/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── dism_component_store.py
│       ├── gui.py
│       └── scanner.py
└── tests/
    ├── test_dism_parse.py
    └── test_help.py
```

## 安装与运行

### 1) 安装依赖

```bash
set PYTHONUTF8=1
python -m pip install -r requirements.txt
```

> Windows（GBK 控制台）建议先设置 `PYTHONUTF8=1`，避免 pip 输出与文件读写编码问题。

### 2) 默认预览（dry-run，默认目标 temp/recycle/wer）

```bash
PYTHONPATH=src python -m clearc
```

### 3) 指定多个目标预览

```bash
PYTHONPATH=src python -m clearc --targets temp,recycle,wer,browser_cache --top 30
```

### 4) 清理（必须带确认）

```bash
PYTHONPATH=src python -m clearc --clean --yes --targets temp,recycle,wer
```

### 5) 系统级目标清理（需管理员）

```bash
PYTHONPATH=src python -m clearc --clean --yes --targets dumps,do_cache,update_cache
```

### 6) 永久删除（危险）

```bash
PYTHONPATH=src python -m clearc --clean --yes --permanent-delete --targets temp
```

### 7) 输出 JSON 报告

```bash
PYTHONPATH=src python -m clearc --targets temp,recycle,wer --json reports/clearc-report.json
```

### 8) 启动 GUI（Tkinter）

```bash
set PYTHONUTF8=1
PYTHONPATH=src python -m clearc.gui
```

GUI 功能包含：
- 扫描/清理按钮（清理会二次确认）；
- `targets` 多选；
- `older-than-days` / `top` 输入；
- 日志窗口；
- Top 文件列表与 target 汇总表。

### 深度清理：WinSxS 组件存储（DISM）

GUI 已内置独立区域“组件存储（WinSxS / DISM）”，支持：
- `Analyze`：`DISM /Online /Cleanup-Image /AnalyzeComponentStore`
- `Clean`：`DISM /Online /Cleanup-Image /StartComponentCleanup`
- `ResetBase`：`DISM /Online /Cleanup-Image /StartComponentCleanup /ResetBase`

风险说明：
- `Clean` 相对安全，主要清理可回收组件；
- `ResetBase` **不可逆**，执行后会失去卸载现有更新的能力（高风险）。

管理员权限说明：
- 非管理员下可执行 `Analyze`；
- `Clean/ResetBase` 会置灰并提示“请以管理员身份运行”；
- 可在 GUI 中点击“以管理员重新启动 GUI”触发 UAC 提权。

`Analyze` 完成后，GUI 会结构化展示以下字段（并保留原始日志输出）：
- Windows 资源管理器报告的组件存储大小
- 组件存储的实际大小
- 已与 Windows 共享 / 备份和已禁用的功能 / 缓存和临时数据
- 上次清理日期
- 可回收的程序包数
- 推荐使用组件存储清理（是/否）

GUI 内部通过 `subprocess` 调用 `python -m clearc ... --json <临时文件>`，再解析 JSON 渲染结果。

### 9) GUI 打包（PyInstaller）

```bash
set PYTHONUTF8=1
python -m pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name clearc-gui src/clearc/gui.py
```

输出文件位于 `dist/clearc-gui.exe`（Windows）。

## 命令行参数
- `--drive`：目标盘符，默认 `C:`
- `--top`：Top 列表数量，默认 `20`
- `--json`：可选，输出 JSON 报告文件路径
- `--targets`：清理目标列表（逗号分隔）
- `--dry-run`：仅预览候选文件（默认开启）
- `--clean`：执行清理动作（需配合 `--yes`）
- `--yes`：确认删除；未提供时 `--clean` 直接退出
- `--older-than-days`：仅对 `temp` 目标生效，默认 `7`
- `--permanent-delete`：显式开启永久删除（默认关闭）

## 最简单自检

```bash
PYTHONPATH=src python -m clearc --help
python -m unittest tests/test_help.py
```
