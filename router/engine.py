from router.analyzer import PromptAnalyzer
from router.monitor import SystemMonitor

class RoutingEngine:
    MAX_LOCAL_TOKENS = 800
    HIGH_COMPLEXITY_THRESHOLD = 0.65
    MODERATE_COMPLEXITY_THRESHOLD = 0.30

    @classmethod
    def determine_tier(cls, prompt_text: str, history_tokens: int = 0):
        analysis = PromptAnalyzer.analyze(prompt_text)
        health = SystemMonitor.check_local_health()

        s_score = analysis["complexity_score"]
        total_tokens = analysis["token_volume"] + history_tokens
        analysis["total_context_tokens"] = total_tokens
        analysis["hardware"] = health

        # Tier 3 (Cloud Heavy): High complexity reasoning OR massive multi-turn context
        if s_score >= cls.HIGH_COMPLEXITY_THRESHOLD or total_tokens > 2500:
            return "TIER_3_CLOUD_HEAVY", analysis

        # Tier 2 (Cloud Light): Moderate complexity, exceeds local context window, OR local hardware overloaded
        if (
            s_score >= cls.MODERATE_COMPLEXITY_THRESHOLD
            or total_tokens > cls.MAX_LOCAL_TOKENS
            or not health["healthy"]
        ):
            return "TIER_2_CLOUD_LIGHT", analysis

        # Tier 1 (Local Light): Low complexity, small context, healthy local hardware
        return "TIER_1_LOCAL_LIGHT", analysis