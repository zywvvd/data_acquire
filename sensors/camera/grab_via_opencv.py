#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 OpenCV（封装层）经 RTSP 取一帧。

对应文档《海康相机取图方式总览.md》「封装层」。
OpenCV 的 VideoCapture 经 ffmpeg 后端拉 RTSP，返回 numpy 数组（BGR）。
注意：密码含 @，RTSP URL 中须编码为 %40。
"""
import cv2

# 主码流；密码 b@light2. 中的 @ 编码为 %40
URL = "rtsp://admin:b%40light2.@192.168.2.2:554/Streaming/Channels/101"

cap = cv2.VideoCapture(URL, cv2.CAP_FFMPEG)
ok, frame = cap.read()
cap.release()

print(f"opened={ok}")
if ok:
    print(f"frame: shape={frame.shape}  dtype={frame.dtype}  (HxWxC, BGR)")
    cv2.imwrite("opencv_frame.jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    print("saved -> opencv_frame.jpg  (主机端 JPEG 质量 95)")
else:
    print("取帧失败：检查 URL / 网络 / 后端")
