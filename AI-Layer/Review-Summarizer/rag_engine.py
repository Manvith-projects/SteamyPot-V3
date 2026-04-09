"""
rag_engine.py — Retrieval-Augmented Generation (RAG) Engine
============================================================
Core of the review summarization system.

╔══════════════════════════════════════════════════════════════╗
║                    RAG PIPELINE OVERVIEW                     ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  1. EMBED     — Convert reviews → dense vector embeddings    ║
║  2. INDEX     — Store embeddings in FAISS vector database    ║
║  3. RETRIEVE  — Find most relevant review clusters           ║
║  4. GENERATE  — LLM summarizes retrieved context             ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝

WHY EMBEDDINGS?
  Embeddings capture the SEMANTIC MEANING of reviews, not just keywords.
  - "Food was delicious" and "Meals are tasty" have different words
    but similar embeddings → grouped together in vector space.
  - This lets us find THEMATIC CLUSTERS of feedback (e.g., all reviews
    about delivery speed) even if they use different vocabulary.
  - Traditional keyword search would miss these semantic connections.

WHY RAG INSTEAD OF JUST SENDING ALL REVIEWS TO THE LLM?
  - LLMs have context window limits — 200 reviews could exceed them.
  - Not all reviews are equally informative — RAG retrieves the MOST
    RELEVANT and DIVERSE review chunks, reducing noise.
  - Embeddings + retrieval lets us pick reviews that cover different
    topics (food quality, delivery, pricing) for a balanced summary.
  - It's more cost-effective: fewer tokens sent to the LLM.

WHY FAISS?
  - Fast Approximate Nearest Neighbor search — handles thousands of
    vectors efficiently.
  - In-memory, no separate server process needed.
  - Perfect for per-request ephemeral vector stores (we rebuild per
    restaurant since reviews change over time).
"""

import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# LangChain imports for the RAG pipeline
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

# Google Generative AI (Gemini) for LLM only
from langchain_google_genai import ChatGoogleGenerativeAI

# HuggingFace embeddings — free, runs locally, no API key needed
# Uses sentence-transformers/all-MiniLM-L6-v2 (384-dim vectors)
# This model maps sentences to a dense vector space where semantically
# similar texts are close together — perfect for clustering reviews.
from langchain_huggingface import HuggingFaceEmbeddings

# FAISS vector store via LangChain community
from langchain_community.vectorstores import FAISS

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# Embedding model — HuggingFace's all-MiniLM-L6-v2 produces 384-dim vectors
# that capture semantic meaning of text. Runs 100% locally, FREE, no API key.
# Ideal for clustering reviews by topic (food quality, delivery, price, etc.)
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# LLM for final summary generation
# Using gemini-2.0-flash-lite — separate free-tier quota from the main flash models.
# If one model's daily quota is exhausted, we fall back to a different model family.
LLM_MODEL = "gemini-2.0-flash-lite"
LLM_FALLBACK_MODEL = "gemini-2.5-flash-lite"  # Backup if primary hits rate limit
LLM_TEMPERATURE = 0.3  # Slightly creative but mostly factual
MAX_RETRIES = 1        # Quick retry, then fall back to statistical summary

# How many review chunks to retrieve for the LLM context
TOP_K_CHUNKS = 30  # Enough for diverse coverage without overwhelming the LLM

# How many reviews per chunk — we group reviews into chunks of 5
# so each "document" in the vector store represents a mini-cluster
REVIEWS_PER_CHUNK = 5
CACHE_TTL_SECONDS = 24 * 60 * 60
CACHE_DIR = Path(__file__).resolve().parent / "cache" / "vectors"


# ---------------------------------------------------------------------------
# Review Chunking
# ---------------------------------------------------------------------------

def chunk_reviews(reviews: list[dict], chunk_size: int = REVIEWS_PER_CHUNK) -> list[Document]:
    """
    Group reviews into chunks and convert to LangChain Documents.

    WHY CHUNK?
      - Individual reviews are often too short for meaningful embeddings.
      - Grouping 5 reviews together creates richer semantic vectors.
      - Each chunk captures a "micro-theme" from multiple reviewers.
      - Reduces the number of vectors in FAISS → faster retrieval.

    Each Document contains:
      - page_content: The combined review texts
      - metadata: Average rating, review count, rating range

    Parameters
    ----------
    reviews : list[dict]
        Preprocessed reviews with 'review_text' and 'rating' keys.
    chunk_size : int
        Number of reviews per chunk.

    Returns
    -------
    list[Document]
        LangChain Document objects ready for embedding.
    """
    documents = []

    for i in range(0, len(reviews), chunk_size):
        chunk = reviews[i : i + chunk_size]

        # Combine review texts with rating context
        texts = []
        ratings = []
        for r in chunk:
            texts.append(f"[{r['rating']}★] {r['review_text']}")
            ratings.append(r["rating"])

        combined_text = "\n".join(texts)
        avg_rating = sum(ratings) / len(ratings) if ratings else 0

        doc = Document(
            page_content=combined_text,
            metadata={
                "avg_rating": round(avg_rating, 2),
                "review_count": len(chunk),
                "min_rating": min(ratings) if ratings else 0,
                "max_rating": max(ratings) if ratings else 0,
                "chunk_index": i // chunk_size,
            },
        )
        documents.append(doc)

    return documents


# ---------------------------------------------------------------------------
# RAG Engine
# ---------------------------------------------------------------------------

class RAGEngine:
    """
    Retrieval-Augmented Generation engine for review summarization.

    Pipeline:
      reviews → chunk → embed → FAISS index → retrieve top-K → LLM → summary

    The engine stores a FAISS index per restaurant and refreshes it once
    per day to avoid rebuilding embeddings on every request.
    """

    def __init__(self):
        """Initialize the embedding model and LLM."""

        # ── Embedding Model ──────────────────────────────────────────
        # HuggingFace's all-MiniLM-L6-v2 maps text → 384-dimensional vectors.
        # Reviews with similar meaning end up close together in this
        # high-dimensional space, enabling semantic search.
        # Runs locally on CPU — FREE, no API key needed, no rate limits.
        self.embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},  # L2 normalize for cosine similarity
        )

        # ── LLM (Gemini 1.5 Flash) ──────────────────────────────────
        # Used in the GENERATION step to synthesize retrieved review
        # chunks into a coherent, structured summary.
        # We keep a fallback model in case the primary hits rate limits.
        self.llm = ChatGoogleGenerativeAI(
            model=LLM_MODEL,
            google_api_key=GOOGLE_API_KEY,
            temperature=LLM_TEMPERATURE,
        )
        self.llm_fallback = ChatGoogleGenerativeAI(
            model=LLM_FALLBACK_MODEL,
            google_api_key=GOOGLE_API_KEY,
            temperature=LLM_TEMPERATURE,
        )

        # ── Output Parser ────────────────────────────────────────────
        # Ensures the LLM output is valid JSON matching our schema.
        self.output_parser = JsonOutputParser()

        # ── Prompt Template ──────────────────────────────────────────
        # The prompt instructs the LLM to analyze retrieved review chunks
        # and produce a structured summary with sentiment analysis.
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", "{query}"),
        ])

        # ── LangChain Chain ──────────────────────────────────────────
        # Compose: prompt → LLM → JSON parser
        self.chain = self.prompt | self.llm | self.output_parser

        self._active = bool(GOOGLE_API_KEY)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def is_active(self) -> bool:
        """Check if the engine has a valid API key."""
        return self._active

    async def summarize(
        self,
        restaurant_id: str,
        reviews: list[dict],
        restaurant_name: str = "the restaurant",
        avg_rating: float = 0.0,
        rating_distribution: Optional[dict] = None,
        max_reviews: int = 200,
    ) -> dict:
        """
        Run the full RAG pipeline to summarize reviews.

        Steps:
          1. CHUNK   — Group reviews into semantic chunks
          2. EMBED   — Convert chunks to vector embeddings
          3. INDEX   — Build a FAISS vector store
          4. RETRIEVE — Find the most relevant/diverse chunks
          5. GENERATE — Send context to Gemini for summarization

        Parameters
        ----------
        reviews : list[dict]
            Preprocessed reviews (after dedup + spam removal).
        restaurant_name : str
            Name of the restaurant (for context in the prompt).
        avg_rating : float
            Average rating from MongoDB aggregation.
        rating_distribution : dict
            Count of reviews per star rating.

        Returns
        -------
        dict with keys:
            summary, top_positive_points, common_complaints,
            overall_sentiment
        """
        if not reviews:
            return _empty_summary("No reviews available for this restaurant.")

        if not self._active:
            fallback = _statistical_summary(reviews, restaurant_name, avg_rating, rating_distribution)
            fallback.update(self._summary_cache_info_from_metadata("bypassed", None))
            return fallback

        review_signature = self._reviews_signature(reviews, max_reviews)
        cached_summary = await asyncio.to_thread(
            self._load_cached_summary,
            restaurant_id,
            max_reviews,
            review_signature,
        )
        vector_cache_info = await asyncio.to_thread(self._read_vector_cache_info, restaurant_id)

        if cached_summary is not None:
            summary_data, summary_meta = cached_summary
            response = dict(summary_data)
            response.update(vector_cache_info)
            response.update(self._summary_cache_info_from_metadata("cached", summary_meta))
            return response

        try:
            vectorstore, cache_info = await self._get_or_build_vectorstore(
                restaurant_id=restaurant_id,
                reviews=reviews,
                restaurant_name=restaurant_name,
            )
        except Exception as e:
            return _empty_summary(f"Embedding/indexing failed: {str(e)}")

        # ─── Step 4: RETRIEVE relevant chunks ───────────────────────
        # We use multiple queries to get diverse coverage:
        #   - "positive feedback" → pulls chunks about good experiences
        #   - "negative complaints" → pulls chunks about problems
        #   - "food quality"       → pulls food-specific feedback
        #   - "delivery experience" → pulls delivery-related reviews
        #   - "value and pricing"  → pulls price-related feedback
        #
        # This multi-query approach ensures the summary covers ALL aspects
        # of the restaurant, not just the dominant sentiment.
        retrieval_queries = [
            "positive feedback and best dishes",
            "negative complaints and problems",
            "food quality taste and freshness",
            "delivery speed and packaging",
            "value for money and pricing",
            "overall customer experience and service",
        ]

        # Collect unique chunks across all queries
        retrieved_docs = {}
        chunks_per_query = max(TOP_K_CHUNKS // len(retrieval_queries), 3)

        for query in retrieval_queries:
            try:
                results = await asyncio.to_thread(
                    vectorstore.similarity_search, query, k=chunks_per_query
                )
                for doc in results:
                    # Deduplicate by chunk content
                    key = doc.page_content[:100]
                    if key not in retrieved_docs:
                        retrieved_docs[key] = doc
            except Exception:
                continue

        if not retrieved_docs:
            return _empty_summary("Review retrieval failed — no matching chunks found.")

        # ─── Step 5: GENERATE summary ────────────────────────────────
        # Combine retrieved chunks into a single context block and send
        # to Gemini with structured instructions for summarization.
        retrieved_list = list(retrieved_docs.values())

        # Build context string from retrieved chunks
        context_parts = []
        for i, doc in enumerate(retrieved_list, 1):
            avg_r = doc.metadata.get("avg_rating", "?")
            context_parts.append(
                f"--- Chunk {i} (avg rating: {avg_r}★) ---\n{doc.page_content}"
            )
        context_text = "\n\n".join(context_parts)

        # Build the rating summary for additional context
        dist_str = ""
        if rating_distribution:
            dist_str = ", ".join(
                f"{stars}★: {count}" for stars, count in sorted(rating_distribution.items())
            )

        query_text = (
            f"Restaurant: {restaurant_name}\n"
            f"Average Rating: {avg_rating}★\n"
            f"Rating Distribution: {dist_str}\n"
            f"Total Reviews Analyzed: {len(reviews)}\n"
            f"Retrieved Review Chunks ({len(retrieved_list)} chunks):\n\n"
            f"{context_text}"
        )

        try:
            result = await self._invoke_with_retry(query_text)

            # Validate and normalize the result
            normalized = _normalize_summary(result)
            normalized.update(cache_info)
            summary_meta = self._save_cached_summary(
                restaurant_id,
                max_reviews,
                review_signature,
                normalized,
            )
            normalized.update(self._summary_cache_info_from_metadata("built", summary_meta))
            return normalized

        except Exception as e:
            # Fallback: try a simpler prompt
            try:
                normalized = await self._fallback_summarize(reviews, restaurant_name)
                normalized.update(cache_info)
                summary_meta = self._save_cached_summary(
                    restaurant_id,
                    max_reviews,
                    review_signature,
                    normalized,
                )
                normalized.update(self._summary_cache_info_from_metadata("built", summary_meta))
                return normalized
            except Exception:
                fallback = _statistical_summary(reviews, restaurant_name, avg_rating, rating_distribution)
                fallback.update(cache_info)
                summary_meta = self._save_cached_summary(
                    restaurant_id,
                    max_reviews,
                    review_signature,
                    fallback,
                )
                fallback.update(self._summary_cache_info_from_metadata("built", summary_meta))
                return fallback

    async def prime_cache_entries(self, entries: list[dict]) -> dict:
        """Warm restaurant vector indexes so requests can reuse them."""
        built = 0
        reused = 0

        for entry in entries:
            try:
                _, cache_info = await self._get_or_build_vectorstore(
                    restaurant_id=entry["restaurant_id"],
                    reviews=entry["reviews"],
                    restaurant_name=entry.get("restaurant_name", "the restaurant"),
                )
                if cache_info.get("cache_status") == "built":
                    built += 1
                else:
                    reused += 1
            except Exception:
                continue

        return {"built": built, "reused": reused, "total": len(entries)}

    async def _get_or_build_vectorstore(
        self,
        restaurant_id: str,
        reviews: list[dict],
        restaurant_name: str,
    ):
        cached = await asyncio.to_thread(self._load_cached_vectorstore, restaurant_id)
        if cached is not None:
            vectorstore, metadata = cached
            return vectorstore, self._cache_info_from_metadata("cached", metadata)

        documents = chunk_reviews(reviews)
        if not documents:
            raise ValueError("No valid review chunks could be created.")

        vectorstore = await asyncio.to_thread(FAISS.from_documents, documents, self.embeddings)
        metadata = {
            "restaurant_id": restaurant_id,
            "restaurant_name": restaurant_name,
            "review_count": len(reviews),
            "chunk_count": len(documents),
            "built_at": datetime.now(timezone.utc).isoformat(),
        }
        await asyncio.to_thread(self._save_cached_vectorstore, restaurant_id, vectorstore, metadata)
        return vectorstore, self._cache_info_from_metadata("built", metadata)

    def _restaurant_cache_dir(self, restaurant_id: str) -> Path:
        safe_id = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in restaurant_id)
        return CACHE_DIR / safe_id

    def _metadata_path(self, restaurant_id: str) -> Path:
        return self._restaurant_cache_dir(restaurant_id) / "meta.json"

    def _summary_cache_path(self, restaurant_id: str, max_reviews: int) -> Path:
        return self._restaurant_cache_dir(restaurant_id) / f"summary_{max_reviews}.json"

    def _load_cached_vectorstore(self, restaurant_id: str):
        cache_dir = self._restaurant_cache_dir(restaurant_id)
        meta_path = self._metadata_path(restaurant_id)

        if not cache_dir.exists() or not meta_path.exists():
            return None

        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            built_at = datetime.fromisoformat(metadata["built_at"])
            age_seconds = (datetime.now(timezone.utc) - built_at).total_seconds()
            if age_seconds > CACHE_TTL_SECONDS:
                return None

            vectorstore = FAISS.load_local(
                str(cache_dir),
                self.embeddings,
                allow_dangerous_deserialization=True,
            )
            return vectorstore, metadata
        except Exception:
            return None

    def _save_cached_vectorstore(self, restaurant_id: str, vectorstore, metadata: dict):
        cache_dir = self._restaurant_cache_dir(restaurant_id)
        cache_dir.mkdir(parents=True, exist_ok=True)
        vectorstore.save_local(str(cache_dir))
        self._metadata_path(restaurant_id).write_text(
            json.dumps(metadata, indent=2),
            encoding="utf-8",
        )

    def _cache_info_from_metadata(self, status: str, metadata: dict) -> dict:
        built_at = metadata.get("built_at")
        age_hours = None

        if built_at:
            try:
                built_dt = datetime.fromisoformat(built_at)
                age_hours = round((datetime.now(timezone.utc) - built_dt).total_seconds() / 3600, 2)
            except Exception:
                age_hours = None

        return {
            "cache_status": status,
            "cache_refreshed_at": built_at,
            "cache_age_hours": age_hours,
        }

    def _read_vector_cache_info(self, restaurant_id: str) -> dict:
        meta_path = self._metadata_path(restaurant_id)
        if not meta_path.exists():
            return self._cache_info_from_metadata("missing", None)

        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            built_at = datetime.fromisoformat(metadata["built_at"])
            age_seconds = (datetime.now(timezone.utc) - built_at).total_seconds()
            status = "cached" if age_seconds <= CACHE_TTL_SECONDS else "stale"
            return self._cache_info_from_metadata(status, metadata)
        except Exception:
            return self._cache_info_from_metadata("missing", None)

    def _reviews_signature(self, reviews: list[dict], max_reviews: int) -> str:
        digest = hashlib.sha256()
        digest.update(str(max_reviews).encode("utf-8"))

        for review in reviews:
            digest.update(str(review.get("rating", "")).encode("utf-8"))
            digest.update(str(review.get("timestamp", "")).encode("utf-8"))
            digest.update(str(review.get("review_text", "")).encode("utf-8"))

        return digest.hexdigest()

    def _load_cached_summary(self, restaurant_id: str, max_reviews: int, review_signature: str):
        summary_path = self._summary_cache_path(restaurant_id, max_reviews)
        if not summary_path.exists():
            return None

        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            metadata = payload.get("metadata", {})
            built_at = datetime.fromisoformat(metadata["built_at"])
            age_seconds = (datetime.now(timezone.utc) - built_at).total_seconds()

            if age_seconds > CACHE_TTL_SECONDS:
                return None
            if metadata.get("review_signature") != review_signature:
                return None

            return payload.get("summary", {}), metadata
        except Exception:
            return None

    def _save_cached_summary(
        self,
        restaurant_id: str,
        max_reviews: int,
        review_signature: str,
        summary: dict,
    ) -> dict:
        summary_path = self._summary_cache_path(restaurant_id, max_reviews)
        summary_path.parent.mkdir(parents=True, exist_ok=True)

        metadata = {
            "built_at": datetime.now(timezone.utc).isoformat(),
            "review_signature": review_signature,
            "max_reviews": max_reviews,
        }
        payload = {
            "metadata": metadata,
            "summary": {
                "summary": summary.get("summary", "Summary not available."),
                "top_positive_points": list(summary.get("top_positive_points", [])),
                "common_complaints": list(summary.get("common_complaints", [])),
                "overall_sentiment": summary.get("overall_sentiment", "unknown"),
            },
        }
        summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return metadata

    def _summary_cache_info_from_metadata(self, status: str, metadata: Optional[dict]) -> dict:
        built_at = metadata.get("built_at") if metadata else None
        age_hours = None

        if built_at:
            try:
                built_dt = datetime.fromisoformat(built_at)
                age_hours = round((datetime.now(timezone.utc) - built_dt).total_seconds() / 3600, 2)
            except Exception:
                age_hours = None

        return {
            "summary_cache_status": status,
            "summary_cache_refreshed_at": built_at,
            "summary_cache_age_hours": age_hours,
        }

    async def _invoke_with_retry(self, query_text: str) -> dict:
        """
        Invoke the LLM chain with retry + model fallback on 429 errors.

        Strategy:
          1. Try primary model (gemini-1.5-flash) up to MAX_RETRIES times
          2. If all retries fail with 429, try fallback model once
          3. Exponential backoff: 2s, 4s, 8s between retries
        """
        last_error = None

        # Try primary model with retries
        for attempt in range(MAX_RETRIES):
            try:
                return await self.chain.ainvoke({"query": query_text})
            except Exception as e:
                last_error = e
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    wait = 2  # Short fixed wait
                    print(f"[RAG] Rate limited on {LLM_MODEL}, retry {attempt+1}/{MAX_RETRIES} in {wait}s...")
                    await asyncio.sleep(wait)
                else:
                    raise  # Non-rate-limit errors fail immediately

        # Primary exhausted — try fallback model
        print(f"[RAG] Primary model exhausted, trying fallback: {LLM_FALLBACK_MODEL}")
        fallback_chain = self.prompt | self.llm_fallback | self.output_parser
        try:
            return await fallback_chain.ainvoke({"query": query_text})
        except Exception:
            raise last_error  # Raise the original error if fallback also fails

    async def _fallback_summarize(
        self, reviews: list[dict], restaurant_name: str
    ) -> dict:
        """
        Fallback summarization without RAG — sends a sample of reviews
        directly to the LLM. Used when the full pipeline fails.
        """
        # Take a sample of 50 reviews
        sample = reviews[:50]
        review_texts = "\n".join(
            f"[{r['rating']}★] {r['review_text']}" for r in sample
        )

        fallback_prompt = ChatPromptTemplate.from_messages([
            ("system", FALLBACK_SYSTEM_PROMPT),
            ("human", f"Restaurant: {restaurant_name}\n\nReviews:\n{review_texts}"),
        ])

        chain = fallback_prompt | self.llm | self.output_parser
        result = await chain.ainvoke({})
        return _normalize_summary(result)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert restaurant review analyst. Your job is to analyze 
retrieved review chunks from a vector database and produce a comprehensive summary.

CONTEXT:
You are part of a Retrieval-Augmented Generation (RAG) pipeline. The reviews below were 
retrieved using semantic similarity search — they represent the most relevant and diverse 
feedback for this restaurant across multiple dimensions (food quality, delivery, pricing, etc.).

INSTRUCTIONS:
1. Analyze ALL the retrieved review chunks carefully.
2. Identify recurring themes in POSITIVE feedback.
3. Identify recurring themes in NEGATIVE feedback / complaints.
4. Determine the overall sentiment based on the balance of positive vs negative reviews 
   AND the average rating.
5. Write a concise, informative summary (2-4 sentences) that a customer would find helpful.

OUTPUT FORMAT — Return ONLY valid JSON:
{{
  "summary": "A 2-4 sentence summary covering the restaurant's strengths, weaknesses, and overall quality. Write in third person.",
  "top_positive_points": ["Point 1", "Point 2", "Point 3"],
  "common_complaints": ["Complaint 1", "Complaint 2"],
  "overall_sentiment": "positive | mixed | negative"
}}

RULES:
- "top_positive_points" should have 2-5 items, each a short phrase.
- "common_complaints" should have 1-4 items. If no complaints, use ["No significant complaints"].
- "overall_sentiment" must be exactly one of: "positive", "mixed", or "negative".
- Base sentiment on the ACTUAL review content, not just the average rating.
- Be specific — mention actual dishes, delivery issues, etc. when the reviews mention them.
- Do NOT invent information not present in the reviews.
- Return ONLY the JSON object, no markdown formatting, no code blocks."""

FALLBACK_SYSTEM_PROMPT = """You are a restaurant review summarizer. Analyze these reviews and 
produce a JSON summary.

Return ONLY valid JSON with these keys:
{{
  "summary": "2-4 sentence summary",
  "top_positive_points": ["point1", "point2"],
  "common_complaints": ["complaint1"],
  "overall_sentiment": "positive | mixed | negative"
}}

Rules:
- Be concise and factual.
- Base analysis only on the provided reviews.
- Return ONLY JSON, no extra text."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_summary(reason: str) -> dict:
    """Return an empty summary structure with a reason message."""
    return {
        "summary": reason,
        "top_positive_points": [],
        "common_complaints": [],
        "overall_sentiment": "unknown",
    }


def _statistical_summary(
    reviews: list[dict],
    restaurant_name: str = "the restaurant",
    avg_rating: float = 0.0,
    rating_distribution: Optional[dict] = None,
) -> dict:
    """Generate a summary using statistics when the LLM is unavailable."""
    if not reviews:
        return _empty_summary("No reviews available.")

    total = len(reviews)
    positive = [r for r in reviews if r.get("rating", 0) >= 4]
    negative = [r for r in reviews if r.get("rating", 0) <= 2]
    neutral = [r for r in reviews if r.get("rating", 0) == 3]

    pos_pct = len(positive) / total * 100
    neg_pct = len(negative) / total * 100

    if pos_pct >= 60:
        sentiment = "positive"
    elif neg_pct >= 40:
        sentiment = "negative"
    else:
        sentiment = "mixed"

    summary = (
        f"{restaurant_name} has {total} reviews with an average rating of {avg_rating}\u2605. "
        f"{len(positive)} positive, {len(neutral)} neutral, and {len(negative)} negative reviews. "
    )
    if sentiment == "positive":
        summary += "Customers generally praise the food quality and taste."
    elif sentiment == "negative":
        summary += "Several customers reported issues with food quality or delivery."
    else:
        summary += "Customer opinions are mixed across food quality, delivery, and pricing."

    top_positive = []
    if positive:
        top_positive = list({r["review_text"][:60] for r in positive[:5]})

    complaints = []
    if negative:
        complaints = list({r["review_text"][:60] for r in negative[:4]})
    if not complaints:
        complaints = ["No significant complaints"]

    return {
        "summary": summary,
        "top_positive_points": top_positive[:5],
        "common_complaints": complaints[:4],
        "overall_sentiment": sentiment,
    }


def _normalize_summary(result: dict) -> dict:
    """Ensure the summary dict has all required keys with correct types."""
    return {
        "summary": str(result.get("summary", "Summary not available.")),
        "top_positive_points": list(result.get("top_positive_points", [])),
        "common_complaints": list(result.get("common_complaints", [])),
        "overall_sentiment": str(result.get("overall_sentiment", "unknown")).lower(),
    }


# ---------------------------------------------------------------------------
# Module-level test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    async def _test():
        engine = RAGEngine()
        print(f"RAG Engine active: {engine.is_active}")

        # Test with dummy reviews
        test_reviews = [
            {"review_text": "Amazing biryani! Best I've ever had.", "rating": 5},
            {"review_text": "Food was great but delivery took too long.", "rating": 3},
            {"review_text": "Terrible experience. Food was cold and tasteless.", "rating": 1},
            {"review_text": "Love the butter chicken here. Always fresh.", "rating": 5},
            {"review_text": "Portions are too small for the price.", "rating": 2},
            {"review_text": "Consistently good quality. My favorite restaurant.", "rating": 5},
            {"review_text": "Naan was hard and stale. Disappointing.", "rating": 2},
            {"review_text": "Fast delivery and hot food. Happy customer!", "rating": 4},
            {"review_text": "Average food, nothing special about it.", "rating": 3},
            {"review_text": "The paneer tikka is absolutely incredible.", "rating": 5},
        ]

        result = await engine.summarize(
            test_reviews,
            restaurant_name="Spice Garden",
            avg_rating=3.5,
            rating_distribution={1: 1, 2: 2, 3: 2, 4: 1, 5: 4},
        )
        import json
        print(json.dumps(result, indent=2))

    asyncio.run(_test())
