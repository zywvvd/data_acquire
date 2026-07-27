# third_party 来源登记表

> 这张表的存在原因:本目录各厂商 SDK 原本是从 GitHub clone 的(自带 `.git`)。为把"我们对每个 SDK 的
> 探索性修改"纳入本仓库主历史、并保持单仓库自包含,已(将)删除各 SDK 的 `.git`。删 `.git` 会丢掉
> "这个库从哪来、什么版本、哪个 commit"的溯源信息——本表把这些信息**固化**下来,任何时候都能用
> `git clone <url> && git checkout <commit>` 精确还原到我们当初拉取的状态,再把本表记录的本地改动重新打上。
>
> **本地改动列是探索状态的核心**:它记录我们对每个 upstream 做了什么、为什么,回归 upstream 或排查时据此对照。

## 速查表

| 目录 | 用途 / 对应设备 | 来源 | 我们基于的版本 | 本地改动 | 状态 |
|---|---|---|---|---|---|
| `camport4/` | 图漾结构光 .114 (FM815-IX-E1) | github `percipioxyz/camport4` | `R4.2.11` @ `e50fa3ee` (main) | 加 `SimpleView_CaptureDump` + 改 sample CMakeLists | ✅ 在用 |
| `HesaiLidar_SDK_2.0/` | 禾赛 QT128 .201 | github `HesaiTechnology/HesaiLidar_SDK_2.0` | `v2.0.12` @ `534c7078` (master) | 加 `test/test_pcd.cc` + 改 CMakeLists | ✅ 在用 |
| `Livox-SDK2/` | Livox HAP .100 | github `Livox-SDK/Livox-SDK2` | `v1.3.1` @ `f5d9375f` (master) | 加 `livox_lidar_pcd_saver/` + 改 samples CMakeLists | ✅ 在用 |
| `rslidar_sdk-v1.5.20/` | 速腾 RSAIRY .202/.205 | github `RoboSense-LiDAR/rslidar_sdk` release **v1.5.20** (zip 解压, 无 .git) | v1.5.20 | 无源码改动(仅 cmake flag 编译) | ✅ 在用 |
| `EN-HCNetSDKV6.1.9.4_build20220412_linux64/` | 海康相机 .107 / 鱼眼 .99 | 海康官方 HCNetSDK **V6.1.9.4 build20220412** (预编译, 无 .git) | V6.1.9.4 / 2022-04-12 | 无(ctypes 直接加载 .so) | ✅ 在用 |
| `Camport3/` | (图漾旧版 API) | github `percipioxyz/camport3` | `v1.6.75` @ `165eeb12` (master) | 无 | ❌ 弃用 → 已被 camport4 取代 |
| `Livox-SDK/` | (Livox v1, 不支持 HAP/Mid-360) | github `Livox-SDK/Livox-SDK` | `v2.3.0` @ `9306596a` (master) | 无实质改动 | ❌ 弃用 → 已被 Livox-SDK2 取代 |

---

## 在用库详记

### camport4 — 图漾结构光(.114 FM815-IX-E1)
- **来源**:`https://github.com/percipioxyz/camport4`(下载渠道已确认 2026-07)。
- **版本**:tag `R4.2.11`,commit `e50fa3ee4ce965d46e07382dbdaa0eee71861eb6`(main, 2026-03-27 "update to SDK R4.2.11")
- **预编译库**:`lib/linux/lib_x64/libtycam.so.4.2.11` + `libtyimgproc.so.1.1.0`(仓库自带,非系统安装)
- **本地改动**:
  - `sample/sample_v1/CMakeLists.txt`:`ALL_SAMPLES` 列表追加 `SimpleView_CaptureDump`(使其被 foreach 自动编译)。
  - 新增 `sample/sample_v1/SimpleView_CaptureDump/main.cpp`:**无头采集 demo**。仿 `SimpleView_FetchFrame`/`SimpleView_Point3D` 但去 GUI/键盘,取 N 帧各落 `depth_%04d.png`(uint16 mm)、`color_%04d.jpg`(原分辨率 BGR)、`points_%04d.pcd`(ASCII,米,带 rgb)。点云:`TYMapRGBImageToDepthCoordinate` → `TYMapDepthImageToPoint3d`;`write_pcd` 两遍法先数有效点再写,`POINTS` 头与行数一致。
- **重新获取**:
  ```bash
  git clone https://github.com/percipioxyz/camport4.git
  cd camport4 && git checkout e50fa3ee
  # 然后把上面两处本地改动重新打上(见本仓库 sensors/structured_light/percipio_demo.py 与本表)
  ```

### HesaiLidar_SDK_2.0 — 禾赛 QT128(.201)
- **来源**:`https://github.com/HesaiTechnology/HesaiLidar_SDK_2.0`(原 remote 是 SSH `git@github.com:...`,公开仓库,HTTPS 同样可 clone)
- **官方下载页**:`https://www.hesaitech.com/downloads/`(固件 / 手册 / SDK 汇总;github 用于回到我们拉取的精确版本,官网用于取最新或配套资料)
- **版本**:tag `v2.0.12`,commit `534c707846a810e8211b93446f878dbf415f7000`(master, 2026-04-27)
- **本地改动**:
  - `CMakeLists.txt`:在 `if(NOT DISENABLE_TEST_CC)` 段加 `add_executable(sample_pcd test/test_pcd.cc)` 并链 `hesai_sdk_lib`。
  - 新增 `test/test_pcd.cc`:仿 `test.cc`,但 `lidarCallback` 回调**直接写 ASCII PCD**(点类型 `LidarPointXYZICRT`),输出目录走环境变量 `PCD_OUT`。**目的:绕开 Ubuntu 22.04 上 VTK/PCL/libtiff 链接冲突——链接 PCL 的 `pcl_tool` 编不过。**
- **重新获取**:
  ```bash
  git clone https://github.com/HesaiTechnology/HesaiLidar_SDK_2.0.git
  cd HesaiLidar_SDK_2.0 && git checkout 534c7078
  ```

### Livox-SDK2 — Livox HAP(.100)
- **来源**:`https://github.com/Livox-SDK/Livox-SDK2`
- **版本**:tag `v1.3.1`,commit `f5d9375f84efe2b15bc0a052d3e18482ed13adf4`(master, 2026-04-15)
- **本地改动**:
  - `samples/CMakeLists.txt`:在 `livox_lidar_quick_start` 后加 `add_subdirectory(livox_lidar_pcd_saver)`。
  - 新增 `samples/livox_lidar_pcd_saver/{main.cpp,CMakeLists.txt}`:仿 `livox_lidar_quick_start` 的 init/Normal 模式流程,**点云回调按帧写 ASCII PCD**。点格式 `LivoxLidarCartesianHighRawPoint`(int32 xyz mm + reflectivity),mm→m。**关键:HAP `frame_cnt` 恒 0 不能分帧,改按每 50000 点切一帧(~10Hz)。** 环境变量 `PCD_OUT` / `LIVOX_RUN_SECS`。
- **重新获取**:
  ```bash
  git clone https://github.com/Livox-SDK/Livox-SDK2.git
  cd Livox-SDK2 && git checkout f5d9375f
  ```

### rslidar_sdk-v1.5.20 — 速腾 RSAIRY(.202/.205)
- **来源**:`https://github.com/RoboSense-LiDAR/rslidar_sdk`,release **v1.5.20**(下载 zip 解压,故无 `.git`)。下载渠道已确认(2026-07)= 该 GitHub 仓库。
- **本地改动**:**无源码改动**。只在其 `src/rs_driver/` 下单独编译(顶层 `rslidar_sdk_node` 需 ROS 编不过,故只编免 ROS 的 `rs_driver` 子目录),编译时加 `-DCMAKE_CXX_FLAGS="-include memory"`(GCC11 老代码缺 `<memory>`)与 `-DCOMPILE_TOOL_PCDSAVER=ON`。
- **重新获取**:从 GitHub release 页下载 `rslidar_sdk-1.5.20.zip` 解压;或
  ```bash
  git clone https://github.com/RoboSense-LiDAR/rslidar_sdk.git rslidar_sdk-v1.5.20
  cd rslidar_sdk-v1.5.20 && git checkout v1.5.20
  ```

### EN-HCNetSDKV6.1.9.4_build20220412_linux64 — 海康相机(.107)/鱼眼(.99)
- **来源**:海康威视官方 HCNetSDK,**V6.1.9.4,build 20220412**(预编译,无 `.git`)。官方下载页 `https://www.hikvision.com/us-en/support/download/sdk/`(2026-07 确认)。
- **本地改动**:无。`sensors/camera/sdk_grabber.py` 用 ctypes 按绝对路径加载 `lib/libhcnetsdk.so`。
- **必备文件**:`lib/` 下需含 `libhcnetsdk.so`、`HCNetSDKCom/`、`libcrypto.so.1.1`、`libssl.so.1.1`、`libPlayCtrl.so`。
- **重新获取**:从官方下载页 `https://www.hikvision.com/us-en/support/download/sdk/` 取 HCNetSDK(Linux64)对应版本;部分版本可能需登录海康账号。

---

## 弃用库(建议删除, 保留可重新获取)

### Camport3 — 图漾旧版 V3 API
- **来源**:`https://github.com/percipioxyz/camport3`,tag `v1.6.75` @ `165eeb12`
- **弃用原因**:`.114` 实测用 **Camport4(V4 API `TYApi.h`)**,V3 已不用。占 131M。
- **若将来需要**:`git clone https://github.com/percipioxyz/camport3.git && git checkout v1.6.75`(V3→V4 API 迁移文档见仓库内 `API_DIFF_V3_V4.md`)。

### Livox-SDK — Livox v1
- **来源**:`https://github.com/Livox-SDK/Livox-SDK`,tag `v2.3.0` @ `9306596a`(下载渠道已确认 2026-07)。
- ⚠️ **这是 v1,与在用的 `Livox-SDK2`(`https://github.com/Livox-SDK/Livox-SDK2`)是两个不同仓库,别混淆。** .100 HAP 实际用的是 SDK2(见上)。
- **弃用原因**:不支持 HAP/Mid-360,且 GCC11 下缺 `<memory>` 编不过。已被 `Livox-SDK2` 取代。占 22M。
- **若将来需要**:`git clone https://github.com/Livox-SDK/Livox-SDK.git && git checkout v2.3.0`。

---

## 设备官方资料(产品页 / 规格 / 手册)

> 设备层的官方资料入口(型号确认、规格、手册),与上方「SDK 来源」互补。

- **速腾 RSAIRY(.202/.205)** = RoboSense **Airy**,产品页 `https://www.robosense.ai/IncrementalComponents/Airy`。型号由三方印证:官方产品页 + 9 型 decoder head-to-head 实测 + `bolight_alg` 生产配置。
- **图漾 FM815-IX-E1(.114)**:规格书 / 用户手册 `https://www.percipio.xyz/services-support/technical-document?type=50&kw=FM855-E1`(2026-07)。
  ⚠️ **型号差异**:机壳/采购标签写 **FM855-E1**,SDK `ListDevices` 实报 **FM815-IX-E1**(本仓以 SDK 实测为准);官网手册页按 `FM855-E1` 关键字检索可命中。
  - 通用技术文档(Camport SDK / API / 用法):`https://doc.percipio.xyz/cam/latest/`(开发参考)。
- *(待补)* Livox HAP(.100) / 禾赛 QT128(.201) / 海康相机(.107)·鱼眼(.99) 的产品页或规格手册入口。

---

## 待补充(用户后续提供)

> 以下信息删 `.git` 后无法从仓库内恢复,需要用户确认/补充,便于将来重新获取或溯源:

- [x] **海康 HCNetSDK 官方下载入口**:`https://www.hikvision.com/us-en/support/download/sdk/`(用户 2026-07 确认)。
- [x] **速腾 rslidar_sdk v1.5.20 下载来源**:`https://github.com/RoboSense-LiDAR/rslidar_sdk`(GitHub,用户 2026-07 确认)。
- [x] 各设备 **登录凭证**:采集所需的只有海康相机(.107/.99),用户 `admin` / 密码 `b@light2.`(已在 `sensors/camera/sdk_grabber.py` 等硬编码,密码含 `@`)。禾赛 / 速腾 / Livox / 图漾 走 UDP 或 SDK 主动查询,**采集无需登录凭证**(各设备网页管理口若有密码,非采集依赖)。
- [ ] 其它用户补充:_________________________________________
