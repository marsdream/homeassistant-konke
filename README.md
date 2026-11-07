# Home Assistant 控客小K 集成

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=flat&logo=home-assistant&logoColor=white)](https://github.com/marsdream/homeassistant-konke)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.4%2B-41BDF5.svg?style=flat&logo=home-assistant&logoColor=white)](https://www.home-assistant.io)
[![License](https://img.shields.io/badge/License-Apache%202.0-D22128.svg?style=flat&logo=apache&logoColor=white)](LICENSE)
[![Support on Ko-fi](https://img.shields.io/badge/Support%20on-Ko--fi-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/aitoken)
[![GitHub Release](https://img.shields.io/github/v/release/marsdream/homeassistant-konke?label=release)](https://github.com/marsdream/homeassistant-konke/releases)

把**控客（Konke）小K 智能插座**接入 Home Assistant，完全走**本地局域网协议**，不需要控客 App、不需要注册账号、不需要云端。

![Mini K](https://cdn.jsdelivr.net/gh/marsdream/homeassistant-konke@main/docs/images/mini-k.png)

<p align="center">
  <a href="https://github.com/marsdream/homeassistant-konke"><img src="https://cdn.jsdelivr.net/gh/marsdream/homeassistant-konke@main/docs/images/hacs-install.png" alt="一键安装 via HACS" width="320" /></a>
</p>

<p align="center">
  <sub>点上面按钮 → 在 HACS 里添加自定义仓库 <code>https://github.com/marsdream/homeassistant-konke</code> → 搜「控客」→ 下载 → 重启 HA</sub>
</p>

## 为什么做这个

控客官方 App 已经 **2022-03-09** 之后就没更新过了，云端服务陆续下线，忘记密码时「获取验证码」经常收不到短信，App 基本用不了。

但插座本身没坏 —— 它仍然在局域网里跑着一套自己的 UDP 协议（端口 `27431`）。只要知道它的 IP，任何人都可以直接控制它，**控客云只是给 App 加了一层壳**。

这个集成就是把那层壳扒掉，直接跟设备说话。

## 主要改动（相对上游 [5high/konke](https://github.com/5high/konke)）

上游的集成是 **YAML 平台**（`setup_platform`），在现代 Home Assistant 上有几个硬伤：

| 问题 | 表现 | 本集成怎么解决 |
|---|---|---|
| YAML 平台无法注册设备 | 前端提示「此设备无法通过用户界面添加」，加不进房间 | 改写成 **config entry 集成**，UI 里点几下就加好 |
| 没有轮询 | 状态永远停在启动时的快照 | 显式声明 `SCAN_INTERVAL = 30s` |
| MAC 拿不到 | `unique_id` 为空，设备注册失败 | 显式 `await device.fetch_info()` |
| MAC 格式不对 | `Invalid mac address format` | 统一 `format_mac()` 转成冒号格式 |
| 拿不到固件版本 | 设备信息里没有版本号 | 用原始 `lan_phone` 报文解析固件 |
| 设备离线时直接崩 | 拔掉电源 → 整个实体从 UI 消失，日志一片红 | 离线只标记 `unavailable`，实体和设备都在 |
| 离线导致 `unique_id` 为空 | HA 报「attempts to attach a device to an entity without a unique ID」 | 用 config entry 里记录的 MAC 做稳定标识 |

另外补了：**房间归属**（添加时直接选房间）、**固件版本**显示、**UI 添加流程**、**中英文错误提示**。

## 支持的设备

| 型号 | 状态 |
|---|---|
| Mini K | ✅ 已实测（`model: minik`） |
| Mini Pro | ⚠️ 同一协议，代码支持，未实测 |
| K1 / Smart Plug | ⚠️ 代码支持，未实测 |
| K2 Pro | ⚠️ 代码支持，未实测（带红外） |

> `model` 填 `minik` 同时覆盖 Mini K 和 Mini Pro。

## 安装

### HACS（推荐）

把这个仓库加进 HACS 的自定义仓库：

```
https://github.com/marsdream/homeassistant-konke
```

然后 HACS → 集成 → 搜「控客」→ 下载 → 重启 Home Assistant。

### 手动

把 `custom_components/konke` 整个目录拷到你的 HA 配置目录（通常是 `/config` 或 `~/.homeassistant`）：

```
<config>/custom_components/konke/
```

重启 Home Assistant。

### 依赖

`manifest.json` 里已经声明 `pykonkeio==2.1.7`，HA 启动时会自动装。

> **注意**：HA 自带的 `pycryptodome` 通常是 3.x，而 `switchbot` / `roborock` 集成要求 `<4.0`。
> 本集成直接复用 HA 自带的版本，**不要手动升级 pycryptodome 到 4.x**，否则会弄坏其他集成。

## 配置

**设置 → 设备与服务 → 添加集成 → 搜「控客」**

| 字段 | 说明 |
|---|---|
| `host` | 设备在局域网里的 IP，例如 `192.168.1.100` |
| `model` | 型号，Mini K 填 `minik` |
| `name` | 显示名称 |
| `area` | 房间（添加完也能在设备页改） |

提交后会自动：探测设备 → 读取 MAC 和固件 → 注册设备 → 归入所选房间。

### 怎么找设备的 IP

看看你的路由器（小米 / 华为 / tp-link 都行）的设备列表，找名字里有 `KONKE` / `miniK` / `小K` 的那台，
或者按厂商信息（杭州控客）筛出来的那台，记下它的 IP。

### 还在用 configuration.yaml？

YAML 方式仍然兼容：

```yaml
switch:
  - platform: konke
    name: 控客小K插座
    model: minik
    host: 192.168.1.100
```

但 YAML 方式**没有 config entry**，设备不会出现在「设备与服务」里，也没法在界面上分配房间。
新装建议用 UI 添加。

## 已知限制

- **只支持单台设备**（一个 config entry 对应一个 IP）。多个插座就添加多次。
- **不支持自动发现**：HA 跑在容器里（Docker / OrbStack）时，容器的网段和家里设备的网段往往不一样，
  广播包过不去，所以只能手填 IP。
- **不支持功率统计**（K2 系的 `get_power()`）。
- **红外遥控**只在 Mini Pro / K2 Pro 上可用，需要在 `configuration.yaml` 里额外配 `remote:` 段。

## 技术细节

协议是 UDP `27431`，AES-ECB 加密，密钥固定。

探测报文：

```
lan_phone%mac%nopassword%<YYYY-mm-dd HH:MM:SS>%heart
```

设备回包自带 **MAC + 密码 + 状态 + 固件版本**。状态串长这样：

```
close#<hardware-version>#<software-version>#hack
```

`hv` / `sv` 后面是硬件 / 软件固件版本，`#hack` 是协议版本标记（**所有**控客设备都有，不是型号标记）。

> ⚠️ 报文里的 `%` 是协议分隔符，**不能用 Python 的 `%` 格式化**去拼这个字符串，
> 会报 `unsupported format character 'm'`。用 f-string。

## 致谢

- [5high/konke](https://github.com/5high/konke) —— 原始集成（Apache-2.0），本项目基于它改写
- [jedmeng/pykonkeio](https://github.com/jedmeng/python-konkeio) —— 底层协议库
- [jedmeng/homeassistant-konke](https://github.com/jedmeng/homeassistant-konke) —— v2 版本的 config entry 改写思路

## License

[Apache License 2.0](LICENSE)

## 支持我

这个集成是纯开源、免费的，没有广告也没有付费墙。如果你觉得它帮你救回了一台老设备，欢迎请我喝杯咖啡 —— 所有赞助都会用在买新硬件和折腾新项目上。

<p align="center">
  <a href="https://ko-fi.com/aitoken"><img src="https://img.shields.io/badge/Support%20on-Ko--fi-FF5E5B?logo=ko-fi&logoColor=white&style=for-the-badge" alt="Support on Ko-fi" height="42" /></a>
</p>

---

## 更多

<p align="center">
  <a href="https://osp.io"><img src="https://cdn.jsdelivr.net/gh/marsdream/homeassistant-konke@main/docs/images/osp.io-logo.png" alt="开源派 osp.io" width="96" /></a>
</p>

<p align="center">
  本项目来自 <a href="https://osp.io">开源派 osp.io</a> —— 一个分享新奇、有趣、实用的
  <b>免费开源软硬件</b> 的中文社区。折腾旧硬件、拆解协议、把厂商 App 扒掉换成
  本地直连，正是开源派最爱干的事。
</p>

<p align="center">
  想看更多这种「把厂商的壳扒掉」的项目？去 <a href="https://osp.io">osp.io</a> 逛逛。
</p>
