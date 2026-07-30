#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理一次采集 run: 以 manifest 为权威清单裁剪冗余帧、重建被截断的 manifest、重生成 run 级索引。

背景
----
· 流式 LiDAR(禾赛/速腾/Livox)子进程会持续往 out_dir 写文件, record.py 每路只 grab 够 N 帧即
  停该路线程 —— 但子进程在 stop 前已写入远多于 N 的帧, 磁盘残留 = manifest 记录的若干倍。
· 批量设备(结构光)若被 record 的兜底 deadline 截断, manifest 可能只记 1 条, 但磁盘上批量
  子进程其实已写满 N 帧(进程被孤儿化后继续跑完)。
两种情况磁盘都「比 manifest 多」。本工具以 manifest 为「权威采集清单」做收尾清理, 让「每设备
N 帧」名副其实(磁盘 = manifest = N)。

做什么
------
  --rebuild NAME[:LIMIT]   据磁盘 pcd 重建 NAME 的 manifest(取前 LIMIT 帧)。用于 manifest 被
                            截断/缺失但磁盘帧完整的设备(如结构光)。可重复: --rebuild a:100 --rebuild b:100
  --trim                   删除各设备目录里 manifest 未引用的数据帧(按文件名末段数字=帧号判定,
                            故结构光同一帧的 points/color/depth 共享帧号, 一起留或一起删)
  --normalize              把所有 manifest 的 ts 改成文件 mtime(墙上时钟)。record.py 原用
                            time.monotonic(), 各设备/各次 run 之间不可比; mtime 同主机可比,
                            这样 index.csv/align.csv 的跨传感器最近邻对齐才有意义
  (末尾总是重生成 <run>/index.csv 与 align.csv)

帧号判定: 取文件名最后一段连续数字 —— frame_000123.pcd→123, points_0042.pcd→42,
color_0042.jpg→42, 00042.pcd→42。无数字的文件(manifest.jsonl/sensor.log/device.json)不参与裁剪。

用法
----
  python3 tools/tidy_run.py data/cap100_20260730_180436 --trim
  python3 tools/tidy_run.py data/cap100_... --rebuild structured_light:100
  python3 tools/tidy_run.py data/cap100_... --rebuild structured_light:100 --rebuild lidar_solid_livox:100 --trim --normalize
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from acquire.record import _load_manifests, _write_index, _write_align  # noqa: E402

_DATA_EXTS = (".jpg", ".jpeg", ".png", ".pcd", ".ply", ".bmp")
_NUM = re.compile(r"(\d+)(?=[^\d]*$)")  # 文件名(去后缀)里最后一段连续数字


def frame_idx(name: str):
    """文件名末段数字 = 帧号; 无数字返回 None(非数据帧文件, 裁剪时跳过)。"""
    stem = os.path.splitext(os.path.basename(name))[0]
    m = _NUM.search(stem)
    return int(m.group(1)) if m else None


def list_payloads(dev_dir: Path):
    """读 manifest.jsonl -> [(payload_relpath, frame_idx), ...]; 无则空。"""
    mf = dev_dir / "manifest.jsonl"
    if not mf.exists():
        return []
    out = []
    with open(mf) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            p = json.loads(line).get("payload")
            if p:
                out.append((p, frame_idx(p)))
    return out


def rebuild(dev_dir: Path, limit=None):
    """据磁盘 pcd 重建 manifest(取前 limit 帧)。返回写入条数。"""
    pcds = sorted(dev_dir.glob("*.pcd"))
    if limit is not None:
        pcds = pcds[:limit]
    mf = dev_dir / "manifest.jsonl"
    n = 0
    with open(mf, "w") as f:
        for i, p in enumerate(pcds, 1):
            f.write(json.dumps({
                "sensor": dev_dir.name,
                "ts": os.path.getmtime(p),          # mtime 墙上时钟, 跨设备可比
                "frame": frame_idx(p.name) if frame_idx(p.name) is not None else i,
                "bytes": os.path.getsize(p),
                "latency_ms": None,
                "payload": p.name,
            }, ensure_ascii=False) + "\n")
            n += 1
    return n


def trim(dev_dir: Path):
    """删 manifest 未引用的数据帧。返回 (保留, 删除) 文件数。"""
    payloads = list_payloads(dev_dir)
    keep_idx = {idx for _, idx in payloads if idx is not None}
    keep_names = {os.path.basename(p) for p, _ in payloads}
    kept = deleted = 0
    for p in dev_dir.iterdir():
        if not p.is_file() or p.suffix.lower() not in _DATA_EXTS:
            continue
        idx = frame_idx(p.name)
        # 有帧号 → 按帧号集合判; 无帧号 → 按文件名精确判(兼容纯文件名 manifest)
        if idx is not None:
            want = idx in keep_idx
        else:
            want = p.name in keep_names
        if want:
            kept += 1
        else:
            p.unlink()
            deleted += 1
    return kept, deleted


def normalize(dev_dir: Path):
    """把 manifest 每条 ts 改成 payload 文件的 mtime。"""
    mf = dev_dir / "manifest.jsonl"
    if not mf.exists():
        return
    rows = []
    with open(mf) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    for r in rows:
        p = dev_dir / r["payload"] if r.get("payload") else None
        if p and p.exists():
            r["ts"] = round(os.path.getmtime(p), 6)
    with open(mf, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(description="整理采集 run: 裁剪冗余帧/重建 manifest/重生成索引")
    ap.add_argument("run", help="run 目录(如 data/cap100_20260730_180436)")
    ap.add_argument("--rebuild", action="append", default=[],
                    help="据磁盘 pcd 重建该设备 manifest, 形如 name 或 name:limit(可重复)")
    ap.add_argument("--trim", action="store_true", help="删除 manifest 未引用的数据帧")
    ap.add_argument("--normalize", action="store_true",
                    help="manifest ts 全部改成文件 mtime(跨设备可比)")
    args = ap.parse_args()

    run = Path(args.run).resolve()
    print(f"整理 run: {run}")

    # 1) 重建 manifest(在 trim 前, 让 trim 有权威清单可依)
    for spec in args.rebuild:
        name, _, lim = spec.partition(":")
        d = run / name
        if not d.is_dir():
            print(f"  [跳过] --rebuild {name}: 目录不存在"); continue
        lim = int(lim) if lim.strip() else None
        n = rebuild(d, lim)
        print(f"  [重建] {name}: manifest <- 磁盘前 {n} 个 pcd")

    # 2) 裁剪冗余帧
    if args.trim:
        for d in sorted(p for p in run.iterdir() if p.is_dir()):
            k, dl = trim(d)
            if dl:
                print(f"  [裁剪] {d.name}: 保留 {k} 个数据文件, 删除 {dl} 个冗余")
            else:
                print(f"  [裁剪] {d.name}: 无冗余(保留 {k})")

    # 3) ts 归一化为 mtime
    if args.normalize:
        for d in sorted(p for p in run.iterdir() if p.is_dir()):
            normalize(d)
        print("  [归一] 所有 manifest ts -> 文件 mtime")

    # 4) 重生成 run 级 index.csv + align.csv
    manifests = _load_manifests(run)
    idx, nidx = _write_index(run, manifests)
    aln = _write_align(run, manifests)
    print(f"  [索引] index.csv {nidx} 行 -> {idx}")
    print(f"  [对齐] {'align.csv -> ' + str(aln) if aln else '(无相机, 跳过 align.csv)'}")
    for name, seq in sorted(manifests.items()):
        print(f"    {name}: {len(seq)} 帧")


if __name__ == "__main__":
    main()
