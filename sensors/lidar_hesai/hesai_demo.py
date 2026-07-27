#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""禾赛 QT128 @ 192.168.1.201 在线取数 demo(薄壳: 委托 hesai_driver.HesaiSensor)。

跑已编译的 HesaiLidar_SDK_2.0/sample_pcd(免 pcap / PCL / ROS): 在线 UDP 解析 + 回调直写
ASCII PCD(规避 Ubuntu22.04 VTK/PCL/libtiff 链接冲突)。在线流不会自停, 到 --seconds 由基类 terminate。

前置(否则收不到帧):
  在 .201 网页 Pandar Console(http://192.168.1.201)把点云目的 IP 设为采集机
  192.168.1.200, UDP 数据口 2364(实测该机 Lidar Destination Port=2364, 非默认 2368)。

用法:
  python3 sensors/lidar_hesai/hesai_demo.py                  # 默认 .201, 10s -> data/hesai_qt128
  python3 sensors/lidar_hesai/hesai_demo.py --seconds 30
  python3 sensors/lidar_hesai/hesai_demo.py --ip 192.168.1.201 --data-port 2364
"""
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)

from sensors.lidar_hesai.hesai_driver import HesaiSensor   # noqa: E402
from sensors.base import capture_once                      # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="禾赛 QT128 在线取数 demo")
    ap.add_argument("--ip", default="192.168.1.201", help="雷达 IP")
    ap.add_argument("--data-port", dest="data_port", type=int, default=2364,
                    help="UDP 数据口(实测 2364, 非默认 2368)")
    ap.add_argument("--ptc-port", dest="ptc_port", type=int, default=9347, help="PTC 端口(角度修正文件)")
    ap.add_argument("--seconds", type=float, default=10.0, help="采集时长(s); 在线流不会自停, 到时强杀")
    ap.add_argument("--out", default=None, help="输出目录, 默认 data/hesai_qt128")
    args = ap.parse_args()

    out = args.out or os.path.join("data", "hesai_qt128")
    os.makedirs(out, exist_ok=True)

    spec = {"ip": args.ip, "data_port": args.data_port, "ptc_port": args.ptc_port,
            "duration": args.seconds, "model": "Hesai QT128", "host_ip": "192.168.1.200"}
    s = HesaiSensor("lidar_hesai", spec)
    s.out_dir = out
    print(f"HesaiSensor  {args.ip}:{args.data_port}  (采 {args.seconds}s) -> {out}")
    print("  注意 sample_pcd 启动时会尝试 sudo 改 rmem_max(无 sudo 报一行错, 不影响)\n")
    n = capture_once(s)
    print(f"done: {n} 帧 PCD -> {out}")


if __name__ == "__main__":
    main()
