"""Web search grounding via Azure Foundry "Grounding with Bing Search".

Two surfaces:
- :func:`search` — sync function that hits the Foundry Responses API with the
  ``bing_grounding`` tool. Copied verbatim from ``gpt-realtime2-demo/grounding.py``
  (only the config import path changed). Never raises.
- :data:`SCHEMA` / :func:`handler` / :func:`register` — wraps :func:`search` as
  an async Tool that can be registered into ``bridge.tools.registry`` so the
  Realtime model can call it via ``web_search(query)``.
"""
import asyncio

from azure.identity import DefaultAzureCredential
from openai import OpenAI

from bridge import config
from bridge.tools import registry as tool_registry

# EnvironmentCredential (service principal via AZURE_* env vars) when set,
# otherwise falls back to az login / managed identity. Portable across machines.
_credential = DefaultAzureCredential()


def _client() -> OpenAI:
    # Fresh bearer token per call (SDK caches/refreshes underneath).
    token = _credential.get_token(config.AI_TOKEN_SCOPE).token
    return OpenAI(
        base_url=f"{config.PROJECT_ENDPOINT}/openai/v1/",
        api_key=token,
    )


def search(query: str) -> dict:
    """Run a grounded web search.

    Returns ``{"answer": str, "sources": [{"title": str, "url": str}]}``.
    Never raises — on failure it returns an ``answer`` describing the error so
    the voice model can react gracefully.
    """
    try:
        resp = _client().responses.create(
            model=config.GROUNDING_DEPLOYMENT,
            input=query,
            instructions=(
                "Search the web and answer concisely. Always cite your sources "
                "inline so citations are produced."
            ),
            tool_choice="required",
            tools=[{
                "type": "bing_grounding",
                "bing_grounding": {
                    "search_configurations": [{
                        "project_connection_id": config.BING_CONNECTION_ID,
                        "count": config.BING_COUNT,
                        "market": config.BING_MARKET,
                        "freshness": config.BING_FRESHNESS,
                    }],
                },
            }],
        )
    except Exception as exc:  # noqa: BLE001 - surface as data, not a crash
        return {"answer": f"web search failed: {exc}", "sources": []}

    sources = []
    for item in resp.output:
        if getattr(item, "type", None) != "message":
            continue
        for part in item.content:
            for ann in (getattr(part, "annotations", None) or []):
                if getattr(ann, "type", None) == "url_citation":
                    sources.append({
                        "title": getattr(ann, "title", "") or "",
                        "url": getattr(ann, "url", "") or "",
                    })

    return {"answer": resp.output_text, "sources": sources}


SCHEMA = {
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
            "query": {"type": "string", "description": "A focused search query."},
        },
        "required": ["query"],
    },
}


async def handler(args: dict) -> dict:
    query = args.get("query", "")
    print(f"🔎 Searching: {query}")
    # search() does blocking HTTP — keep it off the event loop.
    result = await asyncio.to_thread(search, query)
    for s in result.get("sources", []):
        print(f"   • {s.get('title')} — {s.get('url')}")
    return result


def register() -> None:
    tool_registry.register(tool_registry.Tool(
        name="web_search",
        schema=SCHEMA,
        handler=handler,
    ))
