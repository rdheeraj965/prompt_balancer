# Intelligent 3-Tier LLM Routing Gateway (`prompt_balancer`)

An enterprise-grade, multi-parameter AI routing gateway and telemetry platform built with Django, Redis, Ollama, and Google GenAI. The system dynamically orchestrates Large Language Model (LLM) requests across local edge hardware and cloud tiers based on prompt complexity, context token volume, security policies, and live hardware telemetry.

---

## Key Features

* **Deterministic 3-Tier Routing Engine:** Evaluates incoming prompts using a mathematical Complexity Score ($S$) and cumulative Context Token Volume ($T$) to route requests across local and cloud models in sub-milliseconds.
* **Strict DLP Ingress Guardrail:** Intercepts every request at gateway ingress before caching, routing, or model execution. Detects sensitive PII and secrets (API keys, emails, phone numbers, credit cards, government IDs, internal IP addresses) and blocks transmission with zero LLM calls.
* **Hybrid Semantic Caching (Redis):** Uses normalized exact matching paired with 512-dimensional word unigram/bigram and character-trigram L2 cosine similarity vectors (threshold $\ge 0.85$) to serve repeat and paraphrased standalone queries at `$0.0000` cost.
* **Live Edge Hardware Telemetry:** Monitors real-time CPU load, System RAM (`psutil`), NVIDIA GPU VRAM (`nvidia-smi`), and Ollama daemon health. Automatically bypasses Tier 1 to Tier 2 when local memory exceeds safe thresholds ($> 85\%$).
* **Multi-Turn Memory & Local Session Persistence:** Maintains a sliding window of conversation turns in Redis while persisting multi-session chat histories in browser `localStorage` with one-click session restoration and context synchronization.
* **Waterfall Fallback & SSE Streaming:** Streams tokens in real time via Server-Sent Events (SSE) and automatically escalates to the next tier if an edge model times out or fails.
* **Interactive Telemetry & FinOps Dashboard:**
  * Live **3-Tier Visual Pipeline** highlighting active/bypassed nodes and per-message model badges.
  * **Markdown & LaTeX Math Rendering** (Marked.js, DOMPurify, KaTeX) with one-click code copy buttons.
  * **File Context Injection** (`.py`, `.ts`, `.txt`, `.log`, `.json`, `.sql`, etc.) demonstrating token-driven tier escalation.
  * **Faculty Demo Presets, Manual Tier Override & Stream Abort** controls.
  * **Chart.js FinOps Analytics Modal** tracking cumulative cost savings against a Cloud-Heavy baseline, cache hit rates, latency comparisons, and security audit logs.

---

## 3-Tier Model Routing Matrix

| Tier | Category | Routing Criteria | Assigned Model | Provider | Est. Cost / Req |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Cache** | Semantic Cache | Similarity $\ge 85\%$ (standalone query) | `Redis Vector Hit` | Redis 8.10 | `$0.0000` |
| **Tier 1** | Local Light | $S < 0.30$, $T \le 2000$, Healthy Edge | `gemma4:e2b` | Ollama (Local) | `$0.0000` |
| **Tier 2** | Cloud Light | $0.30 \le S < 0.65$, $T > 2000$, or Edge Degraded | `gemini-3.5-flash-lite` | Google GenAI | `$0.0002` |
| **Tier 3** | Cloud Heavy | $S \ge 0.65$ or $T > 2500$ tokens | `gemini-3.8-flash` | Google GenAI | `$0.0050` |

---

## Project Architecture

```text
prompt_balancer/
├── prompt_balancer/          # Django project settings & URL routing
│   ├── settings.py
│   └── urls.py
├── gateway/                  # Core middleware, security, caching & execution
│   ├── analytics.py          # FinOps cost savings & telemetry audit logger
│   ├── config_validator.py   # Startup tier & environment validation
│   ├── memory.py             # Redis sliding-window conversation memory
│   ├── pii_masker.py         # Ingress DLP regex scanner & blocker
│   ├── semantic_cache.py     # 512-dim hybrid vector cosine similarity cache
│   └── services.py           # 3-tier waterfall executor & SSE generator
├── router/                   # Prompt analysis, hardware monitor & API views
│   ├── analyzer.py           # Complexity score (S) & token volume (T) analyzer
│   ├── engine.py             # Deterministic 3-tier routing decision matrix
│   ├── monitor.py            # Live psutil CPU/RAM & nvidia-smi VRAM monitor
│   ├── tests.py              # Offline unit test suite
│   └── views.py              # REST & SSE streaming endpoints
├── static/
│   ├── ts/dashboard.ts       # TypeScript UI controller, SSE parser & Chart.js
│   └── js/dashboard.js       # Compiled ES2020 frontend bundle
├── templates/
│   └── dashboard.html        # Tailwind CSS single-page telemetry dashboard
├── docker-compose.yml        # Redis 8.10.1 service orchestration
├── Dockerfile                # Python 3.14.6 container specification
└── requirements.txt          # Python dependencies
```

---

## Technology Stack

* **Backend:** Python 3.14.6, Django 5.2+, Django REST Framework, `psutil`, `python-dotenv`
* **Cache & State Store:** Redis 8.10.1 (`django-redis`, `redis`)
* **Inference Runtimes:** Ollama (Local Edge), Google GenAI SDK (`google-genai`)
* **Frontend:** HTML5, Tailwind CSS, TypeScript (ES2020), Chart.js, Marked.js, DOMPurify, KaTeX
* **Containerization:** Docker & Docker Compose

---

## Installation & Setup

### 1. Prerequisites
* **Python:** 3.14.6+
* **Node.js / TypeScript:** For compiling `dashboard.ts` (`npx tsc`)
* **Docker & Docker Compose:** For running Redis
* **Ollama:** Installed and running locally on port `11434`

### 2. Clone & Install Dependencies
```bash
git clone https://github.com/rdheeraj965/prompt_balancer.git
cd prompt_balancer

python -m venv venv
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure Environment Variables (`.env`)
Create a `.env` file in the project root:
```env
DEBUG=True
SECRET_KEY=your-secure-django-secret-key
REDIS_URL=redis://127.0.0.1:6379/1
OLLAMA_BASE_URL=http://localhost:11434

# 3-Tier Model Configuration
TIER1_LOCAL_LIGHT_MODEL=gemma4:e2b
TIER1_TIMEOUT_SECONDS=45

TIER2_CLOUD_LIGHT_MODEL=gemini-3.5-flash-lite
TIER2_CLOUD_API_KEY=your_gemini_api_key_here

TIER3_CLOUD_HEAVY_MODEL=gemini-3.8-flash
TIER3_CLOUD_API_KEY=your_gemini_api_key_here

# Cache & Edge Hardware Thresholds
SEMANTIC_SIMILARITY_THRESHOLD=0.85
MAX_LOCAL_RAM_PERCENT=85.0
MAX_LOCAL_VRAM_PERCENT=85.0
```

### 4. Pull the Local Edge Model & Compile Frontend TypeScript
```bash
ollama pull gemma4:e2b
npx tsc static/ts/dashboard.ts --outFile static/js/dashboard.js --target es2020
```

### 5. Start Redis & Launch the Gateway
```bash
docker compose up -d redis
python manage.py runserver
```
Open `http://127.0.0.1:8000/` in your browser.

---

## API Endpoints & SSE Protocol

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Renders the 3-Tier Intelligent Model Router web dashboard. |
| `POST` | `/api/v1/route/` | Accepts `{ "prompt", "session_id", "forced_tier" }` and streams SSE events. |
| `POST` | `/api/v1/chat/reset/` | Clears Redis conversation history for a given `session_id`. |
| `POST` | `/api/v1/chat/sync/` | Syncs restored `localStorage` chat turns back into Redis context. |
| `GET` | `/api/v1/health/` | Returns live CPU, RAM, GPU VRAM, and Ollama liveness status. |
| `GET` / `POST` | `/api/v1/analytics/` | Retrieves or resets FinOps cost savings and tier distribution metrics. |

### SSE Event Stream Schema (`/api/v1/route/`)
* `event: security` / `event: blocked` — Emitted immediately when DLP ingress detects PII or API keys.
* `event: metrics` — Emitted with computed `complexity_score`, `total_context_tokens`, and live hardware telemetry.
* `event: status` — Announces active execution tier (`CACHE`, `TIER_1_LOCAL_LIGHT`, `TIER_2_CLOUD_LIGHT`, `TIER_3_CLOUD_HEAVY`) and model name.
* `event: message` — Streams incremental response text chunks.
* `event: fallback` — Notifies the client if an edge/cloud tier fails and escalates to the next tier.
* `event: complete` — Finalizes the turn with `routed_tier`, `latency_ms`, and `cost`.

---

## Running Unit Tests

The test suite mocks external network and hardware calls using in-memory caching so it runs offline in milliseconds:

```bash
python manage.py test router
```