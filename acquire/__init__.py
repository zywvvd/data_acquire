"""acquire 包: 配置驱动的采集编排层。

对外收敛 registry 的派发接口, 方便 `from acquire import resolve_driver`。
协同采集入口仍是命令行 `python3 acquire/record.py`(避免在包初始化时触发 record 的重 import)。
"""
from acquire.registry import IMPLEMENTED, TABLE, resolve_driver  # noqa: F401
