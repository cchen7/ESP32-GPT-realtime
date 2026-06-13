"""local_test_client — a fake device that pretends to be an AtomS3R+EchoBase.

Runs on Mac (or any host with PortAudio). Captures mic at 16 kHz mono PCM16,
sends frames to the bridge over WebSocket, and plays back whatever audio the
bridge sends. Use this to validate M1 end-to-end without real hardware.

Usage:
    python tools/local_test_client.py                       # ws://127.0.0.1:8765
    python tools/local_test_client.py ws://debian:8765      # remote bridge

Ctrl+C to quit. Speak normally — Azure server-side VAD handles turn taking.
"""
import argparse
import asyncio
import json
import os
import signal
import socket
import sys
import threading

import sounddevice as sd
import websockets


SAMPLE_RATE = 16000      # must match bridge's DEVICE_SAMPLE_RATE
CHANNELS = 1
FRAME_MS = 20
BLOCK_SIZE = SAMPLE_RATE * FRAME_MS // 1000  # 320 samples


class AudioPlayer:
    """Thread-safe PCM16 playback buffer drained by a sounddevice OutputStream."""

    def __init__(self, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS):
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
        with self._lock:
            self._buf.clear()

    def _callback(self, outdata, frames, time_info, status):
        needed = frames * 2  # int16 mono = 2 bytes/frame
        with self._lock:
            take = min(needed, len(self._buf))
            chunk = bytes(self._buf[:take])
            del self._buf[:take]
        if take < needed:
            chunk += b"\x00" * (needed - take)
        outdata[:] = chunk


class FakeDevice:
    def __init__(self, ws_url: str):
        self._ws_url = ws_url
        self._loop = asyncio.get_running_loop()
        self._mic_q: asyncio.Queue[bytes] = asyncio.Queue()
        self._player = AudioPlayer()
        self._mic_stream: sd.RawInputStream | None = None
        self._closing = False

    def _mic_callback(self, indata, frames, time_info, status):
        if status:
            print(f"[mic] {status}", file=sys.stderr)
        self._loop.call_soon_threadsafe(self._mic_q.put_nowait, bytes(indata))

    def _start_mic(self):
        self._mic_stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=BLOCK_SIZE,
            callback=self._mic_callback,
        )
        self._mic_stream.start()

    def _stop_audio(self):
        if self._mic_stream is not None:
            self._mic_stream.stop()
            self._mic_stream.close()
        self._player.stop()

    def _device_id(self) -> str:
        # Stable per-host id so reconnects look like the "same" device.
        return f"mac-{socket.gethostname().split('.')[0]}-{os.getpid() % 10000:04d}"

    async def run(self):
        print(f"Connecting to {self._ws_url} ...")
        async with websockets.connect(self._ws_url, max_size=None) as ws:
            await ws.send(json.dumps({
                "type": "hello",
                "device_id": self._device_id(),
                "fw": "fake-0.1.0",
            }))
            self._player.start()
            self._start_mic()
            print(f"\n🎙️  Speak now. Ctrl+C to quit.\n")
            await asyncio.gather(
                self._send_mic(ws),
                self._recv(ws),
            )

    async def _send_mic(self, ws):
        try:
            while not self._closing:
                pcm = await self._mic_q.get()
                await ws.send(pcm)  # binary frame
        except (asyncio.CancelledError, websockets.ConnectionClosed):
            pass

    async def _recv(self, ws):
        try:
            async for frame in ws:
                if isinstance(frame, bytes):
                    self._player.add(frame)
                else:
                    await self._handle_text(frame)
        except websockets.ConnectionClosed:
            pass

    async def _handle_text(self, raw: str):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            print(f"[bridge] non-json text: {raw[:80]}")
            return
        t = msg.get("type")
        if t == "state":
            print(f"[state] {msg.get('value')}")
        elif t == "transcript":
            role = msg.get("role", "?")
            text = msg.get("text", "")
            icon = "🧑" if role == "user" else "🤖"
            print(f"{icon} {text}")
        elif t == "clear_audio":
            self._player.clear()
            print("[barge-in] cleared playback")
        else:
            print(f"[bridge] {raw[:120]}")

    async def shutdown(self):
        self._closing = True
        self._stop_audio()


async def amain():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "ws_url", nargs="?", default="ws://127.0.0.1:8765",
        help="bridge WebSocket URL (default: ws://127.0.0.1:8765)",
    )
    args = parser.parse_args()

    dev = FakeDevice(args.ws_url)
    stop = asyncio.Event()

    def _ask_stop(*_):
        stop.set()

    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(s, _ask_stop)
        except NotImplementedError:
            pass

    runner = asyncio.create_task(dev.run())
    stopper = asyncio.create_task(stop.wait())
    done, pending = await asyncio.wait(
        {runner, stopper}, return_when=asyncio.FIRST_COMPLETED
    )
    await dev.shutdown()
    for task in pending:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
    if runner in done and runner.exception():
        raise runner.exception()
    print("\nBye 👋")


if __name__ == "__main__":
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass
