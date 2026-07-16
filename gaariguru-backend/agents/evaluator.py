import json
import re
import google.generativeai as genai
from models.car_schema import CarListing
from typing import List
from agents.config import settings, async_retry

# Setup default fallback analysis dictionary if API fails
DEFAULT_AI_ANALYSIS = {
    "red_flags": [],
    "liquidity_score": "Medium",
    "justification": "AI appraisal is currently unavailable. Listing meets general criteria."
}


def _sanitize_json_response(raw_text: str) -> str:
    """
    Bug 3 Fix: Indestructible JSON sanitization layer.
    Strips markdown wrappers, clips between structural brackets,
    removes dangling trailing commas, and attempts truncation recovery.
    """
    text = raw_text.strip()

    # Step 1: Strip markdown code fences (```json ... ``` or ``` ... ```)
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*```$', '', text)
    text = text.strip()

    # Step 2: Bracket-slice — crop precisely between first [ or { and last ] or }
    first_bracket = min(
        (text.find('[') if text.find('[') != -1 else len(text)),
        (text.find('{') if text.find('{') != -1 else len(text))
    )
    last_bracket = max(text.rfind(']'), text.rfind('}'))

    if first_bracket < last_bracket:
        text = text[first_bracket:last_bracket + 1]

    # Step 3: Remove dangling trailing commas before closing brackets
    text = re.sub(r',\s*([\]\}])', r'\1', text)

    # Step 4: Truncation recovery — if Gemini cut off mid-array, attempt to close it.
    # Count unmatched brackets and append closers if needed.
    try:
        json.loads(text)
    except json.JSONDecodeError:
        # Attempt to recover a truncated array by trimming to last complete object
        # Find the last complete closing brace
        last_obj_end = text.rfind('}')
        if last_obj_end != -1:
            text = text[:last_obj_end + 1]
            # Ensure the array is properly closed
            if text.lstrip().startswith('['):
                text = text + ']'
            # Strip any trailing comma before the new closing bracket
            text = re.sub(r',\s*\]$', ']', text)

    return text.strip()


# Retries=3: allows 3 re-attempts on 429 with 15s sleep between each
@async_retry(retries=3, delay=2.0)
async def _execute_gemini_call(model: genai.GenerativeModel, system_instruction: str, prompt: str):
    """Executes the async Gemini call wrapped inside the retry handler."""
    return await model.generate_content_async(
        contents=[system_instruction, prompt],
        generation_config={
            # Task 3 Fix: max_output_tokens raised from 2000 to 8000 to prevent
            # premature JSON truncation when evaluating 5 cars.
            "response_mime_type": "application/json",
            "max_output_tokens": 8000
        }
    )


async def evaluate_scraped_listings(listings: List[CarListing], original_user_query: str) -> List[dict]:
    """Evaluates all scraped listings simultaneously using Gemini 1.5 Flash.

    Appraises Pakistani market red flags, resale liquidity, and intent matching.
    Returns a list of dictionaries representing the listings enriched with 'ai_analysis'.
    """
    if not listings:
        return []

    # Get API key from global settings helper
    api_key = settings.gemini_api_key
    if not api_key:
        print("[Evaluator] WARNING: GEMINI_API_KEY is not configured in settings. Using fallbacks.")
        return [
            {**json.loads(car.model_dump_json()), "ai_analysis": DEFAULT_AI_ANALYSIS}
            for car in listings
        ]

    try:
        # Configure Gemini client
        genai.configure(api_key=api_key)
        # Using gemini-3.1-flash-lite for higher rate limits
        model = genai.GenerativeModel("gemini-3.1-flash-lite")

        # Serialize the listings for model context
        serialized_cars = []
        for car in listings:
            serialized_cars.append({
                "id": car.id,
                "title": car.title,
                "price": car.price,
                "mileage": car.mileage,
                "city": car.city,
                "year": car.year,
                "platform": car.platform
            })

        system_instruction = (
            "You are an expert Pakistani automotive appraiser and market analyst. "
            "Your job is to analyze multiple car listings simultaneously against a user's original query.\n\n"
            "Evaluate each car listing for:\n"
            "1. 'red_flags': Scan the title and metadata for common risk factors in Pakistan, such as:\n"
            "   - 'Duplicate Book' (duplicate registration book/documents)\n"
            "   - 'Showered for fresh look' (body repainted/showered)\n"
            "   - 'Non-Custom Paid' / 'NCP' (smuggled or tax-evaded vehicles)\n"
            "   - 'Engine Swapped' / 'Engine Change'\n"
            "   - 'File Missing' or 'File Duplicate'\n"
            "   - 'Auction Sheet Missing' (for Japanese imports)\n"
            "   - If no red flags are found, return an empty list [].\n"
            "2. 'liquidity_score': The market velocity and ease of resale in Pakistan for this segment. Must be strictly one of: 'High', 'Medium', or 'Low'. "
            "For example: Suzuki Alto, Toyota Corolla, and Honda Civic typically have 'High' liquidity; luxury imports or rare models have 'Low' liquidity.\n"
            "3. 'justification': A clear 2-3 sentence explanation of how well this car matches the user's initial search query (budget, city, model preferences).\n\n"
            "You must return a valid JSON array of objects. Each object must map to one of the input listings by its 'id'. "
            "Do not include any conversational text or markdown code wrappers in the response. Return strictly the raw JSON array.\n"
            "JSON Response format:\n"
            "[\n"
            "  {\n"
            "    \"id\": \"car-uuid\",\n"
            "    \"red_flags\": [\"flag1\", \"flag2\"],\n"
            "    \"liquidity_score\": \"High\" | \"Medium\" | \"Low\",\n"
            "    \"justification\": \"A 2-3 sentence justification matching the query.\"\n"
            "  }\n"
            "]"
        )

        prompt = (
            f"User Original Query: \"{original_user_query}\"\n\n"
            f"Listings to Analyze:\n{json.dumps(serialized_cars, indent=2)}\n\n"
            "Perform the appraisal and return the JSON array matching the request:"
        )

        # Execute API call with retries
        response = await _execute_gemini_call(model, system_instruction, prompt)
        response_text = response.text.strip()
        
        # Parse the JSON response with sanitization
        try:
            sanitized = _sanitize_json_response(response_text)
            analyses = json.loads(sanitized)
            # Create a lookup mapping from id -> analysis block
            analysis_map = {}
            if isinstance(analyses, list):
                for item in analyses:
                    car_id = item.get("id")
                    if car_id:
                        red_flags = item.get("red_flags", [])
                        if not isinstance(red_flags, list):
                            red_flags = [str(red_flags)]
                        
                        score = item.get("liquidity_score", "Medium")
                        if score not in ["High", "Medium", "Low"]:
                            score = "Medium"
                            
                        justification = item.get("justification", "Matches criteria.")
                        
                        analysis_map[car_id] = {
                            "red_flags": red_flags,
                            "liquidity_score": score,
                            "justification": justification
                        }
            
            # Assemble and return final listings list
            final_listings = []
            for car in listings:
                car_dict = json.loads(car.model_dump_json())
                car_dict["ai_analysis"] = analysis_map.get(car.id, DEFAULT_AI_ANALYSIS)
                final_listings.append(car_dict)
                
            return final_listings

        except (json.JSONDecodeError, TypeError) as parse_err:
            print(f"[Evaluator] Error decoding Gemini JSON: {parse_err}. Raw output: {repr(response_text)}")
            return [
                {**json.loads(car.model_dump_json()), "ai_analysis": DEFAULT_AI_ANALYSIS}
                for car in listings
            ]

    except Exception as e:
        print(f"[Evaluator] Exception during Gemini generation: {e}")
        return [
            {**json.loads(car.model_dump_json()), "ai_analysis": DEFAULT_AI_ANALYSIS}
            for car in listings
        ]


async def evaluate_single_listing(listing: dict, original_user_query: str) -> dict:
    """Evaluates a single car listing using Gemini and returns an AI analysis dict.

    Returns a dict with keys: red_flags, liquidity_score, justification.
    Falls back to DEFAULT_AI_ANALYSIS on any failure.
    """
    api_key = settings.gemini_api_key
    if not api_key:
        print("[Evaluator] WARNING: GEMINI_API_KEY not configured. Returning default analysis.")
        return DEFAULT_AI_ANALYSIS

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3.1-flash-lite")

        system_instruction = (
            "You are an expert Pakistani automotive appraiser. "
            "Evaluate this SINGLE vehicle listing against the Pakistani used car market. "
            "Consider its price, mileage, year, and city. "
            "Return a strict JSON object with exactly three keys: "
            "'red_flags' (list of strings - check for Duplicate Book, Showered, NCP, "
            "Engine Swap, File Missing, Auction Sheet Missing etc. - empty list if none), "
            "'liquidity_score' (strictly 'High', 'Medium', or 'Low'), and "
            "'justification' (2-3 sentences explaining market fit). "
            "Do NOT return markdown or conversational text. Return ONLY the raw JSON object."
        )

        prompt = (
            f"User Original Query: \"{original_user_query}\"\n\n"
            f"Listing to Evaluate:\n"
            f"  Title: {listing.get('title', 'N/A')}\n"
            f"  Price: {listing.get('price', 'N/A')}\n"
            f"  Mileage: {listing.get('mileage', 'N/A')}\n"
            f"  Year: {listing.get('year', 'N/A')}\n"
            f"  City: {listing.get('city', 'N/A')}\n"
            f"  Platform: {listing.get('platform', 'N/A')}\n\n"
            "Perform the appraisal and return the JSON object:"
        )

        response = await model.generate_content_async(
            contents=[system_instruction, prompt],
            generation_config={
                "response_mime_type": "application/json",
                "max_output_tokens": 2000
            }
        )

        response_text = response.text.strip()
        sanitized = _sanitize_json_response(response_text)
        parsed = json.loads(sanitized)

        # Validate and normalize the parsed result
        if not isinstance(parsed, dict):
            print(f"[Evaluator] Single listing response is not a dict: {type(parsed)}")
            return DEFAULT_AI_ANALYSIS

        red_flags = parsed.get("red_flags", [])
        if not isinstance(red_flags, list):
            red_flags = [str(red_flags)]

        score = parsed.get("liquidity_score", "Medium")
        if score not in ["High", "Medium", "Low"]:
            score = "Medium"

        justification = parsed.get("justification", "Matches criteria.")
        if not isinstance(justification, str):
            justification = str(justification)

        return {
            "red_flags": red_flags,
            "liquidity_score": score,
            "justification": justification
        }

    except Exception as e:
        print(f"[Evaluator] Exception during single listing evaluation: {e}")
        return DEFAULT_AI_ANALYSIS
