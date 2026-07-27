#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图漾 Percipio 结构光(.114, 实测型号 FM815-IX-E1) 取数 demo。

跑 camport4 自编的 SimpleView_CaptureDump(无头采集, 不依赖 GUI/OpenGL):
每帧落盘 depth(16bit PNG, mm) + color(JPG, 原分辨率) + 点云(ASCII PCD, 米, 带 rgb)。
点云: 先 TYMapRGBImageToDepthCoordinate 把彩色贴到深度分辨率, 再 TYMapDepthImageToPoint3d。

设备经 GigE Vision 广播发现(ListDevices 已确认枚举到 .114)。Camport4 是 V4 API(TYApi.h),
不是 VcameraSDK(已删)、也不是老的 Camport3。

用法:
  python3 sensors/structured_light/percipio_demo.py                 # 默认 .114, 6 帧 -> data/fm815_114
  python3 sensors/structured_light/percipio_demo.py -n 10 --out data/fm815_114
  python3 sensors/structured_light/percipio_demo.py -ip 192.168.1.114 --no-align   # 点云不带色

依赖: LD_LIBRARY_PATH 含 camport4/lib/linux/lib_x64(本脚本已自动注入)。
"""
import argparse
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
CAP = os.path.join(_ROOT, "third_party", "camport4", "sample", "build", "bin",
                   "SimpleView_CaptureDump")
LIBDIR = os.path.join(_ROOT, "third_party", "camport4", "lib", "linux", "lib_x64")


def main():
    ap = argparse.ArgumentParser(description="图漾 Percipio FM815-IX-E1(.114) 取数 demo")
    ap.add_argument("--ip", default="192.168.1.114", help="设备 IP(默认 192.168.1.114)")
    ap.add_argument("-n", type=int, default=6, help="采集帧数(默认 6)")
    ap.add_argument("--out", default=None, help="输出目录, 默认 data/fm815_114")
    ap.add_argument("--no-align", action="store_true", help="不做 color->depth 对齐, 点云不带色")
    args = ap.parse_args()

    out = args.out or os.path.join("data", "fm815_114")
    os.makedirs(out, exist_ok=True)

    if not os.path.exists(CAP):
        sys.exit(f"找不到 SimpleView_CaptureDump: {CAP}\n"
                 "请编译: cd third_party/camport4/sample/build && cmake .. "
                 "-DTYCam_DIR=$PWD/../../.. -DARCH=x64 -DBUILD_SAMPLE_V2=OFF "
                 "-DBUILD_SAMPLE_GENICAM_SFNC=OFF && make SimpleView_CaptureDump -j")

    env = dict(os.environ,
               LD_LIBRARY_PATH=LIBDIR + ":" + os.environ.get("LD_LIBRARY_PATH", ""))
    cmd = [CAP, "-ip", args.ip, "-n", str(args.n), "-outdir", os.path.abspath(out)]
    if args.no_align:
        cmd.append("-noalign")

    print(f"SimpleView_CaptureDump\nip: {args.ip}  frames: {args.n}  -> {out}\n")
    try:
        subprocess.run(cmd, env=env, timeout=args.n * 8 + 15)
    except subprocess.TimeoutExpired:
        print(f"\n(超时截断)")
    except KeyboardInterrupt:
        print("\n中断")

    # 汇总
    files = sorted(os.listdir(out))
    depth = [f for f in files if f.startswith("depth_")]
    color = [f for f in files if f.startswith("color_")]
    pcd = [f for f in files if f.startswith("points_")]
    print(f"done: depth {len(depth)} / color {len(color)} / pcd {len(pcd)} 帧 -> {out}")


if __name__ == "__main__":
    main()
