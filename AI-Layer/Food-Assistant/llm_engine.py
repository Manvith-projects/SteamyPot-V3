"""
llm_engine.py  --  LangChain + Gemini Intent Detection & Entity Extraction
===========================================================================
Uses Google Gemini via LangChain to parse natural language food queries
into structured parameters.

AI Concepts
-----------
1. **Intent Detection** (NLU task):
   Classify what the user wants: search_food, get_recommendations,
   ask_question, greeting, etc.  This is a text classification problem
   that LLMs excel at via in-context learning (no fine-tuning needed).

2. **Entity Extraction** (NER task):
   Pull structured entities from free text:
     "spicy chicken under ₹300 near Kukatpally"
     → {cuisine: null, diet_type: "non-veg", tags: ["spicy"],
        price_limit: 300, location: "Kukatpally"}

3. **Structured Output Parsing** (LangChain concept):
   We use a Pydantic model + LangChain's JSON output parser to
   guarantee the LLM output matches our schema.  This avoids brittle
   regex parsing and handles edge cases the LLM naturally understands.

4. **Prompt Engineering**:
   The system prompt defines:
   - Available fields and their types
   - Examples (few-shot learning)
   - Constraints ("set null if not mentioned")
   This is cheaper and faster than fine-tuning for extraction tasks.

5. **Fallback System**:
   If the Gemini API is unreachable or the API key is missing, we
   fall back to a rule-based regex extractor. This ensures the
   system always works even without an LLM.

Architecture
------------
  User query
      ↓
  LangChain ChatPromptTemplate (system + human messages)
      ↓
  ChatGoogleGenerativeAI (Gemini 1.5 Flash)
      ↓
  PydanticOutputParser → FoodQuery(Pydantic model)
      ↓
  Structured params dict → database.search()
"""

import os
import re
import json
import threading
from typing import Optional, List
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Pydantic schema for structured output
# ---------------------------------------------------------------------------

class FoodQuery(BaseModel):
    """
    Structured representation of a food search query.

    AI Concept: Schema-Constrained Generation
    ------------------------------------------
    By defining a Pydantic schema, we tell the LLM exactly what fields
    to extract and their types.  LangChain's output parser validates the
    response and retries if the JSON is malformed.
    """
    intent: str = Field(
        default="search_food",
        description="User intent: search_food | get_recommendations | browse_offers | greeting | general_question | unclear"
    )
    price_limit: Optional[float] = Field(
        default=None,
        description="Maximum price in ₹ (e.g., 300). Null if not specified."
    )
    cuisine: Optional[str] = Field(
        default=None,
        description="Cuisine type: North Indian, South Indian, Chinese, Biryani, Italian, etc."
    )
    diet_type: Optional[str] = Field(
        default=None,
        description="Diet preference: veg, non-veg, vegan, healthy, spicy, keto, etc."
    )
    tags: Optional[List[str]] = Field(
        default=None,
        description="Food tags: spicy, healthy, comfort, light, protein-rich, low-calorie, keto, etc."
    )
    location: Optional[str] = Field(
        default=None,
        description="Location/area name mentioned by user (e.g., Kukatpally, Madhapur)"
    )
    max_distance_km: Optional[float] = Field(
        default=None,
        description="Maximum delivery distance in km. Null if not specified."
    )
    meal_time: Optional[str] = Field(
        default=None,
        description="Meal time: breakfast, lunch, dinner, snack. Null if not specified."
    )
    specific_item: Optional[str] = Field(
        default=None,
        description="Specific food item mentioned (e.g., biryani, pizza, dosa)"
    )


# ---------------------------------------------------------------------------
# System prompt for Gemini
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an AI food assistant for a food delivery platform in Hyderabad, India.

Your job is to extract structured search parameters from the user's natural language food query.

RULES:
1. Extract ONLY what the user explicitly mentions. Set fields to null if not mentioned.
2. For price_limit, extract the numeric value (e.g., "under 300" → 300, "below ₹500" → 500).
3. For cuisine, map to: North Indian, South Indian, Chinese, Biryani, Italian, Continental, Street Food, Mughlai, Desserts, Healthy Bowls, Fast Food, Seafood.
4. For diet_type, detect: veg, non-veg, vegan, healthy, spicy, keto, etc.
5. For tags, detect descriptors: spicy, healthy, comfort, light, protein-rich, low-calorie, keto, gluten-free, high-fibre, traditional, fusion.
6. For location, extract area names: Kukatpally, Madhapur, Gachibowli, Hitech City, Banjara Hills, Jubilee Hills, Kondapur, Ameerpet, etc.
7. For meal_time, detect: breakfast, lunch, dinner, snack. Infer from time references like "tonight" → dinner, "morning" → breakfast.
8. For specific_item, extract specific food names like "biryani", "pizza", "dosa", "burger".
9. For intent: 
   - "search_food" if user is looking for food/restaurants
   - "get_recommendations" if user asks for suggestions/recommendations
   - "browse_offers" if user asks about offers, deals, discounts, coupons, promotions, or sale
   - "greeting" if user is just saying hello/hi
   - "general_question" if user asks about the platform
   - "unclear" if the query doesn't relate to food

IMPORTANT: Respond ONLY with valid JSON matching this exact schema:
{schema}

EXAMPLES:
User: "Suggest healthy food under ₹300 near me"
→ {{"intent": "search_food", "price_limit": 300, "cuisine": null, "diet_type": "healthy", "tags": ["healthy", "low-calorie"], "location": null, "max_distance_km": 5, "meal_time": null, "specific_item": null}}

User: "I want spicy chicken around Kukatpally"
→ {{"intent": "search_food", "price_limit": null, "cuisine": null, "diet_type": "non-veg", "tags": ["spicy"], "location": "Kukatpally", "max_distance_km": null, "meal_time": null, "specific_item": "chicken"}}

User: "Best vegetarian dinner options tonight"
→ {{"intent": "search_food", "price_limit": null, "cuisine": null, "diet_type": "veg", "tags": null, "location": null, "max_distance_km": null, "meal_time": "dinner", "specific_item": null}}

User: "Show me biryani places in Madhapur under 400"
→ {{"intent": "search_food", "price_limit": 400, "cuisine": "Biryani", "diet_type": null, "tags": null, "location": "Madhapur", "max_distance_km": null, "meal_time": null, "specific_item": "biryani"}}

User: "Any offers?"
→ {{"intent": "browse_offers", "price_limit": null, "cuisine": null, "diet_type": null, "tags": null, "location": null, "max_distance_km": null, "meal_time": null, "specific_item": null}}

User: "Show me discounts on biryani"
→ {{"intent": "browse_offers", "price_limit": null, "cuisine": "Biryani", "diet_type": null, "tags": null, "location": null, "max_distance_km": null, "meal_time": null, "specific_item": "biryani"}}
"""


# ---------------------------------------------------------------------------
# LangChain + Gemini LLM engine
# ---------------------------------------------------------------------------

class LLMEngine:
    """
    Natural language → structured food query using LangChain + Gemini.

    AI Concept: LLM-as-a-Service Architecture
    -------------------------------------------
    Instead of training a custom NER/intent model (expensive, rigid),
    we use a foundation model (Gemini) with prompt engineering.

    Advantages:
      * Zero training data needed (few-shot in-context learning).
      * Handles novel phrasings the user throws at it.
      * Easy to iterate -- just change the prompt.

    Trade-offs:
      * Latency (~0.5-1.5s per call vs ~5ms for a local model).
      * Cost ($0.001-0.01 per call for Gemini Flash).
      * Requires API key & internet connectivity.

    We mitigate the risks with a rule-based fallback.
    """

    def __init__(self):
        self.api_key = os.environ.get("GOOGLE_API_KEY", "")
        self.llm = None
        self.chain = None
        self._llm_initialized = False
        # Start LLM init in background thread with timeout to prevent blocking
        self._init_llm_with_timeout(timeout_seconds=5)

    def _init_llm_with_timeout(self, timeout_seconds=5):
        """Initialise LLM in a separate thread with timeout to prevent blocking."""
        def _init_thread():
            self._init_llm()
            self._llm_initialized = True
        
        thread = threading.Thread(target=_init_thread, daemon=True)
        thread.start()
        thread.join(timeout=timeout_seconds)
        
        if thread.is_alive():
            print("[llm_engine] WARNING: LLM initialization timed out (>5s). Using rule-based fallback.")

    def _init_llm(self):
        """
        Initialise LangChain with Gemini.

        AI Concept: Chain Composition (LangChain Core)
        -----------------------------------------------
        LangChain composes:
          Prompt Template → LLM → Output Parser
        into a single "chain" that handles:
          * Message formatting (system + human)
          * API retry logic
          * JSON parsing + validation
        """
        if not self.api_key:
            print("[llm_engine] WARNING: GOOGLE_API_KEY not set. Using rule-based fallback.")
            return

        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            from langchain_core.prompts import ChatPromptTemplate
            from langchain_core.output_parsers import JsonOutputParser

            # ---------------------------------------------------------------
            # AI Concept: Model Selection
            # ---------------------------------------------------------------
            # Gemini 1.5 Flash is chosen for:
            #   * Low latency (~0.5s) -- critical for chatbot UX.
            #   * Strong JSON output compliance.
            #   * Cost-effective for high-volume extraction tasks.
            #   * Sufficient accuracy for entity extraction (no reasoning needed).
            self.llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                temperature=0.1,           # Low temp = deterministic extraction
                google_api_key=self.api_key,
            )

            # JSON output parser
            self.parser = JsonOutputParser(pydantic_object=FoodQuery)
            schema_str = json.dumps(FoodQuery.model_json_schema(), indent=2)

            # Build the prompt
            # Note: We use from_template with only {query} to avoid template parsing issues
            # The system prompt is pre-formatted with schema before passing to template
            system_msg = SYSTEM_PROMPT.replace("{schema}", schema_str)
            # Escape any double braces in the system message for template engine
            system_msg = system_msg.replace("{", "{{").replace("}", "}}")
            system_msg = system_msg.replace("{{\"", "{\"").replace("\"}}", "\"}")
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_msg),
                ("human", "{query}"),
            ])

            # Compose the chain: prompt → LLM → parser
            self.chain = prompt | self.llm | self.parser
            print("[llm_engine] LangChain + Gemini initialised successfully.")

        except ImportError as e:
            print(f"[llm_engine] LangChain/Gemini packages not installed: {e}")
            print("[llm_engine] Falling back to rule-based extraction.")
        except Exception as e:
            print(f"[llm_engine] LLM init error: {e}")
            print("[llm_engine] Falling back to rule-based extraction.")

    async def extract_query_params(self, user_query: str) -> dict:
        """
        Parse a natural language query into structured FoodQuery params.

        AI Concept: Hybrid NLU (LLM + Rules)
        --------------------------------------
        We try the LLM first (best quality). If it fails, we fall back
        to regex rules (always available, lower quality).  This
        "LLM + rules" pattern is standard in production NLU systems.

        Parameters
        ----------
        user_query : str
            Raw natural language input from the user.

        Returns
        -------
        dict : Parsed FoodQuery fields.
        """
        if self.chain:
            try:
                result = await self.chain.ainvoke({"query": user_query})
                # Validate with Pydantic
                parsed = FoodQuery(**result)
                return parsed.model_dump()
            except Exception as e:
                print(f"[llm_engine] LLM extraction failed: {e}")
                print("[llm_engine] Falling back to rule-based extraction.")

        # Fallback to rule-based extraction
        return self._rule_based_extract(user_query)

    def extract_query_params_sync(self, user_query: str) -> dict:
        """Synchronous version for non-async contexts."""
        if self.chain:
            try:
                result = self.chain.invoke({"query": user_query})
                parsed = FoodQuery(**result)
                return parsed.model_dump()
            except Exception as e:
                print(f"[llm_engine] LLM extraction failed: {e}")

        return self._rule_based_extract(user_query)

    # -----------------------------------------------------------------------
    # Rule-based fallback extractor
    # -----------------------------------------------------------------------

    def _rule_based_extract(self, query: str) -> dict:
        """
        Regex-based entity extraction fallback.

        AI Concept: Rule-Based NER
        ---------------------------
        Pattern matching on known keywords.  Less flexible than LLM
        (won't understand "I'm craving something fiery" → spicy),
        but has zero latency and zero cost.

        Production systems often start with rules, then upgrade to
        ML/LLM as traffic grows and edge cases are catalogued.
        """
        q = query.lower()
        result = FoodQuery()

        # Intent detection
        greetings = ["hello", "hi", "hey", "good morning", "good evening"]
        if any(g in q for g in greetings) and len(q.split()) <= 4:
            result.intent = "greeting"
            return result.model_dump()

        # Offers / deals intent
        offer_keywords = ["offer", "deal", "discount", "coupon", "promo", "sale",
                          "cashback", "bogo", "buy 1 get 1", "free delivery",
                          "combo deal", "today's deal", "special"]
        if any(k in q for k in offer_keywords):
            result.intent = "browse_offers"
        else:
            result.intent = "search_food"

        # Price extraction: "under 300", "below ₹500", "within 200"
        price_match = re.search(r'(?:under|below|within|less than|max|upto|up to)\s*[₹rs.]*\s*(\d+)', q)
        if price_match:
            result.price_limit = float(price_match.group(1))

        # Also check "₹300" standalone
        if not result.price_limit:
            price_match2 = re.search(r'[₹rs.]\s*(\d+)', q)
            if price_match2:
                result.price_limit = float(price_match2.group(1))

        # Cuisine detection
        cuisine_map = {
            "north indian": "North Indian", "south indian": "South Indian",
            "chinese": "Chinese", "biryani": "Biryani", "italian": "Italian",
            "continental": "Continental", "street food": "Street Food",
            "mughlai": "Mughlai", "dessert": "Desserts", "desserts": "Desserts",
            "healthy": "Healthy Bowls", "fast food": "Fast Food",
            "seafood": "Seafood", "burger": "Fast Food", "pizza": "Italian",
            "dosa": "South Indian", "idli": "South Indian",
        }
        for key, val in cuisine_map.items():
            if key in q:
                result.cuisine = val
                break

        # Diet type
        if any(w in q for w in ["vegan"]):
            result.diet_type = "vegan"
        elif any(w in q for w in ["vegetarian", "veg ", " veg", "veggie"]):
            result.diet_type = "veg"
        elif any(w in q for w in ["non-veg", "non veg", "chicken", "mutton", "fish", "prawn", "meat", "egg"]):
            result.diet_type = "non-veg"

        # Tags
        tag_keywords = {
            "spicy": "spicy", "healthy": "healthy", "light": "light",
            "comfort": "comfort", "protein": "protein-rich",
            "low calorie": "low-calorie", "low-calorie": "low-calorie",
            "keto": "keto", "gluten free": "gluten-free",
            "gluten-free": "gluten-free",
        }
        detected_tags = []
        for key, tag in tag_keywords.items():
            if key in q:
                detected_tags.append(tag)
        if detected_tags:
            result.tags = detected_tags

        # Location
        locations = [
            "kukatpally", "kphb", "madhapur", "gachibowli", "hitech city",
            "hitec city", "banjara hills", "jubilee hills", "kondapur",
            "ameerpet", "begumpet", "secunderabad", "dilsukhnagar",
            "lb nagar", "miyapur", "tolichowki", "mehdipatnam",
            "moosapet", "sr nagar",
        ]
        for loc in locations:
            if loc in q:
                result.location = loc.title()
                # Handle special cases
                if loc in ("hitec city", "hitech city"):
                    result.location = "Hitech City"
                elif loc == "kphb":
                    result.location = "KPHB"
                break

        # Meal time
        if any(w in q for w in ["breakfast", "morning"]):
            result.meal_time = "breakfast"
        elif any(w in q for w in ["lunch", "afternoon"]):
            result.meal_time = "lunch"
        elif any(w in q for w in ["dinner", "tonight", "evening"]):
            result.meal_time = "dinner"
        elif any(w in q for w in ["snack", "munch"]):
            result.meal_time = "snack"

        # Specific item
        items = [
            "biryani", "pizza", "burger", "dosa", "idli", "noodles",
            "pasta", "rice", "chicken", "mutton", "fish", "prawn",
            "samosa", "paratha", "roti", "naan", "paneer", "dal",
            "soup", "salad", "wrap", "sandwich", "cake", "brownie",
            "momos", "kebab", "tikka",
        ]
        for item in items:
            if item in q:
                result.specific_item = item
                break

        # Distance
        dist_match = re.search(r'(\d+)\s*(?:km|kilometer)', q)
        if dist_match:
            result.max_distance_km = float(dist_match.group(1))
        elif "near me" in q or "nearby" in q:
            result.max_distance_km = 5.0

        return result.model_dump()
