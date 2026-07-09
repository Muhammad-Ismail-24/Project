import os
import google.generativeai as genai
from openai import AsyncOpenAI
from agents.config import settings, async_retry

# Standard fallback error response if rate limits are hit or connection fails
CHATBOT_FALLBACK_RESPONSE = (
    "I'm sorry, I am currently unable to fetch automotive specification details. "
    "Please try again shortly."
)


async def _execute_llama_call(formatted_messages: list) -> str:
    """Internal helper to execute the Llama 3.3 API request on OpenRouter."""
    api_key = settings.openrouter_api_key
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is empty/not configured.")

    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key
    )

    response = await client.chat.completions.create(
        model="meta-llama/llama-3.3-70b-instruct:free",
        messages=formatted_messages,
        temperature=0.3,
        max_tokens=500,
        timeout=8.0,
        extra_headers={
            "HTTP-Referer": "https://github.com/google/antigravity",
            "X-Title": "CarFinder App Specification Chatbot"
        }
    )
    return response.choices[0].message.content or ""


@async_retry(retries=2, delay=1.0)
async def _execute_gemini_fallback_chat(formatted_messages: list) -> str:
    """Fallback helper to execute chat compilation on Google Gemini if OpenRouter fails."""
    api_key = settings.gemini_api_key
    if not api_key:
         raise ValueError("GEMINI_API_KEY is empty/not configured.")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-3.1-flash-lite")

    # Serialize system instruction and history into a cohesive chat prompt
    system_instruction = formatted_messages[0]["content"] if formatted_messages[0]["role"] == "system" else ""
    history_lines = []
    for msg in formatted_messages[1:]:
        role_label = "User" if msg["role"] == "user" else "Assistant"
        history_lines.append(f"{role_label}: {msg['content']}")
    
    prompt = (
        f"System Instructions:\n{system_instruction}\n\n"
        "Conversation History:\n" + "\n".join(history_lines) + "\nAssistant:"
    )

    response = await model.generate_content_async(prompt)
    return response.text or ""


async def get_chatbot_response(messages: list) -> str:
    """Sends a conversation history to Llama 3.3 70B via OpenRouter

    to answer Pakistani automotive specification questions.
    Uses unified settings configuration and retry protection policies.
    Falls back to Gemini 1.5 Flash if OpenRouter times out or rate limits (429).
    """
    system_instruction = (
        "You are an expert Pakistani automotive encyclopedia and appraiser. "
        "You provide precise, reliable information about cars available in Pakistan.\n\n"
        "Answer user questions accurately regarding:\n"
        "- Ground clearance (in mm or inches) relative to Pakistani speed bumps.\n"
        "- Fuel average (KM/L) in city vs highway conditions.\n"
        "- Parts availability, local manufacturing vs imports, and estimated maintenance costs.\n"
        "- Engine, transmission, and reliability issues common to specific models.\n"
        "- Differences between local trims (e.g., Honda Civic Oriel vs. RS, Toyota Altis Grande vs. GLi, Suzuki Swift DLX vs. GLX).\n\n"
        "Constraints:\n"
        "- Keep answers concise, factual, and direct. Avoid conversational fluff.\n"
        "- Focus only on the automotive domain. Refuse non-automotive queries politely."
    )

    # Build message history beginning with the system instruction
    formatted_messages = [{"role": "system", "content": system_instruction}]
    
    for msg in messages:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            formatted_messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

    # Try OpenRouter Llama first
    try:
        reply = await _execute_llama_call(formatted_messages)
        if reply:
            return reply.strip()
    except Exception as e:
        print(f"[Chatbot] OpenRouter Llama API failed: {e}. Attempting Gemini 1.5 Flash fallback...")

    # Fallback to Gemini 1.5 Flash
    try:
        reply = await _execute_gemini_fallback_chat(formatted_messages)
        if reply:
            return reply.strip()
    except Exception as gemini_err:
        print(f"[Chatbot] Gemini fallback API failed: {gemini_err}")

    return CHATBOT_FALLBACK_RESPONSE


if __name__ == "__main__":
    import asyncio

    async def test():
        test_history = [
            {"role": "user", "content": "What is the ground clearance of civic 2022 in pakistan?"}
        ]
        response = await get_chatbot_response(test_history)
        print("Test Query: What is the ground clearance of civic 2022 in pakistan?")
        print("Response:", response)

    asyncio.run(test())
