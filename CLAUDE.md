# CLAUDE.md — gpt-assistant 项目

> 项目级指南。新会话起手先读这份 + `plan.md`。

## 项目是什么

家用 GPT 语音助手:Azure OpenAI `gpt-realtime-2` + M5Stack 硬件。
第一期硬件:**AtomS3R + Atomic Echo Base**(已在桌上)。
设备 → LAN 桥(Debian) → Azure 三层架构,凭证只在桥。

## 文档地图

| 文件 | 回答什么问题 |
|---|---|
| **plan.md** | 架构、端-桥-云通讯协议、7 个里程碑 M1~M7、设备/桥目录结构、复用层设计 |
| **hardware_atoms3r_echobase.md** | 硬件 spec(每芯片/每线/每寄存器都确认过),引脚总表,I2C/I2S 通路,启动序列代码模板 |
| **bridge/README.md** | 桥本地开发(Mac)与跑法 |
| **bridge/deploy/README.md** | Debian 部署(`systemctl --user`)+ 已知坑 |
| **gpt-realtime2-demo/** | 原 Mac demo(已脱敏:endpoint/sub-id 全在 `.env`)。桥的 `azure_realtime.py` / `tools/web_search.py` 就是从这里抽出来重构的 |

## 锁定的关键决策(不要再讨论,除非用户明确要求改)

- **设备端框架**: 纯 ESP-IDF ≥5.3 + `esp_codec_dev`,不引 Arduino / M5Unified
- **音频采样率**: 全程 16 kHz mono PCM16。设备 ↔ 桥 ↔ Azure 上行都 16k;Azure 24k 输出在桥端 `bridge/audio.py` 下采到 16k 再下发
- **设备-桥传输**: LAN 明文 WS,**设备从 DHCP gateway 取桥 IP**(`ws://<dhcp-gateway>:8765`),无 mDNS
- **唤醒**: 乐鑫预置 `wn9_nihaoxiaozhi_tts`("你好小智"),G41 板载按键作 PTT 备用
- **配网**: SoftAP captive portal(`wifi_provisioning` 组件)
- **桥部署**: Debian 上 `~/work/gpt-assistant-bridge/`,`systemctl --user enable --now gpt-bridge`,端口 8765
- **凭证**: Debian(无 az cli)用 SP via `.env`;Mac dev 用 `az login`。`DefaultAzureCredential` 自动二选一
- **device_id**: MAC 后 3 字节,形如 `atoms3r-AB12CD`
- **状态显示**: 第一期无 LCD,只串口 log;M7 才加 0.85" LCD + `lvgl_kawaii_face`(17+ kawaii 表情)

## 当前进度(截至 2026-06-14)

| 阶段 | 状态 | 备注 |
|---|---|---|
| 调研 + 架构 | ✅ 落到 plan.md / hardware.md | 含硬件原理图逐线确认 |
| M1-T1~T4 桥代码 | ✅ 提交 `9a50be8` + `2fc2071` | 单测 5/5 过 |
| M1-T5 Mac 本地验收 | 🟡 **卡在 Azure auth** | WS 协议层已通(handshake、hello、tool registry 全验过);只等 az 凭证续期 |
| M1-T6 Debian 部署 | ⏸ 等 T5 | 部署文件已就位(`bridge/deploy/`) |
| M2~M7 | ⏸ 设备固件,M1 通了再开 | |

Git: https://github.com/cchen7/ESP32-GPT-realtime  (`main`, 2 commits)

## 下次接续 M1-T5(给 Claude 的指令)

**用户先跑(交互命令,Claude 代不了)**:
```bash
az logout
az login --tenant <your-tenant-id> --scope "https://cognitiveservices.azure.com/.default"
az account set --subscription <your-subscription-id>
```
(tenant 和 sub id 已写在 `bridge/.env.sp.bak` 和用户 az 历史里。新会话可让用户直接贴,或从 `az account list` 查。)

**Claude 续**:
```bash
cd /Users/chenxin/Local/ESP32-proj/gpt-assistant/bridge
source .venv/bin/activate
# 桥(后台,unbuffered)
NO_PROXY=127.0.0.1,localhost python -u -m bridge.server &
# 假设备(前台,真 sounddevice)
NO_PROXY=127.0.0.1,localhost python tools/local_test_client.py ws://127.0.0.1:8765
```

**验收**: 对 Mac 麦说"你好" → 听到回答;问"上海今天天气" → 触发 Bing grounding,回答带来源 URL。

通过后立刻进 T6:rsync 到 `debian:~/work/gpt-assistant-bridge/`,装 venv,把 `bridge/.env.sp.bak` 改名为 `.env` 放过去(SP 凭证),enable systemd unit。详见 `bridge/deploy/README.md`。

## 工程坑(踩过的,新会话别再踩)

1. **macOS 透明代理(ClashX/Surge)截 loopback**:跑 bridge 和 client **必设** `NO_PROXY=127.0.0.1,localhost`,否则 WS handshake 收 EOF
2. **stdout buffer**:桥已 `sys.stdout.reconfigure(line_buffering=True)`,跑时配 `python -u` 双保险(systemd unit 已配)
3. **az 凭证 90 天不活动过期**:AADSTS700082。Mac 上要定期 `az login`
4. **SP 在某些 tenant 触发 Conditional Access**:AADSTS53003。debian 是稳定 LAN IP,大概率不被拦;Mac 临时改用 az login
5. **EchoBase 没接 MCLK**:ES8311 必须配 `use_mclk=false`(用 SCLK 派生主时钟)。漏了完全没声
6. **NS4150 PA 上电默认 enable**(R10 4.7K 上拉到 CTRL):启动序列必须先 PI4IOE P0=0 静音 → init codec → 启 I2S → 再 unmute,否则上电 pop
7. **AtomS3R 两条独立 I2C 总线**:SYS(G0/G45,挂 LP5562/BMI270)和 EXT(G39/G38,挂 EchoBase 的 ES8311/PI4IOE5V6408)。**不能合并到一个 i2c_master_bus 实例**
8. **AtomS3R LCD 驱动 IC**(若 M7 用):2026-05-14 之后批次是 ST7735,旧资料按 GC9107 配 LVGL 会黑屏

## 临时文件位置

按全局 CLAUDE.md 约定:`~/Local/my-proj-temp/gpt-assistant/`
本项目硬件调研的原理图 PDF / 厂商库源码已落:`~/Local/my-proj-temp/gpt-assistant/hw-research/`

## 全局偏好(也要遵守)

详见 `~/.claude/CLAUDE.md` 和自动 memory(`~/.claude/projects/.../memory/MEMORY.md`):
- macOS / zsh / 绝对路径
- 简单优先、surgical changes、不预留单次抽象
- **嵌入式动工前彻底确认硬件 spec / 接口 / 数据走向**(项目 feedback memory,这是 hardware.md 存在的原因)
- skill 只装项目级,不全局
