"""(kind, model) → 驱动 派发表。

配置驱动的核心: rig.yaml 里每台设备的 kind 在这里查到对应驱动类,
record.py 据此实例化。加一种新传感器 = 在 sensors/<kind>/ 写实现 + 在此登记一行。
"""
import importlib

# impl = 仓库根下可 import 的模块路径; cls = 驱动类名; None = 尚未实装。
TABLE = {
    "camera":           dict(impl="sensors.camera.hik_driver", cls="HikSensor",
                             note="海康, 复用 sensors/camera/sdk_grabber"),
    "fisheye":          dict(impl="sensors.camera.hik_driver", cls="HikSensor",
                             note="海康鱼眼, 走 Hik; 全景 dewarp 待加"),
    # ---- 以下待实装 ----
    "lidar_mechanical": None,    # 速腾 → third_party/rslidar_sdk-v1.5.20(就绪, 待包一层)
                                 # 禾赛 → third_party/HesaiLidar_SDK_2.0(待接)
    "lidar_solidstate": None,    # Livox(.100, 纯 UDP/DJI) → Livox SDK2 ctypes
    "structured_light": None,    # .114 待认型号
}

IMPLEMENTED = {k for k, v in TABLE.items() if v}
TODO = {k: (v if v else {}) for k, v in TABLE.items() if not v}


def resolve_driver(kind, model=None):
    """返回驱动类; 该 kind 未实装返回 None。"""
    entry = TABLE.get(kind)
    if not entry:
        return None
    mod = importlib.import_module(entry["impl"])
    return getattr(mod, entry["cls"])
