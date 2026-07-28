#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多传感器协同采集主程序 —— 读 config/rig.yaml, 并发采集全部/指定设备, 落盘 + 索引 + 对齐。

一个触发即可同时采集 rig.yaml 里所有 enabled 设备(相机 / 鱼眼 / 结构光 / 各 LiDAR)。每路一线程、
互不阻塞; 每帧 append 到 data/<run>/<name>/manifest.jsonl; 收尾写 run 级 index.csv(全帧时间轴)
与 align.csv(以相机为基准的跨传感器最近邻对齐, 列布局为「每传感器 ts,payload 相邻」, 供离线配准)。

【设备 name 对照表】—— name = --only 的取值 = 每路输出子目录名
    cam_hik                  海康相机         192.168.1.107   持续拍, --duration/Ctrl-C 停
    fisheye_hik              海康鱼眼         192.168.1.99    持续拍, --duration/Ctrl-C 停
    structured_light         图漾结构光       192.168.1.114   采完 N 帧自停(默认 6 帧)
    lidar_solid_livox        Livox HAP        192.168.1.100   流式, 到 --duration 自停
    lidar_hesai              禾赛 QT128       192.168.1.201   流式, 到 --duration 自停
    lidar_robosense_front    速腾(前)        192.168.1.202   流式, 到 --duration 自停
    lidar_robosense_rear     速腾(后)        192.168.1.205   流式, 到 --duration 自停

【前置】
  · 终端用 anaconda 的 python3(/home/vvd/anaconda3/bin/python3, 带 cv2/yaml/numpy)。
    裸 python3.14(VSCode 默认选它)缺依赖会 ModuleNotFoundError。
  · 采相机/鱼眼前设 SDK 库路径(LiDAR / 结构光的库由各自驱动自动注入, 无需手设):
        export LD_LIBRARY_PATH=$PWD/third_party/EN-HCNetSDKV6.1.9.4_build20220412_linux64/lib

【用法示例】
  # 0. 先看 rig.yaml 里有哪些设备 / 各自 name(用 --only 前查一眼)
  python3 acquire/record.py --help
  grep 'name:' config/rig.yaml

  # 1. 全部 7 路并发, 全局 10s
  python3 acquire/record.py --duration 10

  # 2. 只采一台(例: 禾赛 QT128, 10s)
  python3 acquire/record.py --only lidar_hesai --duration 10

  # 3. 采多台(逗号分隔, 不要空格)
  python3 acquire/record.py --only cam_hik,lidar_robosense_front,lidar_robosense_rear --duration 10
  python3 acquire/record.py --only lidar_hesai,lidar_solid_livox,lidar_robosense_front,lidar_robosense_rear --duration 15   # 只采 4 路 LiDAR

  # 4. 给本次 run 命名(输出目录 data/calib01_<时间戳>/)
  python3 acquire/record.py --only cam_hik,structured_light --tag calib_01 --duration 8

  # 5. 不写 --duration: 流式 LiDAR 按各自 spec.duration 自停, 相机/鱼眼 Ctrl-C 停
  python3 acquire/record.py --only cam_hik,lidar_hesai

  # 6. 采相机/鱼眼(先 export LD_LIBRARY_PATH, 见「前置」)
  export LD_LIBRARY_PATH=$PWD/third_party/EN-HCNetSDKV6.1.9.4_build20220412_linux64/lib
  python3 acquire/record.py --only cam_hik,fisheye_hik --duration 10

  # 7. Ctrl-C 优雅停止: 第一次 Ctrl-C 收尾, 再按一次强制退出
  python3 acquire/record.py                # 跑起来后按 Ctrl-C

【--duration 对不同设备的意义】
  · 流式 LiDAR(禾赛/速腾/Livox): 到 --duration 自然结束。
  · 结构光(图漾): 采完 N 帧自然结束(rig.yaml 默认 6 帧); --duration 只决定 record 等多久,
    不影响帧数 —— 采结构光时把 --duration 给够等待时间即可。
  · 相机/鱼眼: 持续拍, 到 --duration 或 Ctrl-C 停。
  不给 --duration: 流式按各自 spec.duration 自停; 相机/鱼眼靠 Ctrl-C 停。

【输出布局】
  data/<tag_时间戳>/
  ├── cam_hik/  fisheye_hik/  structured_light/  lidar_hesai/ ...   # 每路一个子目录
  │   ├── *.jpg / *.png / *.pcd ...                                   #   帧文件
  │   └── manifest.jsonl                                              #   每帧一行: sensor/ts/frame/bytes/payload
  ├── index.csv                # 全帧时间轴(ts, sensor, payload), 按 ts 升序
  └── align.csv                # 以相机为基准的跨传感器最近邻对齐(无相机则不生成)

【CLI 参数】
  --duration N   全局采集时长(s)。不给则流式按各自 spec.duration 自停、相机靠 Ctrl-C 停。
  --only  NAMES  只采指定设备(逗号分隔 name, 无空格)。不给则采全部 enabled 设备。
  --tag   NAME   给本次 run 命名(目录 data/<tag>_<时间戳>/)。不给则用纯时间戳。

【小贴士】
  · 单台调试也可用各设备自己的 demo(sensors/<kind>/*_demo.py), 可手调 IP/端口/帧数。
  · 想知道某次 run 采了哪些帧: 看 data/<run>/index.csv; 跨传感器配准看 align.csv。
  · 改设备参数(IP/端口/型号/enabled)统一去 config/rig.yaml 改, 不用动本文件。
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
    ap = argparse.ArgumentParser(
        description="多传感器协同采集: 读 rig.yaml → 并发采集全部/指定设备 → 落盘 + index.csv + align.csv",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
设备 name(--only 取值): cam_hik / fisheye_hik / structured_light /
  lidar_solid_livox / lidar_hesai / lidar_robosense_front / lidar_robosense_rear

示例:
  python3 acquire/record.py --duration 10                                  # 全部 7 路
  python3 acquire/record.py --only lidar_hesai --duration 10               # 只采一台
  python3 acquire/record.py --only cam_hik,lidar_hesai --duration 10       # 多台(逗号分隔)
  python3 acquire/record.py --only cam_hik --tag calib_01 --duration 8     # 给 run 命名
  python3 acquire/record.py                                                # Ctrl-C 停相机

(采相机/鱼眼前先: export LD_LIBRARY_PATH=$PWD/third_party/EN-HCNetSDKV6.1.9.4_build20220412_linux64/lib)
详细用法见本文件顶部 docstring。""")
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
