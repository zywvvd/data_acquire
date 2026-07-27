# data_acquire

临时多传感器采集网络的数据采集仓库。目标:用**纯 Python 编排(不依赖 ROS)**,把 7 台异构传感器
(海康相机/鱼眼、禾赛/速腾机械激光雷达、Livox 半固态激光雷达、图漾结构光 3D 相机)的数据统一采下来,
**一个触发即可多路并发协同采集**,各自还留一份**可直接跑的单设备 demo**,采集产物落到 `data/`。

设计上**配置驱动 + 统一抽象**:`config/rig.yaml` 描述每台设备的 `kind/model/ip/凭证/端口`;
`acquire/registry.py` 按 `(kind, model)` 派发到驱动;每台传感器实现统一的 `Sensor` 接口
(`connect/start/grab/stop`),`acquire/record.py` 多线程并发采集,落盘 + manifest + 跨传感器对齐索引。

> 本文档反映 **2026-07-27 实测确认 + 框架重构完成**:7 台设备全部可达、全部已采到真数据;
协同采集入口 `record.py` 已接通全部 7 路。

---

## 1. 网络与采集机

- **采集机 IP:`192.168.1.200`**(USB 网卡 `enx68da73ad5e2d`,子网 `192.168.1.0/24`)。
- 所有传感器与采集机同子网。**每台网络雷达/相机的「目的 IP / 目的端口」必须在其自身网页里指向
  `192.168.1.200`**——它们不会自动跟随采集机 IP。

## 2. 设备总览(实测确认)

| IP | kind | 型号(实测) | SDK | 传输 / 端口 | 产物目录 | 状态 |
|---|---|---|---|---|---|---|
| .99  | fisheye         | 海康 DS-2CD6345EWD-IV | HCNetSDK(ctypes) | TCP 8000,通道 1 | `data/fisheye_99/` | ✅ JPEG |
| .107 | camera          | 海康 DS-2CD3T46WDA4-L | HCNetSDK(ctypes) | TCP 8000,通道 1 | `data/camera_107/` | ✅ JPEG |
| .100 | lidar_solidstate| **Livox HAP**(IndustrialHAP) | Livox-SDK2 | UDP cmd 56000 / point 57000 / imu 58000 / log 59000(主动查询) | `data/livox_hap/` | ✅ ~45万点/s PCD |
| .114 | structured_light| **图漾 FM815-IX-E1**(GigE Vision) | Camport4 | GigE,按 IP 发现 | `data/fm815_114/` | ✅ depth+color+点云 |
| .201 | lidar_mechanical| 禾赛 QT128 | HesaiLidar_SDK_2.0 | UDP **2364** + PTC 9347 | `data/hesai_qt128/` | ✅ ~15万点/帧 PCD |
| .202 | lidar_mechanical| 速腾 **RSAIRY** | rslidar_sdk(rs_driver) | UDP msop 6692 / difop 7782 | `data/robosense_202/` | ✅ PCD |
| .205 | lidar_mechanical| 速腾 **RSAIRY** | rslidar_sdk(rs_driver) | UDP msop 6695 / difop 7785 | `data/robosense_205/` | ✅ PCD |

补充:`.100` Livox SN `5CWD239F4105YV1` dev_type=10;`.114` 机壳标 FM855-E1 但 SDK 实报 **FM815-IX-E1**(以 SDK 为准);速腾 `.202/.205` 经 9 型 head-to-head + `bolight_alg` 生产配置定为 RSAIRY。

## 3. 架构(三层)

```
config/rig.yaml (设备清单: kind/model/ip/端口/凭证)
        │  acquire/record.py 读
        ▼
acquire/registry.py ── (kind, model) 派发 ──► sensors/*_driver.py  (Sensor 子类)
(多线程并发采集)                                connect → start → 反复 grab → stop
        │
        ▼
data/<run>/<name>/{帧文件} + manifest.jsonl  ;  run 级 index.csv / align.csv
```

**两类驱动**(都在 `sensors/base.py` 定义):
- `Sensor`(进程内 poll 型):`grab()` 直接调底层 SDK 拿一帧、自己写文件。→ **海康**(`HikSensor`)。
- `SubprocessSensor`(子进程型):`start()` 拉起外部已编译 C++ 二进制,它边跑边往 `out_dir` 写文件,
  `grab()` 增量扫描这些文件返回。分两种取数模型:
  - **流式型**(`_duration()` 有值):Popen 后台跑 + 轮询增量帧,到时长 terminate。→ 禾赛 / 速腾 / Livox。
  - **批量型**(`_duration()` 为 None):`subprocess.run` 同步跑完 N 帧再逐帧返回。→ 图漾。

设备自然结束(流式到时 / 批量采完)时 `grab()` 返回 `meta={"ended": True}`,record 据此退出该路线程。

**加一种新传感器 = ① 写一个 `Sensor`/`SubprocessSensor` 子类 + ② 在 `registry.py` 登记 `(kind, model)` 一行 +
③ 在 `rig.yaml` 加一条设备。**(详见 §9 扩展指南。)

## 4. 快速开始

> 通用前置:终端用 **anaconda `python3`**(`/home/vvd/anaconda3/bin/python3`,带 cv2/yaml/numpy);
> 相机类还需 `LD_LIBRARY_PATH` 指向海康 SDK 的 lib(LiDAR/结构光的库由各自驱动自动注入)。

### 4.1 协同采集(一触发采全部启用设备)
```bash
export LD_LIBRARY_PATH=$PWD/third_party/EN-HCNetSDKV6.1.9.4_build20220412_linux64/lib
python3 acquire/record.py --duration 10                       # 7 路并发, 全局 10s
python3 acquire/record.py --only cam_hik,lidar_hesai --tag calib_01   # 只采子集 + 命名 run
python3 acquire/record.py                                     # 流式按各自 duration 自停, 相机 Ctrl-C 停
```
输出:`data/<tag_><时间戳>/<name>/{帧} + manifest.jsonl`,run 根有 `index.csv`(全帧时间轴)与
`align.csv`(以相机为基准的跨传感器最近邻对齐,供离线配准)。

### 4.2 单设备 demo(各自委托对应 driver,逻辑与 record 复用)
```bash
# 海康相机 .107 / 鱼眼 .99
python3 sensors/camera/grab_demo.py --ip 192.168.1.107 -n 6
python3 sensors/camera/grab_demo.py --ip 192.168.1.99  -n 6 --out data/fisheye_99
# 禾赛 QT128 .201(网页设目的IP=.200, udp 2364)
python3 sensors/lidar_hesai/hesai_demo.py --seconds 10
# 速腾 .202 / .205(默认 RSAIRY / .202 真实端口)
python3 sensors/lidar_robosense/robosense_demo.py
python3 sensors/lidar_robosense/robosense_demo.py --ip 192.168.1.205 --msop 6695 --difop 7785
# Livox HAP .100(主动查询式, 静态嗅探无流量属正常)
python3 sensors/lidar_livox/livox_demo.py --seconds 15
# 图漾结构光 .114
python3 sensors/structured_light/percipio_demo.py -n 6
```

### 4.3 可视化(见 `tools/`)
```bash
python3 tools/view_depth.py data/fm815_114/depth_0003.png        # uint16 mm 黑图 → 归一化彩色
python3 tools/view_depth.py data/fm815_114/ --cmap turbo         # 整目录批量
python3 tools/view_cloud.py data/fm815_114/                      # 多帧点云 ←/→ 翻帧, 空格播放
python3 tools/view_cloud.py data/hesai_qt128/ --backend auto     # 优先 open3d, 缺则 matplotlib
```

## 5. `data/` 布局

```
data/
├── <tag_时间戳>/            # 协同采集(record.py)的一次 run
│   ├── cam_hik/            #   每路一个子目录
│   │   ├── *.jpg
│   │   └── manifest.jsonl  #   每帧一行: sensor/ts/frame/bytes/payload
│   ├── lidar_hesai/  ... 
│   ├── index.csv            #   全帧时间轴(ts, sensor, payload), 按 ts 排序
│   └── align.csv            #   以相机为基准的跨传感器最近邻对齐(可选)
├── camera_107/  fisheye_99/  hesai_qt128/  robosense_202/  robosense_205/  livox_hap/  fm815_114/
│                            # 单设备 demo 直存的扁平目录(见 §2)
└── fm815_114/{depth_*.png(mm), color_*.jpg, points_*.pcd(米+rgb), *_vis.png(深度彩色版)}
```

## 6. 工具链(跨 SDK 通用, 关键)

- **Python**:必须用 anaconda 的 `python3`。系统另有 VSCode 默认选中的裸 `python3.14`(无依赖),用它跑会 `ModuleNotFoundError`。终端 `python3` 即 anaconda。
- **编译器**:GCC 11(Ubuntu 22.04)。⚠️ 速腾 `rslidar_sdk` 等老 SDK 在 GCC11 下用 `shared_ptr` 却没 `#include <memory>` → 加 `-DCMAKE_CXX_FLAGS="-include memory"`。
- **系统依赖**:`libpcap-dev`(速腾)、系统 `opencv` 4.5.4(图漾 Camport4 用)、`cmake`。
- ⚠️ **PCL/VTK 链接坏**:本机有 PCL 头,但 22.04 上 VTK↔libtiff 冲突,任何**链接 PCL 的工具**(如禾赛 `pcl_tool`)都链接失败。**解法:不依赖 PCL,自写回调直接产 ASCII PCD**(禾赛 `sample_pcd`、Livox `pcd_saver`)。

## 7. SDK 编译与改动(概要)

每条 SDK 的**来源/版本/commit/本地改动**详记于 [`third_party/SOURCES.md`](third_party/SOURCES.md);
每台设备的**采集方案/前置/构建/运行/输出/SDK 改动逐文件说明**见 `sensors/<kind>/README.md`。概要:

| SDK | 设备 | 编译产物 | 本地改动 |
|---|---|---|---|
| HCNetSDK V6.1.9.4 | .107/.99 | 预编译 `.so`,免编译 | 无(ctypes 加载) |
| HesaiLidar_SDK_2.0 | .201 | `build/sample_pcd` | +`test/test_pcd.cc`(回调直写 ASCII PCD 绕 PCL)+ CMakeLists |
| rslidar_sdk v1.5.20 | .202/.205 | `src/rs_driver/build_rs/tool/rs_driver_pcdsaver` | 无源码改(仅 cmake flag `-include memory`, 只编 rs_driver 免 ROS) |
| Livox-SDK2 | .100 | `build/samples/livox_lidar_pcd_saver/...` | +`livox_lidar_pcd_saver/`(回调按 50000 点切帧写 PCD)+ CMakeLists |
| camport4 R4.2.11 | .114 | `sample/build/bin/SimpleView_CaptureDump` | +`SimpleView_CaptureDump/main.cpp`(无头采集: depth+color+点云, 两遍法写 PCD)+ CMakeLists |

关键编译命令见各设备 README 与 SOURCES.md。

## 8. 深度图看起来很黑?——正常

图漾 `depth_*.png` 是 **uint16、单位 mm**。普通图片查看器看着几乎全黑,三因:
1. 有效深度 560–4160mm 只占 uint16(0–65535)低位一小段,8bit 线性映射后仍暗;
2. 有效像素仅 ~7%,其余无效区(depth=0/超量程)= 纯黑;
3. 查看器不按量程归一化。

**数据本身是好的**:同帧 `points_*.pcd` 有 ~2 万个有效点(z≈0.56–4.16m)即证。正确查看:
`python3 tools/view_depth.py <depth.png>`(按 [400,4500]mm 归一化 + jet/turbo 上色,无效留黑)。

## 9. 扩展指南(加一种新传感器)

1. 在 `sensors/<kind>/` 写一个驱动,继承 `Sensor`(进程内 poll)或 `SubprocessSensor`(外部二进制):
   - poll 型:实现 `connect/start/grab/stop`(参考 `sensors/camera/hik_driver.py`)。
   - 子进程型:实现 `_binary/_build_cmd/_env/_duration/_frame_glob` 五个钩子(参考任一 LiDAR driver)。
2. 在 `acquire/registry.py` 的 `TABLE` 登记一行 `(kind, model) → (impl, cls)`。
3. 在 `config/rig.yaml` 加一条设备(name/kind/model/ip/端口/`enabled: true`)。
4. (可选)写一个 `*_demo.py` 薄壳:CLI → spec → 实例化 driver → `capture_once()`。

## 10. 踩坑清单

1. **目的 IP/端口逐台在设备网页改**:雷达不跟随采集机。多为非默认:QT128=2364(非2368)、.202=6692/7782、.205=6695/7785、Livox HAP=56000 系(非 Mid-360 的 56100 系)。**以设备网页实际值为准**。
2. **Livox-SDK2 主动查询式**:静态嗅探无流量属正常,必须跑 SDK。
3. **GCC11 + 老 SDK**:加 `-DCMAKE_CXX_FLAGS="-include memory"`。
4. **PCL/VTK 链接坏**:别用链接 PCL 的工具,自写 ASCII PCD 回调。
5. **速腾顶层编不过**:只编 `src/rs_driver/`(关 ROS)。
6. **RSAIRY vs RSFAIRY**:同包不同垂直角表,按硬件/生产配置选;默认 RSAIRY。
7. **HAP frame_cnt 恒 0**:按点数(50000)切片分帧。
8. **海康通道**:SDK 逻辑通道从 1 起,RTSP/ISAPI 是 101/102。
9. **图漾 SDK**:用 Camport4(V4 API),非 VcameraSDK、非 Camport3。
10. **凭证**:仅海康相机需登录(`admin` / `b@light2.`);LiDAR/结构光走 UDP/SDK 主动查询,无凭证。

## 11. 仓库结构

```
data_acquire/
├── config/rig.yaml           # 设备清单(配置驱动核心)
├── acquire/                  # 编排层
│   ├── registry.py           #   (kind, model) → 驱动 派发表
│   └── record.py             #   协同采集主程序(多路并发 + manifest + 对齐)
├── sensors/                  # 统一接口 + 各厂商驱动
│   ├── base.py               #   Sensor / SubprocessSensor / Sample / capture_once
│   ├── camera/               #   海康: sdk_grabber + hik_driver + grab_demo
│   ├── lidar_hesai/          #   禾赛: hesai_driver + hesai_demo
│   ├── lidar_robosense/      #   速腾: robosense_driver + robosense_demo
│   ├── lidar_livox/          #   Livox: livox_driver + livox_demo + hap/mid360 json
│   └── structured_light/     #   图漾: percipio_driver + percipio_demo
├── tools/                    # 离线查看
│   ├── view_depth.py         #   uint16 mm 深度图 → 归一化彩色
│   └── view_cloud.py         #   多帧点云 ←/→ 翻帧(open3d / matplotlib)
├── third_party/              # 厂商 SDK(自包含; 来源/改动见 SOURCES.md)
└── data/                     # 采集输出(.gitignore)
```

## 12. 进度

- ✅ **7 台全部可达 + 全部已采到真数据**:.99 / .107 / .201 / .202 / .205 / .100 / .114。
- ✅ **统一框架重构完成**:`Sensor`/`SubprocessSensor` 抽象 + `(kind,model)` registry + 全 7 路 driver 接入 +
  `record.py` 多路协同采集(manifest/index/align)+ demo 薄壳化 + 可视化工具。
- ✅ 已知 bug 修复:Hesai demo 改用产 PCD 的 `sample_pcd`(原误用只统计的 `sample`);RoboSense 输出落 `data/`。
