"""Real-time voice chat demo for Azure OpenAI gpt-realtime-2.

Microphone in -> gpt-realtime-2 -> speaker out, using:
  * Microsoft Entra ID (AAD) bearer-token auth (this resource disables API keys)
  * Server-side voice activity detection (VAD) for natural turn-taking
  * Barge-in: speaking over the assistant interrupts its current reply

Run:
    python realtime_voice_demo.py

Press Ctrl+C to quit.
"""
import asyncio
import base64
import json
import signal
import sys
import threading

import sounddevice as sd
import websockets
from azure.identity import DefaultAzureCredential

import config
import grounding


WEB_SEARCH_TOOL = {
    "type": "function",
    "name": "web_search",
    "description": (
        "Search the web for fresh, factual, or time-sensitive information "
        "(news, weather, prices, recent events). Returns a grounded summary "
        "with sources."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "A focused search query.",
            }
        },
        "required": ["query"],
    },
}


class AudioPlayer:
    """Thread-safe PCM16 playback buffer drained by a sounddevice OutputStream."""

    def __init__(self, sample_rate: int, channels: int):
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._stream = sd.RawOutputStream(
            samplerate=sample_rate,
            channels=channels,
            dtype="int16",
            callback=self._callback,
        )

    def start(self):
        self._stream.start()

    def stop(self):
        self._stream.stop()
        self._stream.close()

    def add(self, pcm: bytes):
        with self._lock:
            self._buf.extend(pcm)

    def clear(self):
        """Drop queued audio (used for barge-in)."""
        with self._lock:
            self._buf.clear()

    def pending(self) -> int:
        with self._lock:
            return len(self._buf)

    def _callback(self, outdata, frames, time_info, status):
        needed = frames * 2  # int16 mono = 2 bytes/frame
        with self._lock:
            take = min(needed, len(self._buf))
            chunk = bytes(self._buf[:take])
            del self._buf[:take]
        if take < needed:
            chunk += b"\x00" * (needed - take)  # underrun -> silence
        outdata[:] = chunk


class RealtimeVoiceChat:
    def __init__(self):
        self._cred = DefaultAzureCredential()
        self._loop = asyncio.get_running_loop()
        self._mic_q: asyncio.Queue[bytes] = asyncio.Queue()
        self._player = AudioPlayer(config.SAMPLE_RATE, config.CHANNELS)
        self._mic_stream: sd.RawInputStream | None = None
        self._closing = False

    def _token(self) -> str:
        return self._cred.get_token(config.TOKEN_SCOPE).token

    # ---- microphone ----
    def _mic_callback(self, indata, frames, time_info, status):
        if status:
            print(f"[mic] {status}", file=sys.stderr)
        # Hand the raw PCM bytes to the asyncio loop thread-safely.
        self._loop.call_soon_threadsafe(self._mic_q.put_nowait, bytes(indata))

    def _start_mic(self):
        self._mic_stream = sd.RawInputStream(
            samplerate=config.SAMPLE_RATE,
            channels=config.CHANNELS,
            dtype="int16",
            blocksize=config.BLOCK_SIZE,
            callback=self._mic_callback,
        )
        self._mic_stream.start()

    def _stop_audio(self):
        if self._mic_stream is not None:
            self._mic_stream.stop()
            self._mic_stream.close()
        self._player.stop()

    # ---- websocket session ----
    async def run(self):
        url = config.realtime_url()
        headers = {"Authorization": f"Bearer {self._token()}"}
        print(f"Connecting to {url} ...")
        async with websockets.connect(url, additional_headers=headers, max_size=None) as ws:
            created = json.loads(await ws.recv())
            assert created.get("type") == "session.created", created
            print(f"Session ready: {created['session'].get('model')}")
            await self._configure_session(ws)

            self._player.start()
            self._start_mic()
            print("\n🎙️  Speak now — the assistant replies automatically. Ctrl+C to quit.\n")

            await asyncio.gather(
                self._send_mic(ws),
                self._receive(ws),
            )

    async def _configure_session(self, ws):
        instructions = config.INSTRUCTIONS
        session = {
            "type": "realtime",
            "instructions": instructions,
            "output_modalities": ["audio"],
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": config.SAMPLE_RATE},
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
                    "format": {"type": "audio/pcm", "rate": config.SAMPLE_RATE},
                    "voice": config.VOICE,
                },
            },
        }
        if config.ENABLE_WEB_SEARCH:
            session["instructions"] = (
                instructions
                + " When the user asks about current events, weather, prices, or "
                "anything you may not know or that could be outdated, call the "
                "web_search tool. Before calling it, say a brief filler such as "
                "'让我查一下' so the user isn't left in silence."
            )
            session["tools"] = [WEB_SEARCH_TOOL]
            session["tool_choice"] = "auto"
        await ws.send(json.dumps({"type": "session.update", "session": session}))

    async def _send_mic(self, ws):
        try:
            while not self._closing:
                pcm = await self._mic_q.get()
                await ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(pcm).decode("ascii"),
                }))
        except (asyncio.CancelledError, websockets.ConnectionClosed):
            pass

    async def _receive(self, ws):
        try:
            async for raw in ws:
                evt = json.loads(raw)
                await self._handle(ws, evt)
        except websockets.ConnectionClosed:
            pass

    async def _handle(self, ws, evt: dict):
        t = evt.get("type", "")

        if t == "response.output_audio.delta":
            self._player.add(base64.b64decode(evt["delta"]))

        elif t == "input_audio_buffer.speech_started":
            # User started talking -> barge-in: drop any queued assistant audio.
            self._player.clear()
            print("\n[listening...]", flush=True)

        elif t == "conversation.item.input_audio_transcription.completed":
            print(f"🧑 You: {evt.get('transcript', '').strip()}")

        elif t == "response.output_audio_transcript.done":
            print(f"🤖 Assistant: {evt.get('transcript', '').strip()}\n")

        elif t == "response.function_call_arguments.done":
            # Model requested a tool call; run it without blocking the recv loop.
            asyncio.create_task(self._run_tool_call(ws, evt))

        elif t == "error":
            print(f"[error] {json.dumps(evt.get('error', evt))}", file=sys.stderr)

    async def _run_tool_call(self, ws, evt: dict):
        try:
            await self._dispatch_tool_call(ws, evt)
        except Exception as exc:  # noqa: BLE001 - background task; surface, don't drop
            print(f"[tool error] {exc}", file=sys.stderr)

    async def _dispatch_tool_call(self, ws, evt: dict):
        name = evt.get("name")
        call_id = evt.get("call_id")
        try:
            args = json.loads(evt.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}

        if name == "web_search":
            query = args.get("query", "")
            print(f"🔎 Searching: {query}")
            # grounding.search is blocking (HTTP) -> run off the event loop.
            result = await asyncio.to_thread(grounding.search, query)
            for s in result.get("sources", []):
                print(f"   • {s['title']} — {s['url']}")
            output = json.dumps(result, ensure_ascii=False)
        else:
            output = json.dumps({"error": f"unknown tool {name}"})

        await ws.send(json.dumps({
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": output,
            },
        }))
        # Trigger the model to speak its grounded answer. The instructions below
        # are OPTIONAL — the model already answers correctly without them (verified);
        # they only nudge it to be more concise and on-task.
        await ws.send(json.dumps({
            "type": "response.create",
            "response": {
                "instructions": (
                    "Answer the user's question now, directly and concisely, using "
                    "the web_search result. Do NOT say you will check or look it up "
                    "— you already have the information."
                ),
            },
        }))

    async def shutdown(self):
        self._closing = True
        self._stop_audio()


async def main():
    chat = RealtimeVoiceChat()
    stop = asyncio.Event()

    def _ask_stop(*_):
        stop.set()

    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(s, _ask_stop)
        except NotImplementedError:
            pass

    runner = asyncio.create_task(chat.run())
    stopper = asyncio.create_task(stop.wait())
    done, pending = await asyncio.wait(
        {runner, stopper}, return_when=asyncio.FIRST_COMPLETED
    )
    await chat.shutdown()
    for task in pending:
        task.cancel()
    if runner in done and runner.exception():
        raise runner.exception()
    print("\nBye 👋")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBye 👋")
