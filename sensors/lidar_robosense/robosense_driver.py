#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""速腾 RoboSense RSAIRY(.202 / .205) → Sensor 接口适配(子进程型, 流式)。

跑 rs_driver 的 rs_driver_pcdsaver(免 ROS: rslidar_sdk 顶层 node 需 ROS 编不过, 只编 src/rs_driver;
老代码加 -DCMAKE_CXX_FLAGS="-include memory" 适配 GCC11)。按帧把 PCD 写到 cwd(= out_dir)。
在线流不自停, 到 duration 由基类 terminate。

型号必须对: .202/.205 实测 RSAIRY(bolight_alg 生产配置亦此); 若硬件实为 RS-Fairy, 在 rig.yaml
把 model 改 RSFAIRY(同包不同垂直角表, z 可达 26m)。换别的速腾雷达务必重核 model。

底层 SDK 调用流程(Python 如何封装):
  SubprocessSensor(子进程型): Popen(cwd=out_dir) 拉起 rs_driver_pcdsaver —— rslidar_sdk 上游原样
  工具(无源码改动)。其内部链路(见 rs_driver/tool/rs_driver_pcdsaver.cpp):
    parseParam(-type/-msop/-difop/-host) → regPointCloudCallback(getCb 入 free_queue / putCb 入
    stuffed_queue) → init+start → [SDK 线程收 UDP(MSOP 6692/6695) → 按 -type 选垂直角表解包
    → 组装 PointCloudMsg 入队] → 工作线程出队写 %d.pcd 到 cwd。
  Python 侧只做编排: 命令行由 spec 的 rs_type/msop_port/difop_port/host_ip 拼装; cwd=out_dir 使 PCD
  直接落采集目录(无需 PCD_OUT 环境变量); grab() 增量扫描新 PCD; 到 duration 基类 terminate(在线流
  不自停)。文件系统即跨进程「帧队列」。
  关键约束: -type 必须与硬件一致(RSAIRY/RSFAIRY 同包不同角表), 否则出平面垃圾点或 WRONGMSOPBLKID。
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)

from sensors.base import SubprocessSensor  # noqa: E402

BINARY = os.path.join(_ROOT, "third_party", "rslidar_sdk-v1.5.20", "src", "rs_driver",
                      "build_rs", "tool", "rs_driver_pcdsaver")


class RobosenseSensor(SubprocessSensor):
    """单台速腾 LiDAR: 后台跑 rs_driver_pcdsaver, PCD 写到 out_dir(=cwd)。"""

    def _binary(self):
        return BINARY

    def _build_hint(self):
        return (f"找不到 rs_driver_pcdsaver: {BINARY}\n"
                "请编译: cd third_party/rslidar_sdk-v1.5.20/src/rs_driver && mkdir -p build_rs && "
                "cd build_rs && cmake -DCOMPILE_DEMOS=ON -DCOMPILE_TOOL_PCDSAVER=ON "
                "-DCMAKE_CXX_FLAGS='-include memory' .. && make rs_driver_pcdsaver -j")

    def _build_cmd(self):
        s = self.spec
        return [
            BINARY,
            "-type", str(s.get("rs_type", s.get("model", "RSAIRY"))),
            "-msop", str(s.get("msop_port", 6692)),
            "-difop", str(s.get("difop_port", 7782)),
            "-host", str(s.get("host_ip", "192.168.1.200")),
        ]

    def _duration(self):
        return self.spec.get("duration", 10.0)

    def _frame_glob(self):
        return "*.pcd"
