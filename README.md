# Project Luvcraft

## An internal AI-powered fandom intelligence platform by Project Pluto

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-black?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)
[![Supabase](https://img.shields.io/badge/Supabase-3FCF8E?style=flat-square&logo=supabase&logoColor=white)](https://supabase.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![RabbitMQ](https://img.shields.io/badge/RabbitMQ-FF6600?style=flat-square&logo=rabbitmq&logoColor=white)](https://www.rabbitmq.com/)

---

## Overview

**Project Luvcraft** is developed with **Project Pluto** as the industry partner. The platform aggregates public market signals, tracks hype cycles, measures sentiment across social platforms, and uses Large Language Models (LLMs) to generate multi-dimensional brand collaboration insights for strategic fandom research.

## Key Features

* **Signal Aggregation:** Collects real-time data from social and community platforms.
* **Hype Tracking:** Measures velocity and volume of market trends.
* **AI-Powered Insights:** Uses LangChain and LLMs to generate actionable reports.
* **Unified Analysis:** Runs sentiment, keywords, trend, and engagement
  sequentially over one final dataset with validated results and lifecycle logs.
* **Asynchronous Processing:** Uses a PostgreSQL transactional outbox, Celery Beat, workers, and RabbitMQ for durable background tasks.
* **Interactive Dashboard:** Provides a researcher portal built with Next.js and Tailwind CSS.

## Tech Stack

**Frontend:**

* Next.js 16 & React 19
* Tailwind CSS
* Recharts

**Backend:**

* Python 3.12 & FastAPI
* Celery & RabbitMQ (Task Queues)
* Supabase PostgreSQL (Managed Persistence)
* SQLAlchemy (Data Models)
* Google Gemini structured outputs (implemented hybrid sentiment)
* LangChain & LiteLLM (broader intelligence-layer orchestration)

**AI Model Routing:**

* **Configurable Gemini sentiment model:** Structured English/Vietnamese
  positive/neutral/negative classification through the Google Gen AI SDK. The
  default is stable `gemini-3.1-flash-lite`; environments can pin another
  supported Gemini model.
* **Lexicon fallback:** Deterministic offline classification when the provider,
  credential, or durable cache is unavailable.
* **Broader synthesis routing:** The existing LangChain/LiteLLM intelligence
  service remains a placeholder for later vibe-check and narrative tasks.

**Infrastructure & Data:**

* Docker Compose for local development
* RabbitMQ persistent task queue volume
* Supabase-managed PostgreSQL for deployed persistence
* Local PostgreSQL-compatible container for development fallback

## Architecture & Structure

The repository follows a clean, modular, cloud-ready monorepo structure:

```text
project-luvcraft/
|-- backend/                 # Core API and worker services
|   |-- app/collectors/      # Modular scrapers and public data collectors
|   |-- app/analysis/        # Canonical contracts and analytical modules
|   |-- app/services/        # LLM intelligence and reporting modules
|   `-- app/db/              # PostgreSQL-compatible data models
|-- frontend/                # Researcher dashboard UI
|   `-- components/          # Internal dashboard components
|-- docs/                    # Technical documentation
|   `-- collector.md         # YouTube Collector MVP documentation
|-- compose.yaml             # Local Postgres, RabbitMQ, Celery, Backend, Frontend
`-- CONTRIBUTING.md          # Mandatory Git conventions and team rules
```

The live final-only analytical workflow is documented in
[`docs/unified-analysis-pipeline.md`](docs/unified-analysis-pipeline.md).

## Running The Project

### Prerequisites

Install the following tools before running the project locally:

* [Docker Desktop](https://www.docker.com/products/docker-desktop) for the full local stack.
* Node.js `24.x` and npm `11.x` for local frontend development.
* Python `3.12` for local backend development outside Docker.
* A Supabase PostgreSQL connection string when using the shared cloud database.

The project can run with either Supabase PostgreSQL or the local PostgreSQL container from `compose.yaml`. For normal local development, Docker Compose is the fastest setup because it starts the frontend, backend, Celery worker, Celery Beat dispatcher, PostgreSQL, and RabbitMQ together.

### Environment Variables

Use `.env.local.example` as the local setup template. Copy it to `.env.local` when running the Docker Compose/backend flow, then fill in secrets only in your local `.env.local`. Keep `.env.local.example` free of real API keys so teammates do not accidentally commit or reuse private credentials.

| Variable | Used By | Local Default | Notes |
| :--- | :--- | :--- | :--- |
| `DATABASE_URL` | Backend, Celery | `postgresql://postgres:postgres@localhost:5432/luvcraft` outside Docker, `postgresql://postgres:postgres@postgres:5432/luvcraft` inside Compose | Set this to the Supabase PostgreSQL connection string for shared environments. |
| `MIGRATION_DATABASE_URL` | Backend migration command | None | Optional direct PostgreSQL URL for Alembic when `DATABASE_URL` uses a pooler. |
| `CELERY_BROKER_URL` | Backend, Celery | `pyamqp://luvcraft:luvcraft@localhost:5672//` outside Docker, `pyamqp://luvcraft:luvcraft@rabbitmq:5672//` inside Compose | RabbitMQ replaces Redis as the persistent task broker. |
| `CELERY_RESULT_BACKEND` | Celery | `db+<DATABASE_URL>` | Optional. The backend defaults to storing Celery results in PostgreSQL. |
| `CORS_ORIGINS` | Backend | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated frontend origins allowed to call the FastAPI service. |
| `YOUTUBE_API_KEY` | Backend, Celery | None | Task 4 YouTube collector API key. Do not commit real keys. |
| `YOUTUBE_REGION_CODE` | Backend, Celery | `VN` | Task 4 YouTube search region filter. |
| `YOUTUBE_RELEVANCE_LANGUAGE` | Backend, Celery | `vi` | Task 4 YouTube search relevance language and persisted signal language. |
| `YOUTUBE_MAX_RESULTS` | Celery | `50` | Maximum videos requested per YouTube search. The collector clamps this to YouTube's per-request limit of 50. |
| `YOUTUBE_MIN_RECORDS_THRESHOLD` | Celery | `20` | Minimum persisted YouTube signals before the module omits the insufficient-data warning. |
| `YOUTUBE_TIMEOUT_MAX_RETRIES` | Celery | `3` | Maximum Celery retries for transient YouTube timeout errors before marking the module failed. |
| `YOUTUBE_TIMEOUT_RETRY_DELAY_SECONDS` | Celery | `60` | Delay between retries after a transient YouTube timeout. |
| `SERPEX_API_KEY` | Celery | None | Serpex.dev bearer key for public SERP result collection. Keep the real key only in ignored `.env.local`. |
| `SERPEX_MAX_RESULTS` | Celery | `10` | Maximum results retained from one Serpex response. The current API has no documented pagination or requested-page-size field. |
| `SERPEX_TIMEOUT_SECONDS` | Celery | `10` | Timeout for one Serpex search request. |
| `SERPEX_MAX_RETRIES` | Celery | `3` | Maximum retries for Serpex rate limits and temporary provider/network failures. |
| `SERPEX_RETRY_DELAY_SECONDS` | Celery | `60` | Default delay for retryable Serpex failures when the provider gives no retry delay. |
| `SENTIMENT_ENGINE` | Backend, Celery | `lexicon` | Set to `hybrid` to enable structured LLM sentiment with lexicon fallback. |
| `GEMINI_API_KEY` | Backend, Celery | None | Put the real Gemini API key only in ignored root `.env.local`; never commit it. |
| `GEMINI_SENTIMENT_MODEL` | Backend, Celery | `gemini-3.1-flash-lite` | Configurable Gemini sentiment-classification model. |
| `GEMINI_SENTIMENT_PROMPT_VERSION` | Backend, Celery | `sentiment-gemini-v1` | Version included in cache and result provenance. |
| `GEMINI_SENTIMENT_INPUT_COST_PER_MILLION_USD` | Backend, Celery | None | Optional explicit billing rate; set together with the output rate. |
| `GEMINI_SENTIMENT_OUTPUT_COST_PER_MILLION_USD` | Backend, Celery | None | Optional explicit billing rate; set together with the input rate. |
| `DEBUG_HTTP` | Backend, Celery | `false` | Enables verbose `httpx`/`httpcore` logging for local debugging. Leave disabled when using real API keys. |
| `NEXT_PUBLIC_API_URL` | Frontend | `http://localhost:8000` | API base URL used by the Next.js app. |

If the Supabase database password contains special characters, URL-encode the password before placing it in `DATABASE_URL`.

Task 4 update: YouTube collector verification is backend/API/database only. A completed run means the YouTube collection task finished and persisted `CollectedSignal` records; `/runs/{run_id}/result` still depends on synthesis output and is not part of the Task 4 collector scope.

### Option 1: Run The Full Stack With Docker Compose

Use this path when the team wants the complete app running with the fewest manual steps.

```bash
docker compose --env-file .env.local up --build
```

The backend applies all pending Alembic migrations before starting the API. When running FastAPI manually from `backend/`, run `python -m app.db.migrate` before starting Uvicorn.

Local Compose pins RabbitMQ to `3.13-management-alpine` for compatibility with the current Celery queue declarations.

For deployed environments, set `DATABASE_URL` to the Supabase PostgreSQL connection string. Local Compose falls back to a development PostgreSQL container when `DATABASE_URL` is not provided.

### Option 2: Run Backend and Frontend Standalone (Development Mode)

#### 1. Start Database & Message Broker Infrastructure

Before starting the standalone backend or worker processes, start the local PostgreSQL and RabbitMQ containers:

```bash
# Start background PostgreSQL and RabbitMQ containers
docker compose up -d postgres rabbitmq
```

#### 2. Running Backend, Celery Worker & Beat dispatcher locally

```bash
# Navigate to backend directory
cd backend

# Create and activate virtual environment
python -m venv .venv
# On Windows (PowerShell):
# Note: If you get an ExecutionPolicy error, run: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
# On macOS / Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template and configure secrets
cp ../.env.local.example ../.env.local

# Run database migrations
python -m app.db.migrate

# Start FastAPI API Server (Terminal 1)
# Note for Windows users: if virtualenv activation fails, run using the local binary directly:
# .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Start Celery Worker for background task processing (Terminal 2)
python -m celery -A app.core.worker.celery_app worker -l info

# Start Celery Beat for outbox redispatching and scheduled jobs (Terminal 3)
python -m celery -A app.core.worker.celery_app beat -l info
```

#### 3. Running Frontend locally

```bash
# Navigate to frontend directory
cd frontend

# Install Node.js dependencies
npm install

# Start Next.js development server
npm run dev
```

The frontend will be available at [http://localhost:3000](http://localhost:3000) and will communicate with FastAPI at `http://localhost:8000`.

---

## Running Tests

To run the analytical, API, and integration test suites, ensure you have your python virtual environment activated and the dependencies installed.

### Option 1: Running from the workspace root (recommended)

```powershell
# Set PYTHONPATH to include the backend folder
$env:PYTHONPATH = "backend"
$env:SENTIMENT_ENGINE = "lexicon"

# Run all backend tests (requires running local PostgreSQL on port 5432)
backend\.venv\Scripts\pytest backend/app/tests/

# Run only the offline / analytical vibe check tests (does NOT require local PostgreSQL)
backend\.venv\Scripts\pytest backend/app/tests/test_collab_fit.py backend/app/tests/test_api_vibe_check.py backend/app/tests/test_vibe_check_e2e.py backend/app/tests/test_vibe_check_integration.py backend/app/tests/test_community_health.py backend/app/tests/test_vibe_score.py backend/app/tests/test_geo_comparison.py backend/app/tests/test_anomaly_detection.py backend/app/tests/test_geo_anomaly_persistence.py backend/app/tests/test_vibe_results_repository.py

# Run a specific test suite
backend\.venv\Scripts\pytest backend/app/tests/test_collab_fit.py
backend\.venv\Scripts\pytest backend/app/tests/test_api_vibe_check.py

```

### Option 2: Running from the backend directory

```bash
cd backend

# On Windows:
$env:PYTHONPATH = "."
$env:SENTIMENT_ENGINE = "lexicon"
.venv\Scripts\pytest

# On macOS/Linux:
export PYTHONPATH="."
export SENTIMENT_ENGINE="lexicon"
.venv/bin/pytest
```

---

## DigitalOcean VPS Deployment Guide

This guide outlines how to deploy Project Luvcraft to a production or staging DigitalOcean Droplet (VPS) using the production Compose specification (`compose.prod.yaml`).

### 1. VPS System Requirements & Preparation

- **OS:** Ubuntu 22.04 LTS or 24.04 LTS (Recommended: 4GB RAM / 2 vCPUs minimum for Celery + Next.js build).
- **Prerequisites:** Docker Engine, Docker Compose plugin, Git, UFW firewall.

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install Docker & Docker Compose Plugin
sudo apt install -y docker.io docker-compose-v2 git ufw

# Enable Docker service
sudo systemctl enable --now docker
sudo usermod -aG docker $USER

# Configure UFW Firewall (Only public HTTP/HTTPS and SSH are exposed)
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

### 2. Clone Repository & Setup Production Environment

```bash
# Clone the repository
git clone https://github.com/DongDuong2001/project-luvcraft.git /opt/project-luvcraft
cd /opt/project-luvcraft

# Create production environment file
cp .env.local.example .env.local
nano .env.local
```

Fill in your production environment variables in `.env.local`:
- `DATABASE_URL`: Your production Supabase PostgreSQL connection string.
- `CORS_ORIGINS`: Your VPS domain/IP (e.g. `https://luvcraft.example.com,http://YOUR_VPS_IP`).
- `YOUTUBE_API_KEY`, `SERPEX_API_KEY`, `GEMINI_API_KEY`: Real API keys.
- `NEXT_PUBLIC_API_URL`: `https://luvcraft.example.com` or `http://YOUR_VPS_IP` (routed through Nginx proxy, since port 8000 is bound strictly to loopback `127.0.0.1`).

### 3. Deploy Containers via Production Compose (`compose.prod.yaml`)

The production compose override (`compose.prod.yaml`) builds optimized production Next.js assets (`NODE_ENV=production`), starts the full backend stack (FastAPI, Celery Worker, and Celery Beat outbox dispatcher), and binds internal database/broker ports strictly to loopback (`127.0.0.1`):

```bash
# Build and start all production services in detached mode
docker compose -f compose.prod.yaml --env-file .env.local up -d --build

# Run database migrations inside the backend container
docker compose -f compose.prod.yaml exec backend python -m app.db.migrate

# Check status of running production containers
docker compose -f compose.prod.yaml ps
```

### 4. Nginx Reverse Proxy & SSL Setup (Certbot)

To expose the application cleanly over port 80/443 with SSL:

```bash
# Install Nginx and Certbot
sudo apt install -y nginx certbot python3-certbot-nginx

# Create Nginx server block configuration
sudo nano /etc/nginx/sites-available/luvcraft
```

```nginx
server {
    listen 80 default_server;
    server_name luvcraft.example.com YOUR_VPS_IP _;

    # Frontend (Next.js)
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # Backend API (FastAPI)
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# Remove default Nginx site, enable luvcraft site, and test Nginx syntax
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -s /etc/nginx/sites-available/luvcraft /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Obtain SSL Certificate via Let's Encrypt
sudo certbot --nginx -d luvcraft.example.com
```

### 5. VPS Health & Maintenance

- **View Live Logs:** `docker compose -f compose.prod.yaml logs -f`
- **Restart Services:** `docker compose -f compose.prod.yaml restart`
- **Update Application:**
  ```bash
  git pull origin main
  docker compose -f compose.prod.yaml --env-file .env.local up -d --build
  docker compose -f compose.prod.yaml exec backend python -m app.db.migrate
  ```

---

### Access Points

* **Researcher Dashboard:** [http://localhost:3000](http://localhost:3000)
* **Backend API (Swagger UI):** [http://localhost:8000/docs](http://localhost:8000/docs)
* **RabbitMQ Management UI:** [http://localhost:15672](http://localhost:15672), login with `luvcraft` / `luvcraft`
* **Local PostgreSQL:** `localhost:5432`, database `luvcraft`, user `postgres`, password `postgres`

### Supabase Setup

For shared development, staging, or production environments, set `DATABASE_URL` to the Supabase PostgreSQL connection string before starting the backend or Compose stack.

PowerShell:

```powershell
$env:DATABASE_URL = "postgresql://<user>:<password>@<host>:5432/<database>"
docker compose --env-file .env.local up --build
```

macOS/Linux:

```bash
DATABASE_URL="postgresql://<user>:<password>@<host>:5432/<database>" docker compose --env-file .env.local up --build
```

Do not commit real Supabase credentials to the repository.

### Troubleshooting

* If `next build` fails with a Node.js version error, switch to Node.js `24.x`.
* If the backend cannot connect to RabbitMQ, confirm RabbitMQ is running and `CELERY_BROKER_URL` uses the correct host: `rabbitmq` inside Docker, `localhost` outside Docker.
* If the backend cannot connect to PostgreSQL, confirm `DATABASE_URL` points to either Supabase or the local Compose database.
* If ports are already in use, stop the conflicting local services or change the exposed ports in `compose.yaml`.
* If Docker commands fail before containers start, confirm Docker Desktop is running.

## Documentation

* [YouTube Collector MVP Documentation](docs/collector.md)
* [Serpex Public Search Collector](docs/serpex-collector.md)
* [Analysis Layer Architecture](docs/analysis-architecture.md)
* [Analysis Input and Output Contract](docs/analysis-output-schema.md)
* [Engagement Analysis Module](docs/engagement-analysis.md)
* [Sentiment Analysis Module](docs/sentiment-analysis.md)
* [Hybrid LLM Sentiment and Accuracy Validation](docs/hybrid-sentiment.md)

## Contribution & Git Rules

Please refer to [CONTRIBUTING.md](CONTRIBUTING.md) for the mandatory Git Commit Conventions and structural guidelines required by the Project Pluto team.

## Team Members (Project Pluto)

| Member | Role |
| :--- | :--- |
| **Duong Phu Dong** | Technical Leader / Full-stack Developer |
| **Huynh Quang Dong** | Scrum Master / QA Engineer |
| **Ho Quang Huy** | DevOps / Backend Developer |
| **Vu Thien Minh Hao** | Backend Developer / AI Engineer |
| **Tran Vu Nhat Tin** | Frontend Developer |

## Leadership & Supervision

* **Academic Supervisor:** Dr. Kapil Dev
* **Industry Partner:** Project Pluto
* **Company Representatives:** Mr. Danh Pham, Mr. Hien Nguyen, Mr. Gia Kiet

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Security

For vulnerability reporting and disclosures, please see our [Security Policy](SECURITY.md).

