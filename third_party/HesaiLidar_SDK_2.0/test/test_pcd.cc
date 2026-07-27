// 禾赛 QT128 在线取数 + 每帧存 ASCII PCD(不依赖 PCL, 规避 Ubuntu22.04 VTK/PCL/libtiff 链接冲突)。
// 结构与 test.cc 一致, 仅把回调改成写 ASCII PCD。
// 用法: ./sample_pcd <config.ini>     输出目录由环境变量 PCD_OUT 控制(默认 pcd_out)
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

  sample.Init(param);
  sample.RegRecvCallback(lidarCallback);
  sample.RegRecvCallback(faultMessageCallback);
  sample.Start();
  if (sample.lidar_ptr_->GetInitFinish(FailInit)) { sample.Stop(); return -1; }

  while (!IsPlayEnded(sample) || GetMicroTickCount() - last_frame_time < 1000000) {
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  }
  std::this_thread::sleep_for(std::chrono::milliseconds(1000));
  sample.Stop();
  return 0;
}
