"""海康摄像头/鱼眼 → Sensor 接口适配。复用同目录 sdk_grabber.HikGrabber。

依赖与 grab_via_sdk.py 一致:
  export LD_LIBRARY_PATH=$PWD/third_party/EN-HCNetSDKV6.1.9.4_build20220412_linux64/lib
  用 anaconda python3

底层 SDK 调用流程(Python 如何封装):
  本驱动是 Sensor 进程内 poll 型(唯一非子进程设备)。Python 进程即 SDK 宿主: HikGrabber 构造时
  ctypes 加载 libhcnetsdk.so → SetSDKInitCfg/Init/SetConnectTime/Login_V40(登录一次拿设备句柄 uid);
  每次 grab() 调 NET_DVR_CaptureJPEGPicture(uid, ch, JPEGPARA, path) —— 相机固件在【设备端】编一张
  JPEG 直写到 out_dir, 返回耗时(ms); stop() 调 Logout/Cleanup。详细编号流程见 sdk_grabber.py 顶部。
  特点: 同步、进程内、原始画质(设备端编码, 与 LiDAR 的主机端解码相反)。
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
