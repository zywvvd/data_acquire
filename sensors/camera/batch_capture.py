#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量采集标定图：登录一次连拍 N 张，每批一个时间戳文件夹，每张图用时间戳命名。

用法示例::

    export LD_LIBRARY_PATH=<sdk>/lib
    python3 batch_capture.py -n 20 -i 1.0          # 连拍 20 张，间隔 1s
    python3 batch_capture.py -n 10 --interactive   # 每张前按回车（手动摆标定板）
    python3 batch_capture.py -n 30 -i 2 -o data    # 间隔 2s，输出到 data/

每批输出形如::

    captures/20260717_164200/
        20260717_164200_123456.jpg
        20260717_164201_045678.jpg
        ...
"""
import argparse
import os
import time
from datetime import datetime

import os, sys as _sys
_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdk_grabber import HikGrabber


def ts_folder():
    """批次文件夹名：精确到秒。"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ts_image():
    """单张图片名：精确到微秒，保证同批次内唯一且按字典序可排序。"""
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def main():
    ap = argparse.ArgumentParser(description="批量采集海康相机标定图")
    ap.add_argument("-n", "--count", type=int, default=10, help="采集张数（默认 10）")
    ap.add_argument("-i", "--interval", type=float, default=1.0,
                    help="每张间隔秒数（默认 1.0）；--interactive 模式下忽略")
    ap.add_argument("--interactive", action="store_true",
                    help="交互模式：每张前按回车继续，适合手动摆标定板")
    ap.add_argument("-o", "--out-dir", default="captures", help="根输出目录（默认 captures）")
    args = ap.parse_args()

    if args.count <= 0:
        ap.error("--count 必须为正整数")

    if not os.environ.get("LD_LIBRARY_PATH"):
        print("警告：未设置 LD_LIBRARY_PATH，SDK 依赖库可能加载失败")

    batch_dir = os.path.join(args.out_dir, ts_folder())
    os.makedirs(batch_dir, exist_ok=True)

    mode = "交互（按回车拍下一张）" if args.interactive else f"自动间隔 {args.interval}s"
    print(f"准备采集 {args.count} 张  ->  {batch_dir}")
    print(f"模式：{mode}")

    ok, fail = 0, 0
    t_start = time.monotonic()
    with HikGrabber() as g:
        print("登录成功，开始抓图 ...")
        for k in range(1, args.count + 1):
            if args.interactive:
                input(f"[{k}/{args.count}] 摆好标定板后按回车抓图 ...")
            path = os.path.join(batch_dir, ts_image() + ".jpg")
            try:
                dt = g.capture(path)
                size = os.path.getsize(path)
                print(f"  [{k}/{args.count}] OK   {size:>7} bytes   {dt:>5.0f} ms"
                      f"   -> {os.path.basename(path)}")
                ok += 1
            except RuntimeError as e:
                print(f"  [{k}/{args.count}] FAIL  {e}")
                fail += 1
            if not args.interactive and k < args.count:
                time.sleep(args.interval)

    dt_total = time.monotonic() - t_start
    print(f"\n完成：成功 {ok} / 失败 {fail}   耗时 {dt_total:.1f}s")
    print(f"批次目录：{batch_dir}")


if __name__ == "__main__":
    main()
