#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""禾赛 QT128 @ 192.168.1.201 在线取数 demo。

跑已编译的 HesaiLidar_SDK_2.0/sample 二进制(免 pcap / PCL / ROS), 在线 UDP 解析
点云并逐帧打印统计(frame / points / packet / 时间戳)。看到 "frame:.. points:.."
即证明 .201 已把点云推到采集机。

前置(否则收不到帧):
  在 .201 网页 Pandar Console(http://192.168.1.201)把点云目的 IP 设为采集机
  192.168.1.11, UDP 数据口 2368。

用法:
  python3 sensors/lidar_hesai/hesai_demo.py                  # 默认 10s
  python3 sensors/lidar_hesai/hesai_demo.py --seconds 30
  python3 sensors/lidar_hesai/hesai_demo.py --cfg <自定义.ini>

存盘(每帧 PCD)需另编译 tool/pcl_tool(依赖 PCL), 见 README。
"""
import argparse
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))  # data_acquire/
SAMPLE = os.path.join(_ROOT, "third_party", "HesaiLidar_SDK_2.0", "build", "sample")
DEFAULT_CFG = os.path.join(_HERE, "qt128_online_201.ini")


def main():
    ap = argparse.ArgumentParser(description="禾赛 QT128 在线取数 demo")
    ap.add_argument("--cfg", default=DEFAULT_CFG, help="sample 配置 ini")
    ap.add_argument("--seconds", type=float, default=10.0,
                    help="采集时长(s); 在线流不会自停, 到时强杀")
    args = ap.parse_args()

    if not os.path.exists(SAMPLE):
        sys.exit(f"找不到 sample 二进制: {SAMPLE}\n"
                 "请先编译: cd third_party/HesaiLidar_SDK_2.0 && mkdir build && cd build && cmake .. && make -j")
    if not os.path.exists(args.cfg):
        sys.exit(f"找不到配置: {args.cfg}")

    print(f"sample : {SAMPLE}")
    print(f"config : {args.cfg}")
    print(f"采集 {args.seconds}s —— 注意 sample 启动时会尝试 sudo 改 rmem_max(无 sudo 会报一行错, 不影响)\n")
    try:
        subprocess.run([SAMPLE, args.cfg], timeout=args.seconds)
    except subprocess.TimeoutExpired:
        print(f"\n(到 {args.seconds}s 截断 —— 在线流正常不会自停)")
    except KeyboardInterrupt:
        print("\n中断")


if __name__ == "__main__":
    main()
