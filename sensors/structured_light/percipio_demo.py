#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图漾 Percipio 结构光(.114, 实测型号 FM815-IX-E1) 取数 demo(薄壳: 委托 percipio_driver.PercipioSensor)。

跑 camport4 自编的 SimpleView_CaptureDump(无头, 不依赖 GUI/OpenGL):
每帧落盘 depth(16bit PNG, mm) + color(JPG, 原分辨率) + 点云(ASCII PCD, 米, 带 rgb)。
点云: 先 TYMapRGBImageToDepthCoordinate 把彩色贴到深度分辨率, 再 TYMapDepthImageToPoint3d。
采完 N 帧子进程自停 → 批量型。

设备经 GigE Vision 广播发现(ListDevices 已确认枚举到 .114)。Camport4 是 V4 API(TYApi.h)。

用法:
  python3 sensors/structured_light/percipio_demo.py                 # 默认 .114, 6 帧 -> data/fm815_114
  python3 sensors/structured_light/percipio_demo.py -n 10
  python3 sensors/structured_light/percipio_demo.py --ip 192.168.1.114 --no-align   # 点云不带色

依赖: LD_LIBRARY_PATH 含 camport4/lib/linux/lib_x64(驱动已自动注入)。
"""
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)

from sensors.structured_light.percipio_driver import PercipioSensor   # noqa: E402
from sensors.base import capture_once                                # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="图漾 Percipio FM815-IX-E1(.114) 取数 demo")
    ap.add_argument("--ip", default="192.168.1.114", help="设备 IP(默认 192.168.1.114)")
    ap.add_argument("-n", type=int, default=6, help="采集帧数(默认 6)")
    ap.add_argument("--out", default=None, help="输出目录, 默认 data/fm815_114")
    ap.add_argument("--no-align", dest="no_align", action="store_true", help="不做 color->depth 对齐, 点云不带色")
    ap.add_argument("--ir", action="store_true", help="同开左右 IR(与 depth 同开 -> 灭灯暗帧 max~14, 非真散斑; 真散斑用二进制 -nodepth 单开, 见 README/STRUCTURED_LIGHT.md §8)")
    args = ap.parse_args()

    out = args.out or os.path.join("data", "fm815_114")
    os.makedirs(out, exist_ok=True)

    spec = {"ip": args.ip, "frames": args.n, "no_align": args.no_align, "ir": args.ir,
            "model": "FM815-IX-E1"}
    s = PercipioSensor("structured_light", spec)
    s.out_dir = out
    print(f"PercipioSensor  ip={args.ip}  frames={args.n}  ir={args.ir}  -> {out}\n")
    n = capture_once(s)
    # 汇总产物(按扩展名区分 pcd/ply; ir 仅 --ir 时有)
    files = sorted(os.listdir(out))
    depth = sum(1 for f in files if f.startswith("depth_") and f.endswith(".png") and "_vis" not in f)
    color = sum(1 for f in files if f.startswith("color_"))
    pcd  = sum(1 for f in files if f.startswith("points_") and f.endswith(".pcd"))
    ply  = sum(1 for f in files if f.startswith("points_") and f.endswith(".ply"))
    irl  = sum(1 for f in files if f.startswith("ir_left_"))
    irr  = sum(1 for f in files if f.startswith("ir_right_"))
    extra = f" / ir_left {irl} / ir_right {irr}" if args.ir else ""
    print(f"done: {n} 帧  depth {depth} / color {color} / pcd {pcd} / ply {ply}{extra}  -> {out}")


if __name__ == "__main__":
    main()
