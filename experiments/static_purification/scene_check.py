#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 0.4 · 场景核验:在点云里 RANSAC 找 3 个主导平面,看是否近正交(三面角)。

不依赖 open3d(纯 numpy)。判定:若存在 ≥3 个大平面且两两夹角近 90°(cos 小),
则场景含三面角 → Phase 5.3 绝对准确度可做。
"""
import sys, os, glob, math
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
CAP = os.path.join(_ROOT, "data", "cap100_20260731_110342")


def load_xyz(pcd, max_range=None):
    pts = []
    with open(pcd) as f:
        for ln in f:
            if ln.strip() == "DATA ascii":
                break
        for ln in f:
            t = ln.split()
            if len(t) < 3:
                continue
            try:
                x, y, z = float(t[0]), float(t[1]), float(t[2])
            except ValueError:
                continue
            if x == 0 and y == 0 and z == 0:
                continue
            if max_range and x * x + y * y + z * z > max_range * max_range:
                continue
            pts.append((x, y, z))
    return np.array(pts)


def ransac_plane(pts, thresh=0.03, iters=400, rng=None):
    rng = rng or np.random.default_rng(0)
    n = len(pts)
    if n < 3:
        return None
    best = None
    for _ in range(iters):
        idx = rng.choice(n, 3, replace=False)
        p0, p1, p2 = pts[idx]
        nrm = np.cross(p1 - p0, p2 - p0)
        nn = np.linalg.norm(nrm)
        if nn < 1e-9:
            continue
        nrm /= nn
        d = -nrm @ p0
        dist = np.abs(pts @ nrm + d)
        inl = dist < thresh
        c = int(inl.sum())
        if best is None or c > best[0]:
            best = (c, nrm, inl)
    return best


def segment_planes(pts, n_planes=3, thresh=0.03, iters=400, min_inliers=1000):
    remaining = pts.copy()
    planes = []
    rng = np.random.default_rng(42)
    for _ in range(n_planes):
        if len(remaining) < min_inliers:
            break
        r = ransac_plane(remaining, thresh, iters, rng)
        if r is None or r[0] < min_inliers:
            break
        c, nrm, inl = r
        planes.append((c, nrm))
        remaining = remaining[~inl]
    return planes


def main():
    targets = [
        ("lidar_hesai", "frame_000001.pcd", None),
        ("lidar_solid_livox", "00000.pcd", 30),
        ("structured_light", "points_0000.pcd", None),
    ]
    for name, pat, maxr in targets:
        fs = glob.glob(os.path.join(CAP, name, pat))
        if not fs:
            print(f"\n{name}: 无文件"); continue
        pts = load_xyz(fs[0], maxr)
        print(f"\n=== {name}: {len(pts)} 有效点 ({os.path.basename(fs[0])}) ===")
        planes = segment_planes(pts, 3, thresh=0.03, iters=400, min_inliers=1000)
        for i, (c, n) in enumerate(planes):
            print(f"  面{i+1}: {c:>6} 点  法向=({n[0]:+.2f},{n[1]:+.2f},{n[2]:+.2f})")
        if len(planes) >= 2:
            print("  两两夹角:")
            orth = 0
            for i in range(len(planes)):
                for j in range(i + 1, len(planes)):
                    cos = abs(np.dot(planes[i][1], planes[j][1]))
                    ang = math.degrees(math.acos(min(1.0, cos)))
                    near = "近正交" if cos < 0.25 else ""
                    print(f"    面{i+1}-面{j+1}: {ang:5.1f}°  (|cos|={cos:.2f}) {near}")
                    if cos < 0.25:
                        orth += 1
            print(f"  → 近正交对数: {orth}/{len(planes)*(len(planes)-1)//2}")


if __name__ == "__main__":
    main()
