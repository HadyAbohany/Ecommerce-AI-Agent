"""
app/agent/memory.py

Simple in-memory conversation history, keyed by session_id. This lets
run_agent() remember earlier turns within the same conversation (e.g.
"how much is it?" after asking about a specific product by name).

DELIBERATELY SIMPLE for this stage: a plain Python dict living in
process memory. This is fine for local testing and even for a single-
process FastAPI app (Step 8), but it will NOT survive a server restart
and will NOT work across multiple server processes/instances. If this
ever needs to survive restarts or scale horizontally, swap this for a
real store (Redis, or a database table) behind the same three
functions below — nothing in core.py should need to change if you do.
"""

from google.genai import types

# session_id -> list[types.Content]
_SESSIONS: dict[str, list] = {}

# Cap how many turns we keep per session, so a very long-running
# conversation doesn't grow the prompt (and cost/latency) unbounded.
# Counts "turns" loosely as entries in the contents list, which
# includes both user messages and model/tool-result turns.
MAX_HISTORY_ENTRIES = 20


def get_history(session_id: str) -> list:
    """Returns the stored conversation history for a session (empty list if new)."""
    return _SESSIONS.get(session_id, [])


def save_history(session_id: str, contents: list) -> None:
    """
    Stores the full updated history for a session, trimming from the
    front if it's grown past MAX_HISTORY_ENTRIES.
    """
    if len(contents) > MAX_HISTORY_ENTRIES:
        contents = contents[-MAX_HISTORY_ENTRIES:]
    _SESSIONS[session_id] = contents


def clear_session(session_id: str) -> None:
    """Forgets a session's history entirely — e.g. for a 'start over' command."""
    _SESSIONS.pop(session_id, None)
