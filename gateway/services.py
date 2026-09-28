import time
import json
import os
import requests
from django.conf import settings
from google import genai

class ModelExecutor:
    # Fallback to local host if .env is missing
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    @classmethod
    def execute_with_fallback(cls, initial_tier, prompt):
        tiers_in_order = [
            "TIER_1_LOCAL_LIGHT",
            "TIER_2_LOCAL_HEAVY",
            "TIER_3_CLOUD_LIGHT",
            "TIER_4_CLOUD_HEAVY"
        ]
        
        start_idx = tiers_in_order.index(initial_tier)
        
        for i in range(start_idx, len(tiers_in_order)):
            current_tier = tiers_in_order[i]
            tier_config = settings.MODEL_TIERS.get(current_tier)
            start_time = time.time()
            
            try:
                # Notify client which tier is currently executing
                yield f"event: status\ndata: {json.dumps({'status': 'routing', 'tier': current_tier})}\n\n"
                
                if tier_config["type"] == "LOCAL":
                    stream_generator = cls._call_ollama_stream(tier_config, prompt)
                else:
                    stream_generator = cls._call_gemini_stream(tier_config, prompt)
                
                # Yield text chunks as they arrive
                for chunk in stream_generator:
                    yield f"event: message\ndata: {json.dumps({'text': chunk})}\n\n"
                
                # Final Standardized JSON Schema
                latency = round((time.time() - start_time) * 1000, 2)
                schema = {
                    "status": "Success",
                    "routed_tier": current_tier,
                    "latency_ms": f"{latency} ms",
                    "cost": cls._estimate_cost(current_tier),
                    "error_details": None
                }
                yield f"event: complete\ndata: {json.dumps(schema)}\n\n"
                return 
                
            except Exception as e:
                # If the final tier fails, emit an error block
                if i == len(tiers_in_order) - 1:
                    latency = round((time.time() - start_time) * 1000, 2)
                    error_schema = {
                        "status": "Failed",
                        "routed_tier": current_tier,
                        "latency_ms": f"{latency} ms",
                        "cost": "$0.0000",
                        "error_details": str(e)
                    }
                    yield f"event: error\ndata: {json.dumps(error_schema)}\n\n"
                    return
                
                # Notify client of the fallback trigger
                yield f"event: fallback\ndata: {json.dumps({'failed_tier': current_tier, 'reason': str(e)})}\n\n"

    @classmethod
    def _call_ollama_stream(cls, config, prompt):
        url = f"{cls.OLLAMA_BASE_URL}/api/generate"
        payload = {
            "model": config["model_name"],
            "prompt": prompt,
            "stream": True,
            "keep_alive": "60m" 
        }
        # Stream=True prevents the socket from closing during high-token architectural prompts
        response = requests.post(url, json=payload, stream=True, timeout=config.get("timeout", 180))
        response.raise_for_status()
        
        for line in response.iter_lines():
            if line:
                data = json.loads(line.decode('utf-8'))
                if "response" in data:
                    yield data["response"]

    @classmethod
    def _call_gemini_stream(cls, config, prompt):
        client = genai.Client(api_key=config["api_key"])
        stream = client.models.generate_content_stream(
            model=config["model_name"],
            contents=prompt
        )
        for chunk in stream:
            if chunk.text:
                yield chunk.text

    @classmethod
    def _estimate_cost(cls, tier):
        costs = {
            "TIER_1_LOCAL_LIGHT": "$0.0000",
            "TIER_2_LOCAL_HEAVY": "$0.0000",
            "TIER_3_CLOUD_LIGHT": "$0.0002",
            "TIER_4_CLOUD_HEAVY": "$0.0050"
        }
        return costs.get(tier, "Unknown")