#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 2 · 参考系与粗配准。

- L1 世界系:禾赛全帧桶融合 → ref_qt128(外参=单位阵)。
- 各传感器 → ref:FPFH+RANSAC 全局粗配准 + point-to-plane ICP 精配 → 标称外参 T_nominal
  (作后续 Phase 3/4 所有 ICP 的固定初值)。
"""
import os, json
import numpy as np
import open3d as o3d
from fuse import fuse_mechanical, fuse_voxel, to_o3d, _frames

_HERE = os.path.dirname(os.path.abspath(__file__))


def register(src_xyz, dst_xyz, voxel=0.1, coarse_corr=0.3):
    """src→dst 全局粗配(RANSAC, 大 max_corr)+ 多尺度 ICP 精配。返回 (T, fitness, inlier_rmse)。"""
    src = to_o3d(src_xyz).voxel_down_sample(voxel)
    dst = to_o3d(dst_xyz).voxel_down_sample(voxel)
    src.estimate_normals(o3d.geometry.KDTreeSearchParamKNN(30))
    dst.estimate_normals(o3d.geometry.KDTreeSearchParamKNN(30))
    rad = voxel * 2.5
    fs = o3d.pipelines.registration.compute_fpfh_feature(
        src, o3d.geometry.KDTreeSearchParamHybrid(radius=rad, max_nn=30))
    fd = o3d.pipelines.registration.compute_fpfh_feature(
        dst, o3d.geometry.KDTreeSearchParamHybrid(radius=rad, max_nn=30))
    est = o3d.pipelines.registration.TransformationEstimationPointToPoint(False)
    rr = o3d.pipelines.registration.registration_ransac_based_on_feature_matching(
        src, dst, fs, fd, False, coarse_corr, est, 4,
        [o3d.pipelines.registration.CorrespondenceCheckerBasedOnEdgeLength(0.9),
         o3d.pipelines.registration.CorrespondenceCheckerBasedOnDistance(coarse_corr)],
        o3d.pipelines.registration.RANSACConvergenceCriteria(200000, 0.999))
    T = np.asarray(rr.transformation)
    p2p = o3d.pipelines.registration.TransformationEstimationPointToPlane()
    crit = o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=200)
    # 多尺度 ICP: 0.2 → 0.1 → 0.05
    for mc in [0.2, 0.1, 0.05]:
        ri = o3d.pipelines.registration.registration_icp(src, dst, mc, T, p2p, crit)
        T = np.asarray(ri.transformation)
    return T, ri.fitness, ri.inlier_rmse


def build_ref(n=100):
    fr = _frames("lidar_hesai")[:n]
    xyz = fuse_mechanical(fr, max_range=30)
    o3d.io.write_point_cloud(os.path.join(_HERE, "ref_qt128.ply"), to_o3d(xyz))
    print(f"[ref] QT128 融合({n}帧): {len(xyz)} 点 -> ref_qt128.ply")
    return xyz


def fuse_sensor(name, n=30):
    fr = _frames(name)[:n]
    if name.startswith("lidar_robosense"):
        return fuse_mechanical(fr, max_range=30)
    return fuse_voxel(fr, voxel_size=0.02, max_range=30)


def main():
    ref = build_ref(n=100)
    extr = {}
    for name in ["lidar_robosense_front", "lidar_robosense_rear",
                 "lidar_solid_livox", "structured_light"]:
        xyz = fuse_sensor(name, n=30)
        T, fit, rmse = register(xyz, ref)
        extr[name] = np.asarray(T).tolist()
        print(f"  {name:<24} {len(xyz):>7}点  fitness={fit:.3f}  icp_rmse={rmse*1000:6.1f}mm")
    with open(os.path.join(_HERE, "nominal_extrinsics.json"), "w") as f:
        json.dump(extr, f, indent=2)
    print("-> nominal_extrinsics.json")


if __name__ == "__main__":
    main()
