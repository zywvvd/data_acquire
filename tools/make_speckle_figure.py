#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把"散斑结构光成像流水线"合成一张教学组图:
   左IR散斑 | 右IR散斑 | 深度图(jet) | 彩色RGB | 上色点云(正视图)

讲述: 两只 IR 眼睛看到同一片散斑(左右错开) → SGBM 匹配出深度 → RGB 上色 → 点云。
用法:
  # 先采两组(同位置):
  SimpleView_CaptureDump -ip .114 -n 1 -dmode 1280 -outdir /tmp/set/normal      # depth+color+点云
  SimpleView_CaptureDump -ip .114 -n 1 -nodepth -color=off -laser 100 -ire 120 -outdir /tmp/set/ir  # 左右散斑
  python3 tools/make_speckle_figure.py /tmp/set/ir /tmp/set/normal assets/speckle_pipeline.png
"""
import sys, os, glob
import numpy as np, cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def find(d, pat):
    g = sorted(glob.glob(os.path.join(d, pat)))
    return g[0] if g else None


def render_depth(png):
    d = cv2.imread(png, cv2.IMREAD_UNCHANGED).astype(np.float64)
    mask = d > 0
    out = np.zeros(d.shape, np.uint8)
    v = np.clip((d[mask] - 400) / (4500 - 400), 0, 1)
    out[mask] = (v * 255).astype(np.uint8)
    col = cv2.applyColorMap(out, cv2.COLORMAP_JET)
    col[~mask] = 0
    return cv2.cvtColor(col, cv2.COLOR_BGR2RGB)


def stretch_ir(png):
    m = cv2.imread(png, cv2.IMREAD_UNCHANGED)
    return cv2.normalize(m, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


def cloud_front(ply, max_pts=40000):
    rec = np.dtype([('x', '<f4'), ('y', '<f4'), ('z', '<f4'),
                    ('r', 'u1'), ('g', 'u1'), ('b', 'u1')])
    with open(ply, 'rb') as f:
        hdr = b""
        while True:
            ln = f.readline(); hdr += ln
            if ln.strip() == b"end_header": break
        nv = [int(l.split()[-1]) for l in hdr.split(b"\n") if l.startswith(b"element vertex")][0]
        a = np.frombuffer(f.read(nv * rec.itemsize), dtype=rec)
    rgb = np.stack([a['r'], a['g'], a['b']], 1) / 255.0
    st = max(1, len(a) // max_pts)
    return a['x'][::st], a['y'][::st], rgb[::st]


def main(ir_dir, normal_dir, out):
    left = find(ir_dir, "ir_left_*.png"); right = find(ir_dir, "ir_right_*.png")
    depth = find(normal_dir, "depth_*.png"); color = find(normal_dir, "color_*.jpg")
    ply = find(normal_dir, "points_*.ply")
    miss = [n for n, p in [("left IR", left), ("right IR", right), ("depth", depth),
                            ("color", color), ("ply", ply)] if not p]
    if miss:
        sys.exit(f"缺文件: {miss}  (ir_dir={ir_dir} normal_dir={normal_dir})")

    fig = plt.figure(figsize=(15, 9))
    gs = fig.add_gridspec(2, 3, hspace=0.18, wspace=0.12)
    axL = fig.add_subplot(gs[0, 0]); axR = fig.add_subplot(gs[0, 1])
    axD = fig.add_subplot(gs[0, 2]); axC = fig.add_subplot(gs[1, 0])
    axP = fig.add_subplot(gs[1, 1:])

    axL.imshow(stretch_ir(left), cmap='gray'); axL.set_title("Left IR speckle (1st eye)", fontsize=11)
    axR.imshow(stretch_ir(right), cmap='gray'); axR.set_title("Right IR speckle (2nd eye) — same pattern, shifted", fontsize=11)
    axD.imshow(render_depth(depth)); axD.set_title("Depth map (SGBM disparity -> Z=fB/d, jet)", fontsize=11)
    axC.imshow(cv2.cvtColor(cv2.imread(color), cv2.COLOR_BGR2RGB))
    axC.set_title("Color RGB (visible light, speckle invisible)", fontsize=11)
    x, y, rgb = cloud_front(ply)
    axP.scatter(x, -y, c=rgb, s=0.25, marker='.'); axP.set_title("Colored point cloud (front view)", fontsize=11)
    axP.set_xlabel("X (m)"); axP.set_ylabel("up (m)"); axP.set_aspect('equal')

    for ax in (axL, axR, axD, axC):
        ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle("Speckle structured-light imaging pipeline  (FM815-IX-E1)",
                 fontsize=14, y=0.97)
    # 流程箭头标注
    fig.text(0.5, 0.495, "stereo match (1D disparity search)  ->  depth  ->  texture-map RGB  ->  point cloud",
             ha='center', fontsize=10, color='dimgray')
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    plt.savefig(out, dpi=110)
    print(f"saved -> {out}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("用法: make_speckle_figure.py <ir_dir> <normal_dir> <out.png>")
    main(sys.argv[1], sys.argv[2], sys.argv[3])
