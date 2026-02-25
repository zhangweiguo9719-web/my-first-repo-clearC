# -*- coding: utf-8 -*-
"""PyInstaller GUI 入口：以模块方式启动 clearc.gui。"""

import runpy

# 必须用 run_module("clearc.gui", run_name="__main__") 启动，而不是把 gui.py 当脚本执行。
# 原因：gui.py 内部使用了相对导入（如 from .xxx import ...），只有在“包模块上下文”下
# 才有已知父包（clearc）；若按脚本入口运行会触发
# “attempted relative import with no known parent package”。
runpy.run_module("clearc.gui", run_name="__main__")
