// 禾赛 QT128 在线取数 + 每帧存 ASCII PCD(不依赖 PCL, 规避 Ubuntu22.04 VTK/PCL/libtiff 链接冲突)。
// 结构与官方 test.cc 一致, 仅把回调改成写 ASCII PCD。
// 用法: ./sample_pcd <config.ini>     输出目录由环境变量 PCD_OUT 控制(默认 pcd_out)
//
// ── SDK 本质工作原理 ──
// 传输: UDP 被动接收。雷达持续单向推送 MSOP(点数据, udp_port=2364) + DIFOP(状态) 包;
//   PTC(TCP 9347)是独立控制通道, SDK 经它自动拉取角度修正/发光时刻文件(use_ptc_connected=true)。
// 模型: 异步回调。SDK 内部线程 recvfrom → 按包内角度表解包 → 组装成完整一帧 → 回调 lidarCallback。
//   帧边界来自雷达自身的旋转标记(frame_index, 由包头给出), 不由本程序决定。
// 编码: 主机端解码。SDK 把雷达私有包格式解成笛卡尔点(x/y/z 米 + intensity + ring)在 CPU 上算。
//   (与海康「设备端编码 JPEG」相反 —— 这里主机才是算力所在。)
//
// ── SDK 调用流程(每个序号对应一个 SDK API)──
//   1. LoadIniMap + MergeSourceTypeProfile + ApplyToDriverParam   解析 ini 成 DriverParam
//   2. HesaiLidarSdk.Init(param)                                  初始化驱动(SDK 起 UDP 收包线程)
//   3. RegRecvCallback(lidarCallback)                             注册「每帧就绪」回调(写 PCD 在此)
//   4. Start()                                                     开始接收/解码
//   5. [SDK 线程: 收包 → 解码 → 每帧回调 lidarCallback]            ← 数据在此流转
//   6. Stop()                                                      退出
//   帧→文件 的缝合点就是 lidarCallback: 回调里直接 fwrite ASCII PCD, 绕开链接失败的 PCL。
#include "hesai_lidar_sdk.hpp"
#include "../config/driver_sample_config.hpp"

#include <chrono>
#include <cstring>
#include <fstream>
#include <string>
#include <sys/stat.h>
#include <thread>
#include <unordered_map>

using TestPointType = LidarPointXYZICRT;

uint32_t last_frame_time = 0;

// 每收到一帧点云就写一个 ASCII PCD
void lidarCallback(const LidarDecodedFrame<TestPointType>& frame) {
  last_frame_time = GetMicroTickCount();
  if (frame.points_num == 0) return;

  const char* env = std::getenv("PCD_OUT");
  std::string dir = env ? env : "pcd_out";
  mkdir(dir.c_str(), 0777);

  char path[512];
  snprintf(path, sizeof(path), "%s/frame_%06d.pcd", dir.c_str(), frame.frame_index);
  std::ofstream f(path);
  if (!f) { printf("写失败: %s\n", path); return; }

  uint32_t n = frame.points_num;
  f << "# .PCD v0.7 - Point Cloud Data file format\n"
    << "VERSION 0.7\nFIELDS x y z intensity ring\n"
    << "SIZE 4 4 4 1 2\nTYPE F F F U U\nCOUNT 1 1 1 1 1\n"
    << "WIDTH " << n << "\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\n"
    << "POINTS " << n << "\nDATA ascii\n";
  for (uint32_t i = 0; i < n; ++i) {
    const TestPointType& p = frame.points[i];
    f << p.x << ' ' << p.y << ' ' << p.z << ' '
      << (unsigned)p.intensity << ' ' << p.ring << '\n';
  }
  printf("存盘 %s  (%u 点, frame %d)\n", path, n, frame.frame_index);
}

void faultMessageCallback(const FaultMessageInfo&) {}

bool IsPlayEnded(HesaiLidarSdk<TestPointType>& sdk) {
  return sdk.lidar_ptr_->IsPlayEnded();
}

int main(int argc, char* argv[]) {
  if (argc < 2) {
    fprintf(stderr, "Usage: %s <config.ini>   (输出目录: 环境变量 PCD_OUT, 默认 pcd_out)\n", argv[0]);
    return 1;
  }
  HesaiLidarSdk<TestPointType> sample;
  DriverParam param;
  std::unordered_map<std::string, std::string> kv;
  std::string err;
  if (!hesai::lidar::sample_config::LoadIniMap(argv[1], &kv, &err)
      || !hesai::lidar::sample_config::MergeSourceTypeProfileIntoInput(&kv, &err)
      || !hesai::lidar::sample_config::ApplyToDriverParam(kv, "", &param, &err)) {
    fprintf(stderr, "config error: %s\n", err.c_str());
    return 1;
  }
  if (param.decoder_param.socket_buffer_size == 0) {
    param.decoder_param.socket_buffer_size = 262144000;
  }

  sample.Init(param);                          // 2. 初始化驱动(SDK 内部起 UDP 收包线程)
  sample.RegRecvCallback(lidarCallback);        // 3. 注册点云就绪回调 —— 写 PCD 的入口
  sample.RegRecvCallback(faultMessageCallback); //    故障回调(空实现)
  sample.Start();                              // 4. 开始接收/解码; 此后 UDP 包流入即触发回调
  if (sample.lidar_ptr_->GetInitFinish(FailInit)) { sample.Stop(); return -1; }

  while (!IsPlayEnded(sample) || GetMicroTickCount() - last_frame_time < 1000000) {
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  }
  std::this_thread::sleep_for(std::chrono::milliseconds(1000));
  sample.Stop();
  return 0;
}
