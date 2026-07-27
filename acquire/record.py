#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多传感器协同采集: 读 config/rig.yaml → registry 派发驱动 → 全部启用设备并发采集 → 落盘 + 索引。

一个触发即同时采集 rig.yaml 里所有 enabled 设备(相机 / 鱼眼 / 结构光 / 各 LiDAR)。每路一线程、
互不阻塞; 每帧 append 到 data/<run>/<name>/manifest.jsonl; 收尾写 run 级 index.csv(全帧时间轴)
与 align.csv(以相机为基准的跨传感器最近邻对齐, 供离线配准)。

取数节奏:
  · 流式型 LiDAR: 到 spec.duration 自然结束(grab 返回 ended)。
  · 批量型结构光: 采完 N 帧自然结束。
  · 相机/鱼眼: 持续拍, 靠 --duration 或 Ctrl-C 停。

用法:
  export LD_LIBRARY_PATH=$PWD/third_party/EN-HCNetSDKV6.1.9.4_build20220412_linux64/lib
  python3 acquire/record.py                       # 采全部启用设备, Ctrl-C 停
  python3 acquire/record.py --duration 10         # 全局 10s
  python3 acquire/record.py --only cam_hik,lidar_hesai --tag calib_01
"""
import argparse
import csv
import json
import os
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402
from sensors.base import Sensor  # noqa: E402  (仅用于类型提示/文档)
from acquire.registry import resolve_driver  # noqa: E402

DEFAULT_INTERVAL = 0.5


def load_rig(path=None):
    path = path or (ROOT / "config" / "rig.yaml")
    with open(path) as f:
        cfg = yaml.safe_load(f)
    return cfg.get("devices", []), cfg.get("host", {})


def _append_manifest(path, sample):
    rel = None
    if sample.payload:
        try:
            rel = os.path.relpath(sample.payload, os.path.dirname(path))
        except ValueError:
            rel = sample.payload
    with open(path, "a") as f:
        f.write(json.dumps({
            "sensor": sample.sensor,
            "ts": round(sample.timestamp, 6),
            "frame": sample.meta.get("frame"),
            "bytes": sample.meta.get("bytes"),
            "latency_ms": sample.meta.get("latency_ms"),
            "payload": rel,
        }, ensure_ascii=False) + "\n")


def _run_one(sensor: Sensor, stop: threading.Event, manifest: str):
    """单路采集循环: grab → 落 manifest → 打印, 直到 ended / stop。"""
    interval = sensor.spec.get("interval", DEFAULT_INTERVAL)
    n = 0
    try:
        with sensor:
            while not stop.is_set():
                sample = sensor.grab()
                if sample.meta.get("ended"):
                    break
                _append_manifest(manifest, sample)
                n += 1
                m = sample.meta
                base = os.path.basename(str(sample.payload)) if sample.payload else "-"
                print(f"  {sensor.name}: #{m.get('frame', '-')} "
                      f"{m.get('bytes', '-')}B  -> {base}")
                if stop.wait(interval):    # 可被 stop 立即唤醒的 sleep
                    break
    except Exception as e:
        print(f"  {sensor.name} 采集异常: {e}")
    print(f"  [{sensor.name}] 结束, 共 {n} 帧")
    return n


def _load_manifests(run_dir):
    """{sensor_name: [(ts, payload), ...]}, 各路按 ts 升序。"""
    out = {}
    for mf in sorted(run_dir.glob("*/manifest.jsonl")):
        name = mf.parent.name
        rows = []
        with open(mf) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                rows.append((d.get("ts", 0.0), d.get("payload")))
        out[name] = sorted(rows)
    return out


def _write_index(run_dir, manifests):
    rows = []
    for name, seq in manifests.items():
        for ts, payload in seq:
            rows.append((ts, name, payload))
    rows.sort()
    out = run_dir / "index.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ts", "sensor", "payload"])
        w.writerows(rows)
    return out, len(rows)


def _write_align(run_dir, manifests):
    """以第一个相机/鱼眼为基准, 对其每帧找其它各传感器时间戳最近邻, 写 align.csv。无相机则跳过。"""
    import bisect
    cam = next((n for n in manifests if "cam" in n.lower() or "fisheye" in n.lower()), None)
    others = [n for n in manifests if n != cam]
    if not cam or len(others) < 1:
        return None
    out = run_dir / "align.csv"
    keys = {o: [t for t, _ in manifests[o]] for o in others}
    # 表头与数据行同为「每传感器 (ts, payload) 相邻」的交错布局, 便于按列名解析
    header = ["cam_ts", "cam_payload"]
    for o in others:
        header += [f"{o}_ts", f"{o}_payload"]
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for cts, cp in manifests[cam]:
            row = [cts, cp]
            for o in others:
                k = keys[o]
                if not k:
                    row += ["", ""]
                    continue
                i = bisect.bisect_left(k, cts)
                cands = ([i - 1] if i > 0 else []) + ([i] if i < len(k) else [])
                j = min(cands, key=lambda x: abs(k[x] - cts))
                row += [manifests[o][j][0], manifests[o][j][1]]
            w.writerow(row)
    return out


def main():
    ap = argparse.ArgumentParser(description="多传感器协同采集: 读 rig.yaml → 并发采集全部启用设备")
    ap.add_argument("--duration", type=float, default=None,
                    help="全局采集时长(s); 不给则 Ctrl-C 停(流式 LiDAR 仍按各自 spec.duration 自停)")
    ap.add_argument("--tag", default=None, help="run 命名(目录 data/<tag>_<ts>/)")
    ap.add_argument("--only", default=None, help="只采指定设备(逗号分隔 name), 如 cam_hik,lidar_hesai")
    args = ap.parse_args()

    devices, host = load_rig()
    host_ip = host.get("ip", "192.168.1.200")
    only = set(s.strip() for s in args.only.split(",")) if args.only else None

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = ROOT / "data" / (f"{args.tag}_{ts}" if args.tag else ts)
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"采集机: {host_ip}    本次输出: {run_dir}")
    print(f"rig 共 {len(devices)} 台设备:\n")

    sensors = []
    for d in devices:
        name, kind, model = d.get("name"), d.get("kind"), d.get("model")
        if only and name not in only:
            continue
        enabled = d.get("enabled", True)
        drv = resolve_driver(kind, model)
        if not enabled:
            print(f"  [-禁用] {name:<26} kind={kind}"); continue
        if not drv:
            print(f"  [✗待办] {name:<26} kind={kind:<20} model={model}"); continue
        spec = dict(d)
        spec["host_ip"] = host_ip
        if args.duration is not None:
            spec["duration"] = args.duration    # 全局 duration 覆盖流式时长
        try:
            out = run_dir / name
            out.mkdir(parents=True, exist_ok=True)
            s = drv(name, spec)
            s.out_dir = str(out)
            sensors.append(s)
            print(f"  [✓实装] {name:<26} kind={kind:<20} model={model}  ip={d.get('ip')}")
        except Exception as e:
            print(f"  [!! ] {name} 实例化失败: {e}")

    if not sensors:
        print("\n(没有可采集的设备。)")
        return

    stop = threading.Event()

    def _sig(_signum, _frame):
        if stop.is_set():
            print("\n强制退出。"); os._exit(1)
        print("\n停止中(再按 Ctrl-C 强制退出)...")
        stop.set()
    signal.signal(signal.SIGINT, _sig)

    print(f"\n启动 {len(sensors)} 路, " +
          (f"全局 {args.duration}s 后停" if args.duration else "流式自停 + Ctrl-C 停相机") + " ...")
    threads = []
    for s in sensors:
        manifest = os.path.join(s.out_dir, "manifest.jsonl")
        t = threading.Thread(target=_run_one, args=(s, stop, manifest), daemon=True)
        t.start()
        threads.append(t)

    if args.duration is not None:
        stop.wait(args.duration + 3)           # 容差: 等流式自然收尾
        stop.set()
    else:
        while not stop.is_set() and any(t.is_alive() for t in threads):
            time.sleep(0.3)
    for t in threads:
        t.join(timeout=10)

    manifests = _load_manifests(run_dir)
    idx, nidx = _write_index(run_dir, manifests)
    aln = _write_align(run_dir, manifests)
    total = sum(len(v) for v in manifests.values())
    print(f"\n本次 {len(manifests)} 路共 {total} 帧, 索引 -> {idx}")
    if aln:
        print(f"跨传感器对齐(以相机为基准) -> {aln}")
    print(f"输出根目录: {run_dir}")


if __name__ == "__main__":
    main()
