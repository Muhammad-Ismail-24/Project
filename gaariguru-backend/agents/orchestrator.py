import json
import re
import google.generativeai as genai
from openai import AsyncOpenAI
from agents.config import settings, async_retry

# Default fallback dictionary in case of API failure
FALLBACK_QUERY_DATA = {
    "make": None,
    "model": None,
    "city": None,
    "max_budget": None,
    "color": None,
    "trim": None,
    "min_year": 0,
    "max_year": 0
}

def clean_and_parse_json(response_text: str) -> dict:
    """Defensively cleans code blocks, extra text, or whitespace from the response
    and parses it into a Python dictionary.
    """
    text = response_text.strip()
    
    # Strip markdown block formatting (e.g., ```json ... ``` or ``` ... ```)
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        text = match.group(1).strip()
        
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            return FALLBACK_QUERY_DATA
        
        # Enforce exact keys and check types defensively
        validated_data = {}
        for key in ["make", "model", "city", "trim"]:
            val = data.get(key)
            validated_data[key] = str(val).strip() if val else None
            
        max_budget = data.get("max_budget")
        if max_budget is not None:
            try:
                validated_data["max_budget"] = int(max_budget)
            except (ValueError, TypeError):
                validated_data["max_budget"] = None
        else:
            validated_data["max_budget"] = None

        # Parse color
        color_val = data.get("color")
        validated_data["color"] = str(color_val).strip() if color_val else None

        # Parse year bounds
        for key in ["min_year", "max_year"]:
            val = data.get(key)
            if val is not None:
                try:
                    validated_data[key] = int(val)
                except (ValueError, TypeError):
                    validated_data[key] = 0
            else:
                validated_data[key] = 0
            
        return validated_data
        
    except json.JSONDecodeError as e:
        print(f"[Orchestrator] Failed to parse JSON response: {e}. Raw text: {repr(response_text)}")
        return FALLBACK_QUERY_DATA


async def _execute_openrouter_call(user_input: str) -> str:
    """Internal helper to execute the OpenRouter API request."""
    api_key = settings.openrouter_api_key
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is empty/not configured.")

    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key
    )

    system_prompt = (
        "You are a helpful automotive assistant specializing in Pakistani car markets. "
        "Your job is to translate and extract search parameters from user inputs into structured JSON. "
        "The user inputs can be in English, Urdu (in Arabic script), or Roman Urdu (e.g., 'mujhaye civic chahye lahore me under 30 lakh').\n\n"
        "You must extract the following fields and return ONLY a single JSON object. Do not include explanation or markdown code block wrapper:\n"
        "- 'make': Brand of the car (e.g., 'Honda', 'Toyota', 'Suzuki', 'Kia', 'Hyundai', etc.) or null if unspecified.\n"
        "- 'model': Specific model name (e.g., 'Civic', 'Corolla', 'Alto', 'Sportage', 'Tucson', etc.) or null if unspecified. WARNING for JDM N-Series: Always format Honda N-Series cars with a space (e.g., 'N One', 'N Wgn', 'N Box'). NEVER output smashed words like 'nOne' or 'nwgn'.\n"
        "- 'city': Cleaned, standardized city name (e.g., 'Lahore', 'Karachi', 'Islamabad', 'Rawalpindi', 'Peshawar', 'Faisalabad', 'Multan', 'Gujranwala', etc.). "
        "Normalize common local abbreviation/nicknames: 'isb' or 'isloo' to 'Islamabad', 'lhr' to 'Lahore', 'khi' to 'Karachi', 'rwp' or 'pindi' to 'Rawalpindi', 'pwr' or 'pesh' to 'Peshawar'. "
        "If the user asks for multiple cities, extract all of them and separate them with the word 'and' (e.g., 'Islamabad and Rawalpindi'). Defaults to null if unspecified.\n"
        "- 'max_budget': The maximum price or budget as an integer. Convert values like '30 Lakh', '30 lacs', '30 lakh' to 3000000, or '1.5 crore', '1.5 crores' to 15000000. Defaults to null if unspecified.\n"
        "- 'color': The requested color of the car (e.g., 'Black', 'White', 'Red', 'Silver', 'Grey', 'Blue'). Extract from phrases like 'black civic', 'white corolla', 'kali gari'. Defaults to null if unspecified.\n"
        "- 'trim': If the user specifies a variant, trim, or engine type (e.g., 'GLi', 'Oriel', '2D', 'Turbo'), extract it into this field. Otherwise, leave it null.\n"
        "- 'min_year' and 'max_year': Integer year bounds. If user asks for '2015 Corolla', min=2015, max=2015. 'Corolla between 2010 and 2015' -> min=2010, max=2015. 'Corolla 2000s' -> min=2000, max=2009. Leave null if unspecified.\n\n"
        "Return EXACTLY this JSON structure, with no extra keys or text:\n"
        "{\n"
        "  \"make\": \"brand_name_or_null\",\n"
        "  \"model\": \"model_name_or_null\",\n"
        "  \"city\": \"normalized_city_or_null\",\n"
        "  \"max_budget\": integer_or_null,\n"
        "  \"color\": \"color_name_or_null\",\n"
        "  \"trim\": \"string_or_null\",\n"
        "  \"min_year\": integer_or_null,\n"
        "  \"max_year\": integer_or_null\n"
        "}"
    )

    response = await client.chat.completions.create(
        model="meta-llama/llama-3.3-70b-instruct:free",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ],
        temperature=0.0,
        timeout=3.0,
        extra_headers={
            "HTTP-Referer": "https://github.com/google/antigravity",
            "X-Title": "CarFinder App"
        }
    )
    return response.choices[0].message.content or ""


@async_retry(retries=2, delay=1.0)
async def _execute_gemini_primary_orchestrate(user_input: str) -> str:
    """Primary handler using Google Gemini to parse and structure queries."""
    api_key = settings.gemini_api_key
    if not api_key:
        raise ValueError("GEMINI_API_KEY is empty/not configured.")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-3.1-flash-lite")

    system_prompt = (
        "You are a helpful automotive assistant specializing in Pakistani car markets. "
        "Your job is to translate and extract search parameters from user inputs into structured JSON. "
        "The user inputs can be in English, Urdu (in Arabic script), or Roman Urdu (e.g., 'mujhaye civic chahye lahore me under 30 lakh').\n\n"
        "You must extract the following fields and return ONLY a single JSON object. Do not include explanation or markdown code block wrapper:\n"
        "- 'make': Brand of the car (e.g., 'Honda', 'Toyota', 'Suzuki', 'Kia', 'Hyundai', etc.) or null if unspecified.\n"
        "- 'model': Specific model name (e.g., 'Civic', 'Corolla', 'Alto', 'Sportage', 'Tucson', etc.) or null if unspecified. WARNING for JDM N-Series: Always format Honda N-Series cars with a space (e.g., 'N One', 'N Wgn', 'N Box'). NEVER output smashed words like 'nOne' or 'nwgn'.\n"
        "- 'city': Cleaned, standardized city name (e.g., 'Lahore', 'Karachi', 'Islamabad', 'Rawalpindi', 'Peshawar', 'Faisalabad', 'Multan', 'Gujranwala', etc.). "
        "Normalize common local abbreviation/nicknames: 'isb' or 'isloo' to 'Islamabad', 'lhr' to 'Lahore', 'khi' to 'Karachi', 'rwp' or 'pindi' to 'Rawalpindi', 'pwr' or 'pesh' to 'Peshawar'. "
        "If the user asks for multiple cities, extract all of them and separate them with the word 'and' (e.g., 'Islamabad and Rawalpindi'). Defaults to null if unspecified.\n"
        "- 'max_budget': The maximum price or budget as an integer. Convert values like '30 Lakh', '30 lacs', '30 lakh' to 3000000, or '1.5 crore', '1.5 crores' to 15000000. Defaults to null if unspecified.\n"
        "- 'color': The requested color of the car (e.g., 'Black', 'White', 'Red', 'Silver', 'Grey', 'Blue'). Extract from phrases like 'black civic', 'white corolla', 'kali gari'. Defaults to null if unspecified.\n"
        "- 'trim': If the user specifies a variant, trim, or engine type (e.g., 'GLi', 'Oriel', '2D', 'Turbo'), extract it into this field. Otherwise, leave it null.\n"
        "- 'min_year' and 'max_year': Integer year bounds. If user asks for '2015 Corolla', min=2015, max=2015. 'Corolla between 2010 and 2015' -> min=2010, max=2015. 'Corolla 2000s' -> min=2000, max=2009. Leave null if unspecified.\n\n"
        "Return EXACTLY this JSON structure, with no extra keys or text:\n"
        "{\n"
        "  \"make\": \"brand_name_or_null\",\n"
        "  \"model\": \"model_name_or_null\",\n"
        "  \"city\": \"normalized_city_or_null\",\n"
        "  \"max_budget\": integer_or_null,\n"
        "  \"color\": \"color_name_or_null\",\n"
        "  \"trim\": \"string_or_null\",\n"
        "  \"min_year\": integer_or_null,\n"
        "  \"max_year\": integer_or_null\n"
        "}"
    )

    response = await model.generate_content_async(
        contents=[system_prompt, user_input],
        generation_config={"response_mime_type": "application/json"}
    )
    return response.text or ""


async def parse_user_query(user_input: str) -> dict:
    """Sends user query to Gemini to interpret and structure
    the automotive query fields: make, model, city, and max_budget.
    Falls back to OpenRouter if Gemini fails.
    """
    try:
        # PRIMARY: Gemini — fast, reliable JSON extraction
        content = await _execute_gemini_primary_orchestrate(user_input)
        if content:
            return clean_and_parse_json(content)
    except Exception as gemini_err:
        print(f"[Orchestrator] Gemini primary failed: {gemini_err}. Attempting OpenRouter fallback...")

    # SECONDARY FALLBACK: OpenRouter, with a strict short timeout
    try:
        content = await _execute_openrouter_call(user_input)
        if content:
            parsed_data = clean_and_parse_json(content)
            if parsed_data.get("make") or parsed_data.get("model"):
                return parsed_data
            else:
                print(f"[Orchestrator] OpenRouter returned invalid JSON text: '{content}'. Using safe default parse.")
    except Exception as e:
        print(f"[Orchestrator] OpenRouter fallback also failed: {e}. Using safe default parse.")

    return FALLBACK_QUERY_DATA


if __name__ == "__main__":
    import asyncio
    
    print("=== Testing clean_and_parse_json ===")
    test_json_markdown = """
    ```json
    {
      "make": "Honda",
      "model": "Civic",
      "city": "Lahore",
      "max_budget": 3500000
    }
    ```
    """
    parsed = clean_and_parse_json(test_json_markdown)
    print("Parsed from Markdown JSON:", parsed)