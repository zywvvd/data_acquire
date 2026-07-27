# Livox 固态激光雷达(.100)

## 设备
- `192.168.1.100`,Livox 固态(大疆子公司),具体型号(Mid-360 / Avia / HAP / Tele-15 / ...)待认。
- **纯 UDP 设备**:无任何 TCP 服务(网页/SSH 全无),MAC OUI = `48:1c:b9`(SZ DJI)→ 实锤 Livox。

## 接入计划
Livox 不能裸 sniff,必须走它的 SDK。两条路二选一:
1. **ctypes 包 Livox SDK2**(C 库)——和本仓库海康 `sdk_grabber.py` ctypes 包 HCNetSDK
   完全同套路,最契合「纯 Python」主线。SDK2 走 UDP 广播发现(Mid-360 广播口 56100)。
2. 实在顶不住 → 让官方 `livox_ros_driver2` 当 sidecar 跑 ROS,把数据 bridge 出来;
   本驱动在 `Sensor` 接口后面隐藏这个差异。

先认准型号(Mid-360 用 56100;其它型号广播口/协议不同)。

## 待办
- [ ] 用 Livox Viewer / SDK 认 `.100` 的具体型号
- [ ] 取 Livox SDK2,放进 `third_party/`
- [ ] 写 `livox_driver.py`(ctypes),在 registry 的 `lidar_solidstate` 登记
