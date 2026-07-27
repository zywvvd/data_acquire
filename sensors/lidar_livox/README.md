# lidar_livox — Livox HAP(.100)

Livox(大疆子公司)半固态激光雷达。实测型号 **HAP**(机壳标 "HAP (TX)",SDK 报 `dev_type=10` IndustrialHAP,
SN `5CWD239F4105YV1`)。走 **Livox-SDK2**(支持 HAP/Mid-360;老 v1 不支持,已弃用),**自加 `livox_lidar_pcd_saver`**
样例把点云按帧写成 ASCII PCD。

## 设备信息

- IP `192.168.1.100`;MAC OUI `48:1c:b9`(SZ DJI → Livox)。
- 端口(HAP):cmd `56000` / point `57000` / imu `58000` / log `59000`(⚠️ 与 Mid-360 的 56100 系**完全不同**)。
- 量级:~45.4 万点/s;HAP `frame_cnt` 实测恒 0,故按**每 50000 点切一帧**(约 10Hz)。

## 采集方案

子进程**流式限时自停型**(`LivoxSensor`):`start()` 用 `Popen` 拉起 `livox_lidar_pcd_saver`,SDK **主动查询式**
发现雷达并置 Normal,点云回调累积 CartesianHigh(int32 xyz mm)点,每满 50000 点写一帧 `%05d.pcd`;
环境变量 `LIVOX_RUN_SECS` 到点子进程**自己退出**。

## 流程要点

1. **主动查询式发现**:Livox-SDK2 是 SDK 先广播查询、雷达应答,**不像禾赛/速腾被动持续推流**。
   所以**静态 UDP 嗅探看不到流量是正常的**,必须跑 SDK 才出数据。
2. **配置 json**:驱动按 `spec.model` 选模板(HAP→`hap_host200.json`、Mid-360→`mid360_host200.json`),
   并把 `host_net_info.host_ip` 渲染成采集机 IP(`spec.host_ip`)写到 `out_dir/device.json`。
3. **环境变量**:驱动注入 `LD_LIBRARY_PATH=<sdk>/build/sdk_core`、`PCD_OUT=out_dir`、`LIVOX_RUN_SECS=duration`。
4. **HAP frame_cnt 恒 0**:不能用它分帧;saver 改按累积点数(50000)切帧。

## 构建 SDK

```bash
cd third_party/Livox-SDK2 && mkdir -p build && cd build
cmake .. && make livox_lidar_pcd_saver -j   # -> build/samples/livox_lidar_pcd_saver/livox_lidar_pcd_saver (+ .so)
```
GCC11 直接编过(比老 v1 干净)。

## 运行

```bash
# 单设备 demo(委托 LivoxSensor, 默认 HAP -> data/livox_hap/)
python3 sensors/lidar_livox/livox_demo.py --seconds 15
python3 sensors/lidar_livox/livox_demo.py --model "Mid-360" --out data/livox_mid360
# 协同采集
python3 acquire/record.py --duration 15
```

## 输出

`%05d.pcd`(ASCII),`FIELDS x y z intensity`(xyz float 米,intensity float);每帧 ~50000 点。

## SDK 改动(逐文件, 详见 [SOURCES.md](../../third_party/SOURCES.md#livox-sdk2--livox-hap100))

- **`samples/livox_lidar_pcd_saver/{main.cpp,CMakeLists.txt}`**(新增):仿官方 `livox_lidar_quick_start` 的
  init / Normal 模式流程,点云回调按帧写 ASCII PCD;点格式 `LivoxLidarCartesianHighRawPoint`(int32 xyz mm + reflectivity),
  存盘 mm→m。**关键:HAP `frame_cnt` 恒 0,改按每 50000 点切一帧。** 环境变量 `PCD_OUT` / `LIVOX_RUN_SECS`。
- **`samples/CMakeLists.txt`**:加 `add_subdirectory(livox_lidar_pcd_saver)`。

## 关键文件

- `livox_driver.py` — `LivoxSensor(SubprocessSensor)`:`_cfg_path()` 按 model 选模板并渲染 host_ip;`_env` 注入三变量。
- `livox_demo.py` — 单设备 demo 薄壳(`--model` 选 HAP / Mid-360)。
- `hap_host200.json` / `mid360_host200.json` — 配置模板(HAP / Mid-360, 端口不同)。

## FAQ

- 静态嗅探(tcpdump/wireshark)看不到流量:正常,SDK 主动查询式,直接跑 demo/record。
- 0 帧:确认 `host_net_info.host_ip` = 采集机 IP、雷达与采集机同子网、型号模板选对(HAP vs Mid-360)。
