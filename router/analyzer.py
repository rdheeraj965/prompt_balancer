import re

class PromptAnalyzer:
    # Keywords indicating heavy reasoning, code generation, or architectural tasks
    COMPLEX_KEYWORDS = [
        "architect", "microservice", "infrastructure", "multi-file", 
        "database", "algorithm", "concurrency", "optimize", "system design"
    ]

    @classmethod
    def analyze(cls, prompt_text):
        # 1. Calculate approximate Token Volume (T)
        # A standard rule of thumb is 1 word ≈ 1.3 tokens
        word_count = len(prompt_text.split())
        estimated_tokens = int(word_count * 1.3)

        # 2. Calculate Complexity Score (S) ranging from 0.0 to 1.0
        complexity_score = 0.1  # Base score for any prompt
        
        # Increase score based on dense architectural keywords
        lower_prompt = prompt_text.lower()
        keyword_hits = sum(1 for word in cls.COMPLEX_KEYWORDS if word in lower_prompt)
        
        # Each hit adds 0.2 to the score, capped at 1.0
        complexity_score = min(1.0, complexity_score + (keyword_hits * 0.2))

        # If the prompt is very long, it inherently requires more reasoning
        if estimated_tokens > 500:
            complexity_score = min(1.0, complexity_score + 0.3)

        return {
            "token_volume": estimated_tokens,
            "complexity_score": round(complexity_score, 2)
        }