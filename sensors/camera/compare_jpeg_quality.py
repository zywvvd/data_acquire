#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同场景下对比 ISAPI 抓图与 SDK 各 wPicQuality 档(0/1/2) 的 JPEG 体积。

一次登录连抓四张，消除场景/曝光随时间漂移的干扰，孤立"质量档"这一个变量。
"""
import ctypes
import os
import requests
from requests.auth import HTTPDigestAuth

SDK_LIB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "third_party", "EN-HCNetSDKV6.1.9.4_build20220412_linux64", "lib")
HOST, USER, PWD = "192.168.2.2", "admin", "b@light2."


# ---- ISAPI ----
def grab_isapi(out):
    url = f"http://{HOST}/ISAPI/Streaming/channels/101/picture"
    r = requests.get(url, auth=HTTPDigestAuth(USER, PWD), timeout=10)
    with open(out, "wb") as f:
        f.write(r.content)
    return os.path.getsize(out)


# ---- SDK (ctypes) ----
sdk = ctypes.CDLL(os.path.join(SDK_LIB_DIR, "libhcnetsdk.so"))


class SDK_PATH(ctypes.Structure):
    _fields_ = [("sPath", ctypes.c_char * 256), ("byRes", ctypes.c_ubyte * 128)]


class NET_DVR_USER_LOGIN_INFO(ctypes.Structure):
    _fields_ = [
        ("sDeviceAddress", ctypes.c_char * 129), ("byUseTransport", ctypes.c_ubyte),
        ("wPort", ctypes.c_uint16),
        ("sUserName", ctypes.c_char * 64), ("sPassword", ctypes.c_char * 64),
        ("cbLoginResult", ctypes.c_void_p), ("pUser", ctypes.c_void_p),
        ("bUseAsynLogin", ctypes.c_uint32),
        ("byProxyType", ctypes.c_ubyte), ("byUseUTCTime", ctypes.c_ubyte),
        ("byLoginMode", ctypes.c_ubyte), ("byHttps", ctypes.c_ubyte),
        ("iProxyID", ctypes.c_int32), ("byVerifyMode", ctypes.c_ubyte),
        ("byRes3", ctypes.c_ubyte * 119),
    ]


class NET_DVR_JPEGPARA(ctypes.Structure):
    _fields_ = [("wPicSize", ctypes.c_uint16), ("wPicQuality", ctypes.c_uint16)]


def err(m):
    print(f"{m}  (err={sdk.NET_DVR_GetLastError()})")


def main():
    for t, lib in [(2, SDK_LIB_DIR),
                   (3, os.path.join(SDK_LIB_DIR, "libcrypto.so.1.1")),
                   (4, os.path.join(SDK_LIB_DIR, "libssl.so.1.1"))]:
        p = SDK_PATH(); p.sPath = lib.encode()
        sdk.NET_DVR_SetSDKInitCfg(t, ctypes.byref(p))
    if not sdk.NET_DVR_Init():
        err("Init"); return
    sdk.NET_DVR_SetConnectTime(5000, 3)

    info = NET_DVR_USER_LOGIN_INFO()
    info.sDeviceAddress = HOST.encode(); info.wPort = 8000
    info.sUserName = USER.encode(); info.sPassword = PWD.encode()
    info.byLoginMode = 0
    devbuf = ctypes.create_string_buffer(4096)
    uid = sdk.NET_DVR_Login_V40(ctypes.byref(info), devbuf)
    if uid < 0:
        err("登录失败"); sdk.NET_DVR_Cleanup(); return

    # 一次登录内连抓 q0/q1/q2，场景基本不变
    jpg = NET_DVR_JPEGPARA()
    jpg.wPicSize = 0xff
    for q in (0, 1, 2):
        jpg.wPicQuality = q
        out = f"cmp_sdk_q{q}.jpg"
        ok = sdk.NET_DVR_CaptureJPEGPicture(uid, 1, ctypes.byref(jpg), out.encode())
        print(f"SDK wPicQuality={q}: {'OK ' + str(os.path.getsize(out)) + ' B' if ok else '失败'}")

    sdk.NET_DVR_Logout(uid)
    sdk.NET_DVR_Cleanup()

    # ISAPI 抓一张
    print(f"ISAPI /picture : {grab_isapi('cmp_isapi.jpg')} B")


if __name__ == "__main__":
    main()
