# 速腾 RoboSense 激光雷达(2 台:.202 / .205)

## 设备
- `192.168.1.202` / `192.168.1.205`,均为速腾 RoboSense,具体型号(RS-16/32/Bpearl/Helios/Ruby/...)待认。
- MAC OUI = `08:48:57`(Suteng Innovation = 速腾)。

## SDK(就绪,无需 ROS)
`third_party/rslidar_sdk-v1.5.20/`。该 SDK 的 ROS 是**可选**依赖
(CMake `find_package(roscpp QUIET)`,本机没 ROS 照编),底层 `src/rs_driver/` 自带独立
demo / 工具:
- `demo_online_multi_lidars.cpp` — 多台在线 LiDAR 一起解
- `tool/rs_driver_pcdsaver.cpp` — 直接把点云存成 PCD

## 接入计划
1. 编译:`cd third_party/rslidar_sdk-v1.5.20 && mkdir build && cd build && cmake .. && make -j`
   (依赖 cmake / `libyaml-cpp-dev` / `libpcap-dev`)。
2. 写 `robosense_driver.py`(实现 `Sensor`),内部调 `rs_driver` 出点云(或直接包
   `rs_driver_pcdsaver`,按帧产出 PCD + monotonic 戳)。
3. `acquire/registry.py` 里 `lidar_mechanical`(速腾分支)登记本驱动。
4. `config/rig.yaml` 填这两台的 `lidar_type` / msop / difop 端口。

## 前置必做(否则 SDK 收不到包)
两台的点云 UDP 流当前**目的 IP 不指采集机**。先上各自网页(`http://192.168.1.202`、
`.205`,80 端口)把**目的 IP 改到 192.168.1.11**,端口错开避免撞口:
- `.202` → msop `6699` / difop `7788`
- `.205` → msop `6700` / difop `7789`

## 待办
- [ ] 认 `.202` / `.205` 的具体型号(网页或从 DIFOP 读)→ 填 `lidar_type`
- [ ] 编 SDK(确认无 ROS 能过)
- [ ] 写 `robosense_driver.py` 并在 registry 登记
