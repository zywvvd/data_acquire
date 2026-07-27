#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深度图查看器: uint16(mm) PNG → 按量程归一化 + colormap 上色。

图漾结构光落的 depth_*.png 是 uint16、单位 mm。普通图片查看器按 8bit 线性显示会几乎全黑:
有效深度 560-4160mm 只占 uint16 低位一小段 + 无效像素=0=黑 + 查看器不按量程归一化。
本工具按 [vmin, vmax] mm 归一化到 0-255 再上 jet/turbo 色表, 无效(0)留黑, 才能看清深度。
(同帧 points_*.pcd 点云有效即证明深度数据本身是好的, 只是 PNG 看着黑。)

用法:
  python3 tools/view_depth.py data/fm815_114/depth_0003.png            # 默认存 *_vis.png
  python3 tools/view_depth.py data/fm815_114/ --cmap turbo --max 3500   # 整个目录
  python3 tools/view_depth.py data/fm815_114/depth_0003.png --show      # 弹窗(需 GUI)
"""
import argparse
import glob
import os
import sys

import cv2
import numpy as np

_CMAPS = {"jet": cv2.COLORMAP_JET, "turbo": cv2.COLORMAP_TURBO,
          "viridis": cv2.COLORMAP_VIRIDIS, "hot": cv2.COLORMAP_HOT}


def render(depth_png, vmin=400.0, vmax=4500.0, cmap="jet"):
    """uint16(mm) PNG → 8bit BGR 彩色图; 无效像素(0)留黑。"""
    d = cv2.imread(depth_png, cv2.IMREAD_UNCHANGED)
    if d is None:
        return None
    if d.dtype != np.uint16:
        d = d.astype(np.uint16)
    out = np.zeros(d.shape, dtype=np.uint8)
    mask = d > 0
    if mask.any():
        v = d[mask].astype(np.float32)
        v = np.clip((v - vmin) / max(vmax - vmin, 1e-6), 0.0, 1.0)
        out[mask] = (v * 255.0).astype(np.uint8)
    colored = cv2.applyColorMap(out, _CMAPS.get(cmap, cv2.COLORMAP_JET))
    colored[~mask] = 0
    return colored


def main():
    ap = argparse.ArgumentParser(description="uint16 mm 深度图 → 归一化 + colormap 上色")
    ap.add_argument("input", help="depth_*.png 单图或目录")
    ap.add_argument("--min", dest="vmin", type=float, default=400.0, help="量程下限(mm), 默认 400")
    ap.add_argument("--max", dest="vmax", type=float, default=4500.0, help="量程上限(mm), 默认 4500")
    ap.add_argument("--cmap", default="jet", choices=list(_CMAPS), help="色表")
    ap.add_argument("--suffix", default="_vis", help="保存后缀(默认 *_vis.png)")
    ap.add_argument("--save", dest="save", action="store_true", default=True, help="保存彩色图(默认开)")
    ap.add_argument("--no-save", dest="save", action="store_false", help="不保存")
    ap.add_argument("--show", action="store_true", help="弹窗显示(需 GUI)")
    args = ap.parse_args()

    if os.path.isdir(args.input):
        files = sorted(glob.glob(os.path.join(args.input, "*.png")))
    else:
        files = [args.input]
    if not files:
        sys.exit(f"找不到 PNG: {args.input}")

    for f in files:
        img = render(f, args.vmin, args.vmax, args.cmap)
        if img is None:
            print(f"  跳过(读不到): {f}")
            continue
        if args.save:
            base, _ = os.path.splitext(f)
            out = f"{base}{args.suffix}.png"
            cv2.imwrite(out, img)
            print(f"  {os.path.basename(f)} -> {os.path.basename(out)}  (vmin={args.vmin} vmax={args.vmax} mm)")
        if args.show:
            cv2.imshow(os.path.basename(f), img)
            cv2.waitKey(0)
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
