#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证海康相机 192.168.2.2 的 TCP 端口连通性与 ISAPI 认证。

对应文档《海康相机取图方式总览.md》「端口与认证」。
"""
import socket
import requests
from requests.auth import HTTPDigestAuth

HOST = "192.168.2.2"
USER = "admin"
PWD = "b@light2."

# 端口表里的 TCP 端口（UDP/ONVIF 发现 3702 不在此列，需单独处理）
TCP_PORTS = {
    80:   "Web / ISAPI (HTTP)",
    443:  "Web / ISAPI (HTTPS)",
    554:  "RTSP",
    8000: "HCNetSDK",
    5060: "GB28181 / SIP",
}


def tcp_probe(host, port, timeout=2.0):
    """TCP 三次握手探测：OPEN / closed / filtered / error。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return "OPEN"
    except socket.timeout:
        return "filtered/timeout"
    except ConnectionRefusedError:
        return "closed"
    except OSError as e:
        return f"error({e.errno})"
    finally:
        s.close()


def banner(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main():
    print(f"target host : {HOST}")
    print(f"credentials : {USER} / {'*' * len(PWD)}")

    # ---- 1) TCP 端口探测 ----
    banner("1) TCP 端口探测 (socket.connect)")
    print(f"  {'port':<6}{'state':<20}service")
    for port, name in TCP_PORTS.items():
        print(f"  {port:<6}{tcp_probe(HOST, port):<20}{name}")

    # ---- 2) ISAPI 认证探测 ----
    banner("2) ISAPI 认证探测 (HTTP Digest)")
    base = f"http://{HOST}"
    cap_url = f"{base}/ISAPI/System/capabilities"
    pic_url = f"{base}/ISAPI/Streaming/channels/101/picture"

    # 2a 无凭证 → 预期 401 + WWW-Authenticate: Digest ...
    r = requests.get(cap_url, timeout=5)
    print(f"  [no-auth] GET {cap_url}")
    print(f"            status : {r.status_code}")
    print(f"            WWW-Authenticate : {r.headers.get('WWW-Authenticate', '(none)')}")

    # 2b digest 凭证 → 预期 200
    r = requests.get(cap_url, auth=HTTPDigestAuth(USER, PWD), timeout=10)
    print(f"  [digest ] GET {cap_url}")
    print(f"            status : {r.status_code}   body: {len(r.content)} bytes")

    # 2c digest 抓图 → 预期 200 image/jpeg
    r = requests.get(pic_url, auth=HTTPDigestAuth(USER, PWD), timeout=10)
    ct = r.headers.get("Content-Type", "(none)")
    print(f"  [digest ] GET {pic_url}")
    print(f"            status : {r.status_code}   Content-Type: {ct}   body: {len(r.content)} bytes")
    if r.status_code == 200 and ct.startswith("image/"):
        with open("probe.jpg", "wb") as f:
            f.write(r.content)
        print("            saved -> probe.jpg")
    elif r.status_code == 401:
        print("            认证失败：账号/密码错误或无权限")
    elif r.status_code == 404:
        print("            端点不存在：主码流通道号可能不是 101")


if __name__ == "__main__":
    main()
