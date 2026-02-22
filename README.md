# clearc（Windows 清理 C 盘小助手）

一个 **Python MVP+V2** 工具，主打“安全清理”：
- 默认 `--dry-run`，只预览不删除；
- 仅在 `--clean --yes` 时执行删除；
- 默认优先通过回收站删除（`send2trash`）；
- 仅处理白名单目录与受控规则，避免误删。

## 清理目录白名单
仅扫描/清理以下目录：
- `%TEMP%`
- `%TMP%`
- `C:\Windows\Temp`（可通过 `--drive` 调整盘符）
- `%USERPROFILE%\AppData\Local\Temp`

## 清理规则（V2）
- 仅处理后缀：`.tmp` / `.log` / `.bak` / `.old` / `.temp`
- 且必须满足 `--older-than-days`（默认 7 天）
- 对于“无后缀大文件”（默认 >=100MB）：
  - 仅在 `dry-run` 中展示
  - 默认不删除
- 遇到占用/权限/IO 异常将跳过并统计，不会导致程序崩溃

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
│       └── scanner.py
└── tests/
    └── test_help.py
```

## 安装与运行

### 1) 安装依赖

```bash
python -m pip install -r requirements.txt
```

### 2) 默认预览（dry-run）

```bash
PYTHONPATH=src python -m clearc
PYTHONPATH=src python -m clearc --older-than-days 14 --top 30
```

### 3) 执行清理（必须带确认）

```bash
PYTHONPATH=src python -m clearc --clean --yes
```

### 4) 关闭回收站（危险，直接删除）

```bash
PYTHONPATH=src python -m clearc --clean --yes --no-use-recycle-bin
```

### 5) 输出 JSON 报告

```bash
PYTHONPATH=src python -m clearc --json reports/clearc-report.json
```

## 命令行参数
- `--drive`：目标盘符，默认 `C:`
- `--top`：Top 列表数量，默认 `20`
- `--json`：可选，输出 JSON 报告文件路径
- `--dry-run`：仅预览候选文件（默认开启）
- `--clean`：执行清理动作（需配合 `--yes`）
- `--yes`：确认删除；未提供时 `--clean` 直接退出
- `--older-than-days`：仅处理修改时间早于 N 天文件，默认 `7`
- `--use-recycle-bin / --no-use-recycle-bin`：是否通过回收站删除，默认开启

## 最简单自检

```bash
PYTHONPATH=src python -m clearc --help
python -m unittest tests/test_help.py
```
