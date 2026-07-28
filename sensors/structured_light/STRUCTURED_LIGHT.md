# 结构光成像原理与 FM815-IX-E1 设备实测

本文单独讲清三件事:结构光怎么成像、本设备(FM815-IX-E1, .114)的真实架构、深度如何计算,
以及所有结论的**实测佐证**(取自 `DumpAllFeatures` 特性转储、标定参数、原始 IR 帧、密度对比实验)。
配套脚本 `third_party/camport4/sample/sample_v1/SimpleView_CaptureDump`。

---

## 1. 结构光的两种架构

「结构光」是一个**大类**,核心是「主动投射已知图案 + 相机观察」求深度。按相机数量分两种,
这点必须分清,否则会误判设备:

| | 单目结构光 (monocular) | 双目结构光 / 主动双目 (active stereo) |
|---|---|---|
| 构成 | 1 投射器 + **1** 相机 | 1 投射器 + **2** 相机(立体对) |
| 原理 | 相机看投射图案的**形变**,用「投射器-相机」基线三角测量 | 投射器撒 IR 散斑当**人工纹理**,两相机做**立体匹配**(视差→深度) |
| 典型 | 初代 Kinect、RealSense F200 | RealSense D4xx、Apple TrueDepth、**本设备** |
| 薄弱面 | 受环境光干扰大 | 弱纹理/反光/透明面仍难匹配 |

二者**不互斥**。「双目结构光」就是「结构光 + 立体匹配」的组合——投射器不直接参与测距,
只负责给场景打上人工纹理,让左右两个 IR 相机能匹配上。**本设备属于这一类(下文以实测证明)。**

> 纠正一处早先的过度简化:之前文档写过「结构光≠双目」,不准确。结构光与双目是两个正交维度,
> 组合起来就是主动双目结构光。本设备三个可见镜头 = 左 IR + 右 IR + RGB(投射器是第四个元件,
> 外观也像个镜头),正是主动双目的典型布局。

---

## 2. 本设备的真实架构(实测)

运行 SDK 自带工具 `DumpAllFeatures`(列出设备全部组件与特性),实见 5 个组件:

| 组件 (ID) | 角色 | 关键参数(实测) |
|---|---|---|
| `TY_COMPONENT_LASER` (0x400000) | IR 散斑投射器 | power=100(满), auto_ctrl=1 |
| `TY_COMPONENT_IR_CAM_LEFT` (0x40000) | 左 IR 相机 | 1280×960 mono8, fx=1102.09, exposure≤990, gain∈[0,255] |
| `TY_COMPONENT_IR_CAM_RIGHT` (0x80000) | 右 IR 相机 | 1280×960 mono8, fx=1104.60, 基线 B=99.89mm |
| `TY_COMPONENT_DEPTH_CAM` (0x10000) | SGBM 深度输出 | 模式: 320×240 / **640×480** / **1280×960** |
| `TY_COMPONENT_RGB_CAM_LEFT` (0x100000) | RGB 纹理 | 2560×1920, 仅上色 |

**判定主动双目的铁证:**
- 存在 `TY_COMPONENT_IR_CAM_LEFT` 与 `TY_COMPONENT_IR_CAM_RIGHT` **两个 IR 相机**,且右相机有
  `TY_STRUCT_EXTRINSIC_TO_DEPTH = "rightIR to leftIR extrinsic"`,平移分量 tx = **-99.89mm**(即基线)。
- 深度组件下挂着一整套 `TY_INT_SGBM_*` 参数(`DISPARITY_NUM`、`UNIQUE_FACTOR`、`LRC`、`MEDFILTER`…)。
  **SGBM = Semi-Global Block Matching,经典立体匹配算法。** 深度是「左右 IR 匹配出视差」算出来的,
  不是单相机看图案变形。故确属双目结构光(主动双目)。

RGB 相机与深度解算无关,只负责给点云上色(`TYMapRGBImageToDepthCoordinate`)。

**接口代际 = Gige_2_0**:`TY_COMPONENT_LASER` 下的 `TY_INT_LASER_POWER` / `TY_BOOL_LASER_AUTO_CTRL`
均 readable+writable(access=3),走旧 `TYSetInt/TYSetBool` API(**不是** Gige_2_1 的 GenICam
`LightControllerSelector`/`TYParamGetAccess`)。故 SDK 对 LASER/IR 的设置全部有效,不存在
「接口代际不匹配致 no-op」。HW 1.3.0 / FW 3.13.70。投射器发射验证、IR 帧为何全黑,详 §8。

---

## 3. 深度如何计算(几何推导 + 数值)

### 3.1 公式

双目深度由三角关系得出:

```
        f · B
   Z = ───────
          d
```

- `f`:IR 相机焦距(像素)——左 IR fx = **1102.09 px**(1280 分辨率下)
- `B`:左右 IR 基线 = **99.89 mm**(取自右→左外参)
- `d`:视差(像素),即同一物点在左右图中的水平位置差
- `Z`:物距(深度)

视差越大 → 物体越近;视差越小 → 越远。

### 3.2 视差搜索范围 → 工作量程

SGBM 只在有限视差窗内搜索匹配(实测 `DISPARITY_OFFSET=25`、`DISPARITY_NUM=162`,
故 `d ∈ [25, 187]`)。代入:

```
   最近 Z = f·B/d_max = 1102.09 × 99.89 / 187 ≈ 589 mm ≈ 0.59 m
   最远 Z = f·B/d_min = 1102.09 × 99.89 / 25  ≈ 4407 mm ≈ 4.41 m
```

→ **工作量程 ≈ 0.59–4.4m**。

### 3.3 这解释了「深度值卡在某个范围」的现象

实测深度有效值精确落在 **558–4164mm**,与上面几何推导的 0.59–4.4m 高度吻合——**这不是巧合,
也不是某份规格书,而是视差搜索范围 + 基线 + 焦距共同决定的物理边界**:
- 物体近于 ~0.59m → 视差 > 187(超出搜索窗)→ 匹配失败 → 深度=0(无效)
- 物体远于 ~4.4m → 视差 < 25(超出搜索窗)→ 匹配失败 → 深度=0(无效)

> 历史教训:早先 README 把 0.56–4.16m 当作「规格量程」引用,其实是**从这批数据的有效值上下界
> 反推**的,属循环论证。本文用量程=几何推导纠正之。要改量程,只能改 `DISPARITY_OFFSET/NUM`
> (搜索窗)或换更长基线/焦距的设备。

### 3.4 640×480 是降采样模式

`DEPTH_CAM` 三种模式中,`get_default_image_mode` 默认返回索引 0 = **640×480**,其 fx=522.43,
**正好是原生 1280×960 的 fx(1102.09)的一半**——即 640×480 是从原生 1280×960 **降采样**来的。
真正的满分辨率深度是 **1280×960**(见 §5 实验)。

---

## 4. 为什么点云稀疏,以及如何用对设备

稀疏有四个来源,按可调性排序:

### (a) 场景与量程【影响最大,实测 5 倍】
相机平放桌面时,正下方/前景 <0.59m 的区域**整块无效**(视差超搜索窗)。
实测:同一设备,平放(前景过近)→ 有效率 **6.8%**(≈2 万点);
重新摆位让目标落在 0.6–4m 甜区 → 有效率 **33.5%**(≈10 万点)。**单靠摆位,5 倍提升。**

### (b) 降采样模式【纯赚,4 倍点数】
默认 640×480 是降采样。改 1280×960 后,有效率不变(33.5%→33.7%),**点数 ×4**(10 万→41 万),
精度不降(原生分辨率)。**采集应默认用 1280×960。**

### (c) SGBM 严苛度【密度/精度 trade-off】
默认重精度:`UNIQUE_FACTOR=80` + `LRC=on`(左右一致性,剔除遮挡/误匹配)+ 中值滤波。
放宽(`UNIQUE_FACTOR=80→20`、关 LRC)→ 有效率 33.5%→47.4%,但**引入更多误匹配、丢失遮挡剔除**,
精度下降。要「精确」就保留默认;要「更密」才放宽。

### (d) IR 增益【默认即最优,勿乱动】
- IR 曝光上限 990(已封顶)、增益范围 [0,255]、出厂默认 **gain=32**。
- 实测增益扫描(作用对象是**深度有效率**,即机内喂给 SGBM 匹配的那条被照明 IR 路径):
  `gain 32→33.5%`, `64→25.8%`, `128→1.3%`, `200→0%`。**调高增益反而更差**(饱和/噪声破坏匹配纹理)。
- `-ir` 直存的 IR 帧(max≈14/255)看着全黑**不是增益/曝光不够**——那是 depth+IR 同开时,
  激光同步绑给了 depth、IR 组件取到「灭灯相位」的暗电平读出(详 §8.3)。**gain 对这些直存 IR 帧
  无响应**(无光可放大),但对深度有效率有响应(影响机内另一条被照明的 IR)。要拍真散斑得 IR-only 模式(§8.4)。
- **重要:Percipio 的设置(LASER_POWER / gain 等)会持久化存设备。** 一旦改过,会残留影响后续所有
  采集,必须显式重置(gain→32、laser→power100/auto1)。

### 结构光天性(无法消除)
玻璃、屏幕、黑色、强反光面打不回有效 IR 散斑 → 永远无效。办公室这类面多,会拉低有效率,属正常。

---

## 5. 密度对比实验(佐证 §4)

场景固定,gain=32,n=2 帧取首帧,单一变量:

| 配置 | depth 分辨率 | 有效率 | 有效点数 |
|---|---|---|---|
| 640 默认 | 640×480 | 33.5% | 103 052 |
| **1280 默认** | 1280×960 | 33.7% | **413 812** |
| 640 宽松(uniq20+nolrc) | 640×480 | 47.4% | 145 694 |
| **1280 宽松(uniq20+nolrc)** | 1280×960 | 47.3% | **581 117** |

读法:
- **分辨率列(纵向)**:1280 比 640 点数 ≈ ×4,有效率几乎不变 → 分辨率只放大像素数,不改变匹配成功率。
- **SGBM 列(横向)**:宽松比默认有效率 +14 个百分点 → 靠牺牲精度换密度。
- 从最初平放桌面的 2 万点 → 1280 默认的 41 万点 = **约 20 倍**,稀疏问题主要靠「摆位 + 满分辨率」解决。

---

## 6. 推荐采集配置

兼顾「尽可能多 + 尽可能精确」:

1. **depth 用 1280×960**(满分辨率,纯赚 4×)。sample 加 `-dmode 1280`。
2. **SGBM 保留默认**(要精度);只有明确要密度时才 `-uniq 20 -nolrc`(并接受精度下降)。
3. **gain 保持 32**,切勿扫描;若被改过,先 `-ir -irg 32` 重置。
4. **摆位**:让目标场景填满 0.6–4m;避开屏幕/玻璃/强反光面;漫射光。
5. 量产采集命令示例:
   ```
   SimpleView_CaptureDump -ip 192.168.1.114 -n 6 -dmode 1280 -outdir <dir>
   ```

---

## 7. 佐证清单(可复现)

| 结论 | 佐证 | 复现命令 |
|---|---|---|
| 设备=主动双目 SGBM | `DumpAllFeatures` 见 LEFT/RIGHT IR + SGBM_* + 基线外参 | `DumpAllFeatures`(third_party/camport4) |
| 基线 B=99.89mm | 右→左 IR 外参 tx | 同上,`TY_STRUCT_EXTRINSIC_TO_DEPTH` 段 |
| 焦距 fx=1102(1280) | 左 IR 内参 | 同上,`IR_CAM_LEFT` 段 |
| 工作量程 0.59–4.4m | f·B/d 几何推导,对齐有效值 558–4164mm | 见 §3.2 |
| IR 增益默认 32 最优 | 增益扫描表 | `-ir -irg {32,64,128,200}` 各跑一帧 |
| 1280×960=4× 点 | 密度矩阵 | `-dmode 1280` 对比默认 |
| 设置持久化 | 扫描 gain=200 后,裸默认采集归零,查 gain now=200 残留 | `-ir` 打印 `gain now=` |
| 设备=Gige_2_0,旧 API 有效 | `DumpAllFeatures`: LASER 组件 + LASER_POWER/AUTO_CTRL access=3 | `DumpAllFeatures -ip .114` 看 LASER 段 |
| 投射器发射=深度命脉 | LASER_POWER 0→深度有效率 2.4%, 100→33% | `-laser 0` vs `-laser 100` 各跑看 valid rate |
| IR 全黑=co-enable 抢光照 | depth+IR 同开 IR max=14; IR-only(-nodepth) IR mean=199 | `-ir` vs `-nodepth -laser 100 -ire 80` |

---

## 8. 投射器(散斑)与 IR 直取 —— 排障记录

本节回答两个一度被误判的问题:**散斑投射器到底发不发射?** 和 **`-ir` 存的 IR 帧为什么全黑?**
结论均经对照实验证实,排除了「SDK 太新 / 接口代际不匹配 / 投射器坏了 / IR 相机坏了」等猜测。

### 8.1 设备代际 = Gige_2_0(旧 API 有效)

`DumpAllFeatures` 实测:`TY_COMPONENT_LASER` 存在,`TY_INT_LASER_POWER` / `TY_BOOL_LASER_AUTO_CTRL`
均 readable+writable(access=3)。→ 本设备是 **Gige_2_0** 接口一代,走旧 `TYSetInt/TYSetBool` API
(**不是** Gige_2_1 的 GenICam `LightControllerSelector`/`TYParamGetAccess`)。「SDK 太新致 LASER/gain
设置 no-op」的猜测**不成立**。HW 1.3.0 / FW 3.13.70。

### 8.2 投射器确实发射,且是深度的命脉

散斑投射器是主动双目立体的「人工纹理」来源。对照实验(同一摆位,640×480,各 3 帧平均有效率):

| LASER 配置 | 深度有效率 |
|---|---|
| power=100, auto=1(出厂频闪) | **33.4%** |
| power=100, auto=0(手动常亮) | 33.2% |
| **power=0(关)** | **2.4%** |

关掉投射器,深度有效率从 33% 暴跌到 2% —— **散斑是立体匹配的纹理来源,关掉几乎匹配不出深度。**
投射器正常工作。`TYSetInt(TY_COMPONENT_LASER, TY_INT_LASER_POWER, …)` 读回 0↔100 正确、深度随之响应,
证明旧 API 有效。

> ⚠️ `LASER_POWER` 是**持久化**设置。实验后必须 `-laser 100 -lauto 1` 恢复出厂状态,否则下次裸采集
> (不传 `-laser`)会用残留 power=0 → 深度归零。`main.cpp` 每次启动会打印 `LASER now: power=X auto=Y` 供核查。

### 8.3 IR 帧全黑的真因:depth+IR co-enable 抢了激光同步

`-ir`(同时开 depth + 左右 IR)存出的 `ir_left/right_*.png` 长期是 max≈14/255 的近全黑帧,
且 gain 0→255 无响应。**这不是故障,是光照路由**:

投射器的光照只路由给「主」流。depth 与 IR 同时开时,激光频闪**绑给 depth 时序**——深度引擎
在亮的那一刻内部抓走 IR 图去匹配;而旁路开的 `IR_CAM_LEFT/RIGHT` 组件在**另一时刻**取图 →
取到「灭灯相位」→ 全黑、无光可放大(gain 无效)。铁证(把四种组合的 IR 帧亮度对比):

| 模式 | 投射器 | IR 帧 mean / max / std |
|---|---|---|
| depth + IR 同开(`-ir`) | 开 | 7 / 14 / 5(黑) |
| depth + IR 同开(`-ir`) | 关 | 7 / 14 / 5(黑) |
| **IR-only(`-nodepth`)** | 开 | **199 / 255 / 78(亮)** |
| IR-only(`-nodepth`) | 关 | 19 / 50 / 2(黑) |

IR-only + 投射器开 → IR 帧全亮;Laplacian 纹理方差 **646**(vs 暗帧 105,6×);`analyze_image`
确认是「高密度随机点散斑,物体边缘在点下可见」。**IR 相机和投射器都正常,只是同开时光照没路由到 IR 组件。**

> §4(d) 早先「IR 帧暗是传感器在曝光上限下的正常表现、仍有散斑对比度供匹配」的说法**不准确,据此更正**:
> 那些 `-ir` 帧是**未被照明的暗电平读出,不含有效散斑成像**;深度用的是机内另一条被照明的 IR 路径
> (故深度 33% 与 IR 帧 max=14 并存,不矛盾)。本设备**无独立 IR 泛光灯**
> (`TY_BOOL_IR_FLASHLIGHT` 在所有组件 `TYHasFeature=false`)。

### 8.4 怎么拿到真散斑图

```bash
# 正常采集(要 depth/color/点云):不要加 -ir,避免产出无用的暗 IR 帧
SimpleView_CaptureDump -ip 192.168.1.114 -n 6 -dmode 1280 -outdir <dir>

# 单独拍真散斑(IR-only,牺牲当帧 depth):投射器同步给 IR 流 → IR 帧被照亮
SimpleView_CaptureDump -ip 192.168.1.114 -n 2 -nodepth -color=off -laser 100 -ire 80 -outdir <dir>
# → ir_left_*.png / ir_right_*.png 即被照明的散斑图(-ire 80 降曝光,避免散点亮点半过曝)
```

`main.cpp` 相关开关:`-laser <0..100>`(给值会自动关 auto 进手动常亮)/ `-lauto <0|1>`(投射器
频闪:1=与采图同步/0=手动常亮)/ `-irflash <0|1>`(IR 泛光灯,本设备无效)/ `-nodepth`(纯 IR,
拍散斑用)。每帧末尾打深度有效率,整批末尾打平均有效率(对比 LASER 开关的客观判据)。

---

## 9. RGB 彩色镜头畸变(点云里直线弯曲的成因与修复)

带色点云里墙上**直线(凹槽)看着是弯的**,且弯曲和彩色图里一模一样。本节记录诊断与修复全过程。

### 9.1 两个会误导的度量(先排雷)
- **点到平面平整度(§5 的 1.4mm)**:量的是**离面 z 残差**,看不出**平面内**的桶形畸变——桶形是把直线
  在平面内掰弯,z 几乎不变,故平整度指标对它完全失明。
- **针孔拟合残差**:点云本就用 `X=(u-cx)·Z/fx` 生成,拿这公式反拟合当然残差 0,**循环论证,
  证明不了有没有畸变**。

**正确判据 = 直线特征**:用墙上已知是直的凹槽,看它在点云里直不直(镜头畸变的经典检测法)。

### 9.2 诊断:弯的是颜色,不是几何
- **CloudCompare 决定性验证**:把点云 RGB 颜色关掉、改按高度上色 → **凹槽立刻变直**。
  → 几何没畸变,弯的只是颜色。
- **几何为什么干净**:双目深度在 **rectify(校正)后**的图上算,IR 镜头畸变在校正阶段已消除;
  depth 图存的是轴向 z(实测 `|depth − 点云.z| = 0.00 mm`,完全相等),点云是干净针孔,直线不弯。
- **颜色为什么弯**:RGB 是**独立镜头**,自带桶形畸变;解码出的 BGR 带着它,贴到干净几何上,
  凹槽(靠颜色才看得见)就跟着 RGB 弯。图像和点云弯曲**一模一样** = 同一份 RGB 镜头畸变
  (若弯的是几何/IR,图案会和 RGB 镜头不同)。

### 9.3 RGB 畸变系数怎么来(读出厂标定,无需自标定)
```c
TY_CAMERA_CALIB_INFO color_calib;
TYGetStruct(hDevice, TY_COMPONENT_RGB_CAM, TY_STRUCT_CAM_CALIB_DATA, &color_calib, sizeof(color_calib));
```
`TY_CAMERA_CALIB_INFO` 含两块:
- `intrinsic.data[9]` = 3×3 矩阵 `[fx,0,cx, 0,fy,cy, 0,0,1]`。本机 RGB 实测:**fx=1864.8 fy=1865.3 cx=1278.9 cy=955.2**。
- `distortion.data[12]` = **Percipio 自定义 12 系数畸变模型**(不是 OpenCV 的 5/8 系数)。本机前 6 项实测:
  **`-0.2334, 0.4031, -0.0002, 0.0004, 0.2073, 0.0268`**(首项 k1=−0.2334 <0 → 桶形畸变)。

`main.cpp` 启动时打印这组系数(`color_calib intrinsic ... distortion[0..5] ...`)供核查。

### 9.4 去畸变怎么做(用 SDK 自带接口,别用 OpenCV)
用 `TYUndistortImage`(`TYImageProc.h`)——它懂 Percipio 的 12 系数模型;OpenCV 的 `cv::undistort`
是 5/8 系数,模型不匹配,**不要用**。

```c
// 1) 解码出 BGR8 后, 用 color_calib 去镜头畸变(NULL 新内参 = 保持原 fx/fy/cx/cy, 输出 pinhole 图)
TY_IMAGE_DATA simg{/*BGR8, colorBGR*/}, dimg{/*BGR8, ud 缓冲*/};
TYUndistortImage(&color_calib, &simg, NULL, &dimg, TY_LENS_PINHOLE);   // OK 后用 ud 替换 colorBGR

// 2) 贴点云时, 传给 TYMapRGBImageToDepthCoordinate 的 color_calib 把畸变清零
//    (图已是 pinhole, 不清零会被映射函数再校一次 = 二次校正, 把颜色又挪歪)
TY_CAMERA_CALIB_INFO calib_pin = color_calib;
memset(&calib_pin.distortion, 0, sizeof(calib_pin.distortion));
TYMapRGBImageToDepthCoordinate(&depth_calib, dw, dh, depth, &calib_pin, cw, ch, colorBGR, mappedColor, scale);
```

要点:
- **只去 RGB**。depth/IR 几何已 rectify,不要再动;`TY_BOOL_UNDISTORTION` 只在 IR 组件上有,RGB 没有。
- 去畸变后图是 pinhole,**贴图用的 calib 必须清零畸变**,否则二次校正。
- 去畸变在**存 JPG 之前**做 → 存盘的 `color_*.jpg` 也一并去畸变了(修复前那张带桶形弯)。
- 支持 `TYUndistortImage` 的格式:Mono8/Mono16/RGB8/BGR8/Coord3D_C16;解码出的 BGR8 正好适用。

### 9.5 验证
同一面墙、同一组凹槽:修复前带色点云凹槽弯曲;修复后(本节去畸变)凹槽变直;几何(关 RGB)始终是直的。
深度有效率不受影响(90.2%)。

---

## 附:与 LiDAR 的根本区别

LiDAR(禾赛/速腾/Livox)靠**飞行时间**(ToF,直接测光往返)得距离,每点独立、稀疏但远(百米级)。
本设备靠**双目立体匹配**(被动三角,投射器只补纹理),得**稠密深度图**(每像素一个深度),
但受基线限制量程短(米级)、受表面反射率影响大。二者互补:LiDAR 远而稀,结构光近而密。
