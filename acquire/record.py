"""读 config/rig.yaml → registry 派发驱动 → 实装的路线程化采集 → 时间戳落盘。

现状: camera / fisheye(海康) 已实装并会真正采集; 其余 5 路在 registry 标 None,
record 会跳过并打印 [✗待办], 不影响已实装的路。每路一线程, 互不阻塞;
样本到达即打 time.monotonic() 戳, 离线按最近邻对齐。

用法(采海康那两台):
  export LD_LIBRARY_PATH=$PWD/third_party/EN-HCNetSDKV6.1.9.4_build20220412_linux64/lib
  python3 acquire/record.py
"""
import os
import sys
import time
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402
from sensors.base import Sensor  # noqa: E402
from acquire.registry import resolve_driver  # noqa: E402


def load_rig(path=None):
    path = path or (ROOT / "config" / "rig.yaml")
    with open(path) as f:
        cfg = yaml.safe_load(f)
    return cfg.get("devices", []), cfg.get("host", {})


def main():
    devices, host = load_rig()
    run_dir = ROOT / "data" / datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"采集机: {host.get('ip', '?')}    本次输出: {run_dir}")
    print(f"rig 共 {len(devices)} 台设备:\n")

    runners = []
    for d in devices:
        name = d.get("name"); kind = d.get("kind"); model = d.get("model")
        enabled = d.get("enabled", True)
        drv = resolve_driver(kind, model)
        tag = "-禁用" if not enabled else ("✓实装" if drv else "✗待办")
        print(f"  [{tag}] {name:<26} kind={kind:<20} model={model}  ip={d.get('ip')}")

        if not enabled or not drv:
            continue
        try:
            out = run_dir / name
            out.mkdir(parents=True, exist_ok=True)
            s = drv(name, d)
            s.out_dir = str(out)
            runners.append(s)
        except Exception as e:
            print(f"    !! 实例化 {name} 失败: {e}")

    if not runners:
        print("\n(本轮没有「实装 + 启用」的传感器, 仅打印计划。)")
        return

    print(f"\n启动 {len(runners)} 路, Ctrl-C 停止 ...")
    threads = [threading.Thread(target=_loop, args=(s,), daemon=True) for s in runners]
    for t in threads:
        t.start()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n停止中 ...")


def _loop(sensor: Sensor, interval: float = 1.0):
    try:
        with sensor:
            while True:
                sample = sensor.grab()
                m = sample.meta
                print(f"  {sensor.name}: frame={m.get('frame')} "
                      f"{m.get('bytes', '-')}B  {m.get('latency_ms', '-')}ms  -> {sample.payload}")
                time.sleep(interval)
    except Exception as e:
        print(f"  {sensor.name} 采集异常: {e}")


if __name__ == "__main__":
    main()
