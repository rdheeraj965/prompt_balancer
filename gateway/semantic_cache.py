import json
import math
import re
import time
from typing import Optional, Dict, List
from django.conf import settings
from django.core.cache import cache


class SemanticCache:
    CACHE_KEY = "prompt_balancer:semantic_entries"
    MAX_ENTRIES = 100

    STOPWORDS = {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "in", "on", "at", "to", "for", "with", "by", "of", "and", "or",
        "me", "my", "please", "can", "you", "tell", "give", "what", "how",
    }

    @classmethod
    def _normalize(cls, text: str) -> str:
        cleaned = re.sub(r"[^\w\s\+\-\*/=]", " ", text.lower())
        return " ".join(cleaned.split())

    @classmethod
    def _get_embedding(cls, text: str) -> List[float]:
        normalized = cls._normalize(text)
        tokens = [t for t in normalized.split() if t not in cls.STOPWORDS] or normalized.split()

        # 512-dim deterministic hybrid vector:
        # [0..255]: Content word unigrams & bigrams (captures semantic keywords)
        # [256..511]: Character trigrams (captures morphological/spelling variations)
        vec = [0.0] * 512

        for i, tok in enumerate(tokens):
            idx = hash(f"w:{tok}") % 256
            vec[idx] += 2.0
            if i + 1 < len(tokens):
                bi_idx = hash(f"bi:{tok}_{tokens[i + 1]}") % 256
                vec[bi_idx] += 1.5

        joined_tokens = f" {' '.join(tokens)} "
        for i in range(len(joined_tokens) - 2):
            tri = joined_tokens[i : i + 3]
            tri_idx = 256 + (hash(f"tri:{tri}") % 256)
            vec[tri_idx] += 1.0

        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    @staticmethod
    def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
        if len(v1) != len(v2) or not v1:
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        if norm1 == 0.0 or norm2 == 0.0:
            return 0.0
        return dot / (norm1 * norm2)

    @classmethod
    def lookup(cls, prompt: str) -> Optional[Dict]:
        raw_entries = cache.get(cls.CACHE_KEY)
        if not raw_entries:
            return None

        entries = json.loads(raw_entries)
        norm_query = cls._normalize(prompt)
        query_vec = cls._get_embedding(prompt)

        best_match = None
        best_score = 0.0

        for entry in entries:
            if cls._normalize(entry.get("prompt", "")) == norm_query:
                return {
                    "response": entry["response"],
                    "original_tier": entry["tier"],
                    "similarity": 100.0,
                }

            score = cls._cosine_similarity(query_vec, entry.get("embedding", []))
            if score > best_score:
                best_score = score
                best_match = entry

        threshold = getattr(settings, "SEMANTIC_SIMILARITY_THRESHOLD", 0.85)
        if best_match and best_score >= threshold:
            return {
                "response": best_match["response"],
                "original_tier": best_match["tier"],
                "similarity": round(best_score * 100, 1),
            }
        return None

    @classmethod
    def store(cls, prompt: str, response_text: str, tier: str) -> None:
        if not response_text.strip():
            return
        raw_entries = cache.get(cls.CACHE_KEY)
        entries = json.loads(raw_entries) if raw_entries else []

        norm_prompt = cls._normalize(prompt)
        entries = [e for e in entries if cls._normalize(e.get("prompt", "")) != norm_prompt]

        entries.append({
            "prompt": prompt,
            "embedding": cls._get_embedding(prompt),
            "response": response_text,
            "tier": tier,
            "timestamp": time.time(),
        })

        entries = entries[-cls.MAX_ENTRIES :]
        cache.set(cls.CACHE_KEY, json.dumps(entries), timeout=86400)