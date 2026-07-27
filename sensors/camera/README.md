# camera / fisheye — 海康相机(.107)/ 鱼眼(.99)

海康 IP 相机走 **HCNetSDK**(ctypes 加载 `libhcnetsdk.so`),登录一次、连拍多张**设备端编码 JPEG**
(`NET_DVR_CaptureJPEGPicture`)。相机 `.107`(DS-2CD3T46WDA4-L)与鱼眼 `.99`(DS-2CD6345EWD-IV)共用同一套驱动。

## 设备信息

| | 相机 | 鱼眼 |
|---|---|---|
| IP | 192.168.1.107 | 192.168.1.99 |
| 型号 | DS-2CD3T46WDA4-L | DS-2CD6345EWD-IV(全景鱼眼, 采集后展开需 dewarp) |
| 分辨率 | 1920×1080 | 1920×1920 |
| SDK | HCNetSDK V6.1.9.4(预编译, 无 `.git`) | 同左 |

## 采集方案

进程内 poll 型(`Sensor` 子类 `HikSensor`):每次 `grab()` 调 `NET_DVR_CaptureJPEGPicture` 让 SDK **直接把 JPEG 写到指定路径**,返回耗时(ms)。SDK 调用序列封装在 `HikGrabber`(`sdk_grabber.py`):加载 `.so` → `NET_DVR_Init` → `NET_DVR_SetSDKInitCfg`(组件库 `HCNetSDKCom` + `libcrypto`/`libssl` 路径)→ `NET_DVR_Login_V40` → 连拍 → `NET_DVR_Logout` + `NET_DVR_Cleanup`。

## 流程要点

1. **网络**:相机与采集机同子网;相机网页确认可达。
2. **库路径**:运行前 `export LD_LIBRARY_PATH=<sdk>/lib`(传递依赖 `HCNetSDKCom/`、`libcrypto/libssl/libPlayCtrl`)。
3. **登录**:Private 协议(8000 端口),`byLoginMode=0`,`byHttps=0`。
4. **通道**:**SDK 逻辑通道从 1 起**(`NET_DVR_CaptureJPEGPicture` 用 1)。注意 RTSP/ISAPI 的流号是 101(主)/102(副),别混。
5. **凭证**:`admin` / `b@light2.`(两台同;密码含 `@`)。

## 运行

```bash
export LD_LIBRARY_PATH=$PWD/third_party/EN-HCNetSDKV6.1.9.4_build20220412_linux64/lib
# 单设备 demo(委托 HikSensor)
python3 sensors/camera/grab_demo.py --ip 192.168.1.107 -n 6               # -> data/camera_107/
python3 sensors/camera/grab_demo.py --ip 192.168.1.99  -n 6 --out data/fisheye_99
# 协同采集(record.py 自动采 rig.yaml 里两台)
python3 acquire/record.py --duration 10
```

## 输出

- 单设备 demo:`data/camera_<末段>/<ip>_ch<通道>_<序号>.jpg`(设备端编码 JPEG)。
- 协同采集:`data/<run>/cam_hik/*.jpg` + `manifest.jsonl`。

## SDK 改动

**无源码改动**。HCNetSDK 是海康官方预编译库(V6.1.9.4 build20220412),来源/必备文件见
[`third_party/SOURCES.md`](../../third_party/SOURCES.md#en-hcnetsdkv6194)。`sdk_grabber.py` 用 ctypes
按绝对路径加载 `lib/libhcnetsdk.so`,不修改 SDK。

## 关键文件

- `sdk_grabber.py` — `HikGrabber`:HCNetSDK ctypes 封装(登录一次/连拍多张)。SDK 绝对路径硬编码(见 CLAUDE.md gotcha)。
- `hik_driver.py` — `HikSensor(Sensor)`:把 `HikGrabber` 适配成统一 `Sensor` 接口;`_kwargs()` 做 rig.yaml spec → HikGrabber 参数映射。
- `grab_demo.py` — 单设备 demo 薄壳:CLI → spec → `HikSensor` → `capture_once(max_frames=N)`。

## 常见问题

- `ModuleNotFoundError`:用了裸 `python3.14` 而非 anaconda `python3`。
- 登录失败 / 抓图失败:`NET_DVR_GetLastError` 非零;检查 IP/凭证/库路径/相机是否在线。
