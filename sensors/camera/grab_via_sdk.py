#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过 HCNetSDK (libhcnetsdk.so) 抓取单张 JPEG（设备端编码）。

对应文档《海康相机取图方式总览.md》「SDK 层」。
运行前必须让动态链接器找得到 SDK 依赖库：
    export LD_LIBRARY_PATH=<sdk>/lib
"""
import ctypes
import os
import sys
import time

SDK_LIB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "third_party", "EN-HCNetSDKV6.1.9.4_build20220412_linux64", "lib")

HOST = "192.168.2.2"
PORT = 8000
USER = "admin"
PWD = "b@light2."
CHANNEL = 1        # 设备逻辑通道号（IP 相机一般从 1 起；注意与 RTSP 的 101 区分）
PIC_SIZE = 0xff    # 0xff = 使用当前码流分辨率
PIC_QUALITY = 0    # 0 最好 / 1 较好 / 2 一般
OUT = "sdk_test.jpg"

# ---------- 加载 SDK ----------
HCNetSDK = ctypes.CDLL(os.path.join(SDK_LIB_DIR, "libhcnetsdk.so"))


# ---------- 函数原型 ----------
def _proto():
    HCNetSDK.NET_DVR_Init.restype = ctypes.c_bool
    HCNetSDK.NET_DVR_SetConnectTime.restype = ctypes.c_bool
    HCNetSDK.NET_DVR_SetSDKInitCfg.restype = ctypes.c_bool
    HCNetSDK.NET_DVR_Login_V40.restype = ctypes.c_long
    HCNetSDK.NET_DVR_Login_V40.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    HCNetSDK.NET_DVR_Logout.restype = ctypes.c_bool
    HCNetSDK.NET_DVR_Logout.argtypes = [ctypes.c_long]
    HCNetSDK.NET_DVR_CaptureJPEGPicture.restype = ctypes.c_bool
    HCNetSDK.NET_DVR_CaptureJPEGPicture.argtypes = [
        ctypes.c_long, ctypes.c_long, ctypes.c_void_p, ctypes.c_char_p]
    HCNetSDK.NET_DVR_GetLastError.restype = ctypes.c_uint32
    HCNetSDK.NET_DVR_Cleanup.restype = ctypes.c_bool


# ---------- 结构体 ----------
class NET_DVR_LOCAL_SDK_PATH(ctypes.Structure):
    _fields_ = [("sPath", ctypes.c_char * 256), ("byRes", ctypes.c_ubyte * 128)]


class NET_DVR_USER_LOGIN_INFO(ctypes.Structure):
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


class NET_DVR_JPEGPARA(ctypes.Structure):
    _fields_ = [("wPicSize", ctypes.c_uint16), ("wPicQuality", ctypes.c_uint16)]


def err(msg):
    print(f"{msg}  (NET_DVR_GetLastError={HCNetSDK.NET_DVR_GetLastError()})")


def set_sdk_paths():
    """告诉 SDK 组件库(HCNetSDKCom)与加解密库(libcrypto/libssl)所在路径。"""
    p = NET_DVR_LOCAL_SDK_PATH(); p.sPath = SDK_LIB_DIR.encode()
    HCNetSDK.NET_DVR_SetSDKInitCfg(2, ctypes.byref(p))          # NET_SDK_INIT_CFG_SDK_PATH
    pe = NET_DVR_LOCAL_SDK_PATH(); pe.sPath = os.path.join(SDK_LIB_DIR, "libcrypto.so.1.1").encode()
    HCNetSDK.NET_DVR_SetSDKInitCfg(3, ctypes.byref(pe))         # LIBEAY_PATH
    ps = NET_DVR_LOCAL_SDK_PATH(); ps.sPath = os.path.join(SDK_LIB_DIR, "libssl.so.1.1").encode()
    HCNetSDK.NET_DVR_SetSDKInitCfg(4, ctypes.byref(ps))         # SSLEAY_PATH


def main():
    _proto()
    if not os.environ.get("LD_LIBRARY_PATH"):
        print("警告：未设置 LD_LIBRARY_PATH，依赖库可能加载失败")

    set_sdk_paths()

    if not HCNetSDK.NET_DVR_Init():
        err("NET_DVR_Init 失败"); sys.exit(1)
    HCNetSDK.NET_DVR_SetConnectTime(5000, 3)

    # ---- 登录 ----
    info = NET_DVR_USER_LOGIN_INFO()
    info.sDeviceAddress = HOST.encode()
    info.wPort = PORT
    info.sUserName = USER.encode()
    info.sPassword = PWD.encode()
    info.byLoginMode = 0    # 0-Private(8000 私有协议)
    info.byHttps = 0
    devbuf = ctypes.create_string_buffer(4096)   # NET_DVR_DEVICEINFO_V40，仅接收不解析
    uid = HCNetSDK.NET_DVR_Login_V40(ctypes.byref(info), devbuf)
    if uid < 0:
        err("登录失败"); HCNetSDK.NET_DVR_Cleanup(); sys.exit(1)
    print(f"登录成功  userID={uid}")

    # ---- 抓图 ----
    jpg = NET_DVR_JPEGPARA()
    jpg.wPicSize = PIC_SIZE
    jpg.wPicQuality = PIC_QUALITY
    t0 = time.monotonic()
    ok = HCNetSDK.NET_DVR_CaptureJPEGPicture(uid, CHANNEL, ctypes.byref(jpg), OUT.encode())
    dt = (time.monotonic() - t0) * 1000
    if not ok:
        err("抓图失败"); HCNetSDK.NET_DVR_Logout(uid); HCNetSDK.NET_DVR_Cleanup(); sys.exit(1)
    print(f"抓图成功  -> {OUT}  {os.path.getsize(OUT)} bytes   {dt:.0f} ms")

    HCNetSDK.NET_DVR_Logout(uid)
    HCNetSDK.NET_DVR_Cleanup()


if __name__ == "__main__":
    main()
