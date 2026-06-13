"""DeviceSession — glues one device WebSocket to one Azure Realtime session.

Wire protocol (v1, both directions, text + binary frames):

Device → bridge:
- text  `{"type":"hello","device_id":"...","fw":"..."}` — first frame
- text  `{"type":"wake","src":"wakeword|button","ts":...}` — wake signal (informational in M1)
- text  `{"type":"stop"}` — user pressed stop (optional)
- bin   PCM16LE 16 kHz mono, 20 ms / frame (320 samples = 640 bytes typical)

Bridge → device:
- text  `{"type":"state","value":"idle|listening|thinking|speaking|error"}`
- text  `{"type":"transcript","role":"user|assistant","text":"..."}`
- text  `{"type":"clear_audio"}` — barge-in (device should drop playback buffer)
- bin   PCM16LE 16 kHz mono (model audio, already resampled from 24 kHz)
"""
import asyncio
import json
import sys

import websockets

from bridge import audio
from bridge.azure_realtime import RealtimeClient


class DeviceSession:
    """Owns one Azure session and pipes audio + events to/from one device."""

    def __init__(self, device_ws):
        self._device_ws = device_ws
        self._device_id: str = "unknown"
        self._client: RealtimeClient | None = None
        self._closed = False

    async def run(self) -> None:
        try:
            await self._handshake()
            self._client = RealtimeClient(
                on_assistant_audio=self._on_assistant_audio,
                on_user_speech_started=self._on_user_speech_started,
                on_user_transcript=self._on_user_transcript,
                on_assistant_transcript=self._on_assistant_transcript,
                on_error=self._on_error,
            )
            await self._client.connect()
            await self._send_state("idle")
            await asyncio.gather(
                self._device_recv_loop(),
                self._client.run(),
            )
        except websockets.ConnectionClosed:
            print(f"[session {self._device_id}] device closed")
        except Exception as exc:  # noqa: BLE001
            print(f"[session {self._device_id}] error: {exc}", file=sys.stderr)
        finally:
            self._closed = True
            if self._client is not None:
                try:
                    await self._client.close()
                except Exception:  # noqa: BLE001
                    pass

    async def _handshake(self) -> None:
        raw = await self._device_ws.recv()
        if isinstance(raw, bytes):
            raise RuntimeError("expected hello text frame, got binary")
        msg = json.loads(raw)
        if msg.get("type") != "hello":
            raise RuntimeError(f"expected hello, got {msg.get('type')}")
        self._device_id = msg.get("device_id", "unknown")
        fw = msg.get("fw", "?")
        print(f"[session] hello from {self._device_id} (fw {fw})")

    # ---- device → azure ----

    async def _device_recv_loop(self) -> None:
        async for frame in self._device_ws:
            if isinstance(frame, bytes):
                # Device sends PCM16 16k mono — Azure session is configured to
                # accept 16 kHz input, so forward as-is (no resampling).
                if self._client is not None:
                    await self._client.send_input_audio(frame)
            else:
                try:
                    msg = json.loads(frame)
                except json.JSONDecodeError:
                    continue
                await self._handle_device_control(msg)

    async def _handle_device_control(self, msg: dict) -> None:
        t = msg.get("type")
        if t == "wake":
            src = msg.get("src", "?")
            print(f"[{self._device_id}] wake src={src}")
            await self._send_state("listening")
        elif t == "stop":
            print(f"[{self._device_id}] stop")
            await self._send_state("idle")
        elif t == "hello":
            pass  # ignore duplicate hellos
        else:
            print(f"[{self._device_id}] unknown control type={t}")

    # ---- azure → device ----

    async def _on_assistant_audio(self, pcm24k: bytes) -> None:
        pcm16k = audio.down_24k_to_16k(pcm24k)
        await self._send_binary(pcm16k)
        # Mark state on first audio chunk of a response; cheap idempotent send.
        await self._send_state("speaking")

    async def _on_user_speech_started(self) -> None:
        await self._send_text({"type": "clear_audio"})
        await self._send_state("listening")

    async def _on_user_transcript(self, text: str) -> None:
        if not text:
            return
        print(f"[{self._device_id}] 🧑 {text}")
        await self._send_text({"type": "transcript", "role": "user", "text": text})

    async def _on_assistant_transcript(self, text: str) -> None:
        if not text:
            return
        print(f"[{self._device_id}] 🤖 {text}")
        await self._send_text({"type": "transcript", "role": "assistant", "text": text})
        await self._send_state("idle")

    async def _on_error(self, err: dict) -> None:
        print(f"[{self._device_id}] error: {json.dumps(err)}", file=sys.stderr)
        await self._send_state("error")

    # ---- device wire helpers ----

    async def _send_text(self, obj: dict) -> None:
        if self._closed:
            return
        try:
            await self._device_ws.send(json.dumps(obj, ensure_ascii=False))
        except websockets.ConnectionClosed:
            pass

    async def _send_binary(self, b: bytes) -> None:
        if self._closed or not b:
            return
        try:
            await self._device_ws.send(b)
        except websockets.ConnectionClosed:
            pass

    async def _send_state(self, value: str) -> None:
        await self._send_text({"type": "state", "value": value})
