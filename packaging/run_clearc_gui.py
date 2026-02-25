# -*- coding: utf-8 -*-
"""PyInstaller GUI 入口：根据参数分流到 GUI 或 CLI 模式。"""

import runpy
import sys

# 打包成 onefile 后，GUI 内部通过 subprocess 自调用 sys.executable。
# 如果这里不做模式分流，自调用会再次进入 GUI，导致“点击一次按钮弹出一个新窗口”的无限弹窗问题。
# 约定：传入 --_cli 时执行 CLI 入口；默认执行 GUI 入口。
if "--_cli" in sys.argv:
    sys.argv.remove("--_cli")
    runpy.run_module("clearc", run_name="__main__")
else:
    # 必须用 run_module("clearc.gui", run_name="__main__") 启动，而不是把 gui.py 当脚本执行。
    # 原因：gui.py 内部使用了相对导入（如 from .xxx import ...），只有在“包模块上下文”下
    # 才有已知父包（clearc）；若按脚本入口运行会触发
    # “attempted relative import with no known parent package”。
    runpy.run_module("clearc.gui", run_name="__main__")
