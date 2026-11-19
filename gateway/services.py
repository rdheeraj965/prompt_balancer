import time
import json
import os
import requests
from typing import List, Dict, Optional
from django.conf import settings
from google import genai
from gateway.pii_masker import PIIMasker
from gateway.semantic_cache import SemanticCache
from gateway.memory import ConversationMemory
from gateway.analytics import AnalyticsTracker


class ModelExecutor:
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    CONTEXT_DEPENDENT_WORDS = {
        "it", "this", "that", "those", "these", "they", "them",
        "above", "previous", "earlier", "more", "again", "continue", "elaborate",
    }

    @classmethod
    def execute_chat_stream(
        cls,
        prompt: str,
        session_id: str,
        router_fn,
        forced_tier: Optional[str] = None,
    ):
        start_time = time.time()

        # 1. Strict DLP Ingress Guardrail (Runs FIRST before cache, routing, or LLM calls)
        pii_detected = PIIMasker.inspect(prompt)
        if pii_detected:
            latency = round((time.time() - start_time) * 1000, 2)
            AnalyticsTracker.record(
                tier="DLP_BLOCKED",
                model_name="DLP Guardrail",
                latency_ms=latency,
                cost_str="$0.0000",
                pii_redacted=True,
                cache_hit=False,
            )
            yield f"event: security\ndata: {json.dumps({'blocked': True, 'detected_entities': pii_detected})}\n\n"
            block_payload = {
                "status": "Blocked",
                "reason": "This prompt contains sensitive PII or secret keys and cannot be passed to any LLM.",
                "detected_entities": pii_detected,
                "latency_ms": f"{latency} ms",
                "cost": "$0.0000",
            }
            yield f"event: blocked\ndata: {json.dumps(block_payload)}\n\n"
            return

        history = ConversationMemory.get_history(session_id)
        is_first_turn = len(history) == 0
        valid_override = forced_tier if forced_tier in settings.MODEL_TIERS else None
        cacheable = cls._is_cacheable_query(prompt, is_first_turn)

        # 2. Semantic Cache Lookup (works on turn 1 AND standalone queries in later turns)
        if cacheable and not valid_override:
            cached = SemanticCache.lookup(prompt)
            if cached:
                cache_label = f"Cached ({cached['original_tier']})"
                yield f"event: status\ndata: {json.dumps({'status': 'cache_hit', 'tier': 'SEMANTIC_CACHE (REDIS)', 'model_name': cache_label, 'similarity': cached['similarity']})}\n\n"
                yield f"event: message\ndata: {json.dumps({'text': cached['response']})}\n\n"
                ConversationMemory.append_turn(session_id, prompt, cached["response"])

                latency = round((time.time() - start_time) * 1000, 2)
                AnalyticsTracker.record(
                    tier="CACHE",
                    model_name=cache_label,
                    latency_ms=latency,
                    cost_str="$0.0000",
                    pii_redacted=False,
                    cache_hit=True,
                )

                schema = {
                    "status": "Cache Hit",
                    "routed_tier": f"CACHE ({cached['similarity']}% match)",
                    "model_name": cache_label,
                    "latency_ms": f"{latency} ms",
                    "cost": "$0.0000",
                    "error_details": None,
                }
                yield f"event: complete\ndata: {json.dumps(schema)}\n\n"
                return

        # 3. Analyze & Route (or apply Manual Override)
        history_tokens = ConversationMemory.estimate_history_tokens(history)
        routed_tier, metrics = router_fn(prompt, history_tokens)
        initial_tier = valid_override or routed_tier
        metrics["overridden"] = bool(valid_override)
        yield f"event: metrics\ndata: {json.dumps(metrics)}\n\n"

        # 4. 3-Tier Waterfall Execution
        tiers_in_order = [
            "TIER_1_LOCAL_LIGHT",
            "TIER_2_CLOUD_LIGHT",
            "TIER_3_CLOUD_HEAVY",
        ]
        start_idx = tiers_in_order.index(initial_tier)

        for i in range(start_idx, len(tiers_in_order)):
            current_tier = tiers_in_order[i]
            tier_config = settings.MODEL_TIERS.get(current_tier)
            tier_start = time.time()
            full_response_chunks: List[str] = []

            try:
                yield f"event: status\ndata: {json.dumps({'status': 'routing', 'tier': current_tier, 'model_name': tier_config['model_name']})}\n\n"

                if tier_config["type"] == "LOCAL":
                    stream_gen = cls._call_ollama_chat(tier_config, history, prompt)
                else:
                    stream_gen = cls._call_gemini_chat(tier_config, history, prompt)

                for chunk in stream_gen:
                    full_response_chunks.append(chunk)
                    yield f"event: message\ndata: {json.dumps({'text': chunk})}\n\n"

                complete_reply = "".join(full_response_chunks)
                ConversationMemory.append_turn(session_id, prompt, complete_reply)

                if cacheable:
                    SemanticCache.store(prompt, complete_reply, current_tier)

                latency = round((time.time() - tier_start) * 1000, 2)
                cost_str = cls._estimate_cost(current_tier)

                AnalyticsTracker.record(
                    tier=current_tier,
                    model_name=tier_config["model_name"],
                    latency_ms=latency,
                    cost_str=cost_str,
                    pii_redacted=False,
                    cache_hit=False,
                )

                schema = {
                    "status": "Success",
                    "routed_tier": current_tier,
                    "model_name": tier_config["model_name"],
                    "latency_ms": f"{latency} ms",
                    "cost": cost_str,
                    "error_details": None,
                }
                yield f"event: complete\ndata: {json.dumps(schema)}\n\n"
                return

            except Exception as e:
                if i == len(tiers_in_order) - 1:
                    latency = round((time.time() - tier_start) * 1000, 2)
                    error_schema = {
                        "status": "Failed",
                        "routed_tier": current_tier,
                        "latency_ms": f"{latency} ms",
                        "cost": "$0.0000",
                        "error_details": str(e),
                    }
                    yield f"event: error\ndata: {json.dumps(error_schema)}\n\n"
                    return

                yield f"event: fallback\ndata: {json.dumps({'failed_tier': current_tier, 'reason': str(e)})}\n\n"

    @classmethod
    def _call_ollama_chat(cls, config: Dict, history: List[Dict], prompt: str):
        url = f"{cls.OLLAMA_BASE_URL}/api/chat"
        messages = history + [{"role": "user", "content": prompt}]
        payload = {
            "model": config["model_name"],
            "messages": messages,
            "stream": True,
            "keep_alive": "60m",
        }
        response = requests.post(url, json=payload, stream=True, timeout=config.get("timeout", 60))
        response.raise_for_status()

        for line in response.iter_lines():
            if line:
                data = json.loads(line.decode("utf-8"))
                msg = data.get("message", {})
                if "content" in msg and msg["content"]:
                    yield msg["content"]

    @classmethod
    def _call_gemini_chat(cls, config: Dict, history: List[Dict], prompt: str):
        client = genai.Client(api_key=config["api_key"])
        contents = []
        for turn in history:
            role = "model" if turn["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": turn["content"]}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        stream = client.models.generate_content_stream(
            model=config["model_name"],
            contents=contents,
        )
        for chunk in stream:
            if chunk.text:
                yield chunk.text

    @classmethod
    def _estimate_cost(cls, tier: str) -> str:
        costs = {
            "TIER_1_LOCAL_LIGHT": "$0.0000",
            "TIER_2_CLOUD_LIGHT": "$0.0002",
            "TIER_3_CLOUD_HEAVY": "$0.0050",
        }
        return costs.get(tier, "$0.0000")

    @classmethod
    def _is_cacheable_query(cls, prompt: str, is_first_turn: bool) -> bool:
        if is_first_turn:
            return True
        words = [w.strip(".,?!:;\"'()[]") for w in prompt.lower().split()]
        if len(words) < 4:
            return False
        if any(w in cls.CONTEXT_DEPENDENT_WORDS for w in words):
            return False
        return True