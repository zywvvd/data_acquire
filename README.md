# data_acquire

临时多传感器采集网络的数据采集仓库。目标:用**纯 Python 编排(不依赖 ROS)**,
把 7 台异构传感器(海康相机/鱼眼、禾赛/速腾机械激光雷达、Livox 半固态激光雷达、
图漾结构光 3D 相机)的数据统一采下来,各自留一份**可直接跑的 demo**,采集产物落到 `data/`。

设计上**配置驱动**:`config/rig.yaml` 描述每台设备的 `kind/model/ip/凭证/端口`,
`acquire/registry.py` 按 `(kind, model)` 派发到驱动;每台传感器另有一个**独立可跑的 demo**
(本 README 的重点),不依赖编排框架就能单台取数。

> 本文档记录的是 **2026-07-27 实测确认**的结果:**7 台设备全部可达、全部已采到真数据并落盘**。

---

## 1. 网络与采集机

- **采集机 IP:`192.168.1.200`**(USB 网卡 `enx68da73ad5e2d`,子网 `192.168.1.0/24`)。
  > 历史值曾是 `.11`,本会话改为 `.200`;所有 demo 默认值已随之更新。
- 所有传感器与采集机同子网。**每台网络雷达/相机的「目的 IP / 目的端口」必须在其自身网页里
  指向 `192.168.1.200`**——它们不会自动跟随采集机 IP。

## 2. 设备总览(实测确认)

| IP | kind | 型号(实测) | SDK | 传输 / 端口 | 产物目录 | 状态 |
|---|---|---|---|---|---|---|
| .99  | fisheye         | 海康 DS-2CD6345EWD-IV        | HCNetSDK(ctypes) | TCP 8000,逻辑通道 1 | `data/fisheye_99/`   | ✅ 1920×1920 JPEG |
| .107 | camera          | 海康 DS-2CD3T46WDA4-L        | HCNetSDK(ctypes) | TCP 8000,逻辑通道 1 | `data/camera_107/`   | ✅ 1920×1080 JPEG |
| .100 | lidar(半固态) | **Livox HAP**(IndustrialHAP) | Livox-SDK2       | UDP cmd 56000 / point 57000 / imu 58000 / log 59000(主动查询式) | `data/livox_hap/`    | ✅ ~45.4万点/s PCD |
| .114 | structured_light| **图漾 FM815-IX-E1**(GigE Vision)| Camport4      | GigE,按 IP 发现       | `data/fm815_114/`    | ✅ depth+color+点云 |
| .201 | lidar_mechanical| 禾赛 QT128                   | HesaiLidar_SDK_2.0 | UDP **2364** + PTC 9347 | `data/hesai_qt128/`  | ✅ ~15万点/帧 PCD |
| .202 | lidar_mechanical| 速腾 **RSAIRY**              | rslidar_sdk(rs_driver) | UDP msop 6692 / difop 7782 | `data/robosense_202/` | ✅ ~7.9万点/帧 PCD |
| .205 | lidar_mechanical| 速腾 **RSAIRY**              | rslidar_sdk(rs_driver) | UDP msop 6695 / difop 7785 | `data/robosense_205/` | ✅ ~7.9万点/帧 PCD |

补充事实:
- `.100` Livox:SDK 上报 `dev_type=10`(IndustrialHAP),机壳标注 "HAP (TX)",SN `5CWD239F4105YV1`。
- `.114` 图漾:机壳/用户称 FM855-E1,但 SDK `ListDevices` 实报型号 **FM815-IX-E1**,`TL version: Gige_2_0`,SN `207000147291`。
- 速腾 `.202/.205`:经 9 型 decoder head-to-head 实测定为 `RSAIRY`;`bolight_alg` 生产配置 `rslidar_sdk/config/config.yaml` 亦为 `RSAIRY`(其端口旧 +1,已失效)。

## 3. `data/` 产物布局

```
data/
├── camera_107/      海康相机     N× JPEG 1920×1080(设备端编码)
├── fisheye_99/      海康鱼眼     N× JPEG 1920×1920
├── hesai_qt128/     禾赛 QT128   ASCII PCD,~15万点/帧
├── robosense_202/   速腾 RSAIRY  ASCII PCD,~7.9万点/帧
├── robosense_205/   速腾 RSAIRY  ASCII PCD,~7.9万点/帧
├── livox_hap/       Livox HAP    ASCII PCD,~5万点/帧(按点数切片)
└── fm815_114/       图漾结构光   N× {depth 16bit PNG(mm) + color JPG + 点云 PCD(米)}
```

## 4. 仓库结构

```
data_acquire/
├── config/rig.yaml            # 设备清单(配置驱动核心)
├── acquire/                   # 编排: 读 rig.yaml → registry 派发 → 落盘
│   ├── registry.py            #   (kind, model) → 驱动 派发表
│   └── record.py              #   采集主程序
├── sensors/                   # 每种传感器一个子目录 + 独立 demo
│   ├── base.py                #   统一接口 Sensor + Sample
│   ├── camera/                #   海康: sdk_grabber.py(HikGrabber) + grab_demo.py + hik_driver.py
│   ├── lidar_hesai/           #   禾赛: hesai_demo.py + qt128_online_201.ini
│   ├── lidar_robosense/       #   速腾: robosense_demo.py
│   ├── lidar_livox/           #   Livox: livox_demo.py + hap_host200.json(+ mid360_host200.json 备选)
│   └── structured_light/      #   .114 图漾: percipio_demo.py(包 Camport4 SimpleView_CaptureDump)
├── third_party/               # 厂商 SDK(仓库自包含)
│   ├── EN-HCNetSDKV6.1.9.4_build20220412_linux64/  # 海康(预编译 .so)
│   ├── HesaiLidar_SDK_2.0/                         # 禾赛(自编 + 自加 sample_pcd)
│   ├── rslidar_sdk-v1.5.20/                        # 速腾(只编 src/rs_driver)
│   ├── Livox-SDK2/                                 # Livox(自编 + 自加 pcd_saver 样例)
│   ├── camport4/                                   # 图漾 Camport4(预编译 .so + 自编 sample)
│   ├── Camport3/  Livox-SDK/                       # 历史旧版, 已弃用(保留备查)
│   └── EN-HCNetSDK.../                             # (同上)
└── data/                      # 采集输出(.gitignore)
```

---

## 5. 工具链(关键, 跨 SDK 通用)

- **Python**:必须用 anaconda 的 `python3`(`/home/vvd/anaconda3/bin/python3`,带 `requests`/`opencv-python`/`pyyaml`)。
  系统另有 VSCode 自动选中的裸 `python3.14`(uv 管理,无依赖),用它跑会 `ModuleNotFoundError`。终端里 `python3` 即 anaconda。
- **编译器**:GCC 11(Ubuntu 22.04)。
  - ⚠️ **老厂商 SDK 兼容坑**:速腾 `rslidar_sdk`、老 `Livox-SDK` v1 在 GCC11 下用 `std::shared_ptr`/`std::make_shared` 却没 `#include <memory>` → 编译报 `'shared_ptr' is not a member of 'std'`。
    **统一解法**:`cmake` 加 `-DCMAKE_CXX_FLAGS="-include memory"` 强制预包含。
- **系统依赖**:`libpcap-dev`(速腾)、`opencv` 4.5.4(系统自带,图漾 Camport4 用)、`cmake`。
- ⚠️ **PCL/VTK 链接坏**:本机有 PCL 头(`/usr/include/pcl-1.12`),但 Ubuntu 22.04 上 VTK↔libtiff 冲突,任何**链接 PCL 的工具**(如禾赛 `pcl_tool`)都因 `libvtkIOImage` 里 `TIFF…@LIBTIFF_4.0` 未定义而链接失败。
  **解法**:不依赖 PCL,**自写回调直接产 ASCII PCD**(见禾赛 `sample_pcd`、Livox `livox_lidar_pcd_saver`)。PCD 头 `FIELDS x y z intensity … / DATA ascii`,纯文本,免链接。

---

## 6. 各 SDK 编译过程(逐个, 含原因)

### 6.1 海康 HCNetSDK(.99 / .107)— 预编译, 免编译
- 位置:`third_party/EN-HCNetSDKV6.1.9.4_build20220412_linux64/lib/`,需含
  `libhcnetsdk.so`、`HCNetSDKCom/`、`libcrypto.so.1.1`、`libssl.so.1.1`、`libPlayCtrl.so`。
- `sdk_grabber.py` 用 ctypes 按绝对路径加载 `libhcnetsdk.so`;运行时需 `LD_LIBRARY_PATH` 指向该 `lib/`(传递依赖)。
- 凭证:`admin` / `b@light2.`(两台同;密码含 `@`,RTSP URL 里要 URL-encode 成 `%40`)。
- 通道:**SDK 逻辑通道从 1 起**(`NET_DVR_CaptureJPEGPicture`);RTSP/ISAPI 流号是 101(主)/102(副),别混。

### 6.2 禾赛 HesaiLidar_SDK_2.0(.201 QT128)
```bash
cd third_party/HesaiLidar_SDK_2.0 && mkdir -p build && cd build
cmake .. && make -j
# -> build/sample(帧统计)、build/sample_pcd(自加, 按帧写 ASCII PCD)
```
- **自加目标 `sample_pcd`**:在 `CMakeLists.txt` 的 `if(NOT DISENABLE_TEST_CC)` 内加 `add_executable(sample_pcd test/test_pcd.cc)` 并链 `hesai_sdk_lib`;
  `test/test_pcd.cc` 仿官方 `test.cc`,但回调 `lidarCallback` 直接写 ASCII PCD(点类型 `LidarPointXYZICRT`:x/y/z float、intensity/confidence uint8、ring uint16、timestamp double),输出目录走环境变量 `PCD_OUT`。**目的:绕开链接失败的 `pcl_tool`。**
- 配置 `sensors/lidar_hesai/qt128_online_201.ini`:`source_type=network`、`device_ip_address=192.168.1.201`、`ptc_port=9347`、`use_ptc_connected=true`、**`udp_port=2364`**。
  > ⚠️ **QT128 实测目的端口是 2364,不是默认 2368!** 以雷达网页(Pandar Console)Lidar Destination Port 实际值为准。

### 6.3 速腾 rslidar_sdk v1.5.20(.202 / .205 RSAIRY)
```bash
cd third_party/rslidar_sdk-v1.5.20/src/rs_driver && mkdir -p build_rs && cd build_rs
cmake -DCOMPILE_DEMOS=ON -DCOMPILE_TOOL_PCDSAVER=ON -DCMAKE_CXX_FLAGS="-include memory" ..
make -j
# -> tool/rs_driver_pcdsaver + demo/demo_online[_multi_lidars] 等
```
- ⚠️ **只编 `src/rs_driver/`,不编顶层**:顶层 `rslidar_sdk_node` 在关闭 ROS 时引用未声明的 ROS 符号(`SourcePacketRos` 等),编不过;`rs_driver` 子目录自包含、免 ROS。
- ⚠️ 必须加 `-include memory`(GCC11 老代码坑,见 §5)。
- 在线取数:`rs_driver_pcdsaver -type RSAIRY -msop <port> -difop <port> -host 192.168.1.200`。
- **型号识别过程**:`pcdsaver` 必须给 `-type`,错型要么刷 `ERRCODE_WRONGMSOPBLKID`(块ID不匹配)、要么出几百点/帧的平面垃圾。本机 `.202/.205` 的 MSOP 头是 `55aa055a` + V2 头部(`lidar_model` 字节=0x31),排除 RS16/32/RSBP(`ff ee`/8字节头)与 M1/M2/E1(`55aa5aa5`)。对 9 个 V2 候选 head-to-head:唯 **`RSAIRY`** 零报错 + ~8.3万点/帧真 3D 点云。
  - **RSAIRY vs RSFAIRY**:两者同包格式、不同垂直角表(SDK 无法从包内区分),实测 `RSFAIRY` z 可达 ~26m、`RSAIRY` z ~6m。本仓库按生产配置(`bolight_alg`)默认 **`RSAIRY`**;若硬件实为 RS-Fairy,改 `--type RSFAIRY`。

### 6.4 Livox-SDK2(.100 HAP)
```bash
cd third_party/Livox-SDK2 && mkdir -p build && cd build
cmake .. && make -j
# -> build/samples/livox_lidar_pcd_saver/livox_lidar_pcd_saver 等(+ liblivox_lidar_sdk_shared.so)
```
- GCC11 直接编过(比老 `Livox-SDK` v1 干净,且 v1 不支持 Mid-360/HAP,故弃用 v1)。
- **自加样例 `livox_lidar_pcd_saver`**(在 `samples/livox_lidar_pcd_saver/`,并登记进 `samples/CMakeLists.txt`):仿官方 `livox_lidar_quick_start` 的 init/Normal 模式流程,**只把点云回调改成按帧写 ASCII PCD**。
  - 点格式:`data_type=1` → `LivoxLidarCartesianHighRawPoint`(int32 xyz, 单位 mm + reflectivity + tag),存盘时 mm→m。
  - ⚠️ **HAP 的 `frame_cnt` 实测恒为 0**(不随旋转递增),**不能用它分帧**;saver 改为**每累积 50000 点切一帧**(约 10Hz)。
  - 环境变量:`PCD_OUT`(输出目录,需预创建)、`LIVOX_RUN_SECS`(运行秒数)。运行时 `LD_LIBRARY_PATH` 需含 `build/sdk_core`。
- 配置 `sensors/lidar_livox/hap_host200.json`:顶层 key `"HAP"`;`host_net_info.host_ip=192.168.1.200`;端口 cmd 56000 / point 57000 / imu 58000 / log 59000。
  > ⚠️ **Livox-SDK2 是「主动查询式」发现**(SDK 先广播查询、雷达应答),不像禾赛/速腾被动持续推流。所以**静态 UDP 嗅探看不到流量是正常的,必须跑 SDK 才出数据**。另:HAP 端口(56000 系)与 Mid-360(56100 系)完全不同,别照搬 Mid-360。备选 `mid360_host200.json` 保留。

### 6.5 图漾 Camport4(.114 FM815-IX-E1)
```bash
cd third_party/camport4/sample && mkdir -p build && cd build
cmake .. -DTYCam_DIR=$(cd ../.. && pwd) -DARCH=x64 -DBUILD_SAMPLE_V2=OFF -DBUILD_SAMPLE_GENICAM_SFNC=OFF
make -k -j
# -> sample/build/bin/{ListDevices, SimpleView_OpenWithIP, SimpleView_FetchFrame, SimpleView_Point3D, ...}
```
- `TYCam_DIR` 指 `camport4/` 根(含 `TYCamConfig.cmake`),`ARCH=x64` 选 `lib/linux/lib_x64/libtycam.so.4.2.11`(+ `libtyimgproc.so.1.1.0`)。
- 需系统 opencv(本机 4.5.4)。运行时 `LD_LIBRARY_PATH` 需含 `camport4/lib/linux/lib_x64`。
- **关键确认**:`bin/ListDevices` 已成功枚举到 `.114`(Percipio FM815-IX-E1,GigE Vision,SN 207000147291)。
  > 用 **Camport4**(较新,V4 API `TYApi.h`)。**不是 VcameraSDK**(用户已确认并删除),也不是老的 Camport3。
- **自编无头采集 sample `SimpleView_CaptureDump`**(在 `sample/sample_v1/`,登记进 `ALL_SAMPLES`):仿 `FetchFrame`/`Point3D` 但去掉 GUI/键盘,取 N 帧各落盘 `depth_%04d.png`(uint16 mm)、`color_%04d.jpg`(原分辨率 BGR)、`points_%04d.pcd`(ASCII,米,带 rgb)。点云路径:`TYMapRGBImageToDepthCoordinate`(彩色贴到深度分辨率)→ `TYMapDepthImageToPoint3d`(depth_calib);`write_pcd` 两遍法先数有效点(depth=0 投影为 NaN)再写,`POINTS` 头与数据行数一致。**实测**:depth 640×480(mm,量程 0.56–4.16m,有效 ~7%)、color 2560×1920、点云 ~2万点/帧。
- **Python demo** `sensors/structured_light/percipio_demo.py` 调它,默认 `-ip 192.168.1.114 -n 6 -outdir data/fm815_114`,自动注入 `LD_LIBRARY_PATH`。

---

## 7. demo 运行命令(实测可用)

通用前置:终端用 anaconda `python3`;SDK 类脚本按需 `export LD_LIBRARY_PATH`(下见)。

```bash
# 海康相机 .107 / 鱼眼 .99(默认存 data/camera_<末段>; 鱼眼用 --out 命名)
export LD_LIBRARY_PATH=$PWD/third_party/EN-HCNetSDKV6.1.9.4_build20220412_linux64/lib
python3 sensors/camera/grab_demo.py --ip 192.168.1.107 -n 6
python3 sensors/camera/grab_demo.py --ip 192.168.1.99  -n 6 --out data/fisheye_99

# 禾赛 QT128 .201(配置 qt128_online_201.ini, udp 2364)
python3 sensors/lidar_hesai/hesai_demo.py

# 速腾 .202 / .205(默认 .202 / RSAIRY / .200)
python3 sensors/lidar_robosense/robosense_demo.py --type RSAIRY
python3 sensors/lidar_robosense/robosense_demo.py --ip 192.168.1.205 --msop 6695 --difop 7785 --type RSAIRY

# Livox HAP .100(默认 hap_host200.json)
python3 sensors/lidar_livox/livox_demo.py --seconds 15

# 图漾结构光 .114(LD_LIBRARY_PATH 由 demo 自动注入)
python3 sensors/structured_light/percipio_demo.py -n 6          # 默认 -> data/fm815_114
# 手动验证设备: cd third_party/camport4 && LD_LIBRARY_PATH=$PWD/lib/linux/lib_x64 ./sample/build/bin/ListDevices
```

## 8. 跨设备踩坑清单(深度总结)

1. **目的 IP/端口必须逐台在设备网页改**:雷达不会跟随采集机。端口多为**非默认**:QT128=2364(非2368)、.202=6692/7782、.205=6695/7785、Livox HAP=56000系(非 Mid-360 的 56100 系)。**永远以设备网页实际值为准**。
2. **Livox-SDK2 主动查询式**:静态嗅探无流量属正常,必须跑 SDK。
3. **GCC11 + 老 SDK**:加 `-DCMAKE_CXX_FLAGS="-include memory"`。
4. **PCL/VTK 链接坏(22.04)**:别用链接 PCL 的工具,自写 ASCII PCD 回调。
5. **速腾顶层编不过**:只编 `src/rs_driver/`(关 ROS)。
6. **RSAIRY vs RSFAIRY**:同包不同垂直角表,按硬件/生产配置选;默认 RSAIRY。
7. **HAP frame_cnt 恒 0**:按点数切片分帧。
8. **海康通道**:SDK 逻辑通道从 1 起,RTSP/ISAPI 是 101/102。
9. **采集机 IP**:现为 `.200`(曾 `.11`);`bolight_alg` 旧配置端口在此基础上 +1,已失效。
10. **图漾 SDK**:用 Camport4(V4 API),非 VcameraSDK、非 Camport3。

## 9. 进度

- ✅ **7 台全部可达(ping / 发现),且 7 台全部已采到真数据并落盘 `data/`**:.99、.107、.201、.202、.205、.100、.114。
- ✅ `.114` 图漾 FM815-IX-E1:Camport4 `SimpleView_CaptureDump` 取 depth(640×480 mm)+ color(2560×1920)+ 点云(~2万点/帧,0.56–4.16m),已存 `data/fm815_114/`。
- ⏳ 配置驱动编排层(`config/rig.yaml` + `acquire/registry.py` + `record.py` 多线程统一采集、输出 MCAP):架构已搭,各 `Sensor` 驱动包装待按 demo 收敛后统一接入。
