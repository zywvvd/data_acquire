#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图漾 Percipio FM815-IX-E1(.114) → Sensor 接口适配(子进程型, 批量)。

跑 camport4 自编的 SimpleView_CaptureDump(无头, 不依赖 GUI/OpenGL): 每帧落
depth(16bit PNG, mm) + color(JPG) + 点云(ASCII PCD, 米, rgb)。采完 N 帧子进程自停 → 批量型:
基类 grab() 首次调用时同步 run 完, 之后逐帧返回 points_%04d.pcd(同帧 depth/color 同编号)。
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)

from sensors.base import SubprocessSensor  # noqa: E402

BINARY = os.path.join(_ROOT, "third_party", "camport4", "sample", "build", "bin",
                      "SimpleView_CaptureDump")
LIBDIR = os.path.join(_ROOT, "third_party", "camport4", "lib", "linux", "lib_x64")


class PercipioSensor(SubprocessSensor):
    """单台图漾结构光: 同步跑 SimpleView_CaptureDump 取 N 帧, 每帧 depth+color+points。"""

    def _binary(self):
        return BINARY

    def _build_hint(self):
        return (f"找不到 SimpleView_CaptureDump: {BINARY}\n"
                "请编译: cd third_party/camport4/sample/build && cmake .. "
                "-DTYCam_DIR=$PWD/../../.. -DARCH=x64 -DBUILD_SAMPLE_V2=OFF "
                "-DBUILD_SAMPLE_GENICAM_SFNC=OFF && make SimpleView_CaptureDump -j")

    def _build_cmd(self):
        s = self.spec
        cmd = [BINARY,
               "-ip", str(s.get("ip", "192.168.1.114")),
               "-n", str(s.get("frames", 6)),
               "-outdir", os.path.abspath(self.out_dir)]
        if s.get("no_align"):
            cmd.append("-noalign")
        return cmd

    def _env(self):
        env = dict(os.environ)
        env["LD_LIBRARY_PATH"] = LIBDIR + ":" + env.get("LD_LIBRARY_PATH", "")
        return env

    def _duration(self):
        return None  # 批量型: 采 N 帧自停

    def _frame_glob(self):
        return "points_*.pcd"   # 以点云为帧索引; 同帧 depth_xxxx.png / color_xxxx.jpg 同编号

    def _batch_timeout(self):
        return float(self.spec.get("frames", 6)) * 8 + 15
