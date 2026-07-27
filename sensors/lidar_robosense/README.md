# lidar_robosense — 速腾 RoboSense RSAIRY(.202 / .205)

两台速腾半固态机械激光雷达(机壳 Robosense Airy)。走 **rslidar_sdk v1.5.20** 的 `rs_driver` 子目录
(顶层 `rslidar_sdk_node` 需 ROS 编不过,只编免 ROS 的 `rs_driver`),用 `rs_driver_pcdsaver` 按帧存 PCD。

## 设备信息

| | 前雷达 | 后雷达 |
|---|---|---|
| IP | 192.168.1.202 | 192.168.1.205 |
| MAC | 08:48:57:02:11:9c | 08:48:57:04:cf:13 |
| msop / difop | 6692 / 7782 | 6695 / 7785 |
| 型号 | **RSAIRY**(经 9 型 head-to-head + bolight 生产配置确认) | RSAIRY |

> MSOP 头 `55aa055a` + V2 头部。RSAIRY 与 RSFAIRY 同包不同垂直角表(SDK 无法从包内区分):RSAIRY z~6m、
> RSFAIRY z~26m。默认 RSAIRY;若硬件实为 RS-Fairy,`--type RSFAIRY`。

## 采集方案

子进程**流式型**(`RobosenseSensor`):`start()` 用 `Popen`(cwd=`out_dir`)拉起 `rs_driver_pcdsaver`,
按帧把 PCD 写到 cwd(=`out_dir`);在线流不自停,到 `duration` 由基类 `terminate`。命令行由 spec 的
`rs_type/model`/`msop_port`/`difop_port`/`host_ip` 拼装。

## 流程要点

1. **网页配置**(否则收不到点云):两台网页(http://192.168.1.202 / .205,80)把 Destination IP 指
   `192.168.1.200`;端口错开避免撞口:`.202`→msop 6692/difop 7782、`.205`→msop 6695/difop 7785。
2. **型号必须对**:`-type` 错型要么刷 `ERRCODE_WRONGMSOPBLKID`,要么出几百~几千点的平面垃圾。换别的速腾雷达
   务必重核 `--type`(RS16/32/RSBP/RSHELIOS/RUBY/RSFAIRY/RSAIRY/…)。
3. **host**:命令行 `-host` = 采集机 IP(由 record 注入 `host_ip`,demo 默认 `192.168.1.200`)。

## 构建 SDK

```bash
cd third_party/rslidar_sdk-v1.5.20/src/rs_driver && mkdir -p build_rs && cd build_rs
cmake -DCOMPILE_DEMOS=ON -DCOMPILE_TOOL_PCDSAVER=ON -DCMAKE_CXX_FLAGS="-include memory" ..
make rs_driver_pcdsaver -j        # -> tool/rs_driver_pcdsaver
```
- ⚠️ **只编 `src/rs_driver/`**:顶层 `rslidar_sdk_node` 关 ROS 时引用未声明 ROS 符号,编不过。
- ⚠️ 必须 `-include memory`(GCC11 老代码缺 `<memory>`,见总 README §6)。

## 运行

```bash
# 单设备 demo(委托 RobosenseSensor, 默认 .202 -> data/robosense_202/)
python3 sensors/lidar_robosense/robosense_demo.py
python3 sensors/lidar_robosense/robosense_demo.py --ip 192.168.1.205 --msop 6695 --difop 7785
python3 sensors/lidar_robosense/robosense_demo.py --type RSFAIRY --seconds 20
# 协同采集(两台同时采)
python3 acquire/record.py --duration 10
```

## 输出

`*.pcd`(ASCII),`FIELDS x y z intensity`(米)。点云在**雷达坐标系**,z 值取决于雷达安装姿态与型号配置。

## SDK 改动(详见 [SOURCES.md](../../third_party/SOURCES.md#rslidar_sdk-v1520--速腾-rsairy202205))

**无源码改动**。仅编译时加 cmake flag(`-include memory` 适配 GCC11、`-DCOMPILE_TOOL_PCDSAVER=ON`、只编 `rs_driver` 免 ROS)。

## 关键文件

- `robosense_driver.py` — `RobosenseSensor(SubprocessSensor)`:`_build_cmd` 拼装 `-type/-msop/-difop/-host`,cwd=`out_dir`(PCD 写此)。
- `robosense_demo.py` — 单设备 demo 薄壳。

## FAQ

- 出几千点/平面垃圾 / `WRONGMSOPBLKID`:`--type` 不对,按型号重核。
- z 全相等或量级不对:雷达安装姿态 + 型号垂直角表;确认 `--type` 与硬件一致。
- 编译报 `'shared_ptr' is not a member of 'std'`:缺 `-include memory`。
