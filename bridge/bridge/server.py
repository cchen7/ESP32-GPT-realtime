"""gpt-assistant bridge entry point.

Run with: ``python -m bridge.server``.
"""
import asyncio
import signal
import sys

from bridge import device_ws_server
from bridge.tools import web_search


def _register_tools() -> None:
    web_search.register()


async def amain() -> None:
    _register_tools()
    stop = asyncio.Event()

    def _ask_stop(*_):
        stop.set()

    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(s, _ask_stop)
        except NotImplementedError:
            pass

    serve_task = asyncio.create_task(device_ws_server.serve())
    stop_task = asyncio.create_task(stop.wait())
    done, pending = await asyncio.wait(
        {serve_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass


def main() -> None:
    # Line-buffer stdout so systemd journal / `tail -f` log files see entries
    # as they happen, not at process exit.
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except AttributeError:
        pass
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
