"""传感器统一接口与样本类型。

所有 sensors/<kind>/ 下的驱动实现 Sensor,acquire/ 通过本接口无差别采集各路数据,
与具体厂商解耦。加一种新传感器 = 在 sensors/<kind>/ 写一个 Sensor 子类 +
在 acquire/registry.py 登记一行。
"""
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Sample:
    """一帧采集样本。"""
    sensor: str                         # 设备句柄(rig.yaml 里的 name)
    timestamp: float                    # time.monotonic() 秒 —— 同主机内单调时钟
    payload: Any = None                 # 刚落盘文件路径(str) 或内存数据(bytes/ndarray)
    meta: dict = field(default_factory=dict)  # 型号/帧号/分辨率/延迟 等


class Sensor(ABC):
    """配置驱动的采集器基类。registry 按 (kind, model) 实例化具体子类。

    生命周期: connect() → start() → 反复 grab() → stop() → close()
    recorder 在 start 前会注入 out_dir(每台设备一个独立输出目录)。
    """

    def __init__(self, name: str, spec: dict):
        self.name = name
        self.spec = spec                # rig.yaml 里这一台设备的整段配置
        self.out_dir: str = None        # 由 recorder 注入

    @abstractmethod
    def connect(self): ...
    @abstractmethod
    def start(self): ...
    @abstractmethod
    def grab(self) -> Sample: ...
    @abstractmethod
    def stop(self): ...

    def close(self):
        """可选资源释放, 默认等于 stop。"""
        self.stop()

    def __enter__(self):
        self.connect(); self.start(); return self

    def __exit__(self, *exc):
        self.close(); return False
