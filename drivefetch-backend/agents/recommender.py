"""
agents/recommender.py
LLM logic for mapping user features to specific car models.
"""
import os
import json
import re
import traceback
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

SEMANTIC_MAPPER_PROMPT = """
You are an expert Pakistani automotive advisor with deep knowledge of the
used car market. A user will describe what they want in natural language,
Roman Urdu, or Urdu script. Your job is to translate their requirement
into a list of specific car models they should search for.

STRICT RULES:
1. Return ONLY a valid JSON array. No preamble, no explanation, no markdown.
2. Return 2-5 car models maximum. More is worse — focus on the best matches.
3. Use exact make/model names as they appear on PakWheels Pakistan.
4. If the user mentions a budget, split it across trim levels where relevant.
5. If no city is mentioned, set city to null.
6. Always prefer locally assembled (locally popular) cars over obscure imports.
7. For budget under 20 lacs: Suzuki Alto, Suzuki Cultus, Toyota Vitz, Honda City (old)
8. For 20-40 lacs: Honda Civic (FC/FD), Toyota Corolla (various), Suzuki Swift
9. For 40-80 lacs: Honda Civic (latest), Toyota Fortuner, Kia Sportage, MG HS, Hyundai Tucson
10. For 80+ lacs: Toyota Fortuner (latest), Kia Stinger, Chery Tiggo 8 Pro, MG Gloster

PAKISTANI MARKET KNOWLEDGE:
- "AWD" or "4x4" → Kia Sportage AWD, Hyundai Tucson AWD, Toyota Fortuner 4x4
- "Sunroof" → MG HS, Kia Sportage, Hyundai Tucson, Chery Tiggo 8 Pro
- "7 seater" / "family SUV" → KIA Sorento, Toyota Fortuner, MG Gloster, Chery Tiggo 8 Pro
- "Economical" / "fuel efficient" → Suzuki Alto, Daihatsu Mira, Toyota Vitz
- "Automatic" budget car → Suzuki Alto AGS, Suzuki Cultus AGS
- "Hybrid" → Toyota Prius, Toyota Aqua, Honda Vezel
- "New driver" / "first car" → Suzuki Alto, Suzuki Cultus, Toyota Vitz
- "Performance" / "sports" → Honda Civic (Turbo FC)
- "CNG" → Only if user explicitly wants it.
- Prices in Pakistan are in PKR. "Lacs" = 100,000 PKR. "Crore" = 10,000,000 PKR.

OUTPUT FORMAT (strict JSON array):
[
  {
    "make": "Honda",
    "model": "Civic",
    "trim": "Turbo",
    "city": "Lahore",
    "max_budget": 4000000,
    "rationale": "Best performance car in this budget with factory turbo engine"
  }
]

If trim is not relevant or specified, set trim to null.
If budget is not mentioned, set max_budget to null.
"""

async def semantic_mapper(user_prompt: str) -> list[dict]:
    """
    Calls Gemini using the modern google-genai SDK to translate a natural 
    language requirement into a list of structured car search queries.
    """
    try:
        response = await client.aio.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=user_prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=1000,
                system_instruction=SEMANTIC_MAPPER_PROMPT,
            ),
        )
        
        raw = response.text.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)

        recommendations = json.loads(raw)

        if not isinstance(recommendations, list):
            raise ValueError("Expected JSON array")

        print(f"[Recommender] Semantic Mapper returned {len(recommendations)} targets:")
        for r in recommendations:
            print(f"  → {r.get('make')} {r.get('model')} {r.get('trim','')} | Budget: {r.get('max_budget')}")

        return recommendations

    except Exception as e:
        print(f"[Recommender] Semantic Mapper failed: {e}")
        traceback.print_exc()
        return []