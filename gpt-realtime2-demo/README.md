# gpt-realtime-2 语音对话 Demo

基于 **Azure OpenAI `gpt-realtime-2`** 的实时语音对话:麦克风输入 → 模型 → 扬声器播放。

## 资源信息

| 项目 | 值 |
|---|---|
| 资源 | `<your-resource>` (AIServices, eastus2) |
| 部署名 | `gpt-realtime-2` (model `gpt-realtime-2-2026-05-06`) |
| Realtime 端点 (GA) | `wss://<your-resource>.openai.azure.com/openai/v1/realtime` |
| 认证 | **Microsoft Entra ID (AAD) Bearer Token** — 该资源已禁用 API Key (`disableLocalAuth=true`) |

## 前置条件

- macOS + Python 3.13/3.14
- 系统依赖 portaudio：`brew install portaudio`
- 已登录 Azure CLI 且对该资源有数据面权限：
  ```bash
  az login
  az account set --subscription <your-subscription-id>
  ```

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 运行

```bash
python realtime_voice_demo.py
```

直接对着麦克风说话即可，服务端 VAD 会自动判断你说完并触发回复；说话时打断助手即停止当前播放（barge-in）。按 `Ctrl+C` 退出。

首次运行 macOS 会请求**麦克风权限**，请允许。

## 配置

通过环境变量覆盖 `config.py` 中的默认值：

| 变量 | 说明 | 默认 |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | 资源 host（无 scheme） | `<your-resource>.openai.azure.com` |
| `AZURE_OPENAI_DEPLOYMENT` | 部署名 | `gpt-realtime-2` |
| `REALTIME_VOICE` | 语音音色 | `alloy` |
| `REALTIME_INSTRUCTIONS` | 系统提示词 | 见 `config.py` |

例如换音色：

```bash
REALTIME_VOICE=marin python realtime_voice_demo.py
```

## 实现要点

- **GA 路径**：`/openai/v1/realtime?model=<部署名>`（注意：预览版才用 `/openai/realtime` + `api-version` + `deployment`，混用会 404）。
- **GA 事件 schema**（与旧 beta 不同）：
  - 会话配置嵌套在 `session.audio.input` / `session.audio.output`，输出模态用 `output_modalities`。
  - 模型音频输出事件：`response.output_audio.delta`（base64 PCM16）。
  - 字幕：`response.output_audio_transcript.delta/done`。
  - 用户语音转写：`conversation.item.input_audio_transcription.completed`。
- **音频格式**：24 kHz、单声道、PCM16。
- **认证**：`AzureCliCredential` 获取 `https://cognitiveservices.azure.com/.default` 的 token，作为 `Authorization: Bearer` 头。

## 文件

- `config.py` — 配置与 URL 构造（含 grounding 相关配置）
- `realtime_voice_demo.py` — 主程序（麦克风采集 / WebSocket 收发 / 扬声器播放 / barge-in / web_search 工具）
- `grounding.py` — Grounding with Bing Search 后端（Responses API + bing_grounding）
- `rotate_secret.sh` — 一键轮换 Service Principal 客户端密钥
- `requirements.txt` — 依赖
- `SETUP.md` — 运行与认证（含可移植 SP / 本地 az login 两种模式）
- `DEVELOPMENT.md` — 后续开发指南（架构、实时协议、扩展方法、排错）
- `PERSONA.md` — 自定义语言/语气/个性指南（音色、语速、提示词、限制）
- `persona_samples.py` — persona/voice/language 的 `session.update` 配置片段集（可复制，不执行）

## Web Search Grounding（接入实时联网）

语音 demo 已接入 **Grounding with Bing Search**。当你问及天气、新闻、股价等时效性问题时，gpt-realtime-2 会调用 `web_search` 工具，程序在后台用 Foundry Responses API（`bing_grounding` 工具，走 `<your-bing-account>` 资源）查到带引用的结果再回传，模型据此朗读答案。终端会打印查询词与来源 URL。

```
你说话 → gpt-realtime-2 决定调用 web_search(query)
       → grounding.py 调 Responses API (bing_grounding via bing1)
       → 带引用的答案回传 → gpt-realtime-2 朗读
```

**依赖的 Azure 配置**（已就绪）：

| 项 | 值 |
|---|---|
| Foundry 项目 | `<your-project>` |
| 文本模型部署 | `gpt-4.1-mini`（支持 bing_grounding） |
| Bing.Grounding 资源 | `<your-bing-account>` |
| 项目连接 | `<your-bing-connection>`（GroundingWithBingSearch） |
| Responses 端点 | `https://<your-resource>.services.ai.azure.com/api/projects/<your-project>/openai/v1/` |
| Token scope | `https://ai.azure.com/.default` |

**关闭联网**：`ENABLE_WEB_SEARCH=0 python realtime_voice_demo.py`

⚠️ Grounding with Bing 为**付费**服务，且查询数据会**流出 Azure 合规边界**——请勿在语音里包含敏感信息。

