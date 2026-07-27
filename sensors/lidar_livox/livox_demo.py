#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Livox(.100, 实测型号 HAP) 取数 demo(薄壳: 委托 livox_driver.LivoxSensor)。

跑 Livox-SDK2 的 livox_lidar_pcd_saver(GCC11 直接过; HAP/Mid-360 必须用 SDK2, 不是老 v1)。
SDK **主动查询式**发现雷达、置 Normal(故静态嗅探看不到流量属正常), 按每 50000 点切一帧写 ASCII PCD。
限时自停: 到 --seconds 子进程自己退出。

配置随型号不同(--model 选模板):
  - HAP(.100, 机壳 "HAP (TX)") → hap_host200.json(cmd 56000 / point 57000 / imu 58000 / log 59000)。
  - Mid-360 → mid360_host200.json(端口 56100–56500)。
host_net_info.host_ip 会被驱动渲染成采集机 IP(默认 192.168.1.200)。

用法:
  python3 sensors/lidar_livox/livox_demo.py                       # 默认 HAP -> data/livox_hap
  python3 sensors/lidar_livox/livox_demo.py --seconds 20
  python3 sensors/lidar_livox/livox_demo.py --model "Mid-360" --out data/livox_mid360

依赖: LD_LIBRARY_PATH 含 third_party/Livox-SDK2/build/sdk_core(驱动已自动注入)。
"""
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)

from sensors.lidar_livox.livox_driver import LivoxSensor   # noqa: E402
from sensors.base import capture_once                      # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Livox(HAP/.100) 取数 demo(按帧存 PCD)")
    ap.add_argument("--model", default="Livox HAP", help="Livox HAP 或 Mid-360(选对应配置模板)")
    ap.add_argument("--seconds", type=float, default=15.0)
    ap.add_argument("--out", default=None, help="PCD 输出目录, 默认 data/livox_hap")
    args = ap.parse_args()

    out = args.out or os.path.join("data", "livox_hap")
    os.makedirs(out, exist_ok=True)

    spec = {"model": args.model, "duration": args.seconds, "host_ip": "192.168.1.200"}
    s = LivoxSensor("lidar_livox", spec)
    s.out_dir = out
    print(f"LivoxSensor  model={args.model}  (采 {args.seconds}s) -> {out}\n")
    n = capture_once(s)
    print(f"done: {n} 帧 PCD -> {out}")


if __name__ == "__main__":
    main()
