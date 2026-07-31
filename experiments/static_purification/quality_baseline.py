#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 0.5 · 数据优质度基线:每传感器单帧最大平面的拟合 RMSE = 点噪声 σ_single。

作 G2.1/G4 曲线的 k=1 左端基线;并报有效点占比。纯 numpy。
"""
import os, glob, math
import numpy as np
from scene_check import load_xyz, ransac_plane

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
CAP = os.path.join(_ROOT, "data", "cap100_20260731_110342")


def total_points(pcd):
    with open(pcd) as f:
        for ln in f:
            if ln.startswith("POINTS "):
                return int(ln.split()[1])
    return 0


def main():
    targets = [
        ("lidar_hesai", None, 0.03),
        ("lidar_robosense_front", None, 0.03),
        ("lidar_robosense_rear", None, 0.03),
        ("lidar_solid_livox", 30, 0.03),
        ("structured_light", None, 0.01),
    ]
    print(f"{'sensor':<26} {'总点':>8} {'有效':>8} {'有效%':>6} {'最大面内点':>9} {'平面RMSE(mm)':>12}")
    rows = []
    for name, maxr, thresh in targets:
        fs = sorted(glob.glob(os.path.join(CAP, name, "*.pcd")),
                    key=lambda p: int(''.join(c for c in os.path.basename(p) if c.isdigit()) or 0))
        if not fs:
            print(f"{name}: 无文件"); continue
        total = total_points(fs[0])
        pts = load_xyz(fs[0], maxr)
        valid = len(pts)
        r = ransac_plane(pts, thresh=thresh, iters=400)
        if r is None:
            print(f"{name}: 平面拟合失败"); continue
        c, nrm, inl = r
        d = -nrm @ pts[inl][0]
        dist = np.abs(pts[inl] @ nrm + d)
        rmse = math.sqrt((dist ** 2).mean()) * 1000  # mm
        pct = 100.0 * valid / total if total else 0
        print(f"{name:<26} {total:>8} {valid:>8} {pct:>5.0f}% {c:>9} {rmse:>10.2f}")
        rows.append((name, total, valid, pct, c, rmse))

    # 存 csv
    out = os.path.join(_HERE, "quality_baseline.csv")
    with open(out, "w") as f:
        f.write("sensor,total,valid,valid_pct,plane_inliers,plane_rmse_mm\n")
        for r in rows:
            f.write(",".join(str(x) for x in r) + "\n")
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
