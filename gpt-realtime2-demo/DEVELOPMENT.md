# 开发指南 (DEVELOPMENT)

面向在此 demo 基础上继续开发的人。涵盖架构、实时协议要点、代码结构、
扩展方法、Azure 资源拓扑与排错。

---

## 1. 架构总览

```
                ┌─────────────── 你的机器 ───────────────┐
  麦克风 ──PCM16 24k──► realtime_voice_demo.py ──WebSocket──►  gpt-realtime-2
  扬声器 ◄─PCM16 24k──┤  (asyncio + sounddevice)          │   (Azure OpenAI Realtime, GA)
                      │        │ function_call             │
                      │        ▼                           │
                      │   grounding.py ──Responses API──►  <your-project>
                      └───────────────────────────────────┘   (bing_grounding → bing1)
```

- **realtime_voice_demo.py**：音频采集/播放 + Realtime WebSocket 收发 + 工具调用编排。
- **grounding.py**：把一次 web 搜索封装成 `search(query) -> {answer, sources}`，
  内部走 Foundry Responses API 的 `bing_grounding` 工具。
- **config.py**：所有可配置项 + `.env` 加载 + URL 构造。

全程 **AAD token** 认证，无 API key（见 SETUP.md）。

---

## 2. Azure 资源拓扑

| 角色 | 资源 | 标识 |
|---|---|---|
| Realtime 模型 | `<your-resource>` (AIServices, eastus2) | 部署名 `gpt-realtime-2`（模型 `gpt-realtime-2-2026-05-06`） |
| Grounding 文本模型 | 同上 | 部署名 `gpt-4.1-mini` |
| Foundry 项目 | `<your-project>` | Responses 端点见下 |
| Bing grounding | `<your-bing-account>` (Microsoft.Bing/accounts, Bing.Grounding) | 连接 `<your-bing-connection>` |
| 可移植身份 | App `gpt-realtime2-demo-sp` | appId `8a84ac49-19e3-4d71-9509-3e4ccfedfeaa` |
| Azure 机器身份 | openclaw VM 的系统 MI | 已授数据面角色，可无密钥直连 |

- Realtime 端点：`wss://<your-resource>.openai.azure.com/openai/v1/realtime?model=<部署名>`
- Responses 端点：`https://<your-resource>.services.ai.azure.com/api/projects/<your-project>/openai/v1/`
- Token scope：realtime → `cognitiveservices.azure.com/.default`；Responses → `ai.azure.com/.default`

---

## 3. Realtime 协议要点（GA 版，已实测）

### URL / 版本
- **GA 路径**：`/openai/v1/realtime?model=<部署名>` + `Bearer` token。
- 预览版才用 `/openai/realtime?api-version=...&deployment=...`，**混用会 404**。

### 会话配置（`session.update`）
GA schema 与旧 beta 不同——配置嵌套在 `session.audio.input` / `session.audio.output`，
输出模态用 `output_modalities`（不是 `modalities`）：

```jsonc
{
  "type": "session.update",
  "session": {
    "type": "realtime",
    "instructions": "...",
    "output_modalities": ["audio"],          // 或 ["text"]
    "audio": {
      "input":  { "format": {"type":"audio/pcm","rate":24000},
                  "turn_detection": {"type":"server_vad", ...},
                  "transcription": {"model":"whisper-1"} },
      "output": { "format": {"type":"audio/pcm","rate":24000}, "voice":"alloy" }
    },
    "tools": [ /* function tools */ ],
    "tool_choice": "auto"
  }
}
```

### 关键事件（服务端 → 客户端）
| 事件 | 含义 |
|---|---|
| `session.created` / `session.updated` | 会话就绪 / 配置生效 |
| `input_audio_buffer.speech_started` | 用户开始说话（用于 **barge-in**：清空播放缓冲） |
| `conversation.item.input_audio_transcription.completed` | 用户语音转写文本 |
| `response.output_audio.delta` | 助手音频块（base64 PCM16） |
| `response.output_audio_transcript.delta/done` | 助手字幕 |
| `response.function_call_arguments.done` | 工具调用就绪（含 `name` / `call_id` / `arguments`） |
| `response.done` | 一轮响应结束 |
| `error` | 错误 |

### 客户端 → 服务端
- 送麦克风音频：`input_audio_buffer.append`（`audio` = base64 PCM16）。
- 服务端 VAD 默认开启，说完会自动触发回复，无需手动 `commit` / `response.create`。
- 工具回传：`conversation.item.create`（`item.type=function_call_output`，带 `call_id`/`output`）
  之后 `response.create` 让模型朗读结果。

### 音频
24 kHz、单声道、PCM16。`sounddevice` 用 `RawInputStream/RawOutputStream`（直接收发 bytes）。
播放用带锁的字节缓冲，sounddevice 回调在**音频线程**，麦克风回调用
`loop.call_soon_threadsafe` 把数据交回事件循环。

---

## 4. 代码结构

### realtime_voice_demo.py
- `AudioPlayer`：线程安全播放缓冲；`add()` 入队、`clear()` 用于 barge-in。
- `RealtimeVoiceChat`
  - `run()`：连接 → `session.created` → `_configure_session` → 启动音频 → `gather(_send_mic, _receive)`。
  - `_configure_session(ws)`：发 `session.update`；`ENABLE_WEB_SEARCH` 时挂载 `WEB_SEARCH_TOOL`。
  - `_send_mic(ws)`：从 asyncio 队列取麦克风 PCM，`input_audio_buffer.append`。
  - `_receive(ws)` / `_handle(ws, evt)`：事件分发。
  - `_run_tool_call(ws, evt)`：跑工具（`asyncio.to_thread` 调用阻塞的 `grounding.search`），
    回传 `function_call_output` 并 `response.create`。这里附带一句"直接、简洁作答"的
    instructions 让答案更聚焦——非必需（实测不加也能正确作答），仅作锦上添花。
- `WEB_SEARCH_TOOL`：function 工具的 JSON schema。

### grounding.py
- `search(query)`：`OpenAI(base_url=Responses端点, api_key=AAD token).responses.create(...)`，
  `tools=[{type:"bing_grounding", ...}]`，从 `url_citation` 注解抽取来源。**永不抛异常**（失败转成文本）。

### config.py
- `.env` 自动加载（真实环境变量优先）。
- 资源/部署/端点/scope/VAD/Bing 参数，均可用同名环境变量覆盖。

---

## 5. 如何扩展

### 加一个新的 function 工具
1. 在 `realtime_voice_demo.py` 仿照 `WEB_SEARCH_TOOL` 定义工具 schema。
2. `_configure_session` 的 `session["tools"]` 里加上它。
3. 在 `_run_tool_call` 里加一个 `elif name == "your_tool":` 分支，执行后回传 `function_call_output`。
   阻塞型调用记得用 `await asyncio.to_thread(...)`，别卡住事件循环。

### 换音色 / 改 VAD 灵敏度
- 音色：`REALTIME_VOICE=marin python realtime_voice_demo.py`（或改 `config.VOICE`）。
- VAD：调 `_configure_session` 里 `turn_detection` 的 `threshold` / `silence_duration_ms`。

### 换搜索后端（不想用 Bing）
- 只改 `grounding.search` 的实现，返回结构保持 `{"answer","sources"}` 即可，主程序无需改动。

### 锁定转写语言（减少误识别）
- `transcription` 里可指定语言相关参数，或改用更准的转写部署（Azure 要求填**部署名**而非 `whisper-1`）。

---

## 6. 认证与可移植（详见 SETUP.md）

- 代码用 `DefaultAzureCredential`：有 `AZURE_*` 环境变量（SP）就用 SP，否则回退 `az login`，
  在带 MI 的 Azure 机器上自动用 MI。
- 非 Azure 机器：用 `.env` 里的 SP 密钥；密钥本租户最长约 30 天，到期前跑 `./rotate_secret.sh` 续期。
- 带 MI 的机器：无需密钥，直接用 MI（已授数据面角色）。

---

## 7. 排错

| 现象 | 排查 |
|---|---|
| WebSocket 404 | 用了预览版路径或 api-version；GA 必须 `/openai/v1/realtime?model=<部署名>` |
| 401 / 403 | token scope 不对；或身份缺角色（realtime 需 Cognitive Services OpenAI User，grounding 需 Foundry User） |
| grounding 无引用 | 短答案模型可能不附引用；instructions 里要求"cite sources inline" |
| 模型先说"我查一下"再给答案 | 正常现象：响应①是搜索时的垫场话(语音场景有用)，响应②才是真答案。事件循环要持续处理、勿在响应① `response.done` 处 break(否则会误抓到垫场话) |
| 退出时 `PaMacCore Error -50` | macOS 关闭音频流的无害告警，不影响功能 |
| 麦克风无声 | macOS 需授予终端麦克风权限；确认输入设备 24k 兼容 |

---

## 8. 本地依赖

`brew install portaudio` + `pip install -r requirements.txt`
（`websockets` / `sounddevice` / `azure-identity` / `openai`）。Python 3.12+。
