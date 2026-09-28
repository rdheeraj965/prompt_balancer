import random

class SystemMonitor:
    @classmethod
    def check_local_health(cls):
        # For demonstration and Phase 2 testing, we simulate local hardware status.
        # In Phase 4, this could query an NVIDIA SMI wrapper or Ollama's /api/ps endpoint.
        
        # Simulate 90% uptime for local hardware capacity
        is_gpu_available = random.random() > 0.10 
        
        return {
            "vram_available": is_gpu_available,
            "active_local_jobs": 0 if is_gpu_available else 2
        }