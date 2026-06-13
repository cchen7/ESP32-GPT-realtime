"""Tool registry — maps tool name → schema + async handler.

Designed so adding a new tool (e.g. Home Assistant control) is a single
``registry.register(Tool(...))`` call. The bridge's `RealtimeClient` queries
this registry both to assemble the session's tool list and to dispatch
function-call events from the model.
"""
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

ToolHandler = Callable[[dict], Awaitable[dict]]


@dataclass(frozen=True)
class Tool:
    name: str
    schema: dict          # OpenAI tool/function schema (for session.update)
    handler: ToolHandler  # async fn: args dict → result dict


_TOOLS: dict[str, Tool] = {}


def register(tool: Tool) -> None:
    _TOOLS[tool.name] = tool


def unregister(name: str) -> None:
    _TOOLS.pop(name, None)


def all_schemas() -> list[dict]:
    return [t.schema for t in _TOOLS.values()]


def get(name: str) -> Tool | None:
    return _TOOLS.get(name)


def names() -> list[str]:
    return list(_TOOLS.keys())
