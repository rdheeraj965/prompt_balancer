import json
import time
from typing import Dict, Any, List
from django.core.cache import cache


class AnalyticsTracker:
    CACHE_KEY = "prompt_balancer:analytics_logs"
    MAX_LOGS = 500
    BASELINE_TIER3_COST = 0.0050  # Cost per query if everything defaulted to Cloud Heavy

    @classmethod
    def record(
        cls,
        tier: str,
        model_name: str,
        latency_ms: float,
        cost_str: str,
        pii_redacted: bool = False,
        cache_hit: bool = False,
    ) -> None:
        raw = cache.get(cls.CACHE_KEY)
        logs: List[Dict[str, Any]] = json.loads(raw) if raw else []

        try:
            numeric_cost = float(cost_str.replace("$", "").strip())
        except ValueError:
            numeric_cost = 0.0

        logs.append({
            "timestamp": time.strftime("%H:%M:%S"),
            "tier": tier,
            "model_name": model_name,
            "latency_ms": round(latency_ms, 2),
            "cost": numeric_cost,
            "baseline_cost": cls.BASELINE_TIER3_COST,
            "pii_redacted": pii_redacted,
            "cache_hit": cache_hit,
        })

        cache.set(cls.CACHE_KEY, json.dumps(logs[-cls.MAX_LOGS :]), timeout=86400 * 7)

    @classmethod
    def get_summary(cls) -> Dict[str, Any]:
        raw = cache.get(cls.CACHE_KEY)
        logs: List[Dict[str, Any]] = json.loads(raw) if raw else []

        tiers = ["CACHE", "TIER_1_LOCAL_LIGHT", "TIER_2_CLOUD_LIGHT", "TIER_3_CLOUD_HEAVY"]
        tier_counts = {t: 0 for t in tiers}
        latency_sums = {t: 0.0 for t in tiers}

        total_actual_cost = 0.0
        total_baseline_cost = 0.0
        cache_hits = 0
        pii_events = 0

        for entry in logs:
            t = entry.get("tier", "TIER_1_LOCAL_LIGHT")
            if t not in tier_counts:
                tier_counts[t] = 0
                latency_sums[t] = 0.0

            tier_counts[t] += 1
            latency_sums[t] += float(entry.get("latency_ms", 0.0))
            total_actual_cost += float(entry.get("cost", 0.0))
            total_baseline_cost += float(entry.get("baseline_cost", cls.BASELINE_TIER3_COST))

            if entry.get("cache_hit"):
                cache_hits += 1
            if entry.get("pii_redacted"):
                pii_events += 1

        avg_latency = {
            t: round(latency_sums[t] / tier_counts[t], 1) if tier_counts[t] > 0 else 0.0
            for t in tiers
        }

        total_requests = len(logs)
        total_saved = max(0.0, total_baseline_cost - total_actual_cost)
        savings_percent = round((total_saved / total_baseline_cost) * 100, 1) if total_baseline_cost > 0 else 0.0
        cache_hit_rate = round((cache_hits / total_requests) * 100, 1) if total_requests > 0 else 0.0

        return {
            "total_requests": total_requests,
            "tier_counts": tier_counts,
            "avg_latency_ms": avg_latency,
            "total_actual_cost": round(total_actual_cost, 4),
            "total_baseline_cost": round(total_baseline_cost, 4),
            "total_saved": round(total_saved, 4),
            "savings_percent": savings_percent,
            "cache_hits": cache_hits,
            "cache_hit_rate": cache_hit_rate,
            "pii_events": pii_events,
            "recent_logs": list(reversed(logs[-8:])),
        }

    @classmethod
    def clear(cls) -> None:
        cache.delete(cls.CACHE_KEY)