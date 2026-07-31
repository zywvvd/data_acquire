"""传感器统一接口与样本类型。

所有 sensors/<kind>/ 下的驱动实现 Sensor, acquire/ 通过本接口无差别采集各路数据,
与具体厂商解耦。加一种新传感器 = 在 sensors/<kind>/ 写一个 Sensor 子类 +
在 acquire/registry.py 登记一行。

两类驱动:
  · 进程内 poll 型(如 HikSensor): grab() 直接调底层拿一帧, 自己写文件。
  · 子进程型(SubprocessSensor): 启动外部已编译 C++ 二进制, 它边跑边往 out_dir
    写文件, grab() 增量扫描这些文件。LiDAR / 结构光走这条。
"""
import glob
import os
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class Sample:
    """一帧采集样本。"""
    sensor: str                         # 设备句柄(rig.yaml 里的 name)
    timestamp: float                    # time.monotonic() 秒 —— 同主机内单调时钟
    payload: Any = None                 # 刚落盘文件路径(str) 或内存数据(bytes/ndarray)
    meta: dict = field(default_factory=dict)  # 型号/帧号/分辨率/延迟 等


class Sensor(ABC):
    """配置驱动的采集器基类。registry 按 (kind, model) 实例化具体子类。

    生命周期: connect() → start() → 反复 grab() → stop() → close()
    recorder 在 start 前会注入 out_dir(每台设备一个独立输出目录)。

    结束约定: 设备无更多数据(流式到时 / 批量采完)时, grab() 返回
    Sample(payload=None, meta={"ended": True}), recorder 据此退出该路线程。
    """

    def __init__(self, name: str, spec: dict):
        self.name = name
        self.spec = spec                # rig.yaml 里这一台设备的整段配置
        self.out_dir: str = None        # 由 recorder 注入

    @abstractmethod
    def connect(self): ...
    @abstractmethod
    def start(self): ...
    @abstractmethod
    def grab(self) -> Sample: ...
    @abstractmethod
    def stop(self): ...

    def close(self):
        """可选资源释放, 默认等于 stop。"""
        self.stop()

    def __enter__(self):
        self.connect(); self.start(); return self

    def __exit__(self, *exc):
        self.close(); return False


class SubprocessSensor(Sensor):
    """跑外部已编译二进制、把产物文件落到 out_dir 的传感器基类。

    统一 LiDAR / 结构光那类「启动一个外部 C++ 进程、它边跑边往 out_dir 写文件」
    的取数模型, 与 HikSensor 那种进程内 poll 型并列。

    子类只需实现 5 个钩子:
        _binary()     -> str           可执行文件绝对路径(connect 时校验存在)
        _build_cmd()  -> list[str]     命令行(不含 env/cwd)
        _env()        -> dict          子进程环境(基于 os.environ, 注入 LD_LIBRARY_PATH / PCD_OUT ...)
        _duration()   -> float|None    流式采集时长(秒); 返回 None = 批量型
        _frame_glob() -> str           out_dir 内「一帧产物」的 glob(如 "*.pcd" / "points_*.pcd")

    两种取数模型(由 _duration() 是否为 None 自动区分):
      · 流式型(_duration 有值): start() 用 Popen 后台拉起; grab() 轮询 out_dir
        增量帧, 每次返回一帧; 到 _duration() 秒或 stop() 时 terminate。
        —— Hesai / RoboSense(在线流不自停)与 Livox(LIVOX_RUN_SECS 自停, Popen 等其退出)。
      · 批量型(_duration 为 None): grab() 首次调用时 subprocess.run 同步把子进程
        跑完(子类用 -n / 帧数参数控制), 之后逐帧返回产物; 产物耗尽返回 ended。
        —— Percipio(采 N 帧自停)。
    """

    #: 候选产物「最后修改距今」至少多少秒才算写完(规避子进程正在写半个文件的竞态)。
    _STABLE_SECS = 0.2

    def __init__(self, name: str, spec: dict):
        super().__init__(name, spec)
        self._proc = None
        self._seen = set()        # 已 yield 给上层的产物绝对路径
        self._frame = 0
        self._t0 = 0.0
        self._batch_done = False  # 批量型: 子进程是否已 run 完
        self._streaming = self._duration() is not None

    # ---------------- 子类钩子 ----------------
    def _binary(self) -> str:
        raise NotImplementedError

    def _build_cmd(self) -> list:
        raise NotImplementedError

    def _env(self) -> dict:
        return dict(os.environ)

    def _duration(self) -> Optional[float]:
        return self.spec.get("duration", 10.0)

    def _frame_glob(self) -> str:
        return "*"

    def _build_hint(self) -> str:
        """二进制缺失时的编译提示(子类覆盖以给出具体命令)。"""
        return f"找不到二进制: {self._binary()}"

    def _batch_timeout(self) -> float:
        """批量型单次 run 的超时(子类可覆盖)。"""
        return 120.0

    # ---------------- 生命周期 ----------------
    def connect(self):
        b = self._binary()
        if not os.path.exists(b):
            raise RuntimeError(self._build_hint())
        os.makedirs(self.out_dir, exist_ok=True)

    def start(self):
        if not self._streaming:
            return  # 批量型: 不预启动, 留到 grab() 同步 run
        self._t0 = time.monotonic()
        self._proc = subprocess.Popen(
            self._build_cmd(), env=self._env(), cwd=self.out_dir,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    # ---------------- 帧扫描 ----------------
    def _scan_new(self, stable: bool = True) -> List[str]:
        """out_dir 下匹配 _frame_glob、尚未 yield 的产物, 按文件名排序。

        stable=True 时只返回「最后修改距今 ≥ _STABLE_SECS」的文件 —— 用于子进程仍在写时的
        防半文件竞态。stable=False 时跳过该过滤 —— 仅在确认子进程已退出(批量 run 完 / 流式
        自停 / stop)后调用: 此时所有产物都已写完, 不过滤可避免漏掉刚落盘的最后几帧。
        """
        now = time.time() if stable else 0  # mtime 比较只在 stable 时需要
        out = []
        for p in sorted(glob.glob(os.path.join(self.out_dir, self._frame_glob()))):
            if p in self._seen:
                continue
            if stable:
                try:
                    if now - os.path.getmtime(p) < self._STABLE_SECS:
                        continue  # 正在写, 本轮跳过
                except OSError:
                    continue
            out.append(p)
        return out

    def _yield(self, path: str) -> Sample:
        self._seen.add(path)
        self._frame += 1
        return Sample(
            sensor=self.name, timestamp=time.monotonic(), payload=path,
            meta={"frame": self._frame,
                  "bytes": os.path.getsize(path) if os.path.exists(path) else 0,
                  "model": self.spec.get("model")})

    def _ended(self) -> Sample:
        return Sample(sensor=self.name, timestamp=time.monotonic(), payload=None,
                      meta={"ended": True, "frame": self._frame})

    def grab(self) -> Sample:
        # 子进程是否仍在运行(批量型 _proc 恒为 None → 视作已退出)
        alive = self._proc is not None and self._proc.poll() is None

        # 1) 先消费已积压且写完的帧(批量已 run 完 / 流式积压)
        new = self._scan_new(stable=alive)
        if new:
            return self._yield(new[0])

        # 2) 批量型: 首次同步把子进程跑完, 之后逐帧返回产物; 跑完用无过滤终扫
        if not self._streaming:
            if not self._batch_done:
                self._run_batch()
                self._batch_done = True
                new = self._scan_new(stable=False)   # 进程已退出, 产物完整
                if new:
                    return self._yield(new[0])
            return self._ended()  # 批量: 跑完仍无帧 / 帧耗尽

        # 3) 流式型: 阻塞等下一帧; 到 _duration() 或子进程自停则退出循环后做无过滤终扫
        deadline = self._t0 + self._duration()
        while True:
            alive = self._proc is not None and self._proc.poll() is None
            new = self._scan_new(stable=alive)
            if new:
                return self._yield(new[0])
            if not alive:
                break  # 子进程自停(如 Livox 到 LIVOX_RUN_SECS)
            if time.monotonic() >= deadline:
                self._stop_proc()
                break
            time.sleep(0.05)

        # 终扫: 进程已停, 所有产物都已写完, 不再过滤 mtime(否则会漏掉刚落盘的最后几帧)
        new = self._scan_new(stable=False)
        if new:
            return self._yield(new[0])
        return self._ended()

    def _run_batch(self):
        """批量型: 同步把子进程跑完(子类用参数控制帧数)。"""
        try:
            subprocess.run(
                self._build_cmd(), env=self._env(), cwd=self.out_dir,
                timeout=self._batch_timeout(), check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except subprocess.TimeoutExpired:
            pass

    def _stop_proc(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    def stop(self):
        self._stop_proc()

    def close(self):
        """子进程型: 先终止子进程(让其 stderr 到 EOF), 再把残余 stderr 落到 sensor.log。

        必须先 _stop_proc 再读 stderr: 流式 LiDAR 的子进程(禾赛 sample_pcd / 速腾 rs_driver)
        不会自停, 若先 self._proc.stderr.read() 会一直阻塞到子进程自然退出(永不)——该路线程卡死,
        record 主循环等不到线程结束而挂到兜底 deadline, 且子进程持续写文件污染本次 run。
        """
        proc = self._proc
        self._stop_proc()                       # 先 terminate/kill → 子进程退出 → stderr 到 EOF
        if proc is not None and getattr(proc, "stderr", None) is not None:
            try:
                err = proc.stderr.read() if proc.stderr else b""   # 子进程已退出, read 不再阻塞
                if err:
                    with open(os.path.join(self.out_dir, "sensor.log"), "wb") as f:
                        f.write(err)
            except Exception:
                pass


def capture_once(sensor: Sensor, max_frames: int = None, verbose: bool = True) -> int:
    """同步跑单个 sensor 直到自然结束(ended)或达到 max_frames, 返回采集帧数。

    单设备 demo 的共用入口: connect + start → 反复 grab → stop。
    poll 型(相机)必须给 max_frames(否则永不 ended); 流式/批量型靠 ended 自然停。
    """
    n = 0
    with sensor:
        while True:
            if max_frames is not None and n >= max_frames:
                break
            sample = sensor.grab()
            if sample.meta.get("ended"):
                break
            n += 1
            if verbose:
                m = sample.meta
                base = os.path.basename(str(sample.payload)) if sample.payload else "-"
                print(f"  #{m.get('frame', '-')} {m.get('bytes', '-')}B -> {base}")
    return n
