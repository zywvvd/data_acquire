# lidar_hesai — 禾赛 QT128(.201)

禾赛 Pandar QT128 机械激光雷达。走 **HesaiLidar_SDK_2.0**,在线 UDP 解析点云;**自加 `sample_pcd`**
目标把每帧点云直接写成 ASCII PCD(绕开 Ubuntu 22.04 上链接失败的 PCL)。

## 设备信息

- IP `192.168.1.201`,型号 **Pandar QT128**;MAC OUI `ec:9f:0d`;网页 80 标题 "Pandar Console"。
- 数据口 **UDP 2364**(非默认 2368,以网页实际值为准),PTC `9347`(角度修正文件)。
- 量级:~15–19 万点/帧,~6–7 帧/s。

## 采集方案

子进程**流式型**(`HesaiSensor`):`start()` 用 `Popen` 后台拉起 `sample_pcd`,它持续接收 UDP、回调
`lidarCallback` 每帧写一个 `frame_%06d.pcd` 到 `out_dir`(经 `PCD_OUT` 注入);在线流不自停,到 `duration`
由基类 `terminate`。`grab()` 增量扫描 `out_dir` 的新 PCD 逐帧返回。

## 流程要点

1. **网页配置**(否则收不到帧):`.201` 网页 Pandar Console(http://192.168.1.201)把点云目的 IP 设为采集机
   `192.168.1.200`,Lidar Destination Port = **2364**。
2. **配置 ini**:驱动按 rig.yaml 的 spec 渲染 `device.ini`(`device_ip_address` / `udp_port` / `ptc_port`)写到
   `out_dir`;`use_ptc_connected=true` 让 SDK 经 PTC(9347)自动拉角度修正文件。`qt128_online_201.ini` 是同结构的
   手动模板,留作参考。
3. **PCD_OUT**:驱动把 `out_dir` 绝对路径注入 `PCD_OUT`,sample_pcd 据此落盘。
4. 启动时 sample_pcd 会尝试 `sudo` 改 `rmem_max`(无 sudo 报一行错,**不影响**取数)。

## 构建 SDK

```bash
cd third_party/HesaiLidar_SDK_2.0 && mkdir -p build && cd build
cmake .. && make sample_pcd -j      # -> build/sample_pcd
```

## 运行

```bash
# 单设备 demo(委托 HesaiSensor, 默认 -> data/hesai_qt128/)
python3 sensors/lidar_hesai/hesai_demo.py --seconds 10
python3 sensors/lidar_hesai/hesai_demo.py --data-port 2364 --seconds 30
# 协同采集
python3 acquire/record.py --duration 10
```

## 输出

`frame_%06d.pcd`(ASCII),`FIELDS x y z intensity ring`(x/y/z float 米,intensity uint8,ring uint16)。

## SDK 改动(逐文件, 详见 [SOURCES.md](../../third_party/SOURCES.md#hesailidar_sdk_20--禾赛-qt128201))

- **`test/test_pcd.cc`**(新增):仿官方 `test.cc`,但 `lidarCallback` 回调**直接写 ASCII PCD**(点类型
  `LidarPointXYZICRT`),输出目录走环境变量 `PCD_OUT`。**目的:绕开链接失败的 `pcl_tool`(VTK↔libtiff 冲突)。**
- **`CMakeLists.txt`**:在 `if(NOT DISENABLE_TEST_CC)` 段加 `add_executable(sample_pcd test/test_pcd.cc)` 并链 `hesai_sdk_lib`。

## 关键文件

- `hesai_driver.py` — `HesaiSensor(SubprocessSensor)`:`_binary/_build_cmd/_env/_duration/_frame_glob`;`_ini_path()` 渲染 ini。
- `hesai_demo.py` — 单设备 demo 薄壳。
- `qt128_online_201.ini` — 手动配置模板(driver 渲染时参考其结构)。

## FAQ

- 收不到帧:检查网页目的 IP=采集机、UDP 口=2364、`use_ptc_connected` 能否经 9347 拉到角度文件。
- 0 帧 / 只统计:确认用的是 `sample_pcd`(产 PCD),不是 SDK 自带只打印统计的 `sample`。
