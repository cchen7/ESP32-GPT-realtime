# gpt-assistant 项目实施计划

家用 GPT 语音助手,基于 Azure OpenAI `gpt-realtime-2` + M5Stack 硬件,第一期硬件为 AtomS3R + Atomic Echo Base。

> 硬件细节看 [`hardware_atoms3r_echobase.md`](./hardware_atoms3r_echobase.md)(原理图、寄存器、初始化序列、引脚总表均已落到该文件)。本 plan 只承载产品/架构/里程碑层面的决策。

---

## 0. 决策摘要(2026-06-13 与用户对齐)

| 项 | 决策 | 备注 |
|---|---|---|
| 设备端框架 | **纯 ESP-IDF (≥5.3) + `esp_codec_dev`** | 不引 Arduino / 不引 M5Unified |
| 音频采样率 | **全程 16 kHz mono PCM16** | wake/上传/播放统一,桥端把 Azure 24 kHz 下采到 16 kHz 再下发 |
| 端 ↔ 桥传输 | **LAN 明文 WS** | 16 kHz ≈ 256 kbps,完全够 |
| 唤醒方式 | **本地 wake word — "你好小智"**(乐鑫预置 `wn9_nihaoxiaozhi_tts`) | 不与小米小爱撞名,免费可商用 |
| 备用唤醒 | **AtomS3R 板载 G41 按键作 PTT/wake fallback** | wake word 调不出来时还有手 |
| 配网方式 | **SoftAP captive portal**(`wifi_provisioning`) | 首次配网走 Wi-Fi 设置页 |
| 第一期状态显示 | **无**(只通过 USB 串口 log 观察) | LCD 留到 M7 做 kawaii 表情 |
| 屏幕动画方案 | **`lvgl_kawaii_face`(GitHub `0015/lvgl_kawaii_face`)** | LVGL 9 + 17+ kawaii 表情,过程化动画;M7 才做 |
| 桥服务器 | 局域网 Debian 主机 | 持 AAD/Bing 凭证,复用现有 `gpt-realtime2-demo` 代码 |
| 云端 | 现有 Azure `gpt-realtime-2` + Bing grounding | 不动 |

---

## 1. 系统架构

```
┌─ AtomS3R + EchoBase (ESP-IDF) ─────┐         ┌─ Debian 桥服务器 (Python) ─────┐         ┌─ Azure ───────┐
│                                     │  WS     │                                 │  WSS    │               │
│ ESP-SR WakeNet 听 "你好小智"        │ ─16k──► │ device_ws_server                │ ──────► │ gpt-realtime-2 │
│       │                             │ PCM16   │       │                         │ 24k     │               │
│       ▼ (唤醒后或 G41 按下)         │ ◄─16k── │       ▼  (24k → 16k 重采样)      │ ◄────── │ Bing grounding │
│ I2S mic 16k mono PCM16              │         │ session_manager (每设备一会话)  │         │               │
│ I2S spk 16k mono PCM16              │         │       │                         │         └───────────────┘
│ WS client (esp_websocket_client)    │         │       ▼                         │
│ G41 按键 (PTT 备用)                 │         │ azure_realtime (RealtimeClient) │
│ Wi-Fi prov (SoftAP captive portal)  │         │ tools.web_search (复用 grounding.py)│
└─────────────────────────────────────┘         └─────────────────────────────────┘
```

为什么要中间这台 Debian:
1. AAD token / Bing 凭证不进设备
2. TLS 卸载,设备只跑明文 WS
3. `grounding.py`/persona/未来工具零迁移复用
4. 多设备路由 / 字幕 / 历史集中

---

## 2. 设备端固件

### 2.1 目录结构(为复用做的分层)

```
device/firmware/
├── CMakeLists.txt
├── sdkconfig.defaults             # PSRAM Octal, I2S 新驱动, ESP-SR, partitions
├── partitions.csv                 # app, model(WakeNet), nvs
├── main/
│   ├── CMakeLists.txt
│   ├── idf_component.yml          # esp_codec_dev, esp_websocket_client, esp-sr, lvgl(M7)
│   └── main.c                     # 选 BSP, 组装 voice_link/wakeword/app_state/(display)
└── components/
    ├── bsp_common/                # 抽象接口(硬件无关)
    │   └── include/
    │       ├── bsp_audio.h        # mic_read/spk_write/set_volume/mute
    │       ├── bsp_button.h       # register(cb)
    │       └── bsp_display.h      # init/lvgl_disp_handle (M7 才用)
    ├── bsp_atoms3r_echobase/      # 第一期 BSP
    │   ├── include/bsp_board.h    # 引脚常量(详见 hardware_atoms3r_echobase.md §3)
    │   ├── bsp_audio.c            # esp_codec_dev + driver/i2s_std + PI4IOE PA 控制
    │   ├── bsp_button.c           # G41 按键
    │   └── bsp_display.c          # M7 才实现: ST7735 via esp_lcd + LP5562 背光
    ├── pi4ioe/                    # 通用 PI4IOE5V6408 驱动(~80 行)
    ├── voice_link/                # 硬件无关
    │   ├── include/voice_link.h
    │   ├── voice_link.c           # WS 客户端 + 协议帧 + 重连
    │   └── proto.h
    ├── wakeword/                  # 硬件无关
    │   └── wakeword.c             # ESP-SR WakeNet "你好小智" 封装
    ├── app_state/                 # idle/listening/thinking/speaking/error 状态机
    ├── netprov/                   # wifi_provisioning + softAP + captive portal
    └── (M7) ui_face/              # lvgl_kawaii_face 集成层,把状态机映射成表情
```

**复用性原则**:`bsp_common/` 只定义接口,`voice_link/`、`wakeword/`、`app_state/`、`netprov/`、`ui_face/` 全部不依赖具体硬件,任何 BSP 都能复用。第二期接入新 M5 设备(Core2、Cardputer)只需写 `bsp_<board>/`。

### 2.2 关键引脚常量

完整引脚总表、I2C 地址、电源链、初始化序列见 [`hardware_atoms3r_echobase.md`](./hardware_atoms3r_echobase.md) §3、§10。

第一期固件用到的 GPIO 速查:
- EXT I2C: SCL=G39, SDA=G38(EchoBase ES8311 0x18 + PI4IOE 0x43)
- I2S: BCLK=G8, LRCK=G6, DOUT=G5, DIN=G7,**MCLK 不接**(`I2S_GPIO_UNUSED`,`use_mclk=false`)
- 按键: G41(USER_BUT,低有效)
- 第一期不动 SYS I2C(G0/G45)、SPI(G14/15/21/42/48)、IR(G47)

### 2.3 关键依赖

```yaml
# main/idf_component.yml (M1~M6)
dependencies:
  espressif/esp_codec_dev: "^1.5.0"
  espressif/esp_websocket_client: "^1.3.0"
  espressif/esp-sr: "^2.0.0"
  espressif/protocol_examples_common: "*"
  idf: ">=5.3"
# M7 追加: lvgl/lvgl ^9.0, esp_lcd 自带
```

---

## 3. 桥服务器(Debian)

### 3.1 目录结构

```
bridge/
├── pyproject.toml
├── .env.example
├── bridge/
│   ├── server.py                  # asyncio 入口
│   ├── transports/
│   │   ├── device_ws_server.py    # ws://0.0.0.0:8765
│   │   └── azure_realtime.py      # 从 demo 抽取的 RealtimeClient(去掉 sounddevice)
│   ├── tools/
│   │   ├── web_search.py          # = 现 gpt-realtime2-demo/grounding.py
│   │   └── registry.py
│   ├── session.py                 # 一 DeviceSession 串起设备 WS 和 Azure WS
│   ├── audio.py                   # 24kHz ↔ 16kHz 重采样(scipy.signal.resample_poly)
│   ├── config.py
│   └── persona.py
├── tests/
└── README.md
```

### 3.2 重采样要点

- Azure 模型输出 24 kHz → 桥用 `scipy.signal.resample_poly(audio, up=2, down=3)` 转 16 kHz 再下发
- 设备上行 16 kHz 不变,Azure 端按 16 kHz 接收(Realtime API 支持 16k 输入)
- 实测 CPU 开销:1 秒 24k mono PCM16 重采样在树莓派 4 上 < 5ms,Debian 主机更不在话下

### 3.3 部署形态

systemd service,端口 8765 仅监听 LAN 网段,用 `AzureCliCredential`(人工 `az login`)或 SP(`.env`)。

---

## 4. 设备 ↔ 桥协议 v1

WebSocket,二进制帧承载音频,文本帧承载控制。

### 设备 → 桥

| 帧 | 类型 | 内容 |
|---|---|---|
| 控制 | text | `{"type":"hello","device_id":"atoms3r-01","fw":"0.1.0"}` |
| 控制 | text | `{"type":"wake","src":"wakeword\|button","ts":...}` |
| 控制 | text | `{"type":"stop"}` 用户主动停止(可选) |
| 音频 | binary | PCM16LE **16 kHz** mono,20 ms/帧(320 samples = 640 bytes) |

### 桥 → 设备

| 帧 | 类型 | 内容 |
|---|---|---|
| 控制 | text | `{"type":"state","value":"idle\|listening\|thinking\|speaking\|error"}` |
| 控制 | text | `{"type":"transcript","role":"user\|assistant","text":"..."}` 可选(M7 才用) |
| 音频 | binary | PCM16LE **16 kHz** mono(桥已从 24 kHz 重采样) |
| 控制 | text | `{"type":"clear_audio"}` barge-in,设备清空播放缓冲 |

---

## 5. 里程碑

### M1 — 服务器桥重构(独立于设备,先跑通)
- 把 `gpt-realtime2-demo/realtime_voice_demo.py` 拆成 `RealtimeClient` 类(去掉 sounddevice)
- 写 `device_ws_server.py`,加 24→16 kHz 重采样
- 用一个 Python 测试客户端(Mac sounddevice)模拟设备验证回环
- ✅ 验收:Mac 当虚拟设备连到桥,语音 + 联网搜索都正常

### M2 — 设备最小固件:I2S 回环
- ESP-IDF 项目骨架 + BSP 初始化(I2C → PI4IOE static mute → ES8311 → I2S → unmute)
- 不联网,mic → DMA → spk 直通
- ✅ 验收:对麦克风讲话,扬声器清晰回声,无上电 pop

### M3 — 设备联网 + WS 客户端
- SoftAP captive portal 配网(`wifi_provisioning`)
- `voice_link` 组件:WS 客户端连桥,mic→WS,WS→spk
- 断网自动重连
- ✅ 验收:对 AtomS3R 讲话,桥能收到 16k PCM;桥发音频回去能播

### M4 — 端到端串通(无 wake word,先按键 PTT)
- 加 G41 按键:按下进入 listening,松开进入 idle
- 桥转发 Azure,完整跑通问答 + Bing 联网
- ✅ 验收:按住 G41 问"上海今天天气",听到 gpt-realtime-2 回答(含联网搜索)

### M5 — 本地 wake word("你好小智")
- 集成 ESP-SR WakeNet,加载 `wn9_nihaoxiaozhi_tts` 模型
- 待机时只跑 WakeNet,不上传音频(省流量、保护隐私)
- 唤醒后切到 listening,与 G41 按键并存
- ✅ 验收:不说唤醒词时设备静默;说"你好小智"后进对话

### M6 — 可靠性 + 复用层验证
- 桥重启不掉设备、设备断网重连、长时间运行稳定
- 写第二个 BSP 占位(可空实现),证明分层合理
- 文档 `device/firmware/BSP_PORTING.md`
- ✅ 验收:跑 24 小时不挂

### M7 — 屏幕动画(`lvgl_kawaii_face`)
- 接 ST7735 LCD 驱动(esp_lcd + LVGL 9 + 自写 panel)
- 接 SYS I2C → LP5562 控背光
- 集成 `0015/lvgl_kawaii_face`,把 app_state 状态映射到表情:
  - idle → Neutral / Sleepy(久未交互时)
  - listening → Curious / Excited
  - thinking → Working
  - speaking → Excited / Happy
  - error → Sad
- ✅ 验收:小孩看着表情能猜出助手在做什么

---

## 6. 待办待澄清

- [ ] 自定义 wake word("小派"等),走 microWakeWord 自训(M7 后再说)
- [ ] 多设备时,设备身份在哪发(MAC 自动 vs 桥配)
- [ ] OTA(本项目无量产压力,可后置)
- [ ] 桥服务器 Web 管理页(看会话状态、字幕、历史)

---

## 7. 临时文件

按全局 CLAUDE.md 约定,build 产物/临时实验/scratch 全部输出到:
`~/Local/my-proj-temp/gpt-assistant/`
(本次硬件调研已在 `~/Local/my-proj-temp/gpt-assistant/hw-research/` 落地)
