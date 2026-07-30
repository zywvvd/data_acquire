#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成「机械雷达 vs 固态雷达」对比文档用图。

讲清三种扫描机构的「点云指纹」:机械式(Hesai QT128 / RoboSense)的离散线束环
vs 固态式(Livox 双棱镜 rosette)的连续带状非重复扫描。

用法(默认读最近一次协同采集 run):
  python3 tools/make_lidar_figures.py
  python3 tools/make_lidar_figures.py --run data/20260728_094028 --out sensors/lidar/assets
"""
import sys, os, glob, argparse
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrow, Circle, Wedge
from scipy.signal import find_peaks

RUN_DEFAULT = "data/20260728_094028"
DEVS = [("Hesai QT128", "lidar_hesai", "#1f77b4"),
        ("RoboSense front", "lidar_robosense_front", "#2ca02c"),
        ("RoboSense rear", "lidar_robosense_rear", "#9467bd"),
        ("Livox (solid)", "lidar_solid_livox", "#d62728")]
plt.rcParams.update({"axes.unicode_minus": False, "font.size": 10,
                     "font.family": "WenQuanYi Micro Hei", "axes.unicode_minus": False})


def load_pcd(path):
    flds = None
    with open(path) as f:
        for ln in f:
            if ln.startswith("FIELDS "):
                flds = ln.split()[1:]
            if ln.strip() == "DATA ascii":
                break
        data = np.loadtxt(f)
    return flds, data


def azel(a):
    x, y, z = a[:, 0], a[:, 1], a[:, 2]
    r = np.sqrt(x * x + y * y + z * z)
    return (np.degrees(np.arctan2(y, x)),
            np.degrees(np.arctan2(z, np.sqrt(x * x + y * y))), r)


# ---------------------------------------------------------------- schematics
def rosette_trace(w1=1.0, w2=1.37, delta=1.0, T=62.8, n=4000, phase2=0.0):
    """两片 Risley 棱镜合成的光斑轨迹:净偏转 = δ(cos ω1t,sin ω1t)+δ(cos(ω2t+φ),sin(ω2t+φ))。"""
    t = np.linspace(0, T, n)
    return delta * np.cos(w1 * t) + delta * np.cos(w2 * t + phase2), \
           delta * np.sin(w1 * t) + delta * np.sin(w2 * t + phase2)


def fig_schematic_mechanical(out):
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.6))
    # side view: vertical fan of fixed-elevation beams
    ax[0].set_title("侧视:N 条线束 = N 个固定俯仰角", fontsize=11)
    ax[0].plot(0, 0, 'ks', ms=8)
    for ang in np.linspace(-25, 15, 9):
        a = np.radians(ang)
        ax[0].plot([0, 5 * np.cos(a)], [0, 5 * np.sin(a)], '-', color='#1f77b4', lw=1.2)
    ax[0].text(2.5, 3.2, "每条线束一个\n固定俯仰角", ha='center', fontsize=9, color='#1f77b4')
    ax[0].set_xlim(-0.5, 6); ax[0].set_ylim(-3, 4); ax[0].axis('off')
    # top view: rotating head, one beam sweeps 360
    ax[1].set_title("俯视:整体旋转,一束扫 360° → 一个环", fontsize=11)
    ax[1].add_patch(Circle((0, 0), 0.6, color='#333', zorder=3))
    th = np.linspace(0, 2 * np.pi, 200)
    ax[1].plot(4 * np.cos(th), 4 * np.sin(th), '--', color='gray', lw=1)
    for k in range(6):
        a = k * np.pi / 3
        ax[1].plot([0.6 * np.cos(a), 4 * np.cos(a)], [0.6 * np.sin(a), 4 * np.sin(a)],
                   '-', color='#1f77b4', lw=1, alpha=.5)
    ax[1].add_patch(FancyArrow(2.0, 2.6, -1.0, -1.3, width=.03, head_width=0.18,
                               head_length=0.25, color='crimson', length_includes_head=True))
    ax[1].text(0, -5.3, "整体旋转 ~10 Hz:每转一圈,每条线束画一个水平环", ha='center', fontsize=9)
    ax[1].set_xlim(-5.2, 5.2); ax[1].set_ylim(-5.8, 5); ax[1].set_aspect('equal'); ax[1].axis('off')
    fig.suptitle("机械旋转式多线束激光雷达", fontsize=13)
    plt.tight_layout(rect=[0, 0, 1, 0.94]); fig.savefig(out, dpi=120); plt.close(fig)


def fig_schematic_solid(out):
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.6))
    # two Risley wedges
    ax[0].set_title("两片楔形棱镜(Risley)各自旋转", fontsize=11)
    for cx, phi, c, lab in [(-1.3, 0.5, '#1f77b4', '棱镜1 ω₁'),
                            (1.0, -1.1, '#d62728', '棱镜2 ω₂')]:
        ax[0].add_patch(Circle((cx, 0), 1.0, fill=False, lw=1.5, color=c))
        ax[0].add_patch(Wedge((cx, 0), 1.0, np.degrees(phi) - 22, np.degrees(phi) + 22,
                              color=c, alpha=.45))
        ax[0].add_patch(FancyArrow(cx, 0, 0.9 * np.cos(phi + 1.4), 0.9 * np.sin(phi + 1.4),
                                   width=.02, head_width=0.12, head_length=0.16, color=c,
                                   length_includes_head=True))
        ax[0].text(cx, -1.4, lab, ha='center', fontsize=9, color=c)
    ax[0].annotate("", xy=(3.4, 0), xytext=(2.2, 0),
                   arrowprops=dict(arrowstyle="->", lw=1.5))
    ax[0].text(2.8, 0.3, "出射光束", fontsize=9)
    ax[0].set_xlim(-2.8, 4.2); ax[0].set_ylim(-2, 2); ax[0].set_aspect('equal'); ax[0].axis('off')
    # rosette trace
    ax[1].set_title("折射叠加 → rosette 花瓣轨迹", fontsize=11)
    x, y = rosette_trace()
    ax[1].plot(x, y, '-', color='#d62728', lw=0.6)
    ax[1].text(0, -2.6, "两转速不可约 → 图案永不精确重复\n= 非重复扫描(越看越密)", ha='center', fontsize=9)
    ax[1].set_xlim(-2.6, 2.6); ax[1].set_ylim(-2.8, 2.6); ax[1].set_aspect('equal'); ax[1].axis('off')
    fig.suptitle("固态式激光雷达(Livox 双棱镜)", fontsize=13)
    plt.tight_layout(rect=[0, 0, 1, 0.94]); fig.savefig(out, dpi=120); plt.close(fig)


def fig_scan_cartoon(out):
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.6))
    # mechanical: horizontal rings, identical every frame
    ax[0].set_title("机械式:水平环 · 重复", fontsize=11)
    for el in np.linspace(-10, 12, 11):
        ax[0].plot([-1, 1], [el, el], '-', color='#1f77b4', lw=1)
        ax[0].plot([-1, 1], [el + 0.15, el + 0.15], '-', color='#1f77b4', lw=0.6, alpha=.4)
    ax[0].text(0, -14, "每帧扫同样的环\n(帧间重叠 ~100%)", ha='center', fontsize=9)
    ax[0].set_xlim(-1.1, 1.1); ax[0].set_ylim(-16, 16); ax[0].set_xlabel("azimuth"); ax[0].set_ylabel("elevation"); ax[0].grid(alpha=.2)
    # solid: rosette, precessing
    ax[1].set_title("固态式:rosette 花瓣 · 非重复", fontsize=11)
    for ph, a in [(0, 0.95), (1.1, 0.55), (2.3, 0.35)]:
        x, y = rosette_trace(w1=1.0, w2=1.4, T=44, n=3000, phase2=ph)
        ax[1].plot(x / 2 * 0.92, y / 2 * 13, '-', color='#d62728', lw=1.3, alpha=a)
    ax[1].text(0, -14.5, "每帧花瓣进动\n(细网格帧间重叠 ~52%)", ha='center', fontsize=9)
    ax[1].set_xlim(-1.1, 1.1); ax[1].set_ylim(-16, 16); ax[1].set_xlabel("azimuth"); ax[1].grid(alpha=.2)
    fig.suptitle("扫描图案对照(azimuth × elevation)", fontsize=13)
    plt.tight_layout(rect=[0, 0, 1, 0.94]); fig.savefig(out, dpi=120); plt.close(fig)


# ---------------------------------------------------------------- data figures
def fig_scan_pattern(run, out):
    fig, ax = plt.subplots(1, 4, figsize=(18, 4.8))
    for i, (name, d, col) in enumerate(DEVS):
        _, a = load_pcd(sorted(glob.glob(os.path.join(run, d, "*.pcd")))[0])
        az, el, r = azel(a); m = r > 0.3
        ax[i].scatter(az[m], el[m], s=0.5, c=col, alpha=.55, linewidths=0)
        ax[i].set_title(f"{name}\n{m.sum()} pts", fontsize=11)
        ax[i].set_xlabel("方位角 azimuth (°)"); ax[i].grid(alpha=.25)
        if i == 0: ax[i].set_ylabel("俯仰角 elevation (°)")
    fig.suptitle("单帧扫描图案(azimuth × elevation):机械式 = 水平线束环,固态式 = 连续 rosette 带",
                 fontsize=13)
    plt.tight_layout(rect=[0, 0, 1, 0.93]); fig.savefig(out, dpi=120); plt.close(fig)


def fig_elevation_profile(run, out):
    fig, ax = plt.subplots(2, 2, figsize=(13, 7))
    for i, (name, d, col) in enumerate(DEVS):
        _, a = load_pcd(sorted(glob.glob(os.path.join(run, d, "*.pcd")))[0])
        el, r = azel(a)[1], azel(a)[2]; el = el[r > 0.3]
        lo, hi = el.min(), el.max()
        bins = np.arange(lo, hi, 0.1); h, e = np.histogram(el, bins=bins)
        h = h.astype(float); hs = np.convolve(h, np.ones(3) / 3, 'same')
        mx = hs.max()
        pk, _ = find_peaks(hs, height=0.1 * mx, prominence=0.08 * mx, distance=3)
        fill = (h > 0.05 * mx).mean()
        ax[i // 2][i % 2].plot((e[:-1] + e[1:]) / 2, hs, color=col, lw=1)
        ax[i // 2][i % 2].set_title(f"{name}: {len(pk)} 个尖峰, 填充率 {fill:.0%}", fontsize=11)
        ax[i // 2][i % 2].set_xlabel("elevation (°)"); ax[i // 2][i % 2].grid(alpha=.25)
        if len(pk) > 0:
            ax[i // 2][i % 2].plot((e[:-1] + e[1:])[pk] / 1 + 0 * pk, hs[pk], 'k.', ms=3)
    fig.suptitle("俯仰分布剖面:机械式 = 离散线束尖峰(线间有缝),固态式 = 连续带(无尖峰)", fontsize=13)
    plt.tight_layout(rect=[0, 0, 1, 0.94]); fig.savefig(out, dpi=120); plt.close(fig)


def fig_hesai_rings(run, out):
    flds, a = load_pcd(sorted(glob.glob(os.path.join(run, "lidar_hesai", "*.pcd")))[0])
    ring = a[:, flds.index("ring")].astype(int)
    az, el, r = azel(a); m = r > 0.3
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.8),
                           gridspec_kw={'width_ratios': [1.4, 1]})
    sc = ax[0].scatter(az[m], el[m], c=ring[m], cmap='tab20', s=0.6, linewidths=0)
    ax[0].set_title("Hesai QT128:ring 字段着色(每色 = 一条线束)", fontsize=11)
    ax[0].set_xlabel("azimuth (°)"); ax[0].set_ylabel("elevation (°)"); ax[0].grid(alpha=.25)
    ur = np.unique(ring[m])
    rmax = int(ring.max()) + 1
    hh, _ = np.histogram(ring[m], bins=np.arange(0, rmax + 1))
    ax[1].bar(np.arange(rmax), hh, color='#1f77b4', width=1.0)
    ax[1].set_title(f"ring 编号 0–{rmax-1} 的点计数\n(有效回波线束 {len(ur)}/{rmax})", fontsize=11)
    ax[1].set_xlabel("ring 编号"); ax[1].set_ylabel("点数"); ax[1].grid(alpha=.25)
    fig.suptitle("机械式铁证:`ring` 字段 = 离散线束编号", fontsize=13)
    plt.tight_layout(rect=[0, 0, 1, 0.93]); fig.savefig(out, dpi=120); plt.close(fig)


def fig_livox_precession(run, out):
    files = sorted(glob.glob(os.path.join(run, "lidar_solid_livox", "*.pcd")))
    frames = [load_pcd(f)[1] for f in files[:6]]
    fig, ax = plt.subplots(1, 2, figsize=(13, 5), gridspec_kw={'width_ratios': [1.3, 1]})
    cols = ['crimson', 'steelblue', 'forestgreen']
    for k, fi in enumerate([0, 1, 3]):
        az, el, r = azel(frames[fi]); m = r > 0.3
        ax[0].scatter(az[m], el[m], s=0.5, c=cols[k], alpha=.5, linewidths=0,
                      label=f"frame {fi}")
    ax[0].set_title("Livox 帧叠加:花瓣进动(非重复)", fontsize=11)
    ax[0].set_xlabel("azimuth (°)"); ax[0].set_ylabel("elevation (°)")
    ax[0].legend(markerscale=8, fontsize=9); ax[0].grid(alpha=.25)
    # overlap curve vs frame lag at fine grid
    def gm(a, lo=(-56, 56)):
        az, el, r = azel(a); m = r > 0.3
        naz = int((lo[1] - lo[0]) / 0.25); H, _, _ = np.histogram2d(
            az[m], el[m], bins=[naz, 104], range=[list(lo), [-13, 13]])
        return H > 0
    g0 = gm(frames[0])
    ovs = []
    for f in frames:
        g = gm(f); ovs.append((g0 & g).sum() / max(1, (g0 | g).sum()))
    ax[1].plot(range(len(ovs)), [int(o * 100) for o in ovs], 'o-', color='crimson')
    ax[1].set_title("frame0 与各帧的细网格重叠率", fontsize=11)
    ax[1].set_xlabel("frame index"); ax[1].set_ylabel("重叠率 (%)")
    ax[1].set_ylim(0, 100); ax[1].grid(alpha=.25)
    ax[1].text(0.5, max(ovs) * 100 - 12, "≈50% ⇒ 非重复\n(机械式会 ≈100%)", fontsize=9, color='crimson')
    fig.suptitle("固态式铁证:非重复扫描(细网格帧间重叠 ~50% 并持续进动)", fontsize=13)
    plt.tight_layout(rect=[0, 0, 1, 0.93]); fig.savefig(out, dpi=120); plt.close(fig)


def fig_contrast_metric(run, out):
    names, fills, contrasts = [], [], []
    for name, d, _ in DEVS:
        _, a = load_pcd(sorted(glob.glob(os.path.join(run, d, "*.pcd")))[0])
        el, r = azel(a)[1], azel(a)[2]; el = el[r > 0.3]
        bins = np.arange(el.min(), el.max(), 0.1); h, _ = np.histogram(el, bins=bins)
        h = h.astype(float); hs = np.convolve(h, np.ones(3) / 3, 'same'); mx = hs.max()
        fills.append((h > 0.05 * mx).mean() * 100)
        contrasts.append(mx / (np.percentile(hs, 20) + 1))
        names.append(name)
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
    cols = ['#1f77b4', '#2ca02c', '#9467bd', '#d62728']
    ax[0].bar(names, fills, color=cols); ax[0].set_ylabel("elevation 填充率 (%)")
    ax[0].set_title("俯仰填充率:机械式低(线间有缝),固态式 ~100%"); ax[0].tick_params(axis='x', rotation=15)
    for i, v in enumerate(fills): ax[0].text(i, v + 1, f"{v:.0f}", ha='center', fontsize=9)
    ax[1].bar(names, np.log10(contrasts), color=cols); ax[1].set_ylabel("log₁₀(峰/谷对比度)")
    ax[1].set_title("峰谷对比度:机械式 ≫1(离散),固态式 ~1(连续)"); ax[1].tick_params(axis='x', rotation=15)
    for i, v in enumerate(contrasts): ax[1].text(i, np.log10(v) + 0.1, f"{v:.0f}", ha='center', fontsize=9)
    plt.tight_layout(); fig.savefig(out, dpi=120); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=RUN_DEFAULT)
    ap.add_argument("--out", default="sensors/lidar/assets")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    fig_schematic_mechanical(os.path.join(a.out, "schematic_mechanical.png"))
    fig_schematic_solid(os.path.join(a.out, "schematic_solid.png"))
    fig_scan_cartoon(os.path.join(a.out, "scan_cartoon.png"))
    fig_scan_pattern(a.run, os.path.join(a.out, "scan_pattern_azel.png"))
    fig_elevation_profile(a.run, os.path.join(a.out, "elevation_profile.png"))
    fig_hesai_rings(a.run, os.path.join(a.out, "hesai_rings.png"))
    fig_livox_precession(a.run, os.path.join(a.out, "livox_precession.png"))
    fig_contrast_metric(a.run, os.path.join(a.out, "contrast_metric.png"))
    print("wrote 8 figures to", a.out)


if __name__ == "__main__":
    main()
