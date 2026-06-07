from __future__ import annotations

SLASH_COMMANDS = [
    "/help",
    "/status",
    "/tools",
    "/sessions",
    "/inspect",
    "/clear",
    "/model",
    "/approval",
    "/config",
    "/exit",
    "/quit",
]


def make_slash_completer():
    try:
        from prompt_toolkit.completion import WordCompleter
    except ModuleNotFoundError:
        return None
    return WordCompleter(SLASH_COMMANDS, ignore_case=True)
