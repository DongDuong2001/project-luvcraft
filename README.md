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

**Project Luvcraft** is developed with **Project Pluto** as the industry partner. The platform aggregates public market signals, tracks hype cycles, measures community sentiment across multiple social channels, and uses Large Language Models (LLMs) to generate multi-dimensional brand collaboration insights, qualitative Vibe Check syntheses, and strategic market intelligence for entertainment and gaming fandom research.

---

## Key Features & Capabilities

* **Multi-Channel Signal Ingestion:** Asynchronous, fault-tolerant ingestion pipelines gathering signals from YouTube Data API v3 (videos and comments), Reddit (via SociaVault), Google Trends and Social SERP (via SerpApi), and curated RSS/Atom publications.
* **Hybrid AI Intelligence Layer:** Combines statistical methods with Google Gemini 3.1 Flash-Lite (`gemini-3.1-flash-lite`) LLM reasoning for sentiment classification, qualitative Vibe Check synthesis, and Brand-IP collaboration fit, backed by deterministic rule-based lexicon fallbacks for offline resilience.
* **Qualitative Vibe Check Synthesis:** Generates evidence-linked qualitative summaries, audience posturing, sentiment trajectories, and community health indicators with zero unbacked claims.
* **Quantitative Brand-IP Collaboration Fit:** Evaluates prospective IP collaboration candidates against internal brand profiles with customizable metric weights, proportional auto-balancing, transparent score breakdowns, and multi-candidate comparative tables.
* **Interactive Executive Dashboard:** Built with Next.js 16 (Turbopack), React 19, and Tailwind CSS. Features an animated 4-stage pipeline execution stepper, adaptive KPI grid (1-col mobile to 4-col desktop), responsive volume trajectory charts, and an accessible tabbed deep audit explorer.
* **Multi-Tier Role-Based Access Control (RBAC):** Server-authoritative role governance (`admin`, `analyst`, `client`, `viewer`) with Supabase OAuth (Google Workspace, Microsoft Entra), session isolation, and audit logging.
* **Anomaly & Geo-Divergence Detection:** Automatically flags volume anomalies, sudden sentiment shifts, regional attention variations, and cross-platform divergences with severity metrics and root-cause evidence.
* **Board-Ready PDF & Print Export:** Generates deterministic server-side PDF reports and features dedicated high-contrast `@media print` styling for board-ready executive summaries.

---

## Tech Stack

**Frontend:**
* Next.js 16 & React 19 (Turbopack)
* Tailwind CSS & Phosphor Icons
* Recharts (Responsive Data Visualizations)
* Vitest & React Testing Library (Unit & Integration Testing)

**Backend:**
* Python 3.12 & FastAPI (REST API Engine)
* Celery & RabbitMQ (Distributed Task Queue & Outbox Pattern)
* SQLAlchemy 2.0 & PostgreSQL / Supabase (Data Persistence & Row-Level Security)
* Pydantic v2 (Strict Schema Validation)
* ReportLab (Deterministic PDF Report Generation)

**AI & Natural Language Processing:**
* **Google Gemini LLM (`gemini-3.1-flash-lite`):** Powers qualitative Vibe Check synthesis (`GeminiVibeCheckProvider`), structured collaboration fit analysis (`GeminiCollabFitProvider`), and context-aware sentiment classification (`GeminiSentimentProvider`).
* **Deterministic Fallback Layer:** Offline rule-based scoring and fallback providers (`RuleBasedVibeCheckProvider`, `RuleBasedCollabFitProvider`) ensuring resilience if network access or API quotas are exhausted.

**Infrastructure & Operations:**
* Docker Compose for local full-stack orchestration (`compose.yaml`)
* Production Docker Compose specification (`compose.prod.yaml`) for VPS deployment
* RabbitMQ persistent message broker (`3.13-management-alpine`)
* Supabase PostgreSQL for cloud production database with connection pooling
* Local PostgreSQL container for isolated offline development

---

## Architecture & Structure

The repository follows a clean, modular, cloud-ready monorepo structure:

```text
project-luvcraft/
|-- backend/                 # Core API and worker services
|   |-- app/collectors/      # Modular scrapers (YouTube, Reddit, SerpApi, RSS)
|   |-- app/analysis/        # Canonical contracts and analytical modules
|   |-- app/services/        # LLM intelligence, Vibe Check, and reporting modules
|   `-- app/db/              # PostgreSQL models, repositories, and migrations
|-- frontend/                # Next.js 16 researcher dashboard UI
|   |-- components/          # Reusable UI, layout, and domain section components
|   |-- pages/               # Application routes (dashboard, login, auth, access)
|   `-- state/               # Authentication and dashboard context stores
|-- docs/                    # Architectural specifications and module documentation
|-- compose.yaml             # Local development Docker Compose stack
|-- compose.prod.yaml        # Production VPS Docker Compose stack
`-- CONTRIBUTING.md          # Mandatory Git conventions and team rules
```

---

## Running The Project

### Prerequisites

Install the following tools before running the project locally:

* [Docker Desktop](https://www.docker.com/products/docker-desktop) for the full local stack.
* Node.js `24.x` and npm `11.x` for local frontend development.
* Python `3.12` for local backend development outside Docker.
* A Supabase PostgreSQL connection string when using the shared cloud database.

The project can run with either Supabase PostgreSQL or the local PostgreSQL container from `compose.yaml`. For normal local development, Docker Compose is the fastest setup because it starts the frontend, backend, Celery worker, Celery Beat dispatcher, PostgreSQL, and RabbitMQ together.

### Environment Variables

Use `.env.local.example` as the local setup template. Copy it to `.env.local` when running the Docker Compose or backend flow, then fill in secrets only in your local `.env.local`. Keep `.env.local.example` free of real API keys so teammates do not accidentally commit or reuse private credentials.

| Variable | Used By | Local Default | Notes |
| :--- | :--- | :--- | :--- |
| `DATABASE_URL` | Backend, Celery | `postgresql://postgres:postgres@localhost:5432/luvcraft` outside Docker, `postgresql://postgres:postgres@postgres:5432/luvcraft` inside Compose | Set this to the Supabase PostgreSQL connection string for shared environments. |
| `MIGRATION_DATABASE_URL` | Backend migration command | None | Optional direct PostgreSQL URL for Alembic when `DATABASE_URL` uses a pooler. |
| `CELERY_BROKER_URL` | Backend, Celery | `pyamqp://luvcraft:luvcraft@localhost:5672//` outside Docker, `pyamqp://luvcraft:luvcraft@rabbitmq:5672//` inside Compose | RabbitMQ persistent message broker. |
| `CELERY_RESULT_BACKEND` | Celery | `db+<DATABASE_URL>` | Optional. The backend defaults to storing Celery results in PostgreSQL. |
| `CORS_ORIGINS` | Backend | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated frontend origins allowed to call the FastAPI service. |
| `YOUTUBE_API_KEY` | Backend, Celery | None | YouTube Data API v3 key for video and comment collection. |
| `YOUTUBE_REGION_CODE` | Backend, Celery | `VN` | YouTube search region filter. |
| `YOUTUBE_RELEVANCE_LANGUAGE` | Backend, Celery | `vi` | YouTube search relevance language and persisted signal language. |
| `YOUTUBE_MAX_RESULTS` | Celery | `50` | Maximum videos requested per YouTube search. |
| `YOUTUBE_MIN_RECORDS_THRESHOLD` | Celery | `20` | Minimum persisted YouTube signals before omitting the insufficient-data warning. |
| `YOUTUBE_TIMEOUT_MAX_RETRIES` | Celery | `3` | Maximum Celery retries for transient YouTube timeout errors. |
| `YOUTUBE_TIMEOUT_RETRY_DELAY_SECONDS` | Celery | `60` | Delay between retries after a transient YouTube timeout. |
| `SERPAPI_API_KEY` | Celery | None | SerpApi key for Google Trends and public social SERP collection. |
| `SERPAPI_MAX_RESULTS` | Celery | `10` | Maximum organic or related-query results retained per request. |
| `SERPAPI_TIMEOUT_SECONDS` | Celery | `10` | Maximum timeout for one SerpApi request. |
| `SERPAPI_MAX_ATTEMPTS` | Celery | `3` | Total request attempts including the initial request. |
| `SERPAPI_RETRY_INITIAL_DELAY_SECONDS` | Celery | `5` | Initial delay for SerpApi exponential backoff. |
| `SERPAPI_RETRY_MAX_DELAY_SECONDS` | Celery | `30` | Maximum delay cap for SerpApi retries. |
| `SERPAPI_COLLECTOR_DEADLINE_SECONDS` | Celery | `120` | End-to-end deadline before persistence and analysis. |
| `SERPAPI_MAX_REQUESTS_PER_RUN` | Celery | `5` | Hard successful-search budget per run. |
| `SERPAPI_LOW_QUOTA_THRESHOLD` | Celery | `10` | Trends requests stop at or below this remaining-credit threshold. |
| `SERPAPI_RELATED_QUERIES_ENABLED` | Celery | `true` | Enables related queries collection from Google Trends. |
| `SERPAPI_GEO_TRENDS_ENABLED` | Celery | `true` | Enables regional breakdown collection. |
| `SERPAPI_GEO_COUNTRIES` | Celery | `VN,US,JP` | Comma-separated ISO country codes for regional comparisons. |
| `SERPAPI_GEO_RELATED_COUNTRY_LIMIT` | Celery | `1` | Country limit for related queries extraction. |
| `RSS_MAX_RESULTS` | Celery | `50` | Maximum relevant RSS/Atom articles retained per research run. |
| `RSS_TIMEOUT_SECONDS` | Celery | `15` | Timeout for one RSS/Atom feed request. |
| `RSS_MAX_RETRIES` | Celery | `3` | Maximum retries for transient RSS network failures. |
| `RSS_RETRY_DELAY_SECONDS` | Celery | `30` | Delay between transient RSS retries. |
| `SOCIALVAULT_API_KEY` | Celery | None | SociaVault API key used for public Reddit post and comment collection. |
| `SOCIALVAULT_MAX_RESULTS` | Celery | `50` | Maximum retained Reddit posts per research run. |
| `SOCIALVAULT_TIMEOUT_SECONDS` | Celery | `15` | Timeout for each SociaVault request. |
| `SOCIALVAULT_MAX_RETRIES` | Celery | `3` | Retry budget for transient and quota failures. |
| `SOCIALVAULT_RETRY_DELAY_SECONDS` | Celery | `10` | Delay between SociaVault task retries. |
| `SOCIALVAULT_SUBREDDITS` | Celery | Empty | Optional comma-separated subreddit names; empty searches globally. |
| `SENTIMENT_ENGINE` | Backend, Celery | `hybrid` | Uses cost-controlled Gemini classification with deterministic lexicon fallback. |
| `PRELIMINARY_MIN_SIGNALS` | Backend, Celery | `20` | Minimum non-spam signals before a preliminary snapshot is published. |
| `GEMINI_API_KEY` | Backend, Celery | None | Google Gemini API key. Keep only in `.env.local`; never commit. |
| `GEMINI_SENTIMENT_MODEL` | Backend, Celery | `gemini-3.1-flash-lite` | Configurable Gemini sentiment classification model. |
| `GEMINI_SENTIMENT_PROMPT_VERSION` | Backend, Celery | `sentiment-gemini-v1` | Version tag for caching and result provenance. |
| `SENTIMENT_LLM_FALLBACK_THRESHOLD` | Backend, Celery | `0.65` | Confidence threshold below which signals are escalated to Gemini. |
| `COMMUNITY_CLASSIFIER_ENGINE` | Backend, Celery | `hybrid` | Community posture and toxicity classifier engine (`hybrid` or `rules`). |
| `GEMINI_COMMUNITY_MODEL` | Backend, Celery | `gemini-3.1-flash-lite` | Community posture and audience engagement model. |
| `MOTIVATION_EXTRACTOR_ENGINE` | Backend, Celery | `hybrid` | Semantic opinion and motivation extractor (`hybrid` or `rules`). |
| `GEMINI_MOTIVATION_MODEL` | Backend, Celery | `gemini-3.1-flash-lite` | Structured likes, dislikes, praise, and complaints extractor. |
| `TOPIC_EXTRACTOR_ENGINE` | Backend, Celery | `hybrid` | Semantic subtopic extraction engine with deterministic momentum assignment. |
| `GEMINI_TOPIC_MODEL` | Backend, Celery | `gemini-3.1-flash-lite` | Subtopic extraction model. |
| `DEMAND_EXTRACTOR_ENGINE` | Backend, Celery | `hybrid` | Demand and information-need extraction engine. |
| `GEMINI_DEMAND_MODEL` | Backend, Celery | `gemini-3.1-flash-lite` | Structured feature request and FAQ model. |
| `COLLABORATION_SEMANTIC_ENGINE` | Backend, Celery | `hybrid` | Brand-IP semantic interpretation engine (`hybrid` or `rules_only`). |
| `GEMINI_COLLABORATION_MODEL` | Backend, Celery | `gemini-3.1-flash-lite` | Model used for evidence-linked Brand-IP compatibility. |
| `SUPABASE_URL` | Backend, Frontend | `https://your-project.supabase.co` | Supabase project URL for authentication. |
| `SUPABASE_ANON_KEY` | Backend, Frontend | None | Supabase public anonymous key. |
| `SUPABASE_JWT_SECRET` | Backend | None | Supabase JWT signing secret for server-side token verification. |
| `INTERNAL_EMAIL_DOMAINS` | Backend | `pluto.studio,projectpluto.studio` | Domains automatically granted internal staff profiles. |
| `RBAC_ADMIN_EMAILS` | Backend | None | Comma-separated emails granted administrative privileges upon login. |
| `COOKIE_SECURE` | Backend | `false` | Set to `true` in production to enforce `Secure; SameSite=None` auth cookies. |
| `NEXT_PUBLIC_API_URL` | Frontend | `http://localhost:8000` | FastAPI base URL without `/api/v1` suffix. |
| `NEXT_PUBLIC_SUPABASE_URL` | Frontend | `https://your-project.supabase.co` | Public Supabase endpoint for browser OAuth redirects. |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Frontend | None | Public Supabase client key. |
| `HTTPS_ONLY` | Frontend build | `false` | Enables HSTS and CSP `upgrade-insecure-requests` for HTTPS-only production. |
| `REPORT_STORAGE_PATH` | Backend | `data/reports` | Directory where generated PDF and XLSX exports are persisted. |

---

### Option 1: Run The Full Stack With Docker Compose

Use this path for the easiest complete setup:

```bash
docker compose --env-file .env.local up --build
```

The backend automatically runs pending Alembic migrations before starting the API server. RabbitMQ is pinned to `3.13-management-alpine` for queue compatibility.

### Option 2: Run Backend and Frontend Standalone (Development Mode)

#### 1. Start Database & Message Broker Infrastructure

```bash
# Start background PostgreSQL and RabbitMQ containers
docker compose up -d postgres rabbitmq
```

#### 2. Running Backend, Celery Worker & Beat Dispatcher

```bash
cd backend

# Create and activate virtual environment
python -m venv .venv
# On Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# On macOS / Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run database migrations
python -m app.db.migrate

# Start FastAPI API Server (Terminal 1)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Start Celery Worker (Terminal 2)
python -m celery -A app.core.worker.celery_app worker -l info

# Start Celery Beat for scheduled jobs and outbox dispatch (Terminal 3)
python -m celery -A app.core.worker.celery_app beat -l info
```

#### 3. Running Frontend

```bash
cd frontend

# Install Node.js dependencies
npm install

# Start Next.js development server
npm run dev
```

The frontend will be available at [http://localhost:3000](http://localhost:3000) and will communicate with FastAPI at `http://localhost:8000`.

---

## Running Tests

### Frontend Test Suite (Vitest & Testing Library)

```bash
cd frontend

# Run all unit and integration tests (66 tests across 17 test suites)
npm test

# Run Next.js production build verification
npm run build
```

### Backend Test Suite (Pytest)

Ensure dependencies are installed (`pip install -r requirements.txt`) and your virtual environment is active.

#### On Windows (PowerShell from workspace root):

```powershell
$env:PYTHONPATH = "backend"
$env:SENTIMENT_ENGINE = "lexicon"

# Run all analytical and API test suites
backend\.venv\Scripts\pytest backend/app/tests/

# Run specific analytical test files
backend\.venv\Scripts\pytest backend/app/tests/test_collab_fit.py
backend\.venv\Scripts\pytest backend/app/tests/test_api_vibe_check.py
```

#### On macOS / Linux:

```bash
cd backend
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
- `YOUTUBE_API_KEY`, `SERPAPI_API_KEY`, `GEMINI_API_KEY`: Real API keys.
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

---

## Technical Documentation Index

Detailed architectural specifications and analytical research documentation are organized in the [`docs/`](docs/) directory:

### Architecture & Data Contracts
* [Unified Analysis Pipeline](docs/unified-analysis-pipeline.md): Comprehensive reference for the sequential analytical lifecycle and stage gates.
* [Analysis Layer Architecture](docs/analysis-architecture.md): Service boundaries, repository design patterns, and state machines.
* [Analysis Output Schema](docs/analysis-output-schema.md): Standard JSON contracts and analytical payload schemas.
* [Database Schema](docs/schema.md): PostgreSQL table schemas, entity-relationship diagrams, and Alembic migrations.

### Data Ingestion & Collectors
* [YouTube Collector MVP](docs/collector.md): Video search, comment thread ingestion, rate limiting, and quota management.
* [SerpApi Trends & Social SERP](docs/serpapi-collector.md): Google Trends historical interest and public social search pipelines.
* [RSS/Atom Publication Collector](docs/rss-collector.md): Curated media feed parsing, deduplication, and signal extraction.

### Intelligence & Analytical Models
* [Vibe Check Qualitative Synthesis](docs/vibe-check-framework.md): Citation-backed qualitative fandom dynamics and thematic synthesis.
* [Brand-IP Collaboration Fit](docs/brand-ip-collaboration.md): Quantitative fit scoring, candidate evaluation, and risk detection.
* [Hybrid Sentiment Engine](docs/hybrid-sentiment.md): Gemini LLM classification with cost-controlled deterministic fallback.
* [Sentiment Analysis Module](docs/sentiment-analysis.md): Algorithmic Lexicon weighting and polarity boundaries.
* [Community Motivation Analysis](docs/community-motivation-analysis.md): Semantic extraction of audience likes, dislikes, praise, and complaints.
* [Demand Themes & Narrative Extraction](docs/demand-themes-and-reports.md): Unmet expectations, frequently asked questions, and thematic momentum.
* [Cross-Source Confidence Scoring](docs/cross-source-confidence.md): Multi-channel signal agreement and scoring reliability telemetry.
* [Engagement Velocity Analysis](docs/engagement-analysis.md): Interaction rates, velocity curves, and volume spike detection.

### Security, Authentication & Governance
* [Role-Based Access Control (RBAC)](docs/rbac.md): Server-authoritative role governance (`admin`, `analyst`, `client`, `viewer`).
* [Supabase SSO Frontend Integration](docs/sso-frontend-integration.md): Google Workspace and Microsoft Entra OAuth configuration and cookie management.

### Verification & Quality Reports
* [Frontend E2E Integration Test Report](docs/e2e-frontend-integration-test-report.md): Vitest and React Testing Library validation coverage.
* [Capstone Metrics & Performance Report](docs/capstone_metrics_report.md): Latency benchmarks, memory utilization, and collector throughput.

---

## Contribution & Git Rules

Please refer to [CONTRIBUTING.md](CONTRIBUTING.md) for the mandatory Git Commit Conventions and structural guidelines required by the Project Pluto team.

---

## Team Members (Project Pluto)

| Member | Role |
| :--- | :--- |
| **Duong Phu Dong** | Technical Leader / Full-stack Developer |
| **Huynh Quang Dong** | Scrum Master / QA Engineer |
| **Ho Quang Huy** | Hybrid Backend and AI Engineer |
| **Vu Thien Minh Hao** | Backend Developer |
| **Tran Vu Nhat Tin** | Backend / Data Analyst |

---

## Leadership & Supervision

* **Academic Supervisor:** Dr. Kapil Dev
* **Industry Partner:** Project Pluto
* **Company Representatives:** Mr. Danh Pham, Mr. Hien Nguyen, Mr. Gia Kiet

---

## License

This software and its analytical models are proprietary to **Project Pluto** and **Team Nightswatch (RMIT University Vietnam)**. Commercial deployment, reproduction, or distribution requires an explicit commercial agreement with Project Pluto. For licensing inquiries, contact [creative@projectpluto.studio](mailto:creative@projectpluto.studio). See the [LICENSE](LICENSE) file for complete details.

---

## Security

For vulnerability reporting and disclosures, please see our [Security Policy](SECURITY.md).
