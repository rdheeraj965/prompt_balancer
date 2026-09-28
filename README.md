# 3-Tier Intelligent LLM Routing Gateway

An enterprise-grade, multi-parameter routing engine and API gateway designed to dynamically orchestrate Large Language Model (LLM) requests across local edge hardware and cloud environments.

This project optimizes AI application performance, reduces API latency, and minimizes operational costs by intelligently routing prompts based on compute complexity, token volume, and real-time hardware health.

## 🚀 Key Features

* **Multi-Parameter Routing Engine**: Evaluates incoming prompts using a deterministic complexity score ($S$) and token volume estimation ($T$) to select the optimal model tier.

* **3-Tier Hybrid Architecture**: Seamlessly bridges local execution (Ollama) and cloud execution across three capability tiers.

* **Waterfall Fallback Mechanism**: Ensures 100% uptime. If a local GPU overflows or a cloud API fails, the gateway automatically intercepts the error and cascades the request to the next available tier without crashing.

* **Server-Sent Events (SSE) Streaming**: Maintains open HTTP sockets for high-latency architectural tasks, streaming tokens back to the client in real-time.

* **Live Telemetry Dashboard**: A responsive, TypeScript-powered frontend visualizing routing decisions, latency metrics, and estimated cost savings.

* **Redis Caching**: Sub-millisecond configuration lookups and system state management.

## 🧠 Model Tier Configuration

| Tier | Category | Capability Profile | Assigned Model | Provider | 
 | ----- | ----- | ----- | ----- | ----- | 
| **Tier 1** | Local Light | Fast execution, low VRAM | `gemma4:e2b` | Ollama (Local) | 
|  | 
| **Tier 2** | Cloud Light | High throughput, low cost | `gemini-3.5-flash-lite` | Google GenAI API | 
| **Tier 3** | Cloud Heavy | Enterprise architectural design | `gemini-3.8-flash` | Google GenAI API | 

## 🛠️ Technology Stack

* **Backend**: Python 3.14.6, Django >=5.2, Django REST Framework

* **Cache & State**: Redis 8.10.1, django-redis

* **Local Inference**: Ollama

* **Cloud Inference**: Google GenAI SDK

* **Frontend**: HTML5, Tailwind CSS, TypeScript

* **Infrastructure**: Docker, Docker Compose

## ⚙️ Installation & Setup

### 1. Prerequisites

* **Python**: 3.14.6 or higher

* **Docker & Docker Compose**: For running the Redis cache layer.

* **Ollama**: Installed and running locally.

### 2. Clone the Repository

```
git clone https://github.com/rdheeraj965/prompt_balancer.git
cd prompt_balancer

```

### 3. Environment Setup

Create a virtual environment and install dependencies:

```
python -m venv venv
# Windows: venv\Scripts\activate
# Mac/Linux: source venv/bin/activate

pip install -r requirements.txt

```

### 4. Configuration (`.env`)

Create a `.env` file in the root directory and configure your keys:

```
DEBUG=True
SECRET_KEY=your-secure-django-key
REDIS_URL=redis://127.0.0.1:6379/1
OLLAMA_BASE_URL=http://localhost:11434

# Tier Configurations
TIER1_LOCAL_LIGHT_MODEL=gemma4:e2b
TIER1_TIMEOUT_SECONDS=30

TIER2_CLOUD_LIGHT_MODEL=gemini-3.5-flash-lite
TIER2_CLOUD_API_KEY=your_gemini_api_key_here

TIER3_CLOUD_HEAVY_MODEL=gemini-3.8-flash
TIER3_CLOUD_API_KEY=your_gemini_api_key_here

```

### 5. Pull Local Models

Ensure Ollama is running, then pull the assigned Tier 1 and Tier 2 models:

```
ollama pull model_of_your_choice

```

### 6. Start the Infrastructure

Start the Redis cache using Docker Compose:

```
docker compose up -d redis

```

Run the Django Gateway:

```
python manage.py runserver

```

## 💻 Usage

### Accessing the Telemetry Dashboard

Open your browser and navigate to:

```
http://127.0.0.1:8000/

```

From here, you can input prompts, observe the dynamic routing matrix in action, and view real-time streaming, latency, and cost telemetry.

### API Endpoint (`/api/v1/route/`)

You can bypass the UI and interact directly with the routing engine via standard HTTP POST requests.

**Request:**

```
curl -X POST http://127.0.0.1:8000/api/v1/route/ \
-H "Content-Type: application/json" \
-d '{"prompt": "Write a quick Python loop."}'

```

**Streamed Response Format (SSE):**

```
event: status
data: {"status": "routing", "tier": "TIER_1_LOCAL_LIGHT"}

event: message
data: {"text": "for i in range(10):"}

event: complete
data: {"status": "Success", "routed_tier": "TIER_1_LOCAL_LIGHT", "latency_ms": "1240.5 ms", "cost": "$0.0000", "error_details": null}

```

*Developed as an academic architectural system design project.*