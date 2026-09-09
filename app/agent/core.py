"""
app/agent/core.py

The function-calling loop: takes one user message (plus any prior
history for its session), lets Gemini decide which tool(s) to call
(if any), executes them via TOOL_FUNCTIONS, feeds the results back,
and returns the final natural-language answer.

Conversation memory (Step 7): run_agent() now accepts a session_id and
uses app/agent/memory.py to load prior turns and save the updated
history afterward — so a follow-up like "how much is it?" can resolve
"it" from what was discussed earlier in the same session. Two separate
session_ids never see each other's history.

NOTE on the model name: hardcoded to a specific version like
"gemini-2.5-flash" is risky right now — Gemini 2.5 models are scheduled
to shut down October 16, 2026. Using the "gemini-flash-latest" alias
instead avoids needing to update this file every time a model is
deprecated.

Two API quirks confirmed by live testing (not obvious from docs alone):
- Function-response Content must use role="user", NOT role="tool".
- The function response payload must be a dict, never a bare list —
  any tool result that's a list gets wrapped as {"results": [...]}.
"""

from google import genai
from google.genai import types
from google.genai import errors as genai_errors
import os
import time
from dotenv import load_dotenv

from app.agent.tools import TOOL_SCHEMAS, TOOL_FUNCTIONS
from app.agent.prompts import (
    POLICY_ASSISTANT_SYSTEM_PROMPT,
    MIN_RELEVANCE_SCORE,
    NO_MATCH_RESPONSE_EN,
)
from app.agent.memory import get_history, save_history

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not found. Check your .env file.")

client = genai.Client(api_key=GEMINI_API_KEY)

MODEL_NAME = "gemini-flash-latest"
MAX_TOOL_ROUNDS = 5  # safety cap against an accidental infinite tool-calling loop
DEFAULT_SESSION_ID = "default"  # used when no session_id is given (e.g. quick CLI tests)

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5  # doubles each retry: 5s, 10s, 20s


def _generate_with_retry(**kwargs):
    """
    Wraps client.models.generate_content with retry-with-backoff for
    two kinds of transient errors:
    - 503 ServerError ("high demand") — almost always succeeds on a
      quick retry a few seconds later.
    - 429 ClientError ("RESOURCE_EXHAUSTED" / quota exceeded) — the
      free tier has a small daily request quota per model. If the API
      tells us how long to wait (retryDelay), we honor that; otherwise
      we fall back to the same backoff schedule as 503s. NOTE: if the
      quota exhausted is a hard daily cap (not a short-term rate limit),
      no amount of waiting within this process will fix it — you'll
      see the same error repeatedly until the daily quota resets or
      billing is enabled for a higher limit.
    """
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            return client.models.generate_content(**kwargs)
        except genai_errors.ServerError as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF_SECONDS * (2 ** attempt)
                print(f"  [Gemini server busy, retrying in {wait}s... ({attempt + 1}/{MAX_RETRIES})]")
                time.sleep(wait)
        except genai_errors.ClientError as e:
            is_quota_error = "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e)
            if not is_quota_error or attempt >= MAX_RETRIES - 1:
                raise
            last_error = e
            wait = RETRY_BACKOFF_SECONDS * (2 ** attempt)
            print(f"  [Gemini quota exceeded, retrying in {wait}s... ({attempt + 1}/{MAX_RETRIES}). "
                  f"If this keeps happening, you've likely hit the daily free-tier request limit — "
                  f"see the error message for the exact quota.]")
            time.sleep(wait)
    raise last_error


def _execute_tool(name: str, args: dict) -> dict:
    """
    Runs the actual Python function behind a tool call, with two pieces
    of normalization needed before the result can be sent back to Gemini:

    1. Gemini's function-response format REQUIRES a dict — any list
       result (search_policy, get_product_info's fuzzy-match path) is
       wrapped as {"results": [...]}.
    2. search_policy results below the relevance threshold are replaced
       with an explicit "no match" message instead of being handed to
       the LLM as if they were a good answer.
    """
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return {"error": f"Unknown tool: {name}"}

    try:
        result = func(**args)
    except Exception as e:
        return {"error": f"Tool '{name}' raised an exception: {e}"}

    if name == "search_policy" and isinstance(result, list):
        good_matches = [r for r in result if r.get("score", 0) >= MIN_RELEVANCE_SCORE]
        if not good_matches:
            return {"no_match": True, "message": NO_MATCH_RESPONSE_EN}
        result = good_matches

    if isinstance(result, list):
        return {"results": result}
    if result is None:
        return {"result": None}

    return result


def run_agent(user_message: str, session_id: str = DEFAULT_SESSION_ID) -> str:
    """
    Runs one full turn for a given session: loads that session's prior
    history, sends the new message + history to Gemini along with the
    available tools, executes any tool calls Gemini requests (possibly
    several rounds in a row), saves the updated history, and returns
    the final text reply.
    """
    tool = types.Tool(function_declarations=TOOL_SCHEMAS)
    config = types.GenerateContentConfig(
        system_instruction=POLICY_ASSISTANT_SYSTEM_PROMPT,
        tools=[tool],
    )

    contents = list(get_history(session_id))
    contents.append(types.Content(role="user", parts=[types.Part(text=user_message)]))

    response = None
    for _ in range(MAX_TOOL_ROUNDS):
        response = _generate_with_retry(
            model=MODEL_NAME,
            contents=contents,
            config=config,
        )

        candidate = response.candidates[0]
        function_calls = [
            part.function_call
            for part in candidate.content.parts
            if part.function_call is not None
        ]

        if not function_calls:
            contents.append(candidate.content)
            save_history(session_id, contents)
            return response.text

        contents.append(candidate.content)

        response_parts = []
        for fc in function_calls:
            args = dict(fc.args) if fc.args else {}
            result = _execute_tool(fc.name, args)
            response_parts.append(
                types.Part.from_function_response(name=fc.name, response=result)
            )

        # Gemini's API rejects role="tool" (confirmed via a live 400 error) —
        # function-response turns must use role="user" instead.
        contents.append(types.Content(role="user", parts=response_parts))

    # Safety net: exceeded MAX_TOOL_ROUNDS without a final text answer.
    # Save history anyway so the session isn't silently lost, then
    # return a graceful fallback message.
    save_history(session_id, contents)
    return (response.text if response else None) or \
        "I'm having trouble completing that request — please contact support."


if __name__ == "__main__":
    # Quick manual multi-turn test from the command line:
    #   python -m app.agent.core
    session = "cli-test"
    print(run_agent("What's the price of the LG Pixel13 Wireless Headphones?", session_id=session))
    print(run_agent("Is it in stock?", session_id=session))
    print(run_agent("What's the warranty on it?", session_id=session))