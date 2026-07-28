# structured_light — 图漾 Percipio FM815-IX-E1(.114)

图漾(Percipio)结构光 3D 相机。GigE Vision 接口,经广播发现。走 **Camport4**(V4 API `TYApi.h`);
**自编无头采集 sample `SimpleView_CaptureDump`**,取 N 帧各落 depth + color + 点云。

## 设备信息

- IP `192.168.1.114`;GigE Vision,SN `207000147291`,SDK `ListDevices` 实报型号 **FM815-IX-E1**
  (机壳/采购标签写 FM855-E1,以 SDK 实测为准)。接口代际 **Gige_2_0**(HW 1.3.0 / FW 3.13.70,
  `DumpAllFeatures` 实测:LASER 组件 + LASER_POWER/AUTO_CTRL 可读写)——走旧 `TYSetInt/TYSetBool` API,
  非 Gige_2_1;故 SDK 对 LASER/IR 的设置全部有效。
- 量级:IR 原生 1280×960(双目), depth 默认采 **1280×960** 满分辨率(640×480 是其降采样)、
  color 2560×1920。满分辨率下单帧 **~40 万有效点**(摆位填满甜区时;平放桌面前景过近会跌到 ~7%)。
  **工作量程 ≈ 0.59–4.4m**(由视差搜索范围 + 基线 99.89mm + 焦距几何决定, 非规格书标称;
  推导见 [STRUCTURED_LIGHT.md](STRUCTURED_LIGHT.md))。

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

# 拍真散斑图(IR-only, 直跑二进制; 投射器同步给 IR 流才照亮, 详 STRUCTURED_LIGHT.md §8):
LD_LIBRARY_PATH=third_party/camport4/lib/linux/lib_x64 \
  third_party/camport4/sample/build/bin/SimpleView_CaptureDump \
  -ip 192.168.1.114 -n 2 -nodepth -color=off -laser 100 -ire 80 -outdir data/fm815_114
```

## 输出

每帧四件(同编号):
- `depth_%04d.png` — uint16,**单位 mm**(有效值约 558–4164mm, 见上工作量程);
- `color_%04d.jpg` — 原分辨率 BGR(RGB 相机原始可见光, 仅上色, 不参与测距);
- `points_%04d.pcd` — ASCII,`FIELDS x y z r g b`,**单位米**;
- `points_%04d.ply` — **binary**,`float xyz + uchar rgb`,**单位米**,与同帧 PCD 同源(点数/坐标/颜色逐点一致)。
  **CloudCompare 看点云用它**:本机 CloudCompare(2.11 apt)未带 PCL/PDAL,不认 `.pcd`(`unhandled extension`),
  而 PLY 是其核心一等格式。

**关于 IR 散斑图**(重要, 详见 [STRUCTURED_LIGHT.md](STRUCTURED_LIGHT.md) §8):`-ir` / `ir: true`
和 depth **同开**时,激光同步绑给了 depth,IR 组件取到灭灯相位 → 存出的 `ir_*.png` 是 **max≈14 的暗帧,
不含散斑**(gain 也无效)。**要拿真散斑图必须 IR-only 模式**(`-nodepth` 只开 IR,见上「运行」末尾),
此时投射器同步给 IR 流,IR 帧全亮、可见高密度随机点散斑。即:`-ir` 同开得暗帧,`-nodepth` 单开得真散斑。

## 深度图看起来很黑?——正常

`depth_*.png` 是 uint16(mm),普通查看器看着全黑(有效值只占 uint16 低位 + 93% 无效区=0 + 不归一化)。
**数据有效**(同帧 PCD 有 ~2 万有效点为证)。正确查看:
```bash
python3 tools/view_depth.py data/fm815_114/depth_0003.png   # 按 [400,4500]mm 归一化 + jet 上色
python3 tools/view_cloud.py data/fm815_114/                  # 多帧点云翻帧
```

## SDK 改动(逐文件, 详见 [SOURCES.md](../../third_party/SOURCES.md#camport4--图漾结构光114-fm815-ix-e1))

- **`sample/sample_v1/SimpleView_CaptureDump/main.cpp`**(新增):无头采集,仿 `SimpleView_FetchFrame`/`Point3D`
  但去 GUI/键盘。每帧落 `depth_%04d.png`(uint16 mm)/ `color_%04d.jpg` / `points_%04d.pcd` / `points_%04d.ply`。
  `write_pcd` **两遍法**(先数有效点,depth=0 投影为 NaN)使 `POINTS` 头与数据行一致;点云 `/1000` 转米,
  `TYMapRGBImageToDepthCoordinate`+`TYMapDepthImageToPoint3d`。`write_ply` 与 `write_pcd` **同源**(同一份点数组/颜色,
  逐点镜像),写 binary PLY(`float xyz + uchar rgb`),保证两者点数/坐标/颜色逐点一致(实测 xyz 最大差=PCD `%.4f`
  舍入 0.05mm,rgb 全等);存在理由=本机 CloudCompare 不认 `.pcd`,PLY 兜底(详见 [SOURCES.md](../../third_party/SOURCES.md))。
  扩展诊断/调参开关: `-dmode 1280`(满分辨率深度, 默认)/ `-ir`(同开左右 IR——⚠与 depth 同开得暗帧,见§输出)/
  `-ire/-irg`(IR 曝光·增益)/ `-uniq/-nolrc`(放宽 SGBM 换密度)/ **`-laser <0..100>` + `-lauto <0|1>`**(散斑投射器
  功率/频闪;破案见 [STRUCTURED_LIGHT.md](STRUCTURED_LIGHT.md) §8)/ **`-nodepth`**(纯 IR 拍真散斑)/
  `-irflash`(IR 泛光灯, 本设备无)。每帧统计深度有效率(对比 LASER 开关的判据)。每次启动**锁定 IR gain=32**、
  打印 `LASER now: power=X auto=Y`(设备会持久化残留, 不锁会被污染致深度归零)。
- **`sample/sample_v1/CMakeLists.txt`**:`ALL_SAMPLES` 列表追加 `SimpleView_CaptureDump`(被 foreach 自动编译)。

## 关键文件

- `percipio_driver.py` — `PercipioSensor(SubprocessSensor)`:批量型(`_duration()` 返回 None);`_build_cmd` 拼
  `-ip/-n/-dmode(默认1280)/-outdir`,按 spec 透传 `-noalign` / `-ir`(同开左右 IR——⚠与 depth 同开得暗帧,
  非真散斑;真散斑用 `-nodepth` 单开,见§输出/STRUCTURED_LIGHT §8);`_frame_glob="points_*.pcd"`。
- `percipio_demo.py` — 单设备 demo 薄壳。

## FAQ

- **三个镜头是什么?是双目结构光吗?** 是。本设备经 `DumpAllFeatures` 实测 = **主动双目结构光**
  (接口代际 **Gige_2_0**,HW1.3.0/FW3.13.70):1 个 IR 散斑投射器 + 左右 2 个 IR 相机(做 SGBM
  立体匹配)+ 1 个 RGB(仅上色)。深度由左右 IR 的视差算出,SDK 把解算融合成一路 DEPTH 输出。
  成像原理、深度计算、全部佐证见 [STRUCTURED_LIGHT.md](STRUCTURED_LIGHT.md)。
  (早先「结构光≠双目」的说法不准确,已据此更正。)
- **散斑投射器发不发射?`-ir` 存的 IR 帧为什么全黑?** 投射器**正常发射**(关掉它 `-laser 0` 深度有效率
  从 33% 跌到 2%,是深度命脉)。IR 帧全黑**不是故障**:`-ir` 和 depth 同开时,激光同步绑给了 depth,
  IR 组件取到灭灯相位的暗电平读出(max≈14,gain 也无效)。**要拍真散斑得 IR-only 模式**(`-nodepth`
  只开 IR,投射器转而同步给 IR 流 → IR 帧全亮)。完整排障记录见 [STRUCTURED_LIGHT.md](STRUCTURED_LIGHT.md) §8。
- 深度图全黑:正常,见上「深度图看起来很黑」。
- 用 Camport4(V4 API),**不是** VcameraSDK(已删)、也不是老 Camport3。
- 找不到设备:确认 `.114` 与采集机同子网、GigE Vision 广播可达(跑 `ListDevices` 验证)。
