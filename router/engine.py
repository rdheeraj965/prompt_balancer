from router.analyzer import PromptAnalyzer
from router.monitor import SystemMonitor

class RoutingEngine:
    # Threshold constants
    MAX_LOCAL_TOKENS = 1000
    HIGH_COMPLEXITY_THRESHOLD = 0.7
    MODERATE_COMPLEXITY_THRESHOLD = 0.3

    @classmethod
    def determine_tier(cls, prompt_text):
        analysis = PromptAnalyzer.analyze(prompt_text)
        health = SystemMonitor.check_local_health()

        s_score = analysis["complexity_score"]
        t_volume = analysis["token_volume"]
        gpu_ok = health["vram_available"]

        # Matrix Rule 3: Extreme Complexity or Token limits exceeded -> Cloud Heavy
        if s_score >= cls.HIGH_COMPLEXITY_THRESHOLD and t_volume > 2000:
            return "TIER_3_CLOUD_HEAVY", analysis
            
        # Matrix Rule 2: Heavy workload, but local GPU is busy -> Cloud Light Fallback
        if (s_score >= cls.MODERATE_COMPLEXITY_THRESHOLD or t_volume > cls.MAX_LOCAL_TOKENS) and not gpu_ok:
            return "TIER_2_CLOUD_LIGHT", analysis

        # Matrix Rule 1: Simple task, low tokens -> Local Light
        return "TIER_1_LOCAL_LIGHT", analysis