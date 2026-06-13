# 自定义 gpt-realtime-2 的语言 / 语气 / 个性

本文说明如何控制 `gpt-realtime-2` 语音的**语言、口音、语气、个性、语速、音色**。
所有结论均在部署 `gpt-realtime-2`（模型 `gpt-realtime-2-2026-05-06`）上**实测验证**。

配套可复制的配置片段见同目录 `persona_samples.py`。

---

## TL;DR — 三个控制点

| 想改什么 | 怎么改 | 字段 |
|---|---|---|
| 个性 / 语气 / 语言 / 口音 / 情绪 / 发音 | 写进系统提示词（**主控**） | `session.instructions` |
| 音色（10 选 1） | 选内置语音 | `session.audio.output.voice` |
| 语速（播放快慢 0.25–1.5） | 设倍率 | `session.audio.output.speed` |

> 这三者都在初始 `session.update` 里设置。本文所有片段都是 `session.update` 的 `session` 对象。

---

## 1. instructions —— 语气 / 个性 / 语言的主控

`instructions`（系统提示词）是控制说话风格的**唯一也是最强**的手段。可控：
个性、语气、**语言、口音**、情绪、语速措辞、品牌词发音、回答长度等。
模型不保证 100% 遵守，但 gpt-realtime-2 的遵从度明显强于早期 preview 模型。

### 推荐的提示词结构（OpenAI Realtime 提示词指南）
按需分节，不必全用：

```
# Role & Objective       角色与目标
# Personality & Tone      个性与语气
# Language                语言 / 口音规则
# Pacing                  语速 / 节奏
# Reference Pronunciations 专有名词发音
# Variety                 防止重复、避免机械感
# Tools                   工具调用规则
```

### 实测有效的例子
- **个性**：`你是个开朗的海盗船长` → 实测输出 `"Arrr, the skies be changin' with fickle winds..."`
- **语言锁定**：`只说中文，即使用户说英语也用中文回答`
- **口音**：`Speak English with a light Australian accent. Keep it stable, don't exaggerate.`
- **情绪切换**：`开头很开心，中途转悲伤，结尾变愤怒`（gpt-realtime 系列能逐段切换）
- **发音**：`把 "SQL" 读作 "sequel"，把 "PostgreSQL" 读作 "post-gress"`

具体片段见 `persona_samples.py` 的 `PERSONA_*`。

---

## 2. voice —— 内置音色（实测确认列表）

10 个内置音色（gpt-realtime-2 实测报错信息确认）：

```
alloy, ash, ballad, coral, echo, sage, shimmer, verse, marin, cedar
```

- **推荐 `marin` / `cedar`** —— gpt-realtime 系列的新音色，质量最好。
- 设置位置：`session.audio.output.voice`。
- ⚠️ **一旦本会话发出过音频，就不能再换音色**；要换需新建会话。
- 传入非法音色会被拒绝（实测返回上面这 10 个为 supported values）。

---

## 3. speed —— 语速（播放倍率）

- 字段：`session.audio.output.speed`
- **实测范围 0.25 – 1.5**（默认 1.0；传 2.0 报错 `decimal above maximum value`）。
- 可在会话中途修改，但**只能在两轮之间**，不能在一段回复进行中改。
- 注意：这是**播放快放/慢放**（后处理），不是"说话风格"。想要自然变速，
  额外在 `instructions` 里写 `Pacing` 规则（见 sample）。

---

## 4. ⚠️ 重要：不要用 temperature

很多旧文档 / preview SDK 说顶层 `temperature` 可用，但**本 GA 部署 `gpt-realtime-2`
直接拒绝**：

```
error invalid_request_error / unknown_parameter:
"Unknown parameter: 'session.temperature'."
```

→ **不要在 session 里放 temperature**，否则整个 `session.update` 失败。
表现力调节请改用 `instructions`（语气描述）。

---

## 5. 做不到的（原生 realtime 的边界）

| 限制 | 说明 / 替代 |
|---|---|
| 克隆 / 自定义品牌音色 | 原生 realtime 不支持，只有上面 10 个内置音色 |
| 会话中途换音色 | 发出音频后冻结，需新建会话 |
| SSML `<prosody>` 等精细韵律 | 无；用 `speed` + `instructions` 的 Pacing 规则替代 |
| 自定义神经语音 / 600+ Azure 语音 / 个人语音克隆 | 需改用 **Azure Voice Live API**（`/voice-live/realtime`），见下 |
| 违反内容安全的 persona | 被拦截 |

### 想要自定义音色 → Azure Voice Live API
若必须用**自有品牌音色 / Azure 神经语音 / 语音克隆**，需换端点
`wss://<resource>.services.ai.azure.com/voice-live/realtime?api-version=...&model=gpt-realtime`
（事件格式兼容 OpenAI Realtime）。它额外支持：
`voice.type=azure-custom`（自定义音色）、`azure-personal`（个人语音克隆）、
600+ Azure 神经语音、`voice.rate` 韵律、自定义发音词典、语义 VAD 等。
这是另一套 API，本 demo 用的原生 realtime 端点不支持。

参考：`learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live-how-to-customize`

---

## 6. 怎么用到现有 demo（无需改代码）

本 demo 已支持用环境变量覆盖音色和提示词（见 `config.py`）：

```bash
# 换音色
REALTIME_VOICE=cedar python realtime_voice_demo.py

# 换 persona（系统提示词）
REALTIME_INSTRUCTIONS="$(cat my_persona.txt)" python realtime_voice_demo.py
```

> 注意：现有 demo 暂未暴露 `speed` 的环境变量。要用 `speed`，参考
> `persona_samples.py` 把 `audio.output.speed` 加进 `_configure_session` 的 session 对象即可。

完整可复制片段见 **persona_samples.py**。
