"""Configuration for the gpt-realtime-2 voice demo.

Override any value with an environment variable of the same name.
A local ``.env`` file (if present) is loaded automatically.
"""
import os
from pathlib import Path


def _load_dotenv():
    """Minimal .env loader (no external dependency).

    Lines of the form KEY=VALUE are loaded into os.environ unless the key is
    already set in the real environment (real env wins).
    """
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()

# Azure resource (data-plane endpoint host, no scheme). REQUIRED via .env.
ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "")

# Deployment name of the gpt-realtime model.
DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-realtime-2")


# Voice for the model's spoken output.
VOICE = os.environ.get("REALTIME_VOICE", "alloy")

# System instructions / persona.
INSTRUCTIONS = os.environ.get(
    "REALTIME_INSTRUCTIONS",
    "You are a helpful, friendly voice assistant. Keep replies concise and "
    "conversational. If the user speaks Chinese, reply in Chinese.",
)

# Audio: the Realtime API uses 24 kHz mono PCM16.
SAMPLE_RATE = 24000
CHANNELS = 1
# Mic capture block size in samples (~50 ms at 24 kHz).
BLOCK_SIZE = 1200

# Token scope for Microsoft Entra ID authentication.
TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"

# ---- Web search grounding (Grounding with Bing Search via Responses API) ----

# Enable the web_search tool so the model can ground answers on live web results.
ENABLE_WEB_SEARCH = os.environ.get("ENABLE_WEB_SEARCH", "1") != "0"

# Foundry project endpoint that exposes the Responses API. REQUIRED via .env.
PROJECT_ENDPOINT = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")

# A text model deployment that supports the bing_grounding tool.
GROUNDING_DEPLOYMENT = os.environ.get("GROUNDING_DEPLOYMENT", "gpt-4.1-mini")

# Full ARM resource ID of the project's "Grounding with Bing Search" connection.
# REQUIRED via .env.
BING_CONNECTION_ID = os.environ.get("BING_CONNECTION_ID", "")

# Token scope for the Foundry data plane (Responses API).
AI_TOKEN_SCOPE = "https://ai.azure.com/.default"

# Bing search tuning.
BING_MARKET = os.environ.get("BING_MARKET", "zh-CN")
BING_FRESHNESS = os.environ.get("BING_FRESHNESS", "Day")
BING_COUNT = int(os.environ.get("BING_COUNT", "5"))


def realtime_url() -> str:
    """Build the GA Realtime WebSocket URL."""
    if not ENDPOINT:
        raise RuntimeError(
            "AZURE_OPENAI_ENDPOINT is not set. Copy .env.example to .env "
            "and fill in your Azure resource host."
        )
    return f"wss://{ENDPOINT}/openai/v1/realtime?model={DEPLOYMENT}"
