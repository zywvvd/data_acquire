#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""海康 HCNetSDK 抓图封装（可复用模块）。

在 grab_via_sdk.py 的单张 demo 基础上，把 SDK 加载 / 登录 / 抓图 / 登出 / 清理
封装成 HikGrabber，支持「登录一次、连拍多张」，供批量采集脚本调用。

运行前需让动态链接器找到 SDK 依赖：
    export LD_LIBRARY_PATH=<sdk>/lib
"""
import ctypes
import os
import time

SDK_LIB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "third_party", "EN-HCNetSDKV6.1.9.4_build20220412_linux64", "lib")

# 默认连接参数（与 grab_via_sdk.py 保持一致）
DEFAULT_HOST = "192.168.2.2"
DEFAULT_PORT = 8000
DEFAULT_USER = "admin"
DEFAULT_PWD = "b@light2."

CHANNEL = 1        # 设备逻辑通道号（IP 相机一般从 1 起；注意与 RTSP 的 101 区分）
PIC_SIZE = 0xff    # 0xff = 使用当前码流分辨率
PIC_QUALITY = 0    # 0 最好 / 1 较好 / 2 一般


# ---------- 结构体 ----------
class _NET_DVR_LOCAL_SDK_PATH(ctypes.Structure):
    _fields_ = [("sPath", ctypes.c_char * 256), ("byRes", ctypes.c_ubyte * 128)]


class _NET_DVR_USER_LOGIN_INFO(ctypes.Structure):
    _fields_ = [
        ("sDeviceAddress", ctypes.c_char * 129),
        ("byUseTransport", ctypes.c_ubyte),
        ("wPort", ctypes.c_uint16),
        ("sUserName", ctypes.c_char * 64),
        ("sPassword", ctypes.c_char * 64),
        ("cbLoginResult", ctypes.c_void_p),
        ("pUser", ctypes.c_void_p),
        ("bUseAsynLogin", ctypes.c_uint32),
        ("byProxyType", ctypes.c_ubyte),
        ("byUseUTCTime", ctypes.c_ubyte),
        ("byLoginMode", ctypes.c_ubyte),
        ("byHttps", ctypes.c_ubyte),
        ("iProxyID", ctypes.c_int32),
        ("byVerifyMode", ctypes.c_ubyte),
        ("byRes3", ctypes.c_ubyte * 119),
    ]


class _NET_DVR_JPEGPARA(ctypes.Structure):
    _fields_ = [("wPicSize", ctypes.c_uint16), ("wPicQuality", ctypes.c_uint16)]


class HikGrabber:
    """海康相机抓图器：登录一次，可连续抓多张 JPEG。

    典型用法::

        with HikGrabber(host="192.168.2.2") as g:
            g.capture("a.jpg")
            g.capture("b.jpg")
    """

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, user=DEFAULT_USER,
                 pwd=DEFAULT_PWD, channel=CHANNEL, pic_size=PIC_SIZE,
                 pic_quality=PIC_QUALITY, lib_dir=SDK_LIB_DIR):
        self._channel = channel
        self._pic_size = pic_size
        self._pic_quality = pic_quality
        self._lib_dir = lib_dir
        self._uid = -1
        self._sdk = None

        self._load(lib_dir)
        self._proto()
        self._set_sdk_paths()
        if not self._sdk.NET_DVR_Init():
            self._raise_err("NET_DVR_Init 失败")
        self._sdk.NET_DVR_SetConnectTime(5000, 3)
        self._login(host, port, user, pwd)

    # ---------- 内部 ----------
    def _load(self, lib_dir):
        self._sdk = ctypes.CDLL(os.path.join(lib_dir, "libhcnetsdk.so"))

    def _proto(self):
        s = self._sdk
        s.NET_DVR_Init.restype = ctypes.c_bool
        s.NET_DVR_SetConnectTime.restype = ctypes.c_bool
        s.NET_DVR_SetSDKInitCfg.restype = ctypes.c_bool
        s.NET_DVR_Login_V40.restype = ctypes.c_long
        s.NET_DVR_Login_V40.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        s.NET_DVR_Logout.restype = ctypes.c_bool
        s.NET_DVR_Logout.argtypes = [ctypes.c_long]
        s.NET_DVR_CaptureJPEGPicture.restype = ctypes.c_bool
        s.NET_DVR_CaptureJPEGPicture.argtypes = [
            ctypes.c_long, ctypes.c_long, ctypes.c_void_p, ctypes.c_char_p]
        s.NET_DVR_GetLastError.restype = ctypes.c_uint32
        s.NET_DVR_Cleanup.restype = ctypes.c_bool

    def _set_sdk_paths(self):
        """告诉 SDK 组件库(HCNetSDKCom)与加解密库(libcrypto/libssl)所在路径。"""
        d = self._lib_dir
        p = _NET_DVR_LOCAL_SDK_PATH(); p.sPath = d.encode()
        self._sdk.NET_DVR_SetSDKInitCfg(2, ctypes.byref(p))          # NET_SDK_INIT_CFG_SDK_PATH
        pe = _NET_DVR_LOCAL_SDK_PATH(); pe.sPath = os.path.join(d, "libcrypto.so.1.1").encode()
        self._sdk.NET_DVR_SetSDKInitCfg(3, ctypes.byref(pe))         # LIBEAY_PATH
        ps = _NET_DVR_LOCAL_SDK_PATH(); ps.sPath = os.path.join(d, "libssl.so.1.1").encode()
        self._sdk.NET_DVR_SetSDKInitCfg(4, ctypes.byref(ps))         # SSLEAY_PATH

    def _login(self, host, port, user, pwd):
        info = _NET_DVR_USER_LOGIN_INFO()
        info.sDeviceAddress = host.encode()
        info.wPort = port
        info.sUserName = user.encode()
        info.sPassword = pwd.encode()
        info.byLoginMode = 0    # 0-Private(8000 私有协议)
        info.byHttps = 0
        devbuf = ctypes.create_string_buffer(4096)   # NET_DVR_DEVICEINFO_V40，仅接收不解析
        uid = self._sdk.NET_DVR_Login_V40(ctypes.byref(info), devbuf)
        if uid < 0:
            self._sdk.NET_DVR_Cleanup()
            self._raise_err("登录失败")
        self._uid = uid

    def _raise_err(self, msg):
        raise RuntimeError(
            f"{msg}  (NET_DVR_GetLastError={self._sdk.NET_DVR_GetLastError()})")

    # ---------- 对外 ----------
    def capture(self, out_path) -> float:
        """抓一张 JPEG 到 out_path，返回耗时(ms)。失败抛 RuntimeError。"""
        jpg = _NET_DVR_JPEGPARA()
        jpg.wPicSize = self._pic_size
        jpg.wPicQuality = self._pic_quality
        t0 = time.monotonic()
        ok = self._sdk.NET_DVR_CaptureJPEGPicture(
            self._uid, self._channel, ctypes.byref(jpg), str(out_path).encode())
        dt = (time.monotonic() - t0) * 1000
        if not ok:
            self._raise_err("抓图失败")
        return dt

    def close(self):
        if self._uid >= 0:
            self._sdk.NET_DVR_Logout(self._uid)
            self._uid = -1
        self._sdk.NET_DVR_Cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
