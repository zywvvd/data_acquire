# structured_light — 图漾 Percipio FM815-IX-E1(.114)

图漾(Percipio)结构光 3D 相机。GigE Vision 接口,经广播发现。走 **Camport4**(V4 API `TYApi.h`);
**自编无头采集 sample `SimpleView_CaptureDump`**,取 N 帧各落 depth + color + 点云。

## 设备信息

- IP `192.168.1.114`;GigE Vision,SN `207000147291`,SDK `ListDevices` 实报型号 **FM815-IX-E1**
  (机壳/采购标签写 FM855-E1,以 SDK 实测为准)。
- 量级:depth 640×480(mm,量程 0.56–4.16m,有效 ~7%)、color 2560×1920、点云 ~2 万点/帧。

## 采集方案

子进程**批量型**(`PercipioSensor`):`grab()` 首次调用时 `subprocess.run` 同步把 `SimpleView_CaptureDump`
跑完(由 `-n` 控制帧数),采完 N 帧子进程自停;之后逐帧返回 `points_%04d.pcd`(同帧 depth/color 同编号)。
点云:先 `TYMapRGBImageToDepthCoordinate`(彩色贴到深度分辨率)再 `TYMapDepthImageToPoint3d`(depth_calib)。

## 流程要点

1. **发现**:GigE Vision 广播发现(GVCP),`ListDevices` 已确认枚举到 `.114`。
2. **库路径**:驱动自动注入 `LD_LIBRARY_PATH=camport4/lib/linux/lib_x64`(含 `libtycam.so.4.2.11` + `libtyimgproc.so.1.1.0`)。
3. **输出目录**:`-outdir` 由驱动注入 `out_dir` 绝对路径(也可用环境变量 `OUTDIR`)。
4. **无对齐**:`-noalign` 跳过 color→depth 对齐,点云不带色(默认带色)。

## 构建 SDK

```bash
cd third_party/camport4/sample && mkdir -p build && cd build
cmake .. -DTYCam_DIR=$(cd ../.. && pwd) -DARCH=x64 -DBUILD_SAMPLE_V2=OFF -DBUILD_SAMPLE_GENICAM_SFNC=OFF
make SimpleView_CaptureDump -j   # -> sample/build/bin/SimpleView_CaptureDump
```
需系统 opencv(本机 4.5.4)。

## 运行

```bash
# 单设备 demo(委托 PercipioSensor, 默认 -> data/fm815_114/)
python3 sensors/structured_light/percipio_demo.py -n 6
python3 sensors/structured_light/percipio_demo.py --no-align        # 点云不带色
# 协同采集
python3 acquire/record.py --duration 10
# 手动验证设备发现:
cd third_party/camport4 && LD_LIBRARY_PATH=$PWD/lib/linux/lib_x64 ./sample/build/bin/ListDevices
```

## 输出

每帧三件(同编号):
- `depth_%04d.png` — uint16,**单位 mm**(量程 0.56–4.16m);
- `color_%04d.jpg` — 原分辨率 BGR;
- `points_%04d.pcd` — ASCII,`FIELDS x y z r g b`,**单位米**。

## 深度图看起来很黑?——正常

`depth_*.png` 是 uint16(mm),普通查看器看着全黑(有效值只占 uint16 低位 + 93% 无效区=0 + 不归一化)。
**数据有效**(同帧 PCD 有 ~2 万有效点为证)。正确查看:
```bash
python3 tools/view_depth.py data/fm815_114/depth_0003.png   # 按 [400,4500]mm 归一化 + jet 上色
python3 tools/view_cloud.py data/fm815_114/                  # 多帧点云翻帧
```

## SDK 改动(逐文件, 详见 [SOURCES.md](../../third_party/SOURCES.md#camport4--图漾结构光114-fm815-ix-e1))

- **`sample/sample_v1/SimpleView_CaptureDump/main.cpp`**(新增):无头采集,仿 `SimpleView_FetchFrame`/`Point3D`
  但去 GUI/键盘。每帧落 `depth_%04d.png`(uint16 mm)/ `color_%04d.jpg` / `points_%04d.pcd`。
  `write_pcd` **两遍法**(先数有效点,depth=0 投影为 NaN)使 `POINTS` 头与数据行一致;点云 `/1000` 转米,
  `TYMapRGBImageToDepthCoordinate`+`TYMapDepthImageToPoint3d`。
- **`sample/sample_v1/CMakeLists.txt`**:`ALL_SAMPLES` 列表追加 `SimpleView_CaptureDump`(被 foreach 自动编译)。

## 关键文件

- `percipio_driver.py` — `PercipioSensor(SubprocessSensor)`:批量型(`_duration()` 返回 None);`_build_cmd` 拼 `-ip/-n/-outdir`,`_frame_glob="points_*.pcd"`。
- `percipio_demo.py` — 单设备 demo 薄壳。

## FAQ

- **为什么只有一张图,不是左右两个摄像头?** 结构光≠双目。深度由「投射器 + 相机」这对基线**主动**
  打图案三角测量得出,不是两个可见光相机被动匹配视差。SDK 把内部解算**融合成一路 DEPTH 输出**,
  不给原始左右红外帧。故每帧只有:一张 `depth`(3D 结果)、一张 `color`(独立 RGB 纹理相机,仅上色)、
  一个 `points`(由 depth 经内参反投影)。**数据完整,非漏采。** 要看原始红外图案需另开
  `TY_COMPONENT_IR_CAM`(默认未开)。
- 深度图全黑:正常,见上「深度图看起来很黑」。
- 用 Camport4(V4 API),**不是** VcameraSDK(已删)、也不是老 Camport3。
- 找不到设备:确认 `.114` 与采集机同子网、GigE Vision 广播可达(跑 `ListDevices` 验证)。
