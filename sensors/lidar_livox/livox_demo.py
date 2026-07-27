#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Livox(.100, 实测型号 **HAP**) 取数 demo —— 跑 Livox-SDK2 的 livox_lidar_pcd_saver(存 PCD)。

third_party/Livox-SDK2 已编译(较新, GCC11 直接过; HAP/Mid-360 必须用 SDK2, 不是老 v1)。
pcd_saver 加载配置(host_net_info.host_ip = 采集机), 经**主动查询**发现雷达、置为 Normal 模式,
按帧(frame_cnt)把 CartesianHigh 点云落 ASCII PCD(xyz 米 + intensity)。

注意: Livox-SDK2 是**主动查询式发现**(SDK 先广播查询、雷达应答), 与禾赛/速腾的被动持续推流不同,
所以**静态嗅探看不到流量是正常的**, 必须直接跑 SDK 才会出数据。

配置随型号不同:
  - .100 是 **HAP**(机壳标注 "HAP (TX)") → 默认 hap_host200.json(cmd 56000/point 57000/imu 58000/log 59000)。
  - 若改接 Mid-360 → 用 mid360_host200.json(端口 56100–56500)。
host_net_info.host_ip 必须是采集机 IP(已设 192.168.1.200)。

用法:
  python3 sensors/lidar_livox/livox_demo.py                       # 默认 HAP, 存 PCD 到 data/livox_hap
  python3 sensors/lidar_livox/livox_demo.py --seconds 20
  python3 sensors/lidar_livox/livox_demo.py --cfg mid360_host200.json --out data/livox_mid360

依赖: LD_LIBRARY_PATH 含 third_party/Livox-SDK2/build/sdk_core(本脚本已自动注入)。
"""
import argparse
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
SAVER = os.path.join(_ROOT, "third_party", "Livox-SDK2", "build", "samples",
                     "livox_lidar_pcd_saver", "livox_lidar_pcd_saver")
DEFAULT_CFG = os.path.join(_HERE, "hap_host200.json")
LIBDIR = os.path.join(_ROOT, "third_party", "Livox-SDK2", "build", "sdk_core")


def main():
    ap = argparse.ArgumentParser(description="Livox(HAP/.100) 取数 demo(按帧存 PCD)")
    ap.add_argument("--cfg", default=DEFAULT_CFG, help="配置 json(HAP 用 hap_host200.json)")
    ap.add_argument("--seconds", type=float, default=15.0)
    ap.add_argument("--out", default=None, help="PCD 输出目录, 默认 data/livox_hap")
    args = ap.parse_args()

    out = args.out or os.path.join("data", "livox_hap")
    os.makedirs(out, exist_ok=True)

    if not os.path.exists(SAVER):
        sys.exit(f"找不到 livox_lidar_pcd_saver: {SAVER}\n"
                 "请编译: cd third_party/Livox-SDK2/build && cmake .. && make livox_lidar_pcd_saver -j")
    if not os.path.exists(args.cfg):
        sys.exit(f"找不到配置: {args.cfg}")

    env = dict(os.environ,
               LD_LIBRARY_PATH=LIBDIR + ":" + os.environ.get("LD_LIBRARY_PATH", ""),
               PCD_OUT=os.path.abspath(out),
               LIVOX_RUN_SECS=str(int(args.seconds)))
    print(f"livox_lidar_pcd_saver\nconfig: {args.cfg}\nPCD -> {out}   (采 {args.seconds}s)\n")
    try:
        subprocess.run([SAVER, args.cfg], env=env, timeout=args.seconds + 5)
    except subprocess.TimeoutExpired:
        print(f"\n(到 {args.seconds}s 截断)")
    except KeyboardInterrupt:
        print("\n中断")


if __name__ == "__main__":
    main()
