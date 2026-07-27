# 禾赛 Hesai 激光雷达(.201, QT128)

## 设备
- `192.168.1.201`,禾赛 Pandar QT128。
- MAC OUI = `ec:9f:0d`;网页 80 标题 "Pandar Console"。

## SDK(已就位,待接)
`third_party/HesaiLidar_SDK_2.0/`。

## 接入计划
1. 看 SDK 的 README / demo,确认无 ROS 编译路径与点云输出方式。
2. 写 `hesai_driver.py`(实现 `Sensor`),调禾赛 SDK 出点云 + monotonic 戳。
3. `acquire/registry.py` 里 `lidar_mechanical`(禾赛分支)登记本驱动。

## 前置
与速腾同理:确认 `.201` 的点云目的 IP 指向采集机(网页 "Pandar Console",80 端口,
设置 destination / target = 192.168.1.11),UDP 数据口默认 `2368`。

## 待办
- [ ] 读 `third_party/HesaiLidar_SDK_2.0/README_CN.md`,定无 ROS 编译与输出方式
- [ ] 编 SDK
- [ ] 写 `hesai_driver.py` 并在 registry 登记
