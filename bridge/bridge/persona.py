"""System instructions / persona for the realtime model.

Kept in its own module so we can swap personas without touching the protocol code.
"""
import os


BASE_INSTRUCTIONS = (
    "You are a helpful, friendly voice assistant. Keep replies concise and "
    "conversational. If the user speaks Chinese, reply in Chinese."
)

# Adds web_search nudge when the tool is enabled (mirrors demo behavior).
WEB_SEARCH_INSTRUCTIONS_SUFFIX = (
    " When the user asks about current events, weather, prices, or anything "
    "you may not know or that could be outdated, call the web_search tool. "
    "Before calling it, say a brief filler such as '让我查一下' so the user "
    "isn't left in silence."
)


def base_instructions() -> str:
    return os.environ.get("REALTIME_INSTRUCTIONS", BASE_INSTRUCTIONS)


def instructions_with_web_search() -> str:
    return base_instructions() + WEB_SEARCH_INSTRUCTIONS_SUFFIX
