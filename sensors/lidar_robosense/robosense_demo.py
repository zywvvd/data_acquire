#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""速腾 RoboSense(.202 / .205) 取数 demo(薄壳: 委托 robosense_driver.RobosenseSensor)。

跑 rs_driver 的 rs_driver_pcdsaver(免 ROS; rslidar_sdk 顶层 node 需 ROS 编不过, 只编 src/rs_driver;
老代码加 -DCMAKE_CXX_FLAGS="-include memory" 适配 GCC11)。每台各跑一次, 按帧把 PCD 写到 out。

前置(否则收不到点云):
  - .202 / .205 网页已把 Destination IP 指 192.168.1.200(实测)。各自端口:
    .202→msop 6692 / difop 7782,   .205→msop 6695 / difop 7785。
  - 型号必须对: .202/.205 实测 RSAIRY(bolight_alg 生产配置亦此); 若硬件实为 RS-Fairy 改 --type RSFAIRY
    (同包不同垂直角表, z 可达 ~26m vs RSAIRY ~6m)。换别的速腾雷达务必重核 --type。

用法:
  python3 sensors/lidar_robosense/robosense_demo.py                          # 默认 .202, 10s
  python3 sensors/lidar_robosense/robosense_demo.py --ip 192.168.1.205 --msop 6695 --difop 7785
  python3 sensors/lidar_robosense/robosense_demo.py --type RSFAIRY --seconds 20
"""
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)

from sensors.lidar_robosense.robosense_driver import RobosenseSensor   # noqa: E402
from sensors.base import capture_once                                 # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="速腾 RoboSense 取数 demo(按帧存 PCD)")
    ap.add_argument("--ip", default="192.168.1.202", help="雷达 IP(决定输出目录名)")
    ap.add_argument("--msop", type=int, default=6692, help="UDP 主数据流端口")
    ap.add_argument("--difop", type=int, default=7782, help="UDP 设备控制/状态端口")
    ap.add_argument("--host", default="192.168.1.200", help="采集机 IP")
    ap.add_argument("--type", default="RSAIRY",
                    help="雷达型号; 默认 RSAIRY(.202/.205 生产配置即此). RS-Fairy 则用 RSFAIRY")
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--out", default=None, help="PCD 输出目录, 默认 data/robosense_<ip 末段>")
    args = ap.parse_args()

    out = args.out or os.path.join("data", "robosense_" + args.ip.split(".")[-1])
    os.makedirs(out, exist_ok=True)

    spec = {"ip": args.ip, "msop_port": args.msop, "difop_port": args.difop,
            "host_ip": args.host, "model": args.type, "rs_type": args.type,
            "duration": args.seconds}
    s = RobosenseSensor("lidar_robosense", spec)
    s.out_dir = out
    print(f"RobosenseSensor  type={args.type} msop={args.msop} difop={args.difop} host={args.host}")
    print(f"  PCD -> {out}   (采 {args.seconds}s)\n")
    n = capture_once(s)
    print(f"done: {n} 帧 PCD -> {out}")


if __name__ == "__main__":
    main()
