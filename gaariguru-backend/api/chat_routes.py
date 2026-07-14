"""
api/chat_routes.py

Chatbot API with persistent history for logged-in users.

Endpoints:
  GET  /api/chat/history   → returns chronological chat history (logged-in only)
  POST /api/chat           → sends a message, returns AI reply
  PUT  /api/chat/agent     → updates the user's agent_name preference
  DELETE /api/chat/history → clears the user's chat history

Auth pattern matches the rest of the codebase:
  request.session.get("user_email") → None for guests, email string for logged-in users.

Context window: the last 10 DB messages are passed to the LLM per request.
This prevents token bloat while preserving enough context for multi-turn
conversations about a single car model.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session, select
from typing import Optional

from agents.chatbot import get_chatbot_response, CHATBOT_FALLBACK_RESPONSE, DEFAULT_AGENT_NAME
from models.db_models import User, ChatMessage
from models.database import get_session   # your existing sync session factory

router = APIRouter(prefix="/api/chat", tags=["Chatbot"])

CONTEXT_WINDOW_SIZE = 10   # number of past messages sent to the LLM as context


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class SendMessageRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        description="The new message text from the user.",
        json_schema_extra={"example": "What is the fuel average of Honda Civic 2018?"}
    )

class UpdateAgentNameRequest(BaseModel):
    agent_name: str = Field(
        ...,
        min_length=1,
        max_length=40,
        description="The display name the user wants for their AI assistant.",
        json_schema_extra={"example": "Ustad Jee"}
    )


# ---------------------------------------------------------------------------
# Helper — resolve logged-in user from session
# ---------------------------------------------------------------------------

def _get_user_or_none(request: Request, session: Session) -> Optional[User]:
    """Returns the User DB row if the request session has a logged-in email, else None."""
    email = request.session.get("user_email")
    if not email:
        return None
    return session.exec(select(User).where(User.email == email)).first()


# ---------------------------------------------------------------------------
# GET /api/chat/history
# ---------------------------------------------------------------------------

@router.get("/history")
async def get_chat_history(request: Request):
    """
    Returns the full chronological chat history for the logged-in user.
    Returns an empty list for guests (no error — frontend handles both cases).
    Also returns the user's configured agent_name so the frontend can display it.
    """
    with get_session() as session:
        user = _get_user_or_none(request, session)

        if not user:
            return {
                "agent_name": DEFAULT_AGENT_NAME,
                "messages": [],
                "is_guest": True,
            }

        messages = session.exec(
            select(ChatMessage)
            .where(ChatMessage.user_id == user.id)
            .order_by(ChatMessage.created_at.asc())
        ).all()

        return {
            "agent_name": user.agent_name,
            "messages": [
                {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
                for m in messages
            ],
            "is_guest": False,
        }


# ---------------------------------------------------------------------------
# POST /api/chat
# ---------------------------------------------------------------------------

@router.post("")
async def send_message(request: Request, body: SendMessageRequest):
    """
    Accepts a single new user message and returns the AI reply.

    Logged-in users:
      1. User message saved to DB.
      2. Last CONTEXT_WINDOW_SIZE messages fetched from DB to build context.
      3. AI called with context + user's agent_name persona.
      4. AI reply saved to DB.
      5. Reply returned.

    Guests:
      - Only the single message is passed to the AI (no history, no DB writes).
      - DEFAULT_AGENT_NAME persona is used.
    """
    new_message_text = body.message.strip()

    with get_session() as session:
        user = _get_user_or_none(request, session)

        if user:
            # --- Logged-in path ---

            # 1. Persist the user's message
            user_msg_row = ChatMessage(
                user_id=user.id,
                role="user",
                content=new_message_text,
            )
            session.add(user_msg_row)
            session.commit()

            # 2. Fetch the last N messages (includes the one we just saved)
            recent_rows = session.exec(
                select(ChatMessage)
                .where(ChatMessage.user_id == user.id)
                .order_by(ChatMessage.created_at.desc())
                .limit(CONTEXT_WINDOW_SIZE)
            ).all()

            # Reverse so chronological order is preserved for the LLM
            context_messages = [
                {"role": row.role, "content": row.content}
                for row in reversed(recent_rows)
            ]

            agent_name = user.agent_name or DEFAULT_AGENT_NAME

        else:
            # --- Guest path ---
            context_messages = [{"role": "user", "content": new_message_text}]
            agent_name = DEFAULT_AGENT_NAME

        # 3. Call the LLM
        try:
            reply = await get_chatbot_response(context_messages, agent_name=agent_name)
        except Exception as e:
            print(f"[Chat Router] LLM call failed: {e}")
            raise HTTPException(
                status_code=503,
                detail="Automotive chat service is temporarily unavailable. Please try again later."
            )

        if reply == CHATBOT_FALLBACK_RESPONSE:
            raise HTTPException(
                status_code=503,
                detail="Automotive chat service is temporarily unavailable. Please try again later."
            )

        # 4. Persist the AI reply (logged-in only)
        if user:
            ai_msg_row = ChatMessage(
                user_id=user.id,
                role="assistant",
                content=reply,
            )
            session.add(ai_msg_row)
            session.commit()

    return {"reply": reply, "agent_name": agent_name}


# ---------------------------------------------------------------------------
# PUT /api/chat/agent  — update persona name
# ---------------------------------------------------------------------------

@router.put("/agent")
async def update_agent_name(request: Request, body: UpdateAgentNameRequest):
    """
    Saves the user's preferred AI assistant name.
    Guests receive 401 — this setting only makes sense for logged-in users.
    """
    with get_session() as session:
        user = _get_user_or_none(request, session)
        if not user:
            raise HTTPException(status_code=401, detail="Login required to customize your assistant.")

        user.agent_name = body.agent_name.strip()
        session.add(user)
        session.commit()

    return {"agent_name": user.agent_name, "message": "Assistant name updated."}


# ---------------------------------------------------------------------------
# DELETE /api/chat/history  — clear history
# ---------------------------------------------------------------------------

@router.delete("/history")
async def clear_chat_history(request: Request):
    """
    Deletes all stored chat messages for the logged-in user.
    Useful for starting a fresh conversation. Guests receive 401.
    """
    with get_session() as session:
        user = _get_user_or_none(request, session)
        if not user:
            raise HTTPException(status_code=401, detail="Login required.")

        messages = session.exec(
            select(ChatMessage).where(ChatMessage.user_id == user.id)
        ).all()

        for msg in messages:
            session.delete(msg)
        session.commit()

    return {"message": f"Cleared {len(messages)} messages from your chat history."}