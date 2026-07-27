#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过 ISAPI HTTP 接口抓取单张 JPEG（设备端编码）。

对应文档《海康相机取图方式总览.md》「HTTP 层」。
无需 SDK，仅依赖 requests。认证用 HTTP Digest。
"""
import sys
import time
import requests
from requests.auth import HTTPDigestAuth

HOST = "192.168.2.2"
USER = "admin"
PWD = "b@light2."


def jpeg_size(data):
    """纯 Python 解析 JPEG SOF 段，返回 (width, height)，失败返回 (None, None)。"""
    i = 2  # 跳过 SOI(FF D8)
    while i + 9 < len(data):
        if data[i] != 0xFF:
            return None, None
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):  # SOF0 / SOF1 / SOF2
            h = int.from_bytes(data[i + 5:i + 7], "big")
            w = int.from_bytes(data[i + 7:i + 9], "big")
            return w, h
        seg = int.from_bytes(data[i + 2:i + 4], "big")
        i += 2 + seg
    return None, None


def grab(channel, out):
    url = f"http://{HOST}/ISAPI/Streaming/channels/{channel}/picture"
    t0 = time.monotonic()
    r = requests.get(url, auth=HTTPDigestAuth(USER, PWD), timeout=10)
    dt = (time.monotonic() - t0) * 1000
    print(f"GET {url}")
    print(f"  status={r.status_code}  Content-Type={r.headers.get('Content-Type')}")
    print(f"  size={len(r.content)} bytes   latency={dt:.0f} ms")
    if r.status_code == 200:
        w, h = jpeg_size(r.content)
        print(f"  分辨率={w}x{h}" if w else "  分辨率=(解析失败)")
        with open(out, "wb") as f:
            f.write(r.content)
        print(f"  saved -> {out}")
        return True
    print(f"  失败：body={r.content[:200]!r}")
    return False


if __name__ == "__main__":
    # 主码流(101) vs 子码流(102)：标定只用主码流，子码流仅作对照
    print("== 主码流 channel 101 ==")
    grab(101, "snap_main.jpg")
    print("\n== 子码流 channel 102（对照，分辨率低）==")
    grab(102, "snap_sub.jpg")
