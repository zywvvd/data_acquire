#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ASCII PCD → ASCII PLY(给 CloudCompare 查看用)。全部属性输出为 float。

为什么全 float: CloudCompare 的 ASCII PLY 解析器对混合属性类型(float/uchar/ushort)敏感,
会把 `property ushort ring` 读到某行报 "error reading ring of vertex N"。全 float 最稳。

同时过滤无效点(避免撑爆 CloudCompare 视野):
  · NaN / Inf 坐标
  · 原点 (0,0,0)(雷达无效回波常写成全 0)
  · --max-range R: 距离 > R 的点丢弃(如 Livox 室内出现 157m 飞点)

用法:
  python3 tools/pcd_to_ply.py in.pcd out.ply
  python3 tools/pcd_to_ply.py in.pcd out.ply --max-range 30      # 剔远点(室内)
"""
import sys
import math


def pcd_to_ply(pcd: str, ply: str, max_range: float = None) -> int:
    fields = types = None
    with open(pcd) as f:
        for ln in f:
            s = ln.strip()
            if s.startswith("FIELDS "):
                fields = s.split()[1:]
            elif s.startswith("TYPE "):
                types = s.split()[1:]
            elif s == "DATA ascii":
                break
        if not fields:
            raise ValueError(f"{pcd}: 解析不到 FIELDS")
        try:
            xi, yi, zi = fields.index("x"), fields.index("y"), fields.index("z")
        except ValueError:
            raise ValueError(f"{pcd}: FIELDS 缺 x/y/z")
        good = []
        for ln in f:
            t = ln.split()
            if len(t) != len(fields):
                continue
            try:
                vals = [float(v) for v in t]
            except ValueError:
                continue
            x, y, z = vals[xi], vals[yi], vals[zi]
            if (math.isnan(x) or math.isinf(x) or math.isinf(y) or math.isinf(z)):
                continue
            if x == 0.0 and y == 0.0 and z == 0.0:       # 无效原点
                continue
            if max_range and (x * x + y * y + z * z) > max_range * max_range:
                continue
            good.append(vals)
    with open(ply, "w") as out:
        out.write("ply\nformat ascii 1.0\n")
        out.write(f"comment converted from {pcd}\n")
        out.write(f"element vertex {len(good)}\n")
        for fld in fields:
            out.write(f"property float {fld}\n")          # 全 float
        out.write("end_header\n")
        for vals in good:
            out.write(" ".join(f"{v:.6g}" for v in vals) + "\n")
    return len(good)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python3 tools/pcd_to_ply.py <in.pcd> <out.ply> [--max-range R]"); sys.exit(1)
    mr = None
    args = sys.argv[3:]
    if args and args[0] == "--max-range":
        mr = float(args[1])
    n = pcd_to_ply(sys.argv[1], sys.argv[2], mr)
    print(f"{sys.argv[1]} -> {sys.argv[2]}  ({n} 点" + (f", 剔远点>{mr}m" if mr else "") + ")")
