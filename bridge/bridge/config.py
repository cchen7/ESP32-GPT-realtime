"""Configuration for the gpt-assistant bridge.

Override any value with an environment variable of the same name.
A local ``.env`` file in the bridge/ directory (one level up from this package)
is loaded automatically.
"""
import os
from pathlib import Path


def _load_dotenv():
    """Minimal .env loader (no external dependency).

    Real environment variables win over .env values.
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
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

# ---- Bridge ↔ device WebSocket ----

WS_HOST = os.environ.get("BRIDGE_WS_HOST", "0.0.0.0")
WS_PORT = int(os.environ.get("BRIDGE_WS_PORT", "8765"))

# Device-side audio (after bridge resamples Azure 24k → device 16k).
DEVICE_SAMPLE_RATE = int(os.environ.get("DEVICE_SAMPLE_RATE", "16000"))
DEVICE_CHANNELS = 1
DEVICE_FRAME_MS = 20  # 20 ms frames on the device leg

# ---- Azure OpenAI Realtime ----
#
# These all come from the environment / .env. We deliberately keep no
# hardcoded resource names or subscription ids in source so the repo can be
# shared without leaking the deployment topology.

ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-realtime-2")
VOICE = os.environ.get("REALTIME_VOICE", "alloy")

# Azure Realtime native rate; the bridge resamples on the device leg.
AZURE_SAMPLE_RATE = 24000

TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"

# ---- Web search grounding (Foundry Responses API + bing_grounding) ----

ENABLE_WEB_SEARCH = os.environ.get("ENABLE_WEB_SEARCH", "1") != "0"
PROJECT_ENDPOINT = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")
GROUNDING_DEPLOYMENT = os.environ.get("GROUNDING_DEPLOYMENT", "gpt-4.1-mini")
BING_CONNECTION_ID = os.environ.get("BING_CONNECTION_ID", "")
AI_TOKEN_SCOPE = "https://ai.azure.com/.default"
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
