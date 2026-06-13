# 运行与认证

本项目通过 **Microsoft Entra ID (AAD)** 认证，**没有 API key**
（realtime 资源已禁用本地密钥）。代码用 `DefaultAzureCredential`，支持两种模式：

## A. 可移植模式（推荐用于其他机器 / 容器 / CI）

使用 **Service Principal（应用注册）+ 客户端密钥**，靠环境变量认证，无需交互登录。

1. 准备 `.env`（从 `.env.example` 复制并填入）：
       AZURE_TENANT_ID=<tenant-guid>
       AZURE_CLIENT_ID=<app-client-id>
       AZURE_CLIENT_SECRET=<client-secret>
   `config.py` 启动时会自动加载 `.env`，`DefaultAzureCredential` 优先用这些变量。
   也可以直接 `export` 这三个变量，效果相同。

2. 该 SP 已被授予以下角色（scope = <your-resource>）：
   - Cognitive Services OpenAI User  （realtime 语音数据面）
   - Cognitive Services User          （数据面通用）
   - Foundry User                     （Responses API / Bing grounding）

> ⚠️ 客户端密钥有有效期（本租户策略最长约 30 天）。过期前运行 `./rotate_secret.sh`
> （需以应用 owner 身份 `az login`）即可自动重置密钥并更新 `.env`；或手动执行
> `az ad app credential reset --id <appId> --end-date <≤30天后>` 后更新 `.env`。

## B. 本地开发模式

不设置上述环境变量时，`DefaultAzureCredential` 自动回退到 Azure CLI 登录：

    az login
    az account set --subscription <your-subscription-id>

## 安装依赖并运行

    brew install portaudio                 # 系统依赖（macOS）
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    python realtime_voice_demo.py

详细功能见 README.md。
