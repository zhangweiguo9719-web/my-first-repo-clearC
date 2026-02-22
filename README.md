# clearc（Windows 清理 C 盘小助手）

一个 **Python MVP**，当前版本只做 `scan-only`：
- 扫描并统计常见临时目录占用；
- 输出总占用、文件总数、目录明细；
- 输出按体积排序的 Top 文件列表。

> ⚠️ 安全说明（V1）
> - 本版本**不做任何删除操作**。
> - 后续若实现删除功能，必须支持 `--dry-run`。
> - 后续若实现删除功能，默认应使用回收站删除（`send2trash`）而非直接永久删除。

## 扫描目录范围
默认扫描这些常见临时目录：
- `%TEMP%`
- `%TMP%`
- `C:\Windows\Temp`（可用 `--drive` 切换盘符）
- `%USERPROFILE%\AppData\Local\Temp`

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

### 2) 运行扫描

```bash
PYTHONPATH=src python -m clearc
```

可选参数：

```bash
PYTHONPATH=src python -m clearc --drive C: --top 20
PYTHONPATH=src python -m clearc --json reports/scan-report.json
```

## 命令行参数
- `--drive`：目标盘符，默认 `C:`
- `--top`：Top 列表数量，默认 `20`
- `--json`：可选，输出 JSON 报告文件路径

## 最简单自检

```bash
PYTHONPATH=src python -m clearc --help
python -m unittest tests/test_help.py
```
