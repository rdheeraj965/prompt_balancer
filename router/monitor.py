import os
import subprocess
import psutil
import requests
from django.conf import settings

class SystemMonitor:
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    @classmethod
    def _check_gpu_vram(cls):
        try:
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                stderr=subprocess.DEVNULL,
                timeout=2,
            ).decode("utf-8").strip()
            first_gpu = output.splitlines()[0]
            used_mb, total_mb = [float(x.strip()) for x in first_gpu.split(",")]
            percent = round((used_mb / total_mb) * 100, 1) if total_mb > 0 else 0.0
            return {"available": True, "used_mb": int(used_mb), "total_mb": int(total_mb), "percent": percent}
        except Exception:
            return {"available": False, "used_mb": 0, "total_mb": 0, "percent": 0.0}

    @classmethod
    def _check_ollama_alive(cls) -> bool:
        try:
            resp = requests.get(f"{cls.OLLAMA_BASE_URL}/api/tags", timeout=0.6)
            return resp.status_code == 200
        except Exception:
            return False

    @classmethod
    def check_local_health(cls) -> dict:
        cpu_percent = psutil.cpu_percent(interval=0.05)
        ram_percent = psutil.virtual_memory().percent
        gpu = cls._check_gpu_vram()
        ollama_up = cls._check_ollama_alive()

        max_ram = getattr(settings, "MAX_LOCAL_RAM_PERCENT", 85.0)
        max_vram = getattr(settings, "MAX_LOCAL_VRAM_PERCENT", 85.0)

        reason = "Healthy"
        healthy = True

        if not ollama_up:
            healthy = False
            reason = "Ollama service unreachable"
        elif ram_percent > max_ram:
            healthy = False
            reason = f"High System RAM ({ram_percent}% > {max_ram}%)"
        elif gpu["available"] and gpu["percent"] > max_vram:
            healthy = False
            reason = f"High GPU VRAM ({gpu['percent']}% > {max_vram}%)"

        return {
            "healthy": healthy,
            "reason": reason,
            "cpu_percent": cpu_percent,
            "ram_percent": ram_percent,
            "vram_percent": gpu["percent"],
            "vram_used_mb": gpu["used_mb"],
            "vram_total_mb": gpu["total_mb"],
        }