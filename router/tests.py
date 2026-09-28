from django.test import TestCase
from router.analyzer import PromptAnalyzer
from router.engine import RoutingEngine

class RouterEngineTestCase(TestCase):
    
    def test_low_complexity_routing(self):
        """Simple prompts should route to Tier 1 (Local Light)"""
        prompt = "What is the capital of France?"
        tier, metrics = RoutingEngine.determine_tier(prompt)
        self.assertIn(tier, ["TIER_1_LOCAL_LIGHT", "TIER_2_LOCAL_HEAVY"])
        self.assertLess(metrics["complexity_score"], 0.3)

    def test_high_complexity_routing(self):
        """Architectural/coding prompts should trigger higher complexity scores"""
        prompt = "Architect a microservice with database connection pools and compare concurrency with Go."
        analysis = PromptAnalyzer.analyze(prompt)
        self.assertGreaterEqual(analysis["complexity_score"], 0.5)

    def test_token_volume_estimation(self):
        """Ensure token estimation correctly scales with word count"""
        prompt = "word " * 100
        analysis = PromptAnalyzer.analyze(prompt)
        self.assertGreaterEqual(analysis["token_volume"], 100)