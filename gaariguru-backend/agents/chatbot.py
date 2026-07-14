"""
agents/chatbot.py

Conversational automotive assistant for GaariGuru.

The AI persona is configurable per user via their `agent_name` setting
(stored in the User table, default "GaariGuru Expert"). The caller passes
`agent_name` into `get_chatbot_response()` — the system prompt injects it
so the AI introduces itself by that name and signs its answers with it.

All existing API execution functions (_execute_llama_call,
_execute_gemini_fallback_chat) and retry/fallback logic are unchanged.
"""

import google.generativeai as genai
from openai import AsyncOpenAI
from agents.config import settings, async_retry

# Returned when BOTH primary and fallback APIs fail.
CHATBOT_FALLBACK_RESPONSE = (
    "I'm sorry, I am currently unable to fetch automotive specification details. "
    "Please try again shortly."
)

# Default persona name used for guests and as the pre-settings default for new users.
# Changing this constant changes the out-of-the-box experience for everyone.
DEFAULT_AGENT_NAME = "GaariGuru Expert"


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
    """Fallback: executes the chat on Google Gemini if OpenRouter fails."""
    api_key = settings.gemini_api_key
    if not api_key:
        raise ValueError("GEMINI_API_KEY is empty/not configured.")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-3.1-flash-lite")

    system_instruction = (
        formatted_messages[0]["content"]
        if formatted_messages and formatted_messages[0]["role"] == "system"
        else ""
    )
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


def _build_system_prompt(agent_name: str) -> str:
    """
    Builds the system prompt with the persona injected.

    The agent_name is whatever the user set in Settings (e.g. "Ustad Jee",
    "AutoGuru", "Car Bhai") or the default "GaariGuru Expert" for guests.
    The rest of the persona — knowledge domain, tone, constraints — is fixed.
    """
    return (
        f"Your name is {agent_name}. "
        "You are a top-tier Pakistani automotive expert — the kind of person who "
        "has spent 20 years driving, inspecting, and negotiating cars across "
        "Islamabad, Lahore, and Karachi. You know every pothole route, every "
        "speed-bump height, and which ustaad mechanic to trust on which model.\n\n"

        "Speak with total confidence and authority. You never say 'As an AI' or "
        "'I cannot be sure'. You give direct, specific answers the way a friend "
        "who happens to be a car expert would — not a textbook. Use natural "
        "conversational English. You may occasionally drop a Pakistani automotive "
        "phrase (like 'market ki gari', 'ustaad', 'original condition') where it "
        "fits naturally, but keep the response fully readable in English.\n\n"

        "Your encyclopedic knowledge covers:\n"
        "- Ground clearance in mm/inches and how each model handles Pakistani "
        "speed bumps (especially underbody scraping risk on Corolla, City, Civic).\n"
        "- Real-world fuel averages in Pakistani city traffic vs. motorway — "
        "never quote manufacturer claims, always quote what Pakistani drivers report.\n"
        "- Parts availability: which parts are locally made, which are imported, "
        "and rough PKR cost of a major service (timing belt, clutch, etc.).\n"
        "- Known reliability issues by model year — which years to avoid and why "
        "(e.g., 2012-2013 Civic AC compressor failures, 2017 Cultus auto gearbox).\n"
        "- Complete trim comparison knowledge for Pakistani market variants: "
        "Civic Oriel vs RS, Corolla GLi vs XLi vs Altis Grande, "
        "Alto VXR vs VXL vs AGS, Swift DLX vs GLX vs GLX CVT, "
        "City Aspire vs i-VTEC, BR-V S vs E vs V.\n"
        "- Resale value realities: which cars hold value ('liquid gari') vs. "
        "which depreciate fast and why (Japanese reliability bias in Pakistani market).\n"
        "- Inspection advice: what to check on a used car — frame damage signs, "
        "Carfax equivalents, how to spot flood damage in Pakistan.\n\n"

        "Constraints:\n"
        "- Keep answers concise but complete. Two to four short paragraphs maximum.\n"
        "- If a question is outside the automotive domain, politely decline once "
        "and redirect to car topics.\n"
        "- Never make up specific numbers you are not confident about — "
        "say 'roughly' or give a range instead of a precise figure you might be wrong on.\n"
        f"- Sign off long responses naturally as {agent_name} when it feels right, "
        "but don't force it every time."
    )


async def get_chatbot_response(
    messages: list,
    agent_name: str = DEFAULT_AGENT_NAME,
) -> str:
    """
    Sends a conversation history to Llama 3.3 70B via OpenRouter.

    Args:
        messages:    List of {"role": "user"|"assistant", "content": "..."} dicts.
                     The caller is responsible for limiting context window size
                     (chat_routes.py passes the last 10 DB messages for logged-in users).
        agent_name:  The persona name injected into the system prompt.
                     Fetched from User.agent_name in the DB for logged-in users.
                     Defaults to DEFAULT_AGENT_NAME for guests.

    Falls back to Gemini 1.5 Flash if OpenRouter times out or rate-limits (429).
    """
    system_prompt = _build_system_prompt(agent_name)

    formatted_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            formatted_messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

    # Primary: OpenRouter Llama 3.3 70B
    try:
        reply = await _execute_llama_call(formatted_messages)
        if reply:
            return reply.strip()
    except Exception as e:
        print(f"[Chatbot] OpenRouter Llama API failed: {e}. Attempting Gemini fallback...")

    # Fallback: Google Gemini
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
        response = await get_chatbot_response(test_history, agent_name="GaariGuru Expert")
        print("Test Query: What is the ground clearance of civic 2022 in pakistan?")
        print("Response:", response)

    asyncio.run(test())