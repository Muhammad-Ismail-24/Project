from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session, select
from typing import Optional, List
import uuid

from agents.chatbot import get_chatbot_response, CHATBOT_FALLBACK_RESPONSE, DEFAULT_AGENT_NAME
from models.db_models import User, ChatMessage
from database import get_session

router = APIRouter(prefix="/api/chat", tags=["Chatbot"])

CONTEXT_WINDOW_SIZE = 10

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: Optional[str] = None

class UpdateAgentNameRequest(BaseModel):
    agent_name: str = Field(..., min_length=1, max_length=40)

def _get_user_or_none(request: Request, session: Session) -> Optional[User]:
    # FIX: auth route saves 'user_id' to session, NOT 'user_email'.
    # Reading 'user_email' always returned None, putting every logged-in
    # user into guest mode. Confirmed via Render logs:
    #   all session keys: ['user_id']   ← cookie arrives correctly
    #   user_email in cookie session: None  ← wrong key was being read
    user_id = request.session.get("user_id")
    if not user_id:
        # Try email as a fallback in case auth route varies
        email = request.session.get("user_email")
        if not email:
            return None
        user = session.exec(select(User).where(User.email == email)).first()
        return user

    user = session.exec(select(User).where(User.id == int(user_id))).first()

    # Auto-heal: valid session but DB row missing (e.g. after DB reset)
    if not user:
        email = request.session.get("user_email")
        name = request.session.get("user_name") or "User"
        picture = request.session.get("user_picture")
        if email:
            new_user = User(
                email=email,
                name=name,
                picture=picture,
                agent_name="GaariGuru Expert"
            )
            session.add(new_user)
            session.commit()
            session.refresh(new_user)
            return new_user
        return None

    return user

@router.get("/sessions")
async def get_chat_sessions(request: Request, session: Session = Depends(get_session)):
    user = _get_user_or_none(request, session)
    if not user:
        return {"sessions": [], "is_guest": True}

    messages = session.exec(
        select(ChatMessage)
        .where(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at.desc())
    ).all()

    seen_sessions = set()
    sessions_list = []
    
    for msg in messages:
        if msg.session_id not in seen_sessions:
            seen_sessions.add(msg.session_id)
            snippet = msg.content[:40] + "..." if len(msg.content) > 40 else msg.content
            sessions_list.append({
                "session_id": msg.session_id,
                "latest_message": snippet,
                "updated_at": msg.created_at.isoformat()
            })
            
    return {"sessions": sessions_list, "is_guest": False}

@router.get("/history/{session_id}")
async def get_session_history(session_id: str, request: Request, session: Session = Depends(get_session)):
    user = _get_user_or_none(request, session)
    if not user:
        return {"agent_name": DEFAULT_AGENT_NAME, "messages": [], "is_guest": True}

    messages = session.exec(
        select(ChatMessage)
        .where(ChatMessage.user_id == user.id, ChatMessage.session_id == session_id)
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

@router.post("")
async def send_message(request: Request, body: ChatRequest, session: Session = Depends(get_session)):
    new_message_text = body.message.strip()
    user = _get_user_or_none(request, session)

    session_id = body.session_id
    if not session_id or not session_id.strip():
        session_id = uuid.uuid4().hex

    if user:
        user_msg_row = ChatMessage(
            user_id=user.id,
            session_id=session_id,
            role="user",
            content=new_message_text,
        )
        session.add(user_msg_row)
        session.commit()

        recent_rows = session.exec(
            select(ChatMessage)
            .where(ChatMessage.user_id == user.id, ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(CONTEXT_WINDOW_SIZE)
        ).all()

        context_messages = [
            {"role": row.role, "content": row.content}
            for row in reversed(recent_rows)
        ]

        agent_name = user.agent_name or DEFAULT_AGENT_NAME
    else:
        context_messages = [{"role": "user", "content": new_message_text}]
        agent_name = DEFAULT_AGENT_NAME

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

    if user:
        ai_msg_row = ChatMessage(
            user_id=user.id,
            session_id=session_id,
            role="assistant",
            content=reply,
        )
        session.add(ai_msg_row)
        session.commit()
        print(f"[Chat DEBUG] ✅ assistant message saved — user_id={user.id}, session_id={session_id}")
    else:
        print(f"[Chat DEBUG] ⚠️ guest mode — no messages saved to DB")

    return {"role": "assistant", "content": reply, "session_id": session_id, "agent_name": agent_name}

@router.put("/agent")
async def update_agent_name(request: Request, body: UpdateAgentNameRequest, session: Session = Depends(get_session)):
    user = _get_user_or_none(request, session)
    if not user:
        raise HTTPException(status_code=401, detail="Login required to customize your assistant.")

    user.agent_name = body.agent_name.strip()
    session.add(user)
    session.commit()

    return {"agent_name": user.agent_name, "message": "Assistant name updated."}

@router.delete("/{session_id}")
async def delete_chat_session(session_id: str, request: Request, session: Session = Depends(get_session)):
    user = _get_user_or_none(request, session)
    if not user:
        raise HTTPException(status_code=401, detail="Login required.")

    messages = session.exec(
        select(ChatMessage).where(ChatMessage.user_id == user.id, ChatMessage.session_id == session_id)
    ).all()

    for msg in messages:
        session.delete(msg)
    session.commit()

    return {"message": f"Session {session_id} deleted."}