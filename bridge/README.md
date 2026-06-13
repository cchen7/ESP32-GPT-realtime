# gpt-assistant bridge

Local-network bridge between M5Stack voice devices and Azure OpenAI `gpt-realtime-2`.
Keeps Azure credentials off the device, runs the Bing-grounding tool calls, and
resamples Azure 24 kHz audio down to the device's 16 kHz I2S.

## Layout

```
bridge/
├── bridge/                   # package
│   ├── server.py             # asyncio entrypoint
│   ├── config.py             # .env + env-var driven config
│   ├── persona.py            # system instructions
│   ├── audio.py              # 24k ↔ 16k resampling
│   ├── azure_realtime.py     # RealtimeClient (Azure WS protocol)
│   ├── session.py            # DeviceSession (device WS ↔ Azure)
│   ├── device_ws_server.py   # ws://0.0.0.0:8765 listener
│   └── tools/
│       ├── registry.py
│       └── web_search.py     # Bing grounding (Foundry Responses API)
├── tools/local_test_client.py  # Mac sounddevice client to simulate a device
├── deploy/gpt-bridge.service   # systemctl --user unit
└── tests/                      # unit tests
```

## Run locally (Mac)

```bash
cd bridge
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-client.txt -r requirements-dev.txt
cp .env.example .env       # fill in AZURE_* values, OR delete to use az login

# terminal 1: bridge
NO_PROXY=127.0.0.1,localhost python -m bridge.server

# terminal 2: simulated device
NO_PROXY=127.0.0.1,localhost python tools/local_test_client.py ws://127.0.0.1:8765
```

`NO_PROXY` is only needed if your machine routes traffic through a transparent
HTTP proxy (ClashX / Surge / Charles) — otherwise the loopback WS handshake
gets intercepted.

## Deploy on Debian

See `deploy/README.md`.
