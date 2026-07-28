#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Livox HAP(.100) → Sensor 接口适配(子进程型, 流式限时自停)。

跑 Livox-SDK2 的 livox_lidar_pcd_saver(GCC11 直接过; HAP/Mid-360 必须用 SDK2, 不是老 v1)。
SDK **主动查询式**发现雷达、置 Normal(故静态嗅探看不到流量属正常), 按每 50000 点切一帧
写 ASCII PCD(xyz 米 + intensity)。限时自停: 环境变量 LIVOX_RUN_SECS 到点子进程自己退出。

按 spec.model 选配置模板: HAP → hap_host200.json; Mid-360 → mid360_host200.json;
并把 host_net_info.host_ip 渲染成采集机 IP(spec.host_ip, 换采集机时随 spec 生效)。

底层 SDK 调用流程(Python 如何封装):
  SubprocessSensor(子进程型, 限时自停): Popen 拉起 livox_lidar_pcd_saver。SDK2 属「主动查询式」
  (与禾赛/速腾的被动推流相反), 其内部链路(见 livox_lidar_pcd_saver/main.cpp):
    LivoxLidarSdkInit(json) → SetLivoxLidarPointCloudCallBack + SetLivoxLidarInfoChangeCallback
    → [SDK 广播发现 → 雷达应答 → LidarInfoChangeCallback 置 Normal(雷达才开始推点)
    → PointCloudCallback: 取 LivoxLidarCartesianHighRawPoint(int32 xyz mm) /1000 转米,
    每 50000 点写一帧 %05d.pcd] → sleep(LIVOX_RUN_SECS) → FlushFrame → Uninit。
  Python 侧只做编排: _cfg_path 按 spec.model 选模板(hap/mid360)并渲染 host_ip 写 device.json;
  _env 注入 LD_LIBRARY_PATH(动态链)+ PCD_OUT + LIVOX_RUN_SECS(限时自停, 唯一自己退出的设备);
  grab() 增量扫描新 pcd。
  关键: HAP frame_cnt 实测恒 0 → 改按点数切帧; 静态嗅探无流量是正常的(必须跑 SDK 才有数据)。
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)

from sensors.base import SubprocessSensor  # noqa: E402

BINARY = os.path.join(_ROOT, "third_party", "Livox-SDK2", "build", "samples",
                      "livox_lidar_pcd_saver", "livox_lidar_pcd_saver")
LIBDIR = os.path.join(_ROOT, "third_party", "Livox-SDK2", "build", "sdk_core")


class LivoxSensor(SubprocessSensor):
    """单台 Livox LiDAR: 后台跑 livox_lidar_pcd_saver, 限时自停, PCD 写 out_dir。"""

    def _binary(self):
        return BINARY

    def _build_hint(self):
        return (f"找不到 livox_lidar_pcd_saver: {BINARY}\n"
                "请编译: cd third_party/Livox-SDK2/build && cmake .. && "
                "make livox_lidar_pcd_saver -j")

    def _cfg_path(self):
        s = self.spec
        host_ip = str(s.get("host_ip", "192.168.1.200"))
        model = str(s.get("model", "")).lower()
        tmpl = os.path.join(_HERE, "mid360_host200.json" if "mid" in model else "hap_host200.json")
        if not os.path.exists(tmpl):  # 兜底
            tmpl = os.path.join(_HERE, "hap_host200.json")
        with open(tmpl) as f:
            cfg = json.load(f)
        for _dev, body in cfg.items():           # 把所有 host_net_info[].host_ip 改成采集机 IP
            for h in body.get("host_net_info", []):
                h["host_ip"] = host_ip
        path = os.path.join(self.out_dir, "device.json")
        with open(path, "w") as f:
            json.dump(cfg, f, indent=2)
        return path

    def _build_cmd(self):
        return [BINARY, self._cfg_path()]

    def _env(self):
        env = dict(os.environ)
        env["LD_LIBRARY_PATH"] = LIBDIR + ":" + env.get("LD_LIBRARY_PATH", "")
        env["PCD_OUT"] = os.path.abspath(self.out_dir)
        env["LIVOX_RUN_SECS"] = str(int(self._duration()))
        return env

    def _duration(self):
        return self.spec.get("duration", 15.0)

    def _frame_glob(self):
        return "*.pcd"
