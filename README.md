# AutoIPTV

> 自动同步电信 IPTV 直播源，生成 UDPXY / RTSP 订阅地址和 EPG 节目单。

自动登录电信 IPTV EPG 门户，抓取频道列表，生成可直接在播放器（APTV / TiviMate / PotPlayer 等）中使用的订阅链接和 XMLTV 格式 EPG 节目单。

---

## 功能

- **频道同步** — 自动登录电信 EPG 门户，获取 IGMP / RTSP 频道列表
- **双模式输出**
  - **UDPXY** — IGMP 转 HTTP 代理播放
  - **RTSP** — 点播回看，内置 `catchup-source` 支持（兼容 APTV）
- **动态 Authenticator** — 自动从服务器获取 EncryptToken，通过 3DES/DES 算法计算 Authenticator，无需手动抓包
- **EPG 节目单** — XMLTV 格式（兼容 APTV / TiviMate / Tvheadend），支持多天数据（默认 8 天）
- **Web 管理界面** — 仪表盘、频道列表、EPG 浏览、配置修改、日志查看
- **定时同步** — 每天随机时间自动刷新频道和 EPG
- **Docker 部署** — 开箱即用

---

## 快速开始

### 前置条件

- 电信 IPTV 网络环境（需能访问内网 EPG 服务器）
- 机顶盒的 `USER_ID`、`STBID`（可从机顶盒设置或抓包获取）
- (可选) 机顶盒 `MAC` 地址和加密密钥，用于动态 Authenticator 生成

### 配置

```bash
cp .env.example .env
# 编辑 .env，填入你的配置
```

最低配置（静态 Authenticator，需抓包获取）：

```ini
USER_ID=your_user_id@itv
STBID=your_stbid_hex
BASE_URL=http://your-epg-server:8080
Authenticator=your_static_authenticator
UDPXY=http://your-udpxy-server:7088/udp/
```

推荐配置（动态 Authenticator，自动计算）：

```ini
USER_ID=your_user_id@itv
STBID=your_stbid_hex
BASE_URL=http://your-epg-server:8080
UDPXY=http://your-udpxy-server:7088/udp/
MAC=00:11:22:33:44:55
ENCRYPT_KEY=your_8byte_key
STB_TYPE=B860AV1.1-T2
STB_IP=192.168.1.100
```

> 配置也可通过 Web 界面（系统配置页面）修改，保存后会写入 `static/config.json`。

### 本地运行

```bash
pip install -r requirements.txt
python app.py
```

打开 http://localhost:8899 即可访问管理界面。

### Docker 部署

```bash
docker build -t autoiptv .
docker run -d \
  --name autoiptv \
  -p 8899:8899 \
  -v $(pwd)/.env:/app/.env \
  -v $(pwd)/static:/app/static \
  autoiptv
```

---

## 配置项

| 变量 | 说明 | 必需 |
|---|---|---|
| `USER_ID` | 机顶盒所属用户 ID（通常为 `xxx@itv`） | 是 |
| `STBID` | 机顶盒序列号 / 设备 ID | 是 |
| `BASE_URL` | EPG 门户基础地址 | 是 |
| `UDPXY` | UDPXY 转发地址（igmp → http） | 是 |
| `Authenticator` | 静态 Authenticator（抓包获取） | 动态启用时可选 |
| `MAC` | 机顶盒 MAC 地址 | 动态认证必需 |
| `ENCRYPT_KEY` | 8 位加密密钥 | 动态认证必需 |
| `STB_IP` | 机顶盒 IP（用于 Authenticator 计算） | 推荐 |
| `EPG_HOST` | EPG 节目单服务器地址 | 否 |
| `STB_TYPE` | 机顶盒型号，如 `B860AV1.1-T2` | 否 |
| `DNS_SERVERS` | 内网 DNS 服务器（逗号分隔，用于解析 EAS 域名） | 否 |
| `EAS_DOMAIN` | EAS 认证服务器域名 | 否 |
| `EAS_IP` | EAS 固定 IP（非空则跳过 DNS 解析） | 否 |
| `EAS_SESSION_IP` | EAS 会话初始化参数 IP | 否 |
| `EAS_STB_TYPE` | EAS 会话设备类型 | 否 |
| `SECRET_KEY` | Flask secret key | 建议修改 |

---

## 订阅地址

启动后，以下地址可在播放器中订阅：

| 地址 | 说明 |
|---|---|
| `http://your-host:8899/sub` | UDPXY 频道列表（igmp → http） |
| `http://your-host:8899/sub_rtsp` | RTSP 频道列表（含回看） |
| `http://your-host:8899/epg.xml` | EPG 节目单（XMLTV 格式） |

### 播放器配置

**APTV** 配置示例：

```
名称: AutoIPTV
订阅: http://host:8899/sub_rtsp
EPG:   http://host:8899/epg.xml
```

**TiviMate** 配置示例：

```
播放列表: http://host:8899/sub
EPG:      http://host:8899/epg.xml
```

---

## API 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/save_config` | 保存配置 |
| GET | `/refresh_channels` | 获取 UDPXY 频道列表文本 |
| GET | `/refresh_channels_rtsp` | 获取 RTSP 频道列表文本 |
| GET | `/refresh_logs` | 获取系统日志 |
| GET | `/api/sync_channels` | 后台触发频道同步 |
| GET | `/sub` | UDPXY 订阅（M3U） |
| GET | `/sub_rtsp` | RTSP 订阅（M3U + catchup） |
| GET | `/epg.xml` | EPG 节目单（XMLTV） |
| GET | `/api/epg` | EPG 数据（JSON） |
| GET | `/api/epg/stats` | EPG 统计数据 |
| GET | `/api/epg/fetch_status` | 异步 EPG 抓取状态 |
| GET | `/api/epg/dates` | 可用 EPG 日期列表 |
| GET | `/api/epg/channels` | 有 EPG 数据的频道列表 |
| GET | `/api/epg/programs` | 分页查询节目 |
| GET | `/refresh_epg` | 手动刷新 EPG（后台异步） |
| GET | `/init_epg` | 初始化 EPG 数据 |
| GET | `/rtsp_status` | RTSP 鉴权状态查询 |

---

## 技术架构

```
┌──────────┐     ┌──────────────┐     ┌────────────┐
│ IPTV EPG │ ←── │  AutoIPTV   │ ──→ │  UDPXY     │
│  门户     │     │  (Flask)    │     │  (igmp→http)│
└──────────┘     │             │     └────────────┘
                 │  ┌───────┐  │     ┌────────────┐
┌──────────┐     │  │订阅M3U│  │ ──→ │  播放器    │
│ EAS 认证  │ ←── │  │EPG    │  │     │ APTV/Pot等│
│ 服务器    │     │  └───────┘  │     └────────────┘
└──────────┘     └──────────────┘
```

- 通过 **EAS 认证** 获取 EncryptToken，动态计算 Authenticator
- 登录 **EPG 门户** 抓取频道列表（igmp + rtsp）
- 使用 **APScheduler** 每天随机时间自动同步（13:00~17:00）
- Token **48 小时缓存**，减少重复认证
- EPG 采用 **内存缓存 + 文件缓存**，支持后台异步抓取

---

## 常见问题

### 如何获取 USER_ID 和 STBID？

从机顶盒的设置页面或通过抓包（Wireshark / Charles）获取：
- 抓取机顶盒开机时的 HTTP 请求
- 查找 `auth.jsp` 请求中的 `UserID` 和 `STBID` 参数

### 如何获取静态 Authenticator？

抓包机顶盒的 `auth.jsp` POST 请求，其中的 `Authenticator` 参数值。

### 动态 Authenticator 如何配置？

需要 `MAC` 地址和 `ENCRYPT_KEY`（8 位加密密钥）。
- MAC 可从机顶盒网络设置获取
- 密钥需从机顶盒文件系统提取或通过抓包分析

---

## 许可证

[MIT](LICENSE)
