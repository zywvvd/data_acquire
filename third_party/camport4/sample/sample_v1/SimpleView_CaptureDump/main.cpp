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
#include <cstring>

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

// 写 binary little-endian PCL/PLY(vertex: float x y z + uchar red green blue, 单位米, 跳 NaN)。
// 【与 write_pcd 同源保证一致】同一份 pnts/bgr 输入; 逐点有效判定(!isnan)和颜色转换(BGR->RGB)
// 完全镜像 write_pcd, 且循环同序 —— 故 PLY 与 PCD 的有效点集、坐标、颜色一一对应、完全等价,
// 仅编码不同: PCD=ASCII(%.4f), PLY=binary(float32, 精度反高于 PCD)。
// 起因: 本机 CloudCompare(2.11.3 apt)未带 PCL/PDAL, 不认 .pcd(unhandled extension);
// PLY 是 CloudCompare/open3d/MeshLab 的核心一等格式(不依赖 PCL), 用它兜底查看。
static void write_ply(const TY_VECT_3F* pnts, const uint8_t* bgr, size_t n, const char* file) {
    size_t valid = 0;
    for (size_t i = 0; i < n; ++i) if (!std::isnan(pnts[i].x)) valid++;   // 同 write_pcd 的判定 → 同一有效点集
    FILE* fp = fopen(file, "wb");
    if (!fp) { LOGE("cannot open %s", file); return; }
    fprintf(fp, "ply\n");
    fprintf(fp, "format binary_little_endian 1.0\n");
    fprintf(fp, "comment Percipio point cloud (meters)\n");
    fprintf(fp, "element vertex %zu\n", valid);
    fprintf(fp, "property float x\n");
    fprintf(fp, "property float y\n");
    fprintf(fp, "property float z\n");
    fprintf(fp, "property uchar red\n");
    fprintf(fp, "property uchar green\n");
    fprintf(fp, "property uchar blue\n");
    fprintf(fp, "end_header\n");
    for (size_t i = 0; i < n; ++i) {
        if (std::isnan(pnts[i].x)) continue;                  // 同序跳过 → 与 PCD 逐点对齐
        float xyz[3] = { pnts[i].x/1000.f, pnts[i].y/1000.f, pnts[i].z/1000.f };
        fwrite(xyz, sizeof(float), 3, fp);                     // x86=little-endian, 直写即合格式
        uint8_t rgb[3];
        if (bgr) { rgb[0]=bgr[3*i+2]; rgb[1]=bgr[3*i+1]; rgb[2]=bgr[3*i+0]; }  // BGR->RGB, 同 write_pcd
        else { rgb[0]=rgb[1]=rgb[2]=0; }
        fwrite(rgb, 1, 3, fp);
    }
    fclose(fp);
}

// 返回该帧有效深度像素数(depth!=0); 供主循环累计深度有效率(对比 LASER 开关的判据)。
static int handle_frame(TY_FRAME_DATA* frame, const CbCalib& cb, const std::string& outdir, int idx) {
    TY_IMAGE_DATA* depthImg = nullptr;
    TY_IMAGE_DATA* colorImg = nullptr;
    TY_IMAGE_DATA* irLeftImg = nullptr;
    TY_IMAGE_DATA* irRightImg = nullptr;
    for (int i = 0; i < frame->validCount; ++i) {
        if (frame->image[i].status != TY_STATUS_OK) continue;
        if (frame->image[i].componentID == TY_COMPONENT_DEPTH_CAM) depthImg = &frame->image[i];
        else if (frame->image[i].componentID == TY_COMPONENT_RGB_CAM) colorImg = &frame->image[i];
        else if (frame->image[i].componentID == TY_COMPONENT_IR_CAM_LEFT) irLeftImg = &frame->image[i];
        else if (frame->image[i].componentID == TY_COMPONENT_IR_CAM_RIGHT) irRightImg = &frame->image[i];
    }
    // ---- IR(诊断用): 左右原始 mono8 帧, 看散斑清晰度/曝光是否过暗过曝 ----
    // 放在 depth 必需检查之前: -nodepth 纯 IR 模式(验证投射器是否同步给 IR)也要能 dump IR。
    auto dump_ir = [&](const char* tag, TY_IMAGE_DATA* im) {
        if (!im) return;
        LOGI("IR %s: %dx%d pixelFormat=0x%x size=%u (mono8应为 %d, mono16为 %d)",
             tag, im->width, im->height, im->pixelFormat, im->size,
             im->width*im->height, im->width*im->height*2);
        cv::Mat m;
        if ((size_t)im->size >= (size_t)im->width * im->height * 2) {
            // 16bit: 之前按 CV_8U 读会把每像素拆成2字节=满屏噪声。正确读 CV_16U 再 min-max 归一化。
            cv::Mat m16(im->height, im->width, CV_16U, im->buffer);
            double mn, mx; cv::minMaxLoc(m16, &mn, &mx);
            LOGI("IR %s 16bit 动态范围: min=%.0f max=%.0f", tag, mn, mx);
            double s = (mx > mn) ? 255.0 / (mx - mn) : 1.0;
            m16.convertTo(m, CV_8U, s, -mn * s);
        } else {
            m = cv::Mat(im->height, im->width, CV_8U, im->buffer);
        }
        char ipath[512];
        snprintf(ipath, sizeof(ipath), "%s/ir_%s_%04d.png", outdir.c_str(), tag, idx);
        cv::imwrite(ipath, m);
    };
    dump_ir("left", irLeftImg);
    dump_ir("right", irRightImg);

    if (!depthImg) { LOGW("frame %d: no depth (-nodepth IR-only mode? skip depth/pcd)", idx); return 0; }

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
    // 有效深度像素(depth!=0)计数 —— 深度有效率是判定 LASER/散斑是否参与深度的客观量。
    size_t valid_px = 0;
    for (size_t i = 0; i < depth.size(); ++i) if (depth[i] != 0) valid_px++;
    {
        cv::Mat dm(dh, dw, CV_16U, depth.data());
        snprintf(path, sizeof(path), "%s/depth_%04d.png", outdir.c_str(), idx);
        cv::imwrite(path, dm);
    }

    // ---- color: 解码成 BGR8, 去镜头畸变(TYUndistortImage), 存 jpg ----
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
        // 去镜头畸变: RGB 是独立镜头带桶形畸变, 不修的话颜色贴到点云上, 墙上直线(凹槽)会跟着弯
        // (实测: 点云关掉 RGB 颜色后凹槽是直的 → 几何无畸变, 弯的只是颜色)。用 SDK 的 TYUndistortImage
        // (Percipio 自定义 12 系数模型, 套 OpenCV 不对)。去畸变后图变成 pinhole, 后续贴图用清零畸变的 calib。
        if (!colorBGR.empty() && cw > 0 && ch > 0) {
            TY_IMAGE_DATA simg{}; simg.width = cw; simg.height = ch;
            simg.pixelFormat = TYPixelFormatBGR8; simg.size = (uint32_t)colorBGR.size(); simg.buffer = colorBGR.data();
            std::vector<uint8_t> ud(colorBGR.size());
            TY_IMAGE_DATA dimg{}; dimg.width = cw; dimg.height = ch;
            dimg.pixelFormat = TYPixelFormatBGR8; dimg.size = (uint32_t)ud.size(); dimg.buffer = ud.data();
            int ue = TYUndistortImage(&cb.color_calib, &simg, nullptr, &dimg, TY_LENS_PINHOLE);
            if (ue == TY_STATUS_OK) colorBGR.swap(ud);
            else LOGW("frame %d: color undistort err=%d (distortion 全 0? 跳过去畸变)", idx, ue);
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
        // 颜色已在上方去畸变成 pinhole 图; 这里把 color_calib 的畸变系数清零再传,
        // 否则 TYMapRGBImageToDepthCoordinate 会再做一次畸变校正(二次校正把颜色挪歪)。
        TY_CAMERA_CALIB_INFO color_calib_pin = cb.color_calib;
        memset(&color_calib_pin.distortion, 0, sizeof(color_calib_pin.distortion));
        int err = TYMapRGBImageToDepthCoordinate(
            &cb.depth_calib, dw, dh, depth.data(),
            &color_calib_pin, cw, ch, colorBGR.data(),
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
        snprintf(path, sizeof(path), "%s/points_%04d.ply", outdir.c_str(), idx);
        write_ply(p3d.data(), color_for_pc, p3d.size(), path);   // 与 PCD 同源: 点数/坐标/颜色逐点一致
    }
    int valid_pct = (int)(valid_px * 100 / ((size_t)dw * dh));
    LOGI("frame %d saved: depth %dx%d valid=%zu(%d%%)%s%s%s -> %s",
         idx, dw, dh, valid_px, valid_pct,
         (cw>0? "+color ":""), (cw>0? std::to_string(cw).c_str():""), (ch>0? (std::string("x")+std::to_string(ch)).c_str():""),
         outdir.c_str());
    return (int)valid_px;
}

int main(int argc, char* argv[]) {
    std::string ID, IP;
    std::string outdir = "capture";
    int N = 10;
    bool with_color = true;
    bool align = true;
    bool dump_ir = false;
    int ire = 0;   // IR exposure time override (0 = 不改)
    int irg = 32;  // IR gain(默认 32=出厂最优; 设备会持久化, 故每次显式锁定)
    int depth_idx = 0;   // depth 模式索引: 0=640x480 1=1280x960 2=320x240
    int uniq = -1;       // SGBM uniqueness factor(-1 不改; 越小越宽松=更密但更噪)
    bool nolrc = false;  // 关 SGBM 左右一致性检查(更密, 有假阳性)
    int laser = -1;  // 散斑投射器功率 override(-1 不改; 0 关, 100 满)。给值会自动关 LASER_AUTO_CTRL 进手动常亮
    int lauto = -1;  // 投射器 LASER_AUTO_CTRL(频闪) override(-1 不改; 0 手动常亮, 1 自动频闪)
    int irflash = -1;  // IR 泛光灯(连续 IR 照明, 区别于散斑投射器) override(-1 不改; 0 关, 1 开)
    bool nodepth = false;  // 纯 IR 模式: 不开 depth 只开 IR —— 验证投射器在 depth 缺席时是否同步照亮 IR 流
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "-ip")) IP = argv[++i];
        else if (!strcmp(argv[i], "-id")) ID = argv[++i];
        else if (!strcmp(argv[i], "-n")) N = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-outdir")) outdir = argv[++i];
        else if (!strcmp(argv[i], "-color=off")) with_color = false;
        else if (!strcmp(argv[i], "-noalign")) align = false;
        else if (!strcmp(argv[i], "-ir")) dump_ir = true;
        else if (!strcmp(argv[i], "-ire")) ire = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-irg")) irg = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-dmode")) { int w=atoi(argv[++i]); depth_idx = (w>=1280?1:(w<=320?2:0)); }
        else if (!strcmp(argv[i], "-uniq")) uniq = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-nolrc")) nolrc = true;
        else if (!strcmp(argv[i], "-laser")) laser = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-lauto")) lauto = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-irflash")) irflash = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-nodepth")) nodepth = true;
        else if (!strcmp(argv[i], "-h")) {
            LOGI("Usage: %s -ip <IP> [-n frames] [-outdir dir] [-color=off] [-noalign] [-ir] [-ire us] [-irg gain] [-laser 0..100] [-lauto 0|1]", argv[0]);
            return 0;
        }
    }
    if (const char* e = getenv("OUTDIR")) if (e[0]) outdir = e;
    if (IP.empty()) { LOGE("must set -ip <IP>"); return -1; }
    mkdir(outdir.c_str(), 0755);
    if (nodepth) dump_ir = true;   // 纯 IR 模式: 必须开 IR, 否则没数据

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

    // ── 散斑投射器(LASER)控制 ──────────────────────────────────────────────
    // 本设备经 DumpAllFeatures 实测 = Gige_2_0: TY_COMPONENT_LASER 存在, TY_INT_LASER_POWER /
    // TY_BOOL_LASER_AUTO_CTRL 均可读写(access=3)。LASER_AUTO_CTRL=1(出厂默认)时投射器与深度采图
    // **同步频闪**(只在深度积分窗口点亮), 故单独 dump 的 IR 帧常落在「暗相位」→ 近全黑、增益无效。
    // 实验: -laser <P> 自动关 auto 进手动常亮, 看 IR 帧是否变亮(投射器是否真发射)、深度有效率是否随 P 变。
    if (allComps & TY_COMPONENT_LASER) {
        int32_t p = 0; bool a = false;
        TYGetInt(hDevice, TY_COMPONENT_LASER, TY_INT_LASER_POWER, &p);
        TYGetBool(hDevice, TY_COMPONENT_LASER, TY_BOOL_LASER_AUTO_CTRL, &a);
        LOGI("LASER now: power=%d auto=%d", p, (int)a);
        if (laser >= 0) {
            if (lauto < 0) {  // 给了 -laser 未显式给 -lauto → 强制手动常亮, 否则 power 被频闪逻辑接管
                TYSetBool(hDevice, TY_COMPONENT_LASER, TY_BOOL_LASER_AUTO_CTRL, false);
            }
            TYSetInt(hDevice, TY_COMPONENT_LASER, TY_INT_LASER_POWER, (int32_t)laser);
            int32_t p2 = 0; TYGetInt(hDevice, TY_COMPONENT_LASER, TY_INT_LASER_POWER, &p2);
            LOGI("LASER power -> %d (manual)", p2);
        }
        if (lauto >= 0) {
            TYSetBool(hDevice, TY_COMPONENT_LASER, TY_BOOL_LASER_AUTO_CTRL, lauto != 0);
            bool a2 = false; TYGetBool(hDevice, TY_COMPONENT_LASER, TY_BOOL_LASER_AUTO_CTRL, &a2);
            LOGI("LASER auto -> %d", (int)a2);
        }
    } else {
        LOGW("no TY_COMPONENT_LASER (Gige_2_1 设备走 LightControllerSelector, 本旧 API 不适用)");
    }

    // ── IR 泛光灯(IR_FLASHLIGHT): 独立于散斑投射器的连续 IR 照明(头文件注: "floodlight used in ir component")。
    // 判据: 开泛光灯后 dump 的 IR 帧若变亮 → IR dump 路径是活的, 先前全黑=缺照明路由(可救);
    //       若仍 max=14 → IR dump 是固定暗电平读出, 非活动图像(此 SDK 组件拿不到被照明的 IR)。
    //       特征归属文档有歧义(Laser 组件 / ir 组件), 故逐组件 TYHasFeature 探测落在哪。
    if (irflash >= 0) {
        struct { TY_COMPONENT_ID id; const char* name; } tryComps[] = {
            {TY_COMPONENT_LASER, "LASER"}, {TY_COMPONENT_IR_CAM_LEFT, "IR_LEFT"},
            {TY_COMPONENT_IR_CAM_RIGHT, "IR_RIGHT"}, {TY_COMPONENT_DEVICE, "DEVICE"}};
        bool any = false;
        for (auto& tc : tryComps) {
            if (!(allComps & tc.id)) continue;
            bool has = false;
            TYHasFeature(hDevice, tc.id, TY_BOOL_IR_FLASHLIGHT, &has);
            if (!has) continue;
            bool v = false; TYGetBool(hDevice, tc.id, TY_BOOL_IR_FLASHLIGHT, &v);
            LOGI("IR_FLASHLIGHT on %s: now=%d -> set %d", tc.name, (int)v, irflash);
            TYSetBool(hDevice, tc.id, TY_BOOL_IR_FLASHLIGHT, irflash != 0);
            TYGetBool(hDevice, tc.id, TY_BOOL_IR_FLASHLIGHT, &v);
            LOGI("IR_FLASHLIGHT on %s -> readback=%d", tc.name, (int)v);
            any = true;
        }
        if (!any) LOGW("TY_BOOL_IR_FLASHLIGHT 不存在于任何组件(本设备无独立 IR 泛光灯)");
    }

    CbCalib cb; cb.depth_scale = 1.0f; cb.has_color = false; cb.align = align;

    // depth (-nodepth 时跳过: 纯 IR 模式, 验证投射器是否同步照亮 IR 流)
    if (!nodepth && (allComps & TY_COMPONENT_DEPTH_CAM)) {
        TY_IMAGE_MODE mode;
        ASSERT_OK(get_image_mode(hDevice, TY_COMPONENT_DEPTH_CAM, mode, depth_idx));  // 0=640 1=1280 2=320
        LOGI("depth mode %dx%d", TYImageWidth(mode), TYImageHeight(mode));
        ASSERT_OK(TYSetEnum(hDevice, TY_COMPONENT_DEPTH_CAM, TY_ENUM_IMAGE_MODE, mode));
        ASSERT_OK(TYEnableComponents(hDevice, TY_COMPONENT_DEPTH_CAM));
        // 可选: 放宽 SGBM 严苛度换密度(uniqueness 调低 / 关 LRC)。代价是噪声/假匹配增加。
        if (uniq >= 0) {
            TYSetInt(hDevice, TY_COMPONENT_DEPTH_CAM, TY_INT_SGBM_UNIQUE_FACTOR, (int32_t)uniq);
            LOGI("SGBM uniqueness -> %d", uniq);
        }
        if (nolrc) {
            TYSetBool(hDevice, TY_COMPONENT_DEPTH_CAM, TY_BOOL_SGBM_LRC, false);
            LOGI("SGBM LRC off");
        }
        bool hasScale = false;
        TYHasFeature(hDevice, TY_COMPONENT_DEPTH_CAM, TY_FLOAT_SCALE_UNIT, &hasScale);
        if (hasScale) TYGetFloat(hDevice, TY_COMPONENT_DEPTH_CAM, TY_FLOAT_SCALE_UNIT, &cb.depth_scale);
        ASSERT_OK(TYGetStruct(hDevice, TY_COMPONENT_DEPTH_CAM, TY_STRUCT_CAM_CALIB_DATA, &cb.depth_calib, sizeof(cb.depth_calib)));
    } else if (!nodepth) { LOGE("no depth cam!"); return -1; }

    // color
    if (with_color && (allComps & TY_COMPONENT_RGB_CAM)) {
        ASSERT_OK(TYEnableComponents(hDevice, TY_COMPONENT_RGB_CAM));
        bool hasCalib = false;
        TYHasFeature(hDevice, TY_COMPONENT_RGB_CAM, TY_STRUCT_CAM_CALIB_DATA, &hasCalib);
        if (hasCalib) {
            TYGetStruct(hDevice, TY_COMPONENT_RGB_CAM, TY_STRUCT_CAM_CALIB_DATA, &cb.color_calib, sizeof(cb.color_calib));
            // 打印 RGB 畸变系数: 用于 TYUndistortImage 去镜头畸变(不修则颜色贴到点云上直线会弯)。
            const float* d = cb.color_calib.distortion.data;
            LOGI("color_calib intrinsic fx=%.1f fy=%.1f cx=%.1f cy=%.1f  distortion[0..5]=%.4f %.4f %.4f %.4f %.4f %.4f",
                 cb.color_calib.intrinsic.data[0], cb.color_calib.intrinsic.data[4],
                 cb.color_calib.intrinsic.data[2], cb.color_calib.intrinsic.data[5],
                 d[0], d[1], d[2], d[3], d[4], d[5]);
        }
        cb.has_color = true;
    }

    // IR: 若 -ir 则同时开左右 IR 相机输出 mono8 原始帧(看散斑/曝光)。
    //     无论是否 -ir, 都把增益显式锁定到 irg(默认 32=出厂最优)——
    //     Percipio 设置会持久化, 不锁的话会被上次残留值(可能很高)污染, 导致深度归零。
    {
        TY_COMPONENT_ID irs[2] = {TY_COMPONENT_IR_CAM_LEFT, TY_COMPONENT_IR_CAM_RIGHT};
        for (auto c : irs) {
            if (!(allComps & c)) continue;
            if (dump_ir) {
                TY_IMAGE_MODE m;
                if (get_default_image_mode(hDevice, c, m) == TY_STATUS_OK) {
                    TYSetEnum(hDevice, c, TY_ENUM_IMAGE_MODE, m);   // IR 模式只读, 失败无碍
                }
                TYEnableComponents(hDevice, c);
                TY_INT_RANGE r; TYGetIntRange(hDevice, c, TY_INT_EXPOSURE_TIME, &r);
                int32_t v = 0; TYGetInt(hDevice, c, TY_INT_EXPOSURE_TIME, &v);
                LOGI("IR comp=0x%x exposure now=%d range=[%d,%d]", c, v, r.min, r.max);
                if (ire > 0) TYSetInt(hDevice, c, TY_INT_EXPOSURE_TIME, (int32_t)ire);
            }
            TYSetInt(hDevice, c, TY_INT_GAIN, (int32_t)irg);   // 每次锁定增益
            int32_t gv = 0; TYGetInt(hDevice, c, TY_INT_GAIN, &gv);
            LOGI("IR comp=0x%x gain -> %d", c, gv);
        }
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
    long valid_sum = 0;                                // 累计有效深度像素(算整批平均有效率)
    while (got < N && tries < N * 4) {                // 6. 拉取循环(批量取 N 帧)
        TY_FRAME_DATA frame;
        int err = TYFetchFrame(hDevice, &frame, 3000); //    阻塞拉下一帧(3s 超时; 同步 pull, 非回调)
        if (err == TY_STATUS_OK) {
            valid_sum += handle_frame(&frame, cb, outdir, got);  // 落 depth/color/pcd, 返回有效像素数
            got++;
            TYEnqueueBuffer(hDevice, frame.userBuffer, frame.bufferSize);  // 缓冲回笼(乒乓)
        } else {
            LOGW("TYFetchFrame err=%d (try %d)", err, tries);
        }
        tries++;
    }
    // 深度有效率汇总: 对比 LASER 开/关、auto/手动 的客观判据(有效率越高=散斑参与越充分)。
    if (got > 0 && !nodepth) {
        int dw0 = 1280, dh0 = 960;
        if (depth_idx == 0) { dw0 = 640; dh0 = 480; }
        else if (depth_idx == 2) { dw0 = 320; dh0 = 240; }
        long total = (long)got * dw0 * dh0;
        LOGI("depth valid rate (avg over %d frames) = %.1f%%", got, total ? 100.0 * valid_sum / total : 0.0);
    }

    ASSERT_OK(TYStopCapture(hDevice));
    ASSERT_OK(TYCloseDevice(hDevice));
    ASSERT_OK(TYCloseInterface(hIface));
    ASSERT_OK(TYDeinitLib());
    delete[] buf[0]; delete[] buf[1];
    LOGI("done: %d frames saved to %s", got, outdir.c_str());
    return 0;
}
