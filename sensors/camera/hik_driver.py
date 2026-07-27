"""海康摄像头/鱼眼 → Sensor 接口适配。复用同目录 sdk_grabber.HikGrabber。

依赖与 grab_via_sdk.py 一致:
  export LD_LIBRARY_PATH=$PWD/third_party/EN-HCNetSDKV6.1.9.4_build20220412_linux64/lib
  用 anaconda python3
"""
import os
import sys
import time

# 让本模块无论从哪里 import 都能找到 sdk_grabber 和仓库根( sensors.base )
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _HERE)
sys.path.insert(0, _ROOT)

from sdk_grabber import HikGrabber          # noqa: E402
from sensors.base import Sensor, Sample      # noqa: E402


class HikSensor(Sensor):
    """单台海康相机: 登录一次, 每次 grab() 抓一张设备端编码 JPEG。

    rig.yaml 字段 → HikGrabber 参数映射: ip→host, password→pwd, user/channel 同名。
    """

    def __init__(self, name, spec):
        super().__init__(name, spec)
        self._g: HikGrabber = None
        self._frame = 0

    def _kwargs(self):
        s = self.spec
        kw = {"host": s.get("ip"), "user": s.get("user", "admin"),
              "pwd": s.get("password"), "channel": s.get("channel", 1)}
        return {k: v for k, v in kw.items() if v is not None}

    def connect(self):
        self._g = HikGrabber(**self._kwargs())

    def start(self):
        pass  # HikGrabber 构造时已完成登录, 无额外启动步骤

    def grab(self) -> Sample:
        self._frame += 1
        path = os.path.join(self.out_dir, f"{self.name}_{self._frame:06d}.jpg")
        latency = self._g.capture(path)        # SDK 直接写文件, 返回耗时(ms)
        ts = time.monotonic()
        return Sample(
            sensor=self.name, timestamp=ts, payload=path,
            meta={"frame": self._frame, "latency_ms": latency,
                  "bytes": os.path.getsize(path) if os.path.exists(path) else 0,
                  "model": self.spec.get("model")},
        )

    def stop(self):
        if self._g:
            self._g.close()
            self._g = None
