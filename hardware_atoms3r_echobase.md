# 硬件确认报告 — AtomS3R + Atomic Echo Base

> 基于官方原理图 PDF、官方 datasheet 与 `m5stack/M5Atomic-EchoBase` 实际驱动源码交叉验证。
> 用户硬件:**标准 AtomS3R(SKU C126)+ Atomic Echo Base(SKU A149)**。

---

## 1. 设备概览

| 项 | 主控 AtomS3R | 底座 Atomic Echo Base |
|---|---|---|
| SKU | C126 | A149 |
| 核心芯片 | ESP32-S3-PICO-1-N8R8 | ES8311 codec + NS4150B PA + MEMS mic + PI4IOE5V6408 |
| 形态 | 24×24×12.9 mm,Type-C 供电 | 与 AtomS3R 底部 9-pin 直插对接 |
| 板载外设 | 0.85" ST7735 LCD,LP5562 RGB,BMI270+BMM150,IR LED,用户按键 | 麦克、扬声器、PA、IO 扩展器 |

**版本注意点(2026-05-14 变更)**:LCD 驱动 IC 已从 `GC9107` 换为 `ST7735`。我们项目第一期 EchoBase 不动 LCD,影响仅限"未来如果用 AtomS3R 屏做状态显示"——届时 LVGL 配置选 ST7735。

---

## 2. 完整芯片清单

### 2.1 AtomS3R 板载

| U# | 型号 | 角色 | 总线 | I2C 地址 | 备注 |
|---|---|---|---|---|---|
| U1 | ESP32-S3-PICO-1-N8R8 | 主控 | — | — | 240MHz 双核 LX7,8MB Flash,**8MB Octal PSRAM**,Wi-Fi 2.4G+BLE |
| U2 | JW5712 | 5V→3.3V DC-DC | — | — | 供给整板及通过底座给 EchoBase |
| U4 | LP5562 | 4 通道 RGB LED 驱动 | **SYS I2C**(G0/G45) | 0x30 | 控制板载 RGB + LCD 背光 W 通道 |
| U6 | BMI270 + BMM150 | 9 轴 IMU | SYS I2C(G0/G45) | 0x68 | BMM150 经 BMI270 auxiliary I2C |
| LCD | ST7735(0.85" 128×128) | 屏 | SPI | — | CS=G14, SCK=G15, MOSI=G21, DC=G42, RST=G48, BL=LP5562_W |
| IR | LED | 红外发射 | GPIO | — | DRV=G47 |
| BUTTON | 用户按键 | 按键 | GPIO | — | G41(USER_BUT) |

### 2.2 EchoBase 底座

| U# | 型号 | 角色 | 总线 | I2C 地址 | 备注 |
|---|---|---|---|---|---|
| U1 | MSM381A3729H9BPC | MEMS 麦克 | 模拟 | — | 单端模拟输出,经 100nF 耦合到 ES8311 MIC1P;MIC1N 接 AGND |
| U2 | ES8311 | mono 音频 codec | **EXT I2C**(G39/G38) + I2S | **0x18** | CE=GND 决定地址,MCLK pin 通过 R3(0Ω) 直接接 3.3V(常高),实际靠 SCLK 派生主时钟 |
| U3 | NS4150B | D 类功放 | — | — | INP/INN 来自 ES8311 OUTP/OUTN(100nF 耦合),CTRL 来自 U4 P0(R10 4.7K 上拉到 3.3V,**默认 enable**) |
| U4 | PI4IOE5V6408ZTAEX | 8 位 I2C IO 扩展器 | EXT I2C(G39/G38) | **0x43** | ADDR=GND;**P0 唯一在用**(控制 NS4150B CTRL);P1~P7 全部空置;INT 空连接;RESET 通过 R12 4.7K 上拉 |

---

## 3. AtomS3R 引脚总表(物理分组)

### 3.1 板载内部(不引出到底座)

| GPIO | 用途 | 接到 |
|---|---|---|
| G0 | **SYS_SCL** | LP5562, BMI270 |
| G45 | **SYS_SDA** | LP5562, BMI270 |
| G41 | USER_BUT | 板载用户按键(低有效) |
| G47 | IR_LED_DRV | IR LED 驱动 MOSFET |
| G14 | DISP_CS | LCD 片选 |
| G15 | SPI_SCK | LCD 时钟 |
| G21 | SPI_MOSI | LCD 数据 |
| G42 | DISP_RS | LCD DC |
| G48 | DISP_RST | LCD 复位 |
| (LP5562 W) | LCD_BL | LCD 背光,通过 LP5562 W 通道 PWM(推荐 500Hz) |

### 3.2 底部 9-pin Atom 底座接口(连接 EchoBase)

| AtomS3R GPIO | EchoBase J1/J2 引脚 | EchoBase 信号 | 用途 |
|---|---|---|---|
| **3.3V** | J1 pin 1 | 3.3V | EchoBase 全部 3.3V 供电(EchoBase 无 LDO) |
| **G5** | J1 pin 2 | DSDIN(ES8311 pin 9) | **I2S DOUT(MCU→codec→speaker)** |
| **G6** | J1 pin 3 | LRCK(ES8311 pin 8) | **I2S WS / LRCK** |
| **G7** | J1 pin 4 | ASDOUT(ES8311 pin 7) | **I2S DIN(mic→codec→MCU)** |
| **G8** | J1 pin 5 | SCLK(ES8311 pin 6) | **I2S BCLK,同时是 ES8311 的 MCLK 源** |
| **G39** | J2 pin 1 | SCL(ES8311 pin 1, U4 pin 13) | **EXT I2C SCL**(4.7K 上拉到 3.3V) |
| **G38** | J2 pin 2 | SDA(ES8311 pin 19, U4 pin 14) | **EXT I2C SDA**(4.7K 上拉到 3.3V) |
| **5V** | J2 pin 3 | 5V | 仅"经过"EchoBase 板;EchoBase 自己用 3.3V |
| **GND** | J2 pin 4 | GND | |

### 3.3 HY2.0-4P Grove(Port.A,未占用,留给第二阶段扩展)

| Pin | 颜色 | 信号 |
|---|---|---|
| 1 | Black | GND |
| 2 | Red | 5V |
| 3 | Yellow | **G2** |
| 4 | White | **G1** |

---

## 4. 两条独立 I2C 总线(易踩坑,必须分清)

### SYS I2C(板载,G0=SCL / G45=SDA)
- 设备:LP5562(0x30)、BMI270(0x68)→BMM150
- 第一期**只在用 LED 状态指示和 IMU 时才启用**

### EXT I2C(底座,G39=SCL / G38=SDA)
- 设备:ES8311(0x18)、PI4IOE5V6408(0x43)
- **第一期必用**
- 上拉电阻在 EchoBase 上(R1/R2 各 4.7K → 3.3V)
- M5 库实测频率 = 100 kHz(可拉到 400 kHz,但 codec 控制流量小,无需追快)

---

## 5. I2S 音频通道(EXT,无 MCLK)

| 信号 | AtomS3R GPIO | ES8311 引脚 | 方向 |
|---|---|---|---|
| BCLK / SCLK | **G8** | pin 6 | MCU → codec |
| WS / LRCK | **G6** | pin 8 | MCU → codec |
| DOUT(spk) | **G5** | pin 9 (DSDIN) | MCU → codec |
| DIN(mic) | **G7** | pin 7 (ASDOUT) | codec → MCU |
| MCLK | **不连接**(`I2S_GPIO_UNUSED`) | pin 2 经 R3=0Ω 接 3.3V | — |

**关键时钟约束**(ES8311 datasheet 第 6 章 + R3 接线决定):
- EchoBase **没有给 ES8311 喂 MCLK**,MCLK 引脚被 R3 接到 3.3V 常高
- 必须在 codec init 时设 `mclk_from_mclk_pin = false`,让 codec **用 SCLK(BCLK) 派生内部主时钟**
- ADC/DAC 都需要内部主时钟 ≥ 256×LRCK,且为 16 整数倍
- ESP-IDF 端 I2S 用 **标准模式 STD,Philips 格式,Stereo 16-bit slot**,这样 BCLK = 32×LRCK,ES8311 内部需要 MULT_PRE=8 倍频得到 256×LRCK(esp_codec_dev 的 `es8311_codec` 驱动自动算好,不用手填)
- 16 kHz/24 kHz/48 kHz 都满足该约束

---

## 6. 功放(NS4150B)控制路径

```
ESP32-S3 ──EXT I2C──► PI4IOE5V6408 P0 ──CTRL──► NS4150B
                       (push-pull)      ▲
                                        │
                              R10 4.7K 上拉到 3.3V
                              (PI4IOE 未驱动时默认 enable)
```

**含义**:
- 上电瞬间 PI4IOE 所有 P 口默认 input(高阻),R10 把 CTRL 拉高 → **NS4150 默认就 enable**
- 这是个隐患:codec 还没初始化时若 OUTP/OUTN 有噪声,会被功放放大成 pop
- **正确启动顺序**:
  1. EXT I2C 初始化
  2. PI4IOE5V6408 init → P0 设为 output,写 0(强制拉低 CTRL,**显式静音**)
  3. ES8311 init(寄存器 + 时钟 + 音量 + 模拟麦克模式)
  4. I2S 启动 + DMA 缓冲清零
  5. 写 PI4IOE P0 = 1(unmute,放音)

M5 库源码确认的 PI4IOE 初始化(`pi4ioe_init`):
```c
read  0x00 (CTRL)                  // 读现状
write 0x07 (Output High-Z) = 0x00  // 所有 IO 推挽(0=正常,1=高阻)
write 0x0D (Pull-up enable) = 0xFF // 全部启用内部上拉
write 0x03 (Direction) = 0x6F      // P0/1/2/3/5/6=output, P4/7=input
write 0x05 (Output reg) = 0xFF     // 全部输出高(P0=高 → PA enable)
// setMute(true)  时:write 0x05 = 0x00
// setMute(false) 时:write 0x05 = 0xFF
```

**实际只用到 P0**,其余 output 位无影响(没接东西)。

---

## 7. 电源链

```
USB Type-C 5V ──► JW5712 DC-DC ──► 3.3V ──┬─► ESP32-S3
                                          ├─► BMI270/LP5562/IR/LCD
                                          └─► 底座 J1 pin 1 ──► EchoBase 全板 3.3V
                                              (ES8311 PVDD/DVDD/AVDD,
                                               NS4150B VCC,MEMS mic,PI4IOE VDD)

USB 5V ──直通──► 底座 J2 pin 3(5V) [本项目未使用]
```

**关键事实**:
- EchoBase **没有自己的 LDO**,完全依赖 AtomS3R 的 3.3V
- NS4150B VCC = 3.3V(典型输出功率 ~1.4W@4Ω/3.3V,小喇叭够用)
- AtomS3R 板载 5V→3.3V LDO 是 JW5712,够同时供 MCU + 板载外设 + EchoBase

---

## 8. 完整数据通路

### 8.1 上行(mic → ASR/云端)

```
声音 ─► MEMS mic ─模拟单端─► ES8311 MIC1P
                          ► ES8311 ADC(24-bit Σ-Δ)
                          ► I2S(slot 16-bit,Stereo,Philips)
                            BCLK=G8, LRCK=G6, DIN=G7
                          ► ESP32-S3 I2S 外设 + DMA
                          ► PSRAM 环形缓冲(WakeNet 期 16 kHz,对话期 24 kHz)
   ┌───────────────────────┴────────────────────┐
   ▼ (wake 阶段)                                  ▼ (对话阶段,wake 命中后)
WakeNet9 推理(ESP-SR)                        WebSocket 客户端
  ↓ 命中 "你好小智"                              base64-PCM16 → Debian 桥
触发状态机切到 listening
```

### 8.2 下行(云端 → spk)

```
WebSocket 二进制帧(PCM16 24kHz mono)
  ► ESP32-S3 内存缓冲
  ► I2S TX DMA
    BCLK=G8, LRCK=G6, DOUT=G5
  ► ES8311 DAC ─差分─► OUTP/OUTN
                     ► 100nF DC 阻断
                     ► NS4150B INN/INP
                     ► VoP/VoN(差分功放输出)
                     ► 内置喇叭
```

### 8.3 控制(I2C 一次性初始化 + 偶尔 mute)

```
ESP32-S3 ──EXT I2C 100kHz──► ┬─► ES8311 @0x18(寄存器组初始化 + 音量 + mic 增益)
                              └─► PI4IOE5V6408 @0x43(P0 控制 NS4150 CTRL)
```

---

## 9. 双采样率策略(WakeNet vs gpt-realtime)

| 阶段 | 采样率 | 来源 / 去向 | 备注 |
|---|---|---|---|
| 待机听 wake word | **16 kHz** mono PCM16 | mic → WakeNet | ESP-SR WakeNet 要求 16 kHz |
| 唤醒后 + 用户说话 | **16 kHz** mono PCM16 | mic → 桥 → Azure(桥端重采样 24k 上交) | 设备保持 16k,简化 I2S |
| 模型回放 | **24 kHz** mono PCM16 | Azure → 桥(可选重采样到 16k)→ 设备 | 设备如果只跑 16k I2S,桥下采到 16k 再发 |

**两条路可选**:
- **方案 A — 全程 16 kHz**(推荐):桥服务器把 Azure 24k 下采到 16k 再下发,设备 I2S 永远工作在 16k。**最简单,WakeNet 与对话共用一套 I2S 配置,不需要 reconfig**
- 方案 B — 双速:wake 时 16k,对话时切到 24k。需要 `i2s_channel_disable → reconfig clk → enable`,有 100~200ms 切换间隙

→ **采用方案 A,确认后写入 plan.md**

---

## 10. ESP-IDF 端初始化序列(可直接落地)

```c
// 1) 启动 I2C(EXT 总线)
i2c_master_bus_handle_t i2c_bus;
i2c_master_bus_config_t i2c_cfg = {
    .i2c_port = I2C_NUM_0,
    .sda_io_num = GPIO_NUM_38,
    .scl_io_num = GPIO_NUM_39,
    .clk_source = I2C_CLK_SRC_DEFAULT,
    .glitch_ignore_cnt = 7,
    .flags.enable_internal_pullup = false,  // EchoBase 已有 4.7K 外部上拉
};
i2c_new_master_bus(&i2c_cfg, &i2c_bus);

// 2) PI4IOE5V6408 init,P0 = 0(强制静音,屏蔽 codec 初始化时的瞬态)
pi4ioe_write(0x07, 0x00);   // 全部 push-pull
pi4ioe_write(0x0D, 0xFF);   // 全部内部上拉
pi4ioe_write(0x03, 0x6F);   // P0/1/2/3/5/6=output
pi4ioe_write(0x05, 0x00);   // P0=0,PA mute

// 3) I2S 通道分配(全双工)
i2s_chan_handle_t tx_ch, rx_ch;
i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
i2s_new_channel(&chan_cfg, &tx_ch, &rx_ch);

i2s_std_config_t std_cfg = {
    .clk_cfg  = I2S_STD_CLK_DEFAULT_CONFIG(16000),  // 16 kHz(方案 A)
    .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT,
                                                     I2S_SLOT_MODE_STEREO),
    .gpio_cfg = {
        .mclk = I2S_GPIO_UNUSED,
        .bclk = GPIO_NUM_8,
        .ws   = GPIO_NUM_6,
        .dout = GPIO_NUM_5,
        .din  = GPIO_NUM_7,
    },
};
i2s_channel_init_std_mode(tx_ch, &std_cfg);
i2s_channel_init_std_mode(rx_ch, &std_cfg);

// 4) esp_codec_dev 初始化 ES8311
audio_codec_i2s_cfg_t i2s_codec_cfg = {
    .tx_handle = tx_ch, .rx_handle = rx_ch,
};
const audio_codec_data_if_t *data_if = audio_codec_new_i2s_data(&i2s_codec_cfg);
audio_codec_i2c_cfg_t i2c_codec_cfg = {
    .addr = 0x18, .bus_handle = i2c_bus,
};
const audio_codec_ctrl_if_t *ctrl_if = audio_codec_new_i2c_ctrl(&i2c_codec_cfg);

es8311_codec_cfg_t es8311_cfg = {
    .codec_mode = ESP_CODEC_DEV_WORK_MODE_BOTH,
    .ctrl_if    = ctrl_if,
    .gpio_if    = audio_codec_new_gpio(),
    .pa_pin     = -1,        // PA 不归 esp_codec_dev 管,我们走 PI4IOE
    .use_mclk   = false,     // ★ 关键:用 SCLK 派生主时钟
    .hw_gain    = { .pa_voltage = 3.3, .codec_dac_voltage = 3.3 },
};
const audio_codec_if_t *codec_if = es8311_codec_new(&es8311_cfg);

esp_codec_dev_cfg_t dev_cfg = {
    .codec_if = codec_if, .data_if = data_if,
    .dev_type = ESP_CODEC_DEV_TYPE_IN_OUT,
};
esp_codec_dev_handle_t codec = esp_codec_dev_new(&dev_cfg);

esp_codec_dev_sample_info_t fs = {
    .sample_rate = 16000, .channel = 1,
    .bits_per_sample = 16, .channel_mask = 1,
};
esp_codec_dev_open(codec, &fs);
esp_codec_dev_set_out_vol(codec, 60.0);     // 0~100
esp_codec_dev_set_in_gain(codec, 30.0);     // dB

// 5) 启动 I2S
i2s_channel_enable(tx_ch);
i2s_channel_enable(rx_ch);

// 6) Unmute(此时 codec 已稳定,DMA 在跑零数据,无 pop)
pi4ioe_write(0x05, 0xFF);   // P0=1,PA enable
```

---

## 11. PSRAM 与内存预算(ESP-IDF + WakeNet + WS 客户端)

| 模块 | 估算占用 | 备注 |
|---|---|---|
| WakeNet9 "你好小智" 模型 | ~700 KB | mmap 到 model 分区 |
| ESP-SR AFE/MultiNet 运行时 | ~200 KB SRAM + 1.5 MB PSRAM | 单 wake word,不开 MultiNet 命令词 |
| 音频环形缓冲(上行 16k×16bit×1ch×1 s) | 32 KB | 1 s 滚动窗 |
| 音频环形缓冲(下行 16k×16bit×1ch×3 s) | 96 KB | 抗 Wi-Fi 抖动 |
| Wi-Fi/TCP/TLS 栈 | ~80 KB SRAM | |
| WebSocket 客户端缓冲 | ~16 KB | |
| FreeRTOS + 应用任务栈 | ~40 KB | |

**8 MB PSRAM + 512 KB SRAM 富余很多**,不会成为瓶颈。

---

## 12. 关键风险点 / 注意事项

| 风险 | 影响 | 应对 |
|---|---|---|
| MCLK 没接,只能用 BCLK 派生 | 漏掉 `use_mclk=false` 会导致 codec 完全没声 | 已在示例代码里标★ |
| NS4150 上电默认 enable | 上电瞬间 codec 噪声会被放大成 pop | 启动顺序里**先把 P0 拉低再 init codec** |
| LCD 驱动 IC 已变更为 ST7735 | 若用旧资料按 GC9107 配 LVGL 会黑屏 | 第一期不用 LCD;第二阶段写 BSP 时按 ST7735 |
| BMM150 通过 BMI270 sensor hub 访问 | 直接 I2C 扫地址扫不到 BMM150 | 必须用 Bosch 官方 driver 的 aux I2C 模式 |
| BMI270/LP5562 在 SYS I2C(G0/G45),与 EchoBase 不共线 | 不能用同一个 i2c_master_bus 实例 | 第一期不用;第二阶段 BSP 建两个 bus handle |
| AtomS3R 用户按键 G41 上电状态 | 长按 G41 + reset 进下载模式;运行中按键检测低电平 | 仅作业务按键时正常用 INPUT_PULLUP + 下降沿中断 |
| Port.A G1/G2 是 ADC 通道 | 第二阶段如果接 Grove 模块要避开 ADC2(WiFi 启用时不可用) | G1=ADC0/ADC1_CH0,G2=ADC0/ADC1_CH1,都在 ADC1,安全 |
| Wi-Fi 与 G39 的 CLK_OUT3 复用 | G39 当 SCL 用没问题(只是 GPIO),不会冲突 | — |

---

## 13. 必须用户最终拍板的事项

1. **采样率方案**:推荐方案 A(全程 16 kHz,桥端重采样)。是否同意?
2. **第一期是否用 AtomS3R 板载 LCD/LED 做状态指示**?
   - 若用 → 要加 SYS I2C 初始化(LP5562 控 LED)/ SPI(ST7735 屏)
   - 若不用 → 第一期完全不碰 SYS I2C,固件更小,聚焦音频链
3. **第一期是否保留 G41 按键作 PTT/wake 备用入口**?(强烈建议保留:wake word 调不出来时还能用按键)
4. **EchoBase 上的 P1~P7、INT 都没用**,Port.A 第一期也不接。我把这些都列为"reserved",未来扩展时再启用。同意吗?

---

## 14. 已交叉验证的资料源

- `Sch_ECHO Base_v1.0.pdf`(M5Stack OSS,本地副本:`~/Local/my-proj-temp/gpt-assistant/hw-research/echobase_sch_v1.0.pdf`)
- `AtomS3R.pdf` datasheet/pinmap(M5Stack OSS,本地副本:同目录 `atoms3r_datasheet.pdf`)
- `github.com/m5stack/M5Atomic-EchoBase`(MIT,本地 clone:同目录)
- ES8311 datasheet(everest-semi 官方 + waveshare 上的 user guide)
- PI4IOE5V6408 datasheet(Diodes Inc. DS40583 Rev 1-2)
- Espressif `esp_codec_dev` v1.5.10 component README
