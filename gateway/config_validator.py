from django.conf import settings
from django.core.cache import cache

class TierConfigManager:
    @classmethod
    def validate_tiers(cls):
        tiers = settings.MODEL_TIERS
        local_active = any(t['type'] == 'LOCAL' and t['model_name'] for t in tiers.values())
        cloud_active = any(t['type'] == 'CLOUD' and t['model_name'] for t in tiers.values())

        if not (local_active and cloud_active):
            raise ValueError("System Configuration Error: Must have at least 1 active Local and 1 Cloud model.")

        # Store active configurations into Redis cache for fast router access
        cache.set("active_model_tiers", tiers, timeout=None)
        return True