// Livox(.100 HAP) 点云存盘 demo —— 仿 livox_lidar_quick_start, 把点云回调改为按帧(frame_cnt)
// 累积 CartesianHigh(int32 xyz mm + reflectivity) 点, 落 ASCII PCD。其余 init / Normal 模式逻辑照搬。
//
// 用法: livox_lidar_pcd_saver <config.json>
//   环境变量: PCD_OUT=输出目录(默认 pcd_livox, 需预先创建); LIVOX_RUN_SECS=运行秒数(默认 15)。

#include "livox_lidar_def.h"
#include "livox_lidar_api.h"

#ifdef _WIN32
#include <winsock2.h>
#else
#include <unistd.h>
#endif

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vector>
#include <string>

struct PcdPoint { float x, y, z; uint8_t refl; };

static std::vector<PcdPoint> g_frame;
static uint8_t g_last_frame = 0;
static bool g_first = true;
static int g_frame_idx = 0;
static std::string g_outdir = "pcd_livox";

static void FlushFrame() {
  if (g_frame.empty()) return;
  char path[1024];
  snprintf(path, sizeof(path), "%s/%05d.pcd", g_outdir.c_str(), g_frame_idx++);
  FILE* f = fopen(path, "w");
  if (!f) { g_frame.clear(); return; }
  size_t n = g_frame.size();
  fprintf(f, "# .PCD v0.7 - Livox point cloud\n");
  fprintf(f, "VERSION 0.7\nFIELDS x y z intensity\nSIZE 4 4 4 4\nTYPE F F F F\nCOUNT 1 1 1 1\n");
  fprintf(f, "WIDTH %zu\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\nPOINTS %zu\nDATA ascii\n", n, n);
  for (size_t i = 0; i < n; ++i)
    fprintf(f, "%.3f %.3f %.3f %u\n", g_frame[i].x, g_frame[i].y, g_frame[i].z, (unsigned)g_frame[i].refl);
  fclose(f);
  printf("saved %s  (%zu pts, frame_cnt=%u)\n", path, n, g_last_frame);
  g_frame.clear();
}

void PointCloudCallback(uint32_t handle, const uint8_t dev_type, LivoxLidarEthernetPacket* data, void* client_data) {
  (void)handle; (void)dev_type; (void)client_data;
  if (data == nullptr) return;

  // 仅存 high-cartesian(data_type=1, HAP 默认); 其它类型只提示一次。
  if (data->data_type != kLivoxLidarCartesianCoordinateHighData) {
    static bool warned = false;
    if (!warned) { printf("data_type=%d (非 high-cartesian, 跳过存盘)\n", data->data_type); warned = true; }
    return;
  }

  // HAP 的 frame_cnt 实测恒为 0(不随旋转递增), 改按累积点数切片: 每 50000 点落一帧(约 10Hz)。
  if (g_frame.size() >= 50000) FlushFrame();

  const LivoxLidarCartesianHighRawPoint* pts =
      reinterpret_cast<const LivoxLidarCartesianHighRawPoint*>(data->data);
  for (uint32_t i = 0; i < data->dot_num; ++i) {
    PcdPoint p;
    p.x = pts[i].x / 1000.0f;  // mm -> m
    p.y = pts[i].y / 1000.0f;
    p.z = pts[i].z / 1000.0f;
    p.refl = pts[i].reflectivity;
    g_frame.push_back(p);
  }
}

void WorkModeCallback(livox_status status, uint32_t handle, LivoxLidarAsyncControlResponse* response, void* client_data) {
  (void)status; (void)handle; (void)client_data;
  if (response) printf("WorkMode ret_code=%u error_key=%u\n", response->ret_code, response->error_key);
}

void LidarInfoChangeCallback(const uint32_t handle, const LivoxLidarInfo* info, void* client_data) {
  (void)client_data;
  if (info == nullptr) { printf("lidar info null\n"); return; }
  printf("Lidar discovered  handle=%u SN=%s -> set Normal\n", handle, info->sn);
  SetLivoxLidarWorkMode(handle, kLivoxLidarNormal, WorkModeCallback, nullptr);
}

int main(int argc, const char* argv[]) {
  if (argc != 2) { printf("Usage: %s <config.json>\n", argv[0]); return -1; }
  if (const char* out = getenv("PCD_OUT")) if (out[0]) g_outdir = out;
  int run_secs = 15;
  if (const char* s = getenv("LIVOX_RUN_SECS")) run_secs = atoi(s);

  if (!LivoxLidarSdkInit(argv[1])) {
    printf("Livox Init Failed\n");
    LivoxLidarSdkUninit();
    return -1;
  }
  SetLivoxLidarPointCloudCallBack(PointCloudCallback, nullptr);
  SetLivoxLidarInfoChangeCallback(LidarInfoChangeCallback, nullptr);

  printf("livox_lidar_pcd_saver: out=%s run=%ds\n", g_outdir.c_str(), run_secs);
  for (int i = 0; i < run_secs; ++i) sleep(1);

  FlushFrame();  // 落最后一帧
  LivoxLidarSdkUninit();
  printf("done: %d frames saved to %s\n", g_frame_idx, g_outdir.c_str());
  return 0;
}
