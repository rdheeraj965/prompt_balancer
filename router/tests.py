from unittest.mock import patch
from django.test import TestCase, Client, override_settings
from django.core.cache import cache

from gateway.pii_masker import PIIMasker
from gateway.semantic_cache import SemanticCache
from gateway.memory import ConversationMemory
from router.monitor import SystemMonitor
from router.engine import RoutingEngine


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "prompt-balancer-test-cache",
        }
    }
)
class PromptBalancerFeatureTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()

    # ---------------------------------------------------------
    # 1. PII Data Masking (DLP) Tests
    # ---------------------------------------------------------
    def test_pii_masker_redacts_sensitive_entities(self):
        raw_prompt = (
            "Contact dheeraj@example.com or call 987-654-3210. "
            "Server IP is 192.168.1.45 and key is AIzaSyDummyKey1234567890123456789012345."
        )
        sanitized, detected = PIIMasker.sanitize(raw_prompt)

        self.assertIn("[EMAIL_REDACTED]", sanitized)
        self.assertIn("[PHONE_REDACTED]", sanitized)
        self.assertIn("[IP_ADDRESS_REDACTED]", sanitized)
        self.assertIn("[API_KEY_REDACTED]", sanitized)
        self.assertNotIn("dheeraj@example.com", sanitized)
        self.assertNotIn("987-654-3210", sanitized)
        self.assertEqual(len(detected), 4)

    def test_pii_masker_leaves_clean_prompt_untouched(self):
        clean_prompt = "Explain how a binary search tree balances nodes."
        sanitized, detected = PIIMasker.sanitize(clean_prompt)

        self.assertEqual(sanitized, clean_prompt)
        self.assertEqual(detected, [])

    # ---------------------------------------------------------
    # 2. Semantic Caching Tests
    # ---------------------------------------------------------
    @patch("gateway.semantic_cache.requests.post", side_effect=Exception("Offline mode"))
    def test_semantic_cache_hit_and_miss(self, _mock_post):
        # Store initial query
        SemanticCache.store(
            prompt="What is Docker containerization?",
            response_text="Docker packages applications into lightweight containers.",
            tier="TIER_1_LOCAL_LIGHT",
        )

        # Near-identical phrasing should trigger a semantic cache hit
        hit = SemanticCache.lookup("what is docker containerization")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["original_tier"], "TIER_1_LOCAL_LIGHT")
        self.assertGreaterEqual(hit["similarity"], 90.0)

        # Completely unrelated query should miss
        miss = SemanticCache.lookup("Write a SQL query to join three tables.")
        self.assertIsNone(miss)

    # ---------------------------------------------------------
    # 3. Multi-Turn Conversation Memory Tests
    # ---------------------------------------------------------
    def test_conversation_memory_persistence_and_windowing(self):
        session_id = "test-session-101"
        for i in range(8):
            ConversationMemory.append_turn(session_id, f"Question {i}", f"Answer {i}")

        history = ConversationMemory.get_history(session_id)
        # Capped at MAX_MESSAGES = 12 (last 6 user-assistant pairs)
        self.assertEqual(len(history), 12)
        self.assertEqual(history[0]["content"], "Question 2")
        self.assertEqual(history[-1]["content"], "Answer 7")
        self.assertGreater(ConversationMemory.estimate_history_tokens(history), 0)

        ConversationMemory.clear(session_id)
        self.assertEqual(ConversationMemory.get_history(session_id), [])

    # ---------------------------------------------------------
    # 4. System Health Monitor Tests
    # ---------------------------------------------------------
    @patch.object(SystemMonitor, "_check_ollama_alive", return_value=True)
    @patch.object(SystemMonitor, "_check_gpu_vram", return_value={"available": True, "used_mb": 2000, "total_mb": 8192, "percent": 24.4})
    @patch("router.monitor.psutil.virtual_memory")
    @patch("router.monitor.psutil.cpu_percent", return_value=18.5)
    def test_system_monitor_healthy_state(self, _cpu, mock_vm, _gpu, _ollama):
        mock_vm.return_value.percent = 45.0
        health = SystemMonitor.check_local_health()

        self.assertTrue(health["healthy"])
        self.assertEqual(health["reason"], "Healthy")
        self.assertEqual(health["ram_percent"], 45.0)

    @patch.object(SystemMonitor, "_check_ollama_alive", return_value=True)
    @patch.object(SystemMonitor, "_check_gpu_vram", return_value={"available": False, "used_mb": 0, "total_mb": 0, "percent": 0.0})
    @patch("router.monitor.psutil.virtual_memory")
    @patch("router.monitor.psutil.cpu_percent", return_value=72.0)
    def test_system_monitor_degraded_on_high_ram(self, _cpu, mock_vm, _gpu, _ollama):
        mock_vm.return_value.percent = 92.5
        health = SystemMonitor.check_local_health()

        self.assertFalse(health["healthy"])
        self.assertIn("High System RAM", health["reason"])

    # ---------------------------------------------------------
    # 5. 3-Tier Routing Engine Tests
    # ---------------------------------------------------------
    @patch.object(SystemMonitor, "check_local_health", return_value={"healthy": True, "reason": "Healthy"})
    def test_routing_tier1_local_when_simple_and_healthy(self, _health):
        tier, metrics = RoutingEngine.determine_tier("Define REST API in one line.")
        self.assertEqual(tier, "TIER_1_LOCAL_LIGHT")
        self.assertLess(metrics["complexity_score"], 0.30)

    @patch.object(SystemMonitor, "check_local_health", return_value={"healthy": False, "reason": "High System RAM"})
    def test_routing_bypasses_local_to_tier2_when_hardware_overloaded(self, _health):
        tier, _metrics = RoutingEngine.determine_tier("Define REST API in one line.")
        self.assertEqual(tier, "TIER_2_CLOUD_LIGHT")

    @patch.object(SystemMonitor, "check_local_health", return_value={"healthy": True, "reason": "Healthy"})
    def test_routing_escalates_to_tier3_on_high_complexity_or_long_history(self, _health):
        complex_prompt = "Architect a distributed microservice database system and optimize concurrency algorithms."
        tier_complex, _ = RoutingEngine.determine_tier(complex_prompt)
        self.assertEqual(tier_complex, "TIER_3_CLOUD_HEAVY")

        # Even a short follow-up escalates if conversation history exceeds 2500 tokens
        tier_long_ctx, _ = RoutingEngine.determine_tier("Summarize that.", history_tokens=2600)
        self.assertEqual(tier_long_ctx, "TIER_3_CLOUD_HEAVY")

    # ---------------------------------------------------------
    # 6. Utility API Endpoint Tests
    # ---------------------------------------------------------
    def test_health_and_reset_endpoints(self):
        health_res = self.client.get("/api/v1/health/")
        self.assertEqual(health_res.status_code, 200)
        self.assertIn("healthy", health_res.json())

        ConversationMemory.append_turn("sess-99", "Hi", "Hello")
        reset_res = self.client.post(
            "/api/v1/chat/reset/",
            data={"session_id": "sess-99"},
            content_type="application/json",
        )
        self.assertEqual(reset_res.status_code, 200)
        self.assertEqual(ConversationMemory.get_history("sess-99"), [])

    @patch("gateway.services.ModelExecutor._call_ollama_chat")
    @patch("gateway.services.ModelExecutor._call_gemini_chat")
    def test_gateway_blocks_prompt_with_pii_before_llm_execution(self, mock_gemini, mock_ollama):
        from gateway.services import ModelExecutor

        events = list(
            ModelExecutor.execute_chat_stream(
                prompt="Please debug using my key AIzaSyDummyKey1234567890123456789012345 and email dev@rvce.edu.in",
                session_id="dlp-block-session",
                router_fn=RoutingEngine.determine_tier,
            )
        )

        joined_events = "".join(events)
        self.assertIn("event: blocked", joined_events)
        self.assertIn("cannot be passed to any LLM", joined_events)
        mock_ollama.assert_not_called()
        mock_gemini.assert_not_called()
        self.assertEqual(ConversationMemory.get_history("dlp-block-session"), [])

    def test_semantic_cache_hit_and_miss(self):
        SemanticCache.store(
            prompt="Explain the difference between TCP and UDP in 3 concise bullet points.",
            response_text="TCP is connection-oriented; UDP is connectionless.",
            tier="TIER_1_LOCAL_LIGHT",
        )

        # 1. Exact normalized phrasing -> 100% hit
        exact_hit = SemanticCache.lookup("Explain the difference between TCP and UDP in 3 concise bullet points")
        self.assertIsNotNone(exact_hit)
        self.assertEqual(exact_hit["similarity"], 100.0)

        # 2. Paraphrased phrasing -> >= 85% similarity hit
        paraphrase_hit = SemanticCache.lookup("What is the difference between TCP and UDP?")
        self.assertIsNotNone(paraphrase_hit)
        self.assertGreaterEqual(paraphrase_hit["similarity"], 85.0)

        # 3. Unrelated query -> miss
        miss = SemanticCache.lookup("Write a SQL query to join three tables.")
        self.assertIsNone(miss)