"""
app/main.py

FastAPI entrypoint. Exposes the agent (built in Steps 3-7) as a single
HTTP endpoint — /chat — that any channel (website widget, WhatsApp
adapter, Telegram adapter, etc.) can call the exact same way. None of
those channels need to know anything about Postgres, ChromaDB, or
Gemini function calling — they just POST a message and session_id and
get a text reply back.

Run locally with:
    uvicorn app.main:app --reload

Then test with:
    curl -X POST http://127.0.0.1:8000/chat \
      -H "Content-Type: application/json" \
      -d '{"message": "What is your return policy?", "session_id": "test-1"}'
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.agent.core import run_agent
from app.agent.memory import clear_session

app = FastAPI(
    title="E-commerce AI Agent",
    description="RAG + database tools + order actions, exposed via one channel-agnostic API.",
    version="0.1.0",
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The customer's message.")
    session_id: str = Field(
        default="default",
        description="Groups messages into one conversation. Use a distinct id per "
                    "customer/channel session so different customers never share memory.",
    )


class ChatResponse(BaseModel):
    reply: str
    session_id: str


@app.get("/")
def health_check():
    """Simple liveness check — useful for uptime monitoring and confirming the server is up."""
    return {"status": "ok", "service": "ecommerce-ai-agent"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """
    Main entrypoint for every channel. Takes one user message (plus an
    optional session_id to maintain conversation memory across calls)
    and returns the agent's reply.
    """
    try:
        reply = run_agent(request.message, session_id=request.session_id)
    except Exception as e:
        # Don't leak internal stack traces to the client — log server-side
        # (print() is a placeholder; swap for real logging before production)
        # and return a generic error the caller can display safely.
        print(f"[/chat error] session={request.session_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Something went wrong processing your message. Please try again shortly.",
        )

    return ChatResponse(reply=reply, session_id=request.session_id)


@app.post("/chat/reset")
def reset_chat(session_id: str = "default"):
    """
    Clears a session's conversation history — e.g. for a "start over"
    button in a chat widget, or when a customer explicitly asks to
    reset the conversation.
    """
    clear_session(session_id)
    return {"status": "ok", "session_id": session_id, "message": "Session history cleared."}
