// Percipio(.114 FM815-IX-E1) 无头采集 demo —— 取 N 帧, 落盘 depth(16bit PNG) + color(JPG) + 点云(ASCII PCD)。
//
// 仿 SimpleView_FetchFrame / SimpleView_Point3D, 但去掉 GUI/键盘交互, 适合服务器批量采集。
// 点云: 先 TYMapRGBImageToDepthCoordinate 把彩色贴到深度分辨率, 再 TYMapDepthImageToPoint3d
//        (depth_calib) 得 depth 相机坐标系下的 float3 点; 写 ASCII PCD(FIELDS x y z r g b)。
// depth 像素 = uint16(mm), 实际距离 = pixel * scale_unit(默认 1mm)。
//
// ── SDK 本质工作原理(与 LiDAR 的关键差异: 同步拉取, 非回调)──
// 传输: GigE Vision(GVCP 控制 + GVSP 流), 经广播发现 —— 标准机器视觉协议, 非厂商私有。
// 模型: 同步拉取(pull)。经典 GenICam 式: 先入队 N 个缓冲 → StartCapture → 循环
//   TYFetchFrame(阻塞到下一帧或超时) → 处理 → 缓冲重新入队。无回调线程, 帧由主循环主动「拉」。
//   这正是它能干净映射到「批量取 N 帧」的原因(本工程唯一批量型设备)。
// 编码: 深度是设备端原始输出(uint16 mm 结构光); 彩色主机端解码(TYDecodeImage→BGR)。
//   点云【完全主机端计算】: TYMapDepthImageToPoint3d 用深度相机内参(depth_calib)把每个深度像素反投影成 3D 点。
//
// ── SDK 调用流程(每个序号对应一个 TYApi 调用)──
//   1. TYInitLib                                              初始化库
//   2. selectDevice(GigE, IP) + TYOpenInterface/TYOpenDevice  发现并打开设备
//   3. TYDisableComponents(all) + 选择性 Enable(DEPTH_CAM/RGB_CAM)  只开需要的组件 + 读内参
//   4. TYGetFrameBufferSize + 2× TYEnqueueBuffer              预入队两个帧缓冲(乒乓)
//   5. TYStartCapture                                         开始取流
//   6. 循环 N 次: TYFetchFrame → handle_frame → TYEnqueueBuffer  拉一帧/处理/缓冲回笼
//   7. TYStopCapture / TYCloseDevice / TYCloseInterface / TYDeinitLib
//
// 用法: SimpleView_CaptureDump -ip <IP> [-n <帧数>] [-outdir <目录>] [-color=off] [-noalign] [-h]
//   环境变量 OUTDIR 覆盖输出目录(便于 Python 端注入绝对路径)。
//
// 依赖: 运行时 LD_LIBRARY_PATH 含 camport4/lib/linux/lib_x64。

#include "common.hpp"
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include <sys/stat.h>
#include <vector>
#include <string>
#include <cstdio>

struct CbCalib {
    TY_CAMERA_CALIB_INFO depth_calib;
    TY_CAMERA_CALIB_INFO color_calib;
    float depth_scale;
    bool has_color;
    bool align;          // 是否做 color->depth 对齐(点云带色)
};

// 写 ASCII PCD(FIELDS x y z r g b, 单位: 米), 跳过 NaN 点。
// 注意: TYMapDepthImageToPoint3d 输出单位随 depth(mm)* scale, 这里统一 /1000 转米,
// 与本仓其它 LiDAR 点云(Livox/禾赛/速腾, 均为米)一致。
static void write_pcd(const TY_VECT_3F* pnts, const uint8_t* bgr, size_t n, const char* file) {
    size_t valid = 0;
    for (size_t i = 0; i < n; ++i) if (!std::isnan(pnts[i].x)) valid++;   // 先数有效点(depth=0 投影为 NaN)
    FILE* fp = fopen(file, "w");
    if (!fp) { LOGE("cannot open %s", file); return; }
    fprintf(fp, "# .PCD v0.7 - Percipio point cloud (meters)\n");
    fprintf(fp, "VERSION 0.7\nFIELDS x y z r g b\nSIZE 4 4 4 1 1 1\nTYPE F F F U U U\nCOUNT 1 1 1 1 1 1\n");
    fprintf(fp, "WIDTH %zu\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\nPOINTS %zu\nDATA ascii\n", valid, valid);
    for (size_t i = 0; i < n; ++i) {
        if (std::isnan(pnts[i].x)) continue;
        uint8_t r = 0, g = 0, b = 0;
        if (bgr) { b = bgr[3*i + 0]; g = bgr[3*i + 1]; r = bgr[3*i + 2]; }  // 输入 BGR -> 存 RGB
        fprintf(fp, "%.4f %.4f %.4f %u %u %u\n", pnts[i].x/1000.f, pnts[i].y/1000.f, pnts[i].z/1000.f, r, g, b);
    }
    fclose(fp);
}

static void handle_frame(TY_FRAME_DATA* frame, const CbCalib& cb, const std::string& outdir, int idx) {
    TY_IMAGE_DATA* depthImg = nullptr;
    TY_IMAGE_DATA* colorImg = nullptr;
    for (int i = 0; i < frame->validCount; ++i) {
        if (frame->image[i].status != TY_STATUS_OK) continue;
        if (frame->image[i].componentID == TY_COMPONENT_DEPTH_CAM) depthImg = &frame->image[i];
        else if (frame->image[i].componentID == TY_COMPONENT_RGB_CAM) colorImg = &frame->image[i];
    }
    if (!depthImg) { LOGW("frame %d: no depth, skip", idx); return; }

    const int dw = depthImg->width, dh = depthImg->height;
    char path[512];

    // ---- depth: 直接是 uint16(mm)。若 size != w*h*2, 说明非裸 C16, 用 TYDecodeImage 兜底。----
    std::vector<uint16_t> depth(dw * dh);
    if ((size_t)depthImg->size >= (size_t)(dw * dh * 2)) {
        memcpy(depth.data(), depthImg->buffer, (size_t)dw * dh * 2);
    } else {
        LOGW("frame %d: depth size=%u != %d (unexpected fmt 0x%x), skip depth png",
             idx, depthImg->size, dw*dh*2, depthImg->pixelFormat);
    }
    {
        cv::Mat dm(dh, dw, CV_16U, depth.data());
        snprintf(path, sizeof(path), "%s/depth_%04d.png", outdir.c_str(), idx);
        cv::imwrite(path, dm);
    }

    // ---- color: 解码成 BGR8 存 jpg ----
    std::vector<uint8_t> colorBGR;
    int cw = 0, ch = 0;
    if (cb.has_color && colorImg) {
        TYImageInfo cinfo = ty_image_info(*colorImg);
        uint32_t dst = 0;
        if (TYGetDecodeBufferSize(&cinfo, &dst, TY_OUTPUT_FORMAT_BGR) == TY_DECODE_SUCCESS && dst > 0) {
            colorBGR.resize(dst);
            TYDecodeResult res;
            if (TYDecodeImage(&cinfo, TY_OUTPUT_FORMAT_BGR, colorBGR.data(), dst, &res) == TY_DECODE_SUCCESS) {
                cw = res.width; ch = res.height;
            } else { colorBGR.clear(); }
        } else {
            // 已是裸 BGR/RGB: 直接用
            cw = colorImg->width; ch = colorImg->height;
            colorBGR.assign((uint8_t*)colorImg->buffer, (uint8_t*)colorImg->buffer + colorImg->size);
        }
        if (!colorBGR.empty()) {
            cv::Mat cm(ch, cw, CV_8UC3, colorBGR.data());
            snprintf(path, sizeof(path), "%s/color_%04d.jpg", outdir.c_str(), idx);
            cv::imwrite(path, cm);
        }
    }

    // ---- 点云: color->depth 对齐后, TYMapDepthImageToPoint3d ----
    std::vector<uint8_t> mappedColor;
    const uint8_t* color_for_pc = nullptr;
    if (cb.align && cb.has_color && !colorBGR.empty()) {
        mappedColor.assign((size_t)dw * dh * 3, 0);
        int err = TYMapRGBImageToDepthCoordinate(
            &cb.depth_calib, dw, dh, depth.data(),
            &cb.color_calib, cw, ch, colorBGR.data(),
            mappedColor.data(), cb.depth_scale);
        if (err == TY_STATUS_OK) color_for_pc = mappedColor.data();
        else LOGW("frame %d: TYMapRGBImageToDepthCoordinate err=%d, point cloud will be colorless", idx, err);
    }
    std::vector<TY_VECT_3F> p3d((size_t)dw * dh);
    int err = TYMapDepthImageToPoint3d(&cb.depth_calib, dw, dh, depth.data(), p3d.data(), cb.depth_scale);
    if (err != TY_STATUS_OK) { LOGE("frame %d: TYMapDepthImageToPoint3d err=%d", idx, err); }
    else {
        snprintf(path, sizeof(path), "%s/points_%04d.pcd", outdir.c_str(), idx);
        write_pcd(p3d.data(), color_for_pc, p3d.size(), path);
    }
    LOGI("frame %d saved: depth %dx%d%s%s%s -> %s",
         idx, dw, dh,
         (cw>0? "+color ":""), (cw>0? std::to_string(cw).c_str():""), (ch>0? (std::string("x")+std::to_string(ch)).c_str():""),
         outdir.c_str());
}

int main(int argc, char* argv[]) {
    std::string ID, IP;
    std::string outdir = "capture";
    int N = 10;
    bool with_color = true;
    bool align = true;
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "-ip")) IP = argv[++i];
        else if (!strcmp(argv[i], "-id")) ID = argv[++i];
        else if (!strcmp(argv[i], "-n")) N = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-outdir")) outdir = argv[++i];
        else if (!strcmp(argv[i], "-color=off")) with_color = false;
        else if (!strcmp(argv[i], "-noalign")) align = false;
        else if (!strcmp(argv[i], "-h")) {
            LOGI("Usage: %s -ip <IP> [-n frames] [-outdir dir] [-color=off] [-noalign]", argv[0]);
            return 0;
        }
    }
    if (const char* e = getenv("OUTDIR")) if (e[0]) outdir = e;
    if (IP.empty()) { LOGE("must set -ip <IP>"); return -1; }
    mkdir(outdir.c_str(), 0755);

    LOGD("Init lib");
    ASSERT_OK(TYInitLib());                          // 1. 初始化库
    TY_VERSION_INFO ver; ASSERT_OK(TYLibVersion(&ver));
    LOGI("libtycam %d.%d.%d", ver.major, ver.minor, ver.patch);

    std::vector<TY_DEVICE_BASE_INFO> selected;
    ASSERT_OK(selectDevice(TY_INTERFACE_ALL, ID, IP, 1, selected));  // 2. GigE 广播发现指定 IP
    ASSERT(selected.size() > 0);
    TY_INTERFACE_HANDLE hIface = NULL; TY_DEV_HANDLE hDevice = NULL;
    ASSERT_OK(TYOpenInterface(selected[0].iface.id, &hIface));
    ASSERT_OK(TYOpenDevice(hIface, selected[0].id, &hDevice));       //    打开接口/设备

    TY_COMPONENT_ID allComps; ASSERT_OK(TYGetComponentIDs(hDevice, &allComps));
    ASSERT_OK(TYDisableComponents(hDevice, allComps));

    CbCalib cb; cb.depth_scale = 1.0f; cb.has_color = false; cb.align = align;

    // depth
    if (allComps & TY_COMPONENT_DEPTH_CAM) {
        TY_IMAGE_MODE mode;
        ASSERT_OK(get_default_image_mode(hDevice, TY_COMPONENT_DEPTH_CAM, mode));
        LOGI("depth mode %dx%d", TYImageWidth(mode), TYImageHeight(mode));
        ASSERT_OK(TYSetEnum(hDevice, TY_COMPONENT_DEPTH_CAM, TY_ENUM_IMAGE_MODE, mode));
        ASSERT_OK(TYEnableComponents(hDevice, TY_COMPONENT_DEPTH_CAM));
        bool hasScale = false;
        TYHasFeature(hDevice, TY_COMPONENT_DEPTH_CAM, TY_FLOAT_SCALE_UNIT, &hasScale);
        if (hasScale) TYGetFloat(hDevice, TY_COMPONENT_DEPTH_CAM, TY_FLOAT_SCALE_UNIT, &cb.depth_scale);
        ASSERT_OK(TYGetStruct(hDevice, TY_COMPONENT_DEPTH_CAM, TY_STRUCT_CAM_CALIB_DATA, &cb.depth_calib, sizeof(cb.depth_calib)));
    } else { LOGE("no depth cam!"); return -1; }

    // color
    if (with_color && (allComps & TY_COMPONENT_RGB_CAM)) {
        ASSERT_OK(TYEnableComponents(hDevice, TY_COMPONENT_RGB_CAM));
        bool hasCalib = false;
        TYHasFeature(hDevice, TY_COMPONENT_RGB_CAM, TY_STRUCT_CAM_CALIB_DATA, &hasCalib);
        if (hasCalib) TYGetStruct(hDevice, TY_COMPONENT_RGB_CAM, TY_STRUCT_CAM_CALIB_DATA, &cb.color_calib, sizeof(cb.color_calib));
        cb.has_color = true;
    }

    uint32_t frameSize; ASSERT_OK(TYGetFrameBufferSize(hDevice, &frameSize));
    char* buf[2]; buf[0] = new char[frameSize]; buf[1] = new char[frameSize];
    ASSERT_OK(TYEnqueueBuffer(hDevice, buf[0], frameSize));
    ASSERT_OK(TYEnqueueBuffer(hDevice, buf[1], frameSize));

    bool hasTrig = false;
    TYHasFeature(hDevice, TY_COMPONENT_DEVICE, TY_STRUCT_TRIGGER_PARAM_EX, &hasTrig);
    if (hasTrig) {
        TY_TRIGGER_PARAM_EX t; t.mode = TY_TRIGGER_MODE_OFF;
        TYSetStruct(hDevice, TY_COMPONENT_DEVICE, TY_STRUCT_TRIGGER_PARAM_EX, &t, sizeof(t));
    }

    LOGI("start capture -> %s (%d frames, color=%d align=%d)", outdir.c_str(), N, (int)cb.has_color, (int)align);
    ASSERT_OK(TYStartCapture(hDevice));               // 5. 开始取流

    int got = 0, tries = 0;
    while (got < N && tries < N * 4) {                // 6. 拉取循环(批量取 N 帧)
        TY_FRAME_DATA frame;
        int err = TYFetchFrame(hDevice, &frame, 3000); //    阻塞拉下一帧(3s 超时; 同步 pull, 非回调)
        if (err == TY_STATUS_OK) {
            handle_frame(&frame, cb, outdir, got);     //    落 depth/color/pcd
            got++;
            TYEnqueueBuffer(hDevice, frame.userBuffer, frame.bufferSize);  // 缓冲回笼(乒乓)
        } else {
            LOGW("TYFetchFrame err=%d (try %d)", err, tries);
        }
        tries++;
    }

    ASSERT_OK(TYStopCapture(hDevice));
    ASSERT_OK(TYCloseDevice(hDevice));
    ASSERT_OK(TYCloseInterface(hIface));
    ASSERT_OK(TYDeinitLib());
    delete[] buf[0]; delete[] buf[1];
    LOGI("done: %d frames saved to %s", got, outdir.c_str());
    return 0;
}
