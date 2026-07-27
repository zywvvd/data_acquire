"""(kind, model) → 驱动 派发表。

配置驱动的核心: rig.yaml 里每台设备的 (kind, model) 在这里查到对应驱动类,
record.py 据此实例化。加一种新传感器 = 在 sensors/<kind>/ 写实现 + 在此登记一行。

键: (kind, model); model 为 None 表示该 kind 的默认驱动(仅一个型号时用)。
resolve_driver(kind, model) 先精确匹配 (kind, model), 再 fallback (kind, None),
再按 model 关键字兜底(机械 LiDAR 的禾赛 / 速腾两大家族)。
"""
import importlib

TABLE = {
    # ---- 进程内 poll 型 ----
    ("camera", None):
        dict(impl="sensors.camera.hik_driver", cls="HikSensor",
             note="海康相机 .107, 复用 sdk_grabber"),
    ("fisheye", None):
        dict(impl="sensors.camera.hik_driver", cls="HikSensor",
             note="海康鱼眼 .99, 走 Hik; 全景 dewarp 待加"),
    # ---- 子进程型 ----
    ("structured_light", None):
        dict(impl="sensors.structured_light.percipio_driver", cls="PercipioSensor",
             note="图漾 FM815-IX-E1 .114(批量型)"),
    ("lidar_solidstate", None):
        dict(impl="sensors.lidar_livox.livox_driver", cls="LivoxSensor",
             note="Livox HAP .100(流式限时自停)"),
    ("lidar_mechanical", "Hesai QT128"):
        dict(impl="sensors.lidar_hesai.hesai_driver", cls="HesaiSensor",
             note="禾赛 QT128 .201(流式)"),
    ("lidar_mechanical", "RSAIRY"):
        dict(impl="sensors.lidar_robosense.robosense_driver", cls="RobosenseSensor",
             note="速腾 RSAIRY .202/.205(流式)"),
}

# 已实装的 kind 集合(进度概览用)
IMPLEMENTED = {kind for kind, _model in TABLE}


def resolve_driver(kind, model=None):
    """返回驱动类; 未实装返回 None。"""
    entry = TABLE.get((kind, model)) or TABLE.get((kind, None))
    if not entry and kind == "lidar_mechanical" and model:
        m = model.lower()
        if any(k in m for k in ("hesai", "qt", "pandar", "xt")):
            entry = TABLE.get(("lidar_mechanical", "Hesai QT128"))
        elif any(k in m for k in ("rs", "airy", "helios", "ruby", "bp")):
            entry = TABLE.get(("lidar_mechanical", "RSAIRY"))
    if not entry:
        return None
    mod = importlib.import_module(entry["impl"])
    return getattr(mod, entry["cls"])
