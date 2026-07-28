#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""禾赛 QT128 @ 192.168.1.201 → Sensor 接口适配(子进程型, 流式)。

跑已编译的 HesaiLidar_SDK_2.0/**sample_pcd**(免 pcap / PCL / ROS): 在线 UDP 解析 + 回调
直写 ASCII PCD(规避 Ubuntu22.04 VTK/PCL/libtiff 链接冲突)。输出目录由环境变量 PCD_OUT 注入。

⚠️ 用的是仓库自编的 **sample_pcd**(产 PCD), 不是 SDK 自带只打印统计的 sample。
本驱动按 rig.yaml 的 spec 渲染 device.ini(device_ip / udp_port / ptc_port), 写到 out_dir/device.ini。

依赖: 无额外 LD_LIBRARY_PATH(sample_pcd 静态链了所需库); 在线流不自停, 到 duration 由基类 terminate。

底层 SDK 调用流程(Python 如何封装):
  本驱动是 SubprocessSensor(子进程型)—— 不在 Python 里解码雷达私有包, 而是拉起已编译的 C++
  sample_pcd。其内部链路(见 test/test_pcd.cc):
    LoadIniMap→ApplyToDriverParam → HesaiLidarSdk.Init → RegRecvCallback(lidarCallback)
    → Start → [SDK 线程: 收 UDP(MSOP 2364) → 按包内角度表解包成 x y z intensity ring
    → 每帧回调 lidarCallback 直写 ASCII PCD 到 $PCD_OUT] → Stop。
  Python 侧只做编排: Popen 起进程 + 注入 PCD_OUT=out_dir; grab() 增量扫描 out_dir 的新
  frame_%06d.pcd 逐帧返回 Sample(payload=路径)。文件系统即「帧队列」的跨进程缝合点。
  对照: 海康是进程内 ctypes 同步直调; 这里因包解码器是数千行厂商 C++ 且已稳定, 选「跑二进制
  + 监视目录」比纯 Python/ctypes 移植更稳、更省事。
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)

from sensors.base import SubprocessSensor  # noqa: E402

BINARY = os.path.join(_ROOT, "third_party", "HesaiLidar_SDK_2.0", "build", "sample_pcd")

_INI_TMPL = """\
# 由 hesai_driver.py 按 rig.yaml spec 渲染 —— 在线 UDP 取数配置。
[source_type]
source_type = network

[network]
device_ip_address = {device_ip}
ptc_port = {ptc_port}
udp_port = {udp_port}
multicast_ip_address =
use_ptc_connected = true
correction_file_path =
firetimes_path =
host_ip_address =
fault_message_port = 0
ptc_mode = tcp

[driver]
use_gpu = false

[decoder]
socket_buffer_size = 262144000
enable_packet_loss_tool = false
"""


class HesaiSensor(SubprocessSensor):
    """单台禾赛 LiDAR: 后台跑 sample_pcd, 每帧产 frame_%06d.pcd 到 out_dir。"""

    def _binary(self):
        return BINARY

    def _build_hint(self):
        return (f"找不到 sample_pcd: {BINARY}\n"
                "请编译: cd third_party/HesaiLidar_SDK_2.0 && mkdir -p build && cd build && "
                "cmake .. && make sample_pcd -j")

    def _ini_path(self):
        s = self.spec
        text = _INI_TMPL.format(
            device_ip=s.get("ip", "192.168.1.201"),
            ptc_port=s.get("ptc_port", 9347),
            udp_port=s.get("data_port", 2364),
        )
        path = os.path.join(self.out_dir, "device.ini")
        with open(path, "w") as f:
            f.write(text)
        return path

    def _build_cmd(self):
        return [BINARY, self._ini_path()]

    def _env(self):
        env = dict(os.environ)
        env["PCD_OUT"] = os.path.abspath(self.out_dir)
        return env

    def _duration(self):
        return self.spec.get("duration", 10.0)

    def _frame_glob(self):
        return "*.pcd"
