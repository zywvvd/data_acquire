#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""海康 SDK 抓图 demo(薄壳: 委托 hik_driver.HikSensor)。相机 .107 / 鱼眼 .99 共用。

登录一次, 连抓 N 张设备端编码 JPEG(NET_DVR_CaptureJPEGPicture, 走 HCNetSDK/libhcnetsdk.so)。
本脚本只做 CLI → spec 映射, 采集逻辑全部在 HikSensor / HikGrabber 里(record.py 多路协同也复用同一驱动)。

依赖:
  - anaconda python3
  - LD_LIBRARY_PATH 指向仓库内 SDK 的 lib:
      export LD_LIBRARY_PATH=$PWD/third_party/EN-HCNetSDKV6.1.9.4_build20220412_linux64/lib

运行(两台同一脚本, 不同 IP; 默认存 data/ 下):
  python3 sensors/camera/grab_demo.py --ip 192.168.1.107 -n 6               # 相机 -> data/camera_107/
  python3 sensors/camera/grab_demo.py --ip 192.168.1.99 -n 6 --out data/fisheye_99
"""
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _HERE)
sys.path.insert(0, _ROOT)

from sensors.camera.hik_driver import HikSensor   # noqa: E402
from sensors.base import capture_once             # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="海康 SDK 连拍 demo(相机/鱼眼共用)")
    ap.add_argument("--ip", required=True, help="相机 IP, 如 192.168.1.107 / .99")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--user", default="admin")
    ap.add_argument("--pwd", default="b@light2.")
    ap.add_argument("--channel", type=int, default=1, help="设备逻辑通道(IP 相机一般从 1 起)")
    ap.add_argument("-n", type=int, default=5, help="抓取张数")
    ap.add_argument("--out", default=None, help="输出目录, 默认 data/camera_<ip 末段>")
    args = ap.parse_args()

    out = args.out or os.path.join("data", "camera_" + args.ip.split(".")[-1])
    os.makedirs(out, exist_ok=True)

    spec = {"ip": args.ip, "port": args.port, "user": args.user,
            "password": args.pwd, "channel": args.channel}
    s = HikSensor("camera", spec)
    s.out_dir = out
    print(f"连接 {args.ip}:{args.port}  user={args.user}  channel={args.channel}  -> {out}")
    n = capture_once(s, max_frames=args.n)
    print(f"done: {n} 张 JPEG -> {out}")


if __name__ == "__main__":
    main()
