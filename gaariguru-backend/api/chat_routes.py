from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict
from agents.chatbot import get_chatbot_response, CHATBOT_FALLBACK_RESPONSE

router = APIRouter(prefix="/api/chat", tags=["Chatbot"])

class ChatRequest(BaseModel):
    messages: List[Dict[str, str]] = Field(
        ..., 
        description="List of conversation history containing role ('user', 'assistant') and content",
        json_schema_extra={"example": [{"role": "user", "content": "What is the fuel average of Honda Civic 2018 in city?"}]}
    )

@router.post("")
async def chat_with_llama(request: ChatRequest):
    """Conversational endpoint to chat with the Pakistani automotive specification agent."""
    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages list cannot be empty")
        
    try:
        reply = await get_chatbot_response(request.messages)
        
        # Check if we hit rate limits or configuration exceptions that returned fallback
        if reply == CHATBOT_FALLBACK_RESPONSE:
            raise HTTPException(
                status_code=503, 
                detail="Automotive chat service is temporarily unavailable. Please try again later."
            )
            
        return {"reply": reply}
        
    except HTTPException:
        # Re-raise HTTP exceptions to maintain status codes
        raise
    except Exception as e:
        print(f"[Chat Router] Error getting spec response: {e}")
        raise HTTPException(
            status_code=503, 
            detail="Automotive chat service is temporarily unavailable. Please try again later."
        )
