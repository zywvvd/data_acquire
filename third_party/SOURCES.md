# third_party 来源登记表

本目录各厂商 SDK 原本从 GitHub clone(自带 `.git`)。为把对每个 SDK 的修改纳入本仓库主历史、
并保持单仓库自包含,已删除各 SDK 的 `.git`。删 `.git` 会丢失"从哪来、什么版本、哪个 commit"的
溯源信息,本表将其固化,可用 `git clone <url> && git checkout <commit>` 还原到拉取时的状态,
再把记录的本地改动重新打上。**本地改动列是核心**:记录对每个 upstream 做了什么、为什么。

## 速查表

| 目录 | 对应设备 | 来源 | 版本 (tag @ commit) | 本地改动 |
|---|---|---|---|---|
| `camport4/` | 图漾结构光 .114 (FM815-IX-E1) | github `percipioxyz/camport4` | `R4.2.11` @ `e50fa3ee` (main) | 加 `SimpleView_CaptureDump` + 改 sample CMakeLists |
| `HesaiLidar_SDK_2.0/` | 禾赛 QT128 .201 | github `HesaiTechnology/HesaiLidar_SDK_2.0` | `v2.0.12` @ `534c7078` (master) | 加 `test/test_pcd.cc` + 改 CMakeLists |
| `Livox-SDK2/` | Livox HAP .100 | github `Livox-SDK/Livox-SDK2` | `v1.3.1` @ `f5d9375f` (master) | 加 `livox_lidar_pcd_saver/` + 改 samples CMakeLists |
| `rslidar_sdk-v1.5.20/` | 速腾 RSAIRY .202/.205 | github `RoboSense-LiDAR/rslidar_sdk` release **v1.5.20** (zip 解压, 无 .git) | v1.5.20 | 无源码改动(仅 cmake flag 编译) |
| `EN-HCNetNetSDKV6.1.9.4...` | 海康相机 .107 / 鱼眼 .99 | 海康官方 HCNetSDK **V6.1.9.4 build20220412** (预编译, 无 .git) | V6.1.9.4 / 2022-04-12 | 无(ctypes 直接加载 .so) |
| `Camport3/` | (图漾旧版 API, 已弃用) | github `percipioxyz/camport3` | `v1.6.75` @ `165eeb12` (master) | 无 |
| `Livox-SDK/` | (Livox v1, 不支持 HAP/Mid-360, 已弃用) | github `Livox-SDK/Livox-SDK` | `v2.3.0` @ `9306596a` (master) | 无实质改动 |

---

## 在用库详记

### camport4 — 图漾结构光(.114 FM815-IX-E1)
- **来源**:`https://github.com/percipioxyz/camport4`
- **版本**:tag `R4.2.11`,commit `e50fa3ee4ce965d46e07382dbdaa0eee71861eb6`(main)
- **预编译库**:`lib/linux/lib_x64/libtycam.so.4.2.11` + `libtyimgproc.so.1.1.0`(仓库自带)
- **本地改动**:
  - `sample/sample_v1/CMakeLists.txt`:`ALL_SAMPLES` 列表追加 `SimpleView_CaptureDump`(被 foreach 自动编译)。
  - 新增 `sample/sample_v1/SimpleView_CaptureDump/main.cpp`:无头采集,仿 `SimpleView_FetchFrame`/
    `SimpleView_Point3D` 但去 GUI/键盘,取 N 帧各落 `depth_%04d.png`(uint16 mm)、`color_%04d.jpg`(原分辨率 BGR)、
    `points_%04d.pcd`(ASCII,米,带 rgb) + `points_%04d.ply`(binary,米,带 rgb)。点云:`TYMapRGBImageToDepthCoordinate`
    → `TYMapDepthImageToPoint3d`;`write_pcd` 两遍法先数有效点再写,`POINTS` 头与行数一致。`write_ply` 与 `write_pcd`
    **同源**(同一份点数组/颜色),逐点判定与 BGR→RGB 转换完全镜像,保证 PLY 与 PCD 点数/坐标/颜色逐点一致
    (实测 xyz 最大差 = PCD `%.4f` 舍入 5e-5m,颜色 uint8 全等)。加 PLY 是为本机 CloudCompare(2.11 apt 未带 PCL/PDAL、
    不认 `.pcd`)兜底——PLY 是其核心一等格式。
  - 诊断/调参开关(均经实测,设备=Gige_2_0、旧 API 有效):`-dmode 1280`(满分辨率深度,默认)/
    `-ire/-irg`(IR 曝光·增益)/ `-uniq/-nolrc`(放宽 SGBM 换密度)/ `-ir`(同开左右 IR——与 depth 同开得灭灯暗帧)/
    **`-laser <0..100>` + `-lauto <0|1>`**(散斑投射器功率/频闪;`-laser` 给值自动关 auto 进手动常亮)/
    **`-nodepth`**(纯 IR 模式:只开 IR 不开 depth,投射器转而同步给 IR 流 → 拍到真散斑)/
    `-irflash`(IR 泛光灯,本设备 `TYHasFeature=false` 即无此件)。每帧末尾打深度有效率、整批打平均有效率
    (LASER 开关的客观判据)。启动时读+打 `LASER now: power=X auto=Y` 并锁定 IR gain=32(设置持久化,
    不锁会被残留污染致深度归零)。投射器/IR 排障全记录见 `sensors/structured_light/STRUCTURED_LIGHT.md` §8。
- **重新获取**:
  ```bash
  git clone https://github.com/percipioxyz/camport4.git
  cd camport4 && git checkout e50fa3ee
  # 再把上述两处本地改动重新打上
  ```

### HesaiLidar_SDK_2.0 — 禾赛 QT128(.201)
- **来源**:`https://github.com/HesaiTechnology/HesaiLidar_SDK_2.0`
- **官方下载页**:`https://www.hesaitech.com/downloads/`
- **版本**:tag `v2.0.12`,commit `534c707846a810e8211b93446f878dbf415f7000`(master)
- **本地改动**:
  - `CMakeLists.txt`:在 `if(NOT DISENABLE_TEST_CC)` 段加 `add_executable(sample_pcd test/test_pcd.cc)` 并链 `hesai_sdk_lib`。
  - 新增 `test/test_pcd.cc`:仿 `test.cc`,但 `lidarCallback` 回调直接写 ASCII PCD(点类型 `LidarPointXYZICRT`),
    输出目录走环境变量 `PCD_OUT`。目的:绕开 Ubuntu 22.04 上 VTK/PCL/libtiff 链接冲突——链接 PCL 的 `pcl_tool` 编不过。
- **重新获取**:
  ```bash
  git clone https://github.com/HesaiTechnology/HesaiLidar_SDK_2.0.git
  cd HesaiLidar_SDK_2.0 && git checkout 534c7078
  ```

### Livox-SDK2 — Livox HAP(.100)
- **来源**:`https://github.com/Livox-SDK/Livox-SDK2`
- **版本**:tag `v1.3.1`,commit `f5d9375f84efe2b15bc0a052d3e18482ed13adf4`(master)
- **本地改动**:
  - `samples/CMakeLists.txt`:在 `livox_lidar_quick_start` 后加 `add_subdirectory(livox_lidar_pcd_saver)`。
  - 新增 `samples/livox_lidar_pcd_saver/{main.cpp,CMakeLists.txt}`:仿 `livox_lidar_quick_start` 的 init/Normal
    模式流程,点云回调按帧写 ASCII PCD。点格式 `LivoxLidarCartesianHighRawPoint`(int32 xyz mm + reflectivity),
    mm→m。HAP `frame_cnt` 恒 0 不能分帧,改按每 50000 点切一帧(约 10Hz)。环境变量 `PCD_OUT` / `LIVOX_RUN_SECS`。
- **重新获取**:
  ```bash
  git clone https://github.com/Livox-SDK/Livox-SDK2.git
  cd Livox-SDK2 && git checkout f5d9375f
  ```

### rslidar_sdk-v1.5.20 — 速腾 RSAIRY(.202/.205)
- **来源**:`https://github.com/RoboSense-LiDAR/rslidar_sdk`,release **v1.5.20**(zip 解压,无 `.git`)。
- **本地改动**:无源码改动。只在其 `src/rs_driver/` 下单独编译(顶层 `rslidar_sdk_node` 需 ROS 编不过,
  故只编免 ROS 的 `rs_driver` 子目录),编译时加 `-DCMAKE_CXX_FLAGS="-include memory"`(GCC11 老代码缺
  `<memory>`)与 `-DCOMPILE_TOOL_PCDSAVER=ON`。
- **重新获取**:从 GitHub release 页下载 `rslidar_sdk-1.5.20.zip` 解压;或
  ```bash
  git clone https://github.com/RoboSense-LiDAR/rslidar_sdk.git rslidar_sdk-v1.5.20
  cd rslidar_sdk-v1.5.20 && git checkout v1.5.20
  ```

### EN-HCNetSDKV6.1.9.4_build20220412_linux64 — 海康相机(.107)/鱼眼(.99)
- **来源**:海康威视官方 HCNetSDK,**V6.1.9.4,build 20220412**(预编译,无 `.git`)。
  官方下载页 `https://www.hikvision.com/us-en/support/download/sdk/`。
- **本地改动**:无。`sensors/camera/sdk_grabber.py` 用 ctypes 按绝对路径加载 `lib/libhcnetsdk.so`。
- **必备文件**:`lib/` 下需含 `libhcnetsdk.so`、`HCNetSDKCom/`、`libcrypto.so.1.1`、`libssl.so.1.1`、`libPlayCtrl.so`。
- **重新获取**:从官方下载页取 HCNetSDK(Linux64)对应版本;部分版本可能需登录海康账号。

---

## 弃用库

### Camport3 — 图漾旧版 V3 API
- **来源**:`https://github.com/percipioxyz/camport3`,tag `v1.6.75` @ `165eeb12`
- `.114` 用 Camport4(V4 API `TYApi.h`),V3 不再用(占 131M,可删)。
- 若需要:`git clone https://github.com/percipioxyz/camport3.git && git checkout v1.6.75`
  (V3→V4 API 迁移文档见仓库内 `API_DIFF_V3_V4.md`)。

### Livox-SDK — Livox v1
- **来源**:`https://github.com/Livox-SDK/Livox-SDK`,tag `v2.3.0` @ `9306596a`
- 注意:这是 v1,与在用的 `Livox-SDK2`(`https://github.com/Livox-SDK/Livox-SDK2`)是两个不同仓库。
  `.100` HAP 用 SDK2。v1 不支持 HAP/Mid-360,且 GCC11 下缺 `<memory>` 编不过(占 22M,可删)。
- 若需要:`git clone https://github.com/Livox-SDK/Livox-SDK.git && git checkout v2.3.0`。

---

## 设备官方资料

设备层官方资料入口(型号确认、规格、手册),与上方 SDK 来源互补:

- **速腾 RSAIRY(.202/.205)** = RoboSense Airy,产品页 `https://www.robosense.ai/IncrementalComponents/Airy`。
  型号由三方印证:官方产品页 + 多型 decoder head-to-head + `bolight_alg` 生产配置。
- **图漾 FM815-IX-E1(.114)**:规格书/用户手册
  `https://www.percipio.xyz/services-support/technical-document?type=50&kw=FM855-E1`。
  机壳/采购标签写 FM855-E1,SDK `ListDevices` 实报 FM815-IX-E1(本仓以 SDK 为准);官网手册页按 FM855-E1 检索。
  通用技术文档(Camport SDK / API / 用法):`https://doc.percipio.xyz/cam/latest/`。
- Livox HAP(.100) / 禾赛 QT128(.201) / 海康相机(.107)·鱼眼(.99) 的产品页或规格手册入口待补。

---

## 凭证

采集所需的登录凭证只有海康相机(.107/.99):`admin` / `b@light2.`(密码含 `@`,硬编码于
`sensors/camera/sdk_grabber.py` 等)。禾赛 / 速腾 / Livox / 图漾 走 UDP 或 SDK 主动查询,采集无需登录凭证。
