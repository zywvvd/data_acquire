#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 1 · 净化(融合)函数库。

- fuse_mechanical: 机械雷达(禾赛/速腾)按 (ring,az) / (el,az) 桶取 **均值** = σ/√N 降噪。
- fuse_voxel: 固态(Livox)/结构光 累积 + voxel 降采样 + SOR(去飞点)。
- load_pcd_xyz / filter_invalid / to_o3d / plane_rmse: 通用工具。

mean(非 median)用于机械桶:匹配 σ/√N 理论、可向量化(bincount);边缘双峰桶若需鲁棒后续可换 median。
"""
import os, glob, math
import numpy as np
import open3d as o3d
from scene_check import load_xyz, ransac_plane

_HERE = os.path.dirname(os.path.abspath(__file__))


def load_pcd_xyz(path, max_range=None, need_ring=False):
    """读 ASCII PCD → xyz(滤 0/NaN/远); need_ring 时也返回 ring 数组(无则 None)。"""
    xs, ys, zs, rings = [], [], [], []
    fields = []
    with open(path) as f:
        for ln in f:
            s = ln.strip()
            if s.startswith("FIELDS "):
                fields = s.split()[1:]
            if s == "DATA ascii":
                break
        ri = fields.index("ring") if "ring" in fields else -1
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
            xs.append(x); ys.append(y); zs.append(z)
            if need_ring and ri >= 0:
                rings.append(int(float(t[ri])))
    xyz = np.column_stack([xs, ys, zs]) if xs else np.zeros((0, 3))
    if need_ring:
        return xyz, (np.array(rings) if ri >= 0 else None)
    return xyz


def to_o3d(xyz):
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(np.asarray(xyz, dtype=np.float64))
    return pcd


def fuse_mechanical(paths, az_bins=720, el_bins=128, max_range=None):
    """按 (ring,az_bin)[禾赛] 或 (el_bin,az_bin)[速腾] 分桶,跨帧 xyz 取均值。"""
    xs, ys, zs, keys = [], [], [], []
    for p in paths:
        xyz, ring = load_pcd_xyz(p, max_range, need_ring=True)
        if len(xyz) == 0:
            continue
        az = np.degrees(np.arctan2(xyz[:, 1], xyz[:, 0]))
        az_b = (np.floor((az + 180) / 360 * az_bins).astype(int)) % az_bins
        if ring is not None:
            k = ring.astype(int) * az_bins + az_b
        else:
            el = np.degrees(np.arctan2(xyz[:, 2], np.hypot(xyz[:, 0], xyz[:, 1])))
            el_b = (np.floor((el + 90) / 180 * el_bins).astype(int)) % el_bins
            k = el_b * az_bins + az_b
        xs.append(xyz[:, 0]); ys.append(xyz[:, 1]); zs.append(xyz[:, 2]); keys.append(k)
    if not xs:
        return np.zeros((0, 3))
    x = np.concatenate(xs); y = np.concatenate(ys); z = np.concatenate(zs); k = np.concatenate(keys)
    n = np.bincount(k)
    mx = np.bincount(k, weights=x) / np.maximum(n, 1)
    my = np.bincount(k, weights=y) / np.maximum(n, 1)
    mz = np.bincount(k, weights=z) / np.maximum(n, 1)
    valid = n > 0
    return np.column_stack([mx[valid], my[valid], mz[valid]])


def fuse_voxel(paths, voxel_size=0.02, max_range=None, sor_nb=20, sor_std=2.0):
    """累积全部帧 → voxel 降采样(质心)+ 统计离群剔除(SOR)。"""
    allp = []
    for p in paths:
        xyz = load_pcd_xyz(p, max_range)
        if len(xyz):
            allp.append(xyz)
    if not allp:
        return np.zeros((0, 3))
    pcd = to_o3d(np.concatenate(allp))
    pcd = pcd.voxel_down_sample(voxel_size)
    if sor_nb and len(pcd.points) > sor_nb:
        pcd, _ = pcd.remove_statistical_outlier(nb_neighbors=sor_nb, std_ratio=sor_std)
    return np.asarray(pcd.points)


def plane_rmse(xyz, thresh=0.03, iters=400):
    """最大平面的拟合 RMSE(mm),xyz 为 numpy。"""
    r = ransac_plane(np.asarray(xyz), thresh=thresh, iters=iters)
    if r is None:
        return float("nan")
    c, nrm, inl = r
    d = -nrm @ xyz[inl][0]
    dist = np.abs(xyz[inl] @ nrm + d)
    return math.sqrt((dist ** 2).mean()) * 1000.0


def _frames(name, cap=os.path.join(_HERE, "..", "..", "data", "cap100_20260731_110342")):
    d = os.path.join(cap, name)
    return sorted(glob.glob(os.path.join(d, "*.pcd")),
                  key=lambda p: int(''.join(c for c in os.path.basename(p) if c.isdigit()) or 0))


if __name__ == "__main__":
    # 自测: Hesai 机械桶融合, RMSE 应随 N 按 1/√N 降
    print("== Hesai 机械桶融合(均值,σ/√N 自测)==")
    fr = _frames("lidar_hesai")
    print(f"  可用 {len(fr)} 帧; 取前若干帧融合, 测最大平面 RMSE")
    base = plane_rmse(load_pcd_xyz(fr[0]))
    print(f"  N= 1   RMSE={base:6.2f}mm  (单帧基线)")
    for N in [4, 9, 16, 25]:
        xyz = fuse_mechanical(fr[:N], max_range=30)
        rm = plane_rmse(xyz)
        print(f"  N={N:<3} RMSE={rm:6.2f}mm  期望≈{base/math.sqrt(N):5.2f}  比值={rm/base:.2f}")
    # Livox voxel
    print("\n== Livox voxel 融合(密度随 N 升)==")
    fr = _frames("lidar_solid_livox")
    for N in [1, 4, 16]:
        xyz = fuse_voxel(fr[:N], voxel_size=0.02, max_range=30)
        print(f"  N={N:<3} voxel(2cm)后 {len(xyz)} 点")
