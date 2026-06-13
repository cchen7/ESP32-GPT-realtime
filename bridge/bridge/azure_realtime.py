"""Azure OpenAI gpt-realtime-2 protocol client.

Encapsulates the GA Realtime WebSocket session: AAD bearer-token auth,
``session.update`` configuration, sending PCM16 audio, receiving model audio +
transcripts, and dispatching function-tool calls.

**No audio capture/playback** — that's the caller's responsibility. The client
talks PCM16 mono with Azure; input and output rates are configurable per session
(defaults: input 16 kHz to match the device, output 24 kHz for best model audio).
The bridge resamples the 24 kHz output down to the device's 16 kHz on its own leg.

Tool calls are dispatched via :mod:`bridge.tools.registry` — register your
tools before calling :meth:`connect`.
"""
import asyncio
import base64
import json
import sys
from typing import Awaitable, Callable

import websockets
from azure.identity import DefaultAzureCredential

from bridge import config, persona
from bridge.tools import registry as tool_registry


AssistantAudioCb = Callable[[bytes], Awaitable[None]]
SimpleCb = Callable[[], Awaitable[None]]
TextCb = Callable[[str], Awaitable[None]]
ErrorCb = Callable[[dict], Awaitable[None]]


class RealtimeClient:
    """One Azure Realtime session. Not thread-safe — drive from one event loop."""

    def __init__(
        self,
        on_assistant_audio: AssistantAudioCb,
        on_user_speech_started: SimpleCb | None = None,
        on_user_transcript: TextCb | None = None,
        on_assistant_transcript: TextCb | None = None,
        on_error: ErrorCb | None = None,
        input_rate: int = config.DEVICE_SAMPLE_RATE,
        output_rate: int = config.AZURE_SAMPLE_RATE,
    ):
        self._cred = DefaultAzureCredential()
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._on_assistant_audio = on_assistant_audio
        self._on_user_speech_started = on_user_speech_started
        self._on_user_transcript = on_user_transcript
        self._on_assistant_transcript = on_assistant_transcript
        self._on_error = on_error
        self._input_rate = input_rate
        self._output_rate = output_rate
        self._closed = False

    def _token(self) -> str:
        return self._cred.get_token(config.TOKEN_SCOPE).token

    async def connect(self) -> None:
        url = config.realtime_url()
        headers = {"Authorization": f"Bearer {self._token()}"}
        self._ws = await websockets.connect(url, additional_headers=headers, max_size=None)
        created = json.loads(await self._ws.recv())
        assert created.get("type") == "session.created", created
        print(f"[realtime] session ready: {created['session'].get('model')}")
        await self._configure_session()

    async def _configure_session(self) -> None:
        tools = tool_registry.all_schemas()
        if config.ENABLE_WEB_SEARCH and any(t.get("name") == "web_search" for t in tools):
            instructions = persona.instructions_with_web_search()
        else:
            instructions = persona.base_instructions()

        session: dict = {
            "type": "realtime",
            "instructions": instructions,
            "output_modalities": ["audio"],
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": self._input_rate},
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 400,
                        "create_response": True,
                        "interrupt_response": True,
                    },
                    "transcription": {"model": "whisper-1"},
                },
                "output": {
                    "format": {"type": "audio/pcm", "rate": self._output_rate},
                    "voice": config.VOICE,
                },
            },
        }
        if tools:
            session["tools"] = tools
            session["tool_choice"] = "auto"

        await self._ws.send(json.dumps({"type": "session.update", "session": session}))

    async def send_input_audio(self, pcm: bytes) -> None:
        """Append PCM16 mono audio to the input buffer.

        ``pcm`` rate must match the ``input_rate`` configured at construction.
        """
        if self._closed or self._ws is None or not pcm:
            return
        await self._ws.send(json.dumps({
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(pcm).decode("ascii"),
        }))

    async def run(self) -> None:
        """Receive loop. Returns when the WS closes."""
        if self._ws is None:
            raise RuntimeError("connect() first")
        try:
            async for raw in self._ws:
                evt = json.loads(raw)
                await self._handle(evt)
        except websockets.ConnectionClosed:
            pass

    async def _handle(self, evt: dict) -> None:
        t = evt.get("type", "")

        if t == "response.output_audio.delta":
            pcm = base64.b64decode(evt["delta"])
            await self._on_assistant_audio(pcm)

        elif t == "input_audio_buffer.speech_started":
            if self._on_user_speech_started:
                await self._on_user_speech_started()

        elif t == "conversation.item.input_audio_transcription.completed":
            if self._on_user_transcript:
                await self._on_user_transcript(evt.get("transcript", "").strip())

        elif t == "response.output_audio_transcript.done":
            if self._on_assistant_transcript:
                await self._on_assistant_transcript(evt.get("transcript", "").strip())

        elif t == "response.function_call_arguments.done":
            # Run tool off the recv loop so audio keeps flowing during the call.
            asyncio.create_task(self._run_tool_call(evt))

        elif t == "error":
            err = evt.get("error", evt)
            if self._on_error:
                await self._on_error(err)
            else:
                print(f"[realtime error] {json.dumps(err)}", file=sys.stderr)

    async def _run_tool_call(self, evt: dict) -> None:
        try:
            await self._dispatch_tool_call(evt)
        except Exception as exc:  # noqa: BLE001 - background task; surface, don't drop
            print(f"[tool error] {exc}", file=sys.stderr)

    async def _dispatch_tool_call(self, evt: dict) -> None:
        name = evt.get("name")
        call_id = evt.get("call_id")
        try:
            args = json.loads(evt.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}

        tool = tool_registry.get(name) if name else None
        if tool is None:
            output_obj: dict = {"error": f"unknown tool {name}"}
        else:
            output_obj = await tool.handler(args)

        await self._ws.send(json.dumps({
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(output_obj, ensure_ascii=False),
            },
        }))
        # Nudge the model to speak the grounded answer directly.
        await self._ws.send(json.dumps({
            "type": "response.create",
            "response": {
                "instructions": (
                    "Answer the user's question now, directly and concisely, using "
                    "the tool result. Do NOT say you will check or look it up — "
                    "you already have the information."
                ),
            },
        }))

    async def close(self) -> None:
        self._closed = True
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
