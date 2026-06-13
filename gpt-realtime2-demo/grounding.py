"""Web search grounding via Azure Foundry "Grounding with Bing Search".

Exposes a single function, ``search``, that takes a query string and returns a
grounded answer plus source citations. It calls the Foundry Responses API with
the ``bing_grounding`` tool (backed by the ``bing1`` resource), authenticating
with a Microsoft Entra ID token.

This is the search backend invoked by the realtime voice demo's ``web_search``
function-call handler.
"""
from azure.identity import DefaultAzureCredential
from openai import OpenAI

import config

# Uses EnvironmentCredential (service principal via AZURE_* env vars) when set,
# otherwise falls back to Azure CLI login. Portable across machines.
_credential = DefaultAzureCredential()


def _client() -> OpenAI:
    # Fetch a fresh bearer token per call (the SDK caches/refreshes underneath).
    token = _credential.get_token(config.AI_TOKEN_SCOPE).token
    return OpenAI(
        base_url=f"{config.PROJECT_ENDPOINT}/openai/v1/",
        api_key=token,
    )


def search(query: str) -> dict:
    """Run a grounded web search.

    Returns a dict: ``{"answer": str, "sources": [{"title": str, "url": str}]}``.
    Never raises — on failure it returns an ``answer`` describing the error so the
    voice model can react gracefully.
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
