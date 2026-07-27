#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""速腾 RoboSense(.202 / .205) 在线取数 demo —— 跑 rs_driver_pcdsaver 存 PCD。

rs_driver 取自 third_party/rslidar_sdk-v1.5.20/src/rs_driver, 已单独编译(免 ROS;
对老代码加 -DCMAKE_CXX_FLAGS="-include memory" 适配 GCC11)。每台雷达各跑一次
rs_driver_pcdsaver, 按帧存 PCD 到本地。

前置(否则收不到点云):
  - .202 / .205 网页已把 Destination IP 指 192.168.1.200(实测)。各自端口:
    .202→msop 6692 / difop 7782,   .205→msop 6695 / difop 7785。
  - 型号必须对: .202/.205 是速腾 96 通道半固态(MSOP 头 55aa055a + V2 头部)。实测 RSFAIRY/RSAIRY
    两个 decoder 都能 0 报错解出 ~8.3 万点/帧真 3D 点云, 差别仅在垂直角表(RSFAIRY z 可达 ~26m / RSAIRY z ~6m)。
    bolight_alg 生产 config 用的是 **RSAIRY**, 故默认 RSAIRY; 若硬件实为 RS-Fairy 改 --type RSFAIRY。
    换别的速腾雷达务必重核 --type(RS16/RS32/RSBP/.../RSFAIRY/RSAIRY/...)。

用法:
  python3 sensors/lidar_robosense/robosense_demo.py                          # 默认 .202, 10s
  python3 sensors/lidar_robosense/robosense_demo.py --ip 192.168.1.205 --msop 6695 --difop 7785
  python3 sensors/lidar_robosense/robosense_demo.py --type RSHELIOS --seconds 20
"""
import argparse
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
PCDSAVER = os.path.join(_ROOT, "third_party", "rslidar_sdk-v1.5.20", "src", "rs_driver",
                        "build_rs", "tool", "rs_driver_pcdsaver")


def main():
    ap = argparse.ArgumentParser(description="速腾 RoboSense 在线取数 demo(按帧存 PCD)")
    ap.add_argument("--ip", default="192.168.1.202", help="雷达 IP(决定输出目录名)")
    ap.add_argument("--msop", type=int, default=6692)
    ap.add_argument("--difop", type=int, default=7782)
    ap.add_argument("--host", default="192.168.1.200", help="采集机 IP")
    ap.add_argument("--type", default="RSAIRY",
                    help="雷达型号; 默认 RSAIRY(.202/.205 生产配置即此型). RS-Fairy 则用 RSFAIRY")
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--out", default=None, help="PCD 输出目录, 默认 pcd_robosense/<ip>")
    args = ap.parse_args()

    out = args.out or os.path.join("pcd_robosense", args.ip.replace(".", "_"))
    os.makedirs(out, exist_ok=True)

    if not os.path.exists(PCDSAVER):
        sys.exit(f"找不到 rs_driver_pcdsaver: {PCDSAVER}\n"
                 "请编译: cd third_party/rslidar_sdk-v1.5.20/src/rs_driver && "
                 "mkdir build_rs && cd build_rs && cmake -DCOMPILE_DEMOS=ON "
                 "-DCOMPILE_TOOL_PCDSAVER=ON -DCMAKE_CXX_FLAGS='-include memory' .. && make -j")

    cmd = [PCDSAVER, "-type", args.type, "-msop", str(args.msop),
           "-difop", str(args.difop), "-host", args.host]
    print(f"rs_driver_pcdsaver: type={args.type} msop={args.msop} difop={args.difop} host={args.host}")
    print(f"PCD -> {out}   (采 {args.seconds}s; 收到点云会在此目录生成 .pcd)\n")
    try:
        subprocess.run(cmd, cwd=out, timeout=args.seconds)
    except subprocess.TimeoutExpired:
        print(f"\n(到 {args.seconds}s 截断)")
    except KeyboardInterrupt:
        print("\n中断")


if __name__ == "__main__":
    main()
