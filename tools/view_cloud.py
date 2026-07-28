#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多帧点云查看器: 逐帧浏览目录里的 ASCII PCD, ←/→ 翻帧、空格播放、q 退出。

依赖 open3d(顺滑, 大点云无压力)。open3d 在 boeye 环境里, 故用该环境跑:
  /home/vvd/anaconda3/envs/boeye/bin/python tools/view_cloud.py <input>

兼容本仓四种 PCD 字段(按 FIELDS 行自适应):
  · 图漾 Percipio : FIELDS x y z r g b       (rgb 0-255) -> 按原色着色
  · Livox HAP     : FIELDS x y z intensity   (float)
  · 禾赛 QT128    : FIELDS x y z intensity ring
  · 速腾 RSAIRY   : FIELDS x y z intensity [ring]
有 rgb 按原色; 否则按 intensity 归一化上 jet 色。

用法:
  python3 tools/view_cloud.py data/fm815_114/                 # 图漾(按帧翻)
  python3 tools/view_cloud.py data/hesai_qt128/               # 禾赛(按 intensity 上色)
  python3 tools/view_cloud.py data/livox_hap/00001.pcd        # 单帧
  python3 tools/view_cloud.py data/robosense_202/ --fps 5
"""
import argparse
import glob
import os
import sys

import numpy as np


def load_pcd(path):
    """解析 ASCII PCD -> (xyz Nx3 float64, fi dict(field->col), arr NxK float64)。"""
    fields, npts = [], 0
    with open(path) as f:
        line = f.readline()
        data_lines = None
        while line:
            if line.startswith("FIELDS"):
                fields = line.split()[1:]
            elif line.startswith("POINTS"):
                npts = int(line.split()[1])
            elif line.startswith("DATA"):
                data_lines = f.read().splitlines()
                break
            line = f.readline()
    rows = [r.split() for r in (data_lines or []) if r.strip()]
    if not rows:
        return None
    arr = np.array(rows, dtype=np.float64)
    fi = {name: i for i, name in enumerate(fields)} if len(fields) == arr.shape[1] else {}
    return arr, fi


def _jet(t):
    """t∈[0,1] -> jet RGB (N,3)。"""
    four = 4.0 * t
    r = np.clip(np.minimum(four - 1.5, -four + 4.5), 0, 1)
    g = np.clip(np.minimum(four - 0.5, -four + 3.5), 0, 1)
    b = np.clip(np.minimum(four + 0.5, -four + 2.5), 0, 1)
    return np.stack([r, g, b], axis=1)


def xyz_rgb(arr, fi):
    """从 (arr, fi) 取 xyz(Nx3) 与 color(Nx3 in [0,1])。"""
    if fi and {"x", "y", "z"}.issubset(fi):
        xyz = arr[:, [fi["x"], fi["y"], fi["z"]]]
    else:
        xyz = arr[:, :3]
    if fi and {"r", "g", "b"}.issubset(fi):
        rgb = arr[:, [fi["r"], fi["g"], fi["b"]]] / 255.0
    elif fi and "intensity" in fi and arr.shape[0]:
        inten = arr[:, fi["intensity"]]
        lo, hi = inten.min(), inten.max()
        if hi <= lo:
            hi = lo + 1e-6
        rgb = _jet(np.clip((inten - lo) / (hi - lo), 0, 1))
    else:
        rgb = np.tile([0.3, 0.6, 1.0], (arr.shape[0], 1))   # 默认浅蓝
    return xyz, rgb


def run_viewer(files, fps=3):
    """open3d 翻帧查看器。"""
    import open3d as o3d
    import time
    idx = [0]; auto = [False]; last = [time.monotonic()]
    geom = o3d.geometry.PointCloud()

    def show(i):
        res = load_pcd(files[i])
        if not res:
            return
        arr, fi = res
        xyz, rgb = xyz_rgb(arr, fi)
        geom.points = o3d.utility.Vector3dVector(np.ascontiguousarray(xyz))
        geom.colors = o3d.utility.Vector3dVector(np.ascontiguousarray(rgb))
        print(f"  [{i + 1}/{len(files)}] {os.path.basename(files[i])}  {len(xyz)} 点")

    vis = o3d.visualization.VisualizerWithKeyCallback()
    vis.create_window("view_cloud   ←/→ 翻帧  空格 播放/暂停  Q 退出", 1024, 768)
    vis.add_geometry(geom)

    # 渲染参数: 暗背景突出点云 + 放大点, 大点云才看得清。
    opt = vis.get_render_option()
    opt.background_color = np.array([0.12, 0.12, 0.12])
    opt.point_size = 3.0

    def refresh(v):
        v.update_geometry(geom); v.poll_events(); v.update_renderer()

    def nxt(v):
        idx[0] = min(idx[0] + 1, len(files) - 1); show(idx[0]); refresh(v); return False
    def prv(v):
        idx[0] = max(idx[0] - 1, 0); show(idx[0]); refresh(v); return False
    def tog(v):
        auto[0] = not auto[0]; last[0] = time.monotonic(); return False

    vis.register_key_callback(262, nxt)    # →
    vis.register_key_callback(263, prv)    # ←
    vis.register_key_callback(32, tog)     # space

    def anim(v):
        if auto[0] and time.monotonic() - last[0] > 1.0 / max(fps, 1):
            idx[0] = (idx[0] + 1) % len(files); show(idx[0]); refresh(v); last[0] = time.monotonic()
        return False
    vis.register_animation_callback(anim)

    show(0)
    vis.reset_view_point(True)    # 首帧自适应视角(把点云摆正、占满窗口)
    vis.run()


def main():
    ap = argparse.ArgumentParser(description="多帧 ASCII PCD 点云查看器(open3d)")
    ap.add_argument("input", help="单个 .pcd 或目录")
    ap.add_argument("--fps", type=float, default=3.0, help="自动播放帧率")
    args = ap.parse_args()

    if os.path.isdir(args.input):
        files = sorted(glob.glob(os.path.join(args.input, "*.pcd")))
    else:
        files = [args.input]
    if not files:
        sys.exit(f"找不到 PCD: {args.input}")

    try:
        import open3d  # noqa: F401
    except ImportError:
        sys.exit("未安装 open3d。open3d 在 boeye 环境, 请用该 python 运行:\n"
                 "  /home/vvd/anaconda3/envs/boeye/bin/python tools/view_cloud.py <input>")

    print(f"共 {len(files)} 帧")
    run_viewer(files, args.fps)


if __name__ == "__main__":
    main()
