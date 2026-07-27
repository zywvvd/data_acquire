# 结构光(.114)

## 设备
- `192.168.1.114`,结构光,**品牌型号未知**。
- 探测特征:只开 TCP 22(SSH),无网页(80 关),MAC `06:2d:8c…` 为**本地管理地址**
  (非厂商 OUI,像嵌入式 Linux)。

## 待办(优先级最高:先认出它是什么)
- [ ] SSH 登录 `.114`(需要凭证——待找)看 hostname / `/etc/` / 厂商文件,或物理查看贴纸
- [ ] 候选:Mech-Mind(米文)、Photoneo、Zivid、LMI(Gocator)、Orbbee/奥比中光 等
- [ ] 认准后:取对应 SDK 进 `third_party/`,写 `structured_light_driver.py`,
      在 registry 的 `structured_light` 登记

## 备注
若是 GigE Vision 类,可在采集机上往 UDP 3956 发 GVCP DISCOVERY,设备会主动回型号+序列号。
若是 USB 类(如 RealSense),则不会有 IP,需另查 `.114` 主机或采集机的 USB 设备。
