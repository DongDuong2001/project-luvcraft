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

## Production Stage Deployment

Project Luvcraft is deployed live in the production stage on a **DigitalOcean VPS Droplet** under the official Project Pluto company subdomain:

* **Production Web Application:** [https://luvcraft.projectpluto.studio](https://luvcraft.projectpluto.studio)
* **Backend API & Swagger Documentation:** [https://luvcraft.projectpluto.studio/docs](https://luvcraft.projectpluto.studio/docs)
* **Backend Health Check & Database Probe:** [https://luvcraft.projectpluto.studio/health/db](https://luvcraft.projectpluto.studio/health/db)

The production deployment features automated SSL/TLS termination with Let's Encrypt, strict HSTS, secure cross-origin resource sharing, and containerized Next.js and FastAPI services orchestrated with `compose.prod.yaml`.

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

| Variable | Required | Default / Description |
|---|---|---|
| `DATABASE_URL` | Yes | Target database. Use the local Compose default for offline work or a Supabase connection string for shared environments. |
| `MIGRATION_DATABASE_URL` | Optional | Direct PostgreSQL connection string for Alembic migrations if `DATABASE_URL` connects through a transaction pooler. |
| `CELERY_BROKER_URL` | Yes | RabbitMQ connection URL. Use `pyamqp://luvcraft:luvcraft@rabbitmq:5672//` in Docker, `localhost` outside Docker. |
| `CELERY_RESULT_BACKEND` | Optional | Optional Celery task result backend. |
| `CORS_ORIGINS` | Yes | Allowed frontend origins (e.g. `http://localhost:3000,http://127.0.0.1:3000` or production domain). |
| `INTERNAL_EMAIL_DOMAINS` | Optional | Allowed email domains for internal team access (`pluto.studio,projectpluto.studio`). |
| `RBAC_ADMIN_EMAILS` | Optional | Comma-separated list of emails with immediate administrator privileges. |
| `COOKIE_SECURE` | Optional | Set `true` in HTTPS production deployments; `false` in local development. |
| `SUPABASE_URL` | Optional | Supabase project URL for cloud authentication and database management. |
| `SUPABASE_ANON_KEY` | Optional | Supabase anonymous API key for public client authentication. |
| `SUPABASE_JWT_SECRET` | Optional | Supabase JWT secret used by FastAPI for server-side token verification and RBAC. |
| `NEXT_PUBLIC_SUPABASE_URL` | Optional | Frontend public Supabase URL. |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Optional | Frontend public anonymous key. |
| `NEXT_PUBLIC_API_URL` | Optional | Frontend base URL for the backend API (`http://localhost:8000` locally, or production URL). |
| `HTTPS_ONLY` | Optional | Set `true` in HTTPS deployments to enforce HSTS and `upgrade-insecure-requests` CSP. |
| `REPORT_STORAGE_PATH` | Optional | Storage path for generated PDF reports (`data/reports`). |
| `YOUTUBE_API_KEY` | Optional | Google YouTube Data API v3 key for video metadata and comment ingestion. |
| `YOUTUBE_REGION_CODE` | Optional | Default `VN`. Two-letter country code for YouTube search localization. |
| `YOUTUBE_RELEVANCE_LANGUAGE` | Optional | Default `vi`. Preferred language filter for YouTube searches. |
| `YOUTUBE_MAX_RESULTS` | Optional | Default `50`. Maximum number of YouTube search results to ingest per run. |
| `YOUTUBE_MIN_RECORDS_THRESHOLD` | Optional | Default `20`. Minimum signal threshold required for preliminary analysis. |
| `YOUTUBE_TIMEOUT_MAX_RETRIES` | Optional | Default `3`. Number of retry attempts on transient YouTube API timeouts. |
| `YOUTUBE_TIMEOUT_RETRY_DELAY_SECONDS` | Optional | Default `60`. Backoff delay between retried YouTube API calls. |
| `SERPAPI_API_KEY` | Optional | SerpApi key for Google Trends and social-search indexing. |
| `SERPAPI_MAX_RESULTS` | Optional | Default `10`. Search depth per query. |
| `SERPAPI_TIMEOUT_SECONDS` | Optional | Default `10.0`. HTTP request timeout in seconds. |
| `SERPAPI_MAX_ATTEMPTS` | Optional | Default `3`. Maximum retry attempts on network failures. |
| `SERPAPI_COLLECTOR_DEADLINE_SECONDS` | Optional | Default `120`. Maximum time budget for the entire SerpApi collector task. |
| `SERPAPI_LOW_QUOTA_THRESHOLD` | Optional | Default `10`. Minimum remaining API credits before triggering a quota warning. |
| `SERPAPI_RELATED_QUERIES_ENABLED` | Optional | Default `true`. Fetch related queries from Google Trends. |
| `SERPAPI_GEO_TRENDS_ENABLED` | Optional | Default `true`. Fetch geo-interest comparisons across countries. |
| `SERPAPI_GEO_COUNTRIES` | Optional | Default `VN,US,JP`. Target country codes for geo comparisons. |
| `RSS_MAX_RESULTS` | Optional | Default `50`. Maximum number of RSS feed articles to ingest per run. |
| `SOCIALVAULT_API_KEY` | Optional | SociaVault API key for Reddit post and discussion collection. |
| `SENTIMENT_ENGINE` | Optional | Default `hybrid`. Engine choice: `hybrid` (Gemini with lexicon fallback) or `lexicon`. |
| `GEMINI_API_KEY` | Optional | Google Gemini API key for hybrid sentiment, Vibe Check, and Brand-IP fit. |
| `GEMINI_SENTIMENT_MODEL` | Optional | Default `gemini-3.1-flash-lite`. Gemini model used for classification. |
| `SENTIMENT_LLM_FALLBACK_THRESHOLD` | Optional | Default `0.65`. Confidence threshold below which the model falls back to Lexicon. |
| `COMMUNITY_CLASSIFIER_ENGINE` | Optional | Default `hybrid`. Engine choice for community engagement classification. |
| `MOTIVATION_EXTRACTOR_ENGINE` | Optional | Default `hybrid`. Engine choice for audience motivation extraction. |
| `TOPIC_EXTRACTOR_ENGINE` | Optional | Default `hybrid`. Engine choice for thematic subtopic extraction. |
| `DEMAND_EXTRACTOR_ENGINE` | Optional | Default `hybrid`. Engine choice for demand signal and unmet expectation extraction. |
| `COLLABORATION_SEMANTIC_ENGINE` | Optional | Default `hybrid`. Engine choice for Brand-IP qualitative semantic extraction. |
| `GEMINI_COLLABORATION_MODEL` | Optional | Default `gemini-3.1-flash-lite`. Model for Brand-IP analysis. |

---

## Local Development Workflows

### Option 1: Run The Full Stack With Docker Compose (Recommended)

Use this path when the team wants the complete app running with the fewest manual steps.

```bash
docker compose --env-file .env.local up --build
```

The backend applies all pending Alembic migrations before starting the API. When running FastAPI manually from `backend/`, run `python -m app.db.migrate` before starting Uvicorn.

Local Compose pins RabbitMQ to `3.13-management-alpine` for compatibility with the current Celery queue declarations.

For deployed environments, set `DATABASE_URL` to the Supabase PostgreSQL connection string. Local Compose falls back to a development PostgreSQL container when `DATABASE_URL` is not provided.

### Option 2: Run Backend and Frontend Standalone

#### 1. Running Backend & Worker locally

Start the PostgreSQL and RabbitMQ services from the repository root. The standalone API and worker use the host ports published by these containers:

```bash
# From the repository root
cp .env.local.example .env.local
docker compose --env-file .env.local up -d postgres rabbitmq
```

```bash
# Navigate to backend directory
cd backend

# Create and activate virtual environment
python -m venv .venv
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On macOS / Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure the required API keys and secrets in ../.env.local

# Run database migrations
python -m app.db.migrate

# Start FastAPI API Server
python -m uvicorn app.main:app --reload --port 8000

# Start Celery Worker (in a separate terminal)
python -m celery -A app.core.worker.celery_app worker -l info
```

#### 2. Running Frontend locally

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

## DigitalOcean VPS Production Deployment Guide

Project Luvcraft is deployed to production stage on a **DigitalOcean Droplet (VPS)** under the official company subdomain `luvcraft.projectpluto.studio`. This section outlines the production deployment architecture and server configuration.

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
- `CORS_ORIGINS`: `https://luvcraft.projectpluto.studio`
- `NEXT_PUBLIC_API_URL`: `https://luvcraft.projectpluto.studio` (routed through host Nginx proxy; internal port 8000 is bound strictly to loopback `127.0.0.1`).
- `HTTPS_ONLY`: `true` (enforces HTTP Strict Transport Security and Content Security Policy `upgrade-insecure-requests`).
- `COOKIE_SECURE`: `true` (enforces HTTPS-only cookies for authentication tokens).
- `INTERNAL_EMAIL_DOMAINS`: `projectpluto.studio,pluto.studio`
- `YOUTUBE_API_KEY`, `SERPAPI_API_KEY`, `GEMINI_API_KEY`: Real production API keys.

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

Nginx handles SSL/TLS termination on port 443 and routes incoming traffic to internal container endpoints:

```bash
# Install Nginx and Certbot
sudo apt install -y nginx certbot python3-certbot-nginx

# Create Nginx server block configuration
sudo nano /etc/nginx/sites-available/luvcraft
```

Start with an HTTP-only server block so Nginx can load before any certificate files exist:

```nginx
server {
    listen 80;
    server_name luvcraft.projectpluto.studio;

    # Security Headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;

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

    # OpenAPI Documentation
    location /docs {
        proxy_pass http://127.0.0.1:8000/docs;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /openapi.json {
        proxy_pass http://127.0.0.1:8000/openapi.json;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Health Checks
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# Remove the default site, enable the HTTP-only site, and verify it before reload
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -s /etc/nginx/sites-available/luvcraft /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Obtain the certificate and let Certbot add the HTTPS server block and redirect
sudo certbot --nginx --redirect -d luvcraft.projectpluto.studio

# Verify the generated TLS configuration
sudo nginx -t
sudo systemctl reload nginx
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

#### Production Stage (Company Subdomain)

* **Production Dashboard:** [https://luvcraft.projectpluto.studio](https://luvcraft.projectpluto.studio)
* **Production API (Swagger UI):** [https://luvcraft.projectpluto.studio/docs](https://luvcraft.projectpluto.studio/docs)
* **Production Health Check:** [https://luvcraft.projectpluto.studio/health/db](https://luvcraft.projectpluto.studio/health/db)

#### Local Development Access Points

* **Local Dashboard:** [http://localhost:3000](http://localhost:3000)
* **Local Backend API (Swagger UI):** [http://localhost:8000/docs](http://localhost:8000/docs)
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
